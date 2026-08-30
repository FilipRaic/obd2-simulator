# ELM327 test tools

Scripts that drive a commercial ELM327 diagnostic adapter against the simulator
and print what comes back. They are how the test cases were
actually executed on the assembled v0.7 board on 22.08.2026.

Nothing here is part of the firmware, and nothing here talks to the board
directly. The only link is the OBD-II connector: the PC drives the adapter, the
adapter drives the CAN bus, the simulator answers. That matters, because the
board's own USB path does not work on the first assembled unit, so no counter
inside the firmware can be read out and no instrumented build can be flashed.
Everything below therefore measures the device the way a workshop would.

## Requirements

- An ELM327 adapter, USB or Bluetooth. A Bluetooth one pairs as an **outgoing**
  COM port. Windows creates two ports per pairing, incoming and outgoing, and
  only the outgoing one reaches the adapter.
- `pyserial`. Nothing else.
- The adapter powers itself from pin 16 of the connector, so the board has to be
  running before the adapter can even be paired.

Every script takes the port as its first argument and falls back to `COM5`:

```
python check_link.py COM7
```

## Before measuring anything

1. Power the board from a USB-C charger whose label **explicitly lists 12 V**.
   A charger without that profile leaves the board on 9 V or 5 V, where it
   resets periodically.
2. Check that the home screen says `CAN OK`.
3. Plug the adapter in and let the link come up.
4. For anything that compares values against the screen, switch the device to
   the **Manual** profile. In Idle the simulation model rewrites 11 of the 21
   parameters every 100 ms.

## The scripts

| Script | What it does | Test case |
|---|---|---|
| `elm327.py` | Shared library: adapter client, ISO-TP payload assembly, PID and DTC decoding, the 21-parameter table | - |
| `check_link.py` | Adapter version, negotiated protocol, supported-PID mask against what the protocol core builds | T-01 |
| `service_tests.py` | Supported-PID masks, reference trace, pending DTCs, VIN, unsupported mode. Writes `service_tests.txt` | T-01, T-05, T-07, T-08 |
| `read_sensors.py` | All 21 parameters decoded, formatted for line-by-line comparison with the sensor screen | T-02 |
| `read_dtcs.py` | MIL state, confirmed list, pending list. Run it after each step while walking a code up and down on the device | T-04 |
| `clear_dtcs.py` | Mode 0x04, then proof the bank is empty and the MIL is off. Also shows silence versus negative response | T-06 |
| `freeze_frame.py` | Live values against the frozen snapshot | T-09 |
| `soak_test.py` | Eight parameters in a loop for half an hour, counting lost responses and dropped links. Writes `soak_test.txt` | T-03 |
| `reconnect_test.py` | Watches the link fall and return while the tool is unplugged and plugged back in. Writes `reconnect_test.txt` | T-10 |
| `response_time.py` | Upper bound on the response time by tightening the adapter's own timeout. Writes `response_time.txt` | NZ-5 |
| `throughput.py` | Requests per second, bounded by the adapter rather than the device | - |
| `bus_traffic.py` | Keeps the bus busy while something else is being measured | T-11 and any bench measurement |
| `profile_check.py` | Proves the Manual profile freezes the values | - |

## Order that works

```
python check_link.py            # link is up, mask matches the core
python service_tests.py         # T-01, T-05, T-07, T-08 and the reference trace
python read_sensors.py          # T-02, compare against the screen, Manual profile
python read_dtcs.py             # T-04, once per step while walking a code
python soak_test.py             # T-03, half an hour
python response_time.py         # NZ-5
python clear_dtcs.py            # T-06, this one clears the bank
python freeze_frame.py          # T-09, after re-confirming a DTC
python reconnect_test.py        # T-10
```

`clear_dtcs.py` changes the state of the device, and it has to run before
`freeze_frame.py`, because a freeze frame is captured only on the **first**
confirmation while no valid frame exists. Nothing is written to flash, so a
reset restores the factory scenario.

## Two things worth knowing before reading the numbers

**The adapter, not the device, sets the pace.** Over Bluetooth every request
costs about 200 ms of link latency, and the spread over hundreds of requests is
a few milliseconds. Whatever `throughput.py` prints is a property of the
adapter. The device's own response time is two orders of magnitude smaller and
is measured by `response_time.py`, which tightens the adapter's timeout until
answers start to go missing.

**The screen rounds, the bus does not.** The device shows the internal
floating-point value to a fixed number of decimals, while the bus carries the
value quantised by the conversion formula of the standard. A coolant reading of
110.9 on the screen arrives as 110 on the bus, because the formula's resolution
is 1 °C. `read_sensors.py` prints that resolution next to every row, and a
difference of up to one step is the expected result, not a fault.

## What was measured with these on 22.08.2026.

All eleven test cases of table 14 passed. T-10 was stopped after three cycles
rather than ten, deliberately: J1962 is soldered straight to the board with no
enclosure to take the extraction force.

Highlights, with the raw bytes kept in the project notes rather than here:

- 8840 consecutive requests over 30 minutes, **zero lost responses, zero link
  drops**.
- The device's frame counters agreed with the count kept on the PC **to the
  frame**, once flow-control frames and consecutive frames were accounted for.
- Response time **under 8 ms**, against the 50 ms the standard allows.
- Segmentation moves between services as payload length changes, which is
  visible live by walking one DTC between pending and confirmed.
