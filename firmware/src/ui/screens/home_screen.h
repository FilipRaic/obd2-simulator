// home_screen.h
// Root screen: status overview (active scenario, profile, MIL,
// DTC counts, bus traffic) plus the navigation menu to the other screens.
#pragma once
#include "ui/screen.h"

class HomeScreen : public Screen {
public:
    explicit HomeScreen(UiContext& ctx) : Screen(ctx) {}

    void onEnter() override;
    void onEvent(const InputEvent& e) override;
    void draw() override;

private:
    static constexpr int MENU_COUNT  = 3;
    static constexpr int STATUS_ROWS = 5;
    static constexpr int TOTAL_ROWS  = STATUS_ROWS + MENU_COUNT;

    void buildRow(int row, char* text, size_t n, uint16_t& fg) const;

    int  selected_ = 0;   // menu index 0..2
    char cache_[TOTAL_ROWS][64];
    int  cache_selected_ = -1;
};
