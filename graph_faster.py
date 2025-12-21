#!/usr/bin/env python3
import os, sys, time, datetime, subprocess
from collections import deque
from threading import Thread, Lock
import signal
import logging

import serial
import gpsd

from PyQt5 import QtCore, QtWidgets
import pyqtgraph as pg

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Import API server
try:
    import api_server
    API_SERVER_ENABLED = True
except ImportError:
    print("Warning: api_server module not found. API will not be available.")
    API_SERVER_ENABLED = False

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

# Timeout handler for potentially blocking operations
class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

# Connect to gpsd with timeout
logger.info("Attempting to connect to gpsd...")
gpsd_available = False
try:
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(5)  # 5 second timeout
    gpsd.connect()
    signal.alarm(0)  # Cancel alarm
    gpsd_available = True
    logger.info("Successfully connected to gpsd")
    print("Successfully connected to gpsd")
except TimeoutError:
    logger.warning("gpsd connection timed out after 5 seconds. GPS data will not be available.")
    print("Warning: gpsd connection timed out. GPS data will not be available.")
    gpsd_available = False
except Exception as e:
    logger.error(f"Failed to connect to gpsd: {type(e).__name__}: {e}")
    print(f"Warning: Failed to connect to gpsd: {e}. GPS data will not be available.")
    gpsd_available = False

# --------------------------- Device bring-up ---------------------------
def detect_gmc500(port_500, port_390):
    logger.info(f"Starting GMC-500+ detection on port {port_500}")
    stop_try_500 = False
    max_attempts = 2
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        logger.debug(f"GMC-500+ detection attempt {attempt}/{max_attempts} on port {port_500}")
        try:
            ser = serial.Serial(port_500, BAUD_RATE, timeout=2)
            ser.write(b'<POWERON>>')
            time.sleep(0.5)
            ser.write(b'<GETVER>>')
            resp = ser.read(17).decode("utf-8")
            ser.close()
            logger.debug(f"GMC-500+ response: '{resp}'")
            if resp == "GMC-500+Re 2.42":
                logger.info(f"GMC-500+ detected successfully on port {port_500}")
                print(f"Successful port and power on for GMC-500+. Port {port_500}")
                return port_500, port_390
            elif stop_try_500:
                logger.warning("GMC-500+ command failed, skipping")
                print("Error: Unable to execute command for GMC-500+. Skipping.")
                return port_500, port_390
            else:
                logger.info(f"GMC-500+ not found on {port_500}, swapping to {port_390}")
                print("Error: GMC-500+ not on port. Swapping ports and retrying...")
                port_500, port_390 = port_390, port_500
                stop_try_500 = True
        except Exception as e:
            logger.error(f"GMC-500+ detection error on {port_500}: {type(e).__name__}: {e}")
            if stop_try_500:
                print(f"Final failure GMC-500+: {e}")
                return port_500, port_390
            print(f"GMC-500+ try failed ({e}), swapping once...")
            port_500, port_390 = port_390, port_500
            stop_try_500 = True
    logger.error("GMC-500+ detection failed after max attempts")
    print("Error: Unable to detect GMC-500+ after max attempts.")
    return port_500, port_390

def detect_emf390(port_390):
    logger.info(f"Starting EMF390 detection on port {port_390}")
    stop_try_390 = False
    max_attempts = 2
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        logger.debug(f"EMF390 detection attempt {attempt}/{max_attempts} on port {port_390}")
        try:
            ser = serial.Serial(port_390, BAUD_RATE, timeout=2)
            ser.write(b'<POWERON>>')
            time.sleep(2)
            ser.write(b'<GETVER>>')
            resp = ser.read(20).decode("utf-8")
            logger.debug(f"EMF390 response: '{resp}'")
            if resp == "GQ-EMF390v2Re 3.70\r\n":
                logger.info(f"EMF390 detected successfully on port {port_390}")
                print(f"Successful port and power on for EMF390. Port {port_390}")
                ser.close()
                return port_390
            elif stop_try_390:
                logger.warning("EMF390 command failed, check connections")
                print("Error: Unable to execute command for EMF390. Check connections.")
                ser.close()
                return None
            else:
                logger.info(f"EMF390 not found on {port_390}, trying /dev/ttyUSB0")
                print("EMF390 not found on default, trying /dev/ttyUSB0 ...")
                ser.close()
                port_390 = "/dev/ttyUSB0"
                stop_try_390 = True
        except Exception as e:
            logger.error(f"EMF390 detection error on {port_390}: {type(e).__name__}: {e}")
            if stop_try_390:
                print(f"Final failure EMF390: {e}")
                return None
            print(f"EMF390 try failed ({e}), switching to /dev/ttyUSB0 once...")
            port_390 = "/dev/ttyUSB0"
            stop_try_390 = True
    logger.error("EMF390 detection failed after max attempts")
    print("Error: Unable to detect EMF390 after max attempts.")
    return None

