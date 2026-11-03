/* disp_ili9341.c - ILI9341 320 x 240 RGB565 over SPI2 (ESP32-C3 / ESP32-S3), 40 MHz, mode 0. Chip select is the SPI
 * peripheral's (spics_io_num); DC and RST are plain outputs. The panel takes RGB565 high byte first
 * (display_565_bigendian = 1). Pins are the PIN_ defines (ESP32-C3; the ESP32-S3 pins under SVF_ESP32S3). */
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

const char svf_port_driver_ili9341[] = "ili9341";
const uint8_t display_565_bigendian = 1;

static spi_device_handle_t lcd;

/* keep: leave chip select asserted after this transmit (SPI_TRANS_CS_KEEP_ACTIVE; the bus must be acquired) */
static void lcd_send(int dc, const uint8_t *p, size_t n, int keep)
{
	spi_transaction_t tr;

	if (n == 0)
		return;
	gpio_set_level(PIN_DC, dc); /* DC low: command byte, high: data */
	memset(&tr, 0, sizeof tr);
	tr.flags = keep ? SPI_TRANS_CS_KEEP_ACTIVE : 0;
	tr.length = n * 8;
	tr.tx_buffer = p;
	ESP_ERROR_CHECK(spi_device_polling_transmit(lcd, &tr));
}

static void lcd_cmd(uint8_t cmd, const uint8_t *data, size_t n)
{
	lcd_send(0, &cmd, 1, 0);
	lcd_send(1, data, n, 0);
}

void display_init(void)
{
	spi_bus_config_t bus = {
		.mosi_io_num = PIN_MOSI, .miso_io_num = -1, .sclk_io_num = PIN_SCLK,
		.quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = PORT_LCD_W * LINE_H * 2,
	};
	spi_device_interface_config_t dev = {
		.clock_speed_hz = 40 * 1000 * 1000, .mode = 0, .spics_io_num = PIN_CS, .queue_size = 1,
	};
	gpio_config_t out = {.pin_bit_mask = (1ULL << PIN_DC) | (1ULL << PIN_RST), .mode = GPIO_MODE_OUTPUT};
	uint8_t colmod = 0x55; /* 16 bits a pixel */
	uint8_t madctl = 0x28; /* row/column exchange (landscape 320 x 240), BGR panel */
	volatile const char *marker = svf_port_driver_ili9341;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */

	(void)keep;
	ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
	ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &dev, &lcd));
	ESP_ERROR_CHECK(gpio_config(&out));
	gpio_set_level(PIN_RST, 0);
	vTaskDelay(ESP_RST_LOW_TICKS); /* at least 10 ms, not a tick that can end at once */
	gpio_set_level(PIN_RST, 1);
	vTaskDelay(pdMS_TO_TICKS(120));
	lcd_cmd(0x11, NULL, 0); /* sleep out */
	vTaskDelay(pdMS_TO_TICKS(120));
	lcd_cmd(0x3A, &colmod, 1);
	lcd_cmd(0x36, &madctl, 1);
	lcd_cmd(0x29, NULL, 0); /* display on */
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	uint8_t col[4] = {0x00, 0x00, (PORT_LCD_W - 1) >> 8, (PORT_LCD_W - 1) & 0xFF}, row[4];
	uint8_t ramwr = 0x2C;
	int end, r, n;

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > PORT_LCD_H)
		return;
	end = y + rows - 1;
	row[0] = (uint8_t)(y >> 8);
	row[1] = (uint8_t)y;
	row[2] = (uint8_t)(end >> 8);
	row[3] = (uint8_t)end;

	/* One RAMWR is one chip-select frame: the panel ends the memory write when CS rises, so CS stays low from the
	 * RAMWR command through the last pixel chunk. A device transaction releases CS at its end unless it carries
	 * SPI_TRANS_CS_KEEP_ACTIVE, and that flag needs the bus held (spi_device_acquire_bus), or another device or task
	 * could take the bus between chunks. So: acquire, every transmit from RAMWR on but the last keeps CS active, the
	 * last one lets it go, release. */
	ESP_ERROR_CHECK(spi_device_acquire_bus(lcd, portMAX_DELAY));
	lcd_cmd(0x2A, col, 4); /* column window */
	lcd_cmd(0x2B, row, 4); /* row window */
	lcd_send(0, &ramwr, 1, 1); /* write memory: the pixels follow, CS kept */
	/* the pixels in transmits of at most LINE_H rows: max_transfer_sz is one band, and RAMWR goes on across them */
	for (r = 0; r < rows; r += n) {
		n = rows - r < LINE_H ? rows - r : LINE_H;
		lcd_send(1, buf + (size_t)r * PORT_LCD_W * 2, (size_t)n * PORT_LCD_W * 2, r + n < rows);
	}
	spi_device_release_bus(lcd);
}
