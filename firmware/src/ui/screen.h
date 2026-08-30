// screen.h
// Screen-stack UI: ScreenManager keeps a small fixed stack of
// screens, and the top screen receives InputEvents and repaints only the rows it
// marked dirty (partial refresh avoids flicker on the shared SPI bus).
#pragma once
#include "input.h"
#include "app/app_types.h"
#include <TFT_eSPI.h>

class Screen;
class ScreenManager;

// Shared UI state handed to every screen. `snap` is refreshed from the CAN
// task at 10 Hz by the UI task before drawing.
struct UiContext {
    TFT_eSPI&      tft;
    ScreenManager& mgr;
    app::Snapshot  snap;

    // Navigation targets (wired once in ui_task_start).
    Screen* nav_sensors  = nullptr;
    Screen* nav_dtcs     = nullptr;
    Screen* nav_settings = nullptr;
};

// ── Layout / theme constants (320x240 landscape) ────────────────────────────
namespace ui {
constexpr int SCREEN_W   = 320;
constexpr int SCREEN_H   = 240;
constexpr int HEADER_H   = 28;
constexpr int ROW_H      = 22;
constexpr int VISIBLE_ROWS = (SCREEN_H - HEADER_H - ROW_H) / ROW_H; // footer row

constexpr uint16_t COL_BG        = TFT_BLACK;
constexpr uint16_t COL_HEADER_BG = 0x10A2;      // dark grey-blue
constexpr uint16_t COL_TEXT      = TFT_WHITE;
constexpr uint16_t COL_DIM       = 0x8410;      // grey
constexpr uint16_t COL_ACCENT    = TFT_CYAN;
constexpr uint16_t COL_SELECT_BG = 0x0339;      // selection bar
constexpr uint16_t COL_EDIT_BG   = 0x51E4;      // editing highlight
constexpr uint16_t COL_OK        = TFT_GREEN;
constexpr uint16_t COL_WARN      = TFT_YELLOW;
constexpr uint16_t COL_ALERT     = TFT_RED;
} // namespace ui

class Screen {
public:
    explicit Screen(UiContext& ctx) : ctx_(ctx) {}
    virtual ~Screen() = default;

    virtual void onEnter() { full_redraw_ = true; }
    virtual void onEvent(const InputEvent& e) = 0;
    virtual void draw() = 0;

protected:
    // Common chrome shared by all screens.
    void drawHeader(const char* title);
    void drawFooter(const char* hint);
    void clearBody();

    UiContext& ctx_;
    bool       full_redraw_ = true;
};

class ScreenManager {
public:
    void push(Screen* s);
    void pop();                 // never pops the root screen
    Screen* top() const { return depth_ > 0 ? stack_[depth_ - 1] : nullptr; }

private:
    static constexpr int MAX_DEPTH = 4;
    Screen* stack_[MAX_DEPTH] = {};
    int     depth_ = 0;
};
