// can_handler.h
#pragma once
#include "iso_tp.h"
#include "dtc_bank.h"

// OBD-II identifiers (ISO 15765-4, 11-bit)
static constexpr uint32_t OBD_FUNCTIONAL_ID = 0x7DF; // broadcast request
static constexpr uint32_t OBD_PHYSICAL_ID   = 0x7E0; // physical request, ECU 1
static constexpr uint32_t OBD_RESPONSE_ID   = 0x7E8; // ECU 1 response

// 17-character vehicle identification number, factory default.
extern const char OBD_VIN[18];

// The VIN mode 0x09 actually reports. It starts as OBD_VIN and a scenario may
// replace it, which is why it is not simply OBD_VIN at the point of use.
//
// Until 09.08.2026. it WAS OBD_VIN at the point of use: the firmware parsed
// "vin" out of a scenario file, stored it, published it in the snapshot and
// printed it on the home screen, while the bus kept answering with the factory
// value, so the display and a diagnostic tool disagreed. That limitation was
// written down in firmware/src/storage/scenario.h rather than overlooked, but
// it made the scenario field half useful, so the core now carries the value.
//
// obd_set_vin copies at most 17 characters and always terminates. A null or
// empty argument restores the factory VIN, so a scenario without a "vin" key
// behaves exactly as before.
void        obd_set_vin(const char* vin);
const char* obd_get_vin();

// Dispatch one received CAN frame. Sends the response(s) via can_send_frame.
void process_obd_request(const CanFrame& req, DtcBank& bank);
