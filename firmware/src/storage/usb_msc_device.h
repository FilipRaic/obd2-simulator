// usb_msc_device.h
// PC-link boot mode (v0.5, ESP32-S3 only): the device reboots into a
// dedicated mode where the TS3USB221 mux routes the OTG pins to the USB-C
// connector and TinyUSB exposes the whole W25Q128 as an MSC disk, so the
// scenario files are edited directly from a computer. The local filesystem
// is never mounted in this mode, which avoids concurrent FAT access.
// RETURN reboots back into the simulator.
//
// Role switching between the TinyUSB device stack and the usb_host stack at
// runtime is fragile - hence boot modes selected through an NVS flag.
#pragma once

namespace usb_msc {

// True when the NVS flag requests MSC mode for this boot.
bool boot_requested();

// Set the flag and restart into MSC mode (called from the Settings screen).
void request_and_reboot();

// Run MSC mode. Returns only by rebooting (RETURN button).
[[noreturn]] void run();

// Normal-mode USB pin defaults: mux -> USB-A, stick power off.
void pins_init_normal_mode();

} // namespace usb_msc
