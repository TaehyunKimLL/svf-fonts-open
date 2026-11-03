/* vesa_lines - see vesa_lines.h. tools/vesa_lines.py must give the same table, the same palette and the same message
 * at the same line for every file: change the two together. */
#include "vesa_lines.h"

#include "vbe_select.h"

enum { S_START, S_COLOURS, S_LINES };

/* Strict UTF-8 (no overlong form, no surrogate, nothing above U+10FFFF) over n bytes; 1 when valid. */
static int utf8_ok(const unsigned char *s, size_t n)
{
	size_t i = 0;

	while (i < n) {
		unsigned c = s[i];
		unsigned len, lo = 0x80, hi = 0xBF;

		if (c < 0x80) {
			i++;
			continue;
		}
		if (c >= 0xC2 && c <= 0xDF)
			len = 2;
		else if (c >= 0xE0 && c <= 0xEF) {
			len = 3;
			if (c == 0xE0)
				lo = 0xA0;
			else if (c == 0xED)
				hi = 0x9F;
		} else if (c >= 0xF0 && c <= 0xF4) {
			len = 4;
			if (c == 0xF0)
				lo = 0x90;
			else if (c == 0xF4)
				hi = 0x8F;
		} else
			return 0;
		if (i + len > n || s[i + 1] < lo || s[i + 1] > hi)
			return 0;
		for (unsigned k = 2; k < len; k++)
			if (s[i + k] < 0x80 || s[i + k] > 0xBF)
				return 0;
		i += len;
	}
	return 1;
}

/* A number: decimal or 0x/0X hex digits (a '-' first when neg_ok); saturates above 0xFFFFFFFF, so that any range check
 * below refuses it. 0 ok, -1 not a number. */
static int num(const char *s, int neg_ok, long long *v)
{
	unsigned long long x = 0;
	unsigned base = 10, d;
	int neg = 0, digits = 0;

	if (*s == '-' && neg_ok) {
		neg = 1;
		s++;
	}
	if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
		base = 16;
		s += 2;
	}
	for (; *s; s++, digits++) {
		if (*s >= '0' && *s <= '9')
			d = (unsigned)(*s - '0');
		else if (base == 16 && *s >= 'a' && *s <= 'f')
			d = (unsigned)(*s - 'a') + 10;
		else if (base == 16 && *s >= 'A' && *s <= 'F')
			d = (unsigned)(*s - 'A') + 10;
		else
			return -1;
		if (x <= 0xFFFFFFFFull)
			x = x * base + d;
	}
	if (!digits)
		return -1;
	if (x > 0xFFFFFFFFull)
		x = 0x1FFFFFFFFull;
	*v = neg ? -(long long)x : (long long)x;
	return 0;
}

static int fail(char err[128], const char *msg)
{
	size_t n = strlen(msg);

	if (n > 127)
		n = 127;
	memcpy(err, msg, n);
	err[n] = 0;
	return -1;
}

/* Splits s at '|' in place into f[0..7]; returns the number of fields (counted past 8, only 8 kept); each field is
 * trimmed of spaces and tabs. */
static int split(char *s, char *f[8])
{
	int n = 0;

	for (;;) {
		char *bar = strchr(s, '|'), *e;

		if (bar)
			*bar = 0;
		while (*s == ' ' || *s == '\t')
			s++;
		e = s + strlen(s);
		while (e > s && (e[-1] == ' ' || e[-1] == '\t'))
			*--e = 0;
		if (n < 8)
			f[n] = s;
		n++;
		if (!bar)
			return n;
		s = bar + 1;
	}
}

static int field_numbers(char err[128], long long *v, const char *s, long long lo, long long hi, const char *what,
                         int neg_ok)
{
	char msg[64];

	if (num(s, neg_ok, v) != 0)
		return fail(err, "bad number");
	if (*v < lo || *v > hi) {
		snprintf(msg, sizeof msg, "%s out of range", what);
		return fail(err, msg);
	}
	return 0;
}

static int name_ok(const char *s)
{
	size_t n = strlen(s);

	if (n < 1 || n > VL_NAME_BYTES - 1)
		return 0;
	for (; *s; s++)
		if ((unsigned char)*s <= 0x20 || (unsigned char)*s >= 0x7F)
			return 0;
	return 1;
}

static int face_ok(const char *s, size_t n)
{
	size_t i;

	if (n < 5 || n > 12 || memcmp(s + n - 4, ".SVF", 4) != 0)
		return 0;
	for (i = 0; i < n - 4; i++)
		if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9') || s[i] == '_'))
			return 0;
	/* DOS device names open the device, not a file: CON PRN AUX NUL COM1..9 LPT1..9 */
	if (n - 4 == 3 && (memcmp(s, "CON", 3) == 0 || memcmp(s, "PRN", 3) == 0 || memcmp(s, "AUX", 3) == 0 ||
	                   memcmp(s, "NUL", 3) == 0))
		return 0;
	if (n - 4 == 4 && (memcmp(s, "COM", 3) == 0 || memcmp(s, "LPT", 3) == 0) && s[3] >= '1' && s[3] <= '9')
		return 0;
	return 1;
}

