/* esp_rst.h - the RST low pulse of the ESP32 SPI drivers. vTaskDelay(n) returns after between n - 1 and n ticks (the
 * first tick is partial), so the shortest pulse is (n - 1) ticks. pdMS_TO_TICKS rounds down: it is one tick at the 100 Hz
 * default (a delay that can end at once) and 2 ticks (8 ms) at a 4 ms tick. With n = pdMS_TO_TICKS(10) + 2, n - 1 =
 * floor(10 / tick) + 1 ticks is more than 10 ms at every tick length (and n is at least 2). */
#ifndef ESP_RST_H
#define ESP_RST_H
#include "freertos/FreeRTOS.h"

#define ESP_RST_LOW_TICKS (pdMS_TO_TICKS(10) + 2)
#endif
