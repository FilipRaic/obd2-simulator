// pins_custom_s3.h
// GPIO assignment for the ESP32-S3-WROOM-1 module: the single hardware-first target,
// used on the breadboard adapter during development and on the dedicated PCB.
// This is the authoritative map:
// analog inputs on ADC1 (GPIO1-10), strapping pins (3, 45, 46) and the
// flash/octal-PSRAM range (GPIO26-37) avoided. GPIO0 keeps its standard
// strapping role only: the BOOT button (SW4), never a firmware signal.
#pragma once

// Shared SPI bus (FSPI)
constexpr int PIN_SPI_SCK  = 12;
constexpr int PIN_SPI_MISO = 13;
constexpr int PIN_SPI_MOSI = 11;

// CAN controller (MCP2515)
constexpr int PIN_CS_CAN   = 10;
constexpr int PIN_INT_CAN  = 9;

// Display (ILI9341) - also configured for TFT_eSPI via build flags
constexpr int PIN_CS_TFT   = 14;
constexpr int PIN_DC_TFT   = 21;
constexpr int PIN_RST_TFT  = 47;

// Memory
constexpr int PIN_CS_FLASH = 15;  // W25Q128 (primary storage, FAT filesystem)

// USB (v0.5): one OTG controller on fixed pins, switched between the USB-C
// connector (MSC device, PC link) and the USB-A receptacle (stick host) by
// the TS3USB221 analog mux, and stick VBUS goes through the SY6280 load switch.
// A hardware-first pull-down (R15) holds the mux select LOW while no firmware
// drives it, so at reset the OTG pins face USB-C and the ROM bootloader's
// USB-Serial-JTAG is reachable for flashing (see "Programming" below).
constexpr int PIN_USB_DN      = 19;  // fixed OTG D- (informational)
constexpr int PIN_USB_DP      = 20;  // fixed OTG D+ (informational)
// Mux select: LOW = USB-C, HIGH = USB-A. The firmware KEEPS IT LOW in normal
// operation and raises it only for the duration of a stick session, so the
// ROM's USB-Serial-JTAG stays reachable from a PC and uploads need no button
// presses (see pins_init_normal_mode in src/storage/usb_msc_device.cpp).
constexpr int PIN_USB_SEL     = 16;
// 5 V load-switch enable for USB-A, active high, with a 10 k pull-down (R37)
// so the stick supply stays off until the firmware asks for it.
constexpr int PIN_USB_HOST_EN = 17;

// Programming (informational - none of these are driven by the firmware).
// Upload runs over USB-C via the ROM USB-Serial-JTAG on the fixed OTG pins:
// `pio run -e custom-board -t upload`, with no button presses. The running
// application never calls USB.begin(), so the USB PHY stays routed to the
// USB-Serial-JTAG controller instead of the OTG one, and the mux stays on
// the USB-C side, so esptool sees a port and resets the chip itself.
//
// The manual path - hold BOOT (SW4, GPIO0 low), tap RESET (SW5, EN), release
// BOOT, then upload - is needed only when that port is genuinely gone: in the
// MSC device role (USB.begin() has taken the OTG controller) or when the
// firmware hangs before pins_init_normal_mode() runs.
//
// The serial monitor stays on UART0 (ARDUINO_USB_CDC_ON_BOOT=0) and is
// exposed on header J6 for an external USB-UART adapter. That header carries
// only TX, RX and GND, so the UART path always needs the two buttons.
constexpr int PIN_BOOT_BTN    = 0;   // SW4 to GND, 10 k pull-up (R14)
constexpr int PIN_UART0_TX    = 43;  // J6 pin 1, 115200 baud monitor
constexpr int PIN_UART0_RX    = 44;  // J6 pin 2

// User interface (EN11 incremental encoder, SKRHABE010 5-way switch, three buttons).
// v0.7: the analog stick and its J3 header were replaced by the on-board
// Alps SKRHABE010. JOY_X/JOY_Y stay on the same ADC pins but now carry a
// three-level resistor ladder (idle ~3,3 V / 10 k ladder ~1,96 V / 0 V),
// decoded in ui/input.cpp.
// ENC1 = BI Technologies EN11-HSB1AQ20, incremental, 20 detents/turn, with
// push switch (board v0.8). It replaced the RK12L12 potentiometer: A took
// over the old POT net on GPIO1, B and the switch use two module pins that
// were previously unconnected. GPIO1 is still an ADC pin but is now used
// digitally.
//
// Board v0.9/v0.9b fit an external filter on all three contacts, so the
// internal pull-ups are no longer the only thing holding the lines: 100 R in
// series at the contact (R38-R40), then a 10 k pull-up and 47 nF to ground
// (R32-R34, C31-C33), and 1 nF at the module pin (C34-C36). The rise time is
// therefore ~650 us to the input threshold, which is well inside the ~5 ms
// edge spacing of the fastest realistic turn - the ISR decoding below does not
// need to change. (This comment used to say "no external parts are fitted",
// which stopped being true with board v0.9.)
constexpr int PIN_ENC_A       = 1;   // quadrature channel A (was PIN_POT)
constexpr int PIN_ENC_B       = 38;  // quadrature channel B
constexpr int PIN_ENC_SW      = 39;  // encoder push switch, active low
constexpr int PIN_JOY_X       = 2;   // ADC1_CH1, SW6 A (direct) / B (ladder)
constexpr int PIN_JOY_Y       = 4;   // ADC1_CH3, SW6 C (direct) / D (ladder)
// SW6 centre push, active low, R9 pull-up - ON PAPER. On the assembled v0.7
// board this pin is really the switch's COMMON terminal, because the footprint's
// pin numbering does not match the part (found by measurement 21.08.2026.).
// The firmware holds it LOW so the four directions work at all, and releases it
// for a few hundred microseconds to read the centre. NEVER drive it HIGH: with
// the centre pressed that is a short to ground. Full account in
// ui/input.cpp and hardware/kicad/PROVJERITI-PRIJE-IZRADE.md.
constexpr int PIN_JOY_SW      = 5;
constexpr int PIN_BTN_CONFIRM = 6;   // active low, external pull-up
constexpr int PIN_BTN_CLEAR   = 7;   // active low, external pull-up
constexpr int PIN_BTN_RETURN  = 8;   // active low, external pull-up

// S3 pins are all full I/O, so internal pull-ups exist as a fallback.
constexpr bool PIN_BTN_NEEDS_EXTERNAL_PULLUP = false;
