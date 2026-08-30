// dtc_format.h
// Conversion between the raw 2-byte OBD encoding of a DTC and its display
// string, per SAE J2012 / ISO 15031-6: the two most significant bits select
// the category letter (00=P, 01=C, 10=B, 11=U), the next two bits are the
// first digit (0-3), then three hex digits. E.g. 0x0301 <-> "P0301",
// 0xC100 <-> "U0100".
#pragma once
#include <cstdint>
#include <cstring>

inline void dtc_to_string(uint16_t code, char out[6]) {
    static const char letters[4] = { 'P', 'C', 'B', 'U' };
    static const char hex[]      = "0123456789ABCDEF";
    out[0] = letters[(code >> 14) & 0x03];
    out[1] = static_cast<char>('0' + ((code >> 12) & 0x03));
    out[2] = hex[(code >> 8) & 0x0F];
    out[3] = hex[(code >> 4) & 0x0F];
    out[4] = hex[ code       & 0x0F];
    out[5] = '\0';
}

inline bool dtc_from_string(const char* s, uint16_t& code) {
    if (!s || std::strlen(s) != 5) return false;
    uint16_t cat;
    switch (s[0]) {
        case 'P': case 'p': cat = 0; break;
        case 'C': case 'c': cat = 1; break;
        case 'B': case 'b': cat = 2; break;
        case 'U': case 'u': cat = 3; break;
        default: return false;
    }
    if (s[1] < '0' || s[1] > '3') return false;
    uint16_t value = static_cast<uint16_t>((cat << 14) |
                     (static_cast<uint16_t>(s[1] - '0') << 12));
    for (int i = 2; i < 5; ++i) {
        char c = s[i];
        uint16_t nibble;
        if (c >= '0' && c <= '9')      nibble = static_cast<uint16_t>(c - '0');
        else if (c >= 'A' && c <= 'F') nibble = static_cast<uint16_t>(c - 'A' + 10);
        else if (c >= 'a' && c <= 'f') nibble = static_cast<uint16_t>(c - 'a' + 10);
        else return false;
        value = static_cast<uint16_t>(value | (nibble << (4 * (4 - i))));
    }
    code = value;
    return true;
}
