// crash_report.cpp
// See crash_report.h for why the panic text never reaches USB-C and why the
// core dump in flash is read instead.
#include "crash_report.h"

// Bring-up only. In the shipped `custom-board` build the callers replace
// crash_stage() with a no-op macro and never call crash_report_print(), so
// compiling this out keeps that binary exactly as it was.
#if defined(BRINGUP_DIAG)

#include <Arduino.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <esp_core_dump.h>

// ── Breadcrumb across the reset ─────────────────────────────────────────────
// RTC_NOINIT_ATTR survives a software reset (the panic handler's restart is
// one), so the last stage reached is still readable on the next boot. This is
// the belt to the core dump's braces: it needs no partition, no console and no
// working flash driver, and it also covers a crash in a place where the core
// dump itself cannot be written.
static RTC_NOINIT_ATTR uint32_t s_stage_magic;
static RTC_NOINIT_ATTR uint32_t s_stage;
static constexpr uint32_t STAGE_MAGIC = 0x0BD25746;   // any constant, checked below

void crash_stage(uint32_t stage) {
    s_stage_magic = STAGE_MAGIC;
    s_stage       = stage;
}

// ── Name tables ─────────────────────────────────────────────────────────────
static const char* reset_reason_name(esp_reset_reason_t r) {
    switch (r) {
        case ESP_RST_POWERON:   return "POWERON (power applied)";
        case ESP_RST_EXT:       return "EXT (reset pin)";
        case ESP_RST_SW:        return "SW (esp_restart)";
        case ESP_RST_PANIC:     return "PANIC (exception or abort)";
        case ESP_RST_INT_WDT:   return "INT_WDT (interrupts blocked > 300 ms)";
        case ESP_RST_TASK_WDT:  return "TASK_WDT (a watched task was starved)";
        case ESP_RST_WDT:       return "WDT (other watchdog)";
        case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
        case ESP_RST_BROWNOUT:  return "BROWNOUT (supply dipped)";
        case ESP_RST_SDIO:      return "SDIO";
        default:                return "UNKNOWN";
    }
}

// The Xtensa EXCCAUSE values that can plausibly turn up here. The full table is
// in the ISA manual; anything not listed prints as its number.
static const char* exccause_name(uint32_t c) {
    switch (c) {
        case 0:  return "IllegalInstruction";
        case 1:  return "Syscall";
        case 2:  return "InstructionFetchError";
        case 3:  return "LoadStoreError";      // e.g. a 8/16-bit access to peripheral space
        case 4:  return "Level1Interrupt";
        case 5:  return "Alloca";
        case 6:  return "IntegerDivideByZero";
        case 8:  return "Privileged";
        case 9:  return "LoadStoreAlignment";
        case 12: return "InstrPIFDataError";
        case 13: return "LoadStorePIFDataError";
        case 14: return "InstrPIFAddrError";
        case 15: return "LoadStorePIFAddrError";
        case 20: return "InstrFetchProhibited";
        case 28: return "LoadProhibited";      // read through a null or bad pointer
        case 29: return "StoreProhibited";     // write through a null or bad pointer
        default: return "(see ISA table)";
    }
}

// USB-Serial-JTAG delivers reliably only while the host is draining it, so the
// report goes out in small pieces with a breath between them.
static void say(const char* line) {
    Serial.println(line);
    Serial.flush();
    delay(20);
}

void crash_report_print() {
    char buf[160];

    say("");
    say("===== previous boot report =====");

    const esp_reset_reason_t reason = esp_reset_reason();
    snprintf(buf, sizeof buf, "[crash] reset reason: %d = %s",
             (int)reason, reset_reason_name(reason));
    say(buf);

    if (s_stage_magic == STAGE_MAGIC) {
        snprintf(buf, sizeof buf, "[crash] last stage reached: %lu",
                 (unsigned long)s_stage);
        say(buf);
    } else {
        say("[crash] no stage recorded (cold start)");
    }
    // Start this run's breadcrumb from a known value.
    crash_stage(0);

    if (esp_core_dump_image_check() != ESP_OK) {
        say("[crash] no core dump stored in flash");
        say("================================");
        return;
    }

    esp_core_dump_summary_t s;
    if (esp_core_dump_get_summary(&s) != ESP_OK) {
        say("[crash] a dump exists but cannot be read");
        say("================================");
        return;
    }

    snprintf(buf, sizeof buf, "[crash] task: %.16s", s.exc_task);
    say(buf);
    snprintf(buf, sizeof buf, "[crash] exception PC: 0x%08lx",
             (unsigned long)s.exc_pc);
    say(buf);
    snprintf(buf, sizeof buf, "[crash] cause: %lu = %s, address: 0x%08lx",
             (unsigned long)s.ex_info.exc_cause,
             exccause_name(s.ex_info.exc_cause),
             (unsigned long)s.ex_info.exc_vaddr);
    say(buf);
    // This SHA is the one the crashing image printed as "ELF file SHA256:", so
    // it says which binary these addresses belong to. Decoding a backtrace
    // against the wrong .elf is the classic way to chase a phantom.
    snprintf(buf, sizeof buf, "[crash] image SHA: %s", (const char*)s.app_elf_sha256);
    say(buf);

    snprintf(buf, sizeof buf, "[crash] backtrace (%lu entries, %s):",
             (unsigned long)s.exc_bt_info.depth,
             s.exc_bt_info.corrupted ? "CORRUPTED" : "clean");
    say(buf);
    for (uint32_t i = 0; i < s.exc_bt_info.depth && i < 16; ++i) {
        snprintf(buf, sizeof buf, "[crash]   %2lu: 0x%08lx",
                 (unsigned long)i, (unsigned long)s.exc_bt_info.bt[i]);
        say(buf);
    }

    // One line ready to paste into addr2line, so the PCs turn into file:line
    // without anyone assembling the list by hand.
    String pcs = "[crash] addr2line:";
    pcs += " 0x"; pcs += String(s.exc_pc, HEX);
    for (uint32_t i = 0; i < s.exc_bt_info.depth && i < 16; ++i) {
        pcs += " 0x";
        pcs += String(s.exc_bt_info.bt[i], HEX);
    }
    Serial.println(pcs);
    Serial.flush();
    delay(20);

    // Erase, so the next boot reports the NEXT crash and not this one again.
    esp_core_dump_image_erase();
    say("[crash] dump erased, the next crash writes a fresh one");
    say("================================");
}

#endif // BRINGUP_DIAG
