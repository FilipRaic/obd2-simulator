// can_handler.cpp
// OBD-II request dispatcher: receives ISO 15765-4 frames on 0x7DF/0x7E0,
// builds SAE J1979 / ISO 15031-5 responses and sends them on 0x7E8
// through the ISO-TP layer (single frame or segmented as needed).
//
// Implemented services:
//   0x01 current data, 0x02 freeze frame, 0x03 stored DTCs,
//   0x04 clear DTCs, 0x07 pending DTCs, 0x09 vehicle information.
// All other services get a negative response 0x7F <mode> 0x11.

#include "can_handler.h"
#include "obd2_pids.h"
#include "pid_encoder.h"
#include "sensor_table.h"
#include <cstring>

// Default VIN (17 characters), matching the factory scenario.
const char OBD_VIN[18] = "WVWZZZ1KZAW000001";

// The VIN mode 0x09 reports. A scenario may replace it (see can_handler.h);
// with no scenario, or a scenario without a "vin" key, this stays the default.
static char s_active_vin[18] = "WVWZZZ1KZAW000001";

void obd_set_vin(const char* vin) {
    if (!vin || !vin[0]) {
        std::memcpy(s_active_vin, OBD_VIN, sizeof(s_active_vin));
        return;
    }
    std::strncpy(s_active_vin, vin, sizeof(s_active_vin) - 1);
    s_active_vin[sizeof(s_active_vin) - 1] = '\0';
    // Mode 0x09 always sends exactly 17 characters, so a short VIN is padded
    // rather than left with whatever the previous one had in those positions.
    for (size_t i = std::strlen(s_active_vin); i < 17; ++i)
        s_active_vin[i] = ' ';
    s_active_vin[17] = '\0';
}

const char* obd_get_vin() { return s_active_vin; }

static void send_message(const IsoTpMessage& msg) {
    iso_tp_send(OBD_RESPONSE_ID, msg);
}

static void send_negative_response(uint8_t mode) {
    IsoTpMessage resp;
    resp.push(OBD_NEGATIVE_RESPONSE);       // 0x7F
    resp.push(mode);
    resp.push(NRC_SERVICE_NOT_SUPPORTED);   // 0x11
    send_message(resp);
}

// ── Mode 0x01 - current data ─────────────────────────────────────────────────
static void handle_current_data(uint8_t pid, DtcBank& bank) {
    IsoTpMessage resp;
    resp.push(0x40 | OBD_MODE_CURRENT_DATA);  // 0x41
    resp.push(pid);

    // Supported PID bitmasks (0x00, 0x20, 0x40)
    if (pid == PID_SUPPORTED_01_20 || pid == PID_SUPPORTED_21_40 ||
        pid == PID_SUPPORTED_41_60) {
        uint32_t mask = build_supported_pids(pid);
        resp.push((mask >> 24) & 0xFF);
        resp.push((mask >> 16) & 0xFF);
        resp.push((mask >>  8) & 0xFF);
        resp.push( mask        & 0xFF);
        send_message(resp);
        return;
    }

    // PID 0x01 - MIL status and confirmed DTC count:
    // bit 7 of byte A = MIL, bits 6..0 = number of confirmed DTCs.
    if (pid == PID_MIL_STATUS) {
        resp.push(static_cast<uint8_t>((bank.mil_on() ? 0x80 : 0x00) |
                                       (bank.confirmed_count() & 0x7F)));
        resp.push(0x00);
        resp.push(0x00);
        resp.push(0x00);
        send_message(resp);
        return;
    }

    // General sensor PID
    SensorEntry* sensor = find_sensor(pid);
    if (!sensor) return; // unsupported PID: no response, per J1979
    uint8_t enc[4] = {};
    uint8_t len = encode_pid(pid, sensor->value, enc);
    if (len == 0) return;
    for (uint8_t i = 0; i < len; ++i) resp.push(enc[i]);
    send_message(resp);
}

