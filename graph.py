import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
import time
from gps3 import agps3

os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

pro_dir = "/home/pi/python-libgqe/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_file = pro_dir + "/data/" + timestamp + ".csv"
with open(data_file, "w") as f:
    f.write("date-time,cpm,emf,rf,ef,altitude,latitude,longitude\n")

from gps3.agps3threaded import AGPS3mechanism
agps_thread = AGPS3mechanism()  # Instantiate AGPS3 Mechanisms
agps_thread.stream_data()  # From localhost (), or other hosts, by example, (host='gps.ddns.net')
agps_thread.run_thread()  # Throttle time to sleep after an empty lookup, default '()' 0.2 two tenths of a second

x = []
y_cpm = []
y_emf = []
y_rf = []
y_ef = []
y_lat = []
y_lon = []
y_alt = []

fig, (ax1, ax2, ax3, ax4) = plt.subplots(nrows=4, sharex=True)

# Set the figure location to (x=0,y=0) on the screen
fig.canvas.manager.window.move(0, 0)

line_cpm, = ax1.plot(x, y_cpm)
ax1.set_ylabel("cpm")

line_emf, = ax2.plot(x, y_emf)
ax2.set_ylabel("emf\n(mG)")

line_rf, = ax3.plot(x, y_rf)
ax3.set_ylabel("rf\n(mW/m2)")

line_ef, = ax4.plot(x, y_ef)
ax4.set_ylabel("ef\n(V/m)")

gqe_cli_dir = pro_dir + "gqe-cli"

name_500 = "GMC500Plus"
port_500 = "/dev/ttyUSB0"
ver_500 = "'Re 2.42'"
unit_500_get_cpm = "--get-cpm"

name_390 = "GQEMF390"
port_390 = "/dev/ttyUSB1"
ver_390 = "'Re 3.70'"
unit_390_get_emf = "--get-emf"

arg_unit = "--unit"
arg_revision = "--revision"
arg_power = "--power"
arg_power_on = "true"

# Check if devices port is correct 
# Loop until a successful response is received for the first command
while True:
    try:
        subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, unit_500_get_cpm])
        subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, arg_power, arg_power_on])
        print(f"Successfull port and power on for {name_500}. Port is {port_500}.")
        break
    except subprocess.CalledProcessError:
        print(f"Error: Unable to execute command for {name_500}. Changing default ports. Retrying...")
        port_500, port_390 = port_390, port_500

try:
    subprocess.check_output([gqe_cli_dir, port_390, arg_unit, name_390, arg_revision, ver_390, unit_390_get_emf])
    subprocess.check_output([gqe_cli_dir, port_390, arg_unit, name_390, arg_revision, ver_390, arg_power, arg_power_on])
    print(f"Successfull port and power on for {name_390}. Port is {port_390}.")
except subprocess.CalledProcessError:
    print(f"Error: Unable to execute command for {name_390}. Something wrong. Check physical connections.")
    exit()
        
def update(frame):
    alt = agps_thread.data_stream.alt * 3.28084
    if alt == "n/a":
        alt = 0
        lat = 0
        lon = 0
    else:
        lat = agps_thread.data_stream.lat
        lon = agps_thread.data_stream.lon

    ax1.set_title(f"Latitude: {round(lat,5)}, Longitude: {round(lon, 5)}, Altitude: {round(alt, 2)} ft")
    
    try:
        output_cpm = subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, unit_500_get_cpm])
        cpm = float(output_cpm.decode().strip())
    except subprocess.CalledProcessError as e:
        print(f"Error getting GMC500Plus cpm: {e}")
        cpm = 0
    try:
        output_emf_rf_ef = subprocess.check_output([gqe_cli_dir, port_390, arg_unit, name_390, arg_revision, ver_390, unit_390_get_emf, "--get-rf", "TOTALDENSITY", "--get-ef"])
        output_list = output_emf_rf_ef.decode().split('\n')
        emf = float(output_list[0].split(" ")[0])
        rf = float(output_list[1].strip().split(" ")[0])
        ef = float(output_list[2].split(' ')[0])
    except subprocess.CalledProcessError as e:
        print(f"Error getting GQEMF390 data: {e}")
        emf = 0.0
        rf = 0.0
        ef = 0.0
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(data_file, "a") as f:
        f.write(f"{timestamp},{cpm},{emf},{rf},{ef}, {alt},{lat},{lon}\n")

    x.append(len(x))
    y_cpm.append(cpm)
    y_emf.append(emf)
    y_rf.append(rf)
    y_ef.append(ef)

    line_cpm.set_xdata(x)
    line_cpm.set_ydata(y_cpm)
    
    line_emf.set_xdata(x)
    line_emf.set_ydata(y_emf)
    
    line_rf.set_xdata(x)
    line_rf.set_ydata(y_rf)

    line_ef.set_xdata(x)
    line_ef.set_ydata(y_ef)

    # Manually set the x-limits to match the length of the x array
    ax1.set_xlim([0, len(x)])
    ax2.set_xlim([0, len(x)])
    ax3.set_xlim([0, len(x)])
    ax4.set_xlim([0, len(x)])

    ax1.relim()
    ax1.autoscale_view()
    ax2.relim()
    ax2.autoscale_view()
    ax3.relim()
    ax3.autoscale_view()    
    ax4.relim()
    ax4.autoscale_view()
    return line_cpm, line_emf, line_rf, line_ef


ani = animation.FuncAnimation(fig, update, interval=1)

plt.show()
