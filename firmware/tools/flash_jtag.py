"""Talk to the ESP32-S3 over its USB-Serial-JTAG on Windows, without letting
esptool configure the port.

Why this exists (all measured on this board, 20.08.2026.):

1. esptool opens the port itself, and on win32 it first sets (DTR=0, RTS=0),
   opens at 9600, then reconfigures to 115200. On USB-Serial-JTAG those lines
   drive the internal reset and IO0, and (0,0) is the combination esptool's own
   USBJTAGSerialReset avoids ("go through (1,1) instead of (0,0)"):
       open with pyserial defaults (DTR=1, RTS=1): raw SYNC answered 6/6
       open the esptool way        (DTR=0, RTS=0): raw SYNC answered 0/4
   Repeated attempts knock the chip out of ROM download mode while the USB
   device stays enumerated, because USB-Serial-JTAG enumerates in hardware
   without the CPU. That is why a dead link and a chip that simply left
   download mode look identical from the outside.

2. ANY reconfiguration of the open port re-issues SET_LINE_CODING and fails
   with Windows error 31. esptool changes the read timeout around every
   command, so the port configuration has to be frozen for the whole session.

3. Because it is frozen, the read timeout is whatever the port was opened with,
   for every exchange, and it has to serve two opposite needs. Too short and the
   long operations die: MD5 over 465 kB needs about 3,6 s, and a first attempt
   at 0,4 s failed with "Packet content transfer stopped (received 0 bytes)"
   AFTER all three images had already been written correctly. Too long and the
   failures crawl: at 15 s a chip that was not listening turned esptool's 35
   sync attempts into a ten-minute hang. 6 s covers the MD5 with margin and
   bounds the worst case, together with connect(attempts=2) and BUDGET_S.

Two hooks in esptool make this possible, both checked in v4.11.0:
    loader.py:329    `if isinstance(port, str):`     -> pass an OPEN Serial
                     object and the whole open path is skipped
    __init__.py:90   `def main(argv=None, esp=None)` -> pass a connected object
                     and device discovery is skipped

Everything runs at 115200. Do not pass --baud, it would be silently ignored.

Usage (chip must already be in download mode: hold BOOT/SW4, tap RESET/SW5,
release BOOT):

    python flash_jtag.py chip_id
    python flash_jtag.py flash_id
    python flash_jtag.py write_flash -z 0x0 bootloader.bin 0x8000 ...
"""

import os
import struct
import sys
import time

import serial
import serial.tools.list_ports
from serial.serialutil import SerialBase

BAUD = 115200
OPEN_ATTEMPTS = 120
OPEN_DELAY_S = 0.25
# Wide enough for the longest stub operation (MD5 over the whole app image).
READ_TIMEOUT_S = 6
WRITE_TIMEOUT_S = 6
# esptool attempts inside one port session (the link drops the odd byte).
ATTEMPTS = 5
# Floor under every read timeout esptool asks for.
#
# esptool's SYNC_TIMEOUT is 0,1 s, which is generous on a UART and far too
# short here: the raw probe needs about 0,25 s to see the ROM's answer over
# this USB path. Honouring 0,1 s literally made every sync come back empty
# ("No serial data received") even with the probe proving the chip was
# listening. 0,6 s is comfortably above what was measured and still lets a
# genuine failure resolve quickly.
MIN_READ_S = 0.6
# Wall-clock budget for the whole retry loop, seconds.
BUDGET_S = 330


def find_port(wait_s=45.0):
    """Wait for the board's port to appear, rather than giving up at once.

    Added 21.08.2026. The single-shot version forced a bad order of events: the
    command could only be started once the board was already plugged in and in
    download mode, so the chip sat waiting while a human read a message and
    typed, and it sometimes drifted out of download before the write began.
    Worse, on a wedged usbser handle the cure is a physical unplug - and with
    the board unplugged this function returned None and the script died.

    Waiting here lets the sequence run the right way round: start the command
    FIRST, then hold BOOT and plug the board in. The port then appears with the
    chip already in download mode, which is exactly the state the write needs.

    Enumeration is a read of the device list. It never opens the port, so it
    costs nothing - unlike opening, which on close makes Windows drop DTR and
    RTS and knocks the chip out of download mode.
    """
    deadline = time.time() + wait_s
    announced = False
    while True:
        for p in serial.tools.list_ports.comports():
            if "303A:1001" in p.hwid.upper():
                return p.device
        if time.time() > deadline:
            return None
        if not announced:
            print(f"[0/3] Cekam plocu do {wait_s:.0f} s. "
                  f"Drzi BOOT (SW4) i ukopcaj USB-C.")
            announced = True
        time.sleep(0.25)


