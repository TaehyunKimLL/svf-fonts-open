/* disp_ssd1327.c - SSD1327 128 x 128 16-level grey OLED over 4-wire SPI2 (ESP32-C3 / ESP32-S3), 10 MHz, mode 0. Chip
 * select is the SPI peripheral's; DC and RST are plain outputs. Every command and parameter byte is its own transmit
 * with DC low; the frame data goes with DC high and no prefix byte (there is no 0x40 control byte on SPI). display_show
 * takes GRAY8 rows and packs four at a time (grey_pack_rows) into a 256-byte transmit. Pins are the PIN_ defines
 * (ESP32-C3; the ESP32-S3 pins under SVF_ESP32S3). */
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "display.h"
#include "esp_rst.h"
#include "grey_pack.h"

#include <string.h>

#if SVF_ESP32S3
#define PIN_MOSI 11
#define PIN_SCLK 12
#define PIN_CS 10
#define PIN_DC 4
#define PIN_RST 5
#else
#define PIN_MOSI 7
#define PIN_SCLK 6
#define PIN_CS 10
#define PIN_DC 2
#define PIN_RST 3
#endif

const char svf_port_driver_ssd1327[] = "ssd1327";

static spi_device_handle_t oled;
static uint8_t chunk[4 * GREY_W / 2]; /* static: internal RAM, which SPI DMA can read */

/* keep: leave chip select asserted after this transmit (SPI_TRANS_CS_KEEP_ACTIVE; the bus must be acquired) */
static void oled_send(int dc, const uint8_t *p, size_t n, int keep)
{
	spi_transaction_t tr;

	gpio_set_level(PIN_DC, dc); /* DC low: command byte, high: frame data */
	memset(&tr, 0, sizeof tr);
	tr.flags = keep ? SPI_TRANS_CS_KEEP_ACTIVE : 0;
	tr.length = n * 8;
	tr.tx_buffer = p;
	ESP_ERROR_CHECK(spi_device_polling_transmit(oled, &tr));
}

static void oled_cmds(const uint8_t *cmds, size_t n)
{
	size_t i;

	for (i = 0; i < n; ++i)
		oled_send(0, &cmds[i], 1, 0);
}

void display_init(void)
{
	static const uint8_t init[] = {
		0xAE,       /* display off */
		0xA0, 0x51, /* remap: column address remap, the pixel order grey_pack_rows packs */
		0xA8, 0x7F, /* multiplex: 128 rows */
		0xA1, 0x00, /* start line 0 */
		0xA2, 0x00, /* display offset 0 */
		0x81, 0x7F, /* contrast */
		0xB1, 0xF1, /* phase length */
		0xBC, 0x08, /* precharge voltage */
		0xA4,       /* show RAM */
		0xAF,       /* display on */
	};
	spi_bus_config_t bus = {
		.mosi_io_num = PIN_MOSI, .miso_io_num = -1, .sclk_io_num = PIN_SCLK,
		.quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = sizeof chunk,
	};
	spi_device_interface_config_t dev = {
		.clock_speed_hz = 10 * 1000 * 1000, .mode = 0, .spics_io_num = PIN_CS, .queue_size = 1,
	};
	gpio_config_t out = {.pin_bit_mask = (1ULL << PIN_DC) | (1ULL << PIN_RST), .mode = GPIO_MODE_OUTPUT};
	volatile const char *marker = svf_port_driver_ssd1327;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */

	(void)keep;
	ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
	ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &oled));
	ESP_ERROR_CHECK(gpio_config(&out));
	gpio_set_level(PIN_RST, 0);
	vTaskDelay(ESP_RST_LOW_TICKS); /* at least 10 ms, not a tick that can end at once */
	gpio_set_level(PIN_RST, 1);
	vTaskDelay(pdMS_TO_TICKS(10));
	oled_cmds(init, sizeof init);
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	uint8_t window[6];
	int r;

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > GREY_H || (rows & 3))
		return;
	window[0] = 0x15; /* columns 0 .. 63 (two pixels a column) */
	window[1] = 0x00;
	window[2] = GREY_W / 2 - 1;
	window[3] = 0x75; /* rows y .. y + rows - 1 */
	window[4] = (uint8_t)y;
	window[5] = (uint8_t)(y + rows - 1);
	oled_cmds(window, sizeof window);
	/* the frame data is split into 256-byte transmits: one CS frame, held (bus acquired) through all but the last */
	ESP_ERROR_CHECK(spi_device_acquire_bus(oled, portMAX_DELAY));
	for (r = 0; r < rows; r += 4) {
		grey_pack_rows(buf + (size_t)r * GREY_W, GREY_W, GREY_W, 4, chunk);
		oled_send(1, chunk, sizeof chunk, r + 4 < rows);
	}
	spi_device_release_bus(oled);
}
