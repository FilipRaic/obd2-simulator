// dtc_screen.cpp
#include "dtc_screen.h"
#include "dtc_bank.h"
#include <algorithm>
#include <cstdio>
#include <cstring>

void DtcScreen::onEnter() {
    Screen::onEnter();
    editing_ = false;
    edit_row_ = -1;
    prompt_ = false;
    std::memset(cache_, 0, sizeof(cache_));
}

void DtcScreen::commitEdit() {
    app::Command cmd{};
    cmd.type      = app::CmdType::DtcSetState;
    cmd.dtc_code  = DTC_CATALOG[edit_row_].code;
    cmd.dtc_state = static_cast<app::DtcUiState>(staged_);
    app::send_command(cmd);
    cancelEdit();
}

void DtcScreen::cancelEdit() {
    editing_     = false;
    edit_row_    = -1;
    full_redraw_ = true;   // footer hint changes
}

void DtcScreen::onEvent(const InputEvent& e) {
    // The "erase every code?" prompt is modal: while it is up, only CONFIRM
    // (erase) and CLEAR or RETURN (keep them) mean anything.
    if (prompt_) {
        if (e.kind == InputKind::Ok) {
            app::Command cmd{};
            cmd.type = app::CmdType::DtcClearAll;
            app::send_command(cmd);
        }
        if (e.kind == InputKind::Ok || e.kind == InputKind::Clear ||
            e.kind == InputKind::Back) {
            prompt_ = false;
            full_redraw_ = true;
        }
        return;
    }

    switch (e.kind) {
    case InputKind::Up:
        if (!editing_) selected_ = std::max(0, selected_ - 1);
        break;
    case InputKind::Down:
        if (!editing_)
            selected_ = std::min(static_cast<int>(app::CATALOG_SIZE) - 1,
                                 selected_ + 1);
        break;

    // Left and right walk the staged state up and down the scale. The ends are
    // clamped rather than wrapped, so a code cannot jump from confirmed
    // straight back to absent by one press.
    case InputKind::Left:
        if (editing_) staged_ = std::max(0, staged_ - 1);
        break;
    case InputKind::Right:
        if (editing_) staged_ = std::min(STATE_COUNT - 1, staged_ + 1);
        break;

    // Joystick centre picks the code to change; nothing changes yet.
    case InputKind::Select:
        if (!editing_) {
            editing_     = true;
            edit_row_    = selected_;
            staged_      = static_cast<int>(ctx_.snap.catalog_state[selected_]);
            full_redraw_ = true;
        }
        break;

    case InputKind::Ok:
        if (editing_) commitEdit();
        break;

    case InputKind::Clear:
        if (editing_) cancelEdit();
        else { prompt_ = true; full_redraw_ = true; }
        break;

    case InputKind::Back:
        if (editing_) cancelEdit();
        else          ctx_.mgr.pop();
        break;

    default:
        break;
    }
}

void DtcScreen::draw() {
    TFT_eSPI& tft = ctx_.tft;
    if (full_redraw_) {
        drawHeader("Fault codes");
        clearBody();
        drawFooter(editing_ ? "JOY < >   CONFIRM store   CLEAR revert"
                            : "JOY move/select   CLEAR erase all   RETURN back");
    }

    tft.setTextFont(2);
    for (int row = 0; row < app::CATALOG_SIZE && row < ui::VISIBLE_ROWS;
         ++row) {
        // While editing, the selected row shows the STAGED state, so the
        // user sees what CONFIRM would store before storing it.
        app::DtcUiState state =
            (editing_ && row == edit_row_)
                ? static_cast<app::DtcUiState>(staged_)
                : ctx_.snap.catalog_state[row];
        const char* badge =
            (state == app::DtcUiState::Confirmed) ? "CONF" :
            (state == app::DtcUiState::Pending)   ? "PEND" : "-";

        char text[80];
        snprintf(text, sizeof(text), "%s|%s", DTC_CATALOG[row].label, badge);

        uint16_t bg = (editing_ && row == edit_row_) ? ui::COL_EDIT_BG
                    : (row == selected_)             ? ui::COL_SELECT_BG
                                                     : ui::COL_BG;
        if (!full_redraw_ && cache_[row].bg == bg &&
            std::strcmp(cache_[row].text, text) == 0)
            continue;
        std::strncpy(cache_[row].text, text, sizeof(cache_[row].text) - 1);
        cache_[row].bg = bg;

        int y = ui::HEADER_H + row * ui::ROW_H;
        tft.fillRect(0, y, ui::SCREEN_W, ui::ROW_H, bg);
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(row == selected_ ? ui::COL_ACCENT : ui::COL_TEXT, bg);

        // Catalog labels are "P0301 Cylinder 1 Misfire Detected", so truncate them
        // to leave room for the state badge.
        char label[40];
        std::strncpy(label, DTC_CATALOG[row].label, sizeof(label) - 1);
        label[sizeof(label) - 1] = '\0';
        tft.drawString(label, 6, y + ui::ROW_H / 2);

        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(
            (state == app::DtcUiState::Confirmed) ? ui::COL_ALERT :
            (state == app::DtcUiState::Pending)   ? ui::COL_WARN
                                                  : ui::COL_DIM, bg);
        tft.drawString(badge, ui::SCREEN_W - 6, y + ui::ROW_H / 2);
    }
    if (prompt_) drawPrompt();
    full_redraw_ = false;
}

// A full-width band over the list. Erasing the bank throws away every code
// at once, so it asks first and the safe answer is the one that needs no
// action: walking away with RETURN keeps the codes.
void DtcScreen::drawPrompt() {
    TFT_eSPI& tft = ctx_.tft;
    const int h = ui::ROW_H * 3;
    const int y = ui::HEADER_H + (ui::SCREEN_H - ui::HEADER_H - ui::ROW_H - h) / 2;
    tft.fillRect(0, y, ui::SCREEN_W, h, ui::COL_EDIT_BG);
    tft.drawRect(0, y, ui::SCREEN_W, h, ui::COL_WARN);
    tft.setTextFont(2);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(ui::COL_TEXT, ui::COL_EDIT_BG);
    tft.drawString("Erase every fault code?", ui::SCREEN_W / 2, y + ui::ROW_H);
    tft.setTextColor(ui::COL_WARN, ui::COL_EDIT_BG);
    tft.drawString("CONFIRM erase      RETURN keep", ui::SCREEN_W / 2,
                   y + ui::ROW_H * 2);
}
