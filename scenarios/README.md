# Example simulation scenarios

JSON scenarios in the format the firmware loads from `/flash/scenarios` on
the on-board 16 MB SPI NOR FAT filesystem (v0.5).
Copy them onto the device over the USB-C PC link (the device shows up as a
USB disk) or import them from a USB stick via Settings. Edit values freely,
they are clamped to each sensor's valid range on load.

- `sensors` keys are the named identifiers from
  `firmware/include/sensor_meta.h` (e.g. `coolant_temp_c`, `rpm`,
  `vehicle_speed_kmh`), and values are physical units.
- `dtcs[].state` is `"pending"` or `"confirmed"`. Any confirmed DTC turns the
  MIL on, so `mil_on` is informative only.
- `vin` is both shown in the UI and reported over the bus: loading a scenario
  passes it to `obd_set_vin()`, so mode 0x09 answers with it. Omit the key, or
  set it to an empty string, and the default `WVWZZZ1KZAW000001` applies.

Wiki page: **Usage**, on the repository wiki.
