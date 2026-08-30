// can_task.cpp
// High-priority CAN task and the platform hooks the
// protocol core declares in iso_tp.h. The task exclusively owns the mutable
// simulator state (SENSOR_TABLE, DtcBank, profile), and the UI task interacts
// through the app::Command queue and the republished app::Snapshot.
#include "can_task.h"
#include "can_driver.h"
#include "app/app_types.h"
#include "storage/storage.h"
#include "hal/spi_bus.h"
#include "board_config.h"

#include "can_handler.h"
#include "simulator_core.h"
#include "sensor_table.h"
#include "dtc_bank.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/queue.h>
#include <cstring>

// ── Task-owned state ─────────────────────────────────────────────────────────
static CanDriver         s_can;
static DtcBank           s_bank;
static bool              s_can_ok = false;
static SemaphoreHandle_t s_rx_sem;
static SemaphoreHandle_t s_snap_mutex;
static QueueHandle_t     s_cmd_queue;
static app::Snapshot     s_snapshot;
static uint32_t          s_rx_count = 0;
static uint32_t          s_tx_count = 0;
static char              s_scenario_name[app::SCENARIO_NAME_MAX] = "Factory defaults";
static char              s_vin[18];
static float             s_default_values[SENSOR_COUNT];

// ── MCP2515 interrupt: minimal by design ─────────────────────────────────────
static void IRAM_ATTR can_isr(void*) {
    BaseType_t woken = pdFALSE;
    xSemaphoreGiveFromISR(s_rx_sem, &woken);
    portYIELD_FROM_ISR(woken);
}

// ── Platform hooks required by the protocol core (iso_tp.h) ──────────────────

void can_send_frame(const CanFrame& frame) {
    if (s_can_ok && s_can.send(frame)) ++s_tx_count;
}

// Called by iso_tp_send between the First Frame and the Consecutive Frames.
// It runs in CAN-task context, so it polls the controller directly. N_Bs
// timeout per ISO 15765-2 is 1 s. Non-FC frames arriving during the wait
// are dropped - standard testers do not pipeline requests mid-transfer.
bool iso_tp_wait_flow_control(FlowControl& fc) {
    const TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(1000);
    for (;;) {
        TickType_t now = xTaskGetTickCount();
        if (now >= deadline) return false;
        xSemaphoreTake(s_rx_sem, deadline - now);
        CanFrame f;
        while (s_can_ok && s_can.receive(f)) {
            ++s_rx_count;
            if (f.id == OBD_PHYSICAL_ID && (f.data[0] & 0xF0) == 0x30) {
                fc.flow_status = f.data[0] & 0x0F;
                fc.block_size  = f.data[1];
                fc.st_min_us   = iso_tp_decode_stmin_us(f.data[2]);
                return true;
            }
        }
    }
}

void iso_tp_delay_us(uint32_t us) {
    if (us) delayMicroseconds(us);
}

// ── Scenario application (CAN-task context) ──────────────────────────────────

static void set_sensor_clamped(uint8_t pid, float v) {
    SensorEntry* s = find_sensor(pid);
    if (!s) return;
    if (v < s->min_val) v = s->min_val;
    if (v > s->max_val) v = s->max_val;
    s->value = v;
}

static void apply_scenario(const Scenario& sc) {
    simulator_set_profile(sc.profile);  // also resets the drive-cycle clock

    // Sensor values first, DTCs second, so a confirmed DTC's freeze frame
    // snapshots the scenario values.
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        SENSOR_TABLE[i].value = s_default_values[i];
    for (uint8_t i = 0; i < sc.sensor_count; ++i)
        set_sensor_clamped(sc.sensors[i].pid, sc.sensors[i].value);

    s_bank.clear_all();
    for (uint8_t i = 0; i < sc.dtc_count; ++i)
        s_bank.add(sc.dtcs[i].code, sc.dtcs[i].state);

    std::strncpy(s_scenario_name, sc.name, sizeof(s_scenario_name) - 1);
    s_scenario_name[sizeof(s_scenario_name) - 1] = '\0';
    std::strncpy(s_vin, sc.vin[0] ? sc.vin : OBD_VIN, sizeof(s_vin) - 1);
    s_vin[sizeof(s_vin) - 1] = '\0';
    // Hand it to the protocol core, otherwise mode 0x09 keeps answering with
    // the factory VIN while the home screen shows the scenario's. That was the
    // state until 09.08.2026.: the value was parsed, stored, published and
    // displayed, and the one place that had to see it never did.
    obd_set_vin(s_vin);
}

