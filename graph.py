import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
import time
import serial

import matplotlib.widgets as widgets


TIME_WINDOW = 1  # default time window in minutes


os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

pro_dir = "/home/pi/python-libgqe/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_file = pro_dir + "/data/" + timestamp + ".csv"
with open(data_file, "w") as f:
    f.write("date-time,cpm_h,cpm_l,emf,rf,ef,altitude,latitude,longitude, velocity\n")

import gpsd

# Connect to the local gpsd
gpsd.connect()



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
port_500 = "/dev/ttyUSB1"
ver_500 = "'Re 2.42'"
unit_500_get_cpm_h = "--get-cpm-h"
unit_500_get_cpm_l = "--get-cpm-l"

name_390 = "GQEMF390"
port_390 = "/dev/ttyUSB0"
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
        print(f"Successfull port and power on for {name_500}. Port is {port_500}.")
        break
    elif stop_try_500:
        print(f"Error: Unable to execute command for {name_500}. Skipping.")
        break
    else:
        print(f"Error: Unable to execute command for {name_500}. Changing default ports. Retrying...")
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
    ser.close()

    if (response == "GQ-EMF390v2Re 3.70\r\n"):
        print(f"Successfull port and power on for {name_390}. Port is {port_390}.")
        break
    elif stop_try_390:
        print(f"Error: Unable to execute command for {name_390}. Something wrong. Check physical connections.")
        exit() 
    else:
        print(f"Error: Unable to execute command for {name_390}. Changing default ports. Retrying...")
        port_390 = "/dev/ttyUSB0"
        stop_try_390 = True


def update(frame):
    start = time.time()

    # Get gps position
    packet = gpsd.get_current()

    pos = packet.position()
    lat, lon = pos[0], pos[1]

    alt = packet.altitude() 
    alt = alt  * 3.28084 # m to ft

    vel = packet.speed()
    vel = vel * 2.237  # m/s to mph



    ax1.set_title(f"Lat: {round(lat,5)}, Lon: {round(lon, 5)}")
    
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
        print(f"Error getting GMC500Plus cpm: {e}")
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
        # response = ser.read(12).decode('utf-8')  # 
        response = read_response(ser)

        emf = float(response.split(" ")[2])



        get_ef_command = '<GETEF>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_ef_command)

        # Read the response from the 390
        # response = ser.read(13).decode('utf-8')  # 
        response = read_response(ser)

        ef = float(response.split(" ")[2])



        get_rf_command = '<GETRFTOTALDENSITY>>'.encode()  # Command must be encoded to bytes

        # Write the command to the serial port
        ser.write(get_rf_command)

        # Read the response from the 390
        # response = ser.read(20).decode('utf-8')  # 
        response = read_response(ser)

        rf = float(response.split(" ")[0])
        


        ser.close()

    except subprocess.CalledProcessError as e:
        print(f"Error getting GQEMF390 data: {e}")
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
    ax1.text(1.01, 0.5, f"{cpm_h}", transform=ax1.transAxes, va='center')
    ax2.text(1.01, 0.5, f"{cpm_l}", transform=ax2.transAxes, va='center')
    ax3.text(1.01, 0.5, f"{emf}\nmG", transform=ax3.transAxes, va='center')
    ax4.text(1.01, 0.5, f"{rf}\nmW/m2", transform=ax4.transAxes, va='center')
    ax5.text(1.01, 0.5, f"{ef}\nV/m", transform=ax5.transAxes, va='center')
    ax6.text(1.01, 0.5, f"{round(vel, 1)}\nmph", transform=ax6.transAxes, va='center')
    ax7.text(1.01, 0.5, f"{round(alt, 2)}\nft", transform=ax7.transAxes, va='center')


    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(data_file, "a") as f:
        f.write(f"{timestamp},{cpm_h},{cpm_l},{emf},{rf},{ef},{alt},{lat},{lon},{vel}\n")

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


