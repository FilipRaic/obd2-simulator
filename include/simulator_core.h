// simulator_core.h
#pragma once
#include "dtc_bank.h"
#include <cstdint>

// Simulation profiles:
//   Manual - the user sets every value through the UI,
//   Idle   - RPM oscillates around 800 rpm, coolant warms up to 90 °C,
//   Drive  - a driving cycle where speed, RPM, load and air flow are
//            physically coupled.
enum class SimProfile : uint8_t {
    Manual = 0,
    Idle   = 1,
    Drive  = 2,
};

void       simulator_set_profile(SimProfile p);
SimProfile simulator_get_profile();

// Bind the DTC bank so the model can accumulate PID 0x21
// (distance traveled with MIL on). Optional.
void simulator_bind_dtc_bank(const DtcBank* bank);

// Call from the main loop, internally rate-limited to a 100 ms tick.
void simulator_update();