def open_with_retry(port):
    last = None
    for attempt in range(1, OPEN_ATTEMPTS + 1):
        try:
            ser = serial.Serial(
                port=port,
                baudrate=BAUD,
                timeout=0,          # non-blocking; soft_read does the waiting
                write_timeout=WRITE_TIMEOUT_S,
            )
            print(f"[1/3] {port} otvoren iz {attempt}. pokusaja.")
            return ser
        except Exception as exc:  # noqa: BLE001 - pyserial raises several types
            last = exc
            if attempt % 20 == 0:
                print(f"[1/3] ...jos pokusavam otvoriti {port} ({attempt}/{OPEN_ATTEMPTS})")
            time.sleep(OPEN_DELAY_S)
    raise SystemExit(
        f"[1/3] {port} se nije dao otvoriti u {OPEN_ATTEMPTS} pokusaja.\n"
        f"      Zadnja greska: {last}\n"
        f"      Iskopcati i ukopcati USB-C, pa ponoviti ulazak u download."
    )


def slip(payload):
    out = b"\xc0"
    for b in payload:
        if b == 0xDB:
            out += b"\xdb\xdd"
        elif b == 0xC0:
            out += b"\xdb\xdc"
        else:
            out += bytes([b])
    return out + b"\xc0"


def in_download_mode(ser):
    """Raw esptool SYNC (command 0x08). Answered by the ROM loader and by a
    running stub, by nothing else.

    Drains with in_waiting rather than read(n), because the port timeout is
    deliberately wide and a blocking read of a fixed size would sit there for
    the full timeout on every silent probe.
    """
    data = b"\x07\x07\x12\x20" + b"\x55" * 32
    pkt = slip(struct.pack("<BBHI", 0x00, 0x08, len(data), 0) + data)
    for _ in range(4):
        ser.reset_input_buffer()
        ser.write(pkt)
        ser.flush()
        time.sleep(0.25)
        if ser.in_waiting and ser.read(ser.in_waiting):
            return True
        time.sleep(0.1)
    return False


