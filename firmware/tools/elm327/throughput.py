"""Requests per second through the adapter.

The number carries a caveat: it is bounded by the adapter,
not by the simulator. Over Bluetooth every request costs about 200 ms of link
latency, and the spread over hundreds of requests is a few milliseconds, so the
simulator's own contribution is invisible here. Use response_time.py for that.
"""

import statistics
import sys
import time

import elm327

REQUESTS = 200


def main():
    port = elm327.port_from_argv(sys.argv)
    with elm327.connect(port) as elm:
        elm.command("010C", wait=5.0)   # warm-up, the first request is slower
        times = []
        failed = 0
        start = time.perf_counter()
        for _ in range(REQUESTS):
            begin = time.perf_counter()
            response, _ = elm.command("010C", wait=5.0)
            times.append((time.perf_counter() - begin) * 1000)
            if "41 0C" not in response:
                failed += 1
        total = time.perf_counter() - start

    times.sort()
    print("requests          %d" % REQUESTS)
    print("failed            %d" % failed)
    print("elapsed           %.1f s" % total)
    print("throughput        %.2f requests/s" % (REQUESTS / total))
    print("median            %.1f ms" % statistics.median(times))
    print("95th percentile   %.1f ms" % times[int(0.95 * REQUESTS)])
    print("min / max         %.1f / %.1f ms" % (min(times), max(times)))


if __name__ == "__main__":
    main()