// ── Mode 0x02 - freeze frame ─────────────────────────────────────────────────
// Request: mode, PID, frame number. Response: 0x42, PID, frame, data.
static void handle_freeze_frame(uint8_t pid, uint8_t frame, DtcBank& bank) {
    if (frame != 0x00) return;      // single freeze frame supported

    IsoTpMessage resp;
    resp.push(0x40 | OBD_MODE_FREEZE_FRAME);  // 0x42
    resp.push(pid);
    resp.push(frame);

    // PID 0x02 - DTC that caused the freeze frame (0x0000 if none)
    if (pid == PID_FREEZE_DTC) {
        uint16_t code = bank.freeze.valid ? bank.freeze.dtc : 0x0000;
        resp.push((code >> 8) & 0xFF);
        resp.push( code       & 0xFF);
        send_message(resp);
        return;
    }

    if (!bank.freeze.valid) return;

    // Any sensor PID - encode the value snapshotted at confirmation time
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i) {
        if (SENSOR_TABLE[i].pid != pid) continue;
        uint8_t enc[4] = {};
        uint8_t len = encode_pid(pid, bank.freeze.values[i], enc);
        if (len == 0) return;
        for (uint8_t b = 0; b < len; ++b) resp.push(enc[b]);
        send_message(resp);
        return;
    }
}

// ── Modes 0x03 / 0x07 - stored / pending DTCs ────────────────────────────────
// Response: (mode | 0x40), DTC count, then two bytes per DTC. Responses with
// more than two DTCs exceed a single frame and are segmented by ISO-TP.
static void handle_dtc_read(uint8_t mode, DtcBank& bank) {
    DtcState wanted = (mode == OBD_MODE_PENDING_DTC) ? DtcState::Pending
                                                     : DtcState::Confirmed;
    IsoTpMessage resp;
    resp.push(0x40 | mode);
    resp.push((wanted == DtcState::Pending) ? bank.pending_count()
                                            : bank.confirmed_count());
    for (uint8_t i = 0; i < bank.count; ++i) {
        if (bank.dtcs[i].state != wanted) continue;
        resp.push(bank.dtcs[i].high_byte());
        resp.push(bank.dtcs[i].low_byte());
    }
    send_message(resp);
}

// ── Mode 0x09 - vehicle information ──────────────────────────────────────────
static void handle_vehicle_info(uint8_t info_type) {
    IsoTpMessage resp;
    resp.push(0x40 | OBD_MODE_VEHICLE_INFO);  // 0x49
    resp.push(info_type);

    switch (info_type) {
    case INFOTYPE_VIN_COUNT:            // number of VIN data items
        resp.push(0x01);
        break;
    case INFOTYPE_VIN:                  // 17-char VIN, segmented by ISO-TP
        resp.push(0x01);                // number of data items
        for (uint8_t i = 0; i < 17; ++i)
            resp.push(static_cast<uint8_t>(s_active_vin[i]));
        break;
    default:
        return;                         // unsupported InfoType: no response
    }
    send_message(resp);
}

// ── Main CAN frame dispatcher ────────────────────────────────────────────────
void process_obd_request(const CanFrame& req, DtcBank& bank) {
    if (req.id != OBD_FUNCTIONAL_ID && req.id != OBD_PHYSICAL_ID) return;
    if (req.dlc < 2) return;

    // All standard OBD-II requests fit a single frame:
    // data[0] = PCI (0x0N), data[1] = mode, data[2] = PID/InfoType.
    uint8_t pci  = req.data[0];
    if ((pci & 0xF0) != 0x00) return;   // only single-frame requests
    uint8_t plen = pci & 0x0F;          // payload length (mode + parameters)
    if (plen < 1 || req.dlc < 1 + plen) return;

    uint8_t mode = req.data[1];
    uint8_t pid  = (plen >= 2) ? req.data[2] : 0x00;

    switch (mode) {

    case OBD_MODE_CURRENT_DATA:
        handle_current_data(pid, bank);
        break;

    case OBD_MODE_FREEZE_FRAME:
        handle_freeze_frame(pid, (plen >= 3) ? req.data[3] : 0x00, bank);
        break;

    case OBD_MODE_STORED_DTC:
    case OBD_MODE_PENDING_DTC:
        handle_dtc_read(mode, bank);
        break;

    case OBD_MODE_CLEAR_DTC: {
        bank.clear_all();               // also turns the MIL off
        IsoTpMessage resp;
        resp.push(0x40 | OBD_MODE_CLEAR_DTC);  // 0x44, no data
        send_message(resp);
        break;
    }

    case OBD_MODE_VEHICLE_INFO:
        handle_vehicle_info(pid);
        break;

    default:
        send_negative_response(mode);   // 0x7F <mode> 0x11
        break;
    }
}
