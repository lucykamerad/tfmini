#!/usr/bin/env python3
# Reads a TFmini Plus lidar through a USB-serial adapter and prints what it sends.
#
#   ./tfmini.py                   find the port by itself
#   ./tfmini.py -p /dev/ttyUSB0   use this port
#   ./tfmini.py -r 10             print 10 readings a second (0 = print everything)
#   ./tfmini.py -s 50             set the sensor to 50 Hz first (1-1000, resets on power off)
#
# The sensor sends 9-byte frames at 115200 baud, 8N1:
#   59 59 | dist (2 bytes) | strength (2 bytes) | temp (2 bytes) | checksum
import argparse
import glob
import os
import select
import struct
import sys
import termios
import time

BAUDS = (9600, 19200, 38400, 57600, 115200, 230400, 460800)
DEFAULT_BAUD = 115200
DEFAULT_SENSOR_HZ = 100   # what the sensor does out of the box
MAX_SENSOR_HZ = 1000
FRAME_LEN = 9


def open_port(path=None, baud=DEFAULT_BAUD):
    if path is None:
        found = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
        if not found:
            sys.exit("No /dev/ttyUSB* or /dev/ttyACM* found. Plug the adapter in or use -p.")
        path = found[0]

    try:
        fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as e:
        sys.exit(f"Can't open {path}: {e.strerror} (is your user in the uucp group?)")

    # raw mode, 8 data bits, no parity, no flow control, VMIN/VTIME = 0
    speed = getattr(termios, f"B{baud}")
    cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
    termios.tcsetattr(fd, termios.TCSANOW, [0, 0, cflag, 0, speed, speed, [b"\0"] * termios.NCCS])
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd, path


def set_sensor_rate(fd, hz):
    if not 1 <= hz <= MAX_SENSOR_HZ:
        raise ValueError(f"Sensor rate must be between 1 and {MAX_SENSOR_HZ} Hz.")
    cmd = bytes([0x5A, 0x06, 0x03, hz & 0xFF, hz >> 8])
    os.write(fd, cmd + bytes([sum(cmd) & 0xFF]))


def parse_frames(buf):
    # Returns the good frames as (distance in cm, strength, temperature in C),
    # plus whatever is left over at the end (probably half a frame).
    frames = []
    i = 0
    while i + FRAME_LEN <= len(buf):
        f = buf[i:i + FRAME_LEN]
        if f[:2] == b"YY" and sum(f[:8]) % 256 == f[8]:
            dist, strength, temp = struct.unpack("<HHH", f[2:8])
            frames.append((dist, strength, temp / 8 - 256))
            i += FRAME_LEN
        else:
            i += 1  # out of sync, slide forward one byte
    return frames, buf[i:]


def main():
    ap = argparse.ArgumentParser(description="TFmini Plus reader")
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=DEFAULT_BAUD, choices=BAUDS)
    ap.add_argument("-r", "--rate", type=float, default=10, help="readings printed per second")
    ap.add_argument("-s", "--sensor-rate", type=int, metavar="HZ",
                    help=f"set the sensor output rate (1-{MAX_SENSOR_HZ}), not saved")
    args = ap.parse_args()

    fd, port = open_port(args.port, args.baud)
    if args.sensor_rate is not None:
        try:
            set_sensor_rate(fd, args.sensor_rate)
        except ValueError as e:
            sys.exit(e)
    print(f"Reading {port} at {args.baud} baud. Ctrl+C to stop.")

    gap = 1 / args.rate if args.rate > 0 else 0
    last_print = 0
    last_data = time.monotonic()
    buf = b""

    try:
        while True:
            if not select.select([fd], [], [], 0.5)[0]:
                if time.monotonic() - last_data > 2:
                    print("Nothing from the sensor. Check the wiring, the power and the baud rate.",
                          file=sys.stderr)
                    last_data = time.monotonic()
                continue

            frames, buf = parse_frames(buf + os.read(fd, 4096))
            now = last_data = time.monotonic()
            for dist, strength, temp in frames:
                if now - last_print < gap:
                    continue
                last_print = now
                # datasheet: under 100 the distance can't be trusted, 65535 means saturated
                note = "  (weak signal)" if strength < 100 or strength == 65535 else ""
                print(f"Distance: {dist:5d} cm   Strength: {strength:5d}   Temp: {temp:5.1f} C{note}")
    except KeyboardInterrupt:
        print()
    except OSError as e:
        print(f"\nLost the sensor: {e.strerror}", file=sys.stderr)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
