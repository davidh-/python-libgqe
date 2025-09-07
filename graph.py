import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os
import time
import serial

import matplotlib.widgets as widgets
from threading import Thread, Lock
from threading import Thread, Lock


TIME_WINDOW = 1  # default time window in minutes


os.environ["DISPLAY"] = ":0.0"
os.environ["XAUTHORITY"] = "/home/pi/.Xauthority"

"""
Use current working directory for project root so data files are written under
the folder where the script is started (e.g., repo's python-libgqe/).
"""
pro_dir = os.getcwd().rstrip("/") + "/"

now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")

data_dir = os.path.join(pro_dir, "data")
os.makedirs(data_dir, exist_ok=True)
data_file = os.path.join(data_dir, timestamp + ".csv")
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

# Pre-create text labels once; update their content each frame
text_cpm_h = ax1.text(1.01, 0.5, "", transform=ax1.transAxes, va='center')
text_cpm_l = ax2.text(1.01, 0.5, "", transform=ax2.transAxes, va='center')
text_emf   = ax3.text(1.01, 0.5, "", transform=ax3.transAxes, va='center')
text_rf    = ax4.text(1.01, 0.5, "", transform=ax4.transAxes, va='center')
text_ef    = ax5.text(1.01, 0.5, "", transform=ax5.transAxes, va='center')
text_vel   = ax6.text(1.01, 0.5, "", transform=ax6.transAxes, va='center')
text_alt   = ax7.text(1.01, 0.5, "", transform=ax7.transAxes, va='center')

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

    if (response == "GQ-EMF390v2Re 3.70\r\n"):
        print(f"Successfull port and power on for {name_390}. Port is {port_390}.")
        #get_config = '<GETCFG>>'.encode() 
        #ser.write(get_config)
        #response = ser.read(256).decode('utf-8')  # 
        #print(response)


        ser.close()
        break
    elif stop_try_390:
        print(f"Error: Unable to execute command for {name_390}. Something wrong. Check physical connections.")
        ser.close()
        exit() 
    else:
        print(f"Error: Unable to execute command for {name_390}. Changing default ports. Retrying...")
        port_390 = "/dev/ttyUSB0"
        stop_try_390 = True
        ser.close()


# Persistent EMF serial connection (reuse across frames)
ser_390 = serial.Serial(port_390, baud_rate, timeout=0.2)

# Background EMF/EF/RF reader state
emf_value = 0.0
ef_value = 0.0
rf_value = 0.0
emf_lock = Lock()


def _read_response_bg(ser):
    """Background-friendly serial read similar to read_response inside update()."""
    deadline = time.time() + 0.25
    buf = b''
    while time.time() < deadline and not buf:
        try:
            n = ser.in_waiting
            if n:
                buf += ser.read(n)
                break
        except Exception:
            break
        time.sleep(0.002)

    if buf:
        gap_deadline = time.time() + 0.02
        while time.time() < gap_deadline:
            try:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    gap_deadline = time.time() + 0.01
                else:
                    time.sleep(0.001)
            except Exception:
                break

    try:
        return buf.decode('utf-8', errors='ignore').strip()
    except Exception:
        return ''


def _emf_reader_loop():
    global emf_value, ef_value, rf_value
    while True:
        try:
            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETEMF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock:
                        emf_value = v
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETEF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock:
                        ef_value = v
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETRFTOTALDENSITY>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[0])
                    with emf_lock:
                        rf_value = v
                except Exception:
                    pass

            time.sleep(0.01)
        except Exception:
            # Keep the loop alive even if a read fails
            time.sleep(0.05)


# Start background EMF reader
Thread(target=_emf_reader_loop, daemon=True).start()

# Persistent CPM serial connection (reuse across frames)
ser_500_bg = serial.Serial(port_500, baud_rate, timeout=0.5)

# Background CPM reader state
cpm_h_value = 0.0
cpm_l_value = 0.0
cpm_lock = Lock()


