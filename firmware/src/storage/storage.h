// storage.h
// Scenario persistence (v0.5): JSON files in /flash/scenarios
// on the W25Q128 FAT filesystem, a last-used marker so the device boots
// into the previous scenario, and the compiled-in factory scenario (with an
// optional /flash/factory.json override). A PC edits the same files through
// the USB-C MSC device mode, and a USB-A stick imports/exports copies of them.
#pragma once
#include "scenario.h"
#include <cstdint>

namespace storage {

constexpr uint8_t MAX_SCENARIOS = 16;

// Mount the flash filesystem. Safe to call when the chip is absent (breadboard setup
// development board), and persistence is then disabled.
void init();

bool available();

// /flash/scenarios/<name>.json, and save() also updates the last-used marker.
bool save(const Scenario& sc, const char* name);
bool load(const char* name, Scenario& out);

// Scenario used on boot: last-used if the marker and file exist,
// otherwise the factory scenario.
void load_startup(Scenario& out);

// Factory scenario: /flash/factory.json when present, else built-in.
void factory(Scenario& out);

// List stored scenario names (without extension), returns the count.
uint8_t list(char names[][app::SCENARIO_NAME_MAX], uint8_t max_names);

// Guard for code that touches /flash directly instead of going through the
// functions above.
//
// EVERY FatFs operation on that volume has to hold this, because the CAN task
// applies scenarios while the UI task lists them and copies files to and from
// a USB stick. The functions above take it themselves. usb_stick.cpp does not
// use them - it copies whole files with fopen/fwrite - and until 09.08.2026. it
// took no lock at all, so a stick import could run against a concurrent
// save() on the same volume.
//
// The mutex is recursive, so nesting a guard inside a storage:: call is safe.
struct FsGuard {
    FsGuard();
    ~FsGuard();
    FsGuard(const FsGuard&)            = delete;
    FsGuard& operator=(const FsGuard&) = delete;
};

} // namespace storage
