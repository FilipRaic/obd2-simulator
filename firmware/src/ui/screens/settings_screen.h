// settings_screen.h
// Settings (v0.5): switch the simulation profile, save the
// current state as a scenario, load a stored scenario from the internal
// flash filesystem, restore the factory scenario, and the USB actions:
// import/export scenarios via a USB-A stick and reboot into the USB-C
// PC-link (MSC) mode. USB rows are inert on the development board.
#pragma once
#include "ui/screen.h"
#include "storage/storage.h"

class SettingsScreen : public Screen {
public:
    explicit SettingsScreen(UiContext& ctx) : Screen(ctx) {}

    void onEnter() override;
    void onEvent(const InputEvent& e) override;
    void draw() override;

private:
    static constexpr int ROW_PROFILE    = 0;
    static constexpr int ROW_SAVE       = 1;
    static constexpr int ROW_LOAD       = 2;
    static constexpr int ROW_FACTORY    = 3;
    static constexpr int ROW_USB_IMPORT = 4;
    static constexpr int ROW_USB_EXPORT = 5;
    static constexpr int ROW_USB_MSC    = 6;
    static constexpr int ROW_COUNT      = 7;

    void cycleProfile(int direction);
    void activateRow();
    void refreshFileList();

    int     selected_   = 0;
    uint8_t file_count_ = 0;
    int     file_index_ = 0;
    char    files_[storage::MAX_SCENARIOS][app::SCENARIO_NAME_MAX];
    char    status_[48] = "";

    struct RowCache { char text[80]; uint16_t bg; };
    RowCache cache_[ROW_COUNT + 1];
};
