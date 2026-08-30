## What changed


## Why


## Checklist

- [ ] Walked the matching row in the coupled-files map (`docs/MAPA-POVEZANIH-DATOTEKA.md`), because the same fact is written down in up to six places
- [ ] Any number quoted in documentation was re-measured from the board or the binary, not copied from an earlier version of the text
- [ ] `tests/test_simulator.cpp` updated if the codec, dispatcher, ISO-TP, DTC bank or simulation changed
- [ ] `firmware/include/sensor_meta.h` still index-aligned with `include/sensor_table.h`, if the sensor table changed
- [ ] Wiki updated in **both** languages if the change is user-facing
- [ ] `pio run -e custom-board` still builds, if the firmware changed
