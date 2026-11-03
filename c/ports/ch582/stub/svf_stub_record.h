/* Recording mode of the CH58x SDK stand-ins (host checks only; not the SDK). With SVF_STUB_RECORD defined, the set-up
 * calls of CH58x_common.h and the delay report to the hooks below, which the test (c/ports/check/test_drivers.c)
 * implements; without it the stubs stay no-ops. The test defines EVERY hook unconditionally, as for the Pico and ESP32
 * stubs (same names, same first seven SVF_CFG_* values), so one test source links against any port. */
#ifndef STUB_SVF_STUB_RECORD_H
#define STUB_SVF_STUB_RECORD_H
#include <stddef.h>
#include <stdint.h>

void svf_rec_bytes(int dc, const uint8_t *p, size_t n);          /* the Pico's SPI write (not used by this port) */
void svf_rec_gpio(int pin, int level);                           /* GPIOB_SetBits / ResetBits / InverseBits */
void svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop); /* the test's ch582_i2c_write */
void svf_rec_sleep(uint32_t ms);                                 /* DelayMs: the test asserts the driver's delays */
/* Set-up calls: svf_rec_cfg(what, a, b, c, d) with the arguments in call order, unused ones 0:
 *   (1 .. 7 the Pico's)
 *   PIN_REMAP(state, perph)  GPIOB_MODE(pin mask, mode)  CH58X_I2C(speed, duty, ack, ack address)  SYSCLK(source) */
enum { SVF_CFG_GPIO_INIT = 1, SVF_CFG_GPIO_DIR, SVF_CFG_GPIO_FUNC, SVF_CFG_GPIO_PULL_UP, SVF_CFG_SPI_INIT,
       SVF_CFG_SPI_FORMAT, SVF_CFG_I2C_INIT, SVF_CFG_PIN_REMAP, SVF_CFG_GPIOB_MODE, SVF_CFG_CH58X_I2C,
       SVF_CFG_SYSCLK };
void svf_rec_cfg(int what, int a, int b, int c, int d);
extern int svf_stub_dc_pin;

#endif
