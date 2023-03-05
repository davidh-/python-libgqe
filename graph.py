import subprocess
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import datetime
import os

data_file = "data.csv"

# Check if the data file exists, create it with the header if it doesn't
if not os.path.isfile(data_file):
    with open(data_file, "w") as f:
        f.write("date-time,cpm,emf\n")

x = []
y_cpm = []
y_emf = []

fig, (ax1, ax2) = plt.subplots(nrows=2, sharex=True)

line_cpm, = ax1.plot(x, y_cpm)
ax1.set_ylabel("cpm")

line_emf, = ax2.plot(x, y_emf)
ax2.set_ylabel("emf")

def update(frame):
    output_cpm = subprocess.check_output(["./gqe-cli", "/dev/ttyUSB1", "--unit", "GMC500Plus", "--revision", "'Re 2.42'", "--get-cpm"])
    cpm = float(output_cpm.decode().strip())
    print(cpm)
    
    output_emf = subprocess.check_output(["./gqe-cli", "/dev/ttyUSB0", "--unit", "GQEMF390", "--revision", "'Re 3.70'", "--get-emf"])
    emf = float(output_emf.decode().split(' ')[0])
    print(emf)
    
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(data_file, "a") as f:
        f.write(f"{timestamp},{cpm},{emf}\n")

    x.append(len(x))
    y_cpm.append(cpm)
    y_emf.append(emf)

    line_cpm.set_xdata(x)
    line_cpm.set_ydata(y_cpm)
    line_emf.set_xdata(x)
    line_emf.set_ydata(y_emf)

    # Manually set the x-limits to match the length of the x array
    ax1.set_xlim([0, len(x)])
    ax2.set_xlim([0, len(x)])

    ax1.relim()
    ax1.autoscale_view()
    ax2.relim()
    ax2.autoscale_view()

    return line_cpm, line_emf


ani = animation.FuncAnimation(fig, update, interval=100)

plt.show()
