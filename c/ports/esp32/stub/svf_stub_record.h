/* Recording mode of the ESP-IDF stand-ins (host checks only; not the SDK). With SVF_STUB_RECORD defined,
 * gpio_set_level, spi_device_polling_transmit, vTaskDelay and the set-up calls report to the hooks below, which the
 * test (c/ports/check/test_drivers.c) implements; without it the stubs stay no-ops. The names are those of the Pico
 * stub header (c/ports/pico/stub/svf_stub_record.h), so one test source links against either port; the ESP32 has no
 * I2C hook calls, but the declaration is kept so the test compiles. The first seven SVF_CFG_* values equal the
 * Pico's; the ESP-IDF set-up calls add the rest. */
#ifndef STUB_SVF_STUB_RECORD_H
#define STUB_SVF_STUB_RECORD_H
#include <stddef.h>
#include <stdint.h>

void svf_rec_bytes(int dc, const uint8_t *p, size_t n);          /* one SPI transmit; dc = level of gpio svf_stub_dc_pin */
void svf_rec_gpio(int pin, int level);                           /* gpio_set_level */
void svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop);
void svf_rec_sleep(uint32_t ms);                                 /* vTaskDelay(ticks): ticks * SVF_STUB_TICK_MS (a 100 Hz tick) */
/* ESP32 only (the Pico stub header has neither): the chip-select and bus model of spi_master.h. svf_rec_spi_cs follows
 * the svf_rec_bytes of the same transmit: CS level before it, CS level after it (1 = asserted; stays 1 only with
 * SPI_TRANS_CS_KEEP_ACTIVE), and whether the bus was held by spi_device_acquire_bus. svf_rec_bus: acquire (1) / release (0). */
void svf_rec_spi_cs(int cs_before, int cs_after, int bus_held);
void svf_rec_bus(int acquired);
/* Set-up calls: svf_rec_cfg(what, a, b, c, d) with the arguments in call order, unused ones 0:
 *   SPI_HOST(host, dma)                         spi_bus_initialize, first
 *   SPI_BUS(mosi, sclk, max_transfer_sz, miso)  spi_bus_initialize, second
 *   SPI_DEV_HOST(host)                          spi_bus_add_device, first (must equal SPI_HOST's host)
 *   SPI_DEV(clock_hz, mode, cs, queue_size)     spi_bus_add_device, second
 *   GPIO_OUT(mask_low32, mask_high32, mode)     gpio_config (pin_bit_mask split in two, then the mode)
 * The Pico names stay declared so the shared test compiles; the ESP32 stubs never report them. */
enum { SVF_CFG_GPIO_INIT = 1, SVF_CFG_GPIO_DIR, SVF_CFG_GPIO_FUNC, SVF_CFG_GPIO_PULL_UP, SVF_CFG_SPI_INIT,
       SVF_CFG_SPI_FORMAT, SVF_CFG_I2C_INIT, SVF_CFG_SPI_HOST, SVF_CFG_SPI_BUS, SVF_CFG_SPI_DEV, SVF_CFG_GPIO_OUT,
       SVF_CFG_SPI_DEV_HOST };
void svf_rec_cfg(int what, int a, int b, int c, int d);
extern int svf_stub_dc_pin;

#endif
