// scenario.h
// A simulation scenario: initial sensor values, the active
// profile and the DTC list, stored as human-editable JSON (listing 8 format):
//   { "name": "...", "profile": "idle", "vin": "...",
//     "sensors": { "coolant_temp_c": 112, ... },
//     "dtcs": [ { "code": "P0301", "state": "confirmed" }, ... ],
//     "mil_on": true }
// "mil_on" is written for readability but derived from the DTC states when
// loading. "vin" is both displayed by the UI and reported by mode 0x09: since
// 09.08.2026. apply_scenario() hands it to the protocol core with
// obd_set_vin(). Until then only the UI saw it, and the bus kept answering
// with the constant OBD_VIN, so the display and a diagnostic tool disagreed.
// A file without a "vin" key restores the factory VIN.
#pragma once
#include "app/app_types.h"
#include <cstdint>

struct SensorOverride {
    uint8_t pid;
    float   value;
};

struct ScenarioDtc {
    uint16_t code;
    DtcState state;
};

struct Scenario {
    char           name[app::SCENARIO_NAME_MAX] = "Factory defaults";
    SimProfile     profile                      = SimProfile::Idle;
    char           vin[18]                      = "";
    SensorOverride sensors[SENSOR_COUNT];
    uint8_t        sensor_count                 = 0;
    ScenarioDtc    dtcs[MAX_DTCS];
    uint8_t        dtc_count                    = 0;
};

// Built-in factory scenario: idle profile, SENSOR_TABLE defaults and the
// representative check-engine state of DtcBank::load_defaults() (3 confirmed
// + 2 pending, MIL on).
void scenario_factory_default(Scenario& out);

// JSON (de)serialisation. Buffers must hold the whole document. A scenario
// with all 21 sensors and 20 DTCs stays well under 2 KB.
bool   scenario_from_json(const char* json, Scenario& out);
size_t scenario_to_json(const Scenario& sc, char* buf, size_t buf_size);
