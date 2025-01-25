import time
import serial
import pynmea2
import firebase_admin
from firebase_admin import credentials, firestore, db
from geopy.distance import geodesic
from datetime import datetime, timedelta
import re
import os
import psutil
import subprocess
from picamera2 import Picamera2
import cv2
import libcamera
import csv
import threading
from queue import Queue
import requests
from io import BytesIO

# Initialize Firebase Firestore
cred = credentials.Certificate(
    "/home/k/Desktop/mybus/my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://my-bus-421811-default-rtdb.firebaseio.com/'
})
firestore_db = firestore.client()
realtime_db = db.reference('gps_locations')

# Create queues for GPS data
gps_queue = Queue(maxsize=100)
location_queue = Queue(maxsize=100)

############################################################################################
### Helper Functions
############################################################################################

def get_bus_stops():
    bus_stops_ref = firestore_db.collection('Bus-stations')
    docs = bus_stops_ref.stream()
    bus_stops = []
    for doc in docs:
        stop_data = doc.to_dict()
        stop_data['loc'] = (stop_data['loc'].latitude, stop_data['loc'].longitude)
        bus_stops.append(stop_data)
    return bus_stops

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def get_system_stats():
    memory = psutil.virtual_memory()
    memory_usage = memory.percent
    uptime = subprocess.check_output("awk '{print $1}' /proc/uptime", shell=True).decode().strip()
    uptime_seconds = float(uptime)
    uptime_readable = str(timedelta(seconds=uptime_seconds))
    temp_output = subprocess.check_output("vcgencmd measure_temp", shell=True).decode().strip()
    temperature = float(re.search(r"temp=([\d.]+)", temp_output).group(1))
    
    return {
        "memory_usage": memory_usage,
        "uptime": uptime_readable,
        "temperature": temperature,
    }

def find_closest_bus_stop(current_location, bus_stops, current_stop):
    closest_stop = current_stop if current_stop else None
    min_distance = float('inf')
    for stop in bus_stops:
        stop_location = stop['loc']
        distance = geodesic(current_location, stop_location).meters
        if distance < min_distance and distance < 30:
            min_distance = distance
            closest_stop = stop
    return closest_stop, min_distance

def determine_bus_stops(current_location, bus_stops, line, on_return_trip, current_stop):
    route_u_stops = [stop for stop in bus_stops if 'u' in stop['id']]
    route_b_stops = [stop for stop in bus_stops if 'b' in stop['id']]
    route_u_stops.sort(key=lambda x: natural_sort_key(x['id']))
    route_b_stops.sort(key=lambda x: natural_sort_key(x['id']))
    combined_route_stops = route_u_stops + route_b_stops
    if on_return_trip:
        combined_route_stops.reverse()
    if current_stop is None:
        current_stop = combined_route_stops[0]
    else:
        current_stop, _ = find_closest_bus_stop(current_location, combined_route_stops, current_stop)
    if current_stop:
        current_index = combined_route_stops.index(current_stop)
        if not on_return_trip and current_stop['id'] == 'b5':
            on_return_trip = True
            combined_route_stops.reverse()
            current_index = combined_route_stops.index(current_stop)
        next_stop = combined_route_stops[current_index + 1] if current_index + 1 < len(combined_route_stops) else None
        return current_stop, next_stop, on_return_trip
    return None, None, on_return_trip

def estimate_time_to_next_stop(current_location, next_stop_location, speed_mps):
    distance = geodesic(current_location, next_stop_location).meters
    time_seconds = distance / speed_mps
    minutes, seconds = divmod(time_seconds, 60)
    return int(minutes), int(seconds)

def send_gps_data(lat, lon, bus_id, current_stop, next_stop, time_to_next_stop, system_stats, current_time):
    estimated_time = timedelta(minutes=time_to_next_stop[0], seconds=time_to_next_stop[1]) if time_to_next_stop else None
    data = {
        'latitude': lat,
        'longitude': lon,
        'bus_id': bus_id,
        'current_stop': current_stop['name'] if current_stop else None,
        'next_stop': next_stop['name'] if next_stop else None,
        'estimated': str(estimated_time) if estimated_time else None,
        **system_stats
    }
    realtime_db.update(data)

    # Write data to CSV file
    csv_writer.writerow([
        lat,
        lon,
        bus_id,
        current_stop['name'] if current_stop else 'N/A',
        next_stop['name'] if next_stop else 'N/A',
        str(estimated_time) if estimated_time else 'None',
        current_time if current_time else 'N/A'
    ])

def check_and_handle_system_commands():
    try:
        shutdown = realtime_db.child('shutdown').get()
        reboot = realtime_db.child('reboot').get()

        if shutdown:
            print("Shutdown command received. Initiating shutdown sequence...")
            realtime_db.update({'shutdown': False})
            os.system('sudo killall python')
            time.sleep(3)
            os.system('sudo shutdown now')

        if reboot:
            print("Reboot command received. Initiating reboot sequence...")
            realtime_db.update({'reboot': False})
            os.system('sudo killall python')
            time.sleep(3)
            os.system('sudo reboot')

    except Exception as e:
        print(f"Error handling system commands: {e}")

############################################################################################
### Camera Streamer Class
############################################################################################

