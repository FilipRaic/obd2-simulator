"""Test case T-09: the freeze frame holds the values from the moment a DTC was
confirmed, not the live ones.

The frame is captured only on the FIRST confirmation while no valid frame
exists, so the sequence has to be:

  1. clear_dtcs.py, which invalidates the old frame
  2. set a distinctive sensor value on the device
  3. confirm a DTC on the device, which captures the frame
  4. change that same sensor value again
  5. run this script

Live and frozen must then differ for the parameter that was changed and match
for the ones that were not.
"""

import sys

import elm327

WATCHED = (0x05, 0x0C, 0x11)


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        response, _ = elm.command("0202", wait=6.0)
        data = elm327.payload(response)
        print("causing DTC  0202 -> %s" % response)
        if len(data) >= 5:
            code = elm327.decode_dtc(data[3], data[4])
            print("             %s" % ("none" if code == "P0000" else code))

        response, _ = elm.command("020C01", wait=6.0)
        print("frame 1      020C01 -> %r, only frame 0 exists" % response)
        print()

        print("%-16s %14s %14s   %s" % ("parameter", "live", "frozen", ""))
        print("-" * 60)
        for pid in WATCHED:
            sensor = elm327.SENSOR_BY_PID[pid]
            live_data, _, _ = elm327.read_pid(elm, pid, mode=0x01)
            frozen_data, _, _ = elm327.read_pid(elm, pid, mode=0x02, frame=0x00)
            live = elm327.value_of(sensor, live_data)
            frozen = elm327.value_of(sensor, frozen_data)
            verdict = "DIFFERENT" if live != frozen else "same"
            print("%-16s %10s %-3s %10s %-3s   %s"
                  % (sensor.label, live, sensor.unit, frozen, sensor.unit, verdict))


if __name__ == "__main__":
    main()
