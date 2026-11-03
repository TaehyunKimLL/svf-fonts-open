/* disp_ssd1306.c - SSD1306 128 x 64 mono OLED over I2C0 (Pico): SDA GP4, SCL GP5, address 0x3C. display_show takes
 * MONO_PAGE pages (128 bytes per 8 rows) and sends one 129-byte write per page (0x40, then the page); never a nostop
 * split: with the pico-sdk a nostop write followed by another puts a repeated START and the address on the bus, and the
 * SSD1306 would read the first frame byte as a control byte. */
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "pico/stdlib.h"
#include "display.h"

#include <string.h>

#define OLED_ADDR 0x3C

const char svf_port_driver_ssd1306[] = "ssd1306";

static uint8_t page[1 + OLED_W];

static void oled_cmds(const uint8_t *cmds, size_t n)
{
	uint8_t buf[2] = {0x00, 0}; /* control byte 0x00: a command follows */
	size_t i;

	for (i = 0; i < n; ++i) {
		buf[1] = cmds[i];
		i2c_write_blocking(i2c0, OLED_ADDR, buf, 2, false);
	}
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
	volatile const char *marker = svf_port_driver_ssd1306;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */

	(void)keep;
	i2c_init(i2c0, 400 * 1000);
	gpio_set_function(4, GPIO_FUNC_I2C);
	gpio_set_function(5, GPIO_FUNC_I2C);
	gpio_pull_up(4);
	gpio_pull_up(5);
	oled_cmds(init, sizeof init);
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	uint8_t window[6];
	int p;

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > OLED_H || (rows & 7) || (y & 7))
		return;
	window[0] = 0x21; /* columns 0 .. 127 */
	window[1] = 0x00;
	window[2] = OLED_W - 1;
	window[3] = 0x22; /* pages y / 8 .. (y + rows) / 8 - 1 */
	window[4] = (uint8_t)(y / 8);
	window[5] = (uint8_t)((y + rows) / 8 - 1);
	oled_cmds(window, sizeof window);
	page[0] = 0x40; /* control byte 0x40: data follows */
	for (p = 0; p < rows / 8; ++p) {
		memcpy(page + 1, buf + (size_t)p * OLED_W, OLED_W);
		i2c_write_blocking(i2c0, OLED_ADDR, page, sizeof page, false);
	}
}
