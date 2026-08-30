// pid_encoder.h
#pragma once
#include <cstdint>

uint8_t  encode_pid(uint8_t pid, float value, uint8_t out[4]);
uint32_t build_supported_pids(uint8_t base);
