// storage.cpp
#include "storage.h"
#include "flash_fs.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <sys/stat.h>

namespace storage {

static constexpr size_t JSON_BUF_SIZE = 2048;
static const char* SCENARIO_DIR = "/flash/scenarios";
static const char* LAST_MARKER  = "/flash/scenarios/last.txt";
static const char* FACTORY_FILE = "/flash/factory.json";

// FatFs is used from both tasks (CAN task applies scenarios, the UI task
// lists them and copies files to and from a USB stick), so every file
// operation runs under this mutex - including the ones in usb_stick.cpp, which
// bypass the functions here and go straight at /flash with fopen/fwrite. They
// take it through storage::FsGuard.
//
// RECURSIVE since 09.08.2026., so that a guard taken by such outside code
// cannot deadlock if it ever ends up calling back into storage::.
static SemaphoreHandle_t s_mutex = nullptr;
static bool s_ok = false;

struct FsLock {
    FsLock()  { xSemaphoreTakeRecursive(s_mutex, portMAX_DELAY); }
    ~FsLock() { xSemaphoreGiveRecursive(s_mutex); }
};

FsGuard::FsGuard()  { xSemaphoreTakeRecursive(s_mutex, portMAX_DELAY); }
FsGuard::~FsGuard() { xSemaphoreGiveRecursive(s_mutex); }

void init() {
    if (!s_mutex) s_mutex = xSemaphoreCreateRecursiveMutex();
    s_ok = flash_fs::mount();
    if (s_ok) mkdir(SCENARIO_DIR, 0775);   // idempotent
    Serial.printf("[storage] flash FS %s\n",
                  s_ok ? "ready" : "unavailable (defaults only)");
    Serial.flush();
}

bool available() { return s_ok; }

static void scenario_path(const char* name, char* out, size_t out_size) {
    snprintf(out, out_size, "%s/%s.json", SCENARIO_DIR, name);
}

static bool read_file(const char* path, char* buf, size_t buf_size) {
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    size_t len = fread(buf, 1, buf_size - 1, f);
    fclose(f);
    buf[len] = '\0';
    return len > 0;
}

static bool write_file(const char* path, const char* data, size_t len) {
    FILE* f = fopen(path, "wb");
    if (!f) return false;
    bool ok = fwrite(data, 1, len, f) == len;
    fclose(f);
    return ok;
}

// Write the last-used marker only when it would actually change.
//
// load_startup() reads the marker, then calls load(), and load() ends by
// writing it back. Every power-up therefore erased and reprogrammed the marker
// sector with the value it already held. The wear is not the real problem
// (a NOR sector survives 100 000 cycles), losing power inside that write is:
// the marker would be left half written and the board would silently fall back
// to the factory scenario. Reading it first costs one page read and removes
// the write entirely from the boot path, and from re-loading the same scenario
// from the UI.
static void remember_last(const char* name) {
    char current[app::SCENARIO_NAME_MAX] = {};
    if (read_file(LAST_MARKER, current, sizeof(current))) {
        char* nl = strpbrk(current, "\r\n");
        if (nl) *nl = '\0';
        if (strcmp(current, name) == 0) return;
    }
    write_file(LAST_MARKER, name, strlen(name));
}

bool save(const Scenario& sc, const char* name) {
    if (!s_ok || !name || !name[0]) return false;
    static char json[JSON_BUF_SIZE];
    size_t len = scenario_to_json(sc, json, sizeof(json));
    if (len == 0) return false;

    char path[80];
    scenario_path(name, path, sizeof(path));

    FsLock lock;
    if (!write_file(path, json, len)) return false;
    remember_last(name);
    return true;
}

bool load(const char* name, Scenario& out) {
    if (!s_ok || !name || !name[0]) return false;
    char path[80];
    scenario_path(name, path, sizeof(path));

    static char json[JSON_BUF_SIZE];
    {
        FsLock lock;
        if (!read_file(path, json, sizeof(json))) return false;
    }
    if (!scenario_from_json(json, out)) return false;

    FsLock lock;
    remember_last(name);
    return true;
}

void factory(Scenario& out) {
    if (s_ok) {
        static char json[JSON_BUF_SIZE];
        bool have;
        {
            FsLock lock;
            have = read_file(FACTORY_FILE, json, sizeof(json));
        }
        if (have && scenario_from_json(json, out)) return;
    }
    scenario_factory_default(out);
}

void load_startup(Scenario& out) {
    if (s_ok) {
        char name[app::SCENARIO_NAME_MAX] = {};
        {
            FsLock lock;
            read_file(LAST_MARKER, name, sizeof(name));
        }
        // Trim a possible trailing newline from hand-edited markers.
        char* nl = strpbrk(name, "\r\n");
        if (nl) *nl = '\0';
        if (name[0] && load(name, out)) return;
    }
    factory(out);
}

uint8_t list(char names[][app::SCENARIO_NAME_MAX], uint8_t max_names) {
    if (!s_ok) return 0;
    FsLock lock;
    DIR* dir = opendir(SCENARIO_DIR);
    if (!dir) return 0;

    uint8_t n = 0;
    for (dirent* e = readdir(dir); e && n < max_names; e = readdir(dir)) {
        const char* base = e->d_name;
        const char* ext = strstr(base, ".json");
        if (!ext || ext == base) continue;
        size_t len = static_cast<size_t>(ext - base);
        if (len >= app::SCENARIO_NAME_MAX) continue;
        std::memcpy(names[n], base, len);
        names[n][len] = '\0';
        ++n;
    }
    closedir(dir);
    return n;
}

} // namespace storage
