"""Keep the bus busy.

Useful whenever something has to be measured while the device is actually
answering: current draw at pin 16, a scope on the CAN pair, or simply watching
the frame counters move on the home screen.

Arguments: port, then minutes (default 15).
"""

import sys
import time

import elm327

PIDS = ("010C", "010D", "0105", "0111")


def main():
    port = elm327.port_from_argv(sys.argv)
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    sent = 0
    with elm327.connect(port) as elm:
        print("traffic started, running for %g min" % minutes)
        start = time.perf_counter()
        while time.perf_counter() - start < minutes * 60:
            for pid in PIDS:
                elm.command(pid, wait=5.0)
                sent += 1
            if sent % 200 == 0:
                print("  %.1f min, %d requests" % ((time.perf_counter() - start) / 60, sent))
    print("traffic stopped, %d requests" % sent)


if __name__ == "__main__":
    main()
