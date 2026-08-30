// test_simulator.cpp - host-side unit tests (no MCU hardware-first needed).
// Covers the ISO 15031-5 codec, supported-PID bitmasks, the DTC bank,
// ISO-TP segmentation and the full request/response dispatcher,
// including the edge cases of the implemented subset.

#include "obd2_pids.h"
#include "pid_encoder.h"
#include "sensor_table.h"
#include "dtc_bank.h"
#include "iso_tp.h"
#include "can_handler.h"
#include "simulator_core.h"
#include <cstdio>
#include <cstring>
#include <vector>

// ── Test harness ─────────────────────────────────────────────────────────────
static int g_pass = 0, g_fail = 0;

#define CHECK(name, cond)                                              \
    do {                                                               \
        if (cond) { printf("[PASS] %s\n", name); ++g_pass; }           \
        else      { printf("[FAIL] %s (line %d)\n", name, __LINE__);   \
                    ++g_fail; }                                        \
    } while (0)

// ── Platform stubs ───────────────────────────────────────────────────────────
static std::vector<CanFrame> g_sent;                 // captured CAN frames
void can_send_frame(const CanFrame& f) { g_sent.push_back(f); }

static uint8_t g_fc_status = 0;                      // 0 = CTS (default)
bool iso_tp_wait_flow_control(FlowControl& fc) {
    fc.flow_status = g_fc_status;
    fc.block_size  = 0;
    fc.st_min_us   = 0;
    return true;
}
void iso_tp_delay_us(uint32_t) {}

static uint32_t g_now_ms = 0;
uint32_t millis() { return g_now_ms; }

// Build a single-frame OBD request.
static CanFrame make_request(uint32_t id, std::initializer_list<uint8_t> payload) {
    CanFrame f{};
    f.id  = id;
    f.dlc = 8;
    f.data[0] = static_cast<uint8_t>(payload.size());
    uint8_t i = 1;
    for (uint8_t b : payload) f.data[i++] = b;
    for (; i < 8; ++i) f.data[i] = ISO_TP_PADDING;
    return f;
}

