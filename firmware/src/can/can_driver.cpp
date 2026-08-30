// can_driver.cpp
#include "can_driver.h"
#include "can_handler.h"   // OBD_FUNCTIONAL_ID / OBD_PHYSICAL_ID
#include "hal/spi_bus.h"
#include <Arduino.h>
#include <SPI.h>

static const SPISettings kSpiSettings(10000000, MSBFIRST, SPI_MODE0);

constexpr uint8_t CanDriver::REG_RXF_SIDH[6];

// ── Low-level SPI access (always under the shared-bus mutex) ────────────────

uint8_t CanDriver::readRegister(uint8_t reg) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_READ);
    SPI.transfer(reg);
    uint8_t v = SPI.transfer(0x00);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
    return v;
}

void CanDriver::readRegisters(uint8_t reg, uint8_t* data, uint8_t n) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_READ);
    SPI.transfer(reg);
    for (uint8_t i = 0; i < n; ++i) data[i] = SPI.transfer(0x00);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
}

void CanDriver::writeRegister(uint8_t reg, uint8_t value) {
    writeRegisters(reg, &value, 1);
}

void CanDriver::writeRegisters(uint8_t reg, const uint8_t* data, uint8_t n) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_WRITE);
    SPI.transfer(reg);
    for (uint8_t i = 0; i < n; ++i) SPI.transfer(data[i]);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
}

void CanDriver::bitModify(uint8_t reg, uint8_t mask, uint8_t value) {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_BIT_MODIFY);
    SPI.transfer(reg);
    SPI.transfer(mask);
    SPI.transfer(value);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
}

void CanDriver::reset() {
    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_RESET);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
    delay(10);  // oscillator start-up; controller wakes in configuration mode
}

// ── Configuration ────────────────────────────────────────────────────────────

void CanDriver::setStandardId(uint8_t sidh_reg, uint32_t id) {
    uint8_t regs[4] = {
        static_cast<uint8_t>(id >> 3),           // SIDH
        static_cast<uint8_t>((id & 0x07) << 5),  // SIDL (standard frame)
        0x00, 0x00                               // EID8, EID0
    };
    writeRegisters(sidh_reg, regs, 4);
}

bool CanDriver::setNormalMode() {
    bitModify(REG_CANCTRL, 0xE0, 0x00);
    for (int i = 0; i < 10; ++i) {
        if ((readRegister(REG_CANSTAT) & 0xE0) == 0x00) return true;
        delay(1);
    }
    return false;
}

