// obd2_pids.h
// OBD-II PID definitions per SAE J1979 / ISO 15031-5
// All mode/PID values are as specified in the standard.

#pragma once
#include <cstdint>

// ── Service (Mode) identifiers ──────────────────────────────────────────────
static constexpr uint8_t OBD_MODE_CURRENT_DATA        = 0x01;
static constexpr uint8_t OBD_MODE_FREEZE_FRAME        = 0x02;
static constexpr uint8_t OBD_MODE_STORED_DTC          = 0x03;
static constexpr uint8_t OBD_MODE_CLEAR_DTC           = 0x04;
static constexpr uint8_t OBD_MODE_OXYGEN_SENSORS      = 0x05;
static constexpr uint8_t OBD_MODE_SUPPORTED_TESTS     = 0x06;
static constexpr uint8_t OBD_MODE_PENDING_DTC         = 0x07;
static constexpr uint8_t OBD_MODE_CONTROL             = 0x08;
static constexpr uint8_t OBD_MODE_VEHICLE_INFO        = 0x09;
static constexpr uint8_t OBD_MODE_PERMANENT_DTC       = 0x0A;

// Negative response codes (ISO 15031-5)
static constexpr uint8_t OBD_NEGATIVE_RESPONSE        = 0x7F;
static constexpr uint8_t NRC_SERVICE_NOT_SUPPORTED    = 0x11;

// ── Mode 01 PID identifiers ─────────────────────────────────────────────────
static constexpr uint8_t PID_SUPPORTED_01_20          = 0x00;
static constexpr uint8_t PID_MIL_STATUS               = 0x01;
static constexpr uint8_t PID_FREEZE_DTC               = 0x02;
static constexpr uint8_t PID_FUEL_SYSTEM_STATUS       = 0x03;
static constexpr uint8_t PID_ENGINE_LOAD              = 0x04;  // %
static constexpr uint8_t PID_COOLANT_TEMP             = 0x05;  // °C
static constexpr uint8_t PID_SHORT_FUEL_TRIM_1        = 0x06;  // %
static constexpr uint8_t PID_LONG_FUEL_TRIM_1         = 0x07;  // %
static constexpr uint8_t PID_FUEL_PRESSURE            = 0x0A;  // kPa
static constexpr uint8_t PID_INTAKE_MAP               = 0x0B;  // kPa
static constexpr uint8_t PID_ENGINE_RPM               = 0x0C;  // rpm
static constexpr uint8_t PID_VEHICLE_SPEED            = 0x0D;  // km/h
static constexpr uint8_t PID_TIMING_ADVANCE           = 0x0E;  // degrees
static constexpr uint8_t PID_INTAKE_AIR_TEMP          = 0x0F;  // °C
static constexpr uint8_t PID_MAF_FLOW                 = 0x10;  // g/s
static constexpr uint8_t PID_THROTTLE_POS             = 0x11;  // %
static constexpr uint8_t PID_O2_BANK1_SENSOR1         = 0x14;  // V
static constexpr uint8_t PID_OBD_STANDARD             = 0x1C;  // enum
static constexpr uint8_t PID_RUNTIME                  = 0x1F;  // s
static constexpr uint8_t PID_SUPPORTED_21_40          = 0x20;
static constexpr uint8_t PID_DISTANCE_MIL_ON          = 0x21;  // km
static constexpr uint8_t PID_FUEL_LEVEL               = 0x2F;  // %
static constexpr uint8_t PID_BARO_PRESSURE            = 0x33;  // kPa
static constexpr uint8_t PID_SUPPORTED_41_60          = 0x40;
static constexpr uint8_t PID_CONTROL_MODULE_VOLTAGE   = 0x42;  // V
static constexpr uint8_t PID_AMBIENT_AIR_TEMP         = 0x46;  // °C
static constexpr uint8_t PID_ENGINE_OIL_TEMP          = 0x5C;  // °C

// ── Mode 09 InfoType identifiers ────────────────────────────────────────────
static constexpr uint8_t INFOTYPE_VIN_COUNT           = 0x01;
static constexpr uint8_t INFOTYPE_VIN                 = 0x02;
