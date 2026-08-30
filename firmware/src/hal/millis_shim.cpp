// millis_shim.cpp
// The protocol core declares `extern uint32_t millis();` with C++ linkage
// (simulator_core.cpp), while Arduino's millis() is extern "C" unsigned long
// - a different symbol. This translation unit deliberately does not include
// Arduino.h so it can define the C++-mangled variant the core links against.
#include <cstdint>

extern "C" int64_t esp_timer_get_time(void);  // microseconds since boot

uint32_t millis() {
    return static_cast<uint32_t>(esp_timer_get_time() / 1000);
}
