import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
import time
import serial
import paho.mqtt.client as mqtt
import json
import cv2
import base64
import glob

# Fix Qt/OpenCV GUI issues
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['OPENCV_VIDEOIO_PRIORITY_GSTREAMER'] = '0'
os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

import matplotlib.widgets as widgets

TIME_WINDOW = 1  # default time window in minutes

pro_dir = "/home/pi/python-libgqe/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_file = pro_dir + "/data/" + timestamp + ".csv"
with open(data_file, "w") as f:
    f.write("date-time,cmp_h,cpm_l,emf,rf,ef,altitude,latitude,longitude, velocity\n")

import gpsd

# Connect to the local gpsd
gpsd.connect()

# MQTT Configuration for CLAIR
mqtt_client = mqtt.Client('david-sensor-gui')
mqtt_client.tls_set()
mqtt_client.username_pw_set("clair-mqtt-client", "Eldaeon12")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to CLAIR MQTT broker!")
    else:
        print("Failed to connect to MQTT broker, return code {}".format(rc))

mqtt_client.on_connect = on_connect

# Connect to CLAIR MQTT broker
try:
    mqtt_client.connect("628004c9517248bb8f8e31c52237cb6a.s1.eu.hivemq.cloud", 8883, 60)
    mqtt_client.loop_start()
    print("MQTT client started for CLAIR integration")
except Exception as e:
    print("Failed to connect to MQTT broker: {}".format(e))

# def capture_uv_image():
#     """Capture image from UV camera - Qt-free version"""
#     try:
#         # Try UV camera device first
#         cap = cv2.VideoCapture('/dev/uvcam')
#         if not cap.isOpened():
#             # Fallback to default USB camera
#             cap = cv2.VideoCapture(0)
        
#         if cap.isOpened():
#             cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
#             cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
#             ret, frame = cap.read()
#             if ret:
#                 # Encode image to base64 with reduced quality for MQTT
#                 encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
#                 _, buffer = cv2.imencode('.jpg', frame, encode_param)
#                 img_str = base64.b64encode(buffer).decode()
#                 cap.release()
#                 return img_str
#             cap.release()
#     except Exception as e:
#         print("Error capturing UV image: {}".format(e))
#     return None

# def capture_thermal_image():
#     """Capture thermal image - simplified version"""
#     try:
#         # Simple approach: read a thermal image file if it exists
#         thermal_dir = '/home/pi/ht301_hacklib'
        
#         # Look for recent thermal images
#         png_files = glob.glob(thermal_dir + '/*.png')
#         if png_files:
#             # Get the most recent thermal image
#             latest_file = max(png_files, key=os.path.getctime)
            
#             # Read and encode the image
#             thermal_img = cv2.imread(latest_file)
#             if thermal_img is not None:
#                 encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
#                 _, buffer = cv2.imencode('.jpg', thermal_img, encode_param)
#                 img_str = base64.b64encode(buffer).decode()
#                 return img_str
#     except Exception as e:
#         print("Error capturing thermal image: {}".format(e))
#     return None

x = []; y_cpm_h = []; y_cpm_l = []; y_emf = []; y_rf = []; y_ef = []; y_lat = []; y_lon = []; y_alt = []; y_vel = []

fig, (ax1, ax2, ax3, ax4, ax5, ax6, ax7) = plt.subplots(nrows=7, sharex=True)

line_vel, = ax6.plot(x, y_vel)
ax6.set_ylabel("vel")

line_alt, = ax7.plot(x, y_alt)
ax7.set_ylabel("alt")

# Set the figure location to (x=0,y=0) on the screen
fig.canvas.manager.window.move(0, 0)

line_cpm_h, = ax1.plot(x, y_cpm_h)
ax1.set_ylabel("cpm_h")

line_cpm_l, = ax2.plot(x, y_cpm_l)
ax2.set_ylabel("cpm_l")

line_emf, = ax3.plot(x, y_emf)
ax3.set_ylabel("emf")

