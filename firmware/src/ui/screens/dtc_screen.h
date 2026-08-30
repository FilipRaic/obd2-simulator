// dtc_screen.h
// Fault-code screen: lists the DTC catalog with each code's live
// state. It follows the same two-step model as the sensor screen, so nothing
// changes on a single press: the joystick centre SELECTS a code, left and right
// then walk it along the scale (absent -> pending -> confirmed and back down),
// CONFIRM stores the new state, CLEAR or RETURN abandon the change.
// CLEAR with no code selected erases the whole bank - the same effect a tester
// achieves with service 0x04 - but only after a confirmation prompt, because it
// throws away every code at once.
#pragma once
#include "ui/screen.h"

class DtcScreen : public Screen {
public:
    explicit DtcScreen(UiContext& ctx) : Screen(ctx) {}

    void onEnter() override;
    void onEvent(const InputEvent& e) override;
    void draw() override;

private:
    // Absent -> Pending -> Confirmed, walked with left/right while editing.
    static constexpr int STATE_COUNT = 3;
    void  commitEdit();
    void  cancelEdit();
    void  drawPrompt();

    int  selected_ = 0;
    bool editing_  = false;
    int  edit_row_ = -1;
    int  staged_   = 0;   // app::DtcUiState as an int, so it can be stepped
    bool prompt_   = false;   // "erase every code?" confirmation is showing

    struct RowCache { char text[80]; uint16_t bg; };
    RowCache cache_[ui::VISIBLE_ROWS];
};
