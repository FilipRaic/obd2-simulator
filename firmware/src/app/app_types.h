// app_types.h
// Application-layer contracts between the two FreeRTOS tasks:
// the UI task mutates simulator state only through Command messages, and
// reads it only through the Snapshot the CAN task republishes every tick.
#pragma once
#include "simulator_core.h"
#include "sensor_table.h"
#include "dtc_bank.h"
#include <cstdint>

namespace app {

constexpr uint8_t CATALOG_SIZE      = static_cast<uint8_t>(DTC_CATALOG.size());
constexpr uint8_t SCENARIO_NAME_MAX = 32;

// Per-catalog-entry state as shown on the DTC screen.
enum class DtcUiState : uint8_t { Inactive = 0, Pending = 1, Confirmed = 2 };

enum class CmdType : uint8_t {
    SetProfile,      // profile
    SetSensorValue,  // pid, value (Manual profile editing)
    DtcAddPending,   // dtc_code
    DtcConfirm,      // dtc_code (promotes pending -> confirmed, MIL on)
    // dtc_code + dtc_state: put one code straight into a target state,
    // including back to Inactive. The UI walks a code up and down the
    // scale, which the OBD services themselves never do.
    DtcSetState,
    DtcClearAll,     // same effect as service 0x04
    LoadScenario,    // name (file in /scenarios, without extension)
    SaveScenario,    // name
    FactoryReset,    // load factory scenario (W25Q128 slot or built-in)
};

struct Command {
    CmdType    type;
    SimProfile profile;
    uint8_t    pid;
    float      value;
    uint16_t   dtc_code;
    DtcUiState dtc_state;   // DtcSetState only
    char       name[SCENARIO_NAME_MAX];
};

// Read-only view of the simulation state for the UI task.
struct Snapshot {
    float      values[SENSOR_COUNT];
    SimProfile profile;
    bool       mil;
    bool       can_ok;                 // MCP2515 initialised
    bool       fs_ok;                  // flash filesystem mounted (W25Q128)
    uint8_t    confirmed_count;
    uint8_t    pending_count;
    DtcUiState catalog_state[CATALOG_SIZE];
    uint32_t   rx_frames;
    uint32_t   tx_frames;
    char       scenario_name[SCENARIO_NAME_MAX];
    char       vin[18];
};

// Implemented by the CAN task module (can_task.cpp).
bool send_command(const Command& cmd);   // false if the queue is full
void get_snapshot(Snapshot& out);

} // namespace app
