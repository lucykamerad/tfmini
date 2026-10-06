#!/usr/bin/env python3
# Live graph of the distance from a TFmini Plus.
#
# Sliders:
#   Rate    how many samples per second go on the graph
#   Window  how many seconds of history to show
#   Sensor  the sensor's own output rate (press Apply; resets when it loses power)
#
#   ./tfmini_plot.py -p /dev/ttyUSB0 -r 20 -w 30 -s 100
import argparse
import os
import sys
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider

from tfmini import BAUDS, DEFAULT_BAUD, DEFAULT_SENSOR_HZ, MAX_SENSOR_HZ
from tfmini import open_port, parse_frames, set_sensor_rate

MAX_RATE = 100
MIN_WINDOW, MAX_WINDOW = 2, 120


class Graph:
    def __init__(self, fd, rate, window, sensor_hz):
        self.fd = fd
        self.buf = b""
        self.start = time.monotonic()
        self.last_sample = 0
        self.last_draw = 0
        self.times = deque()
        self.dists = deque()
        self.latest = None

        self.fig, self.ax = plt.subplots(figsize=(10, 6))
        self.fig.subplots_adjust(bottom=0.32)
        self.line, = self.ax.plot([], [], marker=".", ms=3)
        self.ax.set(xlabel="time (s)", ylabel="distance (cm)")
        self.ax.grid(alpha=0.3)
        self.label = self.ax.text(0.01, 0.97, "waiting for data...", va="top",
                                  family="monospace", transform=self.ax.transAxes)

        self.rate = self.add_slider(0.18, "Rate (Hz)", 1, MAX_RATE, rate)
        self.window = self.add_slider(0.12, "Window (s)", MIN_WINDOW, MAX_WINDOW, window)
        self.sensor = self.add_slider(0.06, "Sensor (Hz)", 1, MAX_SENSOR_HZ, sensor_hz)
        self.apply = Button(self.fig.add_axes([0.82, 0.055, 0.09, 0.04]), "Apply")
        self.apply.on_clicked(self.apply_sensor_rate)

        self.timer = self.fig.canvas.new_timer(interval=10)
        self.timer.add_callback(self.update)

    def add_slider(self, y, name, low, high, start):
        ax = self.fig.add_axes([0.12, y, 0.62, 0.03])
        return Slider(ax, name, low, high, valinit=start, valstep=1)

    def apply_sensor_rate(self, event):
        try:
            set_sensor_rate(self.fd, int(self.sensor.val))
        except OSError as e:
            self.lost(e)
            return
        self.buf = b""  # drop frames sent at the old rate

    def lost(self, error):
        self.timer.stop()
        self.label.set_text(f"Lost the sensor: {error.strerror}")
        self.fig.canvas.draw_idle()

    def read(self):
        try:
            chunk = os.read(self.fd, 4096)
        except BlockingIOError:
            return  # nothing new yet
        except OSError as e:
            self.lost(e)
            return

        frames, self.buf = parse_frames(self.buf + chunk)
        gap = 1 / self.rate.val
        for dist, strength, temp in frames:
            self.latest = (dist, strength, temp)
            now = time.monotonic()
            if now - self.last_sample >= gap:
                # step forward by exactly one gap so the rate doesn't drift
                self.last_sample = max(self.last_sample + gap, now - gap)
                self.times.append(now - self.start)
                self.dists.append(dist)

    def update(self):
        self.read()
        now = time.monotonic()
        if now - self.last_draw < 1 / 30:  # 30 fps is plenty
            return
        self.last_draw = now

        t = now - self.start
        oldest = t - self.window.val
        while self.times and self.times[0] < oldest:
            self.times.popleft()
            self.dists.popleft()
        if not self.times:
            return

        low, high = min(self.dists), max(self.dists)
        pad = max(5, (high - low) / 10)
        self.line.set_data(self.times, self.dists)
        self.ax.set_xlim(oldest, t)
        self.ax.set_ylim(max(0, low - pad), high + pad)
        self.label.set_text("Distance {} cm   Strength {}   Temp {:.1f} C".format(*self.latest))
        self.fig.canvas.draw_idle()

    def run(self):
        self.timer.start()
        plt.show()


def main():
    ap = argparse.ArgumentParser(description="TFmini Plus live graph")
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD, choices=BAUDS)
    ap.add_argument("-r", "--rate", type=int, default=20, help=f"samples per second (1-{MAX_RATE})")
    ap.add_argument("-w", "--window", type=int, default=30,
                    help=f"seconds of history ({MIN_WINDOW}-{MAX_WINDOW})")
    ap.add_argument("-s", "--sensor-rate", type=int, metavar="HZ",
                    help=f"set the sensor output rate (1-{MAX_SENSOR_HZ}), not saved")
    args = ap.parse_args()

    fd, _ = open_port(args.port, args.baud)
    sensor_hz = DEFAULT_SENSOR_HZ
    if args.sensor_rate is not None:
        try:
            set_sensor_rate(fd, args.sensor_rate)
        except ValueError as e:
            sys.exit(e)
        sensor_hz = args.sensor_rate

    rate = min(MAX_RATE, max(1, args.rate))
    window = min(MAX_WINDOW, max(MIN_WINDOW, args.window))
    try:
        Graph(fd, rate, window, sensor_hz).run()
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
