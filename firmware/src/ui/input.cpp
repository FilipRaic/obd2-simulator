// input.cpp
#include "input.h"
#include "board_config.h"
#include <Arduino.h>
#include <soc/gpio_reg.h>

// 12-bit ADC geometry (still used by the SKRHABE010 axis ladder)
static constexpr int ADC_MAX = 4095;

// ── Incremental encoder ENC1 (EN11-HSB1AQ20, board v0.8) ────────────────────
// The RK12L12 potentiometer was an ABSOLUTE dial: its shaft position was the
// value. An encoder cannot do that - it turns endlessly and only reports
// "one detent clockwise" or "one detent anticlockwise". The dial is therefore
// relative: each detent nudges the value being edited, starting from whatever
// it already is. That also removes the jump the potentiometer produced, where
// the value snapped to the shaft position on the first movement.
//
// Decoding runs in an interrupt, not in poll(). The UI task polls every 10 ms,
// while a brisk spin of 5 turns per second on a 20 detent encoder produces a
// detent every 10 ms, so polling would drop steps. The ISR triggers on the
// falling edge of A and reads B to get the direction, which yields exactly one
// count per detent on this encoder family.
//
// Resolution: 20 detents per turn is coarse for wide-range sensors (engine
// speed goes to 16383 min-1), so the step size follows how fast the knob is
// turned. Slow gives fine control, a quick spin crosses the whole range in
// about one turn.
static constexpr uint32_t ENC_FAST_MS   = 50;    // below this: coarse steps
static constexpr uint32_t ENC_MEDIUM_MS = 150;   // below this: medium steps
static constexpr float    ENC_STEP_FINE   = 1.0f / 256.0f;
static constexpr float    ENC_STEP_MEDIUM = 1.0f / 64.0f;
static constexpr float    ENC_STEP_COARSE = 1.0f / 16.0f;
// Contact bounce on a mechanical encoder is a few ms; anything faster than
// this on the same edge is bounce, not a detent.
static constexpr uint32_t ENC_BOUNCE_US = 1500;

static volatile int32_t  enc_counter_ = 0;
static volatile uint32_t enc_last_isr_us_ = 0;

// digitalRead() is not guaranteed to sit in IRAM on the Arduino core, and this
// interrupt can fire while the internal flash is busy (the NVS write that arms
// USB mass-storage boot mode, for one), which would crash. The level is
// therefore read straight from the GPIO input register, which needs no flash.
static inline bool IRAM_ATTR enc_read_b() {
    static_assert(PIN_ENC_B >= 32, "ENC_B must be a pin covered by GPIO_IN1_REG");
    return (REG_READ(GPIO_IN1_REG) >> (PIN_ENC_B - 32)) & 1u;
}

static void IRAM_ATTR enc_isr() {
    uint32_t now = micros();
    if (now - enc_last_isr_us_ < ENC_BOUNCE_US) return;
    enc_last_isr_us_ = now;
    // A has just fallen: B still high means one direction, low the other.
    //
    // Which of the two is clockwise depends on how the encoder sits on the
    // board, so it is a thing to measure, not to reason about. Measured on the
    // assembled v0.7 board on 21.08.2026.: with `if (enc_read_b()) ++` a
    // clockwise turn made the value go DOWN, so the two signs are swapped
    // here. Clockwise is now positive, which is what a user expects.
    if (enc_read_b()) --enc_counter_;
    else              ++enc_counter_;
}

// SKRHABE010 axis ladder (v0.7, board R26-R29): 6k8 pull-up to 3,3 V, one
// direction grounds the net through 10 k, the other directly. Nominal ADC
// readings: idle ~4095, ladder 3,3*10/16,8 = 1,96 V ~ 2430, direct ~0.
// The thresholds sit between the bands with wide margins; adjust after
// measuring the real board (XX_pending) only if the part deviates.
static constexpr int LEVEL_DIRECT_MAX = 900;   // below: direct contact closed
static constexpr int LEVEL_LADDER_MAX = 3300;  // below: ladder contact closed