port_500, port_390 = detect_gmc500(PORT_500_DEFAULT, PORT_390_DEFAULT)
port_390 = detect_emf390(port_390)

# Persistent serial if available (with error handling)
logger.info("Opening persistent serial connections...")
ser_390 = None
ser_500 = None
try:
    if port_390:
        logger.debug(f"Opening EMF390 serial on {port_390} (baud={BAUD_RATE}, timeout=0.5s, write_timeout=1.0s)")
        ser_390 = serial.Serial(port_390, BAUD_RATE, timeout=0.5, write_timeout=1.0)
        logger.info(f"Opened persistent serial connection for EMF390 on {port_390}")
        print(f"Opened persistent serial connection for EMF390 on {port_390}")
    else:
        logger.warning("No EMF390 port available, EMF390 serial will not be opened")
except Exception as e:
    logger.error(f"Failed to open EMF390 serial connection: {type(e).__name__}: {e}")
    print(f"Failed to open EMF390 serial connection: {e}")
    ser_390 = None

try:
    if port_500:
        logger.debug(f"Opening GMC-500+ serial on {port_500} (baud={BAUD_RATE}, timeout=0.5s, write_timeout=1.0s)")
        ser_500 = serial.Serial(port_500, BAUD_RATE, timeout=0.5, write_timeout=1.0)
        logger.info(f"Opened persistent serial connection for GMC-500+ on {port_500}")
        print(f"Opened persistent serial connection for GMC-500+ on {port_500}")
    else:
        logger.warning("No GMC-500+ port available, GMC-500+ serial will not be opened")
except Exception as e:
    logger.error(f"Failed to open GMC-500+ serial connection: {type(e).__name__}: {e}")
    print(f"Failed to open GMC-500+ serial connection: {e}")
    ser_500 = None

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
    global emf_value, ef_value, rf_value, ser_390, port_390
    if not ser_390:
        logger.warning("EMF reader loop exiting: ser_390 not available")
        return
    logger.info("EMF reader loop started")
    consecutive_errors = 0
    max_consecutive_errors = 10
    read_count = 0
    reconnect_attempts = 0
    max_reconnect_attempts = 3
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
                    consecutive_errors = 0  # Reset on success
                    reconnect_attempts = 0  # Reset reconnect attempts on success
                    read_count += 1
                    if read_count % 100 == 0:
                        logger.debug(f"EMF reader: {read_count} successful reads, current EMF={v:.3f}")
                except Exception as parse_err:
                    logger.warning(f"EMF reader: Failed to parse EMF response '{r}': {parse_err}")

            try: ser_390.reset_input_buffer()
            except: pass
            ser_390.write(b'<GETEF>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[2])
                    with emf_lock: ef_value = v
                except Exception as parse_err:
                    logger.warning(f"EMF reader: Failed to parse EF response '{r}': {parse_err}")

            try: ser_390.reset_input_buffer()
            except: pass
            ser_390.write(b'<GETRFTOTALDENSITY>>')
            r = _read_response_bg(ser_390)
            if r:
                try:
                    v = float(r.split(' ')[0])
                    with emf_lock: rf_value = v
                except Exception as parse_err:
                    logger.warning(f"EMF reader: Failed to parse RF response '{r}': {parse_err}")
            time.sleep(0.01)
        except serial.SerialException as e:
            consecutive_errors += 1
            logger.error(f"EMF reader: Serial error #{consecutive_errors}: {type(e).__name__}: {e}")

            # Try to recover from serial connection failure
            if "Input/output error" in str(e) or "write failed" in str(e):
                logger.warning("EMF reader: Detected I/O error, attempting to reconnect...")
                try:
                    if ser_390:
                        ser_390.close()
                        logger.info("EMF reader: Closed broken serial connection")
                except Exception as close_err:
                    logger.error(f"EMF reader: Error closing serial: {close_err}")

                # Try to reconnect
                reconnect_attempts += 1
                if reconnect_attempts <= max_reconnect_attempts and port_390:
                    logger.info(f"EMF reader: Reconnect attempt {reconnect_attempts}/{max_reconnect_attempts} to {port_390}")
                    try:
                        ser_390 = serial.Serial(port_390, BAUD_RATE, timeout=0.5, write_timeout=1.0)
                        logger.info(f"EMF reader: Successfully reconnected to {port_390}")
                        print(f"EMF reader: Reconnected to {port_390}")
                        consecutive_errors = 0  # Reset errors on successful reconnect
                        time.sleep(0.5)  # Brief pause before resuming
                        continue
                    except Exception as reconnect_err:
                        logger.error(f"EMF reader: Reconnect failed: {reconnect_err}")
                        ser_390 = None
                        time.sleep(2)  # Wait longer before retrying
                else:
                    logger.critical(f"EMF reader: Max reconnect attempts reached ({max_reconnect_attempts}), will retry later")
                    reconnect_attempts = 0  # Reset for next cycle
                    time.sleep(5)  # Wait longer before retrying

            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"EMF reader: Too many consecutive errors ({consecutive_errors}), continuing with backoff")
                print(f"EMF reader: Too many consecutive errors ({consecutive_errors}), last error: {e}")
                consecutive_errors = 0  # Reset to avoid spam
            time.sleep(0.5)  # Longer sleep on error
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"EMF reader: Error #{consecutive_errors}: {type(e).__name__}: {e}")
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"EMF reader: Too many consecutive errors ({consecutive_errors}), continuing with backoff")
                print(f"EMF reader: Too many consecutive errors ({consecutive_errors}), last error: {e}")
                consecutive_errors = 0  # Reset to avoid spam
            time.sleep(0.5)  # Longer sleep on error

