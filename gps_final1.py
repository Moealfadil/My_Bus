#!/usr/bin/env python
import time
import serial
import pynmea2
import firebase_admin
from firebase_admin import credentials, firestore, db
from geopy.distance import geodesic
from datetime import timedelta
import re

# Initialize Firebase Firestore
cred = credentials.Certificate(
    "/home/mb/Desktop/Mybus/alfadil/My_Bus/my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://my-bus-421811-default-rtdb.firebaseio.com/'
})
firestore_db = firestore.client()
realtime_db = db.reference('gps_locations')

# Function to sort stops naturally
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# Function to get bus stop data from Firestore
def get_bus_stops():
    bus_stops_ref = firestore_db.collection('Bus-stations')
    docs = bus_stops_ref.stream()
    bus_stops = []
    for doc in docs:
        stop_data = doc.to_dict()
        stop_data['loc'] = (stop_data['loc'].latitude, stop_data['loc'].longitude)
        bus_stops.append(stop_data)
    return bus_stops

# Function to find the closest bus stop
def find_closest_bus_stop(current_location, bus_stops, current_stop):
    closest_stop = current_stop if current_stop else None
    min_distance = float('inf')
    for stop in bus_stops:
        stop_location = stop['loc']
        distance = geodesic(current_location, stop_location).meters
        if distance < min_distance and distance < 5:
            min_distance = distance
            closest_stop = stop
    return closest_stop, min_distance

# Function to determine the current and next bus stop
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

# Function to estimate time to next stop
def estimate_time_to_next_stop(current_location, next_stop_location, speed_mps):
    distance = geodesic(current_location, next_stop_location).meters
    time_seconds = distance / speed_mps
    minutes, seconds = divmod(time_seconds, 60)
    return int(minutes), int(seconds)

# Function to send data to Firebase Realtime Database
def send_gps_data(lat, lon, passengers, bus_id, current_stop, next_stop, time_to_next_stop):
    estimated_time = timedelta(minutes=time_to_next_stop[0], seconds=time_to_next_stop[1]) if time_to_next_stop else None
    data = {
        'latitude': lat,
        'longitude': lon,
        'passengers': passengers,
        'bus_id': bus_id,
        'current_stop': current_stop['name'] if current_stop else None,
        'next_stop': next_stop['name'] if next_stop else None,
        'estimated': str(estimated_time) if estimated_time else None
    }
    realtime_db.set(data)

# Setup Serial for GPS
ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# Initialize variables
bus_id = "5"
bus_speed_mps = 15  # Assumed bus speed in m/s (e.g., 10 m/s ~ 36 km/h)
passengers = 50     # Example passengers count
bus_stops = get_bus_stops()
on_return_trip = False
current_stop = None

# Loop to read GPS and update Firebase
while True:
    try:
        line = ser.readline().decode('ascii', errors='replace').strip()
        if line.startswith('$'):
            msg = pynmea2.parse(line)
            if isinstance(msg, pynmea2.types.talker.GGA):
                lat, lon = msg.latitude, msg.longitude
                current_location = (lat, lon)
                
                # Determine bus stops
                current_stop, next_stop, on_return_trip = determine_bus_stops(
                    current_location, bus_stops, line=5, on_return_trip=on_return_trip, current_stop=current_stop
                )
                
                # Estimate time to next stop
                time_to_next_stop = (
                    estimate_time_to_next_stop(current_location, next_stop['loc'], bus_speed_mps) if next_stop else None
                )

                # Send GPS data to Firebase
                send_gps_data(lat, lon, passengers, bus_id, current_stop, next_stop, time_to_next_stop)

                # Print information for debugging
                print(f"Current Location: {lat}, {lon}")
                if current_stop:
                    print(f"Current Stop: {current_stop['name']} ({current_stop['loc']})")
                if next_stop:
                    print(f"Next Stop: {next_stop['name']} ({next_stop['loc']})")
                if time_to_next_stop:
                    print(f"Estimated Time to Next Stop: {time_to_next_stop[0]} minutes and {time_to_next_stop[1]} seconds")
                else:
                    print("Estimated Time to Next Stop: None")

    except pynmea2.ParseError as e:
        print("NMEA Parse error:", e)
    except Exception as e:
        print("An error occurred:", e)
    
    time.sleep(1)
