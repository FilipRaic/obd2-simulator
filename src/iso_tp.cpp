// iso_tp.cpp
// ISO 15765-2 (ISO-TP) transmit path: Single Frame for messages up to
// 7 bytes, First Frame + Flow Control + Consecutive Frames for longer
// messages. All frames are padded to 8 bytes per ISO 15765-4.

#include "iso_tp.h"
#include <cstring>

// STmin encoding per ISO 15765-2: 0x00-0x7F = milliseconds,
// 0xF1-0xF9 = 100-900 microseconds, other values are reserved
// and treated as the maximum of 127 ms.
uint32_t iso_tp_decode_stmin_us(uint8_t st_min) {
    if (st_min <= 0x7F) return static_cast<uint32_t>(st_min) * 1000u;
    if (st_min >= 0xF1 && st_min <= 0xF9)
        return static_cast<uint32_t>(st_min - 0xF0) * 100u;
    return 127000u;
}

static void send_padded(uint32_t id, const uint8_t* data, uint8_t used) {
    CanFrame f{};
    f.id  = id;
    f.dlc = 8;
    std::memcpy(f.data, data, used);
    for (uint8_t i = used; i < 8; ++i) f.data[i] = ISO_TP_PADDING;
    can_send_frame(f);
}

bool iso_tp_send(uint32_t tx_id, const IsoTpMessage& msg) {
    const uint8_t* payload = msg.data();
    const uint16_t len     = msg.size();

    // ── Single Frame: PCI = 0x0N, N = payload length (1-7) ──────────────────
    if (len <= 7) {
        uint8_t buf[8];
        buf[0] = static_cast<uint8_t>(0x00 | len);
        std::memcpy(&buf[1], payload, len);
        send_padded(tx_id, buf, static_cast<uint8_t>(1 + len));
        return true;
    }

    // ── First Frame: PCI = 0x1LLL (12-bit length) + first 6 bytes ───────────
    uint8_t ff[8];
    ff[0] = static_cast<uint8_t>(0x10 | ((len >> 8) & 0x0F));
    ff[1] = static_cast<uint8_t>(len & 0xFF);
    std::memcpy(&ff[2], payload, 6);
    send_padded(tx_id, ff, 8);

    // ── Wait for Flow Control from the tester ────────────────────────────────
    FlowControl fc{};
    if (!iso_tp_wait_flow_control(fc)) return false;
    if (fc.flow_status != 0) return false; // only CTS is handled

    // ── Consecutive Frames: PCI = 0x2N, N = sequence number (1..15, 0, ...) ──
    uint8_t seq = 1;
    for (uint16_t off = 6; off < len; off += 7, seq = (seq + 1) & 0x0F) {
        uint8_t chunk = static_cast<uint8_t>((len - off) < 7 ? (len - off) : 7);
        uint8_t cf[8];
        cf[0] = static_cast<uint8_t>(0x20 | seq);
        std::memcpy(&cf[1], &payload[off], chunk);
        send_padded(tx_id, cf, static_cast<uint8_t>(1 + chunk));
        if (fc.st_min_us > 0 && off + 7 < len) iso_tp_delay_us(fc.st_min_us);
    }
    return true;
}
