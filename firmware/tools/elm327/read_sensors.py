"""Test case T-02: read all 21 parameters and decode them.

The printed "screen should show" column is the decoded value rounded the way
the device rounds it, so the sheet can be ticked off against the sensor screen
row by row. A difference of up to one resolution step is expected and is what
the test case means by "within the resolution of the formula": the screen shows
the internal floating-point value, the bus carries the quantised one.

Switch the device to the Manual profile first. In Idle the model rewrites 11 of
the 21 values every 100 ms, so the two sides can never be compared.
"""

import sys

import elm327


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        print("%3s  %-16s %21s   %-8s %s"
              % ("row", "label on screen", "screen should show", "raw", "resolution"))
        print("-" * 78)
        for row, sensor in enumerate(elm327.SENSORS, 1):
            data, response, _ = elm327.read_pid(elm, sensor.pid)
            if not data:
                print("%3d  %-16s %21s" % (row, sensor.label, "NO ANSWER"))
                continue
            value = elm327.value_of(sensor, data)
            shown = ("%.*f %s" % (sensor.decimals, value, sensor.unit)).strip()
            raw = " ".join("%02X" % b for b in data)
            print("%3d  %-16s %21s   %-8s %.3f %s"
                  % (row, sensor.label, shown, raw, sensor.resolution, sensor.unit))


if __name__ == "__main__":
    main()
