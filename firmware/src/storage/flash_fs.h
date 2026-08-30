// flash_fs.h
// FAT filesystem on the W25Q128 (v0.5 primary storage): FatFs volume "0:"
// with a custom diskio over the raw driver, registered in the VFS at
// /flash. No wear levelling - scenario writes are rare (documented
// trade-off in the design spec). Formatted automatically on first use.
#pragma once

namespace flash_fs {

constexpr const char* BASE_PATH = "/flash";

// Probe the chip, register diskio + VFS, mount (formatting if needed).
// False when the chip is absent (breadboard setup) or the mount/format fails.
bool mount();

// Unmount and unregister (used before exposing the raw medium over MSC).
void unmount();

bool mounted();

// What the last mount() actually did. Plain ints so this header does not have
// to drag ff.h along - the values are FRESULT codes (0 = FR_OK,
// 13 = FR_NO_FILESYSTEM). Added 21.08.2026. as the instrument for the "a PC
// asks to format a disk the board formatted itself" hunt: in USB disk mode
// there is no serial console, so the screen has to say whether the volume on
// the chip was accepted or thrown away.
struct Report {
    int  mount_res    = 0;   // f_mount() on whatever was already there
    bool formatted    = false;
    int  format_res   = 0;
    int  remount_res  = 0;
};

const Report& last_report();

// One line describing what mount() found and decided, kept so a bring-up build
// can repeat it from loop(). The boot log over USB-C loses its first seconds
// every time RESET takes the USB device down with it, and this line is written
// exactly once, at boot. Added 22.08.2026.
const char* mount_summary();

} // namespace flash_fs