static void build_scenario_from_state(Scenario& out, const char* name) {
    out = Scenario{};
    std::strncpy(out.name, name, sizeof(out.name) - 1);
    std::strncpy(out.vin, s_vin, sizeof(out.vin) - 1);
    out.profile = simulator_get_profile();
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        out.sensors[out.sensor_count++] = { SENSOR_TABLE[i].pid,
                                            SENSOR_TABLE[i].value };
    for (uint8_t i = 0; i < s_bank.count && out.dtc_count < MAX_DTCS; ++i)
        out.dtcs[out.dtc_count++] = { s_bank.dtcs[i].code,
                                      s_bank.dtcs[i].state };
}

// ── Command handling (UI task -> CAN task) ───────────────────────────────────

static void handle_command(const app::Command& cmd) {
    Scenario sc;
    switch (cmd.type) {
    case app::CmdType::SetProfile:
        simulator_set_profile(cmd.profile);
        break;
    case app::CmdType::SetSensorValue:
        set_sensor_clamped(cmd.pid, cmd.value);
        break;
    case app::CmdType::DtcAddPending:
        s_bank.add(cmd.dtc_code, DtcState::Pending);
        break;
    case app::CmdType::DtcConfirm:
        s_bank.confirm(cmd.dtc_code);
        break;
    case app::CmdType::DtcSetState:
        if (cmd.dtc_state == app::DtcUiState::Inactive)
            s_bank.remove(cmd.dtc_code);
        else
            s_bank.set_state(cmd.dtc_code,
                             cmd.dtc_state == app::DtcUiState::Confirmed
                                 ? DtcState::Confirmed : DtcState::Pending);
        break;
    case app::CmdType::DtcClearAll:
        s_bank.clear_all();   // same effect as service 0x04
        break;
    case app::CmdType::LoadScenario:
        if (storage::load(cmd.name, sc)) apply_scenario(sc);
        break;
    case app::CmdType::SaveScenario:
        build_scenario_from_state(sc, cmd.name);
        if (storage::save(sc, cmd.name)) {
            std::strncpy(s_scenario_name, cmd.name,
                         sizeof(s_scenario_name) - 1);
        }
        break;
    case app::CmdType::FactoryReset:
        storage::factory(sc);
        apply_scenario(sc);
        break;
    }
}

// ── Snapshot publication ─────────────────────────────────────────────────────

static void publish_snapshot() {
    xSemaphoreTake(s_snap_mutex, portMAX_DELAY);
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        s_snapshot.values[i] = SENSOR_TABLE[i].value;
    s_snapshot.profile         = simulator_get_profile();
    s_snapshot.mil             = s_bank.mil_on();
    s_snapshot.can_ok          = s_can_ok;
    s_snapshot.fs_ok           = storage::available();
    s_snapshot.confirmed_count = s_bank.confirmed_count();
    s_snapshot.pending_count   = s_bank.pending_count();
    for (uint8_t c = 0; c < app::CATALOG_SIZE; ++c) {
        s_snapshot.catalog_state[c] = app::DtcUiState::Inactive;
        for (uint8_t i = 0; i < s_bank.count; ++i) {
            if (s_bank.dtcs[i].code != DTC_CATALOG[c].code) continue;
            s_snapshot.catalog_state[c] =
                (s_bank.dtcs[i].state == DtcState::Confirmed)
                    ? app::DtcUiState::Confirmed
                    : app::DtcUiState::Pending;
            break;
        }
    }
    s_snapshot.rx_frames = s_rx_count;
    s_snapshot.tx_frames = s_tx_count;
    std::memcpy(s_snapshot.scenario_name, s_scenario_name,
                sizeof(s_snapshot.scenario_name));
    std::memcpy(s_snapshot.vin, s_vin, sizeof(s_snapshot.vin));
    xSemaphoreGive(s_snap_mutex);
}