// ── 1. PID encoder (ISO 15031-5 conversion formulas, reverse direction) ──────
static void test_encoder() {
    printf("\n--- PID encoder ---\n");
    uint8_t out[4];

    // RPM 800 rpm -> raw = 800*4 = 3200 = 0x0C80 (reference CAN trace)
    CHECK("RPM 800 -> 0x0C 0x80",
          encode_pid(PID_ENGINE_RPM, 800.0f, out) == 2 &&
          out[0] == 0x0C && out[1] == 0x80);

    // Coolant 90 C -> 90+40 = 130 = 0x82 (ISO 15031-5 example)
    CHECK("Coolant 90 C -> 0x82",
          encode_pid(PID_COOLANT_TEMP, 90.0f, out) == 1 && out[0] == 0x82);

    // Range minimum: -40 C -> 0x00 (edge case)
    CHECK("Coolant -40 C -> 0x00",
          encode_pid(PID_COOLANT_TEMP, -40.0f, out) == 1 && out[0] == 0x00);

    // Range maximum: 215 C -> 0xFF
    CHECK("Coolant 215 C -> 0xFF",
          encode_pid(PID_COOLANT_TEMP, 215.0f, out) == 1 && out[0] == 0xFF);

    // Out-of-range value is clamped, not wrapped
    CHECK("Coolant 300 C clamps to 0xFF",
          encode_pid(PID_COOLANT_TEMP, 300.0f, out) == 1 && out[0] == 0xFF);

    CHECK("Speed 120 km/h -> 0x78",
          encode_pid(PID_VEHICLE_SPEED, 120.0f, out) == 1 && out[0] == 120);

    CHECK("Load 25%% -> 63",
          encode_pid(PID_ENGINE_LOAD, 25.0f, out) == 1 && out[0] == 63);

    CHECK("MAF 3.1 g/s -> raw 310",
          encode_pid(PID_MAF_FLOW, 3.1f, out) == 2 &&
          ((out[0] << 8) | out[1]) == 310);

    // Fuel trim 0 % -> (0+100)*1.28 = 128
    CHECK("STFT 0%% -> 128",
          encode_pid(PID_SHORT_FUEL_TRIM_1, 0.0f, out) == 1 && out[0] == 128);

    // Fuel trim -100 % -> 0
    CHECK("STFT -100%% -> 0",
          encode_pid(PID_SHORT_FUEL_TRIM_1, -100.0f, out) == 1 && out[0] == 0);

    // O2 voltage 0.7 V -> 0.7*200 = 140; byte B = 0xFF (STFT not used)
    CHECK("O2 0.7 V -> 140, 0xFF",
          encode_pid(PID_O2_BANK1_SENSOR1, 0.7f, out) == 2 &&
          out[0] == 140 && out[1] == 0xFF);

    // Timing advance 10 deg -> (10+64)*2 = 148
    CHECK("Timing 10 deg -> 148",
          encode_pid(PID_TIMING_ADVANCE, 10.0f, out) == 1 && out[0] == 148);

    // Fuel pressure 350 kPa -> 350/3 = 116
    CHECK("Fuel pressure 350 kPa -> 116",
          encode_pid(PID_FUEL_PRESSURE, 350.0f, out) == 1 && out[0] == 116);

    // Control module voltage 13.8 V -> 13800 = 0x35E8
    CHECK("Voltage 13.8 V -> 0x35 0xE8",
          encode_pid(PID_CONTROL_MODULE_VOLTAGE, 13.8f, out) == 2 &&
          out[0] == 0x35 && out[1] == 0xE8);

    CHECK("Fuel level 75%% -> 191",
          encode_pid(PID_FUEL_LEVEL, 75.0f, out) == 1 && out[0] == 191);

    CHECK("Runtime 3600 s -> 0x0E 0x10",
          encode_pid(PID_RUNTIME, 3600.0f, out) == 2 &&
          out[0] == 0x0E && out[1] == 0x10);

    CHECK("Distance MIL 260 km -> 0x01 0x04",
          encode_pid(PID_DISTANCE_MIL_ON, 260.0f, out) == 2 &&
          out[0] == 0x01 && out[1] == 0x04);

    CHECK("OBD standard 6 (EOBD) -> 0x06",
          encode_pid(PID_OBD_STANDARD, 6.0f, out) == 1 && out[0] == 0x06);

    // RPM range maximum: 16383.75 rpm -> raw = 65535 = 0xFF 0xFF
    CHECK("RPM 16383.75 -> 0xFF 0xFF",
          encode_pid(PID_ENGINE_RPM, 16383.75f, out) == 2 &&
          out[0] == 0xFF && out[1] == 0xFF);

    // Speed beyond the one-byte range clamps to 255
    CHECK("Speed 300 km/h clamps to 255",
          encode_pid(PID_VEHICLE_SPEED, 300.0f, out) == 1 && out[0] == 255);

    CHECK("Load 100%% -> 255",
          encode_pid(PID_ENGINE_LOAD, 100.0f, out) == 1 && out[0] == 255);

    CHECK("Throttle 100%% -> 255",
          encode_pid(PID_THROTTLE_POS, 100.0f, out) == 1 && out[0] == 255);

    // Fuel trim range maximum: +99.2 % -> (99.2+100)*1.28 = 254
    CHECK("STFT +99.2%% -> 254",
          encode_pid(PID_SHORT_FUEL_TRIM_1, 99.2f, out) == 1 && out[0] == 254);

    // O2 voltage range maximum: 1.275 V -> 255
    CHECK("O2 1.275 V -> 255",
          encode_pid(PID_O2_BANK1_SENSOR1, 1.275f, out) == 2 && out[0] == 255);

    CHECK("MAP 34 kPa -> 34",
          encode_pid(PID_INTAKE_MAP, 34.0f, out) == 1 && out[0] == 34);

    CHECK("Unsupported PID returns 0",
          encode_pid(0x99, 1.0f, out) == 0);

    // Every PID in the sensor table must have an encoder (consistency)
    bool all_encodable = true;
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i) {
        uint8_t tmp[4];
        if (encode_pid(SENSOR_TABLE[i].pid, SENSOR_TABLE[i].value, tmp) == 0)
            all_encodable = false;
    }
    CHECK("All 21 table PIDs have an encoder", all_encodable && SENSOR_COUNT == 21);
}

