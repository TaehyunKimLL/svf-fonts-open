/* Host check for the profiles: one real profile_<p>.c a run, drawing through a recording display_show.
 * Build per run with -DPROFILE_NAME="colour" (quoted for the shell: -DPROFILE_NAME='"colour"'), -DTEST_ID="pico-colour",
 * -DTEST_BIGENDIAN=0|1 (colour), -DSVF_TARGETS=<bit> -DSVF_NO_SCALE [-DSVF_GREY_KIND_GRAY8=1], -I <port dir> -I c/ports
 * -I c/include, sources test_profiles.c profile_<p>.c, every c/src source and the generated faces. Run: test_profiles REF LINES
 * where REF is the screen_ref.py --ref-only [--bigendian B] output (grey: --gray8, the 16,384 GRAY8 bytes) and LINES
 * the output of screens.py lines BOARD PROFILE. Also -DPROFILE_MARKER=svf_port_profile_<p> (its string must be the
 * profile's name) and -DEXPECT_MISSING_ADVANCE=<n> (screens.py's value; link with -Wl,--wrap=svf_draw_utf8). Prints port-check-profile-<TEST_ID>: OK. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "display.h"
#include "profile.h"
#include "svf.h"

#ifndef PROFILE_NAME
#error "pass -DPROFILE_NAME=<quoted profile>"
#endif
#ifndef TEST_ID
#error "pass -DTEST_ID=\"<port>-<profile>\""
#endif
#ifndef PROFILE_MARKER
#error "pass -DPROFILE_MARKER=svf_port_profile_<profile>"
#endif
#ifndef EXPECT_MISSING_ADVANCE
#error "pass -DEXPECT_MISSING_ADVANCE=<screens.py missing_advance>"
#endif
#ifndef TEST_BIGENDIAN
#define TEST_BIGENDIAN 0
#endif

static void fail(int line)
{
	fprintf(stderr, "port-check-profile-%s: FAIL at line %d\n", TEST_ID, line);
	exit(1);
}
#define CHECK(c) do { if (!(c)) fail(__LINE__); } while (0)

extern const char PROFILE_MARKER[];
#define MAX_SHOWS 32
typedef struct { int y, rows; size_t n; uint8_t *buf; } show;
static show shows[MAX_SHOWS];
static int nshows;
static int bytes_per_row; /* of the profile's frame format, set by main */
static int min_rows = 1, panel_rows; /* row granularity and height of the panel */
static int rows_per_unit = 1; /* 8 for MONO_PAGE: bytes_per_row bytes per page of 8 rows */

/* the profile's chain must carry screens.py's missing_advance (a glyph no face has advances that many pixels) */
svf_err __real_svf_draw_utf8(const svf_chain *c, const char *s, size_t len, int16_t x, int16_t y, svf_target *t,
                             uint8_t *scratch, size_t scratch_len);
svf_err __wrap_svf_draw_utf8(const svf_chain *c, const char *s, size_t len, int16_t x, int16_t y, svf_target *t,
                             uint8_t *scratch, size_t scratch_len)
{
	CHECK(c && c->missing_advance == EXPECT_MISSING_ADVANCE);
	return __real_svf_draw_utf8(c, s, len, x, y, t, scratch, scratch_len);
}

const uint8_t display_565_bigendian = TEST_BIGENDIAN;
void display_init(void) {}
void svf_port_idle(void)
{
	printf("idle: profile failed\n");
	exit(1);
}
void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	size_t n;

	/* validate before multiplying: whole pages (mono x8) or groups of 4 rows (grey), inside the panel */
	CHECK(nshows < MAX_SHOWS && buf && rows > 0 && y >= 0 && rows % min_rows == 0);
	CHECK(y + rows <= panel_rows && rows % rows_per_unit == 0);
	n = (size_t)rows / (size_t)rows_per_unit * (size_t)bytes_per_row;
	shows[nshows].y = y;
	shows[nshows].rows = rows;
	shows[nshows].n = n;
	shows[nshows].buf = malloc(n);
	CHECK(shows[nshows].buf);
	memcpy(shows[nshows].buf, buf, n);
	++nshows;
}

static uint8_t *slurp(const char *path, size_t *n, size_t max)
{
	FILE *f = fopen(path, "rb");
	uint8_t *b;
	long len;

	CHECK(f && fseek(f, 0, SEEK_END) == 0 && (len = ftell(f)) >= 0 && fseek(f, 0, SEEK_SET) == 0);
	CHECK((size_t)len <= max && (size_t)len + 1 > (size_t)len); /* the profile maximum, and len + 1 cannot wrap */
	b = malloc((size_t)len + 1);
	CHECK(b && fread(b, 1, (size_t)len, f) == (size_t)len);
	b[len] = 0; /* terminated: callers print from it */
	fclose(f);
	*n = (size_t)len;
	return b;
}

