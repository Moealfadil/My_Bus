import cv2
import numpy as np
import cvzone
import time
from sort import Sort

# Object detection parameters
thres = 0.4

# Load class names
classNames = []
classFile = r'C:\Users\fdool\Downloads\ComputerVisionTasks-main\Object-detection\coco.names'
with open(classFile, 'rt') as f:
    classNames = f.read().rstrip('\n').split('\n')

# Load pre-trained model from disk
configPath = r'C:\Users\fdool\Downloads\ComputerVisionTasks-main\Object-detection\ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt'
weightsPath = r'C:\Users\fdool\Downloads\ComputerVisionTasks-main\Object-detection\frozen_inference_graph.pb'

# Define model
net = cv2.dnn_DetectionModel(weightsPath, configPath)
net.setInputSize(320, 320)
net.setInputScale(1.0 / 127.5)
net.setInputMean((127.5, 127.5, 127.5))
net.setInputSwapRB(True)

# Load video
video_capture = cv2.VideoCapture(r"C:\Users\fdool\Downloads\ComputerVisionTasks-main\Object-detection\test3.mp4")
video_capture.set(3, 1280)
video_capture.set(4, 720)
video_capture.set(10, 70)

# Initialize SORT tracker
tracker = Sort()

cy1, cy2, cy3, cy4 = 300, 250, 180, 130
offset = 15

going_in = {}
counter1 = []
going_out = {}
counter2 = []
passengers = 0

count = 0

while True:
    ret, frame = video_capture.read()
    if not ret:
        break
    count += 1
    if count % 2 != 0:
        continue

    frame = cv2.resize(frame, (600, 480))

    # Object detection
    classIds, confs, bbox = net.detect(frame, confThreshold=thres)
    detections = []
    if len(classIds) != 0:
        for classId, confidence, box in zip(classIds.flatten(), confs.flatten(), bbox):
            if classNames[classId - 1] == "person":
                x, y, w, h = box
                detections.append([x, y, x + w, y + h, confidence])

    # Update tracker with detections if present
    if len(detections) > 0:
        tracked_objects = tracker.update(np.array(detections))

        for obj in tracked_objects:
            x1, y1, x2, y2, obj_id = obj
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            # cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 3)
            # cvzone.putTextRect(frame, f'{int(obj_id)}', (x1, y1), 2, 2)
            # cv2.circle(frame, (cx, cy), 4, (255, 0, 255), -1)

            if cy3 < (cy + offset) and cy3 > (cy - offset):
                going_out[int(obj_id)] = (cx, cy)
            if int(obj_id) in going_out:
                if cy4 < (cy + offset) and cy4 > (cy - offset):
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 3)
                    cvzone.putTextRect(frame, f'{int(obj_id)}', (x1, y1), 2, 2)
                    cv2.circle(frame, (cx, cy), 4, (255, 0, 255), -1)
                    id_out = len(counter1)
                    if len(counter1) == 0:
                        counter1.append(int(obj_id))
                    elif counter1[id_out - 1] != int(obj_id):
                        counter1.append(int(obj_id))
            if cy2 < (cy + offset) and cy2 > (cy - offset):
                going_in[int(obj_id)] = (cx, cy)
            if int(obj_id) in going_in:
                if cy1 < (cy + offset) and cy1 > (cy - offset):
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                    cvzone.putTextRect(frame, f'{int(obj_id)}', (x1, y1), 2, 2)
                    cv2.circle(frame, (cx, cy), 4, (255, 0, 255), -1)
                    id_in = len(counter2)
                    if len(counter2) == 0:
                        counter2.append(int(obj_id))
                    elif counter2[id_in - 1] != int(obj_id):
                        counter2.append(int(obj_id))

    # Draw lines
    cv2.line(frame, (10, cy1), (598, cy1), (255, 255, 255), 2)
    cv2.line(frame, (8, cy2), (598, cy2), (255, 255, 255), 2)
    cv2.line(frame, (10, cy3), (596, cy3), (255, 255, 255), 2)
    cv2.line(frame, (10, cy4), (596, cy4), (255, 255, 255), 2)

    cvzone.putTextRect(frame, 'line1', (10, cy1), 1, 1)
    cvzone.putTextRect(frame, 'line2', (288, cy2), 1, 1)
    cvzone.putTextRect(frame, 'line3', (552, cy3), 1, 1)
    cvzone.putTextRect(frame, 'line4', (300, cy4), 1, 1)

    p_out = len(counter1)
    p_in = len(counter2)
    passengers = p_out - p_in
    cvzone.putTextRect(frame, f'P_OUT: {p_out}', (50, 60), 1, 1)
    cvzone.putTextRect(frame, f'P_IN: {p_in}', (428, 56), 1, 1)

    cv2.imshow('RGB', frame)
    time.sleep(0.01)  # Adjusted to speed up the video
    if cv2.waitKey(1) & 0xFF == 27:  # Press 'Esc' to exit
        break

# Release the video capture and close windows
video_capture.release()
cv2.destroyAllWindows()
print("passengers =", passengers)