def _cpm_reader_loop():
    global cpm_h_value, cpm_l_value
    while True:
        try:
            try:
                ser_500_bg.reset_input_buffer()
            except Exception:
                pass
            # High CPM
            ser_500_bg.write(b'<GETCPMH>>')
            resp = ser_500_bg.read(4)
            if len(resp) == 4:
                try:
                    v = int.from_bytes(resp, byteorder='big')
                    with cpm_lock:
                        cpm_h_value = float(v)
                except Exception:
                    pass

            # Low CPM
            ser_500_bg.write(b'<GETCPML>>')
            resp = ser_500_bg.read(4)
            if len(resp) == 4:
                try:
                    v = int.from_bytes(resp, byteorder='big')
                    with cpm_lock:
                        cpm_l_value = float(v)
                except Exception:
                    pass

            time.sleep(0.02)
        except Exception:
            time.sleep(0.05)


# Start background CPM reader
Thread(target=_cpm_reader_loop, daemon=True).start()

# Background EMF/EF/RF reader state
emf_value = 0.0
ef_value = 0.0
rf_value = 0.0
emf_lock = Lock()


def _read_response_bg(ser):
    """Background-friendly serial read similar to read_response inside update()."""
    deadline = time.time() + 0.25
    buf = b''
    while time.time() < deadline and not buf:
        try:
            n = ser.in_waiting
            if n:
                buf += ser.read(n)
                break
        except Exception:
            break
        time.sleep(0.002)

    if buf:
        gap_deadline = time.time() + 0.02
        while time.time() < gap_deadline:
            try:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    gap_deadline = time.time() + 0.01
                else:
                    time.sleep(0.001)
            except Exception:
                break

    try:
        return buf.decode('utf-8', errors='ignore').strip()
    except Exception:
        return ''


def _emf_reader_loop():
    global emf_value, ef_value, rf_value
    while True:
        try:
            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETEMF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock:
                        emf_value = v
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETEF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock:
                        ef_value = v
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b'<GETRFTOTALDENSITY>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[0])
                    with emf_lock:
                        rf_value = v
                except Exception:
                    pass

            time.sleep(0.01)
        except Exception:
            # Keep the loop alive even if a read fails
            time.sleep(0.05)


# Start background reader
Thread(target=_emf_reader_loop, daemon=True).start()

def update(frame):
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



    ax1.set_title(f"Lat: {round(lat,5)}, Lon: {round(lon, 5)}")
    
    time_start_cpm = time.time()
    # Use latest CPM values from background reader
    with cpm_lock:
        cpm_h = float(cpm_h_value)
        cpm_l = float(cpm_l_value)
    time_end_cpm = time.time()
    print("cpm time:", time_end_cpm - time_start_cpm)

    def read_response(ser):
        """Read available bytes with minimal latency and no busy-wait.
        - Wait briefly (<=0.25s) for the first byte.
        - Once bytes start arriving, coalesce for a short idle gap (~10–20ms).
        Returns whatever bytes were received without requiring newline.
        """
        first_deadline = time.time() + 0.25
        buf = b''
        # Wait for first byte up to a small deadline
        while time.time() < first_deadline and not buf:
            try:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    break
            except Exception:
                break
            time.sleep(0.002)

        # If we got something, allow a tiny coalescing window to grab trailing bytes
        if buf:
            gap_deadline = time.time() + 0.02
            while time.time() < gap_deadline:
                try:
                    n = ser.in_waiting
                    if n:
                        buf += ser.read(n)
                        gap_deadline = time.time() + 0.01  # extend while data flows
                    else:
                        time.sleep(0.001)
                except Exception:
                    break

        try:
            return buf.decode('utf-8', errors='ignore').strip()
        except Exception:
            return ''

    # read_until was attempted for batched reads but caused mis-splits; keep simple reader


    # Use latest EMF/EF/RF from background reader to avoid UI blocking
    time_start_emf = time.time()
    with emf_lock:
        emf = float(emf_value)
        ef = float(ef_value)
        rf = float(rf_value)
    time_end_emf = time.time()
    print("emf time:", time_end_emf - time_start_emf)


    # Update text content of pre-created labels
    text_cpm_h.set_text(f"{cpm_h}")
    text_cpm_l.set_text(f"{cpm_l}")
    text_emf.set_text(f"{emf}\nmG")
    text_rf.set_text(f"{rf}\nmW/m2")
    text_ef.set_text(f"{ef}\nV/m")
    text_vel.set_text(f"{round(vel, 1)}\nmph")
    text_alt.set_text(f"{round(alt, 2)}\nft")


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
