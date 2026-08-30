"""Minimal ELM327 client and OBD-II decoding helpers.

Written for the bring-up of the v0.7 board, where a diagnostic adapter is the
only working link to the simulator: the board's own USB path is dead, so
nothing can be instrumented from inside the firmware.

The adapter is reached over a virtual serial port. A Bluetooth ELM327 pairs as
an outgoing COM port, a USB one enumerates directly. Every script here takes
the port name as its first argument and falls back to DEFAULT_PORT.
"""

import time
from collections import namedtuple

import serial

DEFAULT_PORT = "COM5"
DEFAULT_BAUD = 38400

# No echo, no line feeds, spaces on so raw bytes stay readable, headers on so
# the CAN ID is part of the evidence, and the protocol pinned to ISO 15765-4
# 11-bit / 500 kbit/s rather than left to the adapter's search.
INIT = ("ATZ", "ATE0", "ATL0", "ATS1", "ATH1", "ATSP6")


class Elm327:
    def __init__(self, port=DEFAULT_PORT, baud=DEFAULT_BAUD, timeout=0.2):
        self.serial = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.3)
        self.serial.reset_input_buffer()

    def command(self, text, wait=5.0):
        """Send one command and read until the adapter's '>' prompt.

        Returns (response, elapsed_ms). Line structure is preserved, so a
        multi-frame answer stays one line per CAN frame.
        """
        self.serial.reset_input_buffer()
        self.serial.write((text + "\r").encode())
        buf = b""
        start = time.perf_counter()
        while time.perf_counter() - start < wait:
            chunk = self.serial.read(256)
            if chunk:
                buf += chunk
                if b">" in buf:
                    break
        elapsed_ms = (time.perf_counter() - start) * 1000
        text_out = buf.decode("ascii", "ignore").replace("\r", "\n").replace(">", "")
        return text_out.strip(), elapsed_ms

    def close(self):
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect(port=DEFAULT_PORT, baud=DEFAULT_BAUD):
    """Open the port and run the init sequence."""
    elm = Elm327(port, baud)
    for cmd in INIT:
        elm.command(cmd, wait=6.0)
    return elm


def _is_hex(token):
    return all(c in "0123456789ABCDEFabcdef" for c in token)


def frames(response):
    """Per-frame byte lists. The three-character CAN ID is dropped."""
    out = []
    for line in response.split("\n"):
        tokens = [t for t in line.split() if len(t) == 2 and _is_hex(t)]
        if tokens:
            out.append([int(t, 16) for t in tokens])
    return out


def payload(response):
    """Assemble the ISO-TP payload from a single- or multi-frame response."""
    got = frames(response)
    if not got:
        return []
    if len(got) == 1:
        data = got[0]
        return data[1:1 + (data[0] & 0x0F)]
    first = got[0]
    total = ((first[0] & 0x0F) << 8) | first[1]
    out = first[2:]
    for frame in got[1:]:
        out += frame[1:]
    return out[:total]


def decode_dtc(high, low):
    """Raw two-byte DTC to its printed form, per SAE J2012.

    The top two bits of the high byte select the category, so 0xC1 0x00 is
    U0100 and not a C-code.
    """
    return "%s%d%X%02X" % ("PCBU"[(high >> 6) & 3], (high >> 4) & 3, high & 0x0F, low)


def decode_dtc_list(response):
    """DTC list out of a mode 0x03 or 0x07 response."""
    data = payload(response)
    if len(data) < 2:
        return []
    count = data[1]
    codes = []
    for i in range(count):
        hi, lo = 2 + 2 * i, 3 + 2 * i
        if lo < len(data):
            codes.append(decode_dtc(data[hi], data[lo]))
    return codes


Sensor = namedtuple("Sensor", "pid label unit decimals resolution decode")

