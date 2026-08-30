// screen.cpp
#include "screen.h"

void Screen::drawHeader(const char* title) {
    TFT_eSPI& tft = ctx_.tft;
    tft.fillRect(0, 0, ui::SCREEN_W, ui::HEADER_H, ui::COL_HEADER_BG);
    tft.setTextFont(4);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(ui::COL_ACCENT, ui::COL_HEADER_BG);
    tft.drawString(title, 6, ui::HEADER_H / 2);
}

void Screen::drawFooter(const char* hint) {
    TFT_eSPI& tft = ctx_.tft;
    int y = ui::SCREEN_H - ui::ROW_H;
    tft.fillRect(0, y, ui::SCREEN_W, ui::ROW_H, ui::COL_BG);
    tft.setTextFont(2);
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(ui::COL_DIM, ui::COL_BG);
    tft.drawString(hint, 6, y + ui::ROW_H / 2);
}

void Screen::clearBody() {
    ctx_.tft.fillRect(0, ui::HEADER_H, ui::SCREEN_W,
                      ui::SCREEN_H - ui::HEADER_H, ui::COL_BG);
}

void ScreenManager::push(Screen* s) {
    if (!s || depth_ >= MAX_DEPTH) return;
    stack_[depth_++] = s;
    s->onEnter();
}

void ScreenManager::pop() {
    if (depth_ <= 1) return;    // keep the root (home) screen
    --depth_;
    stack_[depth_ - 1]->onEnter();   // revealed screen repaints fully
}
