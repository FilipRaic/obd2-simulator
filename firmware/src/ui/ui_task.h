// ui_task.h
// Low-priority FreeRTOS task: reads the physical controls,
// drives the screen stack and renders on the ILI9341, always bracketing SPI
// access with the shared-bus mutex. Call once from setup(), after
// can_task_start().
#pragma once

// Bring up the ILI9341. Called from setup() BEFORE any task exists.
//
// It used to run inside the UI task, as the first thing it did, under the
// shared-SPI mutex. On the assembled v0.7 board that panicked every boot:
// the trace reached "[ui] SPI locked, calling tft.init()" and never reached
// "[ui] tft.init() done", and dropping the UI task stopped the reboot loop
// outright. Doing it before the tasks start means nothing else is on the SPI
// bus while the display is initialised.
void ui_display_init();

void ui_task_start();