# The 21 mode 0x01 parameters, in SENSOR_TABLE order, which is also the row
# order on the device's sensor screen. Labels match sensor_meta.h, so a reading
# can be compared against the screen line by line. Resolution is the step of
# the standard's conversion formula, which is the tolerance for that
# comparison.
SENSORS = (
    Sensor(0x04, "Engine load", "%", 1, 100 / 255, lambda a, b: a * 100 / 255),
    Sensor(0x05, "Coolant temp", "C", 1, 1, lambda a, b: a - 40),
    Sensor(0x06, "STFT bank 1", "%", 1, 100 / 128, lambda a, b: a / 1.28 - 100),
    Sensor(0x07, "LTFT bank 1", "%", 1, 100 / 128, lambda a, b: a / 1.28 - 100),
    Sensor(0x0A, "Fuel pressure", "kPa", 0, 3, lambda a, b: a * 3),
    Sensor(0x0B, "Intake MAP", "kPa", 0, 1, lambda a, b: a),
    Sensor(0x0C, "Engine RPM", "rpm", 0, 0.25, lambda a, b: (256 * a + b) / 4),
    Sensor(0x0D, "Vehicle speed", "km/h", 0, 1, lambda a, b: a),
    Sensor(0x0E, "Timing adv", "deg", 1, 0.5, lambda a, b: a / 2 - 64),
    Sensor(0x0F, "Intake air", "C", 1, 1, lambda a, b: a - 40),
    Sensor(0x10, "MAF flow", "g/s", 2, 0.01, lambda a, b: (256 * a + b) / 100),
    Sensor(0x11, "Throttle", "%", 1, 100 / 255, lambda a, b: a * 100 / 255),
    Sensor(0x14, "O2 B1 S1", "V", 2, 0.005, lambda a, b: a / 200),
    Sensor(0x1C, "OBD standard", "", 0, 1, lambda a, b: a),
    Sensor(0x1F, "Run time", "s", 0, 1, lambda a, b: 256 * a + b),
    Sensor(0x21, "Dist w/ MIL", "km", 0, 1, lambda a, b: 256 * a + b),
    Sensor(0x2F, "Fuel level", "%", 0, 100 / 255, lambda a, b: a * 100 / 255),
    Sensor(0x33, "Baro press", "kPa", 0, 1, lambda a, b: a),
    Sensor(0x42, "Module volt", "V", 2, 0.001, lambda a, b: (256 * a + b) / 1000),
    Sensor(0x46, "Ambient air", "C", 1, 1, lambda a, b: a - 40),
    Sensor(0x5C, "Oil temp", "C", 1, 1, lambda a, b: a - 40),
)

SENSOR_BY_PID = {s.pid: s for s in SENSORS}


def read_pid(elm, pid, mode=0x01, frame=None):
    """One mode 0x01 or 0x02 reading. Returns (data_bytes, response, ms).

    data_bytes is empty when the simulator stays silent, which is the correct
    answer for an unsupported PID and for an invalid freeze frame.
    """
    text = "%02X%02X" % (mode, pid)
    if frame is not None:
        text += "%02X" % frame
    response, ms = elm.command(text, wait=6.0)
    data = payload(response)
    header = 2 if mode == 0x01 else 3  # mode 0x02 echoes the frame number
    if len(data) >= header and data[0] == mode + 0x40 and data[1] == pid:
        return data[header:], response, ms
    return [], response, ms


def value_of(sensor, data):
    if not data:
        return None
    return round(sensor.decode(data[0], data[1] if len(data) > 1 else 0), 4)


def supported_mask(base):
    """The mask build_supported_pids() in the protocol core produces."""
    mask = 0
    higher = False
    if base == 0x00:
        mask |= 1 << (0x20 - 0x01)  # PID 0x01 is served from the DTC bank
    for sensor in SENSORS:
        if base < sensor.pid <= base + 0x20:
            mask |= 1 << (0x20 - (sensor.pid - base))
        elif sensor.pid > base + 0x20:
            higher = True
    if higher:
        mask |= 1
    return mask & 0xFFFFFFFF


def port_from_argv(argv):
    return argv[1] if len(argv) > 1 else DEFAULT_PORT