namespace app {

bool send_command(const Command& cmd) {
    return xQueueSend(s_cmd_queue, &cmd, 0) == pdTRUE;
}

void get_snapshot(Snapshot& out) {
    xSemaphoreTake(s_snap_mutex, portMAX_DELAY);
    out = s_snapshot;
    xSemaphoreGive(s_snap_mutex);
}

} // namespace app

// ── Task body ────────────────────────────────────────────────────────────────

static void can_task(void*) {
    Serial.printf("[can] task entered, stack headroom %u B\n",
                  uxTaskGetStackHighWaterMark(nullptr));
    uint32_t iter = 0;
    for (;;) {
        const bool trace = (iter < 3);
        if (trace) Serial.printf("[can] it%u wait\n", iter);
        Serial.flush();

        // Wake on RX interrupt, or every 10 ms to run the simulator tick
        // (simulator_update() rate-limits itself to 10 Hz internally).
        xSemaphoreTake(s_rx_sem, pdMS_TO_TICKS(10));
        if (trace) Serial.printf("[can] it%u woke\n", iter);
        Serial.flush();

        CanFrame frame;
        while (s_can_ok && s_can.receive(frame)) {
            ++s_rx_count;
            process_obd_request(frame, s_bank);
        }
        if (trace) Serial.printf("[can] it%u rx done\n", iter);
        Serial.flush();

        app::Command cmd;
        while (xQueueReceive(s_cmd_queue, &cmd, 0) == pdTRUE)
            handle_command(cmd);
        if (trace) Serial.printf("[can] it%u cmds done\n", iter);
        Serial.flush();

        simulator_update();
        if (trace) Serial.printf("[can] it%u sim done\n", iter);
        Serial.flush();
        publish_snapshot();
        if (trace) Serial.printf("[can] it%u snap done, stack %u B\n",
                                 iter, uxTaskGetStackHighWaterMark(nullptr));
        ++iter;
    }
}

void can_task_start() {
    s_rx_sem     = xSemaphoreCreateBinary();
    s_snap_mutex = xSemaphoreCreateMutex();
    s_cmd_queue  = xQueueCreate(8, sizeof(app::Command));

    // Snapshot factory sensor defaults before any scenario touches them.
    for (uint8_t i = 0; i < SENSOR_COUNT; ++i)
        s_default_values[i] = SENSOR_TABLE[i].value;
    std::strncpy(s_vin, OBD_VIN, sizeof(s_vin) - 1);

    s_can_ok = s_can.begin(PIN_CS_CAN);
    Serial.printf("[can] MCP2515 %s\n",
                  s_can_ok ? "initialised (500 kbit/s)" : "NOT RESPONDING");
    pinMode(PIN_INT_CAN, INPUT_PULLUP);
    attachInterruptArg(digitalPinToInterrupt(PIN_INT_CAN), can_isr,
                       nullptr, FALLING);
    Serial.println("[can] INT attached");
    Serial.flush();

    Scenario sc;
    storage::load_startup(sc);
    Serial.printf("[can] scenario loaded: %s\n", sc.name);
    Serial.flush();
    apply_scenario(sc);
    simulator_bind_dtc_bank(&s_bank);   // PID 0x21 distance-with-MIL
    publish_snapshot();
    Serial.println("[can] snapshot published");
    Serial.flush();

    // High priority, pinned to core 1: guarantees the ISO 15765-4 response
    // deadline regardless of UI rendering.
    xTaskCreatePinnedToCore(can_task, "can", 8192, nullptr, 5, nullptr, 1);
}