bool CanDriver::begin(int cs_pin) {
    cs_pin_ = cs_pin;
    pinMode(cs_pin_, OUTPUT);
    digitalWrite(cs_pin_, HIGH);

    reset();

    // Probe: CNF1 must read back, otherwise no controller is present.
    writeRegister(REG_CNF1, 0x55);
    if (readRegister(REG_CNF1) != 0x55) return false;

    // Bit timing for 500 kbit/s with the 8 MHz crystal.
    //
    // CNF1 = 0x00: SJW = 1 TQ, BRP = 0, so TQ = 2 x (BRP+1) / 8 MHz = 250 ns.
    // A 500 kbit/s bit is 2 us, which is 8 TQ, and 8 TQ is the only choice
    // here: BRP = 1 would give 500 ns per TQ and just 4 TQ per bit, below the
    // 8 TQ minimum.
    //
    // SAMPLE POINT MOVED FROM 62,5 % TO 75 % (09.08.2026.).
    //   was: Sync 1 + Prop 1 + PS1 3 + PS2 3 -> (1+1+3)/8 = 62,5 %
    //   now: Sync 1 + Prop 2 + PS1 3 + PS2 2 -> (1+2+3)/8 = 75 %
    // Both are exactly 500 kbit/s; only where the bit is read changes. CAN
    // practice puts the sample point at 75 to 87,5 %, and diagnostic tools are
    // built around that, so 62,5 % left the smallest margin exactly against the
    // devices this board exists to talk to. 87,5 % is not reachable with 8 TQ,
    // because it would need PS2 = 1 TQ and the MCP2515 requires PS2 >= 2 TQ.
    //
    // CNF2 = 0x91: BTLMODE 1 (PS2 from CNF3), SAM 0 (sample once),
    //              PHSEG1 = 010b -> PS1 = 3 TQ, PRSEG = 001b -> Prop = 2 TQ.
    // CNF3 = 0x01: PHSEG2 = 001b -> PS2 = 2 TQ.
    // Datasheet constraints hold: PS2 >= 2 TQ, PS2 >= SJW (1 TQ), and
    // Prop + PS1 = 5 TQ >= PS2.
    writeRegister(REG_CNF1, 0x00);
    writeRegister(REG_CNF2, 0x91);
    writeRegister(REG_CNF3, 0x01);

    // Accept only the OBD request identifiers 0x7DF and 0x7E0 on both
    // receive buffers (RXB1 catches rollover), everything else is ignored.
    setStandardId(REG_RXM0SIDH, 0x7FF);
    setStandardId(REG_RXM1SIDH, 0x7FF);
    setStandardId(REG_RXF_SIDH[0], OBD_FUNCTIONAL_ID);  // RXB0
    setStandardId(REG_RXF_SIDH[1], OBD_PHYSICAL_ID);
    setStandardId(REG_RXF_SIDH[2], OBD_FUNCTIONAL_ID);  // RXB1
    setStandardId(REG_RXF_SIDH[3], OBD_PHYSICAL_ID);
    setStandardId(REG_RXF_SIDH[4], OBD_FUNCTIONAL_ID);
    setStandardId(REG_RXF_SIDH[5], OBD_PHYSICAL_ID);
    writeRegister(REG_RXB0CTRL, 0x04);  // BUKT: roll over to RXB1 when full
    writeRegister(REG_RXB1CTRL, 0x00);

    // Interrupt on either receive buffer, then enter normal mode.
    writeRegister(REG_CANINTE, IRQ_RX0IF | IRQ_RX1IF);
    return setNormalMode();
}

// ── Receive / transmit ───────────────────────────────────────────────────────

bool CanDriver::readRxBuffer(uint8_t sidh_reg, CanFrame& out) {
    uint8_t raw[13];  // SIDH SIDL EID8 EID0 DLC D0..D7
    readRegisters(sidh_reg, raw, 13);
    out.id  = (static_cast<uint32_t>(raw[0]) << 3) | (raw[1] >> 5);
    out.dlc = raw[4] & 0x0F;
    if (out.dlc > 8) out.dlc = 8;
    for (uint8_t i = 0; i < 8; ++i) out.data[i] = raw[5 + i];
    return true;
}

bool CanDriver::receive(CanFrame& out) {
    uint8_t intf = readRegister(REG_CANINTF);
    if (intf & IRQ_RX0IF) {
        readRxBuffer(REG_RXB0SIDH, out);
        bitModify(REG_CANINTF, IRQ_RX0IF, 0x00);
        return true;
    }
    if (intf & IRQ_RX1IF) {
        readRxBuffer(REG_RXB1SIDH, out);
        bitModify(REG_CANINTF, IRQ_RX1IF, 0x00);
        return true;
    }
    return false;
}

bool CanDriver::send(const CanFrame& frame) {
    // Wait for the previous transmission to finish (a frame takes ~230 us
    // at 500 kbit/s, so 2 ms is a generous bound).
    uint32_t start = micros();
    while (readRegister(REG_TXB0CTRL) & TXREQ) {
        if (micros() - start > 2000) return false;
    }

    uint8_t buf[13];
    buf[0] = static_cast<uint8_t>(frame.id >> 3);
    buf[1] = static_cast<uint8_t>((frame.id & 0x07) << 5);
    buf[2] = 0x00;
    buf[3] = 0x00;
    buf[4] = frame.dlc & 0x0F;
    for (uint8_t i = 0; i < 8; ++i) buf[5 + i] = frame.data[i];
    writeRegisters(REG_TXB0SIDH, buf, 13);

    hal::SpiLock lock;
    SPI.beginTransaction(kSpiSettings);
    digitalWrite(cs_pin_, LOW);
    SPI.transfer(CMD_RTS_TXB0);
    digitalWrite(cs_pin_, HIGH);
    SPI.endTransaction();
    return true;
}