line_rf, = ax4.plot(x, y_rf)
ax4.set_ylabel("rf")

line_ef, = ax5.plot(x, y_ef)
ax5.set_ylabel("ef")

gqe_cli_dir = pro_dir + "gqe-cli"

baud_rate = 115200  # Baud rate as specified by the device documentation

name_500 = "GMC500Plus"
port_500 = "/dev/gmc500"
ver_500 = "'Re 2.42'"
unit_500_get_cpm_h = "--get-cpm-h"
unit_500_get_cpm_l = "--get-cpm-l"

name_390 = "GQEMF390"
port_390 = "/dev/emf390"
ver_390 = "'Re 3.70'"
unit_390_get_emf = "--get-emf"

arg_unit = "--unit"
arg_revision = "--revision"
arg_power = "--power"
arg_power_on = "true"

# Check if devices port is correct 
# Loop until a successful response is received for the first command
stop_try_500 = False
while True:
    # Initialize the serial connection
    ser = serial.Serial(port_500, baud_rate, timeout=1)

    # Command to power on the Geiger Counter
    power_on_command = '<POWERON>>'.encode()  # Command must be encoded to bytes
    ser.write(power_on_command)

    time.sleep(0.5)

    get_ver_command = '<GETVER>>'.encode()  # Command must be encoded to bytes

    # Write the command to the serial port
    ser.write(get_ver_command)

    # Read the response from the Geiger counter
    response = ser.read(17).decode('utf-8')  # 

    ser.close()

    if (response == "GMC-500+Re 2.42"):
        print("Successfull port and power on for {}. Port is {}.".format(name_500, port_500))
        break
    elif stop_try_500:
        print("Error: Unable to execute command for {}. Skipping.".format(name_500))
        break
    else:
        print("Error: Unable to execute command for {}. Changing default ports. Retrying...".format(name_500))
        port_500, port_390 = port_390, port_500
        stop_try_500 = True

stop_try_390 = False
while True:
    # Initialize the serial connection
    ser = serial.Serial(port_390, baud_rate, timeout=1)

    # Command to power on the 390 
    power_on_command = '<POWERON>>'.encode()  # Command must be encoded to bytes
    ser.write(power_on_command)

    time.sleep(2)

    get_ver_command = '<GETVER>>'.encode()  # Command must be encoded to bytes

    # Write the command to the serial port
    ser.write(get_ver_command)

    # Read the response from the 390 
    response = ser.read(20).decode('utf-8')  # 
    print(response)

    if (response == "GQ-EMF390v2Re 3.70\r\n"):
        print("Successfull port and power on for {}. Port is {}.".format(name_390, port_390))
        ser.close()
        break
    elif stop_try_390:
        print("Error: Unable to execute command for {}. Something wrong. Check physical connections.".format(name_390))
        ser.close()
        exit() 
    else:
        print("Error: Unable to execute command for {}. Changing default ports. Retrying...".format(name_390))
        port_390 = "/dev/ttyUSB0"
        stop_try_390 = True
        ser.close()

# # Camera capture counter to reduce frequency
# camera_counter = 0

