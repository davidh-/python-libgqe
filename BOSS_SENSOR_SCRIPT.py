#!/usr/bin/env python3
"""
CLAIR Sensor Integration Script
This script reads data from GMC-500+ and GQ-EMF390 sensors and sends it to CLAIR dashboard.
"""

import subprocess
import datetime
import os
import time
import serial
import json
import paho.mqtt.client as mqtt
import gpsd
import threading

# MQTT Configuration - REPLACE WITH YOUR REMOTE.IT ADDRESS
MQTT_BROKER = 'proxy16.rt3.io'  # e.g., 'beast-abc123.remote.it'
MQTT_PORT = 37735  # or whatever port Remote.it assigned
MQTT_TOPIC = 'clair/sensors/environment'

# Sensor configuration
pro_dir = "/home/pi/python-libgqe/"
gqe_cli_dir = pro_dir + "gqe-cli"
baud_rate = 115200
port_500 = "/dev/gmc500"
port_390 = "/dev/emf390"

# Initialize MQTT client
mqtt_client = mqtt.Client('clair-sensor-pub')

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to CLAIR MQTT broker!")
    else:
        print(f"Failed to connect to MQTT broker, return code {rc}")

def on_disconnect(client, userdata, rc):
    print("Disconnected from MQTT broker")

# Set up MQTT callbacks
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

def connect_mqtt():
    """Connect to the MQTT broker"""
    try:
        print(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return False

def read_gps_data():
    """Read GPS data from gpsd"""
    try:
        packet = gpsd.get_current()
        pos = packet.position()
        lat, lon = pos[0], pos[1]
        alt = packet.altitude() * 3.28084  # m to ft
        vel = packet.hspeed * 2.237  # m/s to mph
        return lat, lon, alt, vel
    except:
        return 0, 0, 0, 0

def read_geiger_data():
    """Read data from GMC-500+ Geiger counter"""
    try:
        ser = serial.Serial(port_500, baud_rate, timeout=1)
        
        # Get CPM high
        get_cpm_h_command = '<GETCPMH>>'.encode()
        ser.write(get_cpm_h_command)
        response = ser.read(4)
        cpm_h = float(int.from_bytes(response, byteorder='big'))
        
        # Get CPM low
        get_cpm_l_command = '<GETCPML>>'.encode()
        ser.write(get_cpm_l_command)
        response = ser.read(4)
        cpm_l = float(int.from_bytes(response, byteorder='big'))
        
        ser.close()
        return cpm_h, cpm_l
    except Exception as e:
        print(f"Error reading Geiger data: {e}")
        return 0, 0

def read_emf_data():
    """Read data from GQ-EMF390"""
    try:
        ser = serial.Serial(port_390, baud_rate, timeout=0.2)
        
        # Get EMF
        get_emf_command = '<GETEMF>>'.encode()
        ser.write(get_emf_command)
        response = ser.read(12).decode('utf-8')
        emf = float(response.split(" ")[2])
        
        # Get RF
        get_rf_command = '<GETRFTOTALDENSITY>>'.encode()
        ser.write(get_rf_command)
        response = ser.read(20).decode('utf-8')
        rf = float(response.split(" ")[0])
        
        ser.close()
        return emf, rf
    except Exception as e:
        print(f"Error reading EMF data: {e}")
        return 0.0, 0.0

def publish_to_clair(timestamp, cpm_h, cpm_l, emf, rf, alt, lat, lon, vel):
    """Publish sensor data to CLAIR dashboard"""
    payload = {
        "timestamp": timestamp,
        "cpm_h": cpm_h,
        "cpm_l": cpm_l,
        "emf": emf,
        "rf": rf,
        "alt": alt,
        "lat": lat,
        "lon": lon,
        "vel": vel
    }
    
    try:
        mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
        print(f"Sent: CPM_H={cpm_h}, CPM_L={cpm_l}, EMF={emf}, RF={rf}, GPS={lat},{lon}")
    except Exception as e:
        print(f"Failed to publish data: {e}")

def sensor_loop():
    """Main sensor reading and publishing loop"""
    print("Starting CLAIR sensor integration...")
    
    # Connect to GPS
    try:
        gpsd.connect()
        print("Connected to GPS")
    except:
        print("GPS not available")
    
    # Connect to MQTT
    if not connect_mqtt():
        print("Cannot continue without MQTT connection")
        return
    
    print("Starting sensor data loop (Ctrl+C to stop)...")
    
    while True:
        try:
            # Read all sensor data
            lat, lon, alt, vel = read_gps_data()
            cpm_h, cpm_l = read_geiger_data()
            emf, rf = read_emf_data()
            
            # Create timestamp
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Publish to CLAIR
            publish_to_clair(timestamp, cpm_h, cpm_l, emf, rf, alt, lat, lon, vel)
            
            # Wait 2 seconds before next reading
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\nStopping sensor integration...")
            break
        except Exception as e:
            print(f"Error in sensor loop: {e}")
            time.sleep(5)  # Wait before retrying
    
    # Cleanup
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    print("Disconnected from CLAIR")

if __name__ == "__main__":
    sensor_loop() 