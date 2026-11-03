/* disp_st7789.c - ST7789 240 x 240 RGB565 over SPI0 (Pico). MOSI GP19 and SCK GP18 are on GPIO_FUNC_SPI; CS GP17, DC GP16
 * and RST GP20 are plain outputs. The panel takes RGB565 high byte first (display_565_bigendian = 1). */
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include "display.h"

#define PIN_MOSI 19
#define PIN_SCK 18
#define PIN_CS 17
#define PIN_DC 16
#define PIN_RST 20

const char svf_port_driver_st7789[] = "st7789";
const uint8_t display_565_bigendian = 1;

/* One command in its own chip-select transaction (init). DC is low for the command byte, high for its parameters. */
static void cmd_cs(uint8_t c, const uint8_t *arg, size_t n)
{
	gpio_put(PIN_CS, 0);
	gpio_put(PIN_DC, 0);
	spi_write_blocking(spi0, &c, 1);
	if (n) {
		gpio_put(PIN_DC, 1);
		spi_write_blocking(spi0, arg, n);
	}
	gpio_put(PIN_CS, 1);
}

void display_init(void)
{
	static const uint8_t colmod[] = {0x55}; /* 16 bits a pixel */
	static const uint8_t madctl[] = {0x00}; /* normal orientation, RGB order */
	volatile const char *marker = svf_port_driver_st7789;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */

	(void)keep;
	spi_init(spi0, 32 * 1000 * 1000);
	spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
	gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
	gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
	gpio_init(PIN_CS);
	gpio_set_dir(PIN_CS, GPIO_OUT);
	gpio_put(PIN_CS, 1);
	gpio_init(PIN_DC);
	gpio_set_dir(PIN_DC, GPIO_OUT);
	gpio_init(PIN_RST);
	gpio_set_dir(PIN_RST, GPIO_OUT);

	/* Hardware reset, then the start-up delays by sleep_ms: 120 ms after SWRESET and 120 ms after SLPOUT.
	 * The 120 ms after SWRESET is not just the command's own 5 ms: it also covers the reset's settle time tRT
	 * (up to 120 ms when the panel was in Sleep Out), which the 1 ms after RST high does not. Do not shorten it. */
	gpio_put(PIN_RST, 0);
	sleep_ms(1);
	gpio_put(PIN_RST, 1);
	sleep_ms(1);
	cmd_cs(0x01, 0, 0); /* SWRESET */
	sleep_ms(120);
	cmd_cs(0x11, 0, 0); /* SLPOUT */
	sleep_ms(120);
	cmd_cs(0x3A, colmod, sizeof colmod); /* COLMOD */
	cmd_cs(0x36, madctl, sizeof madctl); /* MADCTL */
	cmd_cs(0x21, 0, 0); /* INVON: the usual IPS modules */
	cmd_cs(0x29, 0, 0); /* DISPON */
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	uint8_t col[4] = {0x00, 0x00, (PORT_LCD_W - 1) >> 8, (PORT_LCD_W - 1) & 0xFF}, row[4];
	int end;
	uint8_t c;

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > PORT_LCD_H)
		return;
	end = y + rows - 1;
	row[0] = (uint8_t)(y >> 8);
	row[1] = (uint8_t)y;
	row[2] = (uint8_t)(end >> 8);
	row[3] = (uint8_t)end;

	gpio_put(PIN_CS, 0);
	gpio_put(PIN_DC, 0);
	c = 0x2A; /* CASET */
	spi_write_blocking(spi0, &c, 1);
	gpio_put(PIN_DC, 1);
	spi_write_blocking(spi0, col, 4);
	gpio_put(PIN_DC, 0);
	c = 0x2B; /* RASET */
	spi_write_blocking(spi0, &c, 1);
	gpio_put(PIN_DC, 1);
	spi_write_blocking(spi0, row, 4);
	gpio_put(PIN_DC, 0);
	c = 0x2C; /* RAMWR */
	spi_write_blocking(spi0, &c, 1);
	gpio_put(PIN_DC, 1);
	spi_write_blocking(spi0, buf, (size_t)rows * PORT_LCD_W * 2);
	gpio_put(PIN_CS, 1);
}
