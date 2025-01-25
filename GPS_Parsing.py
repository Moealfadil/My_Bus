#!/usr/bin/env python
import time
import serial
import pynmea2

# Setup Serial for GPS
ser = serial.Serial(
    port='/dev/ttyS0',  # Change to your GPS device port
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

while True:
    try:
        line = ser.readline().decode('ascii', errors='replace').strip()
        if line.startswith('$'):
            # Debug: Print each NMEA sentence received
            print("Received line:", line)
            
            msg = pynmea2.parse(line)

            # GGA sentence for latitude and longitude
            if isinstance(msg, pynmea2.types.talker.GGA):
                lat, lon = msg.latitude, msg.longitude
                print(f"Latitude: {lat}, Longitude: {lon}")

            # RMC sentence for speed and course
            elif isinstance(msg, pynmea2.types.talker.RMC):
                print("RMC Sentence Detected")  # Debug line
                if msg.spd_over_grnd:
                    # Convert speed from knots to meters per second
                    speed_mps = float(msg.spd_over_grnd) * 0.514444
                    print(f"Speed: {speed_mps:.2f} m/s")  # Display speed in m/s
                else:
                    print("No speed data in RMC sentence")  # Debug line
    except pynmea2.ParseError as e:
        print("NMEA Parse error:", e)
    except Exception as e:
        print("An error occurred:", e)
    
    time.sleep(1)