// ── 2. Supported-PID bitmasks ────────────────────────────────────────────────
static void test_supported_masks() {
    printf("\n--- Supported-PID bitmasks ---\n");
    uint32_t m00 = build_supported_pids(0x00);
    uint32_t m20 = build_supported_pids(0x20);
    uint32_t m40 = build_supported_pids(0x40);

    auto bit_for = [](uint8_t base, uint8_t pid) -> uint32_t {
        return 1u << (0x20 - (pid - base));
    };

    CHECK("PID 0x01 (MIL) marked supported",   m00 & bit_for(0x00, 0x01));
    CHECK("PID 0x0C (RPM) marked supported",   m00 & bit_for(0x00, 0x0C));
    CHECK("PID 0x03 not marked supported",   !(m00 & bit_for(0x00, 0x03)));
    CHECK("PID 0x2F (fuel) marked supported",  m20 & bit_for(0x20, 0x2F));
    CHECK("PID 0x5C (oil) marked supported",   m40 & bit_for(0x40, 0x5C));

    // Chaining: scanners only query the next block if bit 0 is set
    CHECK("Mask 0x00 chains to 0x20 (bit 0)",  m00 & 0x01);
    CHECK("Mask 0x20 chains to 0x40 (bit 0)",  m20 & 0x01);
    CHECK("Mask 0x40 does not chain",        !(m40 & 0x01));
}

// ── 3. DTC bank ──────────────────────────────────────────────────────────────
static void test_dtc_bank() {
    printf("\n--- DTC bank ---\n");
    DtcBank bank;
    bank.load_defaults();

    CHECK("Defaults: 5 DTCs loaded",      bank.count == 5);
    CHECK("Defaults: 3 confirmed",        bank.confirmed_count() == 3);
    CHECK("Defaults: 2 pending",          bank.pending_count() == 2);
    CHECK("MIL on with confirmed DTCs",   bank.mil_on());
    CHECK("Freeze frame captured",        bank.freeze.valid);
    CHECK("Freeze frame DTC = P0301",     bank.freeze.dtc == 0x0301);

    // Pending -> confirmed promotion
    DtcBank b2;
    b2.add(0x0128, DtcState::Pending);
    CHECK("Pending DTC: MIL stays off",   !b2.mil_on() && !b2.freeze.valid);
    b2.confirm(0x0128);
    CHECK("Confirm turns MIL on",         b2.mil_on() && b2.confirmed_count() == 1);
    CHECK("Confirm captures freeze frame",b2.freeze.valid && b2.freeze.dtc == 0x0128);

    bank.clear_all();
    CHECK("Clear empties bank + MIL off",
          bank.count == 0 && !bank.mil_on() && !bank.freeze.valid);

    // U0100 network code encodes with the U category bits (0xC1 0x00)
    DtcBank b3;
    b3.add(0xC100, DtcState::Pending);
    CHECK("U0100 -> bytes 0xC1 0x00",
          b3.dtcs[0].high_byte() == 0xC1 && b3.dtcs[0].low_byte() == 0x00);

    // set_state / remove: the UI walks one code Absent -> Pending -> Confirmed
    // and back down again, which the OBD services themselves never do.
    DtcBank b4;
    CHECK("set_state on an absent code adds it",
          b4.set_state(0x0420, DtcState::Pending) &&
          b4.count == 1 && b4.pending_count() == 1 && !b4.mil_on());
    CHECK("set_state promotes pending -> confirmed and lights the MIL",
          b4.set_state(0x0420, DtcState::Confirmed) &&
          b4.count == 1 && b4.confirmed_count() == 1 && b4.mil_on());
    CHECK("set_state demotes confirmed -> pending and clears the MIL",
          b4.set_state(0x0420, DtcState::Pending) &&
          b4.confirmed_count() == 0 && !b4.mil_on());
    CHECK("remove takes the code out of the bank",
          b4.remove(0x0420) && b4.count == 0 && !b4.has(0x0420));
    CHECK("remove on an absent code reports false", !b4.remove(0x0420));

    // Removing one code must not disturb the others, and the freeze frame
    // survives, because only mode 0x04 is allowed to erase it.
    DtcBank b5;
    b5.load_defaults();
    const uint8_t before = b5.count;
    CHECK("remove keeps the rest of the bank intact",
          b5.remove(0x0171) && b5.count == before - 1 &&
          b5.has(0x0301) && b5.has(0x0420) && b5.has(0x0128) &&
          !b5.has(0x0171));
    CHECK("remove leaves the freeze frame in place", b5.freeze.valid);
    CHECK("MIL stays on while other confirmed codes remain", b5.mil_on());
}

