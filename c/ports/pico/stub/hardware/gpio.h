/* Compile-check stub of the pico-sdk gpio calls the port makes (c/cross/build-all.sh --ports); not the SDK.
 * Under SVF_STUB_RECORD gpio_put keeps the pin level and reports it (svf_stub_record.h). */
#ifndef STUB_HARDWARE_GPIO_H
#define STUB_HARDWARE_GPIO_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef SVF_STUB_RECORD
#include "svf_stub_record.h"
#endif
#define GPIO_OUT 1
#define GPIO_IN 0
enum gpio_function { GPIO_FUNC_SPI = 1, GPIO_FUNC_I2C = 3 };
#ifdef SVF_STUB_RECORD
/* One copy per translation unit. That is correct because a driver calls gpio_put and spi_write_blocking from the same
 * TU (every driver is one .c file); a driver split over TUs would read a stale DC level here. */
static uint8_t svf_stub_gpio_level[32];
#endif
static inline void gpio_init(unsigned gpio)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_GPIO_INIT, (int)gpio, 0, 0, 0);
#else
	(void)gpio;
#endif
}
static inline void gpio_set_dir(unsigned gpio, bool out)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_GPIO_DIR, (int)gpio, out, 0, 0);
#else
	(void)gpio; (void)out;
#endif
}
static inline void gpio_put(unsigned gpio, bool value)
{
#ifdef SVF_STUB_RECORD
	svf_stub_gpio_level[gpio & 31] = value;
	svf_rec_gpio((int)gpio, value);
#else
	(void)gpio; (void)value;
#endif
}
static inline void gpio_set_function(unsigned gpio, enum gpio_function fn)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_GPIO_FUNC, (int)gpio, (int)fn, 0, 0);
#else
	(void)gpio; (void)fn;
#endif
}
static inline void gpio_pull_up(unsigned gpio)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_GPIO_PULL_UP, (int)gpio, 0, 0, 0);
#else
	(void)gpio;
#endif
}
#endif
