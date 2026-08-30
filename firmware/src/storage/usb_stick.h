// usb_stick.h
// USB-A stick support (v0.5, ESP32-S3 only): on-demand import/export of
// scenario JSON files between the stick's root directory and
// /flash/scenarios. The host stack runs only for the duration of the
// operation: mux -> USB-A, stick powered through the load switch, device
// enumerated, a minimal MSC Bulk-Only-Transport/SCSI driver feeds a second
// FatFs volume ("1:", mounted at /usb), files are copied, everything is
// torn down and the stick powered off again.
//
// NOTE: compile-verified only - not yet exercised on hardware-first (see the
// v0.5 design spec).
#pragma once
#include <cstdint>

namespace usb_stick {

enum class Result : uint8_t {
    Ok,
    NotSupported,   // development board (no USB peripheral)
    NoStick,        // nothing enumerated within the timeout
    MountFailed,    // no FAT filesystem / unsupported block size
    CopyFailed,     // I/O error mid-copy
};

// Copy *.json from the stick's root directory into /flash/scenarios.
Result import_scenarios(uint8_t& copied);

// Copy /flash/scenarios/*.json to the stick's root directory.
Result export_scenarios(uint8_t& copied);

const char* result_text(Result r);

} // namespace usb_stick
