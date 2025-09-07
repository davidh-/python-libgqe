import os
import time
import datetime
from collections import deque
from threading import Thread, Lock

import serial

# Fast plotting
# Requires: pyqtgraph >= 0.12, PyQt5 (or PySide2)
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from pyqtgraph.graphicsItems.DateAxisItem import DateAxisItem

import gpsd


# Defaults
TIME_WINDOW = 1  # minutes


# Ensure X auth for Pi desktop
os.environ.setdefault("DISPLAY", ":0.0")
os.environ.setdefault("XAUTHORITY", "/home/pi/.Xauthority")

# Project/data paths (use CWD like graph.py)
pro_dir = os.getcwd().rstrip("/") + "/"
now = datetime.datetime.now()
timestamp = now.strftime("%Y-%m-%d-%H:%M:%S")
data_dir = os.path.join(pro_dir, "data")
os.makedirs(data_dir, exist_ok=True)
data_file = os.path.join(data_dir, timestamp + ".csv")
with open(data_file, "w") as f:
    f.write("date-time,cpm_h,cpm_l,emf,rf,ef,altitude,latitude,longitude, velocity\n")


# Connect gpsd
gpsd.connect()


# Serial/Device setup
baud_rate = 115200
name_500 = "GMC500Plus"
port_500 = "/dev/gmc500"
name_390 = "GQEMF390"
port_390 = "/dev/emf390"


def _probe_devices():
    # Verify GMC-500+ on port_500 (swap once if needed)
    stop_try_500 = False
    global port_500, port_390
    while True:
        ser = serial.Serial(port_500, baud_rate, timeout=1)
        ser.write(b"<POWERON>>")
        time.sleep(0.5)
        ser.write(b"<GETVER>>")
        resp = ser.read(17).decode("utf-8", errors="ignore")
        ser.close()
        if resp == "GMC-500+Re 2.42":
            print(f"Successful port and power on for {name_500}. Port is {port_500}.")
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
        ser = serial.Serial(port_390, baud_rate, timeout=1)
        ser.write(b"<POWERON>>")
        time.sleep(2)
        ser.write(b"<GETVER>>")
        resp = ser.read(20).decode("utf-8", errors="ignore")
        print(resp)
        if resp == "GQ-EMF390v2Re 3.70\r\n":
            print(f"Successful port and power on for {name_390}. Port is {port_390}.")
            ser.close()
            break
        elif stop_try_390:
            print(f"Error: Unable to execute command for {name_390}. Check physical connections.")
            ser.close()
            return
        else:
            print(f"Error: Unable to execute command for {name_390}. Changing default ports. Retrying...")
            port_390 = "/dev/ttyUSB0"
            stop_try_390 = True
            ser.close()


_probe_devices()


# Background readers (reuse connections, minimal latency)
ser_390 = serial.Serial(port_390, baud_rate, timeout=0.2)
ser_500_bg = serial.Serial(port_500, baud_rate, timeout=0.5)

emf_value = 0.0
ef_value = 0.0
rf_value = 0.0
emf_lock = Lock()

cpm_h_value = 0.0
cpm_l_value = 0.0
cpm_lock = Lock()


def _read_response_bg(ser):
    deadline = time.time() + 0.25
    buf = b""
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
        return buf.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _emf_reader_loop():
    global emf_value, ef_value, rf_value
    while True:
        try:
            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b"<GETEMF>>")
            r = _read_response_bg(ser_390)
            if r:
                try:
                    with emf_lock:
                        emf_value = float(r.split(" ")[2])
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b"<GETEF>>")
            r = _read_response_bg(ser_390)
            if r:
                try:
                    with emf_lock:
                        ef_value = float(r.split(" ")[2])
                except Exception:
                    pass

            try:
                ser_390.reset_input_buffer()
            except Exception:
                pass
            ser_390.write(b"<GETRFTOTALDENSITY>>")
            r = _read_response_bg(ser_390)
            if r:
                try:
                    with emf_lock:
                        rf_value = float(r.split(" ")[0])
                except Exception:
                    pass

            time.sleep(0.01)
        except Exception:
            time.sleep(0.05)


