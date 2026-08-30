// simulator_core.cpp
// Sensor simulation model: the sensor table is
// updated on a 100 ms tick so readings on the diagnostic tool look
// plausible. Three profiles are implemented: Manual (values set from
// the UI), Idle (RPM around 800 rpm, first-order coolant warm-up) and
// Drive (piecewise driving cycle with coupled speed/RPM/load/air flow).

#include "simulator_core.h"
#include "sensor_table.h"
#include "obd2_pids.h"
#include <cstdlib>   // rand()

// ── Platform tick (implement: return ms since boot) ─────────────────────────
extern uint32_t millis();

// ── Simulation state ─────────────────────────────────────────────────────────
static SimProfile     g_profile        = SimProfile::Idle;
static const DtcBank* g_bank           = nullptr;
static uint32_t       g_last_update_ms = 0;
static uint32_t       g_runtime_ms     = 0;   // ms accumulator for PID 0x1F
static float          g_mil_distance_m = 0;   // metres, for PID 0x21
static float          g_cycle_time_s   = 0;   // position inside drive cycle

// ── Simple uniform noise in [-amplitude, +amplitude] ────────────────────────
static float rand_noise(float amplitude) {
    if (amplitude == 0.0f) return 0.0f;
    float r = (float)(rand() % 2001 - 1000) / 1000.0f; // -1.0 .. +1.0
    return r * amplitude;
}

static void set_value(uint8_t pid, float v) {
    if (SensorEntry* s = find_sensor(pid)) {
        if (v < s->min_val) v = s->min_val;
        if (v > s->max_val) v = s->max_val;
        s->value = v;
    }
}

static float get_value(uint8_t pid, float fallback = 0.0f) {
    SensorEntry* s = find_sensor(pid);
    return s ? s->value : fallback;
}

// ── Drive cycle: 0→90 km/h in 30 s, cruise 60 s, brake to 0 in 20 s, idle 20 s
static constexpr float CYCLE_ACCEL_END  = 30.0f;
static constexpr float CYCLE_CRUISE_END = 90.0f;
static constexpr float CYCLE_BRAKE_END  = 110.0f;
static constexpr float CYCLE_TOTAL      = 130.0f;
static constexpr float CYCLE_TOP_SPEED  = 90.0f;   // km/h

// accel_out: -1 (braking) .. +1 (full segment acceleration)
static float drive_cycle_speed(float t, float& accel_out) {
    if (t < CYCLE_ACCEL_END) {                       // acceleration
        accel_out = 1.0f;
        return CYCLE_TOP_SPEED * (t / CYCLE_ACCEL_END);
    }
    if (t < CYCLE_CRUISE_END) {                      // cruise
        accel_out = 0.0f;
        return CYCLE_TOP_SPEED;
    }
    if (t < CYCLE_BRAKE_END) {                       // braking
        accel_out = -1.0f;
        return CYCLE_TOP_SPEED *
               (1.0f - (t - CYCLE_CRUISE_END) / (CYCLE_BRAKE_END - CYCLE_CRUISE_END));
    }
    accel_out = 0.0f;                                // idle pause
    return 0.0f;
}

// Simple gearbox: RPM derived from speed through per-gear ratios,
// never below idle speed.
static float rpm_from_speed(float speed_kmh) {
    float ratio;                    // rpm per km/h
    if      (speed_kmh < 20.0f) ratio = 120.0f;   // 1st gear
    else if (speed_kmh < 40.0f) ratio = 70.0f;    // 2nd gear
    else if (speed_kmh < 60.0f) ratio = 50.0f;    // 3rd gear
    else if (speed_kmh < 80.0f) ratio = 38.0f;    // 4th gear
    else                        ratio = 30.0f;    // 5th gear
    float rpm = speed_kmh * ratio;
    return rpm < 800.0f ? 800.0f : rpm;
}

