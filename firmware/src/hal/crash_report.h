// crash_report.h
// Bring-up diagnostics: report why the PREVIOUS boot ended.
//
// Why this exists (measured 20.-21.08.2026. on the assembled v0.7 board):
// the board panics inside the display init and reboots, and the panic text
// never arrives. The reason is in the Arduino ESP32 sdkconfig:
//
//     CONFIG_ESP_CONSOLE_UART_DEFAULT=y            <- primary console: UART0
//     CONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=y
//
// The panic handler writes to the PRIMARY console, so the Guru Meditation
// line and the backtrace go out on UART0 (header J6). Over USB-C only the
// stray bytes that happen to fit the 64-byte USB-Serial-JTAG FIFO survive,
// which is where the meaningless tail ("fcebc50", then "ELF file SHA256:")
// in the boot log comes from. No amount of Serial.flush() can fix that -
// Serial is not the console the panic handler uses.
//
// The way out does not need a UART adapter. The same sdkconfig has
//
//     CONFIG_ESP_COREDUMP_ENABLE_TO_FLASH=y
//     CONFIG_ESP_COREDUMP_DATA_FORMAT_ELF=y
//
// and the partition table already carries a 64 kB `coredump` partition at
// 0x7F0000. So the panic IS recorded, in flash, completely, at the moment it
// happens. crash_report_print() reads it back on the next boot and prints it
// over whatever console works, at our own pace. A crash that cannot speak
// becomes a crash that can be read afterwards.
#pragma once

#include <stdint.h>

// Print the reset reason and, if one was saved, the core dump summary of the
// previous crash (task, exception cause, faulting address, PC, backtrace),
// then erase the saved dump so the next crash writes a fresh one.
//
// Call FIRST in setup(), right after Serial.begin(). Costs nothing when no
// dump is stored.
void crash_report_print();

// Record how far this boot got, in RTC memory that survives the reset. Two
// stores, no printing, safe to call from anywhere including the middle of a
// display init. The next boot prints the last value reached.
//
// Stages in use (bring-up, 21.08.2026.):
//   10 setup() entered            40 SPI probe: one byte transferred
//   20 storage ready              50 tft.init() entered
//   30 display pins configured    60 tft.init() returned
//   70 screen cleared             80 tasks started
void crash_stage(uint32_t stage);
