// usb_stick.cpp
// Minimal USB MSC host path: usb_host library + Bulk-Only Transport with
// the four SCSI commands a FAT mount needs (TEST UNIT READY, READ
// CAPACITY(10), READ(10), WRITE(10)). Kept deliberately small and fully
// self-contained, and only 512-byte-block sticks are supported (universal for
// USB flash drives).
#include "usb_stick.h"
#include "board_config.h"

namespace usb_stick {

const char* result_text(Result r) {
    switch (r) {
        case Result::Ok:           return "OK";
        case Result::NotSupported: return "USB not available";
        case Result::NoStick:      return "Stick not found";
        case Result::MountFailed:  return "Unreadable file system";
        default:                   return "Copy failed";
    }
}

} // namespace usb_stick

#if !defined(BOARD_HAS_USB)

namespace usb_stick {
Result import_scenarios(uint8_t& copied) { copied = 0; return Result::NotSupported; }
Result export_scenarios(uint8_t& copied) { copied = 0; return Result::NotSupported; }
} // namespace usb_stick

#else

#include "storage.h"
#include "usb_msc_device.h"
#include <Arduino.h>
#include <usb/usb_host.h>
#include <esp_vfs_fat.h>
#include <diskio_impl.h>
#include <ff.h>
#include <cstdio>
#include <cstring>
#include <dirent.h>

