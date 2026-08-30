"""State of the DTC bank: MIL, confirmed list and pending list.

Used for test case T-04 by running it after every step while a code is walked
up and down the scale on the device's DTC screen: absent, pending, confirmed.
An optional argument after the port is a label for the printout.
"""

import sys

import elm327


def report(elm, title):
    print("--- %s ---" % title)
    response, _ = elm.command("0101", wait=6.0)
    data = elm327.payload(response)
    print("  0101 -> %s" % response)
    if len(data) >= 3:
        status = data[2]
        print("         MIL %s, %d confirmed DTC(s)"
              % ("ON" if status & 0x80 else "off", status & 0x7F))
    for command, what in (("03", "confirmed"), ("07", "pending")):
        response, _ = elm.command(command, wait=6.0)
        codes = elm327.decode_dtc_list(response)
        print("  %-4s -> %s" % (command, response))
        print("         %s: %d  %s" % (what, len(codes), codes))
    print()


def main():
    port = elm327.port_from_argv(sys.argv)
    title = sys.argv[2] if len(sys.argv) > 2 else "DTC bank"
    with elm327.connect(port) as elm:
        report(elm, title)


if __name__ == "__main__":
    main()
