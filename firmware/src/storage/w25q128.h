// w25q128.h
// Raw driver for the external W25Q128 NOR flash - since v0.5 the primary
// storage medium: a FAT filesystem (flash_fs) lives on top of it and the
// USB MSC device mode exposes the same contents to a PC. All SPI access
// runs under the shared-bus mutex. The breadboard development setup has no
// chip, and begin() then fails and storage is disabled.
#pragma once
#include <cstddef>
#include <cstdint>

class W25Q128 {
public:
    static constexpr uint32_t CAPACITY    = 16u * 1024u * 1024u;  // 128 Mbit
    static constexpr uint32_t SECTOR_SIZE = 4096;                 // erase unit
    static constexpr uint32_t SECTOR_COUNT = CAPACITY / SECTOR_SIZE;

    // JEDEC-probe the chip, false when absent (wrong/missing ID).
    bool begin(int cs_pin);
    bool present() const { return present_; }

    // Random read of n bytes from byte address addr.
    void read(uint32_t addr, uint8_t* data, size_t n);

    // Program n bytes at addr (page-split internally). The area must have
    // been erased first, NOR bits only go 1 -> 0.
    void program(uint32_t addr, const uint8_t* data, size_t n);

    // Erase the 4 KB sector containing addr.
    void erase_sector(uint32_t addr);

private:
    void command(uint8_t cmd);
    void writeEnable();
    void waitReady();
    void programPage(uint32_t addr, const uint8_t* data, size_t n);

    int  cs_pin_  = -1;
    bool present_ = false;
};

// Single board-wide instance (defined in flash_fs.cpp).
W25Q128& flash_chip();
