# tfmini

Small tools to read a Benewake TFmini Plus lidar through a USB-serial adapter on Linux.

- `tfmini.py` prints distance, signal strength and temperature in the terminal.
- `tfmini_plot.py` shows a live graph of the distance, with sliders for the graph rate, the history window and the sensor's own output rate.

Needs Python 3 for the terminal tool. The graph also needs matplotlib. Your user needs access to the serial port (on Arch that means the `uucp` group).

```
./tfmini.py                  # find the port by itself, 10 readings a second
./tfmini.py -p /dev/ttyUSB0 -r 0 -s 50
./tfmini_plot.py -r 20 -w 30
```

The sensor rate (`-s`, or the Sensor slider + Apply) is not saved to the sensor, so it goes back to 100 Hz after a power cycle.

MIT license.
