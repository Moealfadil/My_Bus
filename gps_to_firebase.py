import firebase_admin
from firebase_admin import credentials, firestore
from geopy.distance import geodesic
import time

# Initialize Firebase
cred = credentials.Certificate(
    r"C:\Users\fdool\Downloads\ComputerVisionTasks-main\Location\my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
firebase_admin.initialize_app(cred)
db = firestore.client()


# Function to get bus stop data from Firestore
def get_bus_stops():
    bus_stops_ref = db.collection('Bus-stations')
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


# Function to determine the current and next bus stop
def determine_bus_stops(current_location, bus_stops, line):
    route_u_stops = [stop for stop in bus_stops if 'u' in stop['id']]
    route_b_stops = [stop for stop in bus_stops if 'b' in stop['id']]

    # Sort the stops by their id within each route
    route_u_stops.sort(key=lambda x: x['id'])
    route_b_stops.sort(key=lambda x: x['id'])

    # Merge route u and b for line 5
    combined_route_stops = route_u_stops + route_b_stops

    current_stop, _ = find_closest_bus_stop(current_location, combined_route_stops)

    if current_stop:
        current_index = combined_route_stops.index(current_stop)
        next_stop = combined_route_stops[current_index + 1] if current_index + 1 < len(combined_route_stops) else None
        return current_stop, next_stop
    return None, None


# Simulating GPS data
# In real implementation, replace these values with data from the GPS module
latitudes = [35.141695, 35.1423563, 35.1452446, 35.1421206, 35.1407914, 35.1307779, 35.1277599, 35.1261780]
longitudes = [33.907058, 33.9095623, 33.9094298, 33.9134012, 33.9116762, 33.9181349, 33.9224228, 33.9251674]


# Load bus stops data
bus_stops = get_bus_stops()

# Iterate through the GPS data and determine bus stops
for lat, lon in zip(latitudes, longitudes):
    current_location = (lat, lon)
    current_stop, next_stop = determine_bus_stops(current_location, bus_stops, line=5)

    if current_stop:
        print(f"Current Stop: {current_stop['name']} ({current_stop['loc']})")
    if next_stop:
        print(f"Next Stop: {next_stop['name']} ({next_stop['loc']})")

    time.sleep(1)  # Pause for 1 second between iterations

print("GPS data processing completed.")