namespace usb_stick {

// ── Host-stack state ─────────────────────────────────────────────────────────
static usb_host_client_handle_t s_client   = nullptr;
static usb_device_handle_t      s_dev      = nullptr;
static volatile uint8_t         s_dev_addr = 0;
static uint8_t  s_itf_num = 0, s_ep_in = 0, s_ep_out = 0;
static uint16_t s_ep_in_mps = 64, s_ep_out_mps = 64;
static uint32_t s_tag = 1;
static uint32_t s_block_count = 0;

static void client_event_cb(const usb_host_client_event_msg_t* msg, void*) {
    if (msg->event == USB_HOST_CLIENT_EVENT_NEW_DEV)
        s_dev_addr = msg->new_dev.address;
}

// Drive both the library daemon duties and our client while waiting.
static void pump_events(uint32_t ms) {
    uint32_t flags = 0;
    usb_host_lib_handle_events(pdMS_TO_TICKS(1), &flags);
    if (s_client) usb_host_client_handle_events(s_client, pdMS_TO_TICKS(ms));
}

// ── Synchronous transfer helper ──────────────────────────────────────────────
struct XferCtx { volatile bool done; };

static void xfer_cb(usb_transfer_t* t) {
    static_cast<XferCtx*>(t->context)->done = true;
}

// Submit a bulk transfer and pump events until completion. Returns actual
// byte count, or -1 on error/timeout.
static int bulk_xfer(uint8_t ep, uint8_t* data, uint32_t len,
                     uint32_t timeout_ms) {
    // IN transfers must request a multiple of the endpoint's MPS.
    uint32_t req = len;
    if (ep & 0x80) {
        uint16_t mps = s_ep_in_mps;
        req = ((len + mps - 1) / mps) * mps;
        if (req == 0) req = mps;
    }

    usb_transfer_t* t = nullptr;
    if (usb_host_transfer_alloc(req, 0, &t) != ESP_OK) return -1;
    XferCtx ctx{false};
    t->device_handle    = s_dev;
    t->bEndpointAddress = ep;
    t->num_bytes        = static_cast<int>(req);
    t->callback         = xfer_cb;
    t->context          = &ctx;
    if (!(ep & 0x80) && len) memcpy(t->data_buffer, data, len);

    int result = -1;
    if (usb_host_transfer_submit(t) == ESP_OK) {
        uint32_t deadline = ::millis() + timeout_ms;
        while (!ctx.done && static_cast<int32_t>(deadline - ::millis()) > 0)
            pump_events(5);
        if (ctx.done && t->status == USB_TRANSFER_STATUS_COMPLETED) {
            result = t->actual_num_bytes;
            if ((ep & 0x80) && data && result > 0)
                memcpy(data, t->data_buffer,
                       result < static_cast<int>(len) ? result : len);
        }
    }
    usb_host_transfer_free(t);
    return result;
}

// ── Bulk-Only Transport (USB MSC) ────────────────────────────────────────────
struct __attribute__((packed)) Cbw {
    uint32_t signature;      // 'USBC'
    uint32_t tag;
    uint32_t data_length;
    uint8_t  flags;          // 0x80 = data IN
    uint8_t  lun;
    uint8_t  cb_length;
    uint8_t  cb[16];
};
struct __attribute__((packed)) Csw {
    uint32_t signature;      // 'USBS'
    uint32_t tag;
    uint32_t residue;
    uint8_t  status;         // 0 = passed
};

static bool scsi_command(const uint8_t* cb, uint8_t cb_len, uint8_t* data,
                         uint32_t data_len, bool data_in,
                         uint32_t timeout_ms = 3000) {
    Cbw cbw{};
    cbw.signature   = 0x43425355;
    cbw.tag         = s_tag++;
    cbw.data_length = data_len;
    cbw.flags       = data_in ? 0x80 : 0x00;
    cbw.lun         = 0;
    cbw.cb_length   = cb_len;
    memcpy(cbw.cb, cb, cb_len);

    if (bulk_xfer(s_ep_out, reinterpret_cast<uint8_t*>(&cbw), 31,
                  timeout_ms) != 31)
        return false;

    if (data_len) {
        int n = bulk_xfer(data_in ? s_ep_in : s_ep_out, data, data_len,
                          timeout_ms);
        if (n < 0 || (!data_in && static_cast<uint32_t>(n) != data_len))
            return false;
    }

    Csw csw{};
    int n = bulk_xfer(s_ep_in, reinterpret_cast<uint8_t*>(&csw), 13,
                      timeout_ms);
    return n >= 13 && csw.signature == 0x53425355 && csw.status == 0;
}

static bool scsi_test_unit_ready() {
    // Fresh sticks report "not ready" briefly, so poll with REQUEST SENSE.
    for (int i = 0; i < 30; ++i) {
        const uint8_t tur[6] = {0x00, 0, 0, 0, 0, 0};
        if (scsi_command(tur, 6, nullptr, 0, false, 1000)) return true;
        uint8_t sense[18];
        const uint8_t rs[6] = {0x03, 0, 0, 0, 18, 0};
        scsi_command(rs, 6, sense, sizeof(sense), true, 1000);
        delay(100);
    }
    return false;
}

static bool scsi_read_capacity() {
    uint8_t cap[8];
    const uint8_t rc[10] = {0x25, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    if (!scsi_command(rc, 10, cap, sizeof(cap), true)) return false;
    uint32_t last_lba   = (cap[0] << 24) | (cap[1] << 16) | (cap[2] << 8) | cap[3];
    uint32_t block_size = (cap[4] << 24) | (cap[5] << 16) | (cap[6] << 8) | cap[7];
    if (block_size != 512) return false;   // only 512-byte sticks supported
    s_block_count = last_lba + 1;
    return true;
}

static bool scsi_rw10(bool write, uint32_t lba, uint16_t blocks,
                      uint8_t* data) {
    uint8_t cb[10] = {};
    cb[0] = write ? 0x2A : 0x28;
    cb[2] = (lba >> 24) & 0xFF;
    cb[3] = (lba >> 16) & 0xFF;
    cb[4] = (lba >>  8) & 0xFF;
    cb[5] =  lba        & 0xFF;
    cb[7] = (blocks >> 8) & 0xFF;
    cb[8] =  blocks       & 0xFF;
    return scsi_command(cb, 10, data, blocks * 512u, !write, 5000);
}

// ── FatFs diskio for the stick (volume "1:", 512-byte sectors) ──────────────
static constexpr BYTE STICK_PDRV = 1;
static constexpr UINT RW_CHUNK   = 8;   // 8 x 512 = 4 KB per transfer

static DSTATUS stick_init(BYTE)   { return 0; }
static DSTATUS stick_status(BYTE) { return 0; }

static DRESULT stick_read(BYTE, BYTE* buff, DWORD sector, UINT count) {
    while (count > 0) {
        UINT n = count < RW_CHUNK ? count : RW_CHUNK;
        if (!scsi_rw10(false, sector, static_cast<uint16_t>(n), buff))
            return RES_ERROR;
        sector += n; buff += n * 512; count -= n;
    }
    return RES_OK;
}

static DRESULT stick_write(BYTE, const BYTE* buff, DWORD sector, UINT count) {
    while (count > 0) {
        UINT n = count < RW_CHUNK ? count : RW_CHUNK;
        if (!scsi_rw10(true, sector, static_cast<uint16_t>(n),
                       const_cast<BYTE*>(buff)))
            return RES_ERROR;
        sector += n; buff += n * 512; count -= n;
    }
    return RES_OK;
}

static DRESULT stick_ioctl(BYTE, BYTE cmd, void* buff) {
    switch (cmd) {
    case CTRL_SYNC:        return RES_OK;
    case GET_SECTOR_COUNT: *reinterpret_cast<DWORD*>(buff) = s_block_count; return RES_OK;
    case GET_SECTOR_SIZE:  *reinterpret_cast<WORD*>(buff) = 512;            return RES_OK;
    case GET_BLOCK_SIZE:   *reinterpret_cast<DWORD*>(buff) = 1;             return RES_OK;
    default:               return RES_PARERR;
    }
}

static const ff_diskio_impl_t kStickDiskio = {
    .init = stick_init, .status = stick_status,
    .read = stick_read, .write = stick_write, .ioctl = stick_ioctl,
};

// ── Enumeration ──────────────────────────────────────────────────────────────
// Walk the raw configuration descriptor for an MSC BOT interface
// (class 0x08, subclass 0x06, protocol 0x50) and its bulk endpoints.
static bool find_msc_interface(const usb_config_desc_t* cfg) {
    const uint8_t* p   = reinterpret_cast<const uint8_t*>(cfg);
    const uint8_t* end = p + cfg->wTotalLength;
    bool in_msc = false;
    while (p + 2 <= end && p[0] >= 2) {
        uint8_t len = p[0], type = p[1];
        if (type == 0x04 && len >= 9) {              // interface descriptor
            in_msc = (p[5] == 0x08 && p[6] == 0x06 && p[7] == 0x50);
            if (in_msc) s_itf_num = p[2];
        } else if (in_msc && type == 0x05 && len >= 7) {  // endpoint
            uint8_t  addr = p[2];
            uint8_t  attr = p[3] & 0x03;
            uint16_t mps  = static_cast<uint16_t>(p[4] | (p[5] << 8));
            if (attr == 0x02) {                       // bulk
                if (addr & 0x80) { s_ep_in = addr;  s_ep_in_mps = mps; }
                else             { s_ep_out = addr; s_ep_out_mps = mps; }
            }
            if (s_ep_in && s_ep_out) return true;
        }
        p += len;
    }
    return false;
}

// ── Session setup / teardown ─────────────────────────────────────────────────
static FATFS* s_stick_fs = nullptr;

static void session_teardown() {
    if (s_stick_fs) {
        f_mount(nullptr, "1:", 0);
        esp_vfs_fat_unregister_path("/usb");
        s_stick_fs = nullptr;
    }
    // Drop the disk driver together with the volume. It points at s_dev, which
    // is closed a few lines below, so leaving it registered would leave a stale
    // pointer behind for the next session to trip over.
    ff_diskio_register(STICK_PDRV, nullptr);
    if (s_dev) {
        usb_host_interface_release(s_client, s_dev, s_itf_num);
        usb_host_device_close(s_client, s_dev);
        s_dev = nullptr;
    }
    if (s_client) {
        usb_host_client_deregister(s_client);
        s_client = nullptr;
    }
    // The host library is torn down asynchronously, and skipping the wait leaks
    // it. usb_host_device_free_all() returns ESP_ERR_NOT_FINISHED when devices
    // are still being released, and usb_host_uninstall() then refuses to run
    // with ESP_ERR_INVALID_STATE. Both return values used to be discarded, so a
    // failed uninstall went unnoticed: the library stayed installed with all of
    // its allocations, and every later usb_host_install() failed, which the UI
    // reported as "stick not found" for the rest of the power cycle.
    //
    // So the daemon is pumped until it reports ALL_FREE, and only then is the
    // library uninstalled. The 1 s cap is there because a stick pulled out
    // mid-transfer can leave the release pending indefinitely, and blocking the
    // UI task forever would be worse than one leaked session.
    if (usb_host_device_free_all() == ESP_ERR_NOT_FINISHED) {
        uint32_t deadline = ::millis() + 1000;
        uint32_t flags = 0;
        while (!(flags & USB_HOST_LIB_EVENT_FLAGS_ALL_FREE) &&
               static_cast<int32_t>(deadline - ::millis()) > 0) {
            usb_host_lib_handle_events(pdMS_TO_TICKS(10), &flags);
        }
    }
    if (usb_host_uninstall() != ESP_OK)
        Serial.println("[usb] host uninstall failed, stick unavailable until reset");
    digitalWrite(PIN_USB_HOST_EN, LOW);   // stick power off
    // Give the OTG pins back to the USB-C connector, so the board is again
    // reachable for flashing. Without this the first stick session would
    // leave the mux on USB-A until the next reset.
    digitalWrite(PIN_USB_SEL, LOW);       // mux -> USB-C (upload / PC side)
    s_dev_addr = 0;
    s_ep_in = s_ep_out = 0;
    s_block_count = 0;
}

static Result session_start() {
    // In normal mode the mux sits on the USB-C side, so that a PC can reach
    // the ROM's USB-Serial-JTAG for flashing (see pins_init_normal_mode).
    // A stick session therefore has to move it here, and session_teardown()
    // moves it back.
    digitalWrite(PIN_USB_SEL, HIGH);      // mux -> USB-A (stick side)
    digitalWrite(PIN_USB_HOST_EN, HIGH);
    delay(100);   // VBUS rise + stick power-up

    const usb_host_config_t host_cfg = {
        .skip_phy_setup = false,
        .intr_flags     = ESP_INTR_FLAG_LEVEL1,
    };
    if (usb_host_install(&host_cfg) != ESP_OK) {
        // The only exit that cannot go through session_teardown(), because the
        // host was never installed and uninstalling it would fail. The mux and
        // the stick supply therefore have to be put back by hand here, or the
        // board would stay on the USB-A side and lose its upload path until
        // the next reset.
        digitalWrite(PIN_USB_HOST_EN, LOW);
        digitalWrite(PIN_USB_SEL, LOW);   // mux -> USB-C (upload / PC side)
        return Result::NoStick;
    }

    usb_host_client_config_t client_cfg = {};
    client_cfg.is_synchronous              = false;
    client_cfg.max_num_event_msg           = 8;
    client_cfg.async.client_event_callback = client_event_cb;
    client_cfg.async.callback_arg          = nullptr;
    if (usb_host_client_register(&client_cfg, &s_client) != ESP_OK) {
        session_teardown();
        return Result::NoStick;
    }

    // Wait for enumeration (up to 3 s).
    uint32_t deadline = ::millis() + 3000;
    while (s_dev_addr == 0 && static_cast<int32_t>(deadline - ::millis()) > 0)
        pump_events(20);
    if (s_dev_addr == 0) { session_teardown(); return Result::NoStick; }

    if (usb_host_device_open(s_client, s_dev_addr, &s_dev) != ESP_OK) {
        session_teardown();
        return Result::NoStick;
    }
    const usb_config_desc_t* cfg = nullptr;
    if (usb_host_get_active_config_descriptor(s_dev, &cfg) != ESP_OK ||
        !find_msc_interface(cfg) ||
        usb_host_interface_claim(s_client, s_dev, s_itf_num, 0) != ESP_OK) {
        session_teardown();
        return Result::MountFailed;
    }

    if (!scsi_test_unit_ready() || !scsi_read_capacity()) {
        session_teardown();
        return Result::MountFailed;
    }

    ff_diskio_register(STICK_PDRV, &kStickDiskio);
    if (esp_vfs_fat_register("/usb", "1:", 4, &s_stick_fs) != ESP_OK ||
        f_mount(s_stick_fs, "1:", 1) != FR_OK) {
        session_teardown();
        return Result::MountFailed;
    }
    return Result::Ok;
}

// ── File copy ────────────────────────────────────────────────────────────────
static bool copy_file(const char* from, const char* to) {
    FILE* in = fopen(from, "rb");
    if (!in) return false;
    FILE* out = fopen(to, "wb");
    if (!out) { fclose(in); return false; }
    static uint8_t buf[1024];
    bool ok = true;
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0)
        if (fwrite(buf, 1, n, out) != n) { ok = false; break; }
    fclose(in);
    fclose(out);
    return ok;
}

static Result copy_json_dir(const char* src_dir, const char* dst_dir,
                            uint8_t& copied) {
    DIR* dir = opendir(src_dir);
    if (!dir) return Result::CopyFailed;
    Result result = Result::Ok;
    for (dirent* e = readdir(dir); e; e = readdir(dir)) {
        const char* name = e->d_name;
        size_t len = strlen(name);
        if (len < 6 || strcasecmp(name + len - 5, ".json") != 0) continue;
        char from[96], to[96];
        snprintf(from, sizeof(from), "%s/%s", src_dir, name);
        snprintf(to,   sizeof(to),   "%s/%s", dst_dir, name);
        if (copy_file(from, to)) ++copied;
        else result = Result::CopyFailed;
    }
    closedir(dir);
    return result;
}

Result import_scenarios(uint8_t& copied) {
    copied = 0;
    if (!storage::available()) return Result::CopyFailed;
    Result r = session_start();
    if (r != Result::Ok) return r;
    {
        // The copy touches /flash directly, so it has to hold the same lock
        // the storage:: functions use. Without it a stick import could run
        // against a scenario save from the CAN task on the same volume.
        storage::FsGuard fs;
        r = copy_json_dir("/usb", "/flash/scenarios", copied);
    }
    session_teardown();
    return r;
}

Result export_scenarios(uint8_t& copied) {
    copied = 0;
    if (!storage::available()) return Result::CopyFailed;
    Result r = session_start();
    if (r != Result::Ok) return r;
    {
        storage::FsGuard fs;   // same reason as in import_scenarios()
        r = copy_json_dir("/flash/scenarios", "/usb", copied);
    }
    session_teardown();
    return r;
}

} // namespace usb_stick

#endif // BOARD_HAS_USB
