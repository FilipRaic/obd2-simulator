// bitbang_probe.cpp
#include "bitbang_probe.h"
#include "board_config.h"
#include <Arduino.h>

namespace hal {

static char s_result[128] = "not run";

const char* bitbang_result() { return s_result; }

namespace {

// ~100 kHz, slow enough that nothing on this board can blame the edge rate.
constexpr uint32_t HALF_BIT_US = 5;

void clock_high() { digitalWrite(PIN_SPI_SCK, HIGH); delayMicroseconds(HALF_BIT_US); }
void clock_low()  { digitalWrite(PIN_SPI_SCK, LOW);  delayMicroseconds(HALF_BIT_US); }

// SPI mode 0, MSB first: the slave samples MOSI on the rising edge and
// presents its own bit after the falling one.
uint8_t transfer(uint8_t out) {
    uint8_t in = 0;
    for (int i = 7; i >= 0; --i) {
        digitalWrite(PIN_SPI_MOSI, (out >> i) & 1);
        clock_high();
        in = static_cast<uint8_t>((in << 1) | (digitalRead(PIN_SPI_MISO) & 1));
        clock_low();
    }
    return in;
}

void select(int cs)   { digitalWrite(cs, LOW);  delayMicroseconds(HALF_BIT_US); }
void deselect(int cs) { digitalWrite(cs, HIGH); delayMicroseconds(HALF_BIT_US); }

} // namespace

void bitbang_probe() {
    pinMode(PIN_SPI_SCK, OUTPUT);
    pinMode(PIN_SPI_MOSI, OUTPUT);
    pinMode(PIN_CS_FLASH, OUTPUT);
    pinMode(PIN_CS_CAN, OUTPUT);
    digitalWrite(PIN_CS_FLASH, HIGH);
    digitalWrite(PIN_CS_CAN, HIGH);
    digitalWrite(PIN_SPI_SCK, LOW);     // mode 0 idles low

    // Is the line free, or is it held? With every chip select high, an
    // undriven MISO must follow whichever internal resistor is switched on.
    // A line that reads 0 with the pull-up on is being held down by something.
    pinMode(PIN_SPI_MISO, INPUT_PULLUP);
    delayMicroseconds(200);
    int miso_pullup = digitalRead(PIN_SPI_MISO);
    pinMode(PIN_SPI_MISO, INPUT_PULLDOWN);
    delayMicroseconds(200);
    int miso_pulldown = digitalRead(PIN_SPI_MISO);
    pinMode(PIN_SPI_MISO, INPUT);

    uint8_t id[3] = {0, 0, 0};
    select(PIN_CS_FLASH);
    transfer(0x9F);                                  // JEDEC ID
    for (uint8_t& b : id) b = transfer(0x00);
    deselect(PIN_CS_FLASH);

    select(PIN_CS_CAN);                              // MCP2515 RESET
    transfer(0xC0);
    deselect(PIN_CS_CAN);
    delay(10);                                       // oscillator start-up

    select(PIN_CS_CAN);                              // WRITE CNF1 = 0x55
    transfer(0x02);
    transfer(0x2A);
    transfer(0x55);
    deselect(PIN_CS_CAN);

    select(PIN_CS_CAN);                              // READ CNF1
    transfer(0x03);
    transfer(0x2A);
    uint8_t cnf1 = transfer(0x00);
    deselect(PIN_CS_CAN);

    select(PIN_CS_CAN);                              // READ CANSTAT
    transfer(0x03);
    transfer(0x0E);
    uint8_t canstat = transfer(0x00);
    deselect(PIN_CS_CAN);

    snprintf(s_result, sizeof(s_result),
             "jedec %02x %02x %02x   cnf1 %02x   canstat %02x   "
             "miso pullup=%d pulldown=%d",
             id[0], id[1], id[2], cnf1, canstat, miso_pullup, miso_pulldown);
    Serial.printf("[bitbang] %s\n", s_result);
    Serial.flush();
}

} // namespace hal
