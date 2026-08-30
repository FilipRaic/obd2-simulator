// dtc_bank.h
// Diagnostic Trouble Code bank for the OBD-II simulator.
// DTC format per SAE J2012 / ISO 15031-6.
//
// Each DTC is either pending (reported by mode 0x07) or confirmed
// (reported by mode 0x03, and any confirmed DTC turns the MIL on).
// When a DTC becomes confirmed, a freeze frame (snapshot of all sensor
// values) is captured and served through mode 0x02.

#pragma once
#include "sensor_table.h"
#include <cstdint>
#include <array>
#include <cstring>

static constexpr uint8_t MAX_DTCS = 20;

enum class DtcState : uint8_t {
    Pending   = 0,   // detected in current/last driving cycle (mode 0x07)
    Confirmed = 1,   // stored, illuminates the MIL (mode 0x03)
};

// DTC category is encoded in the two most significant bits of the raw code:
// 00 = P (powertrain), 01 = C (chassis), 10 = B (body), 11 = U (network).
struct DTC {
    uint16_t code;      // raw 2-byte OBD encoding, e.g. 0x0301 = P0301
    DtcState state;
    char     label[64]; // human-readable (for UI display only)

    uint8_t high_byte() const { return (code >> 8) & 0xFF; }
    uint8_t low_byte()  const { return  code       & 0xFF; }
};

// ── DTC catalog pre-installed in the simulator ──────────────────────────────
inline constexpr std::array<DTC, 9> DTC_CATALOG = {{
    { 0x0100, DtcState::Pending,   "P0100 MAF Sensor Circuit Malfunction"      },
    { 0x0113, DtcState::Pending,   "P0113 Intake Air Temp Sensor High Input"   },
    { 0x0128, DtcState::Pending,   "P0128 Coolant Temp Below Thermostat"       },
    { 0x0171, DtcState::Confirmed, "P0171 System Too Lean (Bank 1)"            },
    { 0x0301, DtcState::Confirmed, "P0301 Cylinder 1 Misfire Detected"         },
    { 0x0420, DtcState::Confirmed, "P0420 Catalyst Efficiency Below Threshold" },
    { 0x0455, DtcState::Pending,   "P0455 EVAP System Large Leak Detected"     },
    { 0x0500, DtcState::Pending,   "P0500 Vehicle Speed Sensor A"              },
    { 0xC100, DtcState::Pending,   "U0100 Lost Communication With ECM/PCM"     },
}};

// ── Freeze frame - sensor snapshot captured when a DTC is confirmed ─────────
struct FreezeFrame {
    bool     valid = false;
    uint16_t dtc   = 0;                  // DTC that caused the freeze frame
    float    values[SENSOR_COUNT] = {};  // snapshot of SENSOR_TABLE values
};

// ── Active DTC store (runtime, editable via UI) ──────────────────────────────
struct DtcBank {
    DTC         dtcs[MAX_DTCS];
    uint8_t     count = 0;
    FreezeFrame freeze;

    // Default scenario: misfire + lean mixture + catalyst (confirmed, MIL on),
    // thermostat + speed sensor (pending).
    void load_defaults() {
        clear_all();
        add(0x0301, DtcState::Confirmed);  // P0301
        add(0x0171, DtcState::Confirmed);  // P0171
        add(0x0420, DtcState::Confirmed);  // P0420
        add(0x0128, DtcState::Pending);    // P0128
        add(0x0500, DtcState::Pending);    // P0500
    }

    bool add(uint16_t code, DtcState state) {
        if (count >= MAX_DTCS) return false;
        DTC d{};
        d.code  = code;
        d.state = state;
        for (const auto& c : DTC_CATALOG)
            if (c.code == code) { std::strncpy(d.label, c.label, sizeof(d.label) - 1); break; }
        dtcs[count++] = d;
        if (state == DtcState::Confirmed) capture_freeze_frame(code);
        return true;
    }

    // Promote a pending DTC to confirmed (turns the MIL on).
    bool confirm(uint16_t code) {
        for (uint8_t i = 0; i < count; ++i) {
            if (dtcs[i].code != code) continue;
            dtcs[i].state = DtcState::Confirmed;
            capture_freeze_frame(code);
            return true;
        }
        return false;
    }

    // Remove one code from the bank, whatever its state. Used by the UI, where
    // a code can be walked back down to "not present"; the OBD services
    // themselves never remove a single code (mode 0x04 clears everything).
    // The freeze frame is deliberately left alone: it is a snapshot of the
    // moment a fault was confirmed and stays until mode 0x04 erases the bank,
    // exactly as it does when other codes come and go.
    bool remove(uint16_t code) {
        for (uint8_t i = 0; i < count; ++i) {
            if (dtcs[i].code != code) continue;
            for (uint8_t j = i; j + 1 < count; ++j) dtcs[j] = dtcs[j + 1];
            --count;
            return true;
        }
        return false;
    }

    // Move one code straight to a target state, adding or removing it as
    // needed. This is what the UI drives: Absent -> Pending -> Confirmed and
    // back down again. Returns false only when the bank is full.
    bool set_state(uint16_t code, DtcState state) {
        for (uint8_t i = 0; i < count; ++i) {
            if (dtcs[i].code != code) continue;
            if (dtcs[i].state == state) return true;
            dtcs[i].state = state;
            if (state == DtcState::Confirmed) capture_freeze_frame(code);
            return true;
        }
        return add(code, state);
    }

    bool has(uint16_t code) const {
        for (uint8_t i = 0; i < count; ++i)
            if (dtcs[i].code == code) return true;
        return false;
    }

    // Mode 0x04: erase all DTCs, freeze frame and turn the MIL off.
    void clear_all() {
        count = 0;
        freeze = FreezeFrame{};
    }

    bool mil_on() const { return confirmed_count() > 0; }

    uint8_t confirmed_count() const {
        uint8_t n = 0;
        for (uint8_t i = 0; i < count; ++i)
            if (dtcs[i].state == DtcState::Confirmed) ++n;
        return n;
    }

    uint8_t pending_count() const {
        uint8_t n = 0;
        for (uint8_t i = 0; i < count; ++i)
            if (dtcs[i].state == DtcState::Pending) ++n;
        return n;
    }

private:
    // First confirmed DTC captures the freeze frame (kept until cleared).
    void capture_freeze_frame(uint16_t code) {
        if (freeze.valid) return;
        freeze.valid = true;
        freeze.dtc   = code;
        for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
            freeze.values[i] = SENSOR_TABLE[i].value;
    }
};