// ── 4. ISO-TP segmentation ───────────────────────────────────────────────────
static void test_iso_tp() {
    printf("\n--- ISO-TP ---\n");

    // 7 payload bytes: still a Single Frame (boundary case)
    g_sent.clear();
    IsoTpMessage m7;
    for (uint8_t i = 0; i < 7; ++i) m7.push(i);
    iso_tp_send(0x7E8, m7);
    CHECK("7 bytes -> one Single Frame",
          g_sent.size() == 1 && g_sent[0].data[0] == 0x07 &&
          g_sent[0].dlc == 8 && g_sent[0].data[7] == 0x06);

    // 8 payload bytes: First Frame + 1 Consecutive Frame
    g_sent.clear();
    IsoTpMessage m8;
    for (uint8_t i = 0; i < 8; ++i) m8.push(i);
    iso_tp_send(0x7E8, m8);
    CHECK("8 bytes -> FF + CF",
          g_sent.size() == 2 &&
          g_sent[0].data[0] == 0x10 && g_sent[0].data[1] == 0x08 &&
          g_sent[1].data[0] == 0x21);

    // First Frame carries the first 6 bytes, CF the remaining 2
    CHECK("FF/CF payload split correct",
          g_sent[0].data[2] == 0 && g_sent[0].data[7] == 5 &&
          g_sent[1].data[1] == 6 && g_sent[1].data[2] == 7);

    // 120 bytes: sequence number must wrap 15 -> 0 (edge case)
    g_sent.clear();
    IsoTpMessage big;
    for (uint16_t i = 0; i < 120; ++i) big.push(static_cast<uint8_t>(i));
    iso_tp_send(0x7E8, big);
    // 6 bytes in FF + 114/7 -> 17 CFs
    bool seq_ok = g_sent.size() == 18;
    uint8_t expected_seq = 1;
    for (size_t i = 1; i < g_sent.size() && seq_ok; ++i) {
        seq_ok = (g_sent[i].data[0] == (0x20 | expected_seq));
        expected_seq = (expected_seq + 1) & 0x0F;
    }
    CHECK("120 bytes -> 17 CFs, seq wraps 15->0", seq_ok);

    // 1 payload byte: minimal Single Frame, rest padded
    g_sent.clear();
    IsoTpMessage m1;
    m1.push(0xAB);
    iso_tp_send(0x7E8, m1);
    CHECK("1 byte -> SF [01 AB], padded",
          g_sent.size() == 1 && g_sent[0].data[0] == 0x01 &&
          g_sent[0].data[1] == 0xAB && g_sent[0].data[2] == ISO_TP_PADDING);

    // First Frame PCI carries the 12-bit total length (120 = 0x078)
    g_sent.clear();
    IsoTpMessage m120;
    for (uint16_t i = 0; i < 120; ++i) m120.push(0x00);
    iso_tp_send(0x7E8, m120);
    CHECK("FF PCI encodes length 120",
          g_sent[0].data[0] == 0x10 && g_sent[0].data[1] == 120);

    // Flow Control WAIT/OVFL aborts the transfer after the First Frame
    g_fc_status = 2;  // overflow
    g_sent.clear();
    IsoTpMessage m20;
    for (uint16_t i = 0; i < 20; ++i) m20.push(0x00);
    bool sent = iso_tp_send(0x7E8, m20);
    CHECK("FC overflow aborts after FF",
          !sent && g_sent.size() == 1 && (g_sent[0].data[0] & 0xF0) == 0x10);
    g_fc_status = 0;

    // STmin decoding
    CHECK("STmin 0x14 -> 20 ms",  iso_tp_decode_stmin_us(0x14) == 20000u);
    CHECK("STmin 0xF3 -> 300 us", iso_tp_decode_stmin_us(0xF3) == 300u);
    CHECK("STmin reserved value -> 127 ms", iso_tp_decode_stmin_us(0xA0) == 127000u);
}

