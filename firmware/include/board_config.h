// board_config.h
// Pin map for the single hardware-first target: the ESP32-S3-WROOM-1 module, used
// both on the breadboard adapter during development and on the dedicated PCB.
#pragma once

#if defined(BOARD_CUSTOM_S3)
#include "pins_custom_s3.h"
// USB OTG (MSC device via USB-C, stick host via USB-A) and the 12 V supply for
// the diagnostic tool exist only on the dedicated PCB (v0.5).
#define BOARD_HAS_USB 1
#else
#error "No board selected: define BOARD_CUSTOM_S3"
#endif
