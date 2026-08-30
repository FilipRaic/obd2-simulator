"""Verify that the adapter is reachable and that the simulator answers.

Run this first after pairing. It prints the adapter's firmware version, the
protocol it settled on and the supported-PID mask.
"""

import sys

import elm327


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        version, _ = elm.command("ATI", wait=6.0)
        protocol, _ = elm.command("ATDP", wait=6.0)
        mask, ms = elm.command("0100", wait=6.0)
        print("port      %s" % port)
        print("adapter   %s" % version)
        print("protocol  %s" % protocol)
        print("0100      %s   (%.0f ms)" % (mask, ms))
        data = elm327.payload(mask)
        if len(data) >= 6 and data[0] == 0x41:
            got = int.from_bytes(bytes(data[2:6]), "big")
            want = elm327.supported_mask(0x00)
            print("mask      %08X, expected %08X, %s"
                  % (got, want, "match" if got == want else "MISMATCH"))
        else:
            print("mask      no answer from the simulator")


if __name__ == "__main__":
    main()
