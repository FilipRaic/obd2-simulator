// iso_tp.h
// ISO 15765-2 (ISO-TP) transport protocol - transmit side.
// Messages up to 7 bytes are sent as a Single Frame, while longer messages are
// segmented into First Frame + Consecutive Frames with Flow Control
// handshake, as required for the VIN response (mode 0x09) and multi-DTC
// responses (mode 0x03).

#pragma once
#include <cstdint>

// ── CAN frame structure (ISO 15765-4, 11-bit ID) ────────────────────────────
struct CanFrame {
    uint32_t id;        // 11-bit standard ID
    uint8_t  dlc;       // data length code (0-8)
    uint8_t  data[8];
};

// ISO 15765-4 requires 8-byte frames, and unused bytes carry a padding pattern.
static constexpr uint8_t ISO_TP_PADDING = 0x55;

// ── Platform hooks (implement for MCP2515, stubbed in host tests) ───────────
extern void can_send_frame(const CanFrame& frame);

struct FlowControl {
    uint8_t  flow_status;  // 0 = CTS (continue to send), 1 = WAIT, 2 = OVFL
    uint8_t  block_size;   // 0 = send all consecutive frames without pause
    uint32_t st_min_us;    // minimum separation time between CFs
};

// Block until a Flow Control frame arrives, false on timeout/abort.
extern bool iso_tp_wait_flow_control(FlowControl& fc);
// Separation-time delay between consecutive frames.
extern void iso_tp_delay_us(uint32_t us);

// ── Outgoing message buffer ──────────────────────────────────────────────────
class IsoTpMessage {
public:
    static constexpr uint16_t MAX_SIZE = 128;

    void push(uint8_t b) { if (len_ < MAX_SIZE) buf_[len_++] = b; }
    void clear()               { len_ = 0; }
    uint16_t size() const      { return len_; }
    const uint8_t* data() const { return buf_; }

private:
    uint8_t  buf_[MAX_SIZE] = {};
    uint16_t len_ = 0;
};

// Decode the STmin byte of a Flow Control frame into microseconds.
uint32_t iso_tp_decode_stmin_us(uint8_t st_min);

// Send a message with the given CAN identifier (SF, or FF/FC/CF sequence).
// Returns false if the Flow Control handshake fails.
bool iso_tp_send(uint32_t tx_id, const IsoTpMessage& msg);
