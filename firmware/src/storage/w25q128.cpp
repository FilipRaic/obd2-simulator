// w25q128.cpp
#include "w25q128.h"
#include "hal/spi_bus.h"
#include <Arduino.h>
#include <SPI.h>

static const SPISettings kSpiSettings(20000000, MSBFIRST, SPI_MODE0);

// Instructions
static constexpr uint8_t CMD_JEDEC_ID     = 0x9F;
static constexpr uint8_t CMD_READ_DATA    = 0x03;
static constexpr uint8_t CMD_PAGE_PROGRAM = 0x02;
static constexpr uint8_t CMD_WRITE_ENABLE = 0x06;
static constexpr uint8_t CMD_SECTOR_ERASE = 0x20;
static constexpr uint8_t CMD_READ_STATUS1 = 0x05;

bool W25Q128::begin(int cs_pin) {
    cs_pin_ = cs_pin;
    pinMode(cs_pin_, OUTPUT);
    digitalWrite(cs_pin_, HIGH);

    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_JEDEC_ID);
    uint8_t mf  = SPI.transfer(0x00);   // manufacturer
    uint8_t typ = SPI.transfer(0x00);   // memory type
    uint8_t cap = SPI.transfer(0x00);   // 0x18 = 128 Mbit
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
    // Both approved 128 Mbit parts share the command set this driver uses
    // (0x03/0x02/0x20/0x06/0x05, uniform 4 KB sectors, 256 B pages):
    //   Winbond  W25Q128JVSIQ      -> EF 40 18
    //   Infineon S25FL128LAGMFM010 -> 01 60 18
    const bool winbond  = (mf == 0xEF && typ == 0x40);
    const bool infineon = (mf == 0x01 && typ == 0x60);
    present_ = (winbond || infineon) && cap == 0x18;
    return present_;
}

void W25Q128::read(uint32_t addr, uint8_t* data, size_t n) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_READ_DATA);
    SPI.transfer((addr >> 16) & 0xFF);
    SPI.transfer((addr >>  8) & 0xFF);
    SPI.transfer( addr        & 0xFF);
    for (size_t i = 0; i < n; ++i) data[i] = SPI.transfer(0x00);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
}

void W25Q128::command(uint8_t cmd) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(cmd);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
}

void W25Q128::writeEnable() { command(CMD_WRITE_ENABLE); }

void W25Q128::waitReady() {
    // The lock covers ONLY the status read, never the wait.
    //
    // It used to span the whole loop body, delay included, because the guard
    // was declared at the top of the body. Erasing one 4 KB sector takes 45 to
    // 400 ms and programming a page a few, so the shared SPI bus stayed taken
    // for practically all of that time and the CAN task could not reach the
    // MCP2515 to answer a request. It showed up as OBD timeouts during a USB
    // stick import, which writes many sectors in a row from the UI task.
    for (;;) {
        uint8_t status;
        {
            hal::SpiLock lock;
            SPI.beginTransaction(kSpiSettings);
            digitalWrite(cs_pin_, LOW);
            SPI.transfer(CMD_READ_STATUS1);
            status = SPI.transfer(0x00);
            digitalWrite(cs_pin_, HIGH);
            SPI.endTransaction();
        }
        if (!(status & 0x01)) return;   // WIP cleared
        delay(1);                       // bus is free for the other task here
    }
}

void W25Q128::erase_sector(uint32_t addr) {
    writeEnable();
    {
        hal::SpiLock lock;
        SPI.beginTransaction(kSpiSettings);
        digitalWrite(cs_pin_, LOW);
        SPI.transfer(CMD_SECTOR_ERASE);
        SPI.transfer((addr >> 16) & 0xFF);
        SPI.transfer((addr >>  8) & 0xFF);
        SPI.transfer( addr        & 0xFF);
        digitalWrite(cs_pin_, HIGH);
        SPI.endTransaction();
    }
    waitReady();
}

void W25Q128::programPage(uint32_t addr, const uint8_t* data, size_t n) {
    writeEnable();
    {
        hal::SpiLock lock;
        SPI.beginTransaction(kSpiSettings);
        digitalWrite(cs_pin_, LOW);
        SPI.transfer(CMD_PAGE_PROGRAM);
        SPI.transfer((addr >> 16) & 0xFF);
        SPI.transfer((addr >>  8) & 0xFF);
        SPI.transfer( addr        & 0xFF);
        for (size_t i = 0; i < n; ++i) SPI.transfer(data[i]);
        digitalWrite(cs_pin_, HIGH);
        SPI.endTransaction();
    }
    waitReady();
}

void W25Q128::program(uint32_t addr, const uint8_t* data, size_t n) {
    while (n > 0) {
        size_t page_room = 256 - (addr % 256);
        size_t chunk = n < page_room ? n : page_room;
        programPage(addr, data, chunk);
        addr += chunk;
        data += chunk;
        n -= chunk;
    }
}
