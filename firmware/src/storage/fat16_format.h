// fat16_format.h
// Lays down a FAT16 volume on the W25Q128 that a PC accepts.
//
// Why this is not f_mkfs (21.08.2026.): FatFs R0.13c, the revision bundled
// with this arduino-esp32, writes exactly ONE copy of the FAT and gives no
// way to ask for two - the n_fat parameter appears only in R0.14. Microsoft's
// FAT specification says the field should always be 2, and warns that many
// programs and drivers do not work when it is not, and Windows refused every
// volume f_mkfs produced here while accepting its own. Everything else about
// those volumes was sound: 512-byte sectors, 8151 clusters, a valid boot
// signature, and FatFs itself mounted them without complaint.
//
// The layout is fixed and computed the way the specification prescribes, for
// one medium only: 32768 sectors of 512 bytes, 2 KB clusters, 512 root
// entries, two FATs.
#pragma once
#include <cstdint>

namespace fat16 {

// Should this medium be (re)formatted? True only for a medium that is blank,
// that carries no boot signature at all, or that this firmware itself wrote
// with the old single-FAT layout. A volume with two FATs is left alone - that
// is what a PC writes, and destroying it is the bug this replaced.
bool needs_format(const uint8_t* boot_sector);

// Write boot sector, both FATs and the root directory. Returns false when the
// medium is not the size this layout was computed for.
bool write_volume();

} // namespace fat16