def _cpm_reader_loop():
    global cpm_h_value, cpm_l_value
    while True:
        try:
            try:
                ser_500_bg.reset_input_buffer()
            except Exception:
                pass
            ser_500_bg.write(b"<GETCPMH>>")
            resp = ser_500_bg.read(4)
            if len(resp) == 4:
                try:
                    with cpm_lock:
                        cpm_h_value = float(int.from_bytes(resp, byteorder="big"))
                except Exception:
                    pass

            ser_500_bg.write(b"<GETCPML>>")
            resp = ser_500_bg.read(4)
            if len(resp) == 4:
                try:
                    with cpm_lock:
                        cpm_l_value = float(int.from_bytes(resp, byteorder="big"))
                except Exception:
                    pass
            time.sleep(0.02)
        except Exception:
            time.sleep(0.05)


Thread(target=_emf_reader_loop, daemon=True).start()
Thread(target=_cpm_reader_loop, daemon=True).start()


# Data storage (timestamps in epoch seconds for fast DateAxisItem)
x = []
y_cpm_h = []
y_cpm_l = []
y_emf = []
y_rf = []
y_ef = []
y_vel = []
y_alt = []
frame_count = 0


# Qt App + UI
pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
app = QtWidgets.QApplication([])

win = QtWidgets.QWidget()
win.setWindowTitle("GQE Sensors (Fast)")
screen = app.primaryScreen()
if screen is not None:
    # Position top-left
    win.move(0, 0)

layout = QtWidgets.QVBoxLayout()
win.setLayout(layout)

# Controls for time window
controls = QtWidgets.QHBoxLayout()
layout.addLayout(controls)

controls.addWidget(QtWidgets.QLabel("Window (min):"))
btn_group = QtWidgets.QButtonGroup()
for label in ["1", "5", "10", "15", "30", "60"]:
    rb = QtWidgets.QRadioButton(label)
    if label == str(TIME_WINDOW):
        rb.setChecked(True)
    btn_group.addButton(rb)
    controls.addWidget(rb)


def _on_time_window(btn):
    global TIME_WINDOW
    try:
        TIME_WINDOW = int(btn.text())
    except Exception:
        pass


btn_group.buttonClicked.connect(_on_time_window)


# Create plot widgets (share X via linking). Use DateAxisItem at bottom.
plots = []
curves = []
labels = ["cpm_h", "cpm_l", "emf", "rf", "ef", "vel", "alt"]
pens = [
    pg.mkPen((200, 50, 50), width=2),
    pg.mkPen((50, 200, 50), width=2),
    pg.mkPen((50, 100, 200), width=2),
    pg.mkPen((200, 150, 50), width=2),
    pg.mkPen((150, 50, 200), width=2),
    pg.mkPen((0, 180, 180), width=2),
    pg.mkPen((180, 0, 180), width=2),
]

text_items = []

for i, name in enumerate(labels):
    # Bottom plot gets DateAxisItem for readable time; others share X range.
    axis = DateAxisItem(orientation='bottom') if i == len(labels) - 1 else 'bottom'
    pw = pg.PlotWidget(axisItems={'bottom': axis} if isinstance(axis, DateAxisItem) else None)
    pw.setLabel('left', name)
    pw.showGrid(x=True, y=True, alpha=0.3)
    # keep Y auto ranging even while we manage X manually
    try:
        pw.enableAutoRange(y=True)
    except Exception:
        pass
    if plots:
        pw.setXLink(plots[0])
    layout.addWidget(pw)
    plots.append(pw)
    # add small symbols so first points are visible
    try:
        color = pens[i].color()
    except Exception:
        color = (50, 50, 200)
    curve = pw.plot([], [], pen=pens[i], symbol='o', symbolSize=3, symbolBrush=color, symbolPen=None)
    curves.append(curve)

    # Right-side text readout
    ti = pg.TextItem(anchor=(1.0, 0.5))
    pw.addItem(ti)
    text_items.append(ti)


