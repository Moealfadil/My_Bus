import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
import time

# Initialize Firebase
cred = credentials.Certificate(r"C:\Users\fdool\Downloads\ComputerVisionTasks-main\Location\my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://my-bus-421811-default-rtdb.firebaseio.com/'
})


def send_gps_location(lat, lon, passengers, bus_id):
    # Create the data to be sent
    data = {"location1" :{
        'latitude': lat,
        'longitude': lon,
        'passengers': passengers,
        'bus_id': bus_id,
    }}

    # Update the data in the Realtime Database
    db.reference('gps_locations').set(data)


# Arrays for latitude, longitude, and passengers
latitudes = [35.14237861, 35.14257861, 35.14277861, 35.14297861, 35.14317861, 35.14337861, 35.14357861, 35.14377861]
longitudes = [33.9077102, 33.9075102, 33.9073102, 33.9071102, 33.9069102, 33.9067102, 33.9065102, 33.9063102]
passengers = [90, 50, 10, 30, 40, 75, 80, 90]

# Bus ID
bus_id = "5"

# Ensure all arrays are of the same length
if not (len(latitudes) == len(longitudes) == len(passengers)):
    print("Error: Latitude, Longitude, and Passengers arrays must have the same length")
else:
    # Iterate through the arrays and send each location, passenger count, and bus ID to the Realtime Database
    for lat, lon, psg in zip(latitudes, longitudes, passengers):
        send_gps_location(lat, lon, psg, bus_id)
        print(f"GPS location {lat}, {lon} with {psg} passengers and bus ID {bus_id} sent to Firebase Realtime Database")
        time.sleep(1)  # Pause for 1 second between iterations

print("All GPS locations sent to Firebase Realtime Database")

#r"C:\Users\fdool\Downloads\ComputerVisionTasks-main\Location\my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json"
#https://my-bus-421811-default-rtdb.firebaseio.com/