// ── 5. Request dispatcher (modes 0x01-0x09) ──────────────────────────────────
static void test_dispatcher() {
    printf("\n--- OBD request dispatcher ---\n");
    DtcBank bank;
    bank.load_defaults();

    // Mode 0x01 PID 0x0C at 800 rpm - must reproduce the CAN trace from
    // Reference trace: request 0x7DF [02 01 0C] -> response 0x7E8 [04 41 0C 0C 80]
    find_sensor(PID_ENGINE_RPM)->value = 800.0f;
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x0C}), bank);
    CHECK("RPM query reproduces the reference trace",
          g_sent.size() == 1 && g_sent[0].id == 0x7E8 && g_sent[0].dlc == 8 &&
          g_sent[0].data[0] == 0x04 && g_sent[0].data[1] == 0x41 &&
          g_sent[0].data[2] == 0x0C && g_sent[0].data[3] == 0x0C &&
          g_sent[0].data[4] == 0x80 && g_sent[0].data[5] == ISO_TP_PADDING);

    // Physical addressing (0x7E0) is accepted too
    g_sent.clear();
    process_obd_request(make_request(0x7E0, {0x01, 0x0D}), bank);
    CHECK("Physical request 0x7E0 answered", g_sent.size() == 1);

    // Frames with foreign identifiers are ignored
    g_sent.clear();
    process_obd_request(make_request(0x123, {0x01, 0x0C}), bank);
    CHECK("Foreign CAN ID ignored", g_sent.empty());

    // Unsupported PID inside mode 0x01: no response
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x99}), bank);
    CHECK("Unsupported PID: no response", g_sent.empty());

    // PID 0x01 - MIL on + 3 confirmed DTCs -> A = 0x83
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x01}), bank);
    CHECK("MIL status: 0x80 | 3 = 0x83",
          g_sent.size() == 1 && g_sent[0].data[3] == 0x83);

    // PID 0x00 - supported bitmask, consistent with the encoder
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x00}), bank);
    uint32_t mask = build_supported_pids(0x00);
    CHECK("Supported mask served correctly",
          g_sent.size() == 1 &&
          g_sent[0].data[3] == ((mask >> 24) & 0xFF) &&
          g_sent[0].data[6] == (mask & 0xFF));

    // Mode 0x03 - 3 confirmed DTCs: 0x43 + count + 6 bytes = 8 bytes -> FF+CF
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x03}), bank);
    CHECK("Mode 0x03 segments into FF + CF",
          g_sent.size() == 2 &&
          g_sent[0].data[0] == 0x10 && g_sent[0].data[1] == 0x08 &&
          g_sent[0].data[2] == 0x43 && g_sent[0].data[3] == 0x03 &&   // count
          g_sent[0].data[4] == 0x03 && g_sent[0].data[5] == 0x01);    // P0301

    // Mode 0x07 - 2 pending DTCs fit a single frame
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x07}), bank);
    CHECK("Mode 0x07 returns pending DTCs",
          g_sent.size() == 1 && g_sent[0].data[1] == 0x47 &&
          g_sent[0].data[2] == 0x02 &&                                // count
          g_sent[0].data[3] == 0x01 && g_sent[0].data[4] == 0x28);    // P0128

    // Mode 0x02 - freeze frame: PID 0x02 returns the causing DTC
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x02, 0x02, 0x00}), bank);
    CHECK("Freeze frame DTC = P0301",
          g_sent.size() == 1 && g_sent[0].data[1] == 0x42 &&
          g_sent[0].data[4] == 0x03 && g_sent[0].data[5] == 0x01);

    // Mode 0x02 - sensor value frozen at confirmation time, not the live one
    float frozen_rpm = 0.0f;
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        if (SENSOR_TABLE[i].pid == PID_ENGINE_RPM) frozen_rpm = bank.freeze.values[i];
    find_sensor(PID_ENGINE_RPM)->value = 3000.0f;
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x02, 0x0C, 0x00}), bank);
    uint16_t raw = (g_sent[0].data[4] << 8) | g_sent[0].data[5];
    CHECK("Freeze frame value is the snapshot",
          g_sent.size() == 1 &&
          raw == static_cast<uint16_t>(frozen_rpm * 4.0f) && raw != 12000);

    // Mode 0x09 - VIN: 0x49 0x02 0x01 + 17 chars = 20 bytes -> FF + 2 CFs
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x09, 0x02}), bank);
    CHECK("VIN response segments into FF + 2 CFs",
          g_sent.size() == 3 &&
          g_sent[0].data[0] == 0x10 && g_sent[0].data[1] == 20 &&
          g_sent[0].data[2] == 0x49 && g_sent[0].data[3] == 0x02 &&
          g_sent[0].data[5] == 'W');
    // Reassemble and compare against the configured VIN
    char vin[18] = {};
    int vi = 0;
    for (int i = 5; i < 8; ++i) vin[vi++] = (char)g_sent[0].data[i];
    for (size_t f = 1; f < g_sent.size(); ++f)
        for (int i = 1; i < 8 && vi < 17; ++i) vin[vi++] = (char)g_sent[f].data[i];
    CHECK("VIN reassembles to WVWZZZ1KZAW000001", strcmp(vin, OBD_VIN) == 0);

    // A scenario may replace the reported VIN (obd_set_vin). Until 09.08.2026.
    // mode 0x09 always sent OBD_VIN, so a scenario's VIN reached the display
    // but never the bus.
    auto read_back_vin = [&](char out[18]) {
        int k = 0;
        for (int i = 5; i < 8; ++i) out[k++] = (char)g_sent[0].data[i];
        for (size_t f = 1; f < g_sent.size(); ++f)
            for (int i = 1; i < 8 && k < 17; ++i) out[k++] = (char)g_sent[f].data[i];
        out[17] = '\0';
    };
    obd_set_vin("ABCDEFGHJ12345678");
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x09, 0x02}), bank);
    char vin2[18] = {};
    read_back_vin(vin2);
    CHECK("Mode 0x09 reports the VIN set by the scenario",
          strcmp(vin2, "ABCDEFGHJ12345678") == 0);

    // A short VIN is padded to 17 characters, not left with the old tail.
    obd_set_vin("SHORT");
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x09, 0x02}), bank);
    char vin3[18] = {};
    read_back_vin(vin3);
    CHECK("Short VIN is space-padded to 17 characters",
          strcmp(vin3, "SHORT            ") == 0);

    // An empty VIN restores the factory value, which is what a scenario file
    // without a "vin" key must produce.
    obd_set_vin("");
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x09, 0x02}), bank);
    char vin4[18] = {};
    read_back_vin(vin4);
    CHECK("Empty VIN falls back to the factory VIN", strcmp(vin4, OBD_VIN) == 0);

    // PID 0x20 and 0x40 supported-mask requests are also served
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x20}), bank);
    uint32_t m20 = build_supported_pids(0x20);
    CHECK("Supported mask 0x20 served",
          g_sent.size() == 1 && g_sent[0].data[2] == 0x20 &&
          g_sent[0].data[3] == ((m20 >> 24) & 0xFF));
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x01, 0x40}), bank);
    uint32_t m40 = build_supported_pids(0x40);
    CHECK("Supported mask 0x40 served",
          g_sent.size() == 1 && g_sent[0].data[2] == 0x40 &&
          g_sent[0].data[6] == (m40 & 0xFF));

    // Mode 0x09 InfoType 0x01 - VIN message count fits a single frame
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x09, 0x01}), bank);
    CHECK("VIN count -> [03 49 01 01]",
          g_sent.size() == 1 && g_sent[0].data[0] == 0x03 &&
          g_sent[0].data[1] == 0x49 && g_sent[0].data[2] == 0x01 &&
          g_sent[0].data[3] == 0x01);

    // Malformed request: PCI declares zero-length payload
    g_sent.clear();
    CanFrame bad = make_request(0x7DF, {});
    process_obd_request(bad, bank);
    CHECK("Zero-length request ignored", g_sent.empty());

    // Multi-frame request PCI (First Frame) is not a valid OBD request here
    g_sent.clear();
    CanFrame ff = make_request(0x7DF, {0x01, 0x0C});
    ff.data[0] = 0x10;  // FF PCI
    process_obd_request(ff, bank);
    CHECK("Non-single-frame request ignored", g_sent.empty());

    // Mode 0x02 with a non-zero frame number: only frame 0 exists
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x02, 0x0C, 0x01}), bank);
    CHECK("Freeze frame #1 not available: no response", g_sent.empty());

    // Mode 0x06 - unsupported: negative response 0x7F 0x06 0x11
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x06, 0x01}), bank);
    CHECK("Mode 0x06 -> 7F 06 11",
          g_sent.size() == 1 && g_sent[0].data[0] == 0x03 &&
          g_sent[0].data[1] == 0x7F && g_sent[0].data[2] == 0x06 &&
          g_sent[0].data[3] == 0x11);

    // Mode 0x0A (permanent DTCs) - also unsupported: 0x7F 0x0A 0x11
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x0A}), bank);
    CHECK("Mode 0x0A -> 7F 0A 11",
          g_sent.size() == 1 && g_sent[0].data[1] == 0x7F &&
          g_sent[0].data[2] == 0x0A && g_sent[0].data[3] == 0x11);

    // Mode 0x04 - clear: positive response 0x44, bank empty
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x04}), bank);
    CHECK("Mode 0x04 clears bank, responds 0x44",
          g_sent.size() == 1 && g_sent[0].data[0] == 0x01 &&
          g_sent[0].data[1] == 0x44 && bank.count == 0 && !bank.mil_on());

    // After clearing: mode 0x03 reports zero DTCs
    g_sent.clear();
    process_obd_request(make_request(0x7DF, {0x03}), bank);
    CHECK("After clear: 0 stored DTCs",
          g_sent.size() == 1 && g_sent[0].data[1] == 0x43 &&
          g_sent[0].data[2] == 0x00);
}

