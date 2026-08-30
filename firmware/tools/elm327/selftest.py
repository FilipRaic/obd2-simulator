"""Check the decoders against responses actually captured from the board.

No hardware needed. Every fixture below is a verbatim response recorded from
the assembled v0.7 board on 22.08.2026., so this doubles as a record of what
the device answers.

    python selftest.py
"""

import elm327

FAILURES = []


def check(what, got, want):
    ok = got == want
    print("%-46s %s" % (what, "ok" if ok else "FAIL  got %r, want %r" % (got, want)))
    if not ok:
        FAILURES.append(what)


def main():
    # Single frame: supported PIDs, first block.
    check("payload of a single frame",
          elm327.payload("7E8 06 41 00 9E 7F 90 13"),
          [0x41, 0x00, 0x9E, 0x7F, 0x90, 0x13])

    # The three masks the device answered, against what the core builds.
    for base, response, want in (
            (0x00, "7E8 06 41 00 9E 7F 90 13", 0x9E7F9013),
            (0x20, "7E8 06 41 20 80 02 20 01", 0x80022001),
            (0x40, "7E8 06 41 40 44 00 00 10", 0x44000010)):
        data = elm327.payload(response)
        got = int.from_bytes(bytes(data[2:6]), "big")
        check("mask 0x%02X matches the device" % base, got, want)
        check("mask 0x%02X matches the core" % base, elm327.supported_mask(base), want)

    # Multi-frame: mode 0x03 with three confirmed DTCs, first frame plus one
    # consecutive frame, padded with 0x55 as ISO 15765-4 requires.
    mode_03 = "7E8 10 08 43 03 03 01 01 71\n7E8 21 04 20 55 55 55 55 55"
    check("payload of a multi-frame answer",
          elm327.payload(mode_03),
          [0x43, 0x03, 0x03, 0x01, 0x01, 0x71, 0x04, 0x20])
    check("confirmed DTC list", elm327.decode_dtc_list(mode_03),
          ["P0301", "P0171", "P0420"])
    check("pending DTC list",
          elm327.decode_dtc_list("7E8 06 47 02 01 28 05 00"),
          ["P0128", "P0500"])

    # The category lives in the top two bits of the high byte, so 0xC1 0x00 is
    # a network code and not a chassis one.
    check("U-category DTC", elm327.decode_dtc(0xC1, 0x00), "U0100")

    # VIN, first frame plus two consecutive frames.
    vin_response = ("7E8 10 14 49 02 01 57 56 57\n"
                    "7E8 21 5A 5A 5A 31 4B 5A 41\n"
                    "7E8 22 57 30 30 30 30 30 31")
    data = elm327.payload(vin_response)
    vin = "".join(chr(b) for b in data[3:] if 32 <= b < 127)
    check("VIN assembled from three frames", vin, "WVWZZZ1KZAW000001")

    # Conversion formulas, on bytes the device actually sent.
    check("coolant 0x96", elm327.value_of(elm327.SENSOR_BY_PID[0x05], [0x96]), 110)
    check("engine RPM 0x0C 0xA9",
          elm327.value_of(elm327.SENSOR_BY_PID[0x0C], [0x0C, 0xA9]), 810.25)
    check("module voltage 0x35 0xBC",
          elm327.value_of(elm327.SENSOR_BY_PID[0x42], [0x35, 0xBC]), 13.756)

    # A silent answer must decode to nothing rather than to a value.
    check("silent response", elm327.payload("NO DATA"), [])

    check("sensor table size", len(elm327.SENSORS), 21)

    print()
    if FAILURES:
        print("%d check(s) failed" % len(FAILURES))
        raise SystemExit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