class CameraStreamer:
    def __init__(self, server_url, picam2, max_dimension=480, quality=80, buffer_size=30):
        self.server_url = server_url
        self.picam2 = picam2
        self.max_dimension = max_dimension
        self.quality = quality
        self.frame_queue = Queue(maxsize=buffer_size)
        self.running = True
        self.sender_thread = threading.Thread(target=self._send_frames)
        self.sender_thread.daemon = True
        self.sender_thread.start()

    def resize_frame(self, frame):
        height, width = frame.shape[:2]
        if height > width and height > self.max_dimension:
            ratio = self.max_dimension / height
            new_size = (int(width * ratio), self.max_dimension)
            return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
        elif width > self.max_dimension:
            ratio = self.max_dimension / width
            new_size = (self.max_dimension, int(height * ratio))
            return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)
        return frame

    def preprocess_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return self.resize_frame(gray)

    def queue_frame(self, frame):
        try:
            processed_frame = self.preprocess_frame(frame)
            if not self.frame_queue.full():
                self.frame_queue.put_nowait(processed_frame)
        except Exception as e:
            print(f"Error queuing frame: {e}")

    def _send_frames(self):
        while self.running:
            try:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get()
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                    
                    response = requests.post(
                        self.server_url, 
                        files={'frame': ('frame.jpg', BytesIO(buffer.tobytes()), 'image/jpeg')},
                        timeout=5
                    )
                    
                    if response.status_code == 200:
                        print("Frame sent successfully")
                    else:
                        print(f"Error sending frame: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Network error: {e}")
            except Exception as e:
                print(f"Error in send_frame: {e}")
            time.sleep(0.1)

    def stop(self):
        self.running = False
        self.sender_thread.join()

############################################################################################
### GPS Thread Classes
############################################################################################

class GPSReader(threading.Thread):
    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True

    def run(self):
        while self.running:
            try:
                line = self.serial_port.readline().decode('ascii', errors='replace').strip()
                if line.startswith('$'):
                    gps_queue.put(line)
            except Exception as e:
                print(f"Error reading GPS data: {e}")
                time.sleep(0.1)

    def stop(self):
        self.running = False

class GPSProcessor(threading.Thread):
    def __init__(self, bus_id, bus_stops):
        super().__init__()
        self.bus_id = bus_id
        self.bus_stops = bus_stops
        self.running = True
        self.current_stop = None
        self.on_return_trip = False
        self.bus_speed_mps = 12

    def run(self):
        while self.running:
            try:
                if not gps_queue.empty():
                    line = gps_queue.get()
                    msg = pynmea2.parse(line)
                    
                    if isinstance(msg, pynmea2.types.talker.RMC):
                        lat, lon = msg.latitude, msg.longitude
                        current_location = (lat, lon)
                        location_queue.put((lat, lon))
                        
                        # Determine bus stops
                        self.current_stop, next_stop, self.on_return_trip = determine_bus_stops(
                            current_location, self.bus_stops, line=5, 
                            on_return_trip=self.on_return_trip, 
                            current_stop=self.current_stop
                        )
                        
                        # Estimate time to next stop
                        time_to_next_stop = (
                            estimate_time_to_next_stop(current_location, next_stop['loc'], self.bus_speed_mps) 
                            if next_stop else None
                        )
                        
                        # Get system stats and current time
                        system_stats = get_system_stats()
                        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Send GPS data and system stats to Firebase
                        send_gps_data(lat, lon, self.bus_id, self.current_stop, next_stop, 
                                    time_to_next_stop, system_stats, current_time)
                        
                        # Check system commands
                        check_and_handle_system_commands()
                        
            except Exception as e:
                print(f"Error processing GPS data: {e}")
                time.sleep(0.1)

    def stop(self):
        self.running = False

############################################################################################
### Main Function
############################################################################################

def main():
    try:
        # Initialize serial port
        ser = serial.Serial(
            port='/dev/ttyS0',
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=0.1
        )

        # Initialize variables
        bus_id = "5"
        bus_stops = get_bus_stops()

        # Initialize camera
        picam2 = Picamera2()
        preview_config = picam2.create_preview_configuration(
            main={"size": (1640, 1232)},
            lores={"size": (640, 480)},
            display="lores",
            transform=libcamera.Transform(hflip=0, vflip=0, rotation=180)
        )
        picam2.configure(preview_config)
        picam2.start()

        # Initialize camera streamer
        SERVER_URL = "http://busfeed.svel-co.com/upload"
        camera_streamer = CameraStreamer(SERVER_URL, picam2)

        # Initialize video writer
        test_time = datetime.now().strftime("%Y-%m-%d%H:%M:%S")
        output_filename = f"/home/k/Desktop/mybus/recorded_video.avi"
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        fps = 15
        frame_size = (640, 480)
        out = cv2.VideoWriter(output_filename, fourcc, fps, frame_size)

        # Initialize CSV writer
        global csv_writer  # Make csv_writer global so it can be accessed by send_gps_data
        csv_file = open(f'bus_data{test_time}.csv', mode='w', newline='')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['Latitude', 'Longitude', 'Bus ID', 'Current Stop', 
                           'Next Stop', 'Estimated Time', 'Current Time'])

        # Start GPS threads
        gps_reader = GPSReader(ser)
        gps_processor = GPSProcessor(bus_id, bus_stops)
        
        gps_reader.start()
        gps_processor.start()

        # Main loop for camera operations
        while True:
            frame = picam2.capture_array()
            
            if not location_queue.empty():
                lat, lon = location_queue.get()
                current_location = (lat, lon)
                
                if gps_processor.current_stop:
                    current_distance = geodesic(current_location, 
                                             gps_processor.current_stop['loc']).meters
                    
                    if current_distance <= 20:
                        camera_streamer.queue_frame(frame)

            out.write(frame)

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Cleanup
        camera_streamer.stop()
        gps_reader.stop()
        gps_processor.stop()
        gps_reader.join()
        gps_processor.join()
        out.release()
        picam2.stop()
        cv2.destroyAllWindows()
        csv_file.close()
        ser.close()

if __name__ == "__main__":
    main()