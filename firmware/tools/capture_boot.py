"""Wait for the board's USB CDC port to appear and log everything it says.

For the custom-board-bringup build, where ARDUINO_USB_MODE=1 puts Serial on the
USB-Serial-JTAG, so the ESP-IDF bootloader banner, the firmware's own
Serial.printf output and any panic backtrace all arrive over USB-C.

Run this first, then power-cycle the board. It keeps reopening the port, so a
chip that reboots in a loop is captured too.
"""

import sys
import time

import serial
import serial.tools.list_ports

WAIT_S = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
LOG = "boot_log.txt"


def find_port():
    for p in serial.tools.list_ports.comports():
        if "303A:1001" in p.hwid.upper():
            return p.device
    return None


def main():
    t0 = time.time()
    print(f"Cekam da se port pojavi, najvise {WAIT_S:.0f} s. Ukopcaj plocu.")
    log = open(LOG, "w", encoding="utf-8", errors="replace")
    seen_any = False
    reopens = 0
    fails = {}

    while time.time() - t0 < WAIT_S:
        port = find_port()
        if port is None:
            time.sleep(0.1)
            continue

        try:
            ser = serial.Serial(port=port, baudrate=115200, timeout=0.2)
        except Exception as exc:
            # Do NOT swallow this. An earlier version retried silently here and
            # the log looked as if the port had simply never come back, when in
            # fact it was there and every open was failing.
            fails[str(exc)[:60]] = fails.get(str(exc)[:60], 0) + 1
            if sum(fails.values()) % 25 == 1:
                note = f"[{time.time() - t0:6.1f} s] {port} postoji, otvaranje pada: {str(exc)[:60]}"
                print(note)
                log.write(note + "\n")
                log.flush()
            time.sleep(0.2)
            continue

        reopens += 1
        stamp = f"\n===== {port} otvoren ({reopens}. put) u {time.time() - t0:.1f} s ====="
        print(stamp)
        log.write(stamp + "\n")
        log.flush()

        try:
            while time.time() - t0 < WAIT_S:
                data = ser.read(4096 if ser.in_waiting else 1)
                if data:
                    seen_any = True
                    text = data.decode("utf-8", errors="replace")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    log.write(text)
                    log.flush()
        except Exception as exc:  # port vanished, chip rebooted
            msg = f"\n----- veza prekinuta: {exc} -----\n"
            print(msg)
            log.write(msg)
            log.flush()
        finally:
            try:
                ser.close()
            except Exception:
                pass

    log.close()
    print(f"\n=== gotovo. otvaranja: {reopens}, ikakvih bajtova: {seen_any} ===")
    print(f"=== dnevnik: {LOG} ===")


if __name__ == "__main__":
    main()
