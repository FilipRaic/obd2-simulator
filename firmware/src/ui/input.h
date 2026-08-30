// input.h
// Physical-control input for UI v0.4. Navigation comes from the
// on-board Alps SKRHABE010 5-way switch (v0.7, replaced the analog stick):
// each axis is read as one ADC level ladder on the old JOY_X/JOY_Y nets -
// idle ~3,3 V, one direction grounds the net through 10 k (~1,96 V), the
// opposite direction grounds it directly (0 V). Centre push and CONFIRM =
// The control model (v0.8):
//   joystick axes      -> Up/Down/Left/Right, navigation only
//   joystick centre    -> Select: enter a submenu, or start editing a value
//   encoder rotation   -> DialStep: change the value being edited
//   encoder push       -> WIRED ON THE BOARD BUT DELIBERATELY UNUSED here
//   SW1 CONFIRM        -> Ok: commit and store the edited value
//   SW2 CLEAR          -> Clear: discard the edit or the entry
//   SW3 RETURN         -> Back: leave the submenu
// Since board v0.8 the value dial is an
// EN11 incremental encoder instead of a potentiometer, so it emits RELATIVE
// steps (InputKind::DialStep) rather than an absolute position: an encoder
// turns endlessly and has no position to report. Everything is normalized into
// InputEvent so screen logic does not depend on the input source.
#pragma once
#include <cstdint>

enum class InputKind : uint8_t {
    None, Up, Down, Left, Right, Select, Ok, Back, Clear, DialStep
};

struct InputEvent {
    InputKind kind    = InputKind::None;
    // DialStep only: signed step as a fraction of the full sensor range,
    // e.g. +0.0039 for one detent at the fine rate.
    float     value01 = 0.0f;
};

class InputReader {
public:
    void begin();

    // Call every ~10 ms, returns one queued event per call.
    bool poll(InputEvent& out);

private:
    static constexpr uint8_t QUEUE_SIZE = 8;

    struct Button {
        int       pin;
        InputKind kind;
        bool      stable_high;
        bool      last_raw;
        uint32_t  last_change_ms;
    };

    struct Axis {
        int       pin;
        InputKind ladder;     // contact behind the 10 k ladder (~1,96 V)
        InputKind direct;     // contact straight to GND (0 V)
        int8_t    stable_level;    // -1 idle, 0 direct, 1 ladder
        int8_t    last_raw_level;
        uint32_t  last_change_ms;
        uint32_t  next_repeat_ms;
    };

    void pushEvent(InputKind kind, float value01 = 0.0f);
    void sampleButtons(uint32_t now);
    void sampleAxis(Axis& axis, uint32_t now);
    void sampleCentre(uint32_t now);
    void sampleEncoder(uint32_t now);

    Button     buttons_[3];
    // SW6's centre. Not in buttons_ because on the assembled board its pin is
    // also the switch's common and has to be driven, not just read. See
    // sampleCentre() in input.cpp.
    Button     centre_;
    Axis       axis_x_, axis_y_;
    uint32_t   enc_last_step_ms_ = 0;
    InputEvent queue_[QUEUE_SIZE];
    uint8_t    q_head_ = 0, q_count_ = 0;
};

#if defined(BRINGUP_DIAG)
// Print the RAW state of every control, twice a second, for bring-up.
//
// The SKRHABE010 thresholds (LEVEL_DIRECT_MAX, LEVEL_LADDER_MAX in input.cpp)
// are nominal values worked out from the schematic: idle ~4095, the 10 k
// ladder ~2430, a direct contact ~0. On the assembled board the axes did
// nothing at all, and the honest way to find out why is to read the numbers
// off the pins rather than to nudge the thresholds and hope. Prints the ADC
// reading and the level each axis is being classified into, plus the level of
// every button and both encoder channels.
void input_debug_dump();
#endif
