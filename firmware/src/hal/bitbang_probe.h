// bitbang_probe.h
// Bring-up only: talk to the two SPI slaves WITHOUT the SPI peripheral.
//
// Written 22.08.2026., after the ohmmeter had cleared the whole bus. Continuity
// says the copper is there, it does not say the signal is. This probe drives
// SCK, MOSI and the two chip selects as plain GPIOs and reads MISO with
// digitalRead, at about 100 kHz, so it shares nothing with the hardware SPI
// but the pads themselves.
//
// It runs FIRST in setup(), before hal::spi_bus_init(), so nothing has claimed
// the pins yet and the pin state it leaves behind is overwritten immediately.
//
// Reading the result:
//   bitbang answers, hardware SPI does not -> the board is fine and the fault
//     is in how the SPI peripheral is set up or driven.
//   neither answers -> the fault is physical after all, and the ohmmeter was
//     measuring a path the signal cannot actually use (a cracked joint that
//     conducts at a microamp, a chip that is not powered when it matters).
//   miso_pullup 0 -> something HOLDS the line low, which a free line with the
//     internal pull-up on cannot do. That is a different fault from silence.
#pragma once

namespace hal {
void bitbang_probe();

// The line bitbang_probe() printed, kept so loop() can repeat it. The probe
// runs once, at boot, and the boot log over USB-C is exactly what gets lost
// when RESET takes the USB device down with it.
const char* bitbang_result();
}
