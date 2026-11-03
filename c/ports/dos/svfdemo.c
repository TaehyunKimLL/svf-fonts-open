/* svfdemo.c - draws Korean text with PAPLG16 + PAPLG18 in VGA mode 13h (DJGPP), both faces streamed from their files.
 *
 * The faces stay on disk: svf_open_stream reads their tables once, then glyph rows are read through a 1 KB block
 * cache as they are drawn. The text is drawn into a 320 x 200 GRAY8 buffer (one byte a pixel, the coverage 0..255),
 * the palette is set to a grey ramp so a coverage byte is its own colour index, and the buffer is copied to the
 * screen. Run it from the directory holding PAPLG16.SVF and PAPLG18.SVF; a key returns to text mode.
 */
#include "svf.h"

#include <conio.h>         /* getch */
#include <dpmi.h>          /* __dpmi_int */
#include <fcntl.h>         /* open */
#include <pc.h>            /* outportb */
#include <stdio.h>
#include <string.h>
#include <sys/movedata.h>  /* dosmemput */
#include <unistd.h>        /* lseek, read, close */

#define W 320
#define H 200
#define BLOCK 1024 /* cache block: the file is read in aligned 1 KB blocks */

/* A cache must hold every block one line touches, or it is read again and again: PAPLG16 is 15 KB (16 blocks: the
 * whole file), a line of PAPLG18 syllables touches up to about 40 of its 122 blocks. A slot is a block + 8 bytes. */
static uint8_t tables16[4096], tables18[32768];
static uint8_t cache16[16 * (BLOCK + 8)], cache18[64 * (BLOCK + 8)];
static uint8_t scratch[2 * 18 * 5]; /* one 18 x 18 2 bpp cell, twice (enough for any svf_chain_scratch_bytes here) */
static uint8_t screen[W * H];

static const char *const lines[] = {
	"SVF 렌더러 DOS 예제",
	"다람쥐 헌 쳇바퀴에 타고파!",
	"키스의 고유조건은 입술끼리",
	"만나야 하고 특별한 기술은",
	"필요치 않다.",
	"PAPLG16 + PAPLG18, 디스크에서",
};

/* The read callback: @p ctx is the file handle. */
static long read_file(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	int fd = *(int *)ctx;

	if (lseek(fd, (off_t)offset, SEEK_SET) != (off_t)offset)
		return -1;
	return (long)read(fd, dst, len);
}

/* Opens @p path as a streamed face read through the handle @p fd (left open: the face reads it when drawing). */
static svf_err open_face(svf_face *f, const char *path, int *fd, uint8_t *tables, size_t tables_len, uint8_t *cache,
                         size_t cache_len)
{
	long len;
	size_t need;
	svf_err e;

	*fd = open(path, O_RDONLY | O_BINARY);
	if (*fd < 0 || (len = lseek(*fd, 0, SEEK_END)) <= 0)
		return SVF_E_IO;
	need = svf_stream_tables_size(read_file, fd, (uint32_t)len, &e);
	if (e != SVF_OK)
		return e;
	if (need > tables_len)
		return SVF_E_NOMEM;
	return svf_open_stream(f, read_file, fd, (uint32_t)len, tables, tables_len, cache, cache_len, BLOCK);
}

static void video_mode(int mode)
{
	__dpmi_regs r;

	memset(&r, 0, sizeof r);
	r.x.ax = (unsigned short)mode;
	__dpmi_int(0x10, &r);
}

int main(void)
{
	static svf_face f16, f18;
	svf_face *faces[2] = {&f16, &f18}; /* PAPLG16 first: ASCII and punctuation; PAPLG18 composes the syllables */
	svf_chain chain;
	svf_target t;
	svf_extent ext;
	svf_err e;
	int fd16, fd18, i, y;

	if ((e = open_face(&f16, "PAPLG16.SVF", &fd16, tables16, sizeof tables16, cache16, sizeof cache16)) != SVF_OK ||
	    (e = open_face(&f18, "PAPLG18.SVF", &fd18, tables18, sizeof tables18, cache18, sizeof cache18)) != SVF_OK) {
		printf("svfdemo: cannot open PAPLG16.SVF / PAPLG18.SVF (svf_err %d)\n", (int)e);
		return 1;
	}
	memset(&chain, 0, sizeof chain);
	chain.faces = faces;
	chain.count = 2;
	chain.missing_advance = 6;
	if (svf_chain_scratch_bytes(&chain) > sizeof scratch ||
	    svf_target_init(&t, SVF_T_GRAY8, screen, sizeof screen, W, H, W) != SVF_OK) {
		printf("svfdemo: scratch or target refused\n");
		return 1;
	}

	/* One line every 26 rows, centred; the faces share the baseline (PAPLG16 ascent 14, PAPLG18 ascent 17). */
	for (i = 0, y = 32; i < (int)(sizeof lines / sizeof lines[0]); ++i, y += 26) {
		size_t n = strlen(lines[i]);
		svf_measure_utf8(&chain, lines[i], n, &ext);
		e = svf_draw_utf8(&chain, lines[i], n, (int16_t)((W - ext.width) / 2), (int16_t)y, &t, scratch,
		                  sizeof scratch);
		if (e != SVF_OK)
			break;
	}

	video_mode(0x13);
	outportb(0x3C8, 0); /* palette: index i is grey i (the DAC takes 6 bits a channel) */
	for (i = 0; i < 256; ++i) {
		outportb(0x3C9, (unsigned char)(i >> 2));
		outportb(0x3C9, (unsigned char)(i >> 2));
		outportb(0x3C9, (unsigned char)(i >> 2));
	}
	dosmemput(screen, sizeof screen, 0xA0000);
	getch();
	video_mode(0x03);

	close(fd16);
	close(fd18);
	if (e != SVF_OK) {
		printf("svfdemo: drawing failed (svf_err %d)\n", (int)e);
		return 1;
	}
	printf("svfdemo: %lu reads from PAPLG16, %lu from PAPLG18\n", (unsigned long)svf_stream_reads(&f16),
	       (unsigned long)svf_stream_reads(&f18));
	return 0;
}
