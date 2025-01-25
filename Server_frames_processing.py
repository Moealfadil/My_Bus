from flask import Flask, request, Response, render_template
import os
from datetime import datetime
import cv2
import numpy as np
from ultralytics import YOLO
import threading
from queue import Queue
from sort import Sort
import json
import base64
import firebase_admin
from firebase_admin import credentials, db
import time

app = Flask(__name__)

# Directory to save incoming frames
SAVE_DIR = "received_frames"
os.makedirs(SAVE_DIR, exist_ok=True)

# Initialize YOLO model
model = YOLO('bestv5_grayscale.pt')

# Initialize SORT tracker
tracker = Sort()

# Define counting lines
cy1, cy2, cy3, cy4 = 240, 190, 230, 180
offset = 15

# Initialize counters and trackers
class PassengerCounter:
    def __init__(self):
        self.going_in = {}
        self.counter1 = set()  # out
        self.going_out = {}
        self.counter2 = set()  # in
        self.lock = threading.Lock()
        
    def get_counts(self):
        with self.lock:
            return {
                "in": len(self.counter2),
                "out": len(self.counter1),
                "total": len(self.counter2) - len(self.counter1)
            }
            
    def update_counters(self, obj_id, cy, cx):
        with self.lock:
            # Check out movement
            if cy3 < (cy + offset) and cy3 > (cy - offset):
                self.going_out[int(obj_id)] = (cx, cy)
            if int(obj_id) in self.going_out:
                if cy4 < (cy + offset) and cy4 > (cy - offset):
                    if int(obj_id) not in self.counter1:
                        self.counter1.add(int(obj_id))

            # Check in movement
            if cy2 < (cy + offset) and cy2 > (cy - offset):
                self.going_in[int(obj_id)] = (cx, cy)
            if int(obj_id) in self.going_in:
                if cy1 < (cy + offset) and cy1 > (cy - offset):
                    if int(obj_id) not in self.counter2:
                        self.counter2.add(int(obj_id))

passenger_counter = PassengerCounter()

# Queues and shared resources
frame_queue = Queue(maxsize=60)  # Increased queue size
processed_frame_queue = Queue(maxsize=60)
latest_frame = None
frame_lock = threading.Lock()

# Initialize Firebase
cred = credentials.Certificate('/Users/mohammedali/Downloads/testtest/my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://my-bus-421811-default-rtdb.firebaseio.com/'
})

# Add these global variables after initializing Firebase
current_stop = "Unknown"
video_writer = None
last_frame_time = None

# Save passenger counts to file periodically
def save_counts():
    counts_file = "passenger_counts.json"
    while True:
        counts = passenger_counter.get_counts()
        with open(counts_file, 'w') as f:
            json.dump(counts, f)
        threading.Event().wait(60)  # Save every minute

def update_firebase_passenger_count():
    while True:
        try:
            # Get the current passenger counts
            counts = passenger_counter.get_counts()
            
            # Update the passenger field in the gps_locations node
            ref = db.reference('gps_locations')
            ref.update({
                'passengers': counts['total']
            })
            
            # Wait for a certain period before updating again (e.g., every 10 seconds)
            time.sleep(10)
        except Exception as e:
            print(f"Error updating Firebase: {e}")
            time.sleep(10)  # Wait before retrying

def update_current_stop():
    global current_stop
    while True:
        try:
            # Get the current_stop from Firebase
            ref = db.reference('gps_locations')
            snapshot = ref.get()
            if snapshot and 'current_stop' in snapshot:
                current_stop = snapshot['current_stop']
            time.sleep(5)  # Update every 5 seconds
        except Exception as e:
            print(f"Error updating current_stop from Firebase: {e}")
            time.sleep(5)

