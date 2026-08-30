// spi_bus.cpp
#include "spi_bus.h"
#include "board_config.h"
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace hal {

static SemaphoreHandle_t s_mutex = nullptr;

void spi_bus_init() {
    if (s_mutex) return;
    s_mutex = xSemaphoreCreateRecursiveMutex();
    SPI.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI);
}

void spi_lock()   { xSemaphoreTakeRecursive(s_mutex, portMAX_DELAY); }
void spi_unlock() { xSemaphoreGiveRecursive(s_mutex); }

} // namespace hal
