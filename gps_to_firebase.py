import firebase_admin
from firebase_admin import credentials, firestore, db
from geopy.distance import geodesic
import re
import time
from datetime import timedelta

# Initialize Firebase Firestore
cred = credentials.Certificate(
    r"C:\Users\fdool\OneDrive\Documents\My_Bus\my-bus-421811-firebase-adminsdk-ex1ek-eea212c754.json")
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

# Function to sort stops naturally
def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

# Function to determine the current and next bus stop
def determine_bus_stops(current_location, bus_stops, line, on_return_trip, current_stop):
    route_u_stops = [stop for stop in bus_stops if 'u' in stop['id']]
    route_b_stops = [stop for stop in bus_stops if 'b' in stop['id']]

    # Sort the stops by their id within each route using natural sort
    route_u_stops.sort(key=lambda x: natural_sort_key(x['id']))
    route_b_stops.sort(key=lambda x: natural_sort_key(x['id']))

    # Merge route u and b for line 5
    combined_route_stops = route_u_stops + route_b_stops

    # If on return trip, reverse the route
    if on_return_trip:
        combined_route_stops.reverse()

    if current_stop is None:
        current_stop = combined_route_stops[0]
    else:
        current_stop, _ = find_closest_bus_stop(current_location, combined_route_stops, current_stop)

    if current_stop:
        current_index = combined_route_stops.index(current_stop)

        # Determine if the bus is on the return trip
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
    if time_to_next_stop:
        estimated_time = timedelta(minutes=time_to_next_stop[0], seconds=time_to_next_stop[1])
    else:
        estimated_time = None

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

# Simulating GPS data
# In real implementation, replace these values with data from the GPS module
latitudes = [35.140695, 35.1423563, 35.1452446, 35.1421206, 35.1407914, 35.1307779,35.13061906,35.13046022,35.13030137,35.13014253,35.12998369,35.12982485,35.12966601,35.12950716,35.12934832,35.12918948,35.12903064,35.12887179,35.12871295,35.12855411,35.12839527,35.12823643,35.12807758,35.12791874,35.1277599, 35.1261780, 35.1240909,
             35.1226413, 35.1206592, 35.1226413, 35.12271759, 35.12279389, 35.12287018, 35.12294648, 35.12302277,
             35.12309907, 35.12317536, 35.12325166, 35.12332795, 35.12340425, 35.12348054, 35.12355684, 35.12363313,
             35.12370943, 35.12378572, 35.12386202, 35.12393831, 35.12401461, 35.1240909]
longitudes = [33.903058, 33.9095623, 33.9094298, 33.9134012, 33.9116762, 33.9181349,33.91836058,33.91858626,33.91881194,33.91903762,33.91926329,33.91948897,33.91971465,33.91994033,33.92016601,33.92039169,33.92061737,33.92084305,33.92106873,33.92129441,33.92152008,33.92174576,33.92197144,33.92219712,33.9224228 , 33.9251674, 33.9292296,
              33.9320308, 33.9361933, 33.9320308, 33.93188337, 33.93173594, 33.93158851, 33.93144107, 33.93129364,
              33.93114621, 33.93099878, 33.93085135, 33.93070392, 33.93055648, 33.93040905, 33.93026162, 33.93011419,
              33.92996676, 33.92981933, 33.92967189, 33.92952446, 33.92937703, 33.9292296]
passengers = [90, 50, 10, 30, 40, 75, 75,75,75,75,75,75,75,75,75,75,75,75,75,75,75,75,75,75, 80, 90, 61, 20, 35, 5, 9, 31, 89, 52, 74, 74, 87, 74, 91, 88, 80, 71, 76, 80, 61,
              16, 49, 17, 41]

# Bus ID
bus_id = "5"

# Assumed bus speed in meters per second (e.g., 10 m/s ~ 36 km/h)
bus_speed_mps = 15

# Load bus stops data
bus_stops = get_bus_stops()

# Ensure all arrays are of the same length
if not (len(latitudes) == len(longitudes) == len(passengers)):
    print("Error: Latitude, Longitude, and Passengers arrays must have the same length")
else:
    on_return_trip = False  # Track if the bus is on the return trip
    current_stop = None  # Initialize current_stop outside the loop
    # Iterate through the GPS data and determine bus stops
    for lat, lon, psg in zip(latitudes, longitudes, passengers):
        current_location = (lat, lon)
        current_stop, next_stop, on_return_trip = determine_bus_stops(current_location, bus_stops, line=5, on_return_trip=on_return_trip, current_stop=current_stop)
        time_to_next_stop = estimate_time_to_next_stop(current_location, next_stop['loc'], bus_speed_mps) if next_stop else None

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
