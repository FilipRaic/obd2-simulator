"""Test case T-10: unplug the tool, plug it back in, repeat.

The script watches for the link to fall and come back on its own, so there is
nothing to confirm between cycles. After every reconnect it checks three
things: the supported-PID mask is unchanged, a live reading answers, and the
DTC bank still holds the factory state, which is what the test case means by
"no residual state".

The adapter is powered from pin 16, so unplugging it cuts its power and forces
a full re-initialisation every time. That is the point of the test.

Mind the connector. On this board J1962 is soldered straight to the PCB with no
enclosure to take the force, so repeated unplugging works the solder joints. If
many cycles are needed, leave an extension cable in the board and unplug the
tool at the far end of it.

Arguments: port, then number of cycles (default 10).
"""

import sys
import time

import elm327

FACTORY_STATUS = "41 01 83"   # MIL on, three confirmed DTCs
DEADLINE_S = 20 * 60
LOG = "reconnect_test.txt"


def try_connect(port):
    """Open, initialise and interrogate. Returns (elm, answers) or (None, reason)."""
    try:
        elm = elm327.Elm327(port, timeout=0.3)
    except Exception as error:
        return None, "port will not open: %s" % type(error).__name__
    try:
        for command in elm327.INIT:
            elm.command(command, wait=6.0)
        answers = {}
        for command in ("0100", "010C", "0101"):
            answers[command], _ = elm.command(command, wait=6.0)
        if "41 00" not in answers["0100"]:
            elm.close()
            return None, "link up but the ECU is quiet: %r" % answers["0100"]
        return elm, answers
    except Exception as error:
        try:
            elm.close()
        except Exception:
            pass
        return None, "init failed: %s" % type(error).__name__


def alive(elm):
    try:
        response, _ = elm.command("010C", wait=2.0)
        return "41 0C" in response
    except Exception:
        return False


def main():
    port = elm327.port_from_argv(sys.argv)
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    log = open(LOG, "w", encoding="utf-8")

    def record(text):
        print(text)
        log.write(text + "\n")
        log.flush()

    record("T-10 started %s, target %d cycles" % (time.strftime("%H:%M:%S"), target))
    record("Unplug the tool, wait for its LED to go out, plug it back in. Repeat.")
    record("-" * 66)

    elm, answers = try_connect(port)
    if elm is None:
        record("initial connection failed: %s" % answers)
        return
    record("baseline: 0100 -> %s" % answers["0100"])
    record("          0101 -> %s" % answers["0101"])
    record("")

    cycle = 0
    start = time.perf_counter()
    while cycle < target and time.perf_counter() - start < DEADLINE_S:
        while alive(elm) and time.perf_counter() - start < DEADLINE_S:
            time.sleep(0.4)
        if time.perf_counter() - start >= DEADLINE_S:
            break
        fell = time.perf_counter()
        try:
            elm.close()
        except Exception:
            pass
        record("[%s] link down, waiting for the tool" % time.strftime("%H:%M:%S"))

        elm = None
        while elm is None and time.perf_counter() - start < DEADLINE_S:
            time.sleep(1.5)
            elm, answers = try_connect(port)
        if elm is None:
            break

        cycle += 1
        record("[%s] cycle %d/%d, link up after %.1f s"
               % (time.strftime("%H:%M:%S"), cycle, target, time.perf_counter() - fell))
        record("    0100 -> %-34s %s"
               % (answers["0100"],
                  "mask unchanged" if "41 00 9E 7F 90 13" in answers["0100"]
                  else "MASK DIFFERS"))
        record("    010C -> %-34s %s"
               % (answers["010C"],
                  "answers" if "41 0C" in answers["010C"] else "NO ANSWER"))
        record("    0101 -> %-34s %s"
               % (answers["0101"],
                  "factory state" if FACTORY_STATUS in answers["0101"]
                  else "STATE DIFFERS"))
        record("")

    try:
        elm.close()
    except Exception:
        pass
    record("-" * 66)
    record("finished %s, %d of %d cycles" % (time.strftime("%H:%M:%S"), cycle, target))
    log.close()


if __name__ == "__main__":
    main()
