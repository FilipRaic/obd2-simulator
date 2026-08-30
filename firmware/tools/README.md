# Bring-up tools

Helpers used while putting the assembled v0.7 board into service. Nothing here
is part of the shipped firmware.

The ordinary way to flash the board is the one on the **Firmware** page of the
repository wiki, over USB-C with PlatformIO. Everything in this directory exists for when that path is
unavailable or when it does not say enough.

| Item | What it is | When it is used |
|---|---|---|
| `elm327/` | Fifteen scripts that drive a commercial ELM327 adapter against the simulator and print what comes back, from a one-line link check to the response-time and throughput measurements. How the test cases were executed on the assembled board. Has its own [`README.md`](elm327/README.md) | after the board answers at all, to prove that it answers *correctly* |
| `flash_jtag.py` | Flashes over USB-C without letting esptool reconfigure the port. On USB-Serial-JTAG the DTR and RTS lines drive the internal reset and IO0, and esptool's own open sequence knocks the chip back out of download mode | whenever the USB-C path is the one in use. See the last section of this file |
| `capture_boot.py` | Waits for the board's USB CDC port to appear and logs everything it says, reopening the port as often as needed | run it **first**, then power-cycle. A chip rebooting in a loop is captured too, which a plain monitor misses |

The rule for all three: **one entry into download mode, one port session.**
Closing the port makes Windows drop DTR and RTS, which on USB-Serial-JTAG costs
another entry by hand, so a stray `device list` is not free.

## Why go through J6 at all

The board can be flashed over USB-C through the ESP32-S3's own USB-Serial-JTAG,
and that is the documented path in `platformio.ini`. During bring-up two things
made it a poor place to stand:

1. **The panic text never arrives.** The Arduino ESP32 SDK sets
   `CONFIG_ESP_CONSOLE_UART_DEFAULT=y` with USB-Serial-JTAG only as the
   *secondary* console. The panic handler writes to the **primary** one, so the
   Guru Meditation line and the backtrace go out on UART0, header J6. Over
   USB-C only whatever fits the 64-byte FIFO between host polls survives, which
   is how a boot log ends in a meaningless fragment like `fcebc50`.
   (`src/hal/crash_report.cpp` is the other half of the answer: it reads the
   core dump back out of flash on the next boot, and needs no adapter.)
2. **The USB-C data path is currently a bodge.** Until U9 is fitted, D+ and D-
   run over flying wires and the link corrupts the occasional byte, which turns
   every flash attempt into a coin flip.

J6 sidesteps both. It carries `TXD0`, `RXD0` and `GND` and nothing else.

## Pinout of J6

| Pin | Net | GPIO | Direction |
|---|---|---|---|
| 1 (square pad) | `TXD0` | 43 | board → PC |
| 2 | `RXD0` | 44 | PC → board |
| 3 | `GND` | - | - |

Any USB-serial converter will do: a CP2102, a CH340, an FT232 module, or a
spare microcontroller board running a pass-through sketch. Wire it straight
across, converter RX to J6 pin 1, converter TX to J6 pin 2, grounds together.

**Check the converter's logic level first.** The ESP32-S3 is a 3,3 V part and
pin 2 is an input into it, so a 5 V converter needs a divider on that line, or
a converter with a 3,3 V / 5 V switch set to 3,3 V. Pin 1 is an output from the
board and is safe either way, since a 5 V receiver reads 3,3 V as a high. Many
cheap modules are labelled 3,3 V but drive 5 V on TX, so measure it rather than
trusting the silkscreen.

## Entering download mode

J6 has no DTR and no RTS, so nothing can put the chip into download mode for
you. By hand, in order of reliability:

1. **Power-up entry (best).** Unplug USB-C, wait 5 s, hold **BOOT (SW4)**, plug
   USB-C back in, count to two, release BOOT. The IO0 level is sampled at
   startup, so this cannot miss the moment.
2. **Button entry.** Hold **BOOT (SW4)**, tap **RESET (SW5)**, release BOOT.

The board stays in download mode until it is reset, so there is no rush.

## Flashing over J6

From `firmware/`, with `COMx` being the **converter's** port, not the board's:

```
python -m platformio run -e custom-board-bringup -t upload --upload-port COMx
```

`--before default_reset` and `--after hard_reset` are harmless here: they toggle
DTR and RTS, which a plain three-wire connection does not carry. Reset the
board by hand
afterwards, or just power-cycle it.

If PlatformIO's own reset handling gets in the way, esptool does the same job
directly:

```
python -m esptool --chip esp32s3 --port COMx --baud 115200 \
    --before no_reset --after no_reset write_flash -z \
    0x0     .pio/build/custom-board-bringup/bootloader.bin \
    0x8000  .pio/build/custom-board-bringup/partitions.bin \
    0x10000 .pio/build/custom-board-bringup/firmware.bin
```

Then the console, on the same port:

```
python -m platformio device monitor -p COMx -b 115200
```

## Flashing over USB-C instead

If the USB-C path is the one in use, the wrapper that works around esptool's
handling of USB-Serial-JTAG on Windows is `flash_jtag.py`, described in the
commissioning note. Its rule is absolute: **one entry into download mode, one
port session.** Closing the port makes Windows drop DTR and RTS, and on
USB-Serial-JTAG those drive the internal reset and IO0, so every stray
`device list` or connection check costs another entry by hand.