// ── Board v0.7 defect: SW6's common is on GPIO5, not on ground ──────────────
// Measured on the assembled board, 21.08.2026. The footprint's pin numbering
// does not match the real SKRHABE010. What the netlist calls pad 2 = JOY_SW is
// in fact the switch's COMMON terminal, and the centre push sits on one of the
// pads the board ties to ground.
//
// What that produces, and every symptom matched before the cause was found:
//   - the four directions close COMMON to JOY_X / JOY_XB / JOY_Y / JOY_YB.
//     COMMON is JOY_SW, which R9 (10 k) holds at 3,3 V, so a direction ties
//     one pulled-up net to another pulled-up net. Nothing moves. Both axes sat
//     at 3159 mV through all 64 samples of the diagnostic dump, never leaving
//     the idle band by a single bit.
//   - the centre push closes COMMON to a grounded pad, so JOY_SW does go low
//     and the firmware reports Select. The centre "worked" by accident, for a
//     completely different reason than the design intended.
//
// The fix needs no rework, because that common lands on a GPIO the firmware
// can drive. Hold GPIO5 LOW and the common becomes the ground the design
// always assumed: a direction then pulls its axis net down exactly as drawn,
// through 0 ohm or through the 10 k ladder, and the thresholds above apply
// unchanged.
//
// The centre still has to be read, so the pin is briefly returned to
// INPUT_PULLUP - see sampleCentre(). Driving it high must NEVER happen: with
// the centre pressed that would be a short to ground.
//
// This is a BOARD defect, recorded for the next revision: SW6 pad 2 belongs on
// GND, and the centre push belongs on the GPIO.
static inline void joy_common_drive_low() {
    pinMode(PIN_JOY_SW, OUTPUT);
    digitalWrite(PIN_JOY_SW, LOW);
}
// No capacitor sits on any JOY_* net (only R9, R26-R29), so the line settles
// in well under a microsecond. This is generous on purpose.
static constexpr uint32_t COMMON_SETTLE_US = 300;
// A digital switch has no deflection, so the repeat rate is fixed.
static constexpr uint32_t REPEAT_MS      = 250;
static constexpr uint32_t DEBOUNCE_MS    = 20;

static void button_pin_mode(int pin) {
    // On the CLASSIC ESP32, pins 34-39 are input-only and have no internal
    // pull-up. The ESP32-S3 has no such restriction: 34-48 are ordinary GPIOs
    // with working pull-ups, and this board only ever uses the S3. The guard
    // stays only so the file remains readable on the classic part.
#if CONFIG_IDF_TARGET_ESP32
    if (pin >= 34 && pin <= 39) pinMode(pin, INPUT);
    else                        pinMode(pin, INPUT_PULLUP);
#else
    pinMode(pin, INPUT_PULLUP);
#endif
}

