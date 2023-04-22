import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
from gps3 import agps3


os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

pro_dir = "/home/pi/python-libgqe/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_file = pro_dir + timestamp + ".csv"
with open(data_file, "w") as f:
    f.write("date-time,cpm,emf,rf,ef,altitude,latitude,longitude\n")
    
gps_socket = agps3.GPSDSocket()
data_stream = agps3.DataStream()
gps_socket.connect()
gps_socket.watch()


x = []
y_cpm = []
y_emf = []
y_rf = []
y_ef = []
y_lat = []
y_lon = []
y_alt = []

fig, (ax1, ax2, ax3, ax4) = plt.subplots(nrows=4, sharex=True)

line_cpm, = ax1.plot(x, y_cpm)
ax1.set_ylabel("cpm")

line_emf, = ax2.plot(x, y_emf)
ax2.set_ylabel("emf\n(mG)")

line_rf, = ax3.plot(x, y_rf)
ax3.set_ylabel("rf\n(mW/m2)")

line_ef, = ax4.plot(x, y_ef)
ax4.set_ylabel("ef\n(V/m)")

gqe_cli_dir = pro_dir + "gqe-cli"

# Loop until a successful response is received for the first command
while True:
    try:
        subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB1", "--unit", "GMC500Plus", "--revision", "'Re 2.42'", "--power", "true"])
        break
    except subprocess.CalledProcessError:
        print("Error: Unable to execute command for GMC500Plus. Retrying...")
        
# Loop until a successful response is received for the second command
while True:
    try:
        subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB0", "--unit", "GQEMF390", "--revision", "'Re 3.70'", "--power", "true"])
        break
    except subprocess.CalledProcessError:
        print("Error: Unable to execute command for GQEMF390. Retrying...")

def update(frame):
    
    end = False
    for new_data in gps_socket:
        if new_data:
            data_stream.unpack(new_data)
            alt = data_stream.alt
            lat = data_stream.lat
            lon = data_stream.lon
            if isinstance(alt, float):
                alt = alt * 3.28084
                print('alt:', alt)
                print('lat:', lat)
                print('lon:', lon)
                end = True
            if end is True:
                break
    
    try:
        output_cpm = subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB1", "--unit", "GMC500Plus", "--revision", "'Re 2.42'", "--get-cpm"])
        cpm = float(output_cpm.decode().strip())
        print("cpm:", cpm)
    except subprocess.CalledProcessError as e:
        print(f"Error getting cpm: {e}")
        cpm = 0.0

    try:
        output_emf = subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB0", "--unit", "GQEMF390", "--revision", "'Re 3.70'", "--get-emf"])
        emf = float(output_emf.decode().split(' ')[0])
        print("emf:", emf)
    except subprocess.CalledProcessError as e:
        print(f"Error getting emf: {e}")
        emf = 0.0

    try:
        output_rf = subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB0", "--unit", "GQEMF390", "--revision", "'Re 3.70'", "--get-rf", "TOTALDENSITY"])
        rf = float(output_rf.decode().strip().split(" ")[0])
        # ~ print(rf_str)
        # ~ if "mW" in rf_str:
            # ~ rf = float(rf_str.replace("mW/m2", ""))
        # ~ else:
            # ~ rf = float(rf_str.replace("W/m2", "")) * 1000
        print("rf:", rf)
    except subprocess.CalledProcessError as e:
        print(f"Error getting rf: {e}")
        rf = 0.0

    try:
        output_ef = subprocess.check_output([gqe_cli_dir, "/dev/ttyUSB0", "--unit", "GQEMF390", "--revision", "'Re 3.70'", "--get-ef"])
        ef = float(output_ef.decode().split(' ')[0])
        print("ef:", ef)
    except subprocess.CalledProcessError as e:
        print(f"Error getting ef: {e}")
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


ani = animation.FuncAnimation(fig, update, interval=100)

plt.show()
