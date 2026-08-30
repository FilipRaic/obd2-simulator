// spi_bus.h
// Shared-SPI arbitration: three peripherals (MCP2515, ILI9341 via
// TFT_eSPI, W25Q128) share one SPI bus used from two FreeRTOS tasks, so every
// transaction must run under this recursive mutex. The MicroSD card was removed
// in v0.5 - the W25Q128 carries the FAT filesystem now.
#pragma once
#include <SPI.h>

namespace hal {

// Initialise the shared bus on the board's pins and create the mutex.
void spi_bus_init();

// Explicit lock/unlock for code that brackets whole operations (UI drawing,
// SD file access).
void spi_lock();
void spi_unlock();

// RAII guard for driver-level transactions.
class SpiLock {
public:
    SpiLock()  { spi_lock(); }
    ~SpiLock() { spi_unlock(); }
    SpiLock(const SpiLock&) = delete;
    SpiLock& operator=(const SpiLock&) = delete;
};

} // namespace hal
