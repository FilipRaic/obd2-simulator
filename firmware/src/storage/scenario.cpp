// scenario.cpp
#include "scenario.h"
#include "sensor_meta.h"
#include "dtc_format.h"
#include "can_handler.h"   // OBD_VIN
#include <ArduinoJson.h>
#include <cstring>

static const char* profile_to_string(SimProfile p) {
    switch (p) {
        case SimProfile::Manual: return "manual";
        case SimProfile::Drive:  return "drive";
        default:                 return "idle";
    }
}

static SimProfile profile_from_string(const char* s) {
    if (s && std::strcmp(s, "manual") == 0) return SimProfile::Manual;
    if (s && std::strcmp(s, "drive")  == 0) return SimProfile::Drive;
    return SimProfile::Idle;
}

void scenario_factory_default(Scenario& out) {
    out = Scenario{};
    std::strncpy(out.name, "Factory defaults", sizeof(out.name) - 1);
    std::strncpy(out.vin, OBD_VIN, sizeof(out.vin) - 1);
    out.profile = SimProfile::Idle;
    // Mirrors DtcBank::load_defaults(): misfire + lean + catalyst confirmed,
    // thermostat + speed sensor pending.
    const ScenarioDtc defaults[] = {
        { 0x0301, DtcState::Confirmed },
        { 0x0171, DtcState::Confirmed },
        { 0x0420, DtcState::Confirmed },
        { 0x0128, DtcState::Pending   },
        { 0x0500, DtcState::Pending   },
    };
    for (const auto& d : defaults) out.dtcs[out.dtc_count++] = d;
}

bool scenario_from_json(const char* json, Scenario& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) return false;

    out = Scenario{};
    if (const char* name = doc["name"])
        std::strncpy(out.name, name, sizeof(out.name) - 1);
    if (const char* vin = doc["vin"])
        std::strncpy(out.vin, vin, sizeof(out.vin) - 1);
    out.profile = profile_from_string(doc["profile"]);

    for (JsonPairConst kv : doc["sensors"].as<JsonObjectConst>()) {
        const SensorMeta* meta = sensor_meta_by_key(kv.key().c_str());
        if (!meta || out.sensor_count >= SENSOR_COUNT) continue;  // unknown keys ignored
        out.sensors[out.sensor_count++] = { meta->pid, kv.value().as<float>() };
    }

    for (JsonObjectConst d : doc["dtcs"].as<JsonArrayConst>()) {
        uint16_t code;
        if (!dtc_from_string(d["code"], code)) continue;
        if (out.dtc_count >= MAX_DTCS) break;
        const char* state = d["state"] | "pending";
        out.dtcs[out.dtc_count++] = {
            code,
            std::strcmp(state, "confirmed") == 0 ? DtcState::Confirmed
                                                 : DtcState::Pending
        };
    }
    return true;
}

size_t scenario_to_json(const Scenario& sc, char* buf, size_t buf_size) {
    JsonDocument doc;
    doc["name"]    = sc.name;
    doc["profile"] = profile_to_string(sc.profile);
    doc["vin"]     = sc.vin[0] ? sc.vin : OBD_VIN;

    JsonObject sensors = doc["sensors"].to<JsonObject>();
    for (uint8_t i = 0; i < sc.sensor_count; ++i) {
        for (const auto& m : SENSOR_META) {
            if (m.pid != sc.sensors[i].pid) continue;
            sensors[m.key] = sc.sensors[i].value;
            break;
        }
    }

    bool mil = false;
    JsonArray dtcs = doc["dtcs"].to<JsonArray>();
    for (uint8_t i = 0; i < sc.dtc_count; ++i) {
        char code[6];
        dtc_to_string(sc.dtcs[i].code, code);
        JsonObject d = dtcs.add<JsonObject>();
        d["code"]  = code;
        d["state"] = (sc.dtcs[i].state == DtcState::Confirmed) ? "confirmed"
                                                               : "pending";
        if (sc.dtcs[i].state == DtcState::Confirmed) mil = true;
    }
    doc["mil_on"] = mil;

    return serializeJsonPretty(doc, buf, buf_size);
}