static int colour_record(vl_table *t, char *f[8], int nf, char err[128])
{
	vl_colour *c;
	long long v;
	int i, isbg;

	if (t->ncolours == VL_MAX_COLOURS)
		return fail(err, "more than 16 colours");
	if (nf != 6)
		return fail(err, "a colour record has 6 fields");
	for (i = 0; i < 6; i++)
		if (!f[i][0])
			return fail(err, "empty field");
	if (!name_ok(f[0]))
		return fail(err, "bad colour name");
	for (i = 0; i < t->ncolours; i++)
		if (strcmp(t->colours[i].name, f[0]) == 0)
			return fail(err, "duplicate colour name");
	c = &t->colours[t->ncolours];
	memset(c, 0, sizeof *c);
	strcpy(c->name, f[0]);
	if (field_numbers(err, &v, f[1], 0, 0xFFFF, "rgb565", 0))
		return -1;
	c->rgb565 = (uint16_t)v;
	if (field_numbers(err, &v, f[2], 0, 0x7FFF, "rgb555", 0))
		return -1;
	c->rgb555 = (uint16_t)v;
	if (field_numbers(err, &v, f[3], 0, 0xFFFFFF, "rgb888", 0))
		return -1;
	c->rgb888 = (uint32_t)v;
	if (field_numbers(err, &v, f[4], 0, 255, "index_base", 0))
		return -1;
	c->index_base = (uint8_t)v;
	if (field_numbers(err, &v, f[5], 0, 255, "index_levels", 0))
		return -1;
	c->index_levels = (uint8_t)v;
	isbg = strcmp(c->name, "background") == 0;
	if (isbg && c->index_levels != 0)
		return fail(err, "background index_levels must be 0");
	if (!isbg && c->index_levels == 0)
		return fail(err, "index_levels 0 only for background");
	if (c->index_base + c->index_levels > 255)
		return fail(err, "index_base + index_levels above 255");
	for (i = 0; i < t->ncolours; i++) {
		const vl_colour *e = &t->colours[i];
		int ebg = strcmp(e->name, "background") == 0;

		if (isbg || ebg) {
			const vl_colour *ramp = isbg ? e : c, *bg = isbg ? c : e;

			if (ramp->index_base <= bg->index_base)
				return fail(err, "background index must be below every ramp");
		} else if (c->index_base <= e->index_base + e->index_levels && e->index_base <= c->index_base + c->index_levels)
			return fail(err, "ramps overlap");
	}
	if (isbg)
		t->background = t->ncolours;
	t->ncolours++;
	return 0;
}

static int line_record(vl_table *t, char *f[8], int nf, char err[128])
{
	vl_line *l;
	long long v, den;
	char *p, *s, *slash;
	int i;

	if (t->nlines == VL_MAX_LINES)
		return fail(err, "more than 32 lines");
	if (nf != 6)
		return fail(err, "a line record has 6 fields");
	for (i = 0; i < 5; i++)
		if (!f[i][0])
			return fail(err, "empty field");
	l = &t->lines[t->nlines];
	memset(l, 0, sizeof *l);
	for (p = f[0];; p = s + 1) {
		s = strchr(p, '+');
		if (l->nfaces == VL_MAX_FACES)
			return fail(err, "more than 4 faces");
		if (!face_ok(p, s ? (size_t)(s - p) : strlen(p)))
			return fail(err, "bad face name");
		memcpy(l->faces[l->nfaces], p, s ? (size_t)(s - p) : strlen(p));
		l->nfaces++;
		if (!s)
			break;
	}
	slash = strchr(f[1], '/');
	if (!slash || strchr(slash + 1, '/'))
		return fail(err, "bad scale");
	*slash = 0;
	if (num(f[1], 0, &v) != 0 || num(slash + 1, 0, &den) != 0)
		return fail(err, "bad scale");
	if (v < 1 || v > 16 || den < 1 || den > 16)
		return fail(err, "scale out of range");
	l->num = (uint8_t)v;
	l->den = (uint8_t)den;
	if (field_numbers(err, &v, f[2], -32768, 32767, "x", 1))
		return -1;
	l->x = (int16_t)v;
	if (field_numbers(err, &v, f[3], -32768, 32767, "baseline", 1))
		return -1;
	l->baseline = (int16_t)v;
	for (i = 0; i < t->ncolours; i++)
		if (strcmp(t->colours[i].name, f[4]) == 0)
			break;
	if (i == t->ncolours)
		return fail(err, "unknown colour");
	if (i == t->background)
		return fail(err, "background is not a line colour");
	l->colour = (uint8_t)i;
	strcpy(l->text, f[5]);
	t->nlines++;
	return 0;
}

