import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
import time

import matplotlib.widgets as widgets

TIME_WINDOW = 1  # default time window in minutes


os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

pro_dir = "/home/pi/python-libgqe/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_file = pro_dir + "/data/" + timestamp + ".csv"
with open(data_file, "w") as f:
    f.write("date-time,cpm,emf,rf,ef,altitude,latitude,longitude, velocity\n")

from gps3.agps3threaded import AGPS3mechanism
agps_thread = AGPS3mechanism()  # Instantiate AGPS3 Mechanisms
agps_thread.stream_data()  # From localhost (), or other hosts, by example, (host='gps.ddns.net')
agps_thread.run_thread()  # Throttle time to sleep after an empty lookup, default '()' 0.2 two tenths of a second

x = []; y_cpm = []; y_emf = []; y_rf = []; y_ef = []; y_lat = []; y_lon = []; y_alt = []; y_vel = []

fig, (ax1, ax2, ax3, ax4, ax5, ax6) = plt.subplots(nrows=6, sharex=True)

line_vel, = ax5.plot(x, y_vel)
ax5.set_ylabel("vel")

line_alt, = ax6.plot(x, y_alt)
ax6.set_ylabel("alt")


# Set the figure location to (x=0,y=0) on the screen
fig.canvas.manager.window.move(0, 0)

line_cpm, = ax1.plot(x, y_cpm)
ax1.set_ylabel("cpm")

line_emf, = ax2.plot(x, y_emf)
ax2.set_ylabel("emf")

line_rf, = ax3.plot(x, y_rf)
ax3.set_ylabel("rf")

line_ef, = ax4.plot(x, y_ef)
ax4.set_ylabel("ef")

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
stop_try_500 = False
while True:
    try:
        subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, unit_500_get_cpm])
        subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, arg_power, arg_power_on])
        print(f"Successfull port and power on for {name_500}. Port is {port_500}.")
        break
    except subprocess.CalledProcessError:
        if stop_try_500:
            print(f"Error: Unable to execute command for {name_500}. Skipping.")
            break
        print(f"Error: Unable to execute command for {name_500}. Changing default ports. Retrying...")
        port_500, port_390 = port_390, port_500
        stop_try_500 = True

try:
    subprocess.check_output([gqe_cli_dir, port_390, arg_unit, name_390, arg_revision, ver_390, unit_390_get_emf])
    subprocess.check_output([gqe_cli_dir, port_390, arg_unit, name_390, arg_revision, ver_390, arg_power, arg_power_on])
    print(f"Successfull port and power on for {name_390}. Port is {port_390}.")
except subprocess.CalledProcessError:
    print(f"Error: Unable to execute command for {name_390}. Something wrong. Check physical connections.")
    exit()
        
def update(frame):
    start = time.time()
    alt = agps_thread.data_stream.alt 
    # print(alt)
    if alt == "n/a":
        alt = 0
        lat = 0
        lon = 0
        vel = 0
    else:
        alt = alt * 3.28084 # m to ft
        lat = agps_thread.data_stream.lat
        lon = agps_thread.data_stream.lon
        vel = agps_thread.data_stream.speed * 2.237  # m/s to mph


    ax1.set_title(f"Lat: {round(lat,5)}, Lon: {round(lon, 5)}")
    
    time_start_cpm = time.time()
    try:
        output_cpm = subprocess.check_output([gqe_cli_dir, port_500, arg_unit, name_500, arg_revision, ver_500, unit_500_get_cpm])
        cpm = float(output_cpm.decode().strip())
    except subprocess.CalledProcessError as e:
        print(f"Error getting GMC500Plus cpm: {e}")
        cpm = 0
    time_end_cpm = time.time()
    print("cpm time:", time_end_cpm-time_start_cpm)

    time_start_emf = time.time()
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
    time_end_emf = time.time()
    print("emf time:", time_end_emf-time_start_emf)


    # Clear any previously drawn text by removing it from the axes
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
        for text in ax.texts:
            text.remove()

    # Add text box to the right of each plot
    ax1.text(1.01, 0.5, f"{cpm}", transform=ax1.transAxes, va='center')
    ax2.text(1.01, 0.5, f"{emf}\nmG", transform=ax2.transAxes, va='center')
    ax3.text(1.01, 0.5, f"{rf}\nmW/m2", transform=ax3.transAxes, va='center')
    ax4.text(1.01, 0.5, f"{ef}\nV/m", transform=ax4.transAxes, va='center')
    ax5.text(1.01, 0.5, f"{round(vel, 1)}\nmph", transform=ax5.transAxes, va='center')
    ax6.text(1.01, 0.5, f"{round(alt, 2)}\nft", transform=ax6.transAxes, va='center')


    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(data_file, "a") as f:
        f.write(f"{timestamp},{cpm},{emf},{rf},{ef},{alt},{lat},{lon},{vel}\n")

    x.append(now)
    y_cpm.append(cpm)
    y_emf.append(emf)
    y_rf.append(rf)
    y_ef.append(ef)

    y_vel.append(vel)
    y_alt.append(alt)


    line_cpm.set_xdata(x)
    line_cpm.set_ydata(y_cpm)
    
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
    for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
        ax.set_xlim([min_time, now])
        ax.relim()
        ax.autoscale_view()

    end = time.time()
    print("update time: ", end-start)
    return line_cpm, line_emf, line_rf, line_ef, line_vel, line_alt


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


