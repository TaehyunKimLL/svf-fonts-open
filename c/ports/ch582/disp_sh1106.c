/* disp_sh1106.c - SH1106 128 x 64 mono OLED over the CH582's hardware I2C (YD-CH582M): SDA PB20, SCL PB21 (the I2C
 * pin remap), address 0x3C. display_show takes MONO_PAGE pages (128 bytes per 8 rows). The SH1106 has 132 columns of
 * RAM and no horizontal addressing mode: every page is sent as its own three commands (page, column low, column
 * high) and one 129-byte data write (0x40, then the page); the 128 visible columns start at column SH1106_COL_OFFSET.
 * With -DOLED_SSD1306=1 the same driver runs an SSD1306 module: its own charge pump (8D 14) instead of the SH1106's
 * DC-DC (AD 8B) and pump voltage (32), page addressing mode (20 02: the per-page stream is the same), RAM column 0.
 * display_init waits for the panel's reset recovery, writes zeros to all 8 pages of RAM (132 columns: the power-on RAM
 * is noise) and only then switches the display on.
 * Every write goes through ch582_i2c_write, which is bounded: the first one that fails (no panel, wrong address, stuck
 * bus) sets DISPLAY_I2C_FAILED and the driver sends nothing more until the next display_init. */
#include "CH58x_common.h"
#include "display.h"
#include "i2c.h"

#include <string.h>

#define OLED_ADDR 0x3C

#ifndef OLED_SSD1306
#define OLED_SSD1306 0 /* 1: the controller is an SSD1306 (a module sold as SH1106 that is one; see the README) */
#endif
#ifndef SH1106_COL_OFFSET
#define SH1106_COL_OFFSET (OLED_SSD1306 ? 0 : 2) /* RAM column of the first visible column: 2 on the usual 132-column
                                                  * SH1106 modules, 0 on an SH1106 whose RAM starts at the first one and
                                                  * on an SSD1306 */
#endif
#ifndef SH1106_REMAP
#define SH1106_REMAP 1 /* 1: segment remap 0xA1 + COM scan reversed 0xC8 ((0, 0) top-left on the usual modules);
                        * 0: 0xA0 + 0xC0 (a module mounted the other way up) */
#endif
#ifndef SH1106_RESET_MS
#define SH1106_RESET_MS 20 /* after power-up, before the first command (RES rises through an RC on the module; the
                            * SH1106 needs up to 2 ms after RES) */
#endif
#ifndef SH1106_ON_DELAY_MS
#define SH1106_ON_DELAY_MS 100 /* after display on: the charge pump settles */
#endif

const char svf_port_driver_sh1106[] = "sh1106";

#define RAM_COLS 132 /* the SH1106's RAM width (the SSD1306 wraps the extra four columns in page mode) */
static uint8_t page[1 + RAM_COLS];
static int state = DISPLAY_IDLE;

/* one command, with its argument when @p arg is not NO_ARG, in one write behind the control byte 0x00; the first
 * failure latches the state, and nothing is sent while it is set */
#define NO_ARG (-1)
static int oled_cmd(uint8_t c, int arg)
{
	uint8_t buf[3];

	if (state == DISPLAY_I2C_FAILED)
		return -1;
	buf[0] = 0x00; /* control byte 0x00: a command follows */
	buf[1] = c;
	buf[2] = (uint8_t)arg;
	if (ch582_i2c_write(OLED_ADDR, buf, arg == NO_ARG ? 2 : 3)) {
		state = DISPLAY_I2C_FAILED;
		return -1;
	}
	return 0;
}

int display_state(void)
{
	return state;
}

void display_init(void)
{
	static const struct { uint8_t cmd; int16_t arg; } init[] = {
		{0xAE, NO_ARG}, /* display off */
		{0xD5, 0x80},   /* clock divide / oscillator frequency */
		{0xA8, 0x3F},   /* multiplex: 64 rows */
		{0xD3, 0x00},   /* display offset 0 */
		{0x40, NO_ARG}, /* start line 0 */
#if OLED_SSD1306
		{0x8D, 0x14},   /* charge pump on (internal VCC) */
		{0x20, 0x02},   /* page addressing mode */
#else
		{0xAD, 0x8B},   /* DC-DC on */
		{0x32, NO_ARG}, /* pump voltage 8.0 V */
#endif
#if SH1106_REMAP
		{0xA1, NO_ARG}, /* segment remap */
		{0xC8, NO_ARG}, /* COM scan reversed: (0, 0) top-left on the usual modules */
#else
		{0xA0, NO_ARG},
		{0xC0, NO_ARG},
#endif
		{0xDA, 0x12},   /* COM pins */
#if OLED_SSD1306
		{0x81, 0xCF},   /* contrast (the values of the Pico SSD1306 driver, for the internal charge pump) */
		{0xD9, 0xF1},   /* precharge */
		{0xDB, 0x40},   /* VCOMH */
#else
		{0x81, 0x80},   /* contrast */
		{0xD9, 0x22},   /* precharge */
		{0xDB, 0x35},   /* VCOMH */
#endif
		{0xA4, NO_ARG}, /* show RAM */
		{0xA6, NO_ARG}, /* not inverted */
	};
	volatile const char *marker = svf_port_driver_sh1106;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */
	size_t i;
	int p;

	(void)keep;
	state = DISPLAY_IDLE;
	GPIOPinRemap(ENABLE, RB_PIN_I2C);
	GPIOB_ModeCfg(GPIO_Pin_20 | GPIO_Pin_21, GPIO_ModeIN_PU);
	I2C_Init(I2C_Mode_I2C, 400000, I2C_DutyCycle_2, I2C_Ack_Enable, I2C_AckAddr_7bit, 0);
	DelayMs(SH1106_RESET_MS);
	for (i = 0; i < sizeof init / sizeof init[0]; ++i)
		if (oled_cmd(init[i].cmd, init[i].arg))
			return;
	/* the RAM holds noise at power-up: clear all 8 pages, every one of the 132 columns, before the display goes on */
	memset(page, 0, sizeof page);
	page[0] = 0x40;
	for (p = 0; p < 8; ++p) {
		if (oled_cmd((uint8_t)(0xB0 + p), NO_ARG) || oled_cmd(0x00, NO_ARG) || oled_cmd(0x10, NO_ARG))
			return;
		if (ch582_i2c_write(OLED_ADDR, page, sizeof page)) {
			state = DISPLAY_I2C_FAILED;
			return;
		}
	}
	if (oled_cmd(0xAF, NO_ARG)) /* display on */
		return;
	DelayMs(SH1106_ON_DELAY_MS);
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	int p;

	if (!buf || rows <= 0 || y < 0 || (int)y + rows > OLED_H || (rows & 7) || (y & 7) || state == DISPLAY_I2C_FAILED)
		return;
	page[0] = 0x40; /* control byte 0x40: data follows */
	for (p = 0; p < rows / 8; ++p) {
		if (oled_cmd((uint8_t)(0xB0 + y / 8 + p), NO_ARG) || /* page address */
		    oled_cmd(SH1106_COL_OFFSET & 0x0F, NO_ARG) ||   /* column low nibble */
		    oled_cmd((uint8_t)(0x10 | (SH1106_COL_OFFSET >> 4)), NO_ARG)) /* column high nibble */
			return;
		memcpy(page + 1, buf + (size_t)p * OLED_W, OLED_W);
		if (ch582_i2c_write(OLED_ADDR, page, 1 + OLED_W)) {
			state = DISPLAY_I2C_FAILED;
			return;
		}
	}
	state = DISPLAY_SHOWN;
}
