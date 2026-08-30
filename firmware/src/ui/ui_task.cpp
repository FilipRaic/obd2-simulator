// ui_task.cpp
#include "ui_task.h"
#include "screen.h"
#include "input.h"
#include "screens/home_screen.h"
#include "screens/sensor_screen.h"
#include "screens/dtc_screen.h"
#include "screens/settings_screen.h"
#include "hal/spi_bus.h"
#include "board_config.h"
#include <Arduino.h>
#include <TFT_eSPI.h>
#if defined(BRINGUP_DIAG)
#include "hal/crash_report.h"
#include <soc/spi_reg.h>
#else
#define crash_stage(n) ((void)0)
#endif

static TFT_eSPI s_tft;   // pins come from the per-env TFT_eSPI build flags

void ui_display_init() {
    // No SpiLock here on purpose: this runs before any task exists, so there
    // is nothing to arbitrate against, and taking the mutex would only hide
    // whether the bus really is quiet.
    // Step-by-step probe of what TFT_eSPI::init() does, so the panic inside it
    // can be attributed. On ESP32-S3 TFT_eSPI binds `SPIClass& spi = SPI`, the
    // same global object hal::spi_bus_init() opens. Arduino's SPIClass::begin
    // returns silently when spiStartBus() fails, leaving _spi NULL, and
    // beginTransaction() then dereferences it in spiGetClockDiv(_spi). That is
    // exactly a LoadProhibited, and it would happen inside tft.init() with no
    // output of its own.
    Serial.println("[ui] probe: pinMode CS/DC/RST");
    Serial.flush();
    pinMode(PIN_CS_TFT, OUTPUT);
    digitalWrite(PIN_CS_TFT, HIGH);
    pinMode(PIN_DC_TFT, OUTPUT);
    digitalWrite(PIN_DC_TFT, HIGH);
    pinMode(PIN_RST_TFT, OUTPUT);
    digitalWrite(PIN_RST_TFT, HIGH);
    Serial.println("[ui] probe: pins done");
    Serial.flush();
    crash_stage(30);

    Serial.println("[ui] probe: SPI.beginTransaction");
    Serial.flush();
    SPI.beginTransaction(SPISettings(20000000, MSBFIRST, SPI_MODE0));
    Serial.println("[ui] probe: transaction open, transferring one byte");
    Serial.flush();
    digitalWrite(PIN_CS_TFT, LOW);
    SPI.transfer(0x00);
    digitalWrite(PIN_CS_TFT, HIGH);
    SPI.endTransaction();
    Serial.println("[ui] probe: SPI OK, bus is usable");
    Serial.flush();
    crash_stage(40);

    Serial.println("[ui] display init, calling tft.init()");
    Serial.flush();
    crash_stage(50);
    s_tft.init();
    crash_stage(60);
    Serial.println("[ui] tft.init() done");
    Serial.flush();
    s_tft.setRotation(1);   // 320x240 landscape, controls to the right
    s_tft.fillScreen(ui::COL_BG);
    crash_stage(70);
#if defined(BRINGUP_DIAG)
    // Kept from the refuted half-duplex hypothesis of 22.08.2026. TFT_eSPI's
    // SET_BUS_WRITE_MODE overwrites the whole SPI user register with
    // SPI_USR_MOSI, which on paper leaves the bus write-only for everyone
    // else. Measured on the board straight after the display has drawn, the
    // register reads 0x18000001, so USR_MISO and DOUTDIN are both still there
    // and the display is NOT what silences the MCP2515 and the flash. The line
    // stays because it costs nothing and it is the one number that closes that
    // question the moment anybody asks it again.
    Serial.printf("[spi] user reg after display: 0x%08lx\n",
                  (unsigned long)READ_PERI_REG(SPI_USER_REG(2)));
    Serial.flush();
#endif
    Serial.println("[ui] screen cleared");
    Serial.flush();
}

static void ui_task(void*) {
    Serial.println("[ui] task entered");
    Serial.flush();

    static ScreenManager  mgr;
    static UiContext      ctx{ s_tft, mgr, {} };
    static HomeScreen     home(ctx);
    static SensorScreen   sensors(ctx);
    static DtcScreen      dtcs(ctx);
    static SettingsScreen settings(ctx);
    ctx.nav_sensors  = &sensors;
    ctx.nav_dtcs     = &dtcs;
    ctx.nav_settings = &settings;

    app::get_snapshot(ctx.snap);
    mgr.push(&home);

    static InputReader input;
    input.begin();
    Serial.println("[ui] input ready, entering loop");
    Serial.flush();

    uint32_t last_snapshot_ms = 0;
    for (;;) {
#if defined(BRINGUP_DIAG)
        input_debug_dump();   // rate-limited to 2 Hz inside
#endif
        InputEvent e;
        while (input.poll(e))
            mgr.top()->onEvent(e);

        uint32_t now = ::millis();
        if (now - last_snapshot_ms >= 100) {   // CAN task publishes at 10 Hz
            app::get_snapshot(ctx.snap);
            last_snapshot_ms = now;
        }

        {
            hal::SpiLock lock;
            mgr.top()->draw();
        }
        vTaskDelay(pdMS_TO_TICKS(15));
    }
}

void ui_task_start() {
    // Low priority, core 0: rendering must never delay the CAN response.
    xTaskCreatePinnedToCore(ui_task, "ui", 16384, nullptr, 2, nullptr, 0);
}
