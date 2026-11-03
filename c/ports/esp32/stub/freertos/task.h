/* Compile-check stub of the ESP-IDF calls main/main.c makes (c/cross/build-all.sh --ports); not the SDK. */
#ifndef STUB_FREERTOS_TASK_H
#define STUB_FREERTOS_TASK_H
#include "FreeRTOS.h"
#ifdef SVF_STUB_RECORD
#include "svf_stub_record.h"
#endif
static inline void vTaskDelay(TickType_t ticks)
{
#ifdef SVF_STUB_RECORD
	svf_rec_sleep(ticks * SVF_STUB_TICK_MS);
#else
	(void)ticks;
#endif
}
#endif
