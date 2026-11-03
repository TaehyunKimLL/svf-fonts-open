/* arduino.ino - Arduino Uno: Korean text on a 128 x 64 SSD1306 OLED over I2C (Wire).
 *
 * The face (svf/dos/NEODG16G.SVF, 16 px 1 bpp jamo, 10.1 KB in mcu-strict) stays in flash (PROGMEM): the library is built with
 * -DSVF_RD8(p)=pgm_read_byte(p), so it reads the face through pgm_read_byte and never copies it to RAM. Text is drawn
 * with the MONO_PAGE target into a 128 x 64 page buffer in the SSD1306's own layout: 1 KB, half the Uno's 2 KB of RAM.
 * The text lines are kept in flash too and copied one at a time into a small buffer.
 * Wiring: SDA A4, SCL A5, the display at address 0x3C.
 */
#include <Arduino.h>
#include <Wire.h>
#include <avr/pgmspace.h>
#include <svf.h>

#define OLED_ADDR 0x3C

extern "C" {
extern const uint8_t svf_face_data[] PROGMEM; /* face.c (mkface.py, README) */
extern const uint32_t svf_face_data_len;
}

static const char line0[] PROGMEM = "Uno SVF 예제";
static const char line1[] PROGMEM = "다람쥐 헌 쳇바퀴";
static const char line2[] PROGMEM = "에 타고파! 1bpp";
static const char line3[] PROGMEM = "안녕하세요";
static const char *const lines[4] = {line0, line1, line2, line3};

static uint8_t page[128 * 64 / 8]; /* the frame: 8 pages of 128 bytes */
static svf_face face;

static void oled_cmd(uint8_t c)
{
	Wire.beginTransmission(OLED_ADDR);
	Wire.write(0x00); /* control byte: a command follows */
	Wire.write(c);
	Wire.endTransmission();
}

static void oled_init(void)
{
	static const uint8_t init[] PROGMEM = {
		0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, /* off, clock, 64 rows, offset 0, charge pump */
		0x20, 0x00,                                                 /* horizontal addressing: page after page */
		0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, /* orientation, COM pins, contrast, timing */
		0xA4, 0xA6, 0xAF,                                           /* show RAM, not inverted, on */
	};
	for (uint8_t i = 0; i < sizeof init; ++i)
		oled_cmd(pgm_read_byte(init + i));
}

static void oled_show(void)
{
	static const uint8_t window[] = {0x21, 0, 127, 0x22, 0, 7}; /* columns 0..127, pages 0..7 */
	for (uint8_t i = 0; i < sizeof window; ++i)
		oled_cmd(window[i]);
	/* Wire sends at most 32 bytes a transmission (its buffer): the control byte and 16 data bytes at a time. */
	for (uint16_t i = 0; i < sizeof page; i += 16) {
		Wire.beginTransmission(OLED_ADDR);
		Wire.write(0x40); /* control byte: data follows */
		Wire.write(page + i, 16);
		Wire.endTransmission();
	}
}

void setup(void)
{
	svf_face *faces[1] = {&face};
	svf_chain chain;
	svf_target t;
	uint8_t scratch[32]; /* one cell: 32 B hold a 16 x 16 1 bpp cell (NEODG16G) */
	char text[32];

	Wire.begin();
	Wire.setClock(400000);
	oled_init();

	memset(&chain, 0, sizeof chain);
	chain.faces = faces;
	chain.count = 1;
	if (svf_open_mapped(&face, svf_face_data, svf_face_data_len) != SVF_OK ||
	    svf_chain_scratch_bytes(&chain) > sizeof scratch ||
	    svf_target_init(&t, SVF_T_MONO_PAGE, page, sizeof page, 128, 64, 128) != SVF_OK)
		return; /* nothing to show */

	for (uint8_t i = 0; i < 4; ++i) {
		strncpy_P(text, lines[i], sizeof text - 1);
		text[sizeof text - 1] = 0;
		svf_draw_utf8(&chain, text, strlen(text), 0, (int16_t)(16 * i + svf_ascent(&face)), &t, scratch,
		              sizeof scratch);
	}
	oled_show();
}

void loop(void) {}
