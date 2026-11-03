/* Host check of the whole CH582 image against a model of the SH1106: main.c (compiled -Dmain=port_main) runs with the
 * real disp_sh1106.c, i2c-level ch582_i2c_write replaced by the panel model below, profile_mono.c and the library.
 * Run: test_sh1106_panel REF OUTDIR, REF the screen_ref.py --ref-only reference of ch582 mono (1,024 bytes). The model
 * has 8 pages of 132 columns of RAM, the page and column registers, and takes each write as the I2C bus would
 * (address 0x3C, control byte 0x00 commands / 0x40 data). Case A: svf_port_idle before anything (the 8 Hz drawing
 * failure code); case B: the whole run (the panel's RAM window must equal REF; written to
 * OUTDIR/ch582-mono.fb); case C:
 * the panel NACKs (the 2 Hz code, one write only). With -DSH1106_COL_OFFSET=0 (the negative build) case B instead
 * requires the shifted result the wrong offset gives. With -DOLED_SSD1306=1 the model is an SSD1306 (charge pump 8D 14
 * and page addressing 20 02 required, no DC-DC AD, RAM column 0). The RAM starts as noise: every RAM byte must have
 * been written before display-on (0xAF), and the columns outside the picture's window must end as zeros. Prints
 * port-check-sh1106-panel: OK (negative: port-check-sh1106-panel-negative: OK; SSD1306: port-check-ssd1306-panel: OK). */
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "CH58x_common.h"
#include "i2c.h"
#include "led.h"

#ifdef OLED_SSD1306
#define SSD 1
#else
#define SSD 0
#endif
#if defined(SH1106_COL_OFFSET) && !SSD
#define NEGATIVE 1
#define ID "port-check-sh1106-panel-negative"
#elif SSD
#define NEGATIVE 0
#define ID "port-check-ssd1306-panel"
#else
#define NEGATIVE 0
#define ID "port-check-sh1106-panel"
#endif
#define DATA_COL (NEGATIVE || SSD ? 0 : 2) /* the RAM column the driver writes the picture at in the build under test */
#define WIN_COL (SSD ? 0 : 2)              /* where the test reads the 128-column window (the SH1106 module's) */

int port_main(void);
void svf_port_idle(void);

#define DISTINCT(n, a, b) typedef char n[(a) != (b) ? 1 : -1]
DISTINCT(d1, LED_STEADY_MS, LED_I2C_FAIL_MS);
DISTINCT(d2, LED_STEADY_MS, LED_SVF_FAIL_MS);
DISTINCT(d3, LED_I2C_FAIL_MS, LED_SVF_FAIL_MS);
DISTINCT(d4, LED_STEADY_MS, 100);
DISTINCT(d5, LED_I2C_FAIL_MS, 100);
DISTINCT(d6, LED_SVF_FAIL_MS, 100);

static void fail(int line)
{
	fprintf(stderr, ID ": FAIL at line %d\n", line);
	exit(1);
}
#define CHECK(c) do { if (!(c)) fail(__LINE__); } while (0)

static uint32_t sleeps[16];
static int nsleeps, nled, led_level = -1, led_at_first_write = -1, first_cfg = -1, first_cfg_a = -1, ncfg;
static int sleep0_calls = -1, sysclk_cfg = -1, i2c_speed = -1, i2c_duty = -1; /* what main.c and the driver configured */

/* ---- the panel model ---- */
#define COLS 132
static struct {
	uint8_t ram[8][COLS];
	int page, col, remap, com_rev, dcdc, pump, pagemode, on, on_dirty;
	uint8_t written[8][COLS];
	int unknown, dropped, framing;
	int nwrites, ndata;
	struct { int page, col, len; } data[64];
	int nack, calls;
} m;

static void model_reset(void)
{
	int nack = m.nack;

	int p, c;

	memset(&m, 0, sizeof m);
	m.nack = nack;
	for (p = 0; p < 8; ++p)
		for (c = 0; c < COLS; ++c)
			m.ram[p][c] = (uint8_t)((0xA5 ^ (p * 37 + c * 11)) | 1); /* noise, never 0 */
}

