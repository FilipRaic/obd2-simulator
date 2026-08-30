// home_screen.cpp
#include "home_screen.h"
#include <cstdio>
#include <cstring>

static const char* profile_name(SimProfile p) {
    switch (p) {
        case SimProfile::Manual: return "Manual";
        case SimProfile::Drive:  return "Drive";
        default:                 return "Idle";
    }
}

static const char* MENU_ITEMS[3] = {
    "Sensors", "Fault codes (DTC)", "Settings"
};

void HomeScreen::onEnter() {
    Screen::onEnter();
    cache_selected_ = -1;
    std::memset(cache_, 0, sizeof(cache_));
}

void HomeScreen::onEvent(const InputEvent& e) {
    switch (e.kind) {
    case InputKind::Up:
        if (selected_ > 0) --selected_;
        break;
    case InputKind::Down:
        if (selected_ < MENU_COUNT - 1) ++selected_;
        break;
    case InputKind::Select: {
        Screen* target = (selected_ == 0) ? ctx_.nav_sensors
                       : (selected_ == 1) ? ctx_.nav_dtcs
                                          : ctx_.nav_settings;
        ctx_.mgr.push(target);
        break;
    }
    default:
        break;   // Ok/Back/Clear/DialStep have no effect on the root screen
    }
}

void HomeScreen::buildRow(int row, char* text, size_t n, uint16_t& fg) const {
    const app::Snapshot& s = ctx_.snap;
    fg = ui::COL_TEXT;
    switch (row) {
    case 0:
        snprintf(text, n, "Scenario: %s", s.scenario_name);
        break;
    case 1:
        snprintf(text, n, "Profile: %s    MIL: %s", profile_name(s.profile),
                 s.mil ? "ON" : "off");
        fg = s.mil ? ui::COL_ALERT : ui::COL_TEXT;
        break;
    case 2:
        snprintf(text, n, "DTC: %u confirmed, %u pending",
                 s.confirmed_count, s.pending_count);
        break;
    case 3:
        snprintf(text, n, "VIN: %s", s.vin);
        fg = ui::COL_DIM;
        break;
    case 4:
        snprintf(text, n, "CAN %s  RX %lu  TX %lu   FS %s",
                 s.can_ok ? "OK" : "FAIL",
                 static_cast<unsigned long>(s.rx_frames),
                 static_cast<unsigned long>(s.tx_frames),
                 s.fs_ok ? "OK" : "--");
        fg = s.can_ok ? ui::COL_DIM : ui::COL_ALERT;
        break;
    default:   // menu rows
        snprintf(text, n, "%s", MENU_ITEMS[row - STATUS_ROWS]);
        break;
    }
}

void HomeScreen::draw() {
    TFT_eSPI& tft = ctx_.tft;
    if (full_redraw_) {
        drawHeader("OBD-II Simulator");
        clearBody();
        drawFooter("JOY move/select to open");
    }

    tft.setTextFont(2);
    for (int row = 0; row < TOTAL_ROWS; ++row) {
        char text[64];
        uint16_t fg;
        buildRow(row, text, sizeof(text), fg);

        bool is_menu     = row >= STATUS_ROWS;
        bool is_selected = is_menu && (row - STATUS_ROWS) == selected_;
        bool sel_changed = is_menu && cache_selected_ != selected_;
        if (!full_redraw_ && !sel_changed &&
            std::strcmp(cache_[row], text) == 0)
            continue;
        std::strncpy(cache_[row], text, sizeof(cache_[row]) - 1);

        int y = ui::HEADER_H + row * ui::ROW_H;
        uint16_t bg = is_selected ? ui::COL_SELECT_BG : ui::COL_BG;
        tft.fillRect(0, y, ui::SCREEN_W, ui::ROW_H, bg);
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(is_menu ? (is_selected ? ui::COL_ACCENT : ui::COL_TEXT)
                                 : fg, bg);
        tft.drawString(is_menu ? (is_selected ? "> " : "  ") : "", 6,
                       y + ui::ROW_H / 2);
        tft.drawString(text, is_menu ? 22 : 6, y + ui::ROW_H / 2);
    }
    cache_selected_ = selected_;
    full_redraw_    = false;
}
