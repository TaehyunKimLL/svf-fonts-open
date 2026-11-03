/* Recording mode of the pico-sdk stand-ins (host checks only; not the SDK). With SVF_STUB_RECORD defined, gpio_put,
 * spi_write_blocking, i2c_write_blocking, sleep_ms and the hardware set-up calls report to the hooks below, which the
 * test (c/ports/check/test_drivers.c) implements; without it the stubs stay no-ops. The test defines EVERY hook
 * unconditionally, svf_rec_sleep and svf_rec_cfg included: the ESP32 stubs (c9edd36) must call or leave them, and the
 * ESP32 stub header must declare the same names so one test source links against either port. */
#ifndef STUB_SVF_STUB_RECORD_H
#define STUB_SVF_STUB_RECORD_H
#include <stddef.h>
#include <stdint.h>

void svf_rec_bytes(int dc, const uint8_t *p, size_t n);          /* one SPI write; dc = level of gpio svf_stub_dc_pin */
void svf_rec_gpio(int pin, int level);                           /* gpio_put */
void svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop);
void svf_rec_sleep(uint32_t ms);                                 /* sleep_ms: the test asserts the driver's delays */
/* Set-up calls: svf_rec_cfg(what, a, b, c, d) with the arguments in call order, unused ones 0:
 *   GPIO_INIT(pin)  GPIO_DIR(pin, out)  GPIO_FUNC(pin, function)  GPIO_PULL_UP(pin)
 *   SPI_INIT(baud)  SPI_FORMAT(bits, cpol, cpha, order)           I2C_INIT(baud) */
enum { SVF_CFG_GPIO_INIT = 1, SVF_CFG_GPIO_DIR, SVF_CFG_GPIO_FUNC, SVF_CFG_GPIO_PULL_UP, SVF_CFG_SPI_INIT,
       SVF_CFG_SPI_FORMAT, SVF_CFG_I2C_INIT };
void svf_rec_cfg(int what, int a, int b, int c, int d);
extern int svf_stub_dc_pin;

#endif