static void command(uint8_t c)
{
	if (c <= 0x0F) m.col = (m.col & 0xF0) | c;
	else if (c <= 0x1F) m.col = (m.col & 0x0F) | ((c & 0x0F) << 4);
	else if (c >= 0x30 && c <= 0x33) { /* pump voltage */ }
	else if (c >= 0x40 && c <= 0x7F) { /* start line */ }
	else if (c == 0xA0 || c == 0xA1) m.remap = c & 1;
	else if (c == 0xA4 || c == 0xA5) { /* all on */ }
	else if (c == 0xA6 || c == 0xA7) { /* inverse */ }
	else if (c == 0xAE || c == 0xAF) {
		int p, k;

		m.on = c & 1;
		for (p = 0; p < 8 && m.on; ++p)
			for (k = 0; k < COLS; ++k)
				if (!m.written[p][k]) m.on_dirty = 1; /* display on with a RAM byte never written */
	}
	else if (c >= 0xB0 && c <= 0xB7) m.page = c & 7;
	else if (c >= 0xC0 && c <= 0xCF) m.com_rev = (c >> 3) & 1;
	else if (c == 0xE3) { /* nop */ }
	else ++m.unknown;
}

static int double_byte(uint8_t c)
{
	return c == 0x81 || c == 0xA8 || c == 0xAD || c == 0x8D || c == 0x20 || c == 0xD3 || c == 0xD5 || c == 0xD9 || c == 0xDA || c == 0xDB;
}

static void feed(uint8_t addr, const uint8_t *b, size_t n)
{
	size_t i;

	++m.nwrites;
	if (addr != 0x3C || n == 0) { ++m.framing; return; }
	if (b[0] == 0x00) {
		for (i = 1; i < n; ++i) {
			if (double_byte(b[i])) {
				if (i + 1 >= n) { ++m.framing; return; }
				if (b[i] == 0xAD) m.dcdc = b[i + 1] == 0x8B;
				if (b[i] == 0x8D) m.pump = b[i + 1] == 0x14;
				if (b[i] == 0x20) m.pagemode = b[i + 1] == 0x02;
				++i;
			} else {
				command(b[i]);
			}
		}
	} else if (b[0] == 0x40) {
		CHECK(m.ndata < 64);
		m.data[m.ndata].page = m.page;
		m.data[m.ndata].col = m.col;
		m.data[m.ndata].len = (int)n - 1;
		++m.ndata;
		for (i = 1; i < n; ++i) {
			/* the real SH1106 stops its column counter at 131 (datasheet); the model drops and counts instead:
			 * unreachable with this driver (128 columns from column 2 end at 129), so the count must stay 0 */
			if (m.col >= COLS) ++m.dropped;
			else { m.written[m.page][m.col] = 1; m.ram[m.page][m.col++] = b[i]; }
		}
	} else {
		++m.framing;
	}
}

int ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n)
{
	if (++m.calls == 1) led_at_first_write = led_level;
	if (m.nack) return -1;
	feed(addr, buf, n);
	return 0;
}

/* ---- the recording hooks ---- */
static jmp_buf out;
static int jump_ms; /* the sleep that ended the run (a longjmp value is read outside a setjmp expression) */

void svf_rec_bytes(int dc, const uint8_t *p, size_t n) { (void)dc; (void)p; (void)n; }
void svf_rec_i2c(uint8_t a, const uint8_t *p, size_t n, int ns) { (void)a; (void)p; (void)n; (void)ns; }
int svf_stub_dc_pin;
void svf_rec_gpio(int pin, int level)
{
	CHECK(pin == LED_PIN);
	led_level = level;
	++nled;
}
void svf_rec_cfg(int what, int a, int b, int c, int d)
{
	(void)c; (void)d;
	if (what == SVF_CFG_SYSCLK) sysclk_cfg = a;
	if (what == SVF_CFG_CH58X_I2C) { i2c_speed = a; i2c_duty = b; }
	if (ncfg++ == 0) { first_cfg = what; first_cfg_a = a; }
}
void svf_rec_sleep(uint32_t ms)
{
	CHECK(nsleeps < 16);
	if (nsleeps == 0) sleep0_calls = m.calls;
	sleeps[nsleeps++] = ms;
	if (ms == LED_STEADY_MS || ms == LED_I2C_FAIL_MS || ms == LED_SVF_FAIL_MS)
	{
		jump_ms = (int)ms;
		longjmp(out, 1);
	}
}

static void run_reset(void)
{
	model_reset();
	nsleeps = nled = ncfg = 0;
	sleep0_calls = -1;
	led_level = led_at_first_write = first_cfg = first_cfg_a = sysclk_cfg = i2c_speed = i2c_duty = -1;
}