int vl_parse(FILE *fp, vl_table *t, char err[128], int *line_no)
{
	char buf[VL_LINE_BYTES + 1], *f[8];
	int state = S_START, seen_bg = 0, n = 0;
	size_t total = 0; /* bytes read so far, the peek included */

	memset(t, 0, sizeof *t);
	for (;;) {
		size_t len = 0;
		int nf, i;
		int ch = 0;
		char *s, *e;

		int toolong = 0;

		while (len < VL_LINE_BYTES && (ch = getc(fp)) != EOF) {
			buf[len++] = (char)ch;
			total++;
			if (ch == '\n')
				break;
		}
		if (len == 0)
			break;
		n++;
		*line_no = n;
		if (buf[len - 1] != '\n' && len == VL_LINE_BYTES && (ch = getc(fp)) != EOF) {
			total++;
			toolong = 1;
		}
		if (total > VL_MAX_FILE) { /* the size comes first, whatever line it is, and is reported at line 1 */
			*line_no = 1;
			return fail(err, "file too large");
		}
		if (toolong)
			return fail(err, "line too long");
		if (buf[len - 1] == '\n')
			len--;
		buf[len] = 0;
		if (strlen(buf) != len)
			return fail(err, "NUL byte");
		if (!utf8_ok((const unsigned char *)buf, len))
			return fail(err, "invalid UTF-8");
		s = buf;
		while (*s == ' ' || *s == '\t')
			s++;
		e = s + strlen(s);
		while (e > s && (e[-1] == ' ' || e[-1] == '\t'))
			*--e = 0;
		if (!*s || *s == '#')
			continue;
		if (*s == '[') {
			if (strcmp(s, "[colours]") == 0) {
				if (state == S_COLOURS)
					return fail(err, "repeated header [colours]");
				if (state == S_LINES)
					return fail(err, "header after [lines]");
				state = S_COLOURS;
			} else if (strcmp(s, "[lines]") == 0) {
				if (state == S_START)
					return fail(err, "first section must be [colours]");
				if (state == S_LINES)
					return fail(err, "repeated header [lines]");
				if (!seen_bg)
					return fail(err, "missing background");
				state = S_LINES;
			} else
				return fail(err, state == S_START ? "first section must be [colours]" : "unknown section header");
			continue;
		}
		if (state == S_START)
			return fail(err, "first section must be [colours]");
		nf = split(s, f);
		if (state == S_COLOURS) {
			if (colour_record(t, f, nf, err) != 0)
				return -1;
			for (i = 0; i < t->ncolours; i++)
				seen_bg |= (strcmp(t->colours[i].name, "background") == 0);
		} else if (line_record(t, f, nf, err) != 0)
			return -1;
	}
	*line_no = n + 1;
	if (ferror(fp))
		return fail(err, "read error");
	if (state == S_START)
		return fail(err, "first section must be [colours]");
	if (!seen_bg)
		return fail(err, "missing background");
	return 0;
}

void vl_palette(const vl_table *t, unsigned dac_bits, uint8_t pal[256][4])
{
	uint8_t bg[3], fg[3];
	const vl_colour *b = &t->colours[t->background];
	unsigned i, k;

	bg[0] = (uint8_t)(b->rgb888 >> 16);
	bg[1] = (uint8_t)(b->rgb888 >> 8);
	bg[2] = (uint8_t)b->rgb888;
	for (i = 0; i < 256; i++)
		vbe_palette_entry(0, 0, bg, bg, dac_bits, pal[i]);
	for (i = 0; i < t->ncolours; i++) {
		const vl_colour *c = &t->colours[i];

		if (i == t->background)
			continue;
		fg[0] = (uint8_t)(c->rgb888 >> 16);
		fg[1] = (uint8_t)(c->rgb888 >> 8);
		fg[2] = (uint8_t)c->rgb888;
		for (k = 0; k <= c->index_levels; k++)
			vbe_palette_entry(k, c->index_levels, bg, fg, dac_bits, pal[c->index_base + k]);
	}
}

size_t vl_substitute(const char *text, unsigned w, unsigned h, unsigned bpp, char *out, size_t out_len)
{
	size_t need = 0;

	while (*text) {
		char tmp[16];
		const char *src = text;
		size_t n = 1;

		if (strncmp(text, "{W}", 3) == 0) {
			snprintf(tmp, sizeof tmp, "%u", w);
			src = tmp, n = strlen(tmp), text += 3;
		} else if (strncmp(text, "{H}", 3) == 0) {
			snprintf(tmp, sizeof tmp, "%u", h);
			src = tmp, n = strlen(tmp), text += 3;
		} else if (strncmp(text, "{BPP}", 5) == 0) {
			snprintf(tmp, sizeof tmp, "%u", bpp);
			src = tmp, n = strlen(tmp), text += 5;
		} else
			text++;
		for (size_t i = 0; i < n; i++, need++)
			if (need + 1 < out_len)
				out[need] = src[i];
	}
	if (out_len > 0)
		out[need < out_len ? need : out_len - 1] = 0;
	return need;
}

size_t vl_cache_slots(size_t file_len)
{
	size_t slots = (file_len + VL_CACHE_BLOCK - 1) / VL_CACHE_BLOCK;

	return slots < 2 ? 2 : slots > 64 ? 64 : slots; /* svf_open_stream refuses fewer than 2 slots */
}
