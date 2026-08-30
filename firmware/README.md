# OBD-II Simulator - firmware

PlatformIO project for the simulator device. The portable
protocol core lives one directory up (`../include`, `../src`) and is compiled
into every environment by `import_core.py`. This project adds the hardware
layers on top of the core's four `extern` platform hooks.

Wiki page for this part of the project, **Firmware**, on the repository wiki. It covers
the same ground for someone who is not reading the source: installing
PlatformIO, the module layout, the request path and how to run the tests.

## Invoking PlatformIO

If PlatformIO was installed with pip rather than as a standalone binary, call it
as a module:

```sh
python -m platformio run -e custom-board
```

Two failure modes worth knowing, because neither says what is wrong:

- **On Windows, `python` may resolve to the Microsoft Store alias**, which
  prints "Python was not found" and does nothing else. Point at the real
  interpreter if that happens.
- **The `native` environment needs a host C++ compiler on `PATH`.** Without one
  the build fails with exit code 1 and no error output at all, so check that
  before looking anywhere else.

## Environments

| env | Target | Notes |
|-----|--------|-------|
| `custom-board` | ESP32-S3-WROOM-1, both on the breadboard adapter and on the dedicated PCB | pins in `include/pins_custom_s3.h`. Flashes over USB-C through the chip's own USB-Serial-JTAG |
| `custom-board-bringup` | the same board, flashed over the UART header J6 | identical firmware, different upload path. Used when the USB-C path is unavailable or when the panic text has to be read, see [`tools/README.md`](tools/README.md) |
| `native` | Development host | runs `../tests/test_simulator.cpp`, no hardware |

```sh
pio run  -e custom-board -t upload  # build + flash the board
pio device monitor              # serial log, 115200 baud
pio test -e native              # host-side protocol tests (98 cases)
```

## Layout

| Path | Module |
|------|---------------------|
| `src/hal/` | shared-SPI mutex (five peripherals, two tasks), `millis` shim |
| `src/can/` | MCP2515 driver (500 kbit/s @ 8 MHz, filters 0x7DF/0x7E0), CAN task, ISO-TP flow-control hook |
| `src/app/` | command/snapshot contracts between the two FreeRTOS tasks |
| `src/ui/` | input (EN11 incremental encoder with push, joystick, CONFIRM/CLEAR/RETURN), screen stack, four screens |
| `src/storage/` | FAT filesystem on S25FL128L (FatFs custom diskio), USB-C MSC device mode, USB-A stick import/export (v0.5) |
| `include/` | board pin maps, sensor metadata, DTC string codec |

## Architecture

![Schematic 3: ESP32-S3-WROOM-1, external flash and USB subsystem](../hardware/schema3.svg)

The hardware this code drives: one SPI bus with three chip selects (MCP2515,
display, flash U7), the interrupt line from the CAN controller, and the single
USB OTG controller that the TS3USB221 mux switches between the USB-C and the
USB-A port. The pin numbers in the figure are the ones in
`include/pins_custom_s3.h`, and the rest of the board is drawn in
[`../hardware/README.md`](../hardware/README.md).

Two FreeRTOS tasks: the high-priority **CAN task** (core 1) owns
all simulator state, answers OBD requests through the protocol core and
republishes a state snapshot at 10 Hz. The low-priority **UI task** (core 0)
renders the ILI9341 and turns the physical controls into `InputEvent`s.
The UI mutates state only through the `app::Command` queue - no unsynchronized
shared state. Every SPI access (CAN, TFT, SD, external flash) runs under the
recursive HAL mutex.

## Scenarios and USB (v0.5)

Stored as JSON in `/flash/scenarios/*.json` on the S25FL128L FAT filesystem
and the last-used scenario is reloaded on boot. The factory
scenario is compiled in (matching `DtcBank::load_defaults()`), with an
optional `/flash/factory.json` override. The scenario `vin` is shown in the UI **and**
answered over the bus: loading a scenario passes it to the core's
`obd_set_vin()`. A missing or empty key restores the default `OBD_VIN`.

The dedicated board has one USB OTG controller switched by a TS3USB221 mux:

- **PC link (MSC)** - Settings action reboots into a boot mode where the
  whole flash filesystem is exposed over USB-C as a USB disk
  (`usb_msc_device.cpp`). RETURN reboots back.
- **USB-A stick** - Settings actions import/export scenario JSON files
  to/from a stick via a minimal MSC BOT/SCSI host driver
  (`usb_stick.cpp`). *Compile-verified only - not yet exercised on
  hardware.*

The breadboard development setup has no USB subsystem and no S25FL128L, so it
runs with the compiled-in factory scenario and inert USB rows.
