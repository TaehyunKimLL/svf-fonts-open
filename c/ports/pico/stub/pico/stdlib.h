/* Compile-check stub of the pico-sdk calls main.c makes (c/cross/build-all.sh --ports); not the SDK.
 * Like the SDK's, it includes hardware/gpio.h. Under SVF_STUB_RECORD sleep_ms reports the delay. */
#ifndef STUB_PICO_STDLIB_H
#define STUB_PICO_STDLIB_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "hardware/gpio.h"
static inline void sleep_ms(uint32_t ms)
{
#ifdef SVF_STUB_RECORD
	svf_rec_sleep(ms);
#else
	(void)ms;
#endif
}
static inline void tight_loop_contents(void) {}
#endif
