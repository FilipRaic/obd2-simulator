"""Upper bound on the response time, measured without an oscilloscope.

The adapter's own wait for a response is adjustable in steps of 4 ms (ATST).
Tighten it, keep asking, and the smallest setting at which every request is
still answered is a measured upper bound on P2, the request-to-response gap
that ISO 15765-4 limits to 50 ms.

Adaptive timing has to be off (ATAT0), otherwise the adapter overrides ATST.

The bound includes the transmission time of the response frame itself, roughly
230 us, so it is conservative: the device is quicker than the number printed.
It is a bound and not a distribution, so there is no median and no percentile.
"""

import sys

import elm327

REQUESTS = 50
STEPS = (0x32, 0x0C, 0x06, 0x03, 0x02, 0x01)   # x 4 ms
LOG = "response_time.txt"


def main():
    port = elm327.port_from_argv(sys.argv)
    log = open(LOG, "w", encoding="utf-8")
    best = None
    with elm327.connect(port) as elm:
        elm.command("ATAT0", wait=6.0)
        print("adaptive timing off, %d requests per step" % REQUESTS)
        print()
        print("%6s %9s %11s %9s  %s" % ("ATST", "wait", "answered", "NO DATA", "result"))
        print("-" * 56)
        for step in STEPS:
            elm.command("ATST %02X" % step, wait=5.0)
            answered = missing = 0
            for _ in range(REQUESTS):
                response, _ = elm.command("010C", wait=5.0)
                if "41 0C" in response:
                    answered += 1
                elif "NO DATA" in response.upper():
                    missing += 1
            passed = answered == REQUESTS
            line = ("%6X %7d ms %8d/%d %9d  %s"
                    % (step, step * 4, answered, REQUESTS, missing,
                       "pass" if passed else "FAIL"))
            print(line)
            log.write(line + "\n")
            if not passed:
                break
            best = step * 4
        elm.command("ATST 32", wait=5.0)   # back to the adapter's default

    verdict = ("measured upper bound: under %d ms" % best) if best else "nothing passed"
    print()
    print(verdict)
    log.write("\n" + verdict + "\n")
    log.close()


if __name__ == "__main__":
    main()
