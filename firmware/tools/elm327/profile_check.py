"""Show that the Manual profile really does freeze the values.

Four readings twelve seconds apart. In Idle or Drive the O2 voltage carries
noise and the coolant creeps towards its target, so both move. In Manual they
stand still, which is what makes a comparison against the device screen
meaningful.

One value keeps moving in Manual as well: engine run time, PID 0x1F. That is
not a fault. In simulator_core.cpp the run-time accumulator sits above the
guard on the profile, so it advances in every profile, Manual included.
"""

import sys
import time

import elm327

WATCHED = (0x14, 0x1F, 0x0C, 0x05)
SAMPLES = 4
GAP_S = 12


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        labels = [elm327.SENSOR_BY_PID[pid].label for pid in WATCHED]
        print("%9s  %s" % ("at", "  ".join("%12s" % label for label in labels)))
        seen = {pid: set() for pid in WATCHED}
        start = time.perf_counter()
        for index in range(SAMPLES):
            row = []
            for pid in WATCHED:
                data, _, _ = elm327.read_pid(elm, pid)
                raw = " ".join("%02X" % b for b in data) if data else "-"
                seen[pid].add(raw)
                row.append(raw)
            print("%8.1fs  %s" % (time.perf_counter() - start,
                                  "  ".join("%12s" % value for value in row)))
            if index < SAMPLES - 1:
                time.sleep(GAP_S)

    print()
    for pid in WATCHED:
        sensor = elm327.SENSOR_BY_PID[pid]
        state = "steady" if len(seen[pid]) == 1 else "changing"
        print("0x%02X  %-16s %s" % (pid, sensor.label, state))


if __name__ == "__main__":
    main()
