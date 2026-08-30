// flash_block.h
// 512-byte logical block layer over the W25Q128's 4 KB NOR erase sectors,
// with a single write-back sector cache.
//
// It exists because the FAT volume and the USB MSC device have to agree on
// one sector size (21.08.2026.). FatFs used to be formatted with 4 KB
// sectors while MSC exposed the same chip in 512-byte blocks, so the boot
// sector announced 4096 bytes per sector to a host that addressed the medium
// in 512, and Windows refused the volume with "you need to format the disk".
// Both paths now go through here, so BPB_BytsPerSec == the MSC block size ==
// BLOCK_SIZE.
//
// The cache is the second half of the fix. Without it every 512-byte block
// write cost a full erase (45 to 400 ms) plus a 4 KB reprogram, and a host
// writing eight consecutive blocks erased the same sector eight times. That
// is what made a PC-side format give up half way through. Consecutive writes
// inside one sector now touch RAM only, and the erase happens once, when the
// write moves on to another sector or sync() is called.
//
// Contents are volatile until sync(): FatFs calls it through CTRL_SYNC on
// every f_close / f_sync, and the MSC mode flushes on eject and when the host
// falls idle.
#pragma once
#include "w25q128.h"
#include <cstddef>
#include <cstdint>

namespace flash_block {

constexpr uint32_t BLOCK_SIZE        = 512;
constexpr uint32_t BLOCK_COUNT       = W25Q128::CAPACITY / BLOCK_SIZE;
constexpr uint32_t BLOCKS_PER_SECTOR = W25Q128::SECTOR_SIZE / BLOCK_SIZE;

// Create the cache mutex. Idempotent, call before any other function
// (flash_fs::mount() and usb_msc::run() both do).
void begin();

void read(uint32_t addr, uint8_t* dst, size_t n);
void write(uint32_t addr, const uint8_t* src, size_t n);

// Write the cached sector back to the chip. No-op when nothing is dirty.
void sync();

// How many times a sector failed to read back as written. Nonzero means the
// medium is not keeping what it is given.
uint32_t verify_failures();

bool     dirty();
uint32_t last_write_ms();   // millis() of the last write() that dirtied the cache

} // namespace flash_block
