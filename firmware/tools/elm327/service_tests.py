"""Test cases T-01, T-05, T-07 and T-08, plus the reference trace.

These are the cases that need nothing but the adapter. The remaining ones need
someone at the device: T-02 uses read_sensors.py, T-04 uses
read_dtcs.py while codes are walked up and down on the screen, T-06 uses
clear_dtcs.py, T-09 uses freeze_frame.py, T-10 uses reconnect_test.py and T-11
is a multimeter reading.

Raw responses go to service_tests.txt so they can be quoted as evidence.
"""

import sys

import elm327

LOG = "service_tests.txt"


def main():
    port = elm327.port_from_argv(sys.argv)
    log = open(LOG, "w", encoding="utf-8")

    def record(tag, command, response, ms):
        line = "[%s] %s -> %r  (%.0f ms)" % (tag, command, response, ms)
        print(line)
        log.write(line + "\n")
        log.flush()

    with elm327.connect(port) as elm:
        print("T-01  supported PIDs")
        for base, command in ((0x00, "0100"), (0x20, "0120"), (0x40, "0140")):
            response, ms = elm.command(command, wait=6.0)
            record("T-01", command, response, ms)
            data = elm327.payload(response)
            want = elm327.supported_mask(base)
            got = int.from_bytes(bytes(data[2:6]), "big") if len(data) >= 6 else None
            print("      expected %08X, got %s, %s"
                  % (want, "%08X" % got if got is not None else "nothing",
                     "match" if got == want else "MISMATCH"))

        print()
        print("Reference trace")
        response, ms = elm.command("010C", wait=6.0)
        record("REF", "010C", response, ms)
        print("      The reference is 7E8 04 41 0C 0C 80, which is exactly 800 rpm.")
        print("      The encoder steps in fractions of the full range, so that")
        print("      exact value cannot be dialled in by hand. Any other value")
        print("      differs only in the payload byte pair.")

        print()
        print("T-05  pending DTCs, T-07  VIN, T-08  unsupported mode")
        for tag, command, note in (("T-05", "07", "pending DTC list"),
                                   ("T-07", "0902", "VIN, multi-frame"),
                                   ("T-08", "06", "must answer 7F 06 11")):
            response, ms = elm.command(command, wait=8.0)
            record(tag, command, response, ms)
            print("      %s" % note)
            if command == "07":
                print("      codes: %s" % elm327.decode_dtc_list(response))
            if command == "0902":
                data = elm327.payload(response)
                vin = "".join(chr(b) for b in data[3:] if 32 <= b < 127)
                print("      VIN: %s" % vin)

    log.close()
    print()
    print("raw log: %s" % LOG)


if __name__ == "__main__":
    main()