def main():
    if len(sys.argv) < 2:
        raise SystemExit(f"Uporaba: python {sys.argv[0]} <esptool naredba i argumenti>")

    port = find_port()
    if port is None:
        raise SystemExit("Nema porta s VID:PID 303A:1001. Je li ploca ukopcana?")

    ser = open_with_retry(port)

    # Optional: put the chip into download mode WITHOUT the buttons,
    # JTAG_RESET=1 (21.08.2026.).
    #
    # This is esptool's own USBJTAGSerialReset sequence, run on the port this
    # script has already opened. Doing it through plain esptool is not an
    # option here - it reconfigures the port on open, and any reconfiguration
    # re-issues SET_LINE_CODING and dies with Windows error 31, which is the
    # whole reason this wrapper exists. Toggling DTR and RTS is not a
    # reconfiguration, so it goes through.
    #
    # The calls look inverted on purpose: on USB-Serial-JTAG those two lines
    # drive the internal reset and IO0, and the pair has to travel through
    # (1,1) rather than (0,0), which is the combination that knocks the chip
    # out. Windows also only propagates a DTR change when RTS is set, hence
    # the repeated setRTS(True).
    if os.environ.get("JTAG_RESET") == "1":
        print("[1b/3] Ulazak u download nacin preko DTR/RTS, bez tipki.")
        ser.setRTS(False)
        ser.setDTR(False)
        time.sleep(0.1)
        ser.setDTR(True)
        ser.setRTS(False)
        time.sleep(0.1)
        ser.setRTS(True)
        ser.setDTR(False)
        ser.setRTS(True)
        time.sleep(0.1)
        ser.setDTR(False)
        ser.setRTS(False)
        time.sleep(0.5)   # let the ROM come up and settle

    # NO raw SYNC probe here any more.
    #
    # It used to prove download mode before handing over to esptool. It also
    # broke the handover: the ROM answers a single SYNC EIGHT times over
    # (112 bytes), the drain did not always catch every last one, and the
    # stragglers landed inside esptool's first real SLIP exchange and shifted
    # its framing. That is where every "result was C0EE" came from - 0xC0 is
    # the SLIP frame delimiter being read as payload.
    #
    # The probe existed to avoid wasting a download-mode entry on a blind
    # attempt, but the thing that actually destroys that state is CLOSING the
    # port: Windows drops DTR and RTS on close, and on USB-Serial-JTAG those
    # drive the internal reset and IO0. So the rule is one download entry, one
    # port session, and esptool's own sync (which speaks the eight-response
    # protocol correctly) does the proving.

    # Optional raw SYNC probe, PROBE_FIRST=1. Off by default, because the ROM
    # answers one SYNC eight times over and stragglers can desynchronise
    # esptool's first exchange. It is here for the diagnostic case: prove the
    # link is alive and, if it is, carry straight on into the write WITHOUT
    # closing the port, so the by-hand download entry is not spent on the
    # diagnosis alone.
    probed = os.environ.get("PROBE_FIRST") == "1"
    if probed:
        alive = in_download_mode(ser)
        print(f"[2/3] sirovi SYNC: {'ODGOVARA' if alive else 'TISINA'}")
        if not alive:
            raise SystemExit(
                "[2/3] Veza ne odgovara. Cip nije u download nacinu ili je veza\n"
                "      pukla. Nista nije upisano."
            )
        # Drain the stragglers before esptool starts its own SLIP exchange.
        quiet_since = time.time()
        while time.time() - quiet_since < 0.4:
            if ser.in_waiting:
                ser.read(ser.in_waiting)
                quiet_since = time.time()
            time.sleep(0.05)

    # Freeze the port configuration for the rest of the session. See point 2 in
    # the module docstring: every reconfiguration re-issues SET_LINE_CODING and
    # this device answers that with Windows error 31. esptool's baud and
    # timeout changes are accepted and ignored, which is safe only because the
    # values it would ask for are already in place.
    ser._reconfigure_port = lambda *a, **k: None

    # Give esptool its timeouts back, in software.
    #
    # Freezing the port (above) also froze the read timeout, and that quietly
    # disabled esptool's own resilience: its SYNC is meant to give up after
    # SYNC_TIMEOUT = 0,1 s and try again, 5 times per connect attempt and 7
    # attempts over, so 35 quick tries. With the timeout stuck at 6 s each of
    # those waited sixty times too long, so on a noisy link only a couple of
    # tries ever happened before the budget ran out.
    #
    # The port is now opened non-blocking and the wait is counted here, off the
    # value esptool sets. Short exchanges fail in a tenth of a second again,
    # and the MD5 still gets its seconds.
    ser._soft_timeout = READ_TIMEOUT_S
    SerialBase.timeout = property(
        lambda self: getattr(self, "_soft_timeout", None),
        lambda self, v: setattr(self, "_soft_timeout", v),
    )

    _raw_read = ser.read

    def soft_read(size=1):
        deadline = time.time() + max(ser._soft_timeout or 0, MIN_READ_S)
        buf = b""
        while len(buf) < size:
            chunk = _raw_read(size - len(buf))
            if chunk:
                buf += chunk
                continue
            if time.time() >= deadline:
                break
            time.sleep(0.002)
        return buf

    ser.read = soft_read

    # Take the port's close() away from esptool for the whole session.
    #
    # ESPLoader.connect() ends with `self._port.close()` on the failure path
    # (loader.py, just before it raises FatalError). That is fatal here twice
    # over: the retry loop below then hits "Attempting to use a port that is
    # not open" on every remaining attempt, and closing the handle makes
    # Windows drop DTR and RTS, which resets the chip out of download mode -
    # so a by-hand button entry is burned by a failure esptool was going to
    # retry anyway. Measured: attempt 1 failed on serial noise, attempt 2 on
    # connect, attempts 3 to 5 never got to try.
    #
    # The handle is released when the process exits, which is soon enough.
    ser.close = lambda: None

    import esptool
    from esptool.targets.esp32s3 import ESP32S3ROM

    # Retry INSIDE the one port session.
    #
    # The link corrupts the odd byte from PC to board: the ROM answered
    # "0105: The format of the received message is invalid" at block 13 of a
    # plain write, and the stub path has failed at three different short
    # exchanges (enter compressed mode, leave compressed mode, MD5) while the
    # bulk transfer itself went through at 1481 kbit/s. So a single attempt is
    # a coin flip and a retry is worth a lot.
    #
    # It has to happen here, without closing the port: the chip stays in
    # download mode only as long as the session lives, because Windows drops
    # DTR and RTS on close and those drive reset and IO0 on USB-Serial-JTAG.
    # Re-running the command from the shell would cost another entry by hand.
    last = None
    deadline = time.time() + BUDGET_S
    for attempt in range(1, ATTEMPTS + 1):
        if time.time() > deadline:
            print('[retry] rok istekao, prestajem')
            break
        try:
            esp = ESP32S3ROM(ser, BAUD)
            # When our own raw SYNC has already proved download mode, skip
            # esptool's sync entirely. Measured repeatedly: the probe answers,
            # and esptool's sync in the very same session then returns
            # "No serial data received" five times over. Its sync is the step
            # that fails, and there is nothing left for it to prove.
            mode = "no_reset_no_sync" if probed else "no_reset"
            esp.connect(mode=mode, attempts=2)
            print(f"[3/3] Spojen ({attempt}. pokusaj): {esp.get_chip_description()}")
            esptool.main(["--after", "no_reset"] + sys.argv[1:], esp=esp)
            print(f"\n=== USPJEH iz {attempt}. pokusaja ===")
            return
        except Exception as exc:  # noqa: BLE001 - esptool raises FatalError
            last = exc
            # Print the type too. esptool raises FatalError with an empty
            # message on some mid-transfer failures, and a bare "pokusaj pao:"
            # tells you nothing about where it died.
            print(f"\n[retry] {attempt}. pokusaj pao: "
                  f"{type(exc).__name__}: {str(exc)[:120] or '(prazna poruka)'}")
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass
            time.sleep(1.0)

    raise SystemExit(f"Svih {ATTEMPTS} pokusaja palo. Zadnja greska: {last}")


if __name__ == "__main__":
    main()
