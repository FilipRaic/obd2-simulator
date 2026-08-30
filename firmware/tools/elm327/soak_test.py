"""Test case T-03: read eight parameters in a loop for half an hour.

What is being looked for is a lost response or a dropped link, so the script
counts both and prints a progress line every five minutes.

Arguments: port, then minutes (default 30).
"""

import statistics
import sys
import time

import serial

import elm327

PIDS = (0x0C, 0x0D, 0x05, 0x04, 0x11, 0x10, 0x42, 0x1F)
LOG = "soak_test.txt"


def main():
    port = elm327.port_from_argv(sys.argv)
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    log = open(LOG, "w", encoding="utf-8")

    def record(text):
        print(text)
        log.write(text + "\n")
        log.flush()

    record("T-03 started %s, running for %g min" % (time.strftime("%H:%M:%S"), minutes))
    record("PIDs: %s" % ", ".join("0x%02X" % pid for pid in PIDS))
    record("-" * 60)

    elm = elm327.connect(port)
    requests = lost = drops = cycles = 0
    times = []
    start = time.perf_counter()
    next_report = 300.0

    while time.perf_counter() - start < minutes * 60:
        cycles += 1
        for pid in PIDS:
            begin = time.perf_counter()
            try:
                data, response, _ = elm327.read_pid(elm, pid)
            except serial.SerialException as error:
                drops += 1
                record("  !! link dropped at %.1f min: %s"
                       % ((time.perf_counter() - start) / 60, error))
                time.sleep(2.0)
                try:
                    elm = elm327.connect(port)
                    record("     link re-established")
                except Exception as retry_error:
                    record("     reconnect failed: %s" % retry_error)
                    break
                continue
            requests += 1
            times.append((time.perf_counter() - begin) * 1000)
            if not data:
                lost += 1
                record("  !! 01%02X at %.1f min -> %r"
                       % (pid, (time.perf_counter() - start) / 60, response))

        elapsed = time.perf_counter() - start
        if elapsed >= next_report:
            record("  %5.1f min: %d cycles, %d requests, %d lost, %d drops"
                   % (elapsed / 60, cycles, requests, lost, drops))
            next_report += 300.0

    elapsed = time.perf_counter() - start
    try:
        elm.close()
    except Exception:
        pass

    times.sort()
    record("-" * 60)
    record("elapsed           %.1f min" % (elapsed / 60))
    record("cycles            %d" % cycles)
    record("requests          %d" % requests)
    record("lost responses    %d" % lost)
    record("link drops        %d" % drops)
    if times:
        record("median            %.1f ms" % statistics.median(times))
        record("95th percentile   %.1f ms" % times[int(0.95 * len(times))])
        record("longest           %.1f ms" % max(times))
    record("RESULT: %s" % ("pass" if lost == 0 and drops == 0 else "FAIL, see above"))
    log.close()


if __name__ == "__main__":
    main()