// ── Profile updates (dt in seconds) ──────────────────────────────────────────
static void tick_idle(float dt) {
    set_value(PID_ENGINE_RPM,    800.0f + rand_noise(25.0f));
    set_value(PID_VEHICLE_SPEED, 0.0f);
    set_value(PID_THROTTLE_POS,  15.0f + rand_noise(0.5f));
    set_value(PID_ENGINE_LOAD,   25.0f + rand_noise(1.0f));
    set_value(PID_INTAKE_MAP,    34.0f + rand_noise(1.0f));
    set_value(PID_MAF_FLOW,       3.1f + rand_noise(0.1f));
    (void)dt;
}

static void tick_drive(float dt) {
    g_cycle_time_s += dt;
    if (g_cycle_time_s >= CYCLE_TOTAL) g_cycle_time_s -= CYCLE_TOTAL;

    float accel = 0.0f;
    float speed = drive_cycle_speed(g_cycle_time_s, accel);
    float rpm   = rpm_from_speed(speed);

    // Load and throttle follow the demanded acceleration.
    float load     = (accel > 0.0f) ? 70.0f : (speed > 1.0f ? 40.0f : 25.0f);
    float throttle = (accel > 0.0f) ? 55.0f : (speed > 1.0f ? 25.0f : 15.0f);

    set_value(PID_VEHICLE_SPEED, speed);
    set_value(PID_ENGINE_RPM,    rpm + rand_noise(25.0f));
    set_value(PID_ENGINE_LOAD,   load + rand_noise(2.0f));
    set_value(PID_THROTTLE_POS,  throttle + rand_noise(1.0f));
    set_value(PID_INTAKE_MAP,    30.0f + load * 0.9f);

    // Idealised volumetric model: air flow follows RPM and load.
    constexpr float DISPLACEMENT_L = 1.6f;
    constexpr float MAF_GAIN       = 0.00035f;   // tuned for g/s range
    set_value(PID_MAF_FLOW, rpm * DISPLACEMENT_L * load * MAF_GAIN);
}

// ── Public API ───────────────────────────────────────────────────────────────
void simulator_set_profile(SimProfile p) {
    g_profile      = p;
    g_cycle_time_s = 0.0f;
}

SimProfile simulator_get_profile() { return g_profile; }

void simulator_bind_dtc_bank(const DtcBank* bank) { g_bank = bank; }

void simulator_update() {
    uint32_t now = millis();
    if (g_last_update_ms == 0) g_last_update_ms = now;    // first call
    uint32_t dt_ms = now - g_last_update_ms;
    if (dt_ms < 100) return;                              // 10 Hz update rate
    g_last_update_ms = now;
    const float dt = dt_ms / 1000.0f;

    // Runtime counter (PID 0x1F): millisecond accumulator, so short
    // ticks are never lost to integer division.
    g_runtime_ms += dt_ms;
    set_value(PID_RUNTIME, (float)(g_runtime_ms / 1000u));

    switch (g_profile) {
    case SimProfile::Idle:   tick_idle(dt);  break;
    case SimProfile::Drive:  tick_drive(dt); break;
    case SimProfile::Manual: break;          // values set from the UI
    }

    if (g_profile != SimProfile::Manual) {
        // Coolant and oil warm up towards operating temperature with a
        // first-order response (time constant 180 s).
        float coolant = get_value(PID_COOLANT_TEMP);
        set_value(PID_COOLANT_TEMP, coolant + (90.0f - coolant) * (dt / 180.0f));
        float oil = get_value(PID_ENGINE_OIL_TEMP);
        set_value(PID_ENGINE_OIL_TEMP, oil + (95.0f - oil) * (dt / 180.0f));

        // Low-amplitude noise on the remaining "live" sensors.
        set_value(PID_O2_BANK1_SENSOR1,
                  get_value(PID_O2_BANK1_SENSOR1) + rand_noise(0.02f));
        set_value(PID_CONTROL_MODULE_VOLTAGE,
                  13.8f + rand_noise(0.05f));
        set_value(PID_TIMING_ADVANCE, 10.0f + rand_noise(0.2f));
    }

    // Distance traveled with MIL on (PID 0x21).
    if (g_bank && g_bank->mil_on()) {
        g_mil_distance_m += get_value(PID_VEHICLE_SPEED) / 3.6f * dt;
        set_value(PID_DISTANCE_MIL_ON, g_mil_distance_m / 1000.0f);
    }
}
