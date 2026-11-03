/* Compile-check stub of the pico-sdk SPI calls the port makes (c/cross/build-all.sh --ports); not the SDK.
 * Under SVF_STUB_RECORD spi_write_blocking reports the bytes with the level of gpio svf_stub_dc_pin. */
#ifndef STUB_HARDWARE_SPI_H
#define STUB_HARDWARE_SPI_H
#include "hardware/gpio.h"
typedef struct spi_inst spi_inst_t;
#define spi0 ((spi_inst_t *)0)
typedef enum { SPI_CPOL_0 = 0, SPI_CPOL_1 = 1 } spi_cpol_t;
typedef enum { SPI_CPHA_0 = 0, SPI_CPHA_1 = 1 } spi_cpha_t;
typedef enum { SPI_LSB_FIRST = 0, SPI_MSB_FIRST = 1 } spi_order_t;
static inline unsigned spi_init(spi_inst_t *spi, unsigned baudrate)
{
	(void)spi;
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_SPI_INIT, (int)baudrate, 0, 0, 0);
#endif
	return baudrate;
}
static inline void spi_set_format(spi_inst_t *spi, unsigned data_bits, spi_cpol_t cpol, spi_cpha_t cpha, spi_order_t order)
{
	(void)spi;
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_SPI_FORMAT, (int)data_bits, (int)cpol, (int)cpha, (int)order);
#else
	(void)data_bits; (void)cpol; (void)cpha; (void)order;
#endif
}
static inline int spi_write_blocking(spi_inst_t *spi, const uint8_t *src, size_t len)
{
	(void)spi;
#ifdef SVF_STUB_RECORD
	svf_rec_bytes(svf_stub_gpio_level[svf_stub_dc_pin & 31], src, len);
#else
	(void)src;
#endif
	return (int)len;
}
#endif
