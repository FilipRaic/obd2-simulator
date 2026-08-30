// sensor_screen.h
// Scrollable list of all 21 parameters with manual editing: the joystick centre begins an edit and SW1 CONFIRM stores it,
// SW2 CLEAR discards it, each encoder detent nudges the
// value by a fraction of the sensor's [min, max] and is applied live, CLEAR reverts
// to the pre-edit value, RETURN pops the screen. Edits are most useful in
// the Manual profile - elsewhere the simulation model overwrites them on
// the next tick.
#pragma once
#include "ui/screen.h"

class SensorScreen : public Screen {
public:
    explicit SensorScreen(UiContext& ctx) : Screen(ctx) {}

    void onEnter() override;
    void onEvent(const InputEvent& e) override;
    void draw() override;

private:
    void beginEdit();
    void endEdit();
    void cancelEdit();
    void applyDialStep(float fraction);
    void formatValue(int index, float value, char* out, size_t n) const;

    int   selected_ = 0;
    int   scroll_   = 0;
    bool  editing_  = false;
    int   edit_row_ = -1;
    float staged_   = 0.0f;
    float orig_     = 0.0f;

    struct RowCache { char text[64]; uint16_t bg; };
    RowCache cache_[ui::VISIBLE_ROWS];
};
