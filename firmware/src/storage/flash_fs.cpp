// flash_fs.cpp
#include "flash_fs.h"
#include "flash_block.h"
#include "fat16_format.h"
#include "w25q128.h"
#include "board_config.h"
#include <Arduino.h>
#include <esp_vfs_fat.h>
#include <diskio_impl.h>
#include <ff.h>
#include <cstring>

static W25Q128 s_chip;
W25Q128& flash_chip() { return s_chip; }

namespace flash_fs {

static constexpr BYTE PDRV = 0;   // FatFs physical drive / volume "0:"
static FATFS* s_fs      = nullptr;
static bool   s_mounted = false;
static Report s_report;

const Report& last_report() { return s_report; }

static char s_summary[192] = "mount not run";
const char* mount_summary() { return s_summary; }

// ── FatFs diskio over the shared 512-byte block layer ─────────────────
// FatFs sector = 512 bytes, the same unit the USB MSC device mode exposes to
// a PC. It used to be the 4 KB NOR erase sector, which made f_mkfs write
// BPB_BytsPerSec = 4096 into a volume the host then addressed in 512-byte
// blocks, and Windows answered by asking to format the disk. flash_block
// turns the 512-byte writes back into whole-sector erase+program, and caches
// one sector so that eight consecutive blocks cost one erase instead of
// eight. See flash_block.h.

static DSTATUS ff_init(BYTE) {
    return s_chip.present() ? 0 : STA_NOINIT;
}

static DSTATUS ff_status(BYTE) {
    return s_chip.present() ? 0 : STA_NOINIT;
}

static DRESULT ff_read(BYTE, BYTE* buff, DWORD sector, UINT count) {
    flash_block::read(sector * flash_block::BLOCK_SIZE, buff,
                      static_cast<size_t>(count) * flash_block::BLOCK_SIZE);
    return RES_OK;
}

static DRESULT ff_write(BYTE, const BYTE* buff, DWORD sector, UINT count) {
    flash_block::write(sector * flash_block::BLOCK_SIZE, buff,
                       static_cast<size_t>(count) * flash_block::BLOCK_SIZE);
    return RES_OK;
}

static DRESULT ff_ioctl(BYTE, BYTE cmd, void* buff) {
    switch (cmd) {
    case CTRL_SYNC:
        // f_close() and f_sync() land here, so a closed file is on the chip.
        flash_block::sync();
        return RES_OK;
    case GET_SECTOR_COUNT:
        *reinterpret_cast<DWORD*>(buff) = flash_block::BLOCK_COUNT;
        return RES_OK;
    case GET_SECTOR_SIZE:
        *reinterpret_cast<WORD*>(buff) = flash_block::BLOCK_SIZE;
        return RES_OK;
    case GET_BLOCK_SIZE:
        // In sectors, so f_mkfs aligns the data area to the 4 KB erase unit.
        *reinterpret_cast<DWORD*>(buff) = flash_block::BLOCKS_PER_SECTOR;
        return RES_OK;
    default:
        return RES_PARERR;
    }
}

static const ff_diskio_impl_t kDiskio = {
    .init   = ff_init,
    .status = ff_status,
    .read   = ff_read,
    .write  = ff_write,
    .ioctl  = ff_ioctl,
};

bool mount() {
    if (s_mounted) return true;
    if (!s_chip.begin(PIN_CS_FLASH)) {
        Serial.println("[flash_fs] W25Q128 not detected");
        Serial.flush();
        snprintf(s_summary, sizeof(s_summary), "chip not detected");
        return false;
    }

    flash_block::begin();
    ff_diskio_register(PDRV, &kDiskio);
    if (esp_vfs_fat_register(BASE_PATH, "0:", 5, &s_fs) != ESP_OK) {
        Serial.println("[flash_fs] VFS registration failed");
        Serial.flush();
        return false;
    }

    // The decision is taken from the boot sector, BEFORE mounting, because
    // this firmware's own old volume mounts perfectly well and still has to
    // go: f_mkfs wrote a single FAT copy, and a PC refuses such a volume.
    // Mountability is therefore no test of whether the medium may stay.
    //
    // What must NOT be touched is a volume a PC wrote. Until 21.08.2026. any
    // volume that failed to mount was formatted over, which is what silently
    // ate the scenario copied onto the disk: the PC wrote its volume, the
    // board could not read it on the next boot, replaced it, and the next
    // connection was offered a disk the PC in turn refused. Proven on the
    // board - a volume Windows had formatted with 16 KB clusters came back
    // with 2 KB clusters and one FAT, which is ours. See fat16::needs_format().
    static uint8_t bs[flash_block::BLOCK_SIZE];
    flash_block::read(0, bs, sizeof(bs));
    s_report = Report{};
    const bool wants = fat16::needs_format(bs);
    if (wants) {
        Serial.println("[flash_fs] prazan nosac ili nas stari, oblikujem FAT16");
        Serial.flush();
        s_report.formatted  = true;
        s_report.format_res = fat16::write_volume() ? 0 : -1;
    }

    FRESULT res = f_mount(s_fs, "0:", 1);
    s_report.mount_res = static_cast<int>(res);
    // The whole decision on one line: what the boot sector says, what
    // needs_format() made of it, and what f_mount() then answered. bps is
    // BPB_BytsPerSec, fats is BPB_NumFATs - the byte needs_format() judges by -
    // and sig is the 55AA at the end of the sector.
    snprintf(s_summary, sizeof(s_summary),
             "bs %02x %02x %02x  bps %u  fats %u  spc %u  sig %02x%02x  "
             "wants_format %d  format_res %d  mount_res %d",
             bs[0], bs[1], bs[2],
             static_cast<unsigned>(bs[0x0B] | (bs[0x0C] << 8)),
             static_cast<unsigned>(bs[0x10]),
             static_cast<unsigned>(bs[0x0D]),
             bs[510], bs[511],
             wants ? 1 : 0, s_report.format_res, static_cast<int>(res));
    Serial.print("[flash_fs] f_mount -> ");
    Serial.println(res);
    Serial.flush();
    if (res != FR_OK && !s_report.formatted) {
        // Someone else's volume that this board cannot read. It stays where
        // it is, and the board runs without persistence, which is recoverable.
        // Formatting over it is not.
        Serial.println("[flash_fs] tudji nosac se ne da procitati, OSTAVLJAM GA");
        Serial.flush();
    }
    if (res != FR_OK) {
        Serial.printf("[flash_fs] mount failed (%d)\n", res);
        Serial.flush();
        esp_vfs_fat_unregister_path(BASE_PATH);
        s_fs = nullptr;
        return false;
    }

    s_mounted = true;
    Serial.println("[flash_fs] mounted at /flash (16 MB FAT)");
    Serial.flush();
    return true;
}

void unmount() {
    if (!s_mounted) return;
    f_mount(nullptr, "0:", 0);
    flash_block::sync();
    esp_vfs_fat_unregister_path(BASE_PATH);
    s_fs      = nullptr;
    s_mounted = false;
}

bool mounted() { return s_mounted; }

} // namespace flash_fs
