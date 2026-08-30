// sensor_screen.cpp
#include "sensor_screen.h"
#include "sensor_meta.h"
#include <algorithm>
#include <cstdio>
#include <cstring>

void SensorScreen::onEnter() {
    Screen::onEnter();
    editing_  = false;
    edit_row_ = -1;
    std::memset(cache_, 0, sizeof(cache_));
}

void SensorScreen::beginEdit() {
    editing_  = true;
    edit_row_ = selected_;
    orig_     = ctx_.snap.values[selected_];
    staged_   = orig_;
    full_redraw_ = true;   // footer hint changes
}

void SensorScreen::endEdit() {
    editing_     = false;
    edit_row_    = -1;
    full_redraw_ = true;
}

void SensorScreen::cancelEdit() {
    app::Command cmd{};
    cmd.type  = app::CmdType::SetSensorValue;
    cmd.pid   = SENSOR_META[edit_row_].pid;
    cmd.value = orig_;
    app::send_command(cmd);
    endEdit();
}

// One encoder detent moves the staged value by a fraction of the sensor's full
// range. Editing starts from the value the sensor already has (beginEdit seeds
// staged_ from orig_), so unlike the old potentiometer there is no jump on the
// first movement.
void SensorScreen::applyDialStep(float fraction) {
    const SensorEntry& s = SENSOR_TABLE[edit_row_];
    staged_ += fraction * (s.max_val - s.min_val);
    if (staged_ < s.min_val) staged_ = s.min_val;
    if (staged_ > s.max_val) staged_ = s.max_val;

    app::Command cmd{};
    cmd.type  = app::CmdType::SetSensorValue;
    cmd.pid   = SENSOR_META[edit_row_].pid;
    cmd.value = staged_;
    app::send_command(cmd);
}

// Modality-independent event handling.
void SensorScreen::onEvent(const InputEvent& e) {
    switch (e.kind) {
    case InputKind::Up:
        if (!editing_) selected_ = std::max(0, selected_ - 1);
        break;
    case InputKind::Down:
        if (!editing_) selected_ = std::min(SENSOR_COUNT - 1, selected_ + 1);
        break;
    // Joystick centre picks the row to edit; it does nothing once an edit is
    // running, because ending one is CONFIRM (store) or CLEAR (discard).
    case InputKind::Select:
        if (!editing_) beginEdit();
        break;
    // SW1 CONFIRM stores the staged value. The value was already applied live
    // by applyDialStep, so committing simply leaves edit mode.
    case InputKind::Ok:
        if (editing_) endEdit();
        break;
    case InputKind::Back:
        if (editing_) cancelEdit();
        ctx_.mgr.pop();
        break;
    case InputKind::Clear:
        if (editing_) cancelEdit();
        break;
    case InputKind::DialStep:
        if (editing_) applyDialStep(e.value01);
        break;
    default:
        break;
    }

    // Keep the selection inside the visible window.
    if (selected_ < scroll_) scroll_ = selected_;
    if (selected_ >= scroll_ + ui::VISIBLE_ROWS)
        scroll_ = selected_ - ui::VISIBLE_ROWS + 1;
}

void SensorScreen::formatValue(int index, float value, char* out,
                               size_t n) const {
    const SensorMeta& m = SENSOR_META[index];
    snprintf(out, n, "%.*f %s", m.decimals, static_cast<double>(value),
             m.unit);
}

void SensorScreen::draw() {
    TFT_eSPI& tft = ctx_.tft;
    if (full_redraw_) {
        drawHeader("Sensors");
        clearBody();
        drawFooter(editing_ ? "ENC set   CONFIRM store   CLEAR revert"
                            : "JOY move/select   RETURN back");
        std::memset(cache_, 0, sizeof(cache_));
    }

    tft.setTextFont(2);
    for (int slot = 0; slot < ui::VISIBLE_ROWS; ++slot) {
        int index = scroll_ + slot;
        if (index >= SENSOR_COUNT) break;

        float value = (editing_ && index == edit_row_)
                          ? staged_
                          : ctx_.snap.values[index];
        char value_text[24];
        formatValue(index, value, value_text, sizeof(value_text));

        char text[64];
        snprintf(text, sizeof(text), "%02X|%s|%s", SENSOR_META[index].pid,
                 SENSOR_META[index].label, value_text);

        uint16_t bg = (editing_ && index == edit_row_) ? ui::COL_EDIT_BG
                    : (index == selected_)             ? ui::COL_SELECT_BG
                                                       : ui::COL_BG;
        if (!full_redraw_ && cache_[slot].bg == bg &&
            std::strcmp(cache_[slot].text, text) == 0)
            continue;
        std::strncpy(cache_[slot].text, text, sizeof(cache_[slot].text) - 1);
        cache_[slot].bg = bg;

        int y = ui::HEADER_H + slot * ui::ROW_H;
        tft.fillRect(0, y, ui::SCREEN_W, ui::ROW_H, bg);
        tft.setTextColor(index == selected_ ? ui::COL_ACCENT : ui::COL_TEXT,
                         bg);
        char pid_label[48];
        snprintf(pid_label, sizeof(pid_label), "%02X  %s",
                 SENSOR_META[index].pid, SENSOR_META[index].label);
        tft.setTextDatum(ML_DATUM);
        tft.drawString(pid_label, 6, y + ui::ROW_H / 2);
        tft.setTextDatum(MR_DATUM);
        tft.drawString(value_text, ui::SCREEN_W - 6, y + ui::ROW_H / 2);
    }
    full_redraw_ = false;
}
