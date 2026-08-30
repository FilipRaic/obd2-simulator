// fat16_format.cpp
#include "fat16_format.h"
#include "flash_block.h"
#include <Arduino.h>
#include <esp_system.h>
#include <cstring>

namespace fat16 {

// ── The layout, as Microsoft's FAT specification computes it ───────────────
// DskSize        = 32768 sectors (16 MB of 512-byte sectors)
// RootDirSectors = (512 entries * 32 B) / 512 B            = 32
// TmpVal1        = DskSize - (RsvdSecCnt + RootDirSectors) = 32735
// TmpVal2        = (256 * SecPerClus) + NumFATs            = 1026
// FATSz          = (TmpVal1 + TmpVal2 - 1) / TmpVal2       = 32
// Data start     = 1 + 2*32 + 32                           = 97 sectors
// Clusters       = (32768 - 97) / 4                        = 8167
// 4085 <= 8167 < 65525, so this is FAT16 and nothing else. The two FATs need
// (8167 + 2) * 2 = 16338 bytes and have 2 * 32 * 512 = 32768, so they fit.
static constexpr uint32_t SECTOR_SIZE   = 512;
static constexpr uint32_t TOTAL_SECTORS = 32768;
static constexpr uint32_t SEC_PER_CLUS  = 4;      // 2 KB clusters
static constexpr uint32_t RSVD_SECTORS  = 1;
static constexpr uint32_t NUM_FATS      = 2;
static constexpr uint32_t ROOT_ENTRIES  = 512;
static constexpr uint32_t ROOT_SECTORS  = ROOT_ENTRIES * 32 / SECTOR_SIZE;   // 32
static constexpr uint32_t FAT_SECTORS   = 32;
static constexpr uint32_t DATA_START    = RSVD_SECTORS + NUM_FATS * FAT_SECTORS
                                          + ROOT_SECTORS;                    // 97

static void put16(uint8_t* p, uint16_t v) {
    p[0] = static_cast<uint8_t>(v & 0xFF);
    p[1] = static_cast<uint8_t>(v >> 8);
}

static void put32(uint8_t* p, uint32_t v) {
    p[0] = static_cast<uint8_t>(v & 0xFF);
    p[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
    p[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
    p[3] = static_cast<uint8_t>(v >> 24);
}

bool needs_format(const uint8_t* bs) {
    bool blank = true;
    for (uint32_t i = 0; i < SECTOR_SIZE; ++i) {
        if (bs[i] != 0xFF) { blank = false; break; }
    }
    if (blank) return true;                                  // virgin NOR

    const bool signature = bs[510] == 0x55 && bs[511] == 0xAA;
    if (!signature) return true;                             // garbage

    // A single FAT copy is this firmware's own old f_mkfs layout, the one a
    // PC would not touch. Anything with two is left alone, because that is
    // what a PC writes and it is not ours to throw away.
    return bs[0x10] == 1;
}

bool write_volume() {
    static uint8_t sec[SECTOR_SIZE];

    // ── Boot sector ────────────────────────────────────────────────────────
    memset(sec, 0, sizeof(sec));
    sec[0] = 0xEB; sec[1] = 0x3C; sec[2] = 0x90;      // jump, as DOS writes it
    memcpy(sec + 0x03, "MSDOS5.0", 8);                // BS_OEMName
    put16(sec + 0x0B, SECTOR_SIZE);                   // BPB_BytsPerSec
    sec[0x0D] = SEC_PER_CLUS;                         // BPB_SecPerClus
    put16(sec + 0x0E, RSVD_SECTORS);                  // BPB_RsvdSecCnt
    sec[0x10] = NUM_FATS;                             // BPB_NumFATs  <- the point
    put16(sec + 0x11, ROOT_ENTRIES);                  // BPB_RootEntCnt
    put16(sec + 0x13, TOTAL_SECTORS);                 // BPB_TotSec16
    sec[0x15] = 0xF8;                                 // BPB_Media (fixed disk)
    put16(sec + 0x16, FAT_SECTORS);                   // BPB_FATSz16
    put16(sec + 0x18, 63);                            // BPB_SecPerTrk
    put16(sec + 0x1A, 255);                           // BPB_NumHeads
    put32(sec + 0x1C, 0);                             // BPB_HiddSec (no partition)
    put32(sec + 0x20, 0);                             // BPB_TotSec32
    sec[0x24] = 0x80;                                 // BS_DrvNum
    sec[0x25] = 0x00;                                 // BS_Reserved1
    sec[0x26] = 0x29;                                 // BS_BootSig
    put32(sec + 0x27, esp_random());                  // BS_VolID
    memcpy(sec + 0x2B, "OBD2SIM    ", 11);            // BS_VolLab
    memcpy(sec + 0x36, "FAT16   ", 8);                // BS_FilSysType
    sec[510] = 0x55; sec[511] = 0xAA;
    flash_block::write(0, sec, SECTOR_SIZE);

    // ── Both FATs ──────────────────────────────────────────────────────────
    // Entry 0 is the media descriptor padded with ones, entry 1 the end-of-
    // chain mark. Every other cluster is free.
    for (uint32_t f = 0; f < NUM_FATS; ++f) {
        const uint32_t base = RSVD_SECTORS + f * FAT_SECTORS;
        memset(sec, 0, sizeof(sec));
        sec[0] = 0xF8; sec[1] = 0xFF; sec[2] = 0xFF; sec[3] = 0xFF;
        flash_block::write(base * SECTOR_SIZE, sec, SECTOR_SIZE);
        memset(sec, 0, sizeof(sec));
        for (uint32_t s = 1; s < FAT_SECTORS; ++s)
            flash_block::write((base + s) * SECTOR_SIZE, sec, SECTOR_SIZE);
    }

    // ── Root directory ─────────────────────────────────────────────────────
    memset(sec, 0, sizeof(sec));
    const uint32_t root_base = RSVD_SECTORS + NUM_FATS * FAT_SECTORS;
    for (uint32_t s = 0; s < ROOT_SECTORS; ++s)
        flash_block::write((root_base + s) * SECTOR_SIZE, sec, SECTOR_SIZE);

    flash_block::sync();

    static_assert(DATA_START == 97, "layout drifted from the computed one");
    static_assert((TOTAL_SECTORS - DATA_START) / SEC_PER_CLUS > 4085,
                  "cluster count fell into FAT12 range");
    static_assert((TOTAL_SECTORS - DATA_START) / SEC_PER_CLUS < 65525,
                  "cluster count fell into FAT32 range");
    static_assert(((TOTAL_SECTORS - DATA_START) / SEC_PER_CLUS + 2) * 2
                  <= FAT_SECTORS * SECTOR_SIZE, "FAT too small for the clusters");
    return flash_block::BLOCK_COUNT == TOTAL_SECTORS;
}

} // namespace fat16