def process_frame_worker():
    global video_writer, last_frame_time
    """
    Worker thread to process frames from the queue
    """
    while True:
        frame = frame_queue.get()
        if frame is None:
            break
            
        # Run YOLO model for detection
        results = model(frame, conf=0.1)

        # Extract detections
        detections = []
        for result in results[0].boxes:
            x1, y1, x2, y2 = map(int, result.xyxy[0].tolist())
            confidence = result.conf[0].item()
            label = result.cls[0].item()
            if label == 0:  # Assuming class 0 is the head
                detections.append([x1, y1, x2, y2, confidence])

        # Update SORT tracker with detections
        if detections:
            tracked_objects = tracker.update(np.array(detections))

            for obj in tracked_objects:
                x1, y1, x2, y2, obj_id = obj
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # Draw bounding boxes and IDs
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, f'{int(obj_id)}', (x1, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.circle(frame, (cx, cy), 4, (255, 0, 255), -1)

                # Update passenger counters
                passenger_counter.update_counters(obj_id, cy, cx)

        # Draw counting lines and counters
        frame_width = frame.shape[1]
        cv2.line(frame, (10, cy1), (frame_width - 10, cy1), (0, 255, 0), 2)
        cv2.line(frame, (10, cy2), (frame_width - 10, cy2), (0, 255, 0), 2)
        cv2.line(frame, (10, cy3), (frame_width - 10, cy3), (0, 0, 255), 2)
        cv2.line(frame, (10, cy4), (frame_width - 10, cy4), (0, 0, 255), 2)

        counts = passenger_counter.get_counts()
        cv2.putText(frame, f'P_OUT: {counts["out"]}', (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        cv2.putText(frame, f'P_IN: {counts["in"]}', (frame_width - 150, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        cv2.putText(frame, f'Passengers: {counts["total"]}', (frame_width // 2 - 100, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Add current stop information to the frame
        cv2.putText(frame, f'Current Stop: {current_stop}', (frame_width // 2 - 100, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Handle video writing
        current_time = datetime.now()
        if video_writer is None:
            # Initialize video writer with current timestamp
            timestamp = current_time.strftime('%Y%m%d_%H%M%S')
            video_path = os.path.join(SAVE_DIR, f"recording_{timestamp}.mp4")
            frame_height, frame_width = frame.shape[:2]
            video_writer = cv2.VideoWriter(
                video_path,
                cv2.VideoWriter_fourcc(*'mp4v'),
                24.0,  # FPS
                (frame_width, frame_height)
            )
            last_frame_time = current_time
        
        # Write frame to video
        video_writer.write(frame)

        # Check if we need to start a new video file (e.g., every hour)
        if last_frame_time and (current_time - last_frame_time).total_seconds() > 3600:  # 1 hour
            video_writer.release()
            video_writer = None

        processed_frame_queue.put(frame)

def generate_frames():
    """
    Generator function to stream processed frames
    """
    while True:
        try:
            frame = processed_frame_queue.get(timeout=1)  # Add timeout to prevent blocking
            if frame is None:
                continue
                
            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                continue
                
            # Convert to bytes
            frame_bytes = buffer.tobytes()
            
            # Yield the frame in proper MJPEG format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except:
            continue

# Add a route for the main page
@app.route('/')
def index():
    """
    Serve the main page with video feed
    """
    return """
    <html>
    <head>
        <title>Live Passenger Counter</title>
        <style>
            body { 
                font-family: Arial, sans-serif;
                margin: 20px;
                text-align: center;
            }
            .video-container {
                margin: 20px auto;
                max-width: 800px;
            }
            .stats {
                margin: 20px;
                padding: 10px;
                background: #f0f0f0;
                border-radius: 5px;
            }
            img {
                max-width: 100%;
                height: auto;
            }
        </style>
        <script>
            function updateCounts() {
                fetch('/counts')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('in-count').textContent = data.in;
                        document.getElementById('out-count').textContent = data.out;
                        document.getElementById('total-count').textContent = data.total;
                    });
            }
            // Update counts every second
            setInterval(updateCounts, 1000);
        </script>
    </head>
    <body>
        <h1>Live Passenger Counter</h1>
        <div class="video-container">
            <img src="/video_feed" />
        </div>
        <div class="stats">
            <h2>Current Counts</h2>
            <p>In: <span id="in-count">0</span></p>
            <p>Out: <span id="out-count">0</span></p>
            <p>Total: <span id="total-count">0</span></p>
        </div>
    </body>
    </html>
    """

@app.route('/video_feed')
def video_feed():
    """
    Video streaming route
    """
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/counts')
def get_counts():
    """
    API endpoint to get current passenger counts
    """
    return passenger_counter.get_counts()

@app.route('/upload', methods=['POST'])
def upload_frame():
    try:
        if 'frame' not in request.files:
            return {"error": "No frame provided"}, 400

        frame_file = request.files['frame']
        nparr = np.frombuffer(frame_file.read(), np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Add frame to processing queue
        frame_queue.put(frame)

        # Save original frame if needed
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = os.path.join(SAVE_DIR, f"{timestamp}.jpg")
        cv2.imwrite(filename, frame)

        return {
            "status": "success", 
            "file": filename,
            **passenger_counter.get_counts()
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    # Start processing thread
    process_thread = threading.Thread(target=process_frame_worker, daemon=True)
    process_thread.start()
    
    # Start count saving thread
    save_thread = threading.Thread(target=save_counts, daemon=True)
    save_thread.start()
    
    # Start Firebase update thread
    firebase_thread = threading.Thread(target=update_firebase_passenger_count, daemon=True)
    firebase_thread.start()
    
    # Start current stop update thread
    current_stop_thread = threading.Thread(target=update_current_stop, daemon=True)
    current_stop_thread.start()
    
    app.run(debug=False, host='0.0.0.0', port=9898, threaded=True)