int main(int argc, char **argv)
{
	static uint8_t ref[1024], win[1024];
	char path[4096];
	FILE *f;
	int p, i, j;

	alarm(60);
	CHECK(argc == 3);
	f = fopen(argv[1], "rb");
	CHECK(f && fread(ref, 1, sizeof ref, f) == sizeof ref && fgetc(f) == EOF);
	fclose(f);

	/* case A: the drawing-failure code, no init at all */
	run_reset();
	jump_ms = 0;
	if (setjmp(out) == 0) svf_port_idle();
	j = jump_ms;
	CHECK(j == LED_SVF_FAIL_MS && nled == 1 && m.calls == 0);

	/* case B: the whole run */
	run_reset();
	jump_ms = 0;
	if (setjmp(out) == 0) port_main();
	j = jump_ms;
	CHECK(j == LED_STEADY_MS);
	CHECK(first_cfg == SVF_CFG_SYSCLK && first_cfg_a == 0x54);
	/* the SDK's I2C_Init divider (CH58x_i2c.c, fast mode) on the clock main.c set: PLL_<n>MHz is 0x40 | (480 / n) */
	{
		uint32_t sys = 480000000u / ((uint32_t)sysclk_cfg & 0x1F), ccr;

		CHECK(sysclk_cfg >= 0 && i2c_speed == 400000 && sys / 1000000 >= 2 && sys / 1000000 <= 36);
		if (i2c_duty == I2C_DutyCycle_2) {
			ccr = (sys / ((uint32_t)i2c_speed * 3)) & 0xFFF;
			CHECK(ccr > 0 && sys / (3 * ccr) <= 400000); /* SH1106 SCL maximum */
			CHECK(ccr == 20 && sys / (3 * ccr) == 400000);
		} else {
			ccr = (sys / ((uint32_t)i2c_speed * 25)) & 0xFFF;
			CHECK(ccr > 0 && sys / (25 * ccr) <= 400000);
		}
	}
	CHECK(nsleeps == 3 && sleeps[0] == 20 && sleeps[1] == 100 && sleeps[2] == LED_STEADY_MS);
	CHECK(sleep0_calls == 0); /* the reset recovery wait comes before the first command */
	CHECK(led_at_first_write == 1 && led_level == 0); /* off (high) before the first write, on (low) at the end */
	CHECK(m.on == 1 && m.remap == 1 && m.com_rev == 1 && m.on_dirty == 0);
	if (SSD) CHECK(m.dcdc == 0 && m.pump == 1 && m.pagemode == 1);
	else CHECK(m.dcdc == 1 && m.pump == 0);
	CHECK(m.unknown == 0 && m.dropped == 0 && m.framing == 0);
	CHECK(m.ndata == 16); /* 8 pages of the RAM clear (132 bytes), then the 8 pages of the picture (128 bytes) */
	for (p = 0; p < 8; ++p) {
		int k, seen = 0, cleared = 0;
		for (k = 0; k < 16; ++k)
			if (m.data[k].page == p) {
				if (m.data[k].len == 132) { ++cleared; CHECK(m.data[k].col == 0 && k < 8); }
				else { ++seen; CHECK(m.data[k].len == 128 && m.data[k].col == DATA_COL && k >= 8); }
			}
		CHECK(seen == 1 && cleared == 1);
	}
	for (p = 0; p < 8; ++p)
		memcpy(win + p * 128, &m.ram[p][WIN_COL], 128);
	/* outside the picture's window the cleared RAM is zero, not the noise it started as */
	for (p = 0; p < 8; ++p)
		for (i = 0; i < COLS; ++i)
			if (i < DATA_COL || i >= DATA_COL + 128) CHECK(m.ram[p][i] == 0);
	if (!NEGATIVE) {
		CHECK(memcmp(win, ref, sizeof ref) == 0);
		if (!SSD) { /* the compare in screen_ref.py reads the SH1106 build's window */
			snprintf(path, sizeof path, "%s/ch582-mono.fb", argv[2]);
			f = fopen(path, "wb");
			CHECK(f && fwrite(win, 1, sizeof win, f) == sizeof win);
			fclose(f);
		}
	} else {
		/* RAM column c holds frame[p][c]; the window starts at RAM column 2; columns 128..129 stay 0 */
		int g = -1, first = -1;
		for (i = 0; i < 1024 && g < 0; ++i)
			if (i % 128 < 126 ? ref[i] != ref[i + 2] : ref[i] != 0) g = i;
		CHECK(g >= 0);
		for (i = 0; i < 1024; ++i) {
			uint8_t want = i % 128 < 126 ? ref[i + 2] : 0;
			CHECK(win[i] == want);
			if (first < 0 && win[i] != ref[i]) first = i;
		}
		CHECK(first == g);
	}

	/* case C: the panel does not answer */
	run_reset();
	m.nack = 1;
	jump_ms = 0;
	if (setjmp(out) == 0) port_main();
	j = jump_ms;
	CHECK(j == LED_I2C_FAIL_MS && m.calls == 1);

	printf(ID ": OK\n");
	return 0;
}