def cpm_reader_loop():
    global cpm_h_value, cpm_l_value, ser_500, port_500
    if not ser_500:
        logger.warning("CPM reader loop exiting: ser_500 not available")
        return
    logger.info("CPM reader loop started")
    consecutive_errors = 0
    max_consecutive_errors = 10
    read_count = 0
    reconnect_attempts = 0
    max_reconnect_attempts = 3
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
                    consecutive_errors = 0  # Reset on success
                    reconnect_attempts = 0  # Reset reconnect attempts on success
                    read_count += 1
                    if read_count % 100 == 0:
                        logger.debug(f"CPM reader: {read_count} successful reads, current CPM_H={v}")
                except Exception as parse_err:
                    logger.warning(f"CPM reader: Failed to parse CPM_H response (len={len(resp)}): {parse_err}")
            else:
                logger.warning(f"CPM reader: CPM_H response wrong length (expected 4, got {len(resp)})")

            ser_500.write(b'<GETCPML>>')
            resp = ser_500.read(4)
            if len(resp) == 4:
                try:
                    v = int.from_bytes(resp, "big")
                    with cpm_lock: cpm_l_value = float(v)
                except Exception as parse_err:
                    logger.warning(f"CPM reader: Failed to parse CPM_L response (len={len(resp)}): {parse_err}")
            else:
                logger.warning(f"CPM reader: CPM_L response wrong length (expected 4, got {len(resp)})")
            time.sleep(0.02)
        except serial.SerialException as e:
            consecutive_errors += 1
            logger.error(f"CPM reader: Serial error #{consecutive_errors}: {type(e).__name__}: {e}")

            # Try to recover from serial connection failure
            if "Input/output error" in str(e) or "write failed" in str(e):
                logger.warning("CPM reader: Detected I/O error, attempting to reconnect...")
                try:
                    if ser_500:
                        ser_500.close()
                        logger.info("CPM reader: Closed broken serial connection")
                except Exception as close_err:
                    logger.error(f"CPM reader: Error closing serial: {close_err}")

                # Try to reconnect
                reconnect_attempts += 1
                if reconnect_attempts <= max_reconnect_attempts and port_500:
                    logger.info(f"CPM reader: Reconnect attempt {reconnect_attempts}/{max_reconnect_attempts} to {port_500}")
                    try:
                        ser_500 = serial.Serial(port_500, BAUD_RATE, timeout=0.5, write_timeout=1.0)
                        logger.info(f"CPM reader: Successfully reconnected to {port_500}")
                        print(f"CPM reader: Reconnected to {port_500}")
                        consecutive_errors = 0  # Reset errors on successful reconnect
                        time.sleep(0.5)  # Brief pause before resuming
                        continue
                    except Exception as reconnect_err:
                        logger.error(f"CPM reader: Reconnect failed: {reconnect_err}")
                        ser_500 = None
                        time.sleep(2)  # Wait longer before retrying
                else:
                    logger.critical(f"CPM reader: Max reconnect attempts reached ({max_reconnect_attempts}), will retry later")
                    reconnect_attempts = 0  # Reset for next cycle
                    time.sleep(5)  # Wait longer before retrying

            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"CPM reader: Too many consecutive errors ({consecutive_errors}), continuing with backoff")
                print(f"CPM reader: Too many consecutive errors ({consecutive_errors}), last error: {e}")
                consecutive_errors = 0  # Reset to avoid spam
            time.sleep(0.5)  # Longer sleep on error
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"CPM reader: Error #{consecutive_errors}: {type(e).__name__}: {e}")
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"CPM reader: Too many consecutive errors ({consecutive_errors}), continuing with backoff")
                print(f"CPM reader: Too many consecutive errors ({consecutive_errors}), last error: {e}")
                consecutive_errors = 0  # Reset to avoid spam
            time.sleep(0.5)  # Longer sleep on error

