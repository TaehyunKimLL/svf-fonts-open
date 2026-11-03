/* disp_ssd1327.c - SSD1327 128 x 128 16-level grey OLED over I2C0 (Pico): SDA GP4, SCL GP5, address 0x3C. display_show takes
 * GRAY8 rows and packs four at a time (grey_pack_rows) into a 257-byte chunk (0x40, then 256 panel bytes), one
 * i2c_write_blocking each; never a nostop split. */
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "pico/stdlib.h"
#include "display.h"
#include "grey_pack.h"

#define OLED_ADDR 0x3C

const char svf_port_driver_ssd1327[] = "ssd1327";

static uint8_t chunk[1 + 4 * GREY_W / 2];

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
	volatile const char *marker = svf_port_driver_ssd1327;
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
	chunk[0] = 0x40; /* control byte 0x40: data follows */
	for (r = 0; r < rows; r += 4) {
		grey_pack_rows(buf + (size_t)r * GREY_W, GREY_W, GREY_W, 4, chunk + 1);
		i2c_write_blocking(i2c0, OLED_ADDR, chunk, sizeof chunk, false);
	}
}
