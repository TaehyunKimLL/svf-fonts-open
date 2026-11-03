/* disp_ssd1306.c - SSD1306 128 x 64 mono OLED over 4-wire SPI2 (ESP32-C3 / ESP32-S3), 10 MHz, mode 0. Chip select is
 * the SPI peripheral's; DC and RST are plain outputs. Every command and parameter byte is its own transmit with DC low;
 * the frame data goes with DC high and no prefix byte, in one transmit of rows * 16 bytes (display_show takes MONO_PAGE
 * pages: 128 bytes per 8 rows; the caller's buffer must be DMA-capable, as the band buffer is). Pins are the PIN_
 * defines (ESP32-C3; the ESP32-S3 pins under SVF_ESP32S3). */
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "display.h"
#include "esp_rst.h"

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

const char svf_port_driver_ssd1306[] = "ssd1306";

static spi_device_handle_t oled;

static void oled_send(int dc, const uint8_t *p, size_t n) /* one transmit, one CS frame; the frame is not split */
{
	spi_transaction_t tr;

	gpio_set_level(PIN_DC, dc); /* DC low: command byte, high: frame data */
	memset(&tr, 0, sizeof tr);
	tr.length = n * 8;
	tr.tx_buffer = p;
	ESP_ERROR_CHECK(spi_device_polling_transmit(oled, &tr));
}

static void oled_cmds(const uint8_t *cmds, size_t n)
{
	size_t i;

	for (i = 0; i < n; ++i)
		oled_send(0, &cmds[i], 1);
}

void display_init(void)
{
	static const uint8_t init[] = {
		0xAE,       /* display off */
		0xD5, 0x80, /* clock divide */
		0xA8, 0x3F, /* multiplex: 64 rows */
		0xD3, 0x00, /* display offset 0 */
		0x40,       /* start line 0 */
		0x8D, 0x14, /* charge pump on */
		0x20, 0x00, /* horizontal addressing: the frame is written page after page */
		0xA1, 0xC8, /* segment remap, COM scan reversed: (0, 0) top-left on the usual modules */
		0xDA, 0x12, /* COM pins */
		0x81, 0xCF, /* contrast */
		0xD9, 0xF1, /* precharge */
		0xDB, 0x40, /* VCOMH */
		0xA4, 0xA6, /* show RAM, not inverted */
		0xAF,       /* display on */
	};
	spi_bus_config_t bus = {
		.mosi_io_num = PIN_MOSI, .miso_io_num = -1, .sclk_io_num = PIN_SCLK,
		.quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = OLED_W * OLED_H / 8,
	};
	spi_device_interface_config_t dev = {
		.clock_speed_hz = 10 * 1000 * 1000, .mode = 0, .spics_io_num = PIN_CS, .queue_size = 1,
	};
	gpio_config_t out = {.pin_bit_mask = (1ULL << PIN_DC) | (1ULL << PIN_RST), .mode = GPIO_MODE_OUTPUT};
	volatile const char *marker = svf_port_driver_ssd1306;
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

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > OLED_H || (rows & 7) || (y & 7))
		return;
	window[0] = 0x21; /* columns 0 .. 127 */
	window[1] = 0x00;
	window[2] = OLED_W - 1;
	window[3] = 0x22; /* pages y / 8 .. (y + rows) / 8 - 1 */
	window[4] = (uint8_t)(y / 8);
	window[5] = (uint8_t)((y + rows) / 8 - 1);
	oled_cmds(window, sizeof window);
	oled_send(1, buf, (size_t)rows * OLED_W / 8);
}
