// main.cpp
// OBD-II simulator firmware entry point.
// setup() initialises the shared SPI bus and storage, then starts the two
// FreeRTOS tasks: the high-priority CAN task (protocol core + MCP2515) and
// the low-priority UI task (ILI9341 + physical controls). On the dedicated
// ESP32-S3 board (v0.5) an NVS flag can select the PC-link boot mode
// instead, where the device exposes its scenario storage over USB-C as an
// MSC disk. The Arduino loop stays idle - all work happens in the tasks.
#include <Arduino.h>
#include "hal/spi_bus.h"
#if defined(BRINGUP_DIAG)
#include "hal/bitbang_probe.h"
#endif
#if defined(BRINGUP_DIAG)
#include "hal/crash_report.h"
#else
#define crash_stage(n) ((void)0)
#endif
#include "storage/storage.h"
#if defined(BRINGUP_DIAG)
#include "storage/flash_fs.h"
#endif
#include "storage/usb_msc_device.h"
#include "can/can_task.h"
#include "ui/ui_task.h"
#include "board_config.h"

void setup() {
    Serial.begin(115200);
    Serial.println("\nOBD-II Simulator");

#if defined(BRINGUP_DIAG)
    // Why did the PREVIOUS boot end? Printed before anything else can crash
    // again. This is the answer to the panic text that never arrives over
    // USB-C - see hal/crash_report.h.
    crash_report_print();
#endif
    crash_stage(10);

#if defined(BRINGUP_DIAG)
    // Before the SPI peripheral claims the pins - see hal/bitbang_probe.h.
    hal::bitbang_probe();
#endif

    hal::spi_bus_init();

#if defined(BOARD_HAS_USB)
    if (usb_msc::boot_requested())
        usb_msc::run();                 // never returns (reboots)
    usb_msc::pins_init_normal_mode();   // mux -> USB-C, stick power off
#endif

    storage::init();
    crash_stage(20);

    // Display first, while the SPI bus still has no other user.
    ui_display_init();
#if defined(BRINGUP_NO_CAN)
    // The other half of the bisection, see BRINGUP_NO_UI below. With the CAN
    // task left out, a UI that then reaches its main loop puts the fault in
    // the interaction between the two tasks over the shared SPI bus, and a UI
    // that still dies inside s_tft.init() puts it in the display path alone.
    Serial.println("[boot] CAN task DISABLED (BRINGUP_NO_CAN)");
    Serial.flush();
#else
    can_task_start();
    Serial.println("[boot] can_task_start returned");
    Serial.flush();
#endif
#if defined(BRINGUP_NO_UI)
    // Bring-up bisection (20.08.2026.): the board panics and reboots once the
    // tasks are up, and the panic text is lost - USB-Serial-JTAG delivers only
    // the tail of the last line, "ELF file SHA256:", so the Guru Meditation
    // line and the backtrace never arrive. With the UI task left out, a CAN
    // task that then loops quietly through it0/it1/it2 puts the fault in the
    // UI path, and one that still dies puts it in the CAN path.
    Serial.println("[boot] UI task DISABLED (BRINGUP_NO_UI)");
    Serial.flush();
#else
    ui_task_start();
    Serial.println("[boot] ui_task_start returned");
    Serial.flush();
#endif
}

#if defined(BRINGUP_DIAG)
// Repeated SPI probe, added 22.08.2026.
//
// Everything about this fault has to be read off a boot log that arrives over
// USB-C, and RESET takes the USB device down with it, so the first seconds are
// lost every single time. The two lines that decide where to look next are
// printed at boot and only at boot: whether the flash answers its JEDEC probe
// and whether the MCP2515 answers its CNF1 readback. Printing them again every
// few seconds costs nothing and cannot be missed by a capture that starts late.
//
// How to read the result:
//   jedec 01 60 18   the flash answers, so SCK, MOSI and MISO all reach the
//                    bottom of the chain and the bus is healthy. A mute
//                    MCP2515 is then its own problem - crystal Y1, CS_CAN or
//                    the chip's own supply.
//   jedec ff ff ff   nothing drives MISO. Either no slave answers at all
//                    (SCK or MOSI broken past the display branch, or both
//                    chips unpowered) or MISO is stuck high.
//   jedec 00 00 00   MISO is held low, which is a short to ground rather than
//                    a silent slave.
// miso_idle is the pad level with every chip select high, and it separates a
// floating line from a stuck one.
static void bringup_spi_probe() {
    hal::SpiLock lock;
    SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));

    uint8_t id[3] = {0, 0, 0};
    digitalWrite(PIN_CS_FLASH, LOW);
    SPI.transfer(0x9F);                       // JEDEC ID
    for (uint8_t& b : id) b = SPI.transfer(0x00);
    digitalWrite(PIN_CS_FLASH, HIGH);

    digitalWrite(PIN_CS_CAN, LOW);            // MCP2515 WRITE CNF1 = 0x55
    SPI.transfer(0x02);
    SPI.transfer(0x2A);
    SPI.transfer(0x55);
    digitalWrite(PIN_CS_CAN, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_CS_CAN, LOW);            // MCP2515 READ CNF1
    SPI.transfer(0x03);
    SPI.transfer(0x2A);
    uint8_t cnf1 = SPI.transfer(0x00);
    digitalWrite(PIN_CS_CAN, HIGH);

    SPI.endTransaction();

    Serial.printf("[probe] jedec %02x %02x %02x   cnf1 %02x   miso_idle %d\n",
                  id[0], id[1], id[2], cnf1, digitalRead(PIN_SPI_MISO));
    // Repeated with it, because the bit-bang probe runs once at boot and the
    // first seconds of the log are what USB-C keeps losing.
    Serial.printf("[bitbang] %s\n", hal::bitbang_result());
    Serial.printf("[fs] %s\n", flash_fs::mount_summary());
    Serial.flush();
}
#endif

void loop() {
#if defined(BRINGUP_DIAG)
    bringup_spi_probe();
    vTaskDelay(pdMS_TO_TICKS(3000));
#else
    vTaskDelay(pdMS_TO_TICKS(1000));
#endif
}
