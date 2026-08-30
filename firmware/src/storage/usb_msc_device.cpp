// usb_msc_device.cpp
#include "usb_msc_device.h"
#include "board_config.h"
#include <Arduino.h>
#include <Preferences.h>

#if defined(BOARD_HAS_USB)
#include <USB.h>
#include <USBMSC.h>
#include <TFT_eSPI.h>
#include "w25q128.h"
#include "flash_block.h"
#include "flash_fs.h"
#include "hal/spi_bus.h"
#endif

namespace usb_msc {

static const char* NVS_NAMESPACE = "obdsim";
static const char* NVS_KEY       = "usbmsc";

bool boot_requested() {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, true);
    bool req = prefs.getBool(NVS_KEY, false);
    prefs.end();
    return req;
}

static void set_flag(bool value) {
    Preferences prefs;
    prefs.begin(NVS_NAMESPACE, false);
    prefs.putBool(NVS_KEY, value);
    prefs.end();
}

void request_and_reboot() {
    set_flag(true);
    ESP.restart();
}

#if defined(BOARD_HAS_USB)

void pins_init_normal_mode() {
    // The mux is PARKED ON USB-C, not on USB-A.
    //
    // It used to be parked on USB-A ("the stick side, where it is needed"),
    // and that quietly cost the board its upload path. With the OTG pins
    // switched away from the USB-C connector, the ROM's USB-Serial-JTAG is
    // physically unreachable while the application runs: `pio run -t upload`
    // finds no port, so it cannot toggle DTR/RTS to enter download mode, and
    // every single flash needed the manual dance (hold BOOT, tap RESET,
    // release BOOT). The platformio.ini note claimed that dance was only
    // needed in MSC mode, which was wrong for exactly this reason.
    //
    // Parking on USB-C costs nothing: usb_stick.cpp drives PIN_USB_SEL HIGH
    // itself in session_start() before it installs the USB host, and puts it
    // back LOW in session_teardown(). So the stick still works, and between
    // sessions the board stays reachable from a PC.
    //
    // This also matches what the hardware-first already does on its own: R15 is a
    // 10 k pull-down on PIN_USB_SEL, so the mux sits on the USB-C side at
    // reset. The firmware now simply keeps it there instead of moving it.
    pinMode(PIN_USB_SEL, OUTPUT);
    digitalWrite(PIN_USB_SEL, LOW);       // mux -> USB-C (upload / PC side)
    pinMode(PIN_USB_HOST_EN, OUTPUT);
    digitalWrite(PIN_USB_HOST_EN, LOW);   // stick power off until needed
}

// ── MSC block access over the shared 512-byte block layer ──────────────
// The host addresses the medium in 512-byte blocks and the FAT volume on the
// chip is formatted with exactly that sector size, so what Windows reads at
// LBA 0 is a boot sector that describes the medium it is actually talking to.
// Until 21.08.2026. FatFs used 4 KB sectors here while MSC advertised 512,
// and the PC answered every connection with "you need to format the disk".
//
// Writes go through the flash_block cache instead of erasing a 4 KB sector
// per 512-byte callback. TinyUSB delivers one endpoint buffer at a time, so
// the old path erased the same sector eight times in a row, blocking the USB
// task for hundreds of milliseconds each time - that is why the PC-side
// format then failed as well.
static constexpr uint32_t MSC_BLOCK_SIZE  = flash_block::BLOCK_SIZE;
static constexpr uint32_t MSC_BLOCK_COUNT = flash_block::BLOCK_COUNT;

// The host has stopped writing for this long -> push the cache to the chip,
// so pulling the cable without ejecting loses at most the last sector.
static constexpr uint32_t FLUSH_IDLE_MS = 300;


static int32_t on_read(uint32_t lba, uint32_t offset, void* buffer,
                       uint32_t bufsize) {
    flash_block::read(lba * MSC_BLOCK_SIZE + offset,
                      static_cast<uint8_t*>(buffer), bufsize);
    return static_cast<int32_t>(bufsize);
}

static int32_t on_write(uint32_t lba, uint32_t offset, uint8_t* buffer,
                        uint32_t bufsize) {
    flash_block::write(lba * MSC_BLOCK_SIZE + offset, buffer, bufsize);
    return static_cast<int32_t>(bufsize);
}