// ── 6. Simulation model ──────────────────────────────────────────────────────
static void test_simulation() {
    printf("\n--- Simulation model ---\n");
    DtcBank bank;
    bank.load_defaults();
    simulator_bind_dtc_bank(&bank);

    // Idle profile: runtime counts up, RPM stays near 800
    simulator_set_profile(SimProfile::Idle);
    g_now_ms = 1000;
    simulator_update();                       // primes the tick timestamp
    for (int i = 0; i < 50; ++i) {            // 5 simulated seconds
        g_now_ms += 100;
        simulator_update();
    }
    float runtime = find_sensor(PID_RUNTIME)->value;
    CHECK("Runtime counter advances (5 s)", runtime >= 4.0f && runtime <= 6.0f);

    float rpm = find_sensor(PID_ENGINE_RPM)->value;
    CHECK("Idle RPM near 800", rpm > 700.0f && rpm < 900.0f);
    CHECK("Idle speed is 0", find_sensor(PID_VEHICLE_SPEED)->value == 0.0f);

    // Cold coolant warms up towards 90 C (first-order response)
    find_sensor(PID_COOLANT_TEMP)->value = 20.0f;
    for (int i = 0; i < 600; ++i) {           // 60 simulated seconds
        g_now_ms += 100;
        simulator_update();
    }
    float coolant = find_sensor(PID_COOLANT_TEMP)->value;
    CHECK("Coolant warms up (20 C -> >35 C after 60 s)",
          coolant > 35.0f && coolant < 90.5f);

    // Untouched sensors keep their values across profile ticks
    CHECK("Ambient temp untouched by profile",
          find_sensor(PID_AMBIENT_AIR_TEMP)->value > 20.0f &&
          find_sensor(PID_AMBIENT_AIR_TEMP)->value < 24.0f);

    // Drive profile: vehicle accelerates, RPM and MAF follow
    simulator_set_profile(SimProfile::Drive);
    for (int i = 0; i < 200; ++i) {           // 20 s into the cycle
        g_now_ms += 100;
        simulator_update();
    }
    float speed = find_sensor(PID_VEHICLE_SPEED)->value;
    CHECK("Drive: speed rises during acceleration", speed > 30.0f && speed < 90.0f);
    CHECK("Drive: RPM above idle", find_sensor(PID_ENGINE_RPM)->value > 1000.0f);
    CHECK("Drive: MAF above idle", find_sensor(PID_MAF_FLOW)->value > 5.0f);

    // MIL is on -> distance with MIL (PID 0x21) accumulates while driving
    CHECK("Distance with MIL accumulates",
          find_sensor(PID_DISTANCE_MIL_ON)->value > 0.0f);

    simulator_bind_dtc_bank(nullptr);
}

int main() {
    printf("=== OBD-II simulator - host-side unit tests ===\n");

    test_encoder();
    test_supported_masks();
    test_dtc_bank();
    test_iso_tp();
    test_dispatcher();
    test_simulation();

    printf("\n=== Results: %d passed, %d failed ===\n", g_pass, g_fail);
    return g_fail;
}
