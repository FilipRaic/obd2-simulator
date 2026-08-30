// sensor_meta.h
// UI/storage metadata for the 21 simulated parameters: display label, unit,
// decimal places and the JSON key used by scenario files.
// Entries are index-aligned with SENSOR_TABLE so snapshot values can be
// addressed by row index without a lookup.
#pragma once
#include "sensor_table.h"
#include <cstring>

struct SensorMeta {
    uint8_t     pid;
    const char* key;    // scenario JSON key
    const char* label;  // short display name (fits a 320 px row)
    const char* unit;
    uint8_t     decimals;
};

inline constexpr SensorMeta SENSOR_META[] = {
    { PID_ENGINE_LOAD,            "engine_load_pct",     "Engine load",   "%",    1 },
    { PID_COOLANT_TEMP,           "coolant_temp_c",      "Coolant temp",  "C",    1 },
    { PID_SHORT_FUEL_TRIM_1,      "short_fuel_trim_pct", "STFT bank 1",   "%",    1 },
    { PID_LONG_FUEL_TRIM_1,       "long_fuel_trim_pct",  "LTFT bank 1",   "%",    1 },
    { PID_FUEL_PRESSURE,          "fuel_pressure_kpa",   "Fuel pressure", "kPa",  0 },
    { PID_INTAKE_MAP,             "intake_map_kpa",      "Intake MAP",    "kPa",  0 },
    { PID_ENGINE_RPM,             "rpm",                 "Engine RPM",    "rpm",  0 },
    { PID_VEHICLE_SPEED,          "vehicle_speed_kmh",   "Vehicle speed", "km/h", 0 },
    { PID_TIMING_ADVANCE,         "timing_advance_deg",  "Timing adv",    "deg",  1 },
    { PID_INTAKE_AIR_TEMP,        "intake_air_temp_c",   "Intake air",    "C",    1 },
    { PID_MAF_FLOW,               "maf_gs",              "MAF flow",      "g/s",  2 },
    { PID_THROTTLE_POS,           "throttle_pct",        "Throttle",      "%",    1 },
    { PID_O2_BANK1_SENSOR1,       "o2_b1s1_v",           "O2 B1 S1",      "V",    2 },
    { PID_OBD_STANDARD,           "obd_standard",        "OBD standard",  "",     0 },
    { PID_RUNTIME,                "runtime_s",           "Run time",      "s",    0 },
    { PID_DISTANCE_MIL_ON,        "distance_mil_km",     "Dist w/ MIL",   "km",   0 },
    { PID_FUEL_LEVEL,             "fuel_level_pct",      "Fuel level",    "%",    0 },
    { PID_BARO_PRESSURE,          "baro_kpa",            "Baro press",    "kPa",  0 },
    { PID_CONTROL_MODULE_VOLTAGE, "control_module_v",    "Module volt",   "V",    2 },
    { PID_AMBIENT_AIR_TEMP,       "ambient_air_temp_c",  "Ambient air",   "C",    1 },
    { PID_ENGINE_OIL_TEMP,        "oil_temp_c",          "Oil temp",      "C",    1 },
};

static_assert(sizeof(SENSOR_META) / sizeof(SensorMeta) == SENSOR_COUNT,
              "SENSOR_META must stay index-aligned with SENSOR_TABLE");

inline const SensorMeta* sensor_meta_by_key(const char* key) {
    for (const auto& m : SENSOR_META)
        if (std::strcmp(m.key, key) == 0) return &m;
    return nullptr;
}
