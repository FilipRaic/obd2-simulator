// sensor_table.h
// Simulated sensor value table.
// Each entry maps a PID to a floating-point simulated value
// and an optional noise configuration.
//
// The 21 parameters below are exactly the mode 0x01 PIDs of the
// implemented SAE J1979 subset.

#pragma once
#include "obd2_pids.h"
#include <cstdint>

struct SensorEntry {
    uint8_t pid;
    float   value;      // current simulated value (in PID's native unit)
    float   min_val;
    float   max_val;
    float   noise_amp;  // ±amplitude of random noise per sample
};

// ── Default sensor table - 21 parameters ────────────────────────────────────
// Values represent a "car at idle, warm engine, no load" state.
inline SensorEntry SENSOR_TABLE[] = {
//  PID                          value  min    max      noise
    { PID_ENGINE_LOAD,           25.0f,  0,    100,     0.5f  },  // %
    { PID_COOLANT_TEMP,          90.0f, -40,   215,     0.2f  },  // °C
    { PID_SHORT_FUEL_TRIM_1,      0.0f, -100,  99.2f,   0.3f  },  // %
    { PID_LONG_FUEL_TRIM_1,      -1.5f, -100,  99.2f,   0.1f  },  // %
    { PID_FUEL_PRESSURE,        350.0f,  0,    765,     0.0f  },  // kPa
    { PID_INTAKE_MAP,            34.0f,  0,    255,     1.0f  },  // kPa
    { PID_ENGINE_RPM,           800.0f,  0,  16383.75f, 5.0f  },  // rpm
    { PID_VEHICLE_SPEED,          0.0f,  0,    255,     0.0f  },  // km/h
    { PID_TIMING_ADVANCE,        10.0f, -64,   63.5f,   0.2f  },  // °
    { PID_INTAKE_AIR_TEMP,       35.0f, -40,   215,     0.3f  },  // °C
    { PID_MAF_FLOW,               3.1f,  0,    655.35f, 0.05f },  // g/s
    { PID_THROTTLE_POS,          15.0f,  0,    100,     0.1f  },  // %
    { PID_O2_BANK1_SENSOR1,       0.7f,  0,    1.275f,  0.02f },  // V
    { PID_OBD_STANDARD,           6.0f,  0,    255,     0.0f  },  // enum (6 = EOBD)
    { PID_RUNTIME,                0.0f,  0,  65535,     0.0f  },  // s (auto-inc)
    { PID_DISTANCE_MIL_ON,        0.0f,  0,  65535,     0.0f  },  // km
    { PID_FUEL_LEVEL,            75.0f,  0,    100,     0.0f  },  // %
    { PID_BARO_PRESSURE,        101.0f,  0,    255,     0.0f  },  // kPa
    { PID_CONTROL_MODULE_VOLTAGE,13.8f,  0,    65.535f, 0.05f },  // V
    { PID_AMBIENT_AIR_TEMP,      22.0f, -40,   215,     0.1f  },  // °C
    { PID_ENGINE_OIL_TEMP,       95.0f, -40,   215,     0.2f  },  // °C
};

static constexpr uint8_t SENSOR_COUNT =
    static_cast<uint8_t>(sizeof(SENSOR_TABLE) / sizeof(SensorEntry));

// Find sensor entry by PID, returns nullptr if not found.
inline SensorEntry* find_sensor(uint8_t pid) {
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        if (SENSOR_TABLE[i].pid == pid) return &SENSOR_TABLE[i];
    return nullptr;
}
