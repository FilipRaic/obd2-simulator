// settings_screen.cpp
#include "settings_screen.h"
#include "storage/usb_stick.h"
#include "storage/usb_msc_device.h"
#include "board_config.h"
#include <algorithm>
#include <cstdio>
#include <cstring>

static const char* profile_name(SimProfile p) {
    switch (p) {
        case SimProfile::Manual: return "Manual";
        case SimProfile::Drive:  return "Drive";
        default:                 return "Idle";
    }
}

void SettingsScreen::onEnter() {
    Screen::onEnter();
    std::memset(cache_, 0, sizeof(cache_));
    status_[0] = '\0';
    refreshFileList();
}

void SettingsScreen::refreshFileList() {
    file_count_ = storage::list(files_, storage::MAX_SCENARIOS);
    if (file_index_ >= file_count_) file_index_ = 0;
}

void SettingsScreen::cycleProfile(int direction) {
    static const SimProfile order[] = { SimProfile::Manual, SimProfile::Idle,
                                        SimProfile::Drive };
    int current = 1;
    for (int i = 0; i < 3; ++i)
        if (order[i] == ctx_.snap.profile) current = i;
    SimProfile next = order[(current + direction + 3) % 3];

    app::Command cmd{};
    cmd.type    = app::CmdType::SetProfile;
    cmd.profile = next;
    app::send_command(cmd);
}

void SettingsScreen::activateRow() {
    app::Command cmd{};
    switch (selected_) {
    case ROW_PROFILE:
        cycleProfile(+1);
        break;
    case ROW_SAVE:
        if (!ctx_.snap.fs_ok) {
            snprintf(status_, sizeof(status_), "Storage unavailable");
            break;
        }
        cmd.type = app::CmdType::SaveScenario;
        std::strncpy(cmd.name, "user", sizeof(cmd.name) - 1);
        app::send_command(cmd);
        snprintf(status_, sizeof(status_), "Saving as 'user'...");
        break;
    case ROW_LOAD:
        if (file_count_ == 0) {
            snprintf(status_, sizeof(status_), "No saved scenarios");
            break;
        }
        cmd.type = app::CmdType::LoadScenario;
        std::strncpy(cmd.name, files_[file_index_], sizeof(cmd.name) - 1);
        app::send_command(cmd);
        snprintf(status_, sizeof(status_), "Loading '%s'...",
                 files_[file_index_]);
        break;
    case ROW_FACTORY:
        cmd.type = app::CmdType::FactoryReset;
        app::send_command(cmd);
        snprintf(status_, sizeof(status_), "Factory scenario restored");
        break;
    case ROW_USB_IMPORT: {
        // Blocking by design: the copy takes a few seconds and the CAN task
        // keeps answering the tester meanwhile.
        uint8_t copied = 0;
        usb_stick::Result r = usb_stick::import_scenarios(copied);
        if (r == usb_stick::Result::Ok) {
            snprintf(status_, sizeof(status_), "Imported %u scenarios", copied);
            refreshFileList();
        } else {
            snprintf(status_, sizeof(status_), "%s", usb_stick::result_text(r));
        }
        break;
    }
    case ROW_USB_EXPORT: {
        uint8_t copied = 0;
        usb_stick::Result r = usb_stick::export_scenarios(copied);
        if (r == usb_stick::Result::Ok)
            snprintf(status_, sizeof(status_), "Exported %u scenarios", copied);
        else
            snprintf(status_, sizeof(status_), "%s", usb_stick::result_text(r));
        break;
    }
    case ROW_USB_MSC:
#if defined(BOARD_HAS_USB)
        usb_msc::request_and_reboot();   // does not return
#else
        snprintf(status_, sizeof(status_), "USB not available (development build)");
#endif
        break;
    }
}

void SettingsScreen::onEvent(const InputEvent& e) {
    switch (e.kind) {
    case InputKind::Up:
        selected_ = std::max(0, selected_ - 1);
        break;
    case InputKind::Down:
        selected_ = std::min(ROW_COUNT - 1, selected_ + 1);
        break;
    case InputKind::Left:
        if (selected_ == ROW_PROFILE) cycleProfile(-1);
        if (selected_ == ROW_LOAD && file_count_ > 0)
            file_index_ = (file_index_ + file_count_ - 1) % file_count_;
        break;
    case InputKind::Right:
        if (selected_ == ROW_PROFILE) cycleProfile(+1);
        if (selected_ == ROW_LOAD && file_count_ > 0)
            file_index_ = (file_index_ + 1) % file_count_;
        break;
    case InputKind::Select:
        activateRow();
        break;
    case InputKind::Back:
        ctx_.mgr.pop();
        break;
    default:
        break;
    }
}

void SettingsScreen::draw() {
    TFT_eSPI& tft = ctx_.tft;
    if (full_redraw_) {
        drawHeader("Settings");
        clearBody();
        drawFooter("JOY move/change/select   RETURN back");
    }

#if defined(BOARD_HAS_USB)
    const bool usb_ok = true;
#else
    const bool usb_ok = false;
#endif

    tft.setTextFont(2);
    for (int row = 0; row <= ROW_COUNT; ++row) {
        char text[80];
        switch (row) {
        case ROW_PROFILE:
            snprintf(text, sizeof(text), "Profile:  < %s >",
                     profile_name(ctx_.snap.profile));
            break;
        case ROW_SAVE:
            snprintf(text, sizeof(text), "Save scenario as 'user'%s",
                     ctx_.snap.fs_ok ? "" : "  (no storage)");
            break;
        case ROW_LOAD:
            if (file_count_ > 0)
                snprintf(text, sizeof(text), "Load scenario:  < %s >",
                         files_[file_index_]);
            else
                snprintf(text, sizeof(text), "Load scenario:  (none)");
            break;
        case ROW_FACTORY:
            snprintf(text, sizeof(text), "Factory reset");
            break;
        case ROW_USB_IMPORT:
            snprintf(text, sizeof(text), "USB stick: import scenarios%s",
                     usb_ok ? "" : "  (n/a)");
            break;
        case ROW_USB_EXPORT:
            snprintf(text, sizeof(text), "USB stick: export scenarios%s",
                     usb_ok ? "" : "  (n/a)");
            break;
        case ROW_USB_MSC:
            snprintf(text, sizeof(text), "PC link (USB-C disk) - restart%s",
                     usb_ok ? "" : "  (n/a)");
            break;
        default:   // status line
            snprintf(text, sizeof(text), "%s", status_);
            break;
        }

        bool is_selected = row == selected_ && row < ROW_COUNT;
        uint16_t bg = is_selected ? ui::COL_SELECT_BG : ui::COL_BG;
        if (!full_redraw_ && cache_[row].bg == bg &&
            std::strcmp(cache_[row].text, text) == 0)
            continue;
        std::strncpy(cache_[row].text, text, sizeof(cache_[row].text) - 1);
        cache_[row].bg = bg;

        int y = ui::HEADER_H + row * ui::ROW_H;
        tft.fillRect(0, y, ui::SCREEN_W, ui::ROW_H, bg);
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(row >= ROW_COUNT ? ui::COL_WARN
                         : (is_selected ? ui::COL_ACCENT : ui::COL_TEXT), bg);
        tft.drawString(text, 6, y + ui::ROW_H / 2);
    }
    full_redraw_ = false;
}