// (power_condition, start, load_eject) - "stop" or an eject means the host is
// done with the medium, so nothing may stay in the cache.
static bool on_start_stop(uint8_t, bool start, bool load_eject) {
    if (!start || load_eject) flash_block::sync();
    return true;
}

// ── What is actually in the boot sector ───────────────────────────
// Added 21.08.2026., during the "Windows still asks to format" hunt. The
// board has no serial console in this mode (ARDUINO_USB_MODE=0, CDC off), so
// the screen is the only instrument available, and guessing at the layout
// f_mkfs writes is exactly what this hunt must not do. The numbers below are
// read straight off the chip, so they say what the PC is being offered.
static uint16_t le16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

static uint32_t le32(const uint8_t* p) {
    return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
           (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

static void draw_msc_screen(TFT_eSPI& tft) {
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM);
    tft.setTextFont(4);
    tft.setTextColor(TFT_CYAN, TFT_BLACK);
    tft.drawString("USB veza s racunalom", 160, 80);
    tft.setTextFont(2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("Uredjaj je vidljiv kao USB disk (scenariji).", 160, 120);
    tft.drawString("Eject the disk safely before going back.", 160, 140);
    tft.setTextColor(TFT_YELLOW, TFT_BLACK);
    tft.drawString("RETURN = povratak u simulator", 160, 180);
}

void run() {
    set_flag(false);   // one-shot: a plain reboot returns to the simulator

    // Route the OTG pins to the USB-C connector, and the stick stays unpowered.
    pinMode(PIN_USB_SEL, OUTPUT);
    digitalWrite(PIN_USB_SEL, LOW);
    pinMode(PIN_USB_HOST_EN, OUTPUT);
    digitalWrite(PIN_USB_HOST_EN, LOW);

    if (!flash_chip().begin(PIN_CS_FLASH)) {
        Serial.println("[usb_msc] W25Q128 missing, rebooting");
        ESP.restart();
    }

    flash_block::begin();

    // Snapshot the boot sector BEFORE mounting, because mount() may replace
    // the volume, and what the PC left behind is precisely the evidence.
    // Mount once and let go again, purely for the side effect: a chip that
    // carries no valid volume (a fresh board, or one still holding the old
    // 4 KB-sector layout) is formatted here, so the PC never meets a medium
    // it would ask to format. The volume must not stay mounted while the
    // host owns it - two writers on one FAT corrupt it.
    if (flash_fs::mount()) flash_fs::unmount();

    static USBMSC msc;
    msc.vendorID("OBD2SIM");
    msc.productID("OBD-II Sim");
    msc.productRevision("2.0");
    msc.onRead(on_read);
    msc.onWrite(on_write);
    msc.onStartStop(on_start_stop);
    msc.mediaPresent(true);
    msc.begin(MSC_BLOCK_COUNT, MSC_BLOCK_SIZE);
    USB.begin();
    Serial.println("[usb_msc] MSC device mode active");

    static TFT_eSPI tft;
    {
        hal::SpiLock lock;
        tft.init();
        tft.setRotation(1);
        draw_msc_screen(tft);
    }

    // RETURN (active low, debounced) reboots into the simulator.
    //
    // The "pins 34-39 are input-only" guard that used to stand here is gone
    // (09.08.2026.). It belongs to the CLASSIC ESP32; on the S3 that this board
    // always uses, 34-48 are ordinary GPIOs with working pull-ups. Keeping it
    // meant that moving the button into that range would silently leave it
    // floating and make the MSC screen unable to return to the simulator.
    // input.cpp dropped the same guard for the same reason.
    pinMode(PIN_BTN_RETURN, INPUT_PULLUP);
    uint32_t low_since = 0;
    for (;;) {
        bool pressed = digitalRead(PIN_BTN_RETURN) == LOW;
        uint32_t now = ::millis();
        if (!pressed)            low_since = 0;
        else if (low_since == 0) low_since = now;
        else if (now - low_since > 50) { flash_block::sync(); ESP.restart(); }

        // Idle flush: a host that wrote and then went quiet gets its data on
        // the chip even if the user never ejects the disk.
        if (flash_block::dirty() &&
            now - flash_block::last_write_ms() > FLUSH_IDLE_MS)
            flash_block::sync();

        delay(10);
    }
}

#else  // development board: no USB peripheral

void pins_init_normal_mode() {}

void run() {
    ESP.restart();   // cannot happen: flag is never set on this board
}

#endif

} // namespace usb_msc
