"""Test case T-06: clear the DTC bank with mode 0x04 and prove it is empty.

This changes the state of the device. Nothing is written to flash, so a reset
restores the factory scenario.

While the freeze frame is invalid the script also shows the difference
between silence and a negative response: sensor PIDs of mode 0x02
get no frame at all, and the adapter reports NO DATA only after its timeout,
while an unsupported mode answers 7F 06 11 straight away.
"""

import sys

import elm327

import read_dtcs


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        read_dtcs.report(elm, "before clearing")

        response, ms = elm.command("04", wait=8.0)
        print("mode 0x04 -> %s   (%.0f ms)" % (response, ms))
        print()

        read_dtcs.report(elm, "after clearing")

        print("freeze frame while it is invalid:")
        for command, note in (("0202", "causing DTC, answers 0x0000"),
                              ("020C", "engine RPM, must stay silent"),
                              ("0205", "coolant, must stay silent"),
                              ("06", "unsupported mode, must answer 7F 06 11")):
            response, ms = elm.command(command, wait=6.0)
            print("  %-6s %-38s -> %-24r (%.0f ms)" % (command, note, response, ms))


if __name__ == "__main__":
    main()