void InputReader::begin() {
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_JOY_X, ADC_11db);
    analogSetPinAttenuation(PIN_JOY_Y, ADC_11db);

    buttons_[0] = { PIN_BTN_CONFIRM, InputKind::Ok,    true, true, 0 };
    buttons_[1] = { PIN_BTN_CLEAR,   InputKind::Clear, true, true, 0 };
    buttons_[2] = { PIN_BTN_RETURN,  InputKind::Back,  true, true, 0 };
    centre_     = { PIN_JOY_SW,      InputKind::Select, true, true, 0 };
    // PIN_ENC_SW is intentionally NOT read. The encoder's push switch is wired
    // on the board (net ENC_SW to GPIO39) so it stays available for a later
    // function, but the current control model gives it no job: selecting is the
    // joystick centre and committing is SW1 CONFIRM. Leaving it unconfigured
    // also means it cannot emit anything by accident.
    //
    // Board v0.9b fits R34, R40, C33 and C36 on that line anyway, so it gets
    // the same filter as A and B. Those four parts are therefore stock for a
    // function that does not exist yet - worth knowing before anyone prunes
    // them from the BOM.
    for (auto& b : buttons_) button_pin_mode(b.pin);
    // Ground SW6's common. Everything the axes do depends on this.
    joy_common_drive_low();

    // Contact-to-direction mapping per the board wiring (SW6: A/C = direct,
    // B/D = ladder). Which physical direction closes which contact is
    // verified on the assembled board - swapping a pair here is the fix.
    //
    // BOARD v0.9b: the encoder is no longer three bare contacts. Each line now
    // carries 100 ohm in series at the contact (R38-R40), a 10 k pull-up and
    // 47 nF to ground (R32-R34, C31-C33) and 1 nF at the module pin
    // (C34-C36). The internal pull-ups below stay enabled on purpose: in
    // parallel with the external 10 k they give about 8,2 k, so the line rises
    // to the input threshold in roughly 530 us instead of 650 us, and the pin
    // is never left floating if a resistor is missing at assembly time.
    // The falling edge, which is the one the ISR triggers on, is unaffected -
    // closing the contact discharges the capacitor through those 100 ohm.
    pinMode(PIN_ENC_A, INPUT_PULLUP);
    pinMode(PIN_ENC_B, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_A), enc_isr, FALLING);

    axis_y_ = { PIN_JOY_Y, InputKind::Up,    InputKind::Down, -1, -1, 0, 0 };
    axis_x_ = { PIN_JOY_X, InputKind::Right, InputKind::Left, -1, -1, 0, 0 };
}

void InputReader::pushEvent(InputKind kind, float value01) {
    if (q_count_ >= QUEUE_SIZE) return;   // overflow: drop, UI catches up
    queue_[(q_head_ + q_count_) % QUEUE_SIZE] = { kind, value01 };
    ++q_count_;
}

void InputReader::sampleButtons(uint32_t now) {
    for (auto& b : buttons_) {
        bool raw = digitalRead(b.pin) == HIGH;
        if (raw != b.last_raw) {
            b.last_raw       = raw;
            b.last_change_ms = now;
            continue;
        }
        if (raw != b.stable_high && now - b.last_change_ms >= DEBOUNCE_MS) {
            b.stable_high = raw;
            if (!raw) pushEvent(b.kind);   // active low: event on press
        }
    }
}

// Read SW6's centre, which shares its pin with the switch's common.
//
// The pin is let go to INPUT_PULLUP just long enough for one read, then put
// straight back to driving low. During that window:
//   - centre pressed  -> common meets a grounded pad, the pin reads LOW,
//   - direction held  -> common meets an axis net, which its own pull-up holds
//                        at 3,3 V, so the pin reads HIGH and there is no false
//                        centre press,
//   - nothing pressed -> R9 holds it HIGH.
// The axes are sampled elsewhere in the same poll, while the common is low
// again, so they never see this window.
void InputReader::sampleCentre(uint32_t now) {
    pinMode(PIN_JOY_SW, INPUT_PULLUP);
    delayMicroseconds(COMMON_SETTLE_US);
    const bool raw = digitalRead(PIN_JOY_SW) == HIGH;
    joy_common_drive_low();

    Button& b = centre_;
    if (raw != b.last_raw) {
        b.last_raw       = raw;
        b.last_change_ms = now;
        return;
    }
    if (raw != b.stable_high && now - b.last_change_ms >= DEBOUNCE_MS) {
        b.stable_high = raw;
        if (!raw) pushEvent(b.kind);   // active low: event on press
    }
}

