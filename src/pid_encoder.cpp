// pid_encoder.cpp
// Encodes simulated sensor values into OBD-II response bytes
// per SAE J1979 / ISO 15031-5 formula definitions. The simulator applies
// each formula in reverse: physical value -> raw bytes A..D.

#include "obd2_pids.h"
#include "pid_encoder.h"
#include "sensor_table.h"
#include <cstdint>

// ── Helper: clamp float ──────────────────────────────────────────────────────
static float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

// ── PID encoding per ISO 15031-5 formula table ───────────────────────────────
// Returns number of data bytes written to out[].  0 = PID not supported.
uint8_t encode_pid(uint8_t pid, const float value, uint8_t out[4]) {
    uint32_t raw = 0;

    switch (pid) {

    // PID 0x04 - Engine load  value = A * 100 / 255  →  A = value * 255 / 100
    case PID_ENGINE_LOAD:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 100) * 255.0f / 100.0f);
        return 1;

    // PID 0x05,0x0F,0x46,0x5C - Temperatures  value = A - 40  →  A = value + 40
    case PID_COOLANT_TEMP:
    case PID_INTAKE_AIR_TEMP:
    case PID_AMBIENT_AIR_TEMP:
    case PID_ENGINE_OIL_TEMP:
        out[0] = static_cast<uint8_t>(clampf(value, -40, 215) + 40.0f);
        return 1;

    // PID 0x06,0x07 - Fuel trims  value = A / 1.28 - 100  →  A = (value + 100) * 1.28
    case PID_SHORT_FUEL_TRIM_1:
    case PID_LONG_FUEL_TRIM_1:
        out[0] = static_cast<uint8_t>((clampf(value, -100, 99.2f) + 100.0f) * 1.28f);
        return 1;

    // PID 0x0A - Fuel pressure  value = 3 * A  →  A = value / 3
    case PID_FUEL_PRESSURE:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 765) / 3.0f);
        return 1;

    // PID 0x0B - Intake MAP  A = value (kPa, 0-255)
    case PID_INTAKE_MAP:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 255));
        return 1;

    // PID 0x0C - Engine RPM  value = (256*A + B) / 4  →  raw = value * 4
    case PID_ENGINE_RPM:
        raw = static_cast<uint32_t>(clampf(value, 0, 16383.75f) * 4.0f);
        out[0] = (raw >> 8) & 0xFF;
        out[1] =  raw       & 0xFF;
        return 2;

    // PID 0x0D - Vehicle speed  A = value (km/h, 0-255)
    case PID_VEHICLE_SPEED:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 255));
        return 1;

    // PID 0x0E - Timing advance  value = A / 2 - 64  →  A = (value + 64) * 2
    case PID_TIMING_ADVANCE:
        out[0] = static_cast<uint8_t>((clampf(value, -64, 63.5f) + 64.0f) * 2.0f);
        return 1;

    // PID 0x10 - MAF  value = (256*A + B) / 100 g/s  →  raw = value * 100
    case PID_MAF_FLOW:
        raw = static_cast<uint32_t>(clampf(value, 0, 655.35f) * 100.0f);
        out[0] = (raw >> 8) & 0xFF;
        out[1] =  raw       & 0xFF;
        return 2;

    // PID 0x11 - Throttle position  A = value * 255 / 100
    case PID_THROTTLE_POS:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 100) * 255.0f / 100.0f);
        return 1;

    // PID 0x14 - O2 sensor voltage (B1S1)  value = A / 200  →  A = value * 200
    // Byte B carries the short fuel trim, 0xFF = not used in the test.
    case PID_O2_BANK1_SENSOR1:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 1.275f) * 200.0f);
        out[1] = 0xFF;
        return 2;

    // PID 0x1C - OBD standard the vehicle conforms to (enumeration)
    case PID_OBD_STANDARD:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 255));
        return 1;

    // PID 0x1F - Run time since engine start  value = 256*A + B  seconds
    case PID_RUNTIME:
        raw = static_cast<uint32_t>(clampf(value, 0, 65535));
        out[0] = (raw >> 8) & 0xFF;
        out[1] =  raw       & 0xFF;
        return 2;

    // PID 0x21 - Distance traveled with MIL on  value = 256*A + B  km
    case PID_DISTANCE_MIL_ON:
        raw = static_cast<uint32_t>(clampf(value, 0, 65535));
        out[0] = (raw >> 8) & 0xFF;
        out[1] =  raw       & 0xFF;
        return 2;

    // PID 0x2F - Fuel level  A = value * 255 / 100
    case PID_FUEL_LEVEL:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 100) * 255.0f / 100.0f);
        return 1;

    // PID 0x33 - Barometric pressure  A = value (kPa)
    case PID_BARO_PRESSURE:
        out[0] = static_cast<uint8_t>(clampf(value, 0, 255));
        return 1;

    // PID 0x42 - Control module voltage  value = (256*A + B) / 1000  →  raw = value * 1000
    case PID_CONTROL_MODULE_VOLTAGE:
        raw = static_cast<uint32_t>(clampf(value, 0, 65.535f) * 1000.0f);
        out[0] = (raw >> 8) & 0xFF;
        out[1] =  raw       & 0xFF;
        return 2;

    default:
        return 0; // unsupported PID
    }
}

// ── Supported PID bitmask builder (PIDs 0x00, 0x20, 0x40) ────────────────────
// Returns the 4-byte bitmask where bit (0x20 - N) of the 32-bit word marks
// PID (base + N) as supported. Bit 0 chains to the next block: it is set
// when any PID above (base + 0x20) is supported, so a scanner that starts
// at PID 0x00 discovers every implemented parameter.
// The mask is generated from the sensor table itself, so it can never
// disagree with the actually implemented parameters.
uint32_t build_supported_pids(uint8_t base) {
    uint32_t mask = 0;
    bool has_higher = false;

    // PID 0x01 (MIL status / DTC count) is served from the DTC bank,
    // not the sensor table, but is always supported.
    if (base == 0x00) mask |= (1u << (0x20 - 0x01));

    for (uint8_t i = 0; i < SENSOR_COUNT; ++i) {
        uint8_t pid = SENSOR_TABLE[i].pid;
        if (pid > base && pid <= base + 0x20)
            mask |= (1u << (0x20 - (pid - base)));
        else if (pid > base + 0x20)
            has_higher = true;
    }

    if (has_higher) mask |= 0x01; // PID (base + 0x20) = next supported-mask
    return mask;
}