/* the profile's string i against the file's line at TXT + pos (n bytes in all; a last line without its newline is a
 * line that differs): say which string and what each side holds (stderr; the reference is the file), then exit 1 */
static void text_differs(int i, const char *want, const char *txt, size_t n, size_t pos)
{
	size_t e = pos;

	while (e < n && txt[e] != '\n')
		++e;
	fprintf(stderr, "port-check-profile-%s: string %d differs: expected \"%.*s\" (screens.py lines), got \"%s\" (profile)\n",
	        TEST_ID, i, (int)(e - pos), pos <= n ? txt + pos : "", want);
	if (pos < n && e == n && strlen(want) == e - pos && memcmp(txt + pos, want, e - pos) == 0)
		fprintf(stderr, "port-check-profile-%s: (the text is equal: the file's last line has no newline)\n", TEST_ID);
	exit(1);
}

/* svf_port_text[0..n) against the lines of the LINES file (each line ends with \n) */
static void check_text(const char *path)
{
	size_t n, pos = 0;
	char *txt = (char *)slurp(path, &n, 4096);
	int i;

	for (i = 0; i < svf_port_text_n; ++i) {
		size_t len = strlen(svf_port_text[i]);

		if (!(pos + len < n && memcmp(txt + pos, svf_port_text[i], len) == 0 && txt[pos + len] == '\n'))
			text_differs(i, svf_port_text[i], txt, n, pos);
		pos += len + 1;
	}
	if (pos != n) { /* as many lines in the file as strings in the profile */
		fprintf(stderr, "port-check-profile-%s: the file has more lines than the profile has strings (%d); next: \"%.*s\"\n",
		        TEST_ID, svf_port_text_n, (int)(n - pos), txt + pos);
		exit(1);
	}
	free(txt);
}

int main(int argc, char **argv)
{
	size_t ref_n;
	uint8_t *ref;
	int i;

	CHECK(argc == 3);
	ref = slurp(argv[1], &ref_n, 240 * 320 * 2);
	CHECK(strcmp(PROFILE_MARKER, PROFILE_NAME) == 0);
	if (strcmp(PROFILE_NAME, "colour") == 0) {
		const uint8_t bg_pair[2] = {TEST_BIGENDIAN ? 0x00 : 0x10, TEST_BIGENDIAN ? 0x10 : 0x00}; /* bg 0x0010 */
		size_t stride = (size_t)PORT_LCD_W * 2;

		bytes_per_row = (int)stride;
		panel_rows = PORT_LCD_H;
		profile_run();
		CHECK(nshows == 15 && ref_n == stride * 240);
		for (i = 0; i < 10; ++i) { /* the clear pass */
			size_t k;

			CHECK(shows[i].y == 24 * i && shows[i].rows == 24 && shows[i].n == stride * 24);
			for (k = 0; k < shows[i].n; k += 2)
				CHECK(shows[i].buf[k] == bg_pair[0] && shows[i].buf[k + 1] == bg_pair[1]);
		}
		for (i = 0; i < 5; ++i) { /* the text bands */
			const show *s = &shows[10 + i];
			int y = 16 + 28 * i;

			CHECK(s->y == y && s->rows == 24 && s->n == stride * 24);
			CHECK(memcmp(s->buf, ref + (size_t)y * stride, s->n) == 0);
		}
	} else if (strcmp(PROFILE_NAME, "grey") == 0) {
		bytes_per_row = GREY_W;
		panel_rows = GREY_H;
		min_rows = 4; /* SSD1327: groups of 4 rows */
		profile_run();
		CHECK(nshows == 1 && shows[0].y == 0 && shows[0].rows == 128);
		CHECK(ref_n == 16384 && shows[0].n == 16384 && memcmp(shows[0].buf, ref, ref_n) == 0);
	} else if (strcmp(PROFILE_NAME, "mono") == 0) {
		bytes_per_row = OLED_W;
		rows_per_unit = 8; /* whole pages */
		min_rows = 8;
		panel_rows = OLED_H;
		profile_run();
		CHECK(nshows == 1 && shows[0].y == 0 && shows[0].rows == 64);
		CHECK(ref_n == 1024 && shows[0].n == 1024);
		CHECK(memcmp(shows[0].buf, ref, ref_n) == 0);
	} else {
		CHECK(0);
	}
	check_text(argv[2]);
	for (i = 0; i < nshows; ++i)
		free(shows[i].buf);
	free(ref);
	printf("port-check-profile-%s: OK\n", TEST_ID);
	return 0;
}