logger.info("Starting background reader threads...")
Thread(target=emf_reader_loop, daemon=True).start()
Thread(target=cpm_reader_loop, daemon=True).start()
logger.info("Background reader threads started")

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
        # Pull GPS with timeout
        lat = lon = alt = vel = 0.0
        if gpsd_available:
            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(1)  # 1 second timeout for GPS read
                pkt = gpsd.get_current()
                signal.alarm(0)  # Cancel alarm
                # Check if we have a valid GPS fix (mode 2 = 2D fix, mode 3 = 3D fix)
                if pkt.mode >= 2:
                    lat, lon = pkt.position()
                    alt = (pkt.altitude() or 0.0) * 3.28084
                    vel = (pkt.hspeed or 0.0) * 2.237
                else:
                    # No GPS fix yet
                    lat = lon = alt = vel = 0.0
            except TimeoutError:
                logger.warning("GPS read timed out in update_gui")
                pass
            except Exception as e:
                # "GPS not active" is expected when no GPS fix, log as debug
                if "GPS not active" in str(e) or "UserWarning" in type(e).__name__:
                    if not hasattr(self, '_gps_warning_logged'):
                        logger.warning(f"GPS not active (will suppress further warnings)")
                        self._gps_warning_logged = True
                else:
                    logger.error(f"GPS error in update_gui: {type(e).__name__}: {e}")
                pass

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

        # Periodic heartbeat log (every 100 updates = ~10 seconds at 100ms refresh)
        if not hasattr(self, '_update_count'):
            self._update_count = 0
            logger.info("GUI update loop started")
        self._update_count += 1
        if self._update_count % 100 == 0:
            logger.debug(f"GUI update #{self._update_count}: cpm_h={cpm_h:.0f}, cpm_l={cpm_l:.0f}, emf={emf:.3f}, rf={rf:.3f}, ef={ef:.3f}")

        # Log to CSV (fast enough; one line per tick)
        ts = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(DATA_FILE, "a") as f:
                f.write(f"{ts},{cpm_h},{cpm_l},{emf},{rf},{ef},{alt},{lat},{lon},{vel}\n")
        except Exception as csv_err:
            logger.error(f"Failed to write to CSV file {DATA_FILE}: {type(csv_err).__name__}: {csv_err}")

        # Update API server with new data
        if API_SERVER_ENABLED:
            try:
                api_server.update_shared_data(now, cpm_h, cpm_l, emf, rf, ef, alt, lat, lon, vel)
            except Exception as e:
                logger.error(f"API server update failed: {type(e).__name__}: {e}")
                pass  # Silently ignore API errors to not disrupt GUI

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
            # Always show the full time window, even if data doesn't fill it yet
            tmax = time.time()
            tmin = tmax - TIME_WINDOW_MIN * 60
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
        logger.info("Dashboard close event triggered")
        print("Dashboard closed")
        try:
            if ser_390:
                logger.info("Closing EMF390 serial connection")
                ser_390.close()
        except Exception as e:
            logger.error(f"Error closing EMF390 serial: {e}")
        try:
            if ser_500:
                logger.info("Closing GMC-500+ serial connection")
                ser_500.close()
        except Exception as e:
            logger.error(f"Error closing GMC-500+ serial: {e}")
        logger.info("Dashboard closed, exiting")
        return super().closeEvent(ev)

# ------------------------------- Main ---------------------------------
if __name__ == "__main__":
    logger.info("="*60)
    logger.info("ELDAEON Graph Faster Data Logger starting...")
    logger.info("="*60)

    # Start API server in background thread
    if API_SERVER_ENABLED:
        logger.info("Starting API server thread...")
        api_thread = Thread(target=api_server.run_server, kwargs={'host': '0.0.0.0', 'port': 5000}, daemon=True)
        api_thread.start()
        logger.info("API server thread started")
        print("API server started in background")
    else:
        logger.warning("API server not enabled (module not found)")

    logger.info("Creating Qt application...")
    app = QtWidgets.QApplication(sys.argv)
    # Better default look
    pg.setConfigOptions(antialias=True)
    logger.info("Creating main window...")
    win = MainWindow()
    logger.info("Showing main window...")
    win.show()
    logger.info("Entering Qt event loop...")
    exit_code = app.exec_()
    logger.info(f"Qt event loop exited with code {exit_code}")
    sys.exit(exit_code)
