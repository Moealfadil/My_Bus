import firebase_admin
from firebase_admin import credentials, firestore, db
from geopy.distance import geodesic
import re
import time

# Initialize Firebase Firestore
cred = credentials.Certificate(
    r"C:\Users\fdool\Downloads\ComputerVisionTasks-main\Location\my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://my-bus-421811-default-rtdb.firebaseio.com/'
})
firestore_db = firestore.client()
realtime_db = db.reference('gps_locations')


# Function to get bus stop data from Firestore
def get_bus_stops():
    bus_stops_ref = firestore_db.collection('Bus-stations')
    docs = bus_stops_ref.stream()

    bus_stops = []
    for doc in docs:
        stop_data = doc.to_dict()
        # Convert Firestore GeoPoint to tuple
        stop_data['loc'] = (stop_data['loc'].latitude, stop_data['loc'].longitude)
        bus_stops.append(stop_data)
    return bus_stops


# Function to find the closest bus stop
def find_closest_bus_stop(current_location, bus_stops):
    closest_stop = None
    min_distance = float('inf')

    for stop in bus_stops:
        stop_location = stop['loc']
        distance = geodesic(current_location, stop_location).meters
        if distance < min_distance:
            min_distance = distance
            closest_stop = stop

    return closest_stop, min_distance


# Function to sort stops naturally
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


# Function to determine the current and next bus stop
def determine_bus_stops(current_location, bus_stops, line):
    route_u_stops = [stop for stop in bus_stops if 'u' in stop['id']]
    route_b_stops = [stop for stop in bus_stops if 'b' in stop['id']]

    # Sort the stops by their id within each route using natural sort
    route_u_stops.sort(key=lambda x: natural_sort_key(x['id']))
    route_b_stops.sort(key=lambda x: natural_sort_key(x['id']))

    # Merge route u and b for line 5
    combined_route_stops = route_u_stops + route_b_stops

    current_stop, _ = find_closest_bus_stop(current_location, combined_route_stops)

    if current_stop:
        current_index = combined_route_stops.index(current_stop)

        # Determine if the bus is on the return trip
        if 'b5' in combined_route_stops[current_index]['id']:
            combined_route_stops.reverse()
            current_index = combined_route_stops.index(current_stop)

        next_stop = combined_route_stops[current_index + 1] if current_index + 1 < len(combined_route_stops) else None
        return current_stop, next_stop
    return None, None


# Function to estimate time to next stop
def estimate_time_to_next_stop(current_location, next_stop_location, speed_mps):
    distance = geodesic(current_location, next_stop_location).meters
    time_seconds = distance / speed_mps
    minutes, seconds = divmod(time_seconds, 60)
    return int(minutes), int(seconds)


# Function to send data to Firebase Realtime Database
def send_gps_data(lat, lon, passengers, bus_id, current_stop, next_stop, time_to_next_stop):
    minutes, seconds = time_to_next_stop
    data = {
        'latitude': lat,
        'longitude': lon,
        'passengers': passengers,
        'bus_id': bus_id,
        'current_stop': current_stop['name'] if current_stop else None,
        'next_stop': next_stop['name'] if next_stop else None,
        'time_to_next_stop': f"{minutes} minutes and {seconds} seconds" if time_to_next_stop else None
    }
    realtime_db.set(data)


# Simulating GPS data
# In real implementation, replace these values with data from the GPS module
latitudes = [35.141695, 35.1423563, 35.1452446, 35.1421206, 35.1407914, 35.1307779, 35.1277599, 35.1261780, 35.1240909,
             35.1226413, 35.1206592]
longitudes = [33.907058, 33.9095623, 33.9094298, 33.9134012, 33.9116762, 33.9181349, 33.9224228, 33.9251674, 33.9292296,
              33.9320308, 33.9361933]
passengers = [90, 50, 10, 30, 40, 75, 80, 90, 61, 20, 35]

# Bus ID
bus_id = "5"

# Assumed bus speed in meters per second (e.g., 10 m/s ~ 36 km/h)
bus_speed_mps = 10

# Load bus stops data
bus_stops = get_bus_stops()

# Ensure all arrays are of the same length
if not (len(latitudes) == len(longitudes) == len(passengers)):
    print("Error: Latitude, Longitude, and Passengers arrays must have the same length")
else:
    # Iterate through the GPS data and determine bus stops
    for lat, lon, psg in zip(latitudes, longitudes, passengers):
        current_location = (lat, lon)
        current_stop, next_stop = determine_bus_stops(current_location, bus_stops, line=5)
        time_to_next_stop = estimate_time_to_next_stop(current_location, next_stop['loc'],
                                                       bus_speed_mps) if next_stop else None

        send_gps_data(lat, lon, psg, bus_id, current_stop, next_stop, time_to_next_stop)

        if current_stop:
            print(f"Current Stop: {current_stop['name']} ({current_stop['loc']})")
        if next_stop:
            print(f"Next Stop: {next_stop['name']} ({next_stop['loc']})")
        if time_to_next_stop:
            minutes, seconds = time_to_next_stop
            print(f"Estimated Time to Next Stop: {minutes} minutes and {seconds} seconds")
        else:
            print("Estimated Time to Next Stop: None")

        time.sleep(1)  # Pause for 1 second between iterations

print("GPS data processing completed.")