def _update_text_positions():
    # Place text items near right edge, mid Y
    for pw, ti in zip(plots, text_items):
        vb = pw.getViewBox()
        xr = vb.viewRange()[0]
        yr = vb.viewRange()[1]
        x_pos = xr[1] - (xr[1] - xr[0]) * 0.01
        y_pos = (yr[0] + yr[1]) * 0.5
        ti.setPos(x_pos, y_pos)


def _update():
    global frame_count
    # GPS
    try:
        packet = gpsd.get_current()
        pos = packet.position()
        lat, lon = pos[0], pos[1]
        alt = (packet.altitude() or 0.0) * 3.28084  # m->ft
        vel = (packet.hspeed or 0.0) * 2.237       # m/s->mph
    except Exception:
        lat = lon = 0.0
        alt = vel = 0.0

    # Sensor latest (from background threads)
    with cpm_lock:
        cpm_h = float(cpm_h_value)
        cpm_l = float(cpm_l_value)
    with emf_lock:
        emf = float(emf_value)
        ef = float(ef_value)
        rf = float(rf_value)

    # Append
    now_dt = datetime.datetime.now()
    ts = now_dt.timestamp()
    x.append(ts)
    y_cpm_h.append(cpm_h)
    y_cpm_l.append(cpm_l)
    y_emf.append(emf)
    y_rf.append(rf)
    y_ef.append(ef)
    y_vel.append(vel)
    y_alt.append(alt)

    # CSV log
    if len(x) % 2 == 0:  # throttle file IO slightly
        with open(data_file, "a") as f:
            f.write(f"{now_dt.strftime('%Y-%m-%d %H:%M:%S')},{cpm_h},{cpm_l},{emf},{rf},{ef},{alt},{lat},{lon},{vel}\n")

    # Windowing
    min_ts = ts - TIME_WINDOW * 60
    def clip(xs, ys):
        # Find first index >= min_ts; simple linear scan for clarity
        i0 = 0
        n = len(xs)
        while i0 < n and xs[i0] < min_ts:
            i0 += 1
        return xs[i0:], ys[i0:]

    # Update curves
    data_pairs = [
        (y_cpm_h, ""),
        (y_cpm_l, ""),
        (y_emf, "mG"),
        (y_rf, "mW/m2"),
        (y_ef, "V/m"),
        (y_vel, "mph"),
        (y_alt, "ft"),
    ]

    for pw, curve, (ys, unit) in zip(plots, curves, data_pairs):
        xs_c, ys_c = clip(x, ys)
        curve.setData(xs_c, ys_c)
        # Keep X range trimmed
        pw.setXRange(min_ts, ts, padding=0.02)

    # Title with GPS lat/lon on top plot
    if plots:
        plots[0].setTitle(f"Lat: {round(lat, 5)}, Lon: {round(lon, 5)}")

    # Update right-side text values
    texts = [
        f"{cpm_h}",
        f"{cpm_l}",
        f"{emf}\n mG",
        f"{rf}\n mW/m2",
        f"{ef}\n V/m",
        f"{round(vel,1)}\n mph",
        f"{round(alt,2)}\n ft",
    ]
    for ti, txt in zip(text_items, texts):
        ti.setText(txt)

    _update_text_positions()

    # occasional console heartbeat for debugging
    frame_count += 1
    if frame_count % 20 == 0:
        try:
            print(f"update {frame_count}: n={len(x)} last=({x[-1]:.1f}, {y_cpm_h[-1]:.2f}, {y_emf[-1]:.2f})")
        except Exception:
            pass


# Timer for UI updates (fast, non-blocking)
timer = QtCore.QTimer()
timer.timeout.connect(_update)
timer.start(50)  # ~20 FPS; adjust if needed


win.show()
try:
    # seed a first frame so plots show immediately
    _update()
except Exception:
    pass

if __name__ == "__main__":
    QtWidgets.QApplication.instance().exec_()
