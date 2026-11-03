/* Compile-check stub of the ESP-IDF calls main/main.c makes (c/cross/build-all.sh --ports); not the SDK. */
#ifndef STUB_DRIVER_GPIO_H
#define STUB_DRIVER_GPIO_H
#include <stdint.h>
#include "esp_err.h"
#ifdef SVF_STUB_RECORD
#include "svf_stub_record.h"
/* One copy per translation unit; correct because a driver calls gpio_set_level and spi_device_polling_transmit from the
 * same TU (every driver is one .c file). */
static uint8_t svf_stub_gpio_level[64];
#endif
typedef int gpio_num_t;
typedef enum { GPIO_MODE_DISABLE = 0, GPIO_MODE_OUTPUT = 2 } gpio_mode_t;
typedef struct {
	uint64_t pin_bit_mask;
	gpio_mode_t mode;
	int pull_up_en, pull_down_en, intr_type;
} gpio_config_t;
static inline esp_err_t gpio_config(const gpio_config_t *c)
{
#ifdef SVF_STUB_RECORD
	if (c)
		svf_rec_cfg(SVF_CFG_GPIO_OUT, (int)(uint32_t)c->pin_bit_mask, (int)(uint32_t)(c->pin_bit_mask >> 32),
		            (int)c->mode, 0);
#endif
	return c ? ESP_OK : ESP_FAIL;
}
static inline esp_err_t gpio_set_level(gpio_num_t pin, uint32_t level)
{
#ifdef SVF_STUB_RECORD
	svf_stub_gpio_level[pin & 63] = (uint8_t)level;
	svf_rec_gpio((int)pin, (int)level);
#else
	(void)pin; (void)level;
#endif
	return ESP_OK;
}
#endif