def update(frame):
    # global camera_counter
    start = time.time()
    try:
        # Get gps position
        packet = gpsd.get_current()
        pos = packet.position()
        lat, lon = pos[0], pos[1]

        alt = packet.altitude() 
        alt = alt  * 3.28084 # m to ft

        vel = packet.hspeed
        vel = vel * 2.237  # m/s to mph
    except:
        # reset gps here TODO subprocess
        lat = 0
        lon = 0
        alt = 0
        vel = 0

    ax1.set_title("Lat: {}, Lon: {}".format(round(lat,5), round(lon, 5)))
    
    time_start_cpm = time.time()
    try:
        ser = serial.Serial(port_500, baud_rate, timeout=1)

        # Command to get the CPM of the low dose tube for GMC-500+
        get_cpm_h_command = '<GETCPMH>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_cpm_h_command)

        # Read the response from the Geiger counter
        response = ser.read(4)  # Read 4 bytes as specified by the documentation

        # Convert the response from bytes to an integer assuming little-endian format
        cpm_h_value = int.from_bytes(response, byteorder='big')

        cpm_h = float(cpm_h_value)

        # Command to get the CPM of the low dose tube for GMC-500+
        get_cpm_l_command = '<GETCPML>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_cpm_l_command)

        # Read the response from the Geiger counter
        response = ser.read(4)  # Read 4 bytes as specified by the documentation

        # Convert the response from bytes to an integer assuming little-endian format
        cpm_l_value = int.from_bytes(response, byteorder='big')

        cpm_l = float(cpm_l_value)

        ser.close()

    except subprocess.CalledProcessError as e:
        print("Error getting GMC500Plus cpm: {}".format(e))
        cpm_h = 0
        cpm_l = 0
    time_end_cpm = time.time()
    print("cpm time:", time_end_cpm-time_start_cpm)

    def read_response(ser):
        response = b''  # Initialize response as an empty byte string
        while ser.in_waiting > 0 or not response:  # While there's something to read or we haven't started reading yet
            response += ser.read(ser.in_waiting)  # Read whatever is available
        return response.decode('utf-8').strip()  # Decode and strip whitespace

    time_start_emf = time.time()
    try:
        # Initialize the serial connection
        ser = serial.Serial(port_390, baud_rate, timeout=0.2)

        get_emf_command = '<GETEMF>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_emf_command)

        # Read the response from the 390
        response = read_response(ser)

        emf = float(response.split(" ")[2])

        get_ef_command = '<GETEF>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_ef_command)

        # Read the response from the 390
        response = read_response(ser)

        ef = float(response.split(" ")[2])

        get_rf_command = '<GETRFTOTALDENSITY>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_rf_command)

        # Read the response from the 390
        response = read_response(ser)

        rf = float(response.split(" ")[0])

        ser.close()

    except subprocess.CalledProcessError as e:
        print("Error getting GQEMF390 data: {}".format(e))
        emf = 0.0
        rf = 0.0
        ef = 0.0
    time_end_emf = time.time()
    print("emf time:", time_end_emf-time_start_emf)

    # Clear any previously drawn text by removing it from the axes
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6, ax7]:
        for text in ax.texts:
            text.remove()

    # Add text box to the right of each plot
    ax1.text(1.01, 0.5, "{}".format(cpm_h), transform=ax1.transAxes, va='center')
    ax2.text(1.01, 0.5, "{}".format(cpm_l), transform=ax2.transAxes, va='center')
    ax3.text(1.01, 0.5, "{}\nmG".format(emf), transform=ax3.transAxes, va='center')
    ax4.text(1.01, 0.5, "{}\nmW/m2".format(rf), transform=ax4.transAxes, va='center')
    ax5.text(1.01, 0.5, "{}\nV/m".format(ef), transform=ax5.transAxes, va='center')
    ax6.text(1.01, 0.5, "{}\nmph".format(round(vel, 1)), transform=ax6.transAxes, va='center')
    ax7.text(1.01, 0.5, "{}\nft".format(round(alt, 2)), transform=ax7.transAxes, va='center')

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(data_file, "a") as f:
        f.write("{},{},{},{},{},{},{},{},{},{}\n".format(timestamp,cpm_h,cpm_l,emf,rf,ef,alt,lat,lon,vel))

    x.append(now)
    y_cpm_h.append(cpm_h)
    y_cpm_l.append(cpm_l)
    y_emf.append(emf)
    y_rf.append(rf)
    y_ef.append(ef)

    y_vel.append(vel)
    y_alt.append(alt)

    line_cpm_h.set_xdata(x)
    line_cpm_h.set_ydata(y_cpm_h)

    line_cpm_l.set_xdata(x)
    line_cpm_l.set_ydata(y_cpm_l)
    
    line_emf.set_xdata(x)
    line_emf.set_ydata(y_emf)
    
    line_rf.set_xdata(x)
    line_rf.set_ydata(y_rf)

    line_ef.set_xdata(x)
    line_ef.set_ydata(y_ef)

    line_vel.set_xdata(x)
    line_vel.set_ydata(y_vel)
    
    line_alt.set_xdata(x)
    line_alt.set_ydata(y_alt)

    # Update x-limits to only show the last TIME_WINDOW minutes
    min_time = now - datetime.timedelta(minutes=TIME_WINDOW)
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6, ax7]:
        ax.set_xlim([min_time, now])
        ax.relim()
        ax.autoscale_view()

    # Send data to CLAIR dashboard
    try:
        timestamp = datetime.datetime.now().isoformat()
        
        # Send each sensor type separately
        geiger_payload = {
            "id": "geiger-sensor",
            "timestamp": timestamp,
            "cpm_h": cpm_h,
            "cpm_l": cpm_l,
            "value": {
                "beta": cpm_h,
                "gamma": cpm_l,
                "xray": 0.9
            }
        }
        mqtt_client.publish("sensor/data", json.dumps(geiger_payload))
        
        emf_payload = {
            "id": "emf-sensor", 
            "timestamp": timestamp,
            "emf": emf,
            "value": {
                "level": emf
            }
        }
        mqtt_client.publish("sensor/data", json.dumps(emf_payload))
        
        rf_payload = {
            "id": "rf-sensor",
            "timestamp": timestamp, 
            "rf": rf,
            "value": {
                "power": rf
            }
        }
        mqtt_client.publish("sensor/data", json.dumps(rf_payload))
        
        gps_payload = {
            "id": "gps-sensor",
            "timestamp": timestamp,
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "vel": vel,
            "value": {
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "velocity": vel
            }
        }
        mqtt_client.publish("sensor/data", json.dumps(gps_payload))
        
        # # Capture and send camera images every 10 updates (reduce frequency)
        # camera_counter += 1
        # if camera_counter >= 10:
        #     camera_counter = 0
            
        #     # Capture UV camera image
        #     uv_image = capture_uv_image()
        #     if uv_image:
        #         uv_payload = {
        #             "id": "uv-camera",
        #             "timestamp": timestamp,
        #             "image": uv_image,
        #             "type": "uv"
        #         }
        #         mqtt_client.publish("camera/data", json.dumps(uv_payload))
        #         print("UV camera image sent to CLAIR")
            
        #     # Capture thermal camera image
        #     thermal_image = capture_thermal_image()
        #     if thermal_image:
        #         thermal_payload = {
        #             "id": "thermal-camera",
        #             "timestamp": timestamp,
        #             "image": thermal_image,
        #             "type": "thermal"
        #         }
        #         mqtt_client.publish("camera/data", json.dumps(thermal_payload))
        #         print("Thermal camera image sent to CLAIR")
        
    except Exception as e:
        print("Error sending to CLAIR: {}".format(e))

    end = time.time()
    print("update time: ", end-start)
    return line_cpm_h, line_cpm_l, line_emf, line_rf, line_ef, line_vel, line_alt

ani = animation.FuncAnimation(fig, update, interval=0, cache_frame_data=False)

def on_close(event):
    print('Plot closed')

# Radio buttons to control the time window
time_options = ['1', '5', '10', '15', '30', '60']
radio_ax = plt.axes([0.1, 0.90, 0.15, 0.075], frame_on=False)  # adjust these values to position the radio buttons
radio = widgets.RadioButtons(radio_ax, labels=time_options, active=0)

# adjust radius here. The default is 0.05
for circle in radio.circles:
    circle.set_radius(0.1)

for label in radio.labels:
    label.set_fontsize(14)  # Change the fontsize to the desired value

def on_select(label):
    global TIME_WINDOW
    TIME_WINDOW = int(label)
radio.on_clicked(on_select)

fig.canvas.mpl_connect('close_event', on_close)

plt.show()
