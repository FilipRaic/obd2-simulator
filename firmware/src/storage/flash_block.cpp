// flash_block.cpp
#include "flash_block.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <cstring>

namespace flash_block {

static constexpr uint32_t NO_SECTOR = 0xFFFFFFFFu;

static SemaphoreHandle_t s_mutex      = nullptr;
static uint8_t           s_buf[W25Q128::SECTOR_SIZE];
static uint32_t          s_base       = NO_SECTOR;   // byte address of the cached sector
static bool              s_dirty      = false;
static uint32_t          s_last_write = 0;

struct Lock {
    Lock()  { if (s_mutex) xSemaphoreTakeRecursive(s_mutex, portMAX_DELAY); }
    ~Lock() { if (s_mutex) xSemaphoreGiveRecursive(s_mutex); }
};

void begin() {
    if (!s_mutex) s_mutex = xSemaphoreCreateRecursiveMutex();
}

static inline uint32_t sector_base(uint32_t addr) {
    return addr - (addr % W25Q128::SECTOR_SIZE);
}

// Erase, program, then READ BACK and compare (21.08.2026.).
//
// The board kept finding erased blocks where a volume had been written, which
// is the state NOR is left in when an erase completes and the program that
// should follow does not. The verify turns that from an invisible loss into
// something the next attempt can repair, and the counter says how often it
// happens - a number worth having before blaming the driver, the timing or
// the power.
static uint32_t s_verify_failures = 0;

uint32_t verify_failures() { return s_verify_failures; }

static void flush_locked() {
    if (!s_dirty) return;
    static uint8_t check[W25Q128::SECTOR_SIZE];
    for (int attempt = 0; attempt < 3; ++attempt) {
        flash_chip().erase_sector(s_base);
        flash_chip().program(s_base, s_buf, W25Q128::SECTOR_SIZE);
        flash_chip().read(s_base, check, W25Q128::SECTOR_SIZE);
        if (memcmp(check, s_buf, W25Q128::SECTOR_SIZE) == 0) {
            s_dirty = false;
            return;
        }
        ++s_verify_failures;
    }
    // Three failed attempts on one sector. The cache is dropped anyway, since
    // holding it would only repeat the same failure at every later flush.
    s_dirty = false;
}

// Make base the cached sector, writing back whatever was cached before.
static void load_locked(uint32_t base) {
    if (s_base == base) return;
    flush_locked();
    flash_chip().read(base, s_buf, W25Q128::SECTOR_SIZE);
    s_base = base;
}

void read(uint32_t addr, uint8_t* dst, size_t n) {
    Lock lock;
    size_t done = 0;
    while (done < n) {
        uint32_t a    = addr + static_cast<uint32_t>(done);
        uint32_t base = sector_base(a);
        uint32_t off  = a - base;
        size_t   chunk = W25Q128::SECTOR_SIZE - off;
        if (chunk > n - done) chunk = n - done;

        // Only unwritten data may come straight from the chip. A read is
        // never allowed to evict the cached sector - a large sequential read
        // would otherwise flush and reload on every step.
        if (s_dirty && base == s_base) memcpy(dst + done, s_buf + off, chunk);
        else                           flash_chip().read(a, dst + done, chunk);
        done += chunk;
    }
}

void write(uint32_t addr, const uint8_t* src, size_t n) {
    Lock lock;
    size_t done = 0;
    while (done < n) {
        uint32_t a    = addr + static_cast<uint32_t>(done);
        uint32_t base = sector_base(a);
        uint32_t off  = a - base;
        size_t   chunk = W25Q128::SECTOR_SIZE - off;
        if (chunk > n - done) chunk = n - done;

        load_locked(base);
        memcpy(s_buf + off, src + done, chunk);
        s_dirty = true;
        done += chunk;
    }
    s_last_write = ::millis();
}

void sync() {
    Lock lock;
    flush_locked();
}

bool dirty() {
    Lock lock;
    return s_dirty;
}

uint32_t last_write_ms() {
    Lock lock;
    return s_last_write;
}

} // namespace flash_block