void InputReader::sampleAxis(Axis& axis, uint32_t now) {
    int raw = analogRead(axis.pin);
    int8_t level = (raw < LEVEL_DIRECT_MAX) ? 0
                 : (raw < LEVEL_LADDER_MAX) ? 1
                 : -1;

    // Debounce like the buttons: a closing contact sweeps the ADC through
    // the ladder band for a moment, so a level only counts once it has been
    // read stable for DEBOUNCE_MS.
    if (level != axis.last_raw_level) {
        axis.last_raw_level = level;
        axis.last_change_ms = now;
        return;
    }
    if (now - axis.last_change_ms < DEBOUNCE_MS) return;

    if (level != axis.stable_level) {
        axis.stable_level = level;
        if (level >= 0) {                 // press: first event immediately
            axis.next_repeat_ms = now + REPEAT_MS;
            pushEvent(level == 1 ? axis.ladder : axis.direct);
        }
        return;
    }
    if (level < 0) return;                // idle
    if (static_cast<int32_t>(now - axis.next_repeat_ms) < 0) return;
    axis.next_repeat_ms = now + REPEAT_MS;
    pushEvent(level == 1 ? axis.ladder : axis.direct);
}

void InputReader::sampleEncoder(uint32_t now) {
    noInterrupts();
    int32_t steps = enc_counter_;
    enc_counter_  = 0;
    interrupts();
    if (steps == 0) return;

    uint32_t gap = now - enc_last_step_ms_;
    enc_last_step_ms_ = now;
    float step = (gap < ENC_FAST_MS)   ? ENC_STEP_COARSE
               : (gap < ENC_MEDIUM_MS) ? ENC_STEP_MEDIUM
                                       : ENC_STEP_FINE;
    pushEvent(InputKind::DialStep, static_cast<float>(steps) * step);
}

#if defined(BRINGUP_DIAG)
void input_debug_dump() {
    static uint32_t last_ms = 0;
    uint32_t now = ::millis();
    if (now - last_ms < 500) return;
    last_ms = now;

    // Axes while the common is held low, which is its normal state.
    const int rx = analogRead(PIN_JOY_X);
    const int ry = analogRead(PIN_JOY_Y);
    const int mvx = (int)analogReadMilliVolts(PIN_JOY_X);
    const int mvy = (int)analogReadMilliVolts(PIN_JOY_Y);
    // The centre needs the pin released, exactly as sampleCentre() does it.
    pinMode(PIN_JOY_SW, INPUT_PULLUP);
    delayMicroseconds(COMMON_SETTLE_US);
    const int centre = digitalRead(PIN_JOY_SW);
    joy_common_drive_low();
    auto level = [](int raw) {
        return (raw < LEVEL_DIRECT_MAX) ? 0 : (raw < LEVEL_LADDER_MAX) ? 1 : -1;
    };
    // Millivolts as well as counts: the thresholds were derived from a divider
    // in volts, so volts are what makes a mismatch obvious.
    Serial.printf("[in] X=%4d (%4dmV lvl %2d)  Y=%4d (%4dmV lvl %2d)  "
                  "CONF=%d SEL=%d CLR=%d RET=%d  A=%d B=%d ENCSW=%d\n",
                  rx, mvx, level(rx), ry, mvy, level(ry),
                  digitalRead(PIN_BTN_CONFIRM), centre,
                  digitalRead(PIN_BTN_CLEAR),   digitalRead(PIN_BTN_RETURN),
                  digitalRead(PIN_ENC_A), digitalRead(PIN_ENC_B),
                  digitalRead(PIN_ENC_SW));
    Serial.flush();
}
#endif

bool InputReader::poll(InputEvent& out) {
    if (q_count_ == 0) {
        uint32_t now = ::millis();
        sampleButtons(now);
        // Axes first, while SW6's common is still held low, then the centre,
        // which borrows that pin for a few hundred microseconds.
        sampleAxis(axis_y_, now);
        sampleAxis(axis_x_, now);
        sampleCentre(now);
        sampleEncoder(now);
    }
    if (q_count_ == 0) return false;
    out     = queue_[q_head_];
    q_head_ = (q_head_ + 1) % QUEUE_SIZE;
    --q_count_;
    return true;
}
