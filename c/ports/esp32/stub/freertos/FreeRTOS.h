/* Compile-check stub of the ESP-IDF calls main/main.c makes (c/cross/build-all.sh --ports); not the SDK. */
#ifndef STUB_FREERTOS_H
#define STUB_FREERTOS_H
#include <stdint.h>
typedef uint32_t TickType_t;
/* A 100 Hz tick (the IDF default CONFIG_FREERTOS_HZ): pdMS_TO_TICKS(10) is one tick, which can elapse almost at once */
#ifndef SVF_STUB_TICK_MS /* a test may set another rate: 10 = 100 Hz, 1 = 1000 Hz */
#define SVF_STUB_TICK_MS 10
#endif
#define pdMS_TO_TICKS(ms) ((TickType_t)((ms) / SVF_STUB_TICK_MS))
#define portMAX_DELAY ((TickType_t)0xFFFFFFFFu)
#endif
