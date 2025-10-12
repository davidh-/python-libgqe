#!/usr/bin/env python3
import os, sys, time, datetime, subprocess
from collections import deque
from threading import Thread, Lock

import serial
import gpsd

from PyQt5 import QtCore, QtWidgets
import pyqtgraph as pg

# ----------------------------- Config ---------------------------------
TIME_WINDOW_MIN = 1              # default time window (minutes)
UPDATE_MS = 100                  # GUI refresh timer (milliseconds)
BAUD_RATE = 115200
PORT_500_DEFAULT = "/dev/gmc500"
PORT_390_DEFAULT = "/dev/emf390"

# CSV logging dir
PRO_DIR = os.getcwd().rstrip("/") + "/"
DATA_DIR = os.path.join(PRO_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
tstamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
DATA_FILE = os.path.join(DATA_DIR, tstamp + ".csv")
with open(DATA_FILE, "w") as f:
    f.write("date-time,cpm_h,cpm_l,emf,rf,ef,altitude,latitude,longitude,velocity\n")

# Connect to gpsd
gpsd.connect()

# --------------------------- Device bring-up ---------------------------
def detect_gmc500(port_500, port_390):
    stop_try_500 = False
    while True:
        try:
            ser = serial.Serial(port_500, BAUD_RATE, timeout=1)
            ser.write(b'<POWERON>>')
            time.sleep(0.5)
            ser.write(b'<GETVER>>')
            resp = ser.read(17).decode("utf-8")
            ser.close()
            if resp == "GMC-500+Re 2.42":
                print(f"Successful port and power on for GMC-500+. Port {port_500}")
                return port_500, port_390
            elif stop_try_500:
                print("Error: Unable to execute command for GMC-500+. Skipping.")
                return port_500, port_390
            else:
                print("Error: GMC-500+ not on port. Swapping ports and retrying...")
                port_500, port_390 = port_390, port_500
                stop_try_500 = True
        except Exception as e:
            if stop_try_500:
                print(f"Final failure GMC-500+: {e}")
                return port_500, port_390
            print(f"GMC-500+ try failed ({e}), swapping once...")
            port_500, port_390 = port_390, port_500
            stop_try_500 = True

def detect_emf390(port_390):
    stop_try_390 = False
    while True:
        try:
            ser = serial.Serial(port_390, BAUD_RATE, timeout=1)
            ser.write(b'<POWERON>>')
            time.sleep(2)
            ser.write(b'<GETVER>>')
            resp = ser.read(20).decode("utf-8")
            if resp == "GQ-EMF390v2Re 3.70\r\n":
                print(f"Successful port and power on for EMF390. Port {port_390}")
                ser.close()
                return port_390
            elif stop_try_390:
                print("Error: Unable to execute command for EMF390. Check connections.")
                ser.close()
                return None
            else:
                print("EMF390 not found on default, trying /dev/ttyUSB0 ...")
                ser.close()
                port_390 = "/dev/ttyUSB0"
                stop_try_390 = True
        except Exception as e:
            if stop_try_390:
                print(f"Final failure EMF390: {e}")
                return None
            print(f"EMF390 try failed ({e}), switching to /dev/ttyUSB0 once...")
            port_390 = "/dev/ttyUSB0"
            stop_try_390 = True

port_500, port_390 = detect_gmc500(PORT_500_DEFAULT, PORT_390_DEFAULT)
port_390 = detect_emf390(port_390)

# Persistent serial if available
ser_390 = serial.Serial(port_390, BAUD_RATE, timeout=0.2) if port_390 else None
ser_500 = serial.Serial(port_500, BAUD_RATE, timeout=0.5) if port_500 else None

# --------------------------- Background readers -----------------------
emf_value = 0.0
ef_value  = 0.0
rf_value  = 0.0
cpm_h_value = 0.0
cpm_l_value = 0.0

emf_lock = Lock()
cpm_lock = Lock()

def _read_response_bg(ser, first_deadline_s=0.25, gap_s=0.02):
    deadline = time.time() + first_deadline_s
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
        gap_dead = time.time() + gap_s
        while time.time() < gap_dead:
            try:
                n = ser.in_waiting
                if n:
                    buf += ser.read(n)
                    gap_dead = time.time() + 0.01
                else:
                    time.sleep(0.001)
            except Exception:
                break
    try:
        return buf.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""

def emf_reader_loop():
    global emf_value, ef_value, rf_value
    if not ser_390:
        return
    while True:
        try:
            try: ser_390.reset_input_buffer()
            except: pass
            ser_390.write(b'<GETEMF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock: emf_value = v
                except: pass

            try: ser_390.reset_input_buffer()
            except: pass
            ser_390.write(b'<GETEF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock: ef_value = v
                except: pass

            try: ser_390.reset_input_buffer()
            except: pass
            ser_390.write(b'<GETRFTOTALDENSITY>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[0])
                    with emf_lock: rf_value = v
                except: pass
            time.sleep(0.01)
        except Exception:
            time.sleep(0.05)

def cpm_reader_loop():
    global cpm_h_value, cpm_l_value
    if not ser_500:
        return
    while True:
        try:
            try: ser_500.reset_input_buffer()
            except: pass
            ser_500.write(b'<GETCPMH>>')
            resp = ser_500.read(4)
            if len(resp) == 4:
                try:
                    v = int.from_bytes(resp, "big")
                    with cpm_lock: cpm_h_value = float(v)
                except: pass

            ser_500.write(b'<GETCPML>>')
            resp = ser_500.read(4)
            if len(resp) == 4:
                try:
                    v = int.from_bytes(resp, "big")
                    with cpm_lock: cpm_l_value = float(v)
                except: pass
            time.sleep(0.02)
        except Exception:
            time.sleep(0.05)

Thread(target=emf_reader_loop, daemon=True).start()
Thread(target=cpm_reader_loop, daemon=True).start()

# ------------------------------- Data ---------------------------------
# We’ll store timestamps as POSIX seconds (float) for DateAxisItem
def deque_len_for_window(minutes, refresh_ms=UPDATE_MS):
    # generous headroom: ~10 updates/sec even if timer drifts
    approx_rate = max(1, int(1000 / refresh_ms))
    return max(200, minutes * 60 * approx_rate)

def make_buffers(minutes):
    n = deque_len_for_window(minutes)
    return (
        deque(maxlen=n),  # t
        deque(maxlen=n),  # cpm_h
        deque(maxlen=n),  # cpm_l
        deque(maxlen=n),  # emf
        deque(maxlen=n),  # rf
        deque(maxlen=n),  # ef
        deque(maxlen=n),  # vel
        deque(maxlen=n),  # alt
    )

t_buf, cpmh_buf, cpml_buf, emf_buf, rf_buf, ef_buf, vel_buf, alt_buf = make_buffers(TIME_WINDOW_MIN)

# ------------------------------- GUI ----------------------------------
class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ELDÆON Realtime Dashboard (PyQtGraph)")
        self.resize(1100, 800)

        # Fast date axis
        axis_time = pg.graphicsItems.DateAxisItem.DateAxisItem(orientation='bottom')

        # 7 plots stacked, x-linked
        self.plot_cpmh = pg.PlotWidget(axisItems={'bottom': axis_time})
        self.plot_cpml = pg.PlotWidget()
        self.plot_emf  = pg.PlotWidget()
        self.plot_rf   = pg.PlotWidget()
        self.plot_ef   = pg.PlotWidget()
        self.plot_vel  = pg.PlotWidget()
        self.plot_alt  = pg.PlotWidget()

        self.plot_cpml.setXLink(self.plot_cpmh)
        self.plot_emf.setXLink(self.plot_cpmh)
        self.plot_rf.setXLink(self.plot_cpmh)
        self.plot_ef.setXLink(self.plot_cpmh)
        self.plot_vel.setXLink(self.plot_cpmh)
        self.plot_alt.setXLink(self.plot_cpmh)

        for p, ylab in [
            (self.plot_cpmh, "cpm_h"),
            (self.plot_cpml, "cpm_l"),
            (self.plot_emf,  "emf (mG)"),
            (self.plot_rf,   "rf (mW/m²)"),
            (self.plot_ef,   "ef (V/m)"),
            (self.plot_vel,  "vel (mph)"),
            (self.plot_alt,  "alt (ft)"),
        ]:
            p.showGrid(x=True, y=True, alpha=0.3)
            p.setLabel('left', ylab)

        # Hide bottom x-axis on all but the first (cpm_h) to avoid duplicate time axes
        for p in [self.plot_cpml, self.plot_emf, self.plot_rf, self.plot_ef, self.plot_vel, self.plot_alt]:
            try:
                p.showAxis('bottom', False)
            except Exception:
                pass

        # Curves with distinct colors
        colors = {
            'cpmh': '#e74c3c',  # red
            'cpml': '#27ae60',  # green
            'emf':  '#3498db',  # blue
            'rf':   '#e67e22',  # orange
            'ef':   '#9b59b6',  # purple
            'vel':  '#16a085',  # teal
            'alt':  '#e91e63',  # magenta
        }

        self.c_cpmh = self.plot_cpmh.plot(pen=pg.mkPen(colors['cpmh'], width=2))
        self.c_cpml = self.plot_cpml.plot(pen=pg.mkPen(colors['cpml'], width=2))
        self.c_emf  = self.plot_emf.plot(pen=pg.mkPen(colors['emf'],  width=2))
        self.c_rf   = self.plot_rf.plot(pen=pg.mkPen(colors['rf'],   width=2))
        self.c_ef   = self.plot_ef.plot(pen=pg.mkPen(colors['ef'],   width=2))
        self.c_vel  = self.plot_vel.plot(pen=pg.mkPen(colors['vel'],  width=2))
        self.c_alt  = self.plot_alt.plot(pen=pg.mkPen(colors['alt'],  width=2))

        # Live readouts: per-plot value labels on the right side
        self.lbl_latlon = QtWidgets.QLabel("Lat, Lon: -, -")
        self.val_cpmh   = QtWidgets.QLabel("-")
        self.val_cpml   = QtWidgets.QLabel("-")
        self.val_emf    = QtWidgets.QLabel("- mG")
        self.val_rf     = QtWidgets.QLabel("- mW/m²")
        self.val_ef     = QtWidgets.QLabel("- V/m")
        self.val_vel    = QtWidgets.QLabel("- mph")
        self.val_alt    = QtWidgets.QLabel("- ft")

        for w in [self.val_cpmh, self.val_cpml, self.val_emf, self.val_rf, self.val_ef, self.val_vel, self.val_alt]:
            w.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            w.setMinimumWidth(90)
            w.setStyleSheet("font-weight: 600;")

        # Match value label text colors to curves
        try:
            self.val_cpmh.setStyleSheet(f"color: {colors['cpmh']}; font-weight: 600;")
            self.val_cpml.setStyleSheet(f"color: {colors['cpml']}; font-weight: 600;")
            self.val_emf.setStyleSheet(f"color: {colors['emf']}; font-weight: 600;")
            self.val_rf.setStyleSheet(f"color: {colors['rf']}; font-weight: 600;")
            self.val_ef.setStyleSheet(f"color: {colors['ef']}; font-weight: 600;")
            self.val_vel.setStyleSheet(f"color: {colors['vel']}; font-weight: 600;")
            self.val_alt.setStyleSheet(f"color: {colors['alt']}; font-weight: 600;")
        except Exception:
            pass

        head = QtWidgets.QHBoxLayout()
        head.addWidget(self.lbl_latlon, 1)

        # Time window chooser
        self.window_choice = QtWidgets.QComboBox()
        for m in ["1","5","10","15","30","60"]:
            self.window_choice.addItem(m)
        self.window_choice.setCurrentText(str(TIME_WINDOW_MIN))
        self.window_choice.currentTextChanged.connect(self.change_time_window)
        head.addWidget(QtWidgets.QLabel("Window (min):"))
        head.addWidget(self.window_choice)

        # Layout
        # Grid with plots in column 0 and value labels in column 1
        grid = QtWidgets.QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)

        rows = [
            (self.plot_cpmh, self.val_cpmh),
            (self.plot_cpml, self.val_cpml),
            (self.plot_emf,  self.val_emf),
            (self.plot_rf,   self.val_rf),
            (self.plot_ef,   self.val_ef),
            (self.plot_vel,  self.val_vel),
            (self.plot_alt,  self.val_alt),
        ]
        for r, (plot, val) in enumerate(rows):
            grid.addWidget(plot, r, 0)
            grid.addWidget(val,  r, 1)

        v = QtWidgets.QVBoxLayout(self)
        v.addLayout(head)
        v.addLayout(grid)

        # Timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(UPDATE_MS)

    def change_time_window(self, label):
        global t_buf, cpmh_buf, cpml_buf, emf_buf, rf_buf, ef_buf, vel_buf, alt_buf, TIME_WINDOW_MIN
        minutes = int(label)
        TIME_WINDOW_MIN = minutes
        # Recreate deques with new maxlen, copying recent data
        new_max = deque_len_for_window(minutes)
        def resize(old):
            d = deque(old, maxlen=new_max)
            return d
        t_buf     = resize(t_buf)
        cpmh_buf  = resize(cpmh_buf)
        cpml_buf  = resize(cpml_buf)
        emf_buf   = resize(emf_buf)
        rf_buf    = resize(rf_buf)
        ef_buf    = resize(ef_buf)
        vel_buf   = resize(vel_buf)
        alt_buf   = resize(alt_buf)

    def update_gui(self):
        # Pull GPS
        try:
            pkt = gpsd.get_current()
            # Check if we have a valid GPS fix (mode 2 = 2D fix, mode 3 = 3D fix)
            if pkt.mode >= 2:
                lat, lon = pkt.position()
                alt = (pkt.altitude() or 0.0) * 3.28084
                vel = (pkt.hspeed or 0.0) * 2.237
            else:
                # No GPS fix yet
                lat = lon = alt = vel = 0.0
        except Exception:
            lat = lon = alt = vel = 0.0

        # Pull shared sensor values
        with cpm_lock:
            cpm_h = float(cpm_h_value)
            cpm_l = float(cpm_l_value)
        with emf_lock:
            emf = float(emf_value)
            ef  = float(ef_value)
            rf  = float(rf_value)

        # Append to buffers
        now = time.time()
        t_buf.append(now)
        cpmh_buf.append(cpm_h)
        cpml_buf.append(cpm_l)
        emf_buf.append(emf)
        rf_buf.append(rf)
        ef_buf.append(ef)
        vel_buf.append(vel)
        alt_buf.append(alt)

        # Log to CSV (fast enough; one line per tick)
        ts = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(DATA_FILE, "a") as f:
                f.write(f"{ts},{cpm_h},{cpm_l},{emf},{rf},{ef},{alt},{lat},{lon},{vel}\n")
        except Exception:
            pass

        # Update labels
        self.lbl_latlon.setText(f"Lat, Lon: {round(lat,5)}, {round(lon,5)}")
        self.val_cpmh.setText(f"{cpm_h:.0f}")
        self.val_cpml.setText(f"{cpm_l:.0f}")
        self.val_emf.setText(f"{emf:.3f} mG")
        self.val_rf.setText(f"{rf:.3f} mW/m²")
        self.val_ef.setText(f"{ef:.3f} V/m")
        self.val_vel.setText(f"{vel:.1f} mph")
        self.val_alt.setText(f"{alt:.1f} ft")

        # Update curves (use list() to give PyQtGraph a contiguous array-like)
        if len(t_buf) > 1:
            self.c_cpmh.setData(list(t_buf), list(cpmh_buf))
            self.c_cpml.setData(list(t_buf), list(cpml_buf))
            self.c_emf.setData(list(t_buf), list(emf_buf))
            self.c_rf.setData(list(t_buf), list(rf_buf))
            self.c_ef.setData(list(t_buf), list(ef_buf))
            self.c_vel.setData(list(t_buf), list(vel_buf))
            self.c_alt.setData(list(t_buf), list(alt_buf))

            # Keep x-range pinned to a moving window of TIME_WINDOW_MIN
            # Use the actual data range, bounded by the time window
            tmax = time.time()
            tmin = tmax - TIME_WINDOW_MIN * 60
            # If we have older data in the buffer, use the oldest timestamp
            if t_buf:
                actual_tmin = min(t_buf)
                # Show all available data, but don't exceed the time window
                tmin = max(actual_tmin, tmin)
            self.plot_cpmh.setXRange(tmin, tmax, padding=0)
            # y autoscale lightweight
            for plot, buf in [
                (self.plot_cpmh, cpmh_buf),
                (self.plot_cpml, cpml_buf),
                (self.plot_emf,  emf_buf),
                (self.plot_rf,   rf_buf),
                (self.plot_ef,   ef_buf),
                (self.plot_vel,  vel_buf),
                (self.plot_alt,  alt_buf),
            ]:
                if buf:
                    vmin = min(buf)
                    vmax = max(buf)
                    if vmin == vmax:
                        # Avoid zero-height range
                        vmin -= 1
                        vmax += 1
                    plot.setYRange(vmin, vmax, padding=0.1)

    def closeEvent(self, ev):
        print("Dashboard closed")
        try:
            if ser_390: ser_390.close()
        except: pass
        try:
            if ser_500: ser_500.close()
        except: pass
        return super().closeEvent(ev)

# ------------------------------- Main ---------------------------------
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # Better default look
    pg.setConfigOptions(antialias=True)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
