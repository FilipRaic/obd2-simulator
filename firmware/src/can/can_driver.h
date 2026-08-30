// can_driver.h
// Register-level driver for the MCP2515 CAN controller.
// Bus speed 500 kbit/s from the 8 MHz crystal (ISO 15765-4). Acceptance
// filters pass only the OBD request identifiers 0x7DF and 0x7E0. All SPI
// transactions run under the shared-bus mutex and outside interrupt context
// - the ISR merely wakes the CAN task.
#pragma once
#include "iso_tp.h"
#include <cstdint>

class CanDriver {
public:
    // Full init sequence: reset, bit timing, filters, interrupts, normal mode.
    // Returns false if the controller does not respond or refuses the mode.
    bool begin(int cs_pin);

    // Fetch one pending frame from RXB0/RXB1, false when both are empty.
    bool receive(CanFrame& out);

    // Transmit through TXB0 (blocks until the previous TXREQ clears,
    // bounded by a short timeout). Returns false on timeout.
    bool send(const CanFrame& frame);

private:
    // SPI instructions
    static constexpr uint8_t CMD_RESET      = 0xC0;
    static constexpr uint8_t CMD_READ       = 0x03;
    static constexpr uint8_t CMD_WRITE      = 0x02;
    static constexpr uint8_t CMD_BIT_MODIFY = 0x05;
    static constexpr uint8_t CMD_RTS_TXB0   = 0x81;

    // Registers
    static constexpr uint8_t REG_CANSTAT  = 0x0E;
    static constexpr uint8_t REG_CANCTRL  = 0x0F;
    static constexpr uint8_t REG_CNF3     = 0x28;
    static constexpr uint8_t REG_CNF2     = 0x29;
    static constexpr uint8_t REG_CNF1     = 0x2A;
    static constexpr uint8_t REG_CANINTE  = 0x2B;
    static constexpr uint8_t REG_CANINTF  = 0x2C;
    static constexpr uint8_t REG_RXM0SIDH = 0x20;
    static constexpr uint8_t REG_RXM1SIDH = 0x24;
    static constexpr uint8_t REG_RXB0CTRL = 0x60;
    static constexpr uint8_t REG_RXB1CTRL = 0x70;
    static constexpr uint8_t REG_RXB0SIDH = 0x61;
    static constexpr uint8_t REG_RXB1SIDH = 0x71;
    static constexpr uint8_t REG_TXB0CTRL = 0x30;
    static constexpr uint8_t REG_TXB0SIDH = 0x31;

    // Filter base registers RXF0..RXF5
    static constexpr uint8_t REG_RXF_SIDH[6] = { 0x00, 0x04, 0x08, 0x10, 0x14, 0x18 };

    // Flags
    static constexpr uint8_t IRQ_RX0IF = 0x01;
    static constexpr uint8_t IRQ_RX1IF = 0x02;
    static constexpr uint8_t TXREQ     = 0x08;

    uint8_t readRegister(uint8_t reg);
    void    writeRegister(uint8_t reg, uint8_t value);
    void    writeRegisters(uint8_t reg, const uint8_t* data, uint8_t n);
    void    readRegisters(uint8_t reg, uint8_t* data, uint8_t n);
    void    bitModify(uint8_t reg, uint8_t mask, uint8_t value);
    void    reset();
    bool    setNormalMode();
    void    setStandardId(uint8_t sidh_reg, uint32_t id);
    bool    readRxBuffer(uint8_t sidh_reg, CanFrame& out);

    int cs_pin_ = -1;
};
