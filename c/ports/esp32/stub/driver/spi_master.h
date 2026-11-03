/* Compile-check stub of the ESP-IDF calls main/main.c makes (c/cross/build-all.sh --ports); not the SDK. */
#ifndef STUB_DRIVER_SPI_MASTER_H
#define STUB_DRIVER_SPI_MASTER_H
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/gpio.h"
typedef enum { SPI1_HOST, SPI2_HOST, SPI3_HOST } spi_host_device_t;
typedef enum { SPI_DMA_DISABLED = 0, SPI_DMA_CH_AUTO = 3 } spi_dma_chan_t;
typedef struct {
	int mosi_io_num, miso_io_num, sclk_io_num, quadwp_io_num, quadhd_io_num;
	int max_transfer_sz;
} spi_bus_config_t;
typedef struct {
	uint8_t mode;
	int clock_speed_hz, spics_io_num, queue_size;
} spi_device_interface_config_t;
#define SPI_TRANS_CS_KEEP_ACTIVE (1u << 8) /* IDF: SPI_TRANS_CS_KEEP_ACTIVE = BIT(8) (BIT(10) is SPI_TRANS_MODE_OCT); keep CS asserted after this transaction (bus must be acquired) */
typedef struct {
	uint32_t flags;
	size_t length; /* bits */
	const void *tx_buffer;
} spi_transaction_t;
typedef struct spi_device_t *spi_device_handle_t;
#ifdef SVF_STUB_RECORD
/* Chip-select model, one copy per translation unit like the GPIO levels: CS is asserted for a transaction and released
 * after it unless SPI_TRANS_CS_KEEP_ACTIVE (which needs the bus acquired); releasing the bus leaves CS as it is. */
static int svf_stub_cs, svf_stub_bus;
#endif
static inline esp_err_t spi_bus_initialize(spi_host_device_t h, const spi_bus_config_t *c, spi_dma_chan_t dma)
{
#ifdef SVF_STUB_RECORD
	if (c) {
		svf_rec_cfg(SVF_CFG_SPI_HOST, (int)h, (int)dma, 0, 0);
		svf_rec_cfg(SVF_CFG_SPI_BUS, c->mosi_io_num, c->sclk_io_num, c->max_transfer_sz, c->miso_io_num);
	}
#else
	(void)h; (void)dma;
#endif
	return c ? ESP_OK : ESP_FAIL;
}
static inline esp_err_t spi_bus_add_device(spi_host_device_t h, const spi_device_interface_config_t *c,
                                           spi_device_handle_t *d)
{
#ifdef SVF_STUB_RECORD
	if (c) {
		svf_rec_cfg(SVF_CFG_SPI_DEV_HOST, (int)h, 0, 0, 0);
		svf_rec_cfg(SVF_CFG_SPI_DEV, c->clock_speed_hz, c->mode, c->spics_io_num, c->queue_size);
	}
#else
	(void)h;
#endif
	*d = 0;
	return c ? ESP_OK : ESP_FAIL;
}
static inline esp_err_t spi_device_polling_transmit(spi_device_handle_t d, spi_transaction_t *t)
{
	(void)d;
	if (!t->tx_buffer || t->length == 0)
		return ESP_FAIL; /* nothing to send: not recorded */
#ifdef SVF_STUB_RECORD
	if ((t->flags & SPI_TRANS_CS_KEEP_ACTIVE) && !svf_stub_bus)
		return ESP_ERR_INVALID_ARG; /* as IDF: keeping CS active needs spi_device_acquire_bus; nothing is sent */
	{
		int before = svf_stub_cs;

		svf_stub_cs = (t->flags & SPI_TRANS_CS_KEEP_ACTIVE) != 0;
		svf_rec_bytes(svf_stub_gpio_level[svf_stub_dc_pin & 63], (const uint8_t *)t->tx_buffer, t->length / 8);
		svf_rec_spi_cs(before, svf_stub_cs, svf_stub_bus);
		/* CS is asserted during every transaction (before or not); only KEEP_ACTIVE leaves it so afterwards */
	}
#endif
	return ESP_OK;
}
static inline esp_err_t spi_device_acquire_bus(spi_device_handle_t d, uint32_t ticks_to_wait)
{
	(void)d; (void)ticks_to_wait;
#ifdef SVF_STUB_RECORD
	svf_stub_bus = 1;
	svf_rec_bus(1);
#endif
	return ESP_OK;
}
static inline void spi_device_release_bus(spi_device_handle_t d)
{
	(void)d;
#ifdef SVF_STUB_RECORD
	svf_stub_bus = 0; /* CS is not touched: as IDF, a kept-active CS stays asserted until a transaction without the flag */
	svf_rec_bus(0);
#endif
}
#endif
