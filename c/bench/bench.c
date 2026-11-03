/* bench.c - the emulated speed probe of c/bench/run-*.sh (since bf1d0da, 2026-10-19): times the library on one platform and reports
 * each case as (name, iterations, a checksum of the pixels drawn) with the time the platform measures.
 *
 * Build with one of
 *   -DBENCH_PICO   Cortex-M0+ under rp2040js: no clock in the program; markers (BKPT) let c/bench/pico-run.mjs read
 *                  the emulator's cycle counter around each case
 *   -DBENCH_AVR    ATmega328P under simavr: the same markers as writes to GPIOR0/GPIOR1, read by c/bench/avr-run.c
 *   -DBENCH_ESP32C3  ESP32-C3 (RV32IMC) under Espressif's QEMU: rdinstret (instructions executed) before and after
 *                  each case, printed with newlib's printf through semihosting
 *   -DBENCH_ESP32S3  ESP32-S3 (Xtensa) under Espressif's QEMU at -icount shift=5: the ICOUNT register (instructions of
 *                  core 0) before and after each case, after a calibration on NOPs and on a 1M-instruction loop
 *   -DBENCH_M33    Cortex-M33 (RP2350's Arm core) under QEMU 8.2.2 -M mps2-an505 -icount shift=0: SysTick ticks x 50 =
 *                  instructions executed (not RP2350 cycles), after a calibration on a 2,000,000-instruction loop;
 *                  printed with newlib-nano's printf through semihosting. -DBENCH_MCU is not implied: the runner
 *                  passes it for the MCU cases and omits it for the line cases, as run-host.sh does
 *   -DBENCH_RP2350 RP2350 (Hazard3 or Cortex-M33) in a pico-sdk pico2 image under rp2350js: no clock in the program; calls
 *                  to four marker functions let c/bench/rp2350-run.mjs read rp2350js's cycle counter around each case.
 *                  -DBENCH_MCU is not implied (the runner passes it for the MCU cases, none for the line cases)
 *   -DBENCH_ESP_STUB with one of the three QEMU defines: counters faked, no asm, for a host compile of the section
 *   -DBENCH_DOS    DJGPP under DOSBox-X: uclock() (the PIT, 1.19 MHz), printed; faces read from files
 *   -DBENCH_WASM   emcc under node: emscripten_get_now() (performance.now), printed
 *   -DBENCH_HOST   the host compiler: clock_gettime(CLOCK_MONOTONIC), printed (pixel checksums to compare against)
 *
 * Cases on the microcontrollers (one 16 px 1 bpp jamo face, mapped; MONO_PAGE 128 x 64, the SSD1306 layout):
 *   syl_ga, syl_bwelk   svf_draw_utf8 of one syllable (2 and 3 pieces: compose + blit), the same spot each time
 *   compose_bwelk       svf_compose of the 3-piece syllable alone (the part of syl_bwelk that is not drawing)
 *   screen32            clear the page buffer and draw 4 lines of 8 syllables (32 glyphs)
 *   line8               (not on the Uno) the first of those lines, drawn alone
 * The target is -DBENCH_KIND=SVF_T_MONO_PAGE (default), SVF_T_GRAY8, SVF_T_GRAY (gray_bits 8, which svf_target_init sets:
 * the GRAY8 sums and the same bytes through the parametric kind) or SVF_T_RGB565, 128 x 64. With GRAY8, GRAY or RGB565
 * compiled in (-DSVF_TARGETS), set B follows (PAPLG16 + PAPLG18, 2 bpp, a 240 x 24 band, fg 0xFFE0 on bg 0x0010):
 *   aa_syl_ga, aa_syl_bwelk, aa_line12 (a 12 code point line), aa_screen10 (ten bands: clear and draw a line each;
 *   only those are timed, the checksums of the bands are not)
 * Expected checksums: c/bench/sums.py (from tools/svfline.py).
 * Every build, last: layout_probe (one iteration; the layouts the build reads, see its comment).
 * Cases on DOS, WASM and the host (PAPLG16 + PAPLG18, 2 bpp; a 40 code point line, GRAY8 640 x 24):
 *   line40_mapped        both faces held whole in memory
 *   line40_mapped_cache  the same with a composed-syllable cache (svf_chain_cache)
 *   line40_stream_cold   both faces streamed with 1 KB block caches that hold the line's blocks (16 slots for
 *                        PAPLG16, 64 for PAPLG18: 82 KB), the first draw after opening them (caches empty)
 *   line40_stream_warm   the same, further draws (no read)
 *   line40_stream_small  streamed with caches smaller than the line's blocks (4 and 16 slots, 21 KB): every draw
 *                        reads again (least recently used replacement over a working set larger than the cache)
 *   line40_stream_nocache  streamed without a block cache: every glyph and piece read when drawn
 *   line40_scaled32      the same line at 3/2 (scale_num 3, scale_den 2) on GRAY8 960 x 36, baseline 28, mapped, no
 *                        syllable cache (run after line40_mapped_cache; no reads_per_iter line)
 * Each other line case is followed by "  reads_per_iter=R": read callback calls a draw.
 * Cases on DOS and the host only (the packed kinds of the VESA modes, mapped faces, the line drawn with index_base 16,
 * index_levels 3, fg565 0xFFFF, fg888 0xFFFFFF, bg 0 on a buffer cleared to 0; the checksum covers rows * stride):
 *   line40_<kind>      PAPLG16 + PAPLG18, 640 x 24, baseline 19, for indexed8, rgb555, rgb565, xrgb8888, rgb888
 *   line40_24_<kind>   MARUS24A, 640 x 32, baseline 25, the same five kinds
 *   line40_24m_<kind>  MARUS24, 640 x 32, baseline 25, for indexed8, rgb565, xrgb8888
 * BENCH_CASE_SUFFIX (a string literal, default "") is appended to every case name that bench_report prints (DOS, WASM
 * and host; the Pico, Uno and ESP32 reporters ignore it): run-dos.sh builds the program a second time with
 * -DSVF_WORD_STORE=0 -DBENCH_CASE_SUFFIX='"_bytes"' to time the byte loops against the word stores.
 * DOS streams from the .SVF files (fseek + fread); WASM and the host stream from the embedded arrays (memcpy).
 *
 * The checksum is FNV-1a over the target buffer after the case: the same case gives the same value on every
 * platform (it only depends on the pixels). Not part of `make -C c check`: the emulators are host tools.
 */
#if defined(BENCH_HOST)
#define _POSIX_C_SOURCE 199309L /* clock_gettime */
#endif
#include "svf.h"

#include <stdint.h>
#include <string.h>

#ifndef BENCH_CASE_SUFFIX
#define BENCH_CASE_SUFFIX ""
#endif

#if defined(BENCH_PICO) + defined(BENCH_AVR) + defined(BENCH_ESP32C3) + defined(BENCH_ESP32S3) + defined(BENCH_M33) + \
        defined(BENCH_RP2350) + defined(BENCH_DOS) + defined(BENCH_WASM) + defined(BENCH_HOST) != 1
#error "build with exactly one of -DBENCH_PICO, -DBENCH_AVR, -DBENCH_ESP32C3, -DBENCH_ESP32S3, -DBENCH_M33, -DBENCH_RP2350, -DBENCH_DOS, -DBENCH_WASM, -DBENCH_HOST"
#endif

#if defined(BENCH_PICO) || defined(BENCH_AVR) || defined(BENCH_ESP32C3) || defined(BENCH_ESP32S3)
#define BENCH_MCU 1 /* the microcontroller cases; -DBENCH_HOST -DBENCH_MCU runs them on the host; BENCH_M33 and BENCH_RP2350 do not
                       imply it (the runner passes -DBENCH_MCU for the MCU cases, none for the line cases) */
#endif

/* ---- the platform: start/stop marks and reporting ------------------------------------------------------------- */

#if defined(BENCH_PICO)
/* BKPT #1 start, #2 stop, #3 report (r0 the name, r1 iterations, r2 the checksum), #4 end; pico-run.mjs reads the
 * cycle counter at each and goes on. */
#define BENCH_SYL_N 100u
#define BENCH_SCREEN_N 20u
static void bench_start(void) { __asm__ volatile("bkpt #1" ::: "memory"); }
static void bench_stop(void) { __asm__ volatile("bkpt #2" ::: "memory"); }
static void bench_report(const char *name, uint32_t iters, uint32_t sum)
{
	register const char *r0 __asm__("r0") = name;
	register uint32_t r1 __asm__("r1") = iters, r2 __asm__("r2") = sum;
	__asm__ volatile("bkpt #3" ::"r"(r0), "r"(r1), "r"(r2) : "memory");
}
static void bench_end(int code)
{
	register int r0 __asm__("r0") = code;
	for (;;)
		__asm__ volatile("bkpt #4" ::"r"(r0) : "memory");
}
#elif defined(BENCH_AVR)
/* GPIOR0 = 1 start, 2 stop, 3 report (after the name, NUL, iterations and checksum, both u32 little-endian, written
 * byte by byte to GPIOR1), 4 end (after the exit code on GPIOR1); then interrupts off and sleep, which ends simavr. */
#include <avr/io.h>
#include <avr/pgmspace.h>
#include <avr/sleep.h>
#define BENCH_SYL_N 20u
#define BENCH_SCREEN_N 2u
static void bench_start(void) { GPIOR0 = 1; }
static void bench_stop(void) { GPIOR0 = 2; }
static void put32(uint32_t v)
{
	uint8_t i;
	for (i = 0; i < 4; ++i, v >>= 8)
		GPIOR1 = (uint8_t)v;
}
static void bench_report_P(const char *name, uint32_t iters, uint32_t sum)
{
	char ch;
	do {
		ch = (char)pgm_read_byte(name++);
		GPIOR1 = (uint8_t)ch;
	} while (ch);
	put32(iters);
	put32(sum);
	GPIOR0 = 3;
}
#define bench_report(name, iters, sum) bench_report_P(PSTR(name), iters, sum)
static void bench_end(int code)
{
	GPIOR1 = (uint8_t)code;
	GPIOR0 = 4;
	__asm__ volatile("cli");
	for (;;) {
		set_sleep_mode(SLEEP_MODE_PWR_DOWN);
		sleep_mode();
	}
}
#elif defined(BENCH_RP2350)
/* RP2350 (Hazard3 or Cortex-M33) in a pico-sdk pico2 image under rp2350js: no clock in the program. Calls to four
 * marker functions let c/bench/rp2350-run.mjs read rp2350js's cycle counter: it watches the PC of each function's
 * first instruction. The functions are real code (a store to bench_mark_state; on a board they cost a few cycles and
 * do nothing else); noinline and distinct stores keep gcc from inlining or merging them. */
#include <stdio.h> /* FILE in the line section; no stdio driver is initialised, so its printf goes nowhere */
#define BENCH_SYL_N 100u
#define BENCH_SCREEN_N 20u
#define BENCH_LINE_N 20u
volatile uint32_t bench_mark_state;
__attribute__((noinline, used)) void bench_mark_start(void) { bench_mark_state = 1; }
__attribute__((noinline, used)) void bench_mark_stop(void) { bench_mark_state = 2; }
__attribute__((noinline, used)) void bench_mark_report(const char *name, uint32_t iters, uint32_t sum)
{
	__asm__ volatile("" ::"r"(name), "r"(iters), "r"(sum) : "memory"); /* the arguments stay in a0-a2 / r0-r2 */
	bench_mark_state = 3;
}
__attribute__((noinline, used)) void bench_mark_end(int code)
{
	__asm__ volatile("" ::"r"(code) : "memory");
	bench_mark_state = 4;
	for (;;)
		__asm__ volatile("" ::: "memory");
}
static void bench_start(void) { bench_mark_start(); }
static void bench_stop(void) { bench_mark_stop(); }
static void bench_report(const char *name, uint32_t iters, uint32_t sum) { bench_mark_report(name, iters, sum); }
static void bench_end(int code) { bench_mark_end(code); }
/* Two intervals the runner checks before the cases: an empty one (start, stop: the marks' own cost) and a loop of
 * 1,000,000 x 2 instructions whose cost rp2350js models exactly (Hazard3: addi 1 cycle + a backward bnez its
 * one-entry branch predictor hits, 1 cycle; Cortex-M33: subs 1 + taken bne 2). 32-bit encodings at a 4-aligned
 * label: no misaligned-fetch cycle after the jump. Reported as cal_empty and cal_loop1m. */
static void bench_calibrate(void)
{
	uint32_t n = 1000000u;
	bench_start();
	bench_stop();
	bench_report("cal_empty", 1, 0);
	bench_start();
#if defined(__riscv)
	__asm__ volatile(".option push\n\t.option norvc\n\t.p2align 2\n1:\taddi %0, %0, -1\n\tbnez %0, 1b\n\t.option pop"
	                 : "+r"(n));
#elif defined(__thumb__)
	__asm__ volatile(".p2align 2\n1:\tsubs %0, %0, #1\n\tbne 1b" : "+l"(n)::"cc");
#else
#error "BENCH_RP2350 is for the RP2350's Hazard3 or Cortex-M33"
#endif
	bench_stop();
	bench_report("cal_loop1m", 1000000u, 0);
}
#elif defined(BENCH_ESP32C3) || defined(BENCH_ESP32S3) || defined(BENCH_M33)
/* The same iteration counts as the Pico (100 / 20 / 5). A case's intervals (start/stop pairs) add up in acc; the
 * report prints the case line of pico-run.mjs without insns (integers only, no float printf):
 *   case=NAME iters=N cycles=C per_iter_cycles=P.F sum=S   (+ " ccount=TICKS" on the S3)
 * where "cycles" holds instructions of this core: rdinstret on the C3, the Xtensa ICOUNT register on the S3 (QEMU
 * implements it: it counts the instructions core 0 completes, whatever core 1 does). The instructions between the
 * counter read of bench_start and the one of bench_stop (a handful, the same every interval) are in the count; the
 * printf of a report is outside it. */
#include <stdio.h>
#include <stdlib.h>
#define BENCH_SYL_N 100u
#define BENCH_SCREEN_N 20u
#define BENCH_LINE_N 20u
static uint64_t t0, acc; /* the counter at start; its advance over the intervals since the last report */

#if defined(BENCH_ESP_STUB)
/* Host test of this section (no QEMU, no asm): counters that advance by 1,000 a read (ticks: 32 per 25). */
static uint32_t stub_n;
static uint64_t bench_now(void) { return stub_n += 1000; }
static void bench_exit(int code) { exit(code); }
#endif

#if defined(BENCH_ESP32C3)
#if !defined(BENCH_ESP_STUB)
/* 64-bit instret: high, low, high again until the high word is stable. */
static uint64_t bench_now(void)
{
	uint32_t hi, lo, hi2;
	do {
		__asm__ volatile("rdinstreth %0\n\trdinstret %1\n\trdinstreth %2" : "=r"(hi), "=r"(lo), "=r"(hi2)::"memory");
	} while (hi != hi2);
	return ((uint64_t)hi << 32) | lo;
}
static void bench_exit(int code)
{
	/* SYS_EXIT_EXTENDED: a0 = 0x20, a1 -> {ADP_Stopped_ApplicationExit, code}; the three instructions are the
	 * semihosting trap (QEMU recognises slli/ebreak/srai as 32-bit encodings, hence norvc). */
	static volatile uint32_t args[2];
	register uint32_t a0 __asm__("a0") = 0x20;
	register volatile uint32_t *a1 __asm__("a1") = args;
	args[0] = 0x20026;
	args[1] = (uint32_t)code;
	__asm__ volatile(".option push\n\t.option norvc\n\tslli zero, zero, 0x1f\n\tebreak\n\tsrai zero, zero, 7\n\t.option pop"
	                 : "+r"(a0)
	                 : "r"(a1)
	                 : "memory");
	for (;;)
		;
}
#endif
#elif defined(BENCH_ESP32S3)
#ifndef BENCH_ICOUNT_SHIFT
#error "-DBENCH_ICOUNT_SHIFT=5 (the -icount shift the run uses) is required"
#elif BENCH_ICOUNT_SHIFT != 5
#error "the S3 calibration is for -icount shift=5 only"
#endif
/* QEMU's CCOUNT is the global virtual clock at 40 MHz (25 ns a tick); under -icount shift=N an instruction takes 2^N ns
 * (32 ns at 5): one instruction is 1.28 ticks, so ticks * 25 / 2^N is the number of instructions executed by ALL
 * cores. QEMU also runs the APP CPU (core 1), spinning in the ROM on a double exception, and under -icount it takes
 * turns with core 0 in slices of about 390,630 instructions: core 0's CCOUNT includes them, by a layout-dependent
 * amount (measured; MEASUREMENTS.md). Core 1 cannot be parked in this QEMU (see MEASUREMENTS.md), so the measurement is
 * of core 0 alone: ICOUNT, which the CPU maintains per core. CCOUNT is still read and printed (ccount=), as the
 * evidence of the difference. */
#define BENCH_ICOUNT_DIV (1u << BENCH_ICOUNT_SHIFT)
static uint64_t tk0, acc_ticks;
#if !defined(BENCH_ESP_STUB)
static uint64_t bench_now(void) /* ICOUNT */
{
	uint32_t v;
	__asm__ volatile("rsr.icount %0" : "=a"(v)::"memory");
	return v;
}
static uint32_t bench_ticks(void) /* CCOUNT */
{
	uint32_t v;
	__asm__ volatile("rsr.ccount %0" : "=a"(v)::"memory");
	return v;
}
static void bench_exit(int code) { exit(code); }
/* ICOUNT counts every instruction completed at an interrupt level below ICOUNTLEVEL (15 here); it is zeroed first. */
static void bench_icount_init(void)
{
	uint32_t z = 0, lvl = 15;
	__asm__ volatile("wsr.icount %0\n\twsr.icountlevel %1\n\tisync" ::"a"(z), "a"(lvl) : "memory");
}
#else
static uint32_t bench_ticks(void) { return (uint32_t)((uint64_t)stub_n * BENCH_ICOUNT_DIV / 25); }
static void bench_icount_init(void) {}
#endif
/* Both counters are 32 bits wide: an interval's advance is taken modulo 2^32. */
static void bench_start(void)
{
	tk0 = bench_ticks();
	t0 = bench_now();
}
static void bench_stop(void)
{
	acc += (uint32_t)((uint32_t)bench_now() - (uint32_t)t0);
	acc_ticks += (uint32_t)(bench_ticks() - (uint32_t)tk0);
}
/* The calibration, before the cases: 1,000 straight NOPs (CCOUNT ticks; 1280 expected), then BENCH_CAL_LOOPS loops of
 * 500,000 x (addi, bnez) = 1,000,000 instructions (each longer than core 1's slice), printing the ICOUNT advance and
 * the CCOUNT ticks of each. run-esp32.sh checks the lines: ICOUNT must read the loop's 1,000,000 +- 0.1 %, the
 * measurement the cases rely on; the ticks show what CCOUNT alone would have made of it. */
#define BENCH_CAL_LOOPS 4
static void bench_calibrate(void)
{
	int k;
	bench_icount_init();
#if defined(BENCH_ESP_STUB)
	printf("cal=nop1000 ccount=%lu\n", 1281ul);
	for (k = 0; k < BENCH_CAL_LOOPS; ++k)
		printf("cal=loop1m icount=%lu ccount=%lu\n", 1000000ul, (unsigned long)(1000000ul * BENCH_ICOUNT_DIV / 25));
#else
	uint32_t a, b, ia, ib, n;
	__asm__ volatile("rsr.ccount %0\n\t.rept 1000\n\tnop\n\t.endr\n\trsr.ccount %1" : "=a"(a), "=a"(b)::"memory");
	printf("cal=nop1000 ccount=%lu\n", (unsigned long)(b - a));
	for (k = 0; k < BENCH_CAL_LOOPS; ++k) {
		n = 500000u;
		__asm__ volatile("rsr.ccount %0\n\trsr.icount %2\n\t1: addi %4, %4, -1\n\tbnez %4, 1b\n\trsr.icount %3\n\trsr.ccount %1"
		                 : "=&a"(a), "=&a"(b), "=&a"(ia), "=&a"(ib), "+&a"(n)::"memory");
		printf("cal=loop1m icount=%lu ccount=%lu\n", (unsigned long)(ib - ia), (unsigned long)(b - a));
	}
#endif
}
#else
/* Cortex-M33 under QEMU mps2-an505 with -icount shift=0: virtual time runs one instruction to the nanosecond, so one
 * SysTick tick of the 20 MHz processor clock (50 ns) is exactly 50 instructions executed (the calibration below shows
 * it: a loop of 2,000,000 instructions reads 40,000 ticks). SysTick counts down from 0xFFFFFF; its interrupt counts
 * the wraps, so bench_now() is the tick count since the calibration started the counter, times 50: instructions, with
 * a granularity of 50. No pipeline, memory or flash timing; not RP2350 cycles. The instructions between the counter
 * read of bench_start and that of bench_stop (a few dozen, the same every interval) are in the count; the printf
 * of a report is outside it. The line cases print reads_per_iter with a float printf, also outside every interval. */
#define SYST_CSR (*(volatile uint32_t *)0xE000E010u)
#define SYST_RVR (*(volatile uint32_t *)0xE000E014u)
#define SYST_CVR (*(volatile uint32_t *)0xE000E018u)
#if !defined(BENCH_ESP_STUB)
static volatile uint32_t wraps; /* incremented by systick_handler */
/* Wrap-stable read: `wraps` is read around SYST_CVR and the pair taken again when the SysTick handler ran in between.
 * Under QEMU 8.2 the handler runs when the counter reaches 0 and the counter then reads 0 for one tick (50 instructions)
 * before it reloads, so a read of c == 0 already has the wrap counted in `wraps` but not yet in the counter: it would be
 * one whole period (2^24 ticks) too high. Such a read is taken again (it waits out that one tick). */
static uint64_t bench_now(void)
{
	uint32_t w, c;
	do {
		w = wraps;
		c = SYST_CVR;
	} while (w != wraps || c == 0);
	return ((uint64_t)w * 0x1000000u + (0xFFFFFFu - c)) * 50u;
}
/* ARM semihosting: bkpt 0xAB with the operation in r0 and its argument in r1. */
static uint32_t semi(uint32_t op, const void *arg)
{
	register uint32_t r0 __asm__("r0") = op;
	register const void *r1 __asm__("r1") = arg;
	__asm__ volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
	return r0;
}
/* SYS_EXIT_EXTENDED: r1 -> {ADP_Stopped_ApplicationExit, code}; on 32-bit ARM plain SYS_EXIT cannot carry a code. */
static void bench_exit(int code)
{
	static volatile uint32_t args[2];
	args[0] = 0x20026;
	args[1] = (uint32_t)code;
	semi(0x20, (const void *)args);
	for (;;)
		;
}
/* newlib's stdio ends here: SYS_WRITE0 takes a NUL-terminated string, so the bytes go in copies of at most 63. */
int _write(int fd, const void *buf, size_t n)
{
	const char *p = (const char *)buf;
	size_t done = 0;
	char tmp[64];
	(void)fd;
	while (done < n) {
		size_t k = n - done < 63 ? n - done : 63;
		memcpy(tmp, p + done, k);
		tmp[k] = 0;
		semi(0x04, tmp);
		done += k;
	}
	return (int)n;
}
#endif
/* The calibration, before the cases: SysTick is started (processor clock, interrupt on), and 1,000,000 x (subs, bne) =
 * 2,000,000 instructions are timed twice: ticks is the raw SYST_CVR difference, insns the advance of bench_now(), the
 * clock every row uses. run-m33.sh checks the line: insns must be within 100 of ticks * 50 (the two clocks agree: bench_now's
 * own few instructions fall between its counter read and the loop's) and within 100 of 2,000,000 (the instruction rate,
 * the end-to-end check of the measurement). */
static void bench_calibrate(void)
{
#if defined(BENCH_ESP_STUB)
	printf("cal=loop2m ticks=%lu insns=%lu\n", 40000ul, 2000000ul);
#else
	uint32_t a, b, n = 1000000u, ticks;
	uint64_t i0, i1;
	SYST_RVR = 0xFFFFFFu;
	SYST_CVR = 0;
	SYST_CSR = 7; /* processor clock, interrupt, enable */
	while (SYST_CVR == 0)
		;
	i0 = bench_now();
	a = SYST_CVR;
	__asm__ volatile("1: subs %0, %0, #1\n\tbne 1b" : "+l"(n)::"cc");
	b = SYST_CVR;
	i1 = bench_now();
	ticks = (a - b) & 0xFFFFFFu;
	printf("cal=loop2m ticks=%lu insns=%lu\n", (unsigned long)ticks, (unsigned long)(i1 - i0));
#endif
}
#endif
#if !defined(BENCH_ESP32S3)
static void bench_start(void) { t0 = bench_now(); }
static void bench_stop(void) { acc += bench_now() - t0; }
#endif

static void bench_report(const char *name, uint32_t iters, uint32_t sum)
{
	const uint32_t c = (uint32_t)acc;
	printf("case=%s iters=%lu cycles=%lu per_iter_cycles=%lu.%lu sum=%08lx", name, (unsigned long)iters,
	       (unsigned long)c, (unsigned long)(c / iters), (unsigned long)((c % iters) * 10 / iters),
	       (unsigned long)sum);
#if defined(BENCH_ESP32S3)
	printf(" ccount=%lu", (unsigned long)acc_ticks);
	acc_ticks = 0;
#endif
	printf("\n");
	acc = 0;
}
static void bench_end(int code)
{
	printf("end=%d\n", code);
	fflush(stdout);
	bench_exit(code);
	for (;;)
		;
}
#if defined(BENCH_M33) && !defined(BENCH_ESP_STUB)
/* Start-up: the vector table (initial stack pointer, reset, the faults, SysTick) and the reset handler, which clears
 * .bss (m33.ld) and runs main; a fault ends the run with exit code 99. */
extern uint32_t __bss_start__, __bss_end__, __stack_top;
int main(void);
void fault_handler(void) { bench_end(99); }
void systick_handler(void) { ++wraps; }
void reset_handler(void)
{
	uint32_t *p;
	for (p = &__bss_start__; p < &__bss_end__; ++p)
		*p = 0;
	bench_end(main());
}
__attribute__((section(".vectors"), used)) const void *const bench_vectors[16] = {
    &__stack_top,  (void *)reset_handler, (void *)fault_handler, (void *)fault_handler,
    (void *)fault_handler, (void *)fault_handler, (void *)fault_handler, (void *)fault_handler,
    0,             0,                     0,                     (void *)fault_handler,
    (void *)fault_handler, 0,             (void *)fault_handler, (void *)systick_handler};
#endif
#else
#include <stdio.h>
#include <stdlib.h>
#if defined(BENCH_DOS)
#include <time.h> /* uclock, UCLOCKS_PER_SEC */
#define BENCH_LINE_N 50u
static uclock_t t0;
static double acc_us; /* the sum of the start/stop intervals since the last report */
static void bench_start(void) { t0 = uclock(); }
static void bench_stop(void) { acc_us += (double)(uclock() - t0) * 1e6 / (double)UCLOCKS_PER_SEC; }
#elif defined(BENCH_WASM)
#include <emscripten.h>
#define BENCH_LINE_N 2000u
static double t0;
static double acc_us;
static void bench_start(void) { t0 = emscripten_get_now(); }
static void bench_stop(void) { acc_us += (emscripten_get_now() - t0) * 1e3; }
#else
#include <time.h>
#define BENCH_LINE_N 2000u
static struct timespec t0;
static double acc_us;
static void bench_start(void) { clock_gettime(CLOCK_MONOTONIC, &t0); }
static void bench_stop(void)
{
	struct timespec t1;
	clock_gettime(CLOCK_MONOTONIC, &t1);
	acc_us += (double)(t1.tv_sec - t0.tv_sec) * 1e6 + (double)(t1.tv_nsec - t0.tv_nsec) / 1e3;
}
#endif
#define BENCH_SYL_N 10000u
#define BENCH_SCREEN_N 1000u
static void bench_report(const char *name, uint32_t iters, uint32_t sum)
{
	double us = acc_us;
	acc_us = 0;
	printf("case=%s%s iters=%lu total_us=%.1f per_iter_us=%.2f sum=%08lx\n", name, BENCH_CASE_SUFFIX,
	       (unsigned long)iters, us, us / (double)iters, (unsigned long)sum);
}
static void bench_end(int code)
{
	printf("end=%d\n", code);
	fflush(stdout);
	exit(code);
}
#endif

static uint32_t fnv1a_update(uint32_t h, const uint8_t *p, size_t n)
{
	while (n--)
		h = (h ^ *p++) * 16777619u;
	return h;
}

static uint32_t fnv1a(const uint8_t *p, size_t n) { return fnv1a_update(2166136261u, p, n); }

/* Stops the run with @p code (1..) when @p e is not SVF_OK. */
static void check(svf_err e, int code)
{
	if (e != SVF_OK)
		bench_end(code * 16 + (int)e);
}

/* ---- layout_probe: the build's SVF_LAYOUTS, seen through svf_open_mapped (every build, every platform) --------------
 * Three 48 byte headers (SVFN v3, one 8 x 8 glyph, bpp 1) in the layouts mcu-strict, dos (tight) and simd16, whose tables
 * all lie at file offset 48 = the file length: a build that reads the layout gets SVF_E_RANGE from the code point table
 * (the layout bytes are checked first, in the same order and with the same codes by the mapped open as by the stream
 * open), a build whose SVF_LAYOUTS leaves it out SVF_E_LAYOUT. The sum is (e_simd16 << 16) | (e_dos << 8) | e_strict:
 * 00040404 for a build that reads every layout, 00080804 for one built with -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT.
 * Uses no stream code (the Uno build links none). The headers are constants (PROGMEM on AVR, whose SVF_RD8 reads flash),
 * not built in the function. */
#if defined(BENCH_AVR)
#define PROBE_PGM PROGMEM
#else
#define PROBE_PGM
#endif
#define PROBE_HDR(b9, b10)                                                                                          \
	{'S', 'V', 'F', 'N', 3, 0, 0, 0, 1, (b9), (b10), 0, 1, 0, 8, 8, 8, 0, 0, 0, 0, 0, 0, 0, 48, 0, 0, 0, 0, 0, 0, 0, \
	 48, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 48, 0, 0, 0}
static const uint8_t probe_strict[48] PROBE_PGM = PROBE_HDR(2, 2);  /* REC 4, ROW 1, TAB 4 bytes */
static const uint8_t probe_dos[48] PROBE_PGM = PROBE_HDR(0, 0);     /* 1 / 1 / 1 */
static const uint8_t probe_simd16[48] PROBE_PGM = PROBE_HDR(4, 4);  /* 16 / 1 / 16 */

static void layout_probe(void)
{
	svf_face f;
	uint32_t e_strict, e_dos, e_simd16;

	bench_start();
	memset(&f, 0, sizeof f);
	e_strict = (uint32_t)svf_open_mapped(&f, probe_strict, sizeof probe_strict);
	memset(&f, 0, sizeof f);
	e_dos = (uint32_t)svf_open_mapped(&f, probe_dos, sizeof probe_dos);
	memset(&f, 0, sizeof f);
	e_simd16 = (uint32_t)svf_open_mapped(&f, probe_simd16, sizeof probe_simd16);
	bench_stop();
	bench_report("layout_probe", 1, e_simd16 << 16 | e_dos << 8 | e_strict);
}

/* The kind of the host/DOS/WASM line cases' GRAY target (scaled_case and the line40 cases, the two svf_target_init calls
 * below): SVF_T_GRAY8, or -DBENCH_LINE_KIND=SVF_T_GRAY for the same cases through the parametric kind at its default
 * 8 bits (the checksums are the same). Host-only knob: the Pico/Uno/ESP32 runs (run-pico.sh) build only the BENCH_MCU
 * cases above, which take BENCH_KIND, so run-pico.sh cannot reach it. */
#ifndef BENCH_LINE_KIND
#define BENCH_LINE_KIND SVF_T_GRAY8
#endif

#ifdef BENCH_MCU
/* ---- Pico, Uno (and ESP32): one 16 px 1 bpp jamo face on a 128 x 64 target; set B: 2 bpp band --------------------- */

#ifndef BENCH_KIND
#define BENCH_KIND SVF_T_MONO_PAGE
#endif

/* Set A's buffer: 128 x 64 pixels of the largest kind the build compiles (the Uno has 1 KB: MONO_PAGE only). */
#if defined(BENCH_AVR)
#define BENCH_A_BYTES 1024u
#elif SVF_TARGETS & SVF_TARGET_RGB565
#define BENCH_A_BYTES 16384u
#elif SVF_TARGETS & (SVF_TARGET_GRAY8 | SVF_TARGET_GRAY)
#define BENCH_A_BYTES 8192u
#else
#define BENCH_A_BYTES 1024u
#endif
/* The bytes and the stride of BENCH_KIND's 128 x 64 target. */
#define BENCH_A_USED (BENCH_KIND == SVF_T_RGB565 ? 16384u : BENCH_KIND == SVF_T_GRAY8 || BENCH_KIND == SVF_T_GRAY ? 8192u : 1024u)
#define BENCH_A_STRIDE (BENCH_KIND == SVF_T_RGB565 ? 256u : 128u)

extern const uint8_t bench_face[];
extern const uint32_t bench_face_len;

static uint8_t page[BENCH_A_BYTES];
static uint8_t scratch[32]; /* one 16 x 16 1 bpp cell */
static svf_face face;

/* Four lines of eight syllables: the 128 x 64 screen of 16 px glyphs. */
static const char screen_text[4][25] = {"다람쥐헌쳇바퀴에", "타고파뷁쌓읽가나", "대한민국만세하늘", "바다보다넓은마음"};

#if !defined(BENCH_AVR) && (SVF_TARGETS & (SVF_TARGET_GRAY8 | SVF_TARGET_GRAY | SVF_TARGET_RGB565))
#define BENCH_SET_B 1
extern const uint8_t bench_face16[], bench_face18[];
extern const uint32_t bench_face16_len, bench_face18_len;

#define BAND_W 240
#define BAND_H 24
#define BAND_X 8
#define BAND_Y 19 /* baseline: PAPLG18's ascent 17 plus a margin */
static uint8_t band[BAND_W * BAND_H * 2];
static uint8_t scratch_aa[2 * 18 * 5]; /* two 18 x 18 2 bpp cells */
static svf_face face16, face18;

/* The ten lines of aa_screen10, one band each. */
static const char *const aa_lines[10] = {
    screen_text[0], screen_text[1], screen_text[2], screen_text[3], "다람쥐 헌 쳇바퀴에 타",
    "Score: 120 점", "뷁쌓읽 가나다", "OK 타고파!", "가나다라마바사", "한글 ABC"};

/* The band emptied: bg 0x0010 high byte first on RGB565, 0 on GRAY8. */
static void band_fill(size_t n)
{
	size_t i;
	if (BENCH_KIND == SVF_T_RGB565)
		for (i = 0; i < n; i += 2) {
			band[i] = 0x00;
			band[i + 1] = 0x10;
		}
	else
		memset(band, 0, n);
}
#endif

int main(void)
{
	svf_face *faces[1] = {&face};
	svf_chain c;
	svf_target t;
	uint32_t i;
	uint8_t l;
	int16_t top;

#if defined(BENCH_ESP32S3) || defined(BENCH_M33) || defined(BENCH_RP2350)
	bench_calibrate();
#endif
	memset(&c, 0, sizeof c);
	check(svf_open_mapped(&face, bench_face, bench_face_len), 1);
	if (!svf_is_jamo(&face) || svf_cell_bytes(&face) > sizeof scratch)
		bench_end(2);
	c.faces = faces;
	c.count = 1;
	if (BENCH_A_USED > sizeof page)
		bench_end(7);
	check(svf_target_init(&t, BENCH_KIND, page, BENCH_A_USED, 128, 64, BENCH_A_STRIDE), 3);

	memset(page, 0, BENCH_A_USED);
	bench_start();
	for (i = 0; i < BENCH_SYL_N; ++i)
		svf_draw_utf8(&c, "가", 3, 0, 14, &t, scratch, sizeof scratch);
	bench_stop();
	bench_report("syl_ga", BENCH_SYL_N, fnv1a(page, BENCH_A_USED));

	memset(page, 0, BENCH_A_USED);
	bench_start();
	for (i = 0; i < BENCH_SYL_N; ++i)
		svf_draw_utf8(&c, "뷁", 3, 0, 14, &t, scratch, sizeof scratch);
	bench_stop();
	bench_report("syl_bwelk", BENCH_SYL_N, fnv1a(page, BENCH_A_USED));

	bench_start();
	for (i = 0; i < BENCH_SYL_N; ++i)
		svf_compose(&face, 0xBDC1, scratch, sizeof scratch); /* 뷁 */
	bench_stop();
	bench_report("compose_bwelk", BENCH_SYL_N, fnv1a(scratch, svf_cell_bytes(&face)));

	top = svf_ascent(&face); /* four 16 px lines, each baseline the face's ascent below the line's top row */
	bench_start();
	for (i = 0; i < BENCH_SCREEN_N; ++i) {
		memset(page, 0, BENCH_A_USED);
		for (l = 0; l < 4; ++l)
			svf_draw_utf8(&c, screen_text[l], 24, 0, (int16_t)(top + 16 * l), &t, scratch, sizeof scratch);
	}
	bench_stop();
	bench_report("screen32", BENCH_SCREEN_N, fnv1a(page, BENCH_A_USED));

#if !defined(BENCH_AVR)
	memset(page, 0, BENCH_A_USED);
	bench_start();
	for (i = 0; i < BENCH_SYL_N; ++i)
		svf_draw_utf8(&c, screen_text[0], 24, 0, 14, &t, scratch, sizeof scratch);
	bench_stop();
	bench_report("line8", BENCH_SYL_N, fnv1a(page, BENCH_A_USED));
#endif

	/* The return codes, outside the timed loops: every draw above must have succeeded. */
	check(svf_draw_utf8(&c, screen_text[0], 24, 0, 14, &t, scratch, sizeof scratch), 4);

#ifdef BENCH_SET_B
	if (BENCH_KIND != SVF_T_MONO_PAGE) { /* set B is for GRAY8, GRAY (bits 8) and RGB565 whatever else is compiled in */
		svf_face *faces2[2] = {&face16, &face18};
		svf_chain c2;
		svf_target tb;
		const svf_target_kind kb = BENCH_KIND == SVF_T_RGB565 ? SVF_T_RGB565 : BENCH_KIND == SVF_T_GRAY ? SVF_T_GRAY : SVF_T_GRAY8; /* chosen in C, never #if */
		const size_t nb = kb == SVF_T_RGB565 ? (size_t)BAND_W * BAND_H * 2 : (size_t)BAND_W * BAND_H;
		const uint16_t sb = kb == SVF_T_RGB565 ? BAND_W * 2 : BAND_W;
		size_t aa_len[10];
		uint32_t h;

		memset(&c2, 0, sizeof c2);
		c2.faces = faces2;
		c2.count = 2;
		check(svf_open_mapped(&face16, bench_face16, bench_face16_len), 5);
		check(svf_open_mapped(&face18, bench_face18, bench_face18_len), 6);
		if (svf_chain_scratch_bytes(&c2) > sizeof scratch_aa)
			bench_end(8);
		check(svf_target_init(&tb, kb, band, nb, BAND_W, BAND_H, sb), 9);
		tb.fg565 = 0xFFE0;
		tb.bg565 = 0x0010;
		tb.flags = SVF_TF_565_BIGENDIAN;

		band_fill(nb);
		bench_start();
		for (i = 0; i < BENCH_SYL_N; ++i)
			svf_draw_utf8(&c2, "가", 3, BAND_X, BAND_Y, &tb, scratch_aa, sizeof scratch_aa);
		bench_stop();
		bench_report("aa_syl_ga", BENCH_SYL_N, fnv1a(band, nb));

		band_fill(nb);
		bench_start();
		for (i = 0; i < BENCH_SYL_N; ++i)
			svf_draw_utf8(&c2, "뷁", 3, BAND_X, BAND_Y, &tb, scratch_aa, sizeof scratch_aa);
		bench_stop();
		bench_report("aa_syl_bwelk", BENCH_SYL_N, fnv1a(band, nb));

		band_fill(nb);
		bench_start();
		for (i = 0; i < BENCH_SCREEN_N; ++i)
			svf_draw_utf8(&c2, "다람쥐 헌 쳇바퀴에 타", sizeof "다람쥐 헌 쳇바퀴에 타" - 1, BAND_X, BAND_Y, &tb,
			              scratch_aa, sizeof scratch_aa);
		bench_stop();
		bench_report("aa_line12", BENCH_SCREEN_N, fnv1a(band, nb));

		/* Ten bands a screen; only the clear and the draw are timed (one start/stop pair a band: the platforms add
		 * the intervals), the checksum of each band, carried across the ten, is not. */
		for (l = 0; l < 10; ++l)
			aa_len[l] = strlen(aa_lines[l]);
		for (i = 0; i < 5; ++i) {
			h = 2166136261u;
			for (l = 0; l < 10; ++l) {
				bench_start();
				band_fill(nb);
				svf_draw_utf8(&c2, aa_lines[l], aa_len[l], BAND_X, BAND_Y, &tb, scratch_aa, sizeof scratch_aa);
				bench_stop();
				h = fnv1a_update(h, band, nb);
			}
		}
		bench_report("aa_screen10", 5, h);
		check(svf_draw_utf8(&c2, aa_lines[4], aa_len[4], BAND_X, BAND_Y, &tb, scratch_aa, sizeof scratch_aa), 10);
	}
#endif
	layout_probe();
	bench_end(0);
	return 0;
}

#else
/* ---- DOS, WASM, host: PAPLG16 + PAPLG18, one 40 code point line ------------------------------------------------ */

#define LINE_W 640
#define LINE_H 24
#define LINE_Y 19 /* baseline: PAPLG18's ascent 17 plus a margin */
#define SCALED_W 960 /* line40_scaled32: the line at 3/2 is 749 x 26 + 6 pixels */
#define SCALED_H 36
#define SCALED_Y 28

/* 40 code points: ASCII from PAPLG16, 18 syllables composed from PAPLG18's pieces, spaces and punctuation. */
static const char line_text[] = "Score: 120 점, 다람쥐 헌 쳇바퀴에 타고파! 뷁쌓읽 가나다 OK";

#if defined(BENCH_DOS) || defined(BENCH_HOST)
#define PACKED_H 32 /* the 24 px cases: 640 x 32 pixels of up to 4 bytes, the largest buffer any case needs */
static uint8_t screen[LINE_W * PACKED_H * 4];
#else
static uint8_t screen[SCALED_W * SCALED_H];
#endif
#define GRAY8_BYTES (LINE_W * LINE_H)
static uint8_t scratch[1024]; /* two 24 x 24 2 bpp cells (a streamed face without a block cache): 336; the 3/2 line: 909 */
static uint8_t syllables[64 * (8 + 18 * 5)];
static svf_face f16, f18;

typedef struct {
	const uint8_t *data; /* embedded bytes (WASM, host) */
	FILE *fp;            /* or a file (DOS) */
} source;

#if defined(BENCH_DOS)
static const uint8_t *data16, *data18, *data24a, *data24m;
static uint32_t len16, len18, len24a, len24m;

/* The whole file in memory (malloc; not timed). */
static const uint8_t *slurp(const char *path, uint32_t *len)
{
	FILE *fp = fopen(path, "rb");
	uint8_t *p;
	long n;

	if (!fp || fseek(fp, 0, SEEK_END) || (n = ftell(fp)) <= 0 || fseek(fp, 0, SEEK_SET))
		bench_end(90);
	p = (uint8_t *)malloc((size_t)n);
	if (!p || fread(p, 1, (size_t)n, fp) != (size_t)n)
		bench_end(91);
	fclose(fp);
	*len = (uint32_t)n;
	return p;
}
#else
extern const uint8_t bench_face16[], bench_face18[];
extern const uint32_t bench_face16_len, bench_face18_len;
#define data16 bench_face16
#define data18 bench_face18
#define len16 bench_face16_len
#define len18 bench_face18_len
#if defined(BENCH_HOST)
extern const uint8_t bench_face24a[], bench_face24m[];
extern const uint32_t bench_face24a_len, bench_face24m_len;
#define data24a bench_face24a
#define data24m bench_face24m
#define len24a bench_face24a_len
#define len24m bench_face24m_len
#endif
#endif

static long read_src(void *ctx, uint32_t offset, uint8_t *dst, uint32_t len)
{
	source *s = (source *)ctx;

	if (s->fp) {
		if (fseek(s->fp, (long)offset, SEEK_SET))
			return -1;
		return (long)fread(dst, 1, len, s->fp);
	}
	memcpy(dst, s->data + offset, len);
	return (long)len;
}

static svf_target target;

/* Draws the line @p n times (screen cleared once, before), timed; reports it as @p name, then the read callback
 * calls a draw (streamed faces). */
static void line_case(const char *name, const svf_chain *c, uint32_t n)
{
	svf_err e = SVF_OK;
	uint32_t i, r0 = svf_stream_reads(&f16) + svf_stream_reads(&f18);

	memset(screen, 0, sizeof screen);
	bench_start();
	for (i = 0; i < n; ++i)
		e = svf_draw_utf8(c, line_text, sizeof line_text - 1, 0, LINE_Y, &target, scratch, sizeof scratch);
	bench_stop();
	check(e, 5);
	bench_report(name, n, fnv1a(screen, GRAY8_BYTES));
	printf("  reads_per_iter=%.1f\n", (double)(svf_stream_reads(&f16) + svf_stream_reads(&f18) - r0) / (double)n);
}

/* The same line at 3/2 (svf_chain scale_num 3, scale_den 2) on GRAY8 960 x 36, baseline 28, mapped faces, no syllable
 * cache: BENCH_LINE_N draws of a buffer cleared once; the chain's scale is reset afterwards. */
static void scaled_case(svf_chain *c)
{
	svf_target t;
	svf_err e = SVF_OK;
	uint32_t i;

	c->scale_num = 3;
	c->scale_den = 2;
	if (svf_chain_scratch_bytes(c) > sizeof scratch)
		bench_end(97);
	check(svf_target_init(&t, BENCH_LINE_KIND, screen, sizeof screen, SCALED_W, SCALED_H, SCALED_W), 11);
	memset(screen, 0, SCALED_W * SCALED_H);
	bench_start();
	for (i = 0; i < BENCH_LINE_N; ++i)
		e = svf_draw_utf8(c, line_text, sizeof line_text - 1, 0, SCALED_Y, &t, scratch, sizeof scratch);
	bench_stop();
	check(e, 11);
	bench_report("line40_scaled32", BENCH_LINE_N, fnv1a(screen, SCALED_W * SCALED_H));
	c->scale_num = c->scale_den = 0;
}

#if defined(BENCH_DOS) || defined(BENCH_HOST)
/* Draws the line @p n times on a @p kind target of @p w x @p h (stride w * @p bpp bytes) as @p name: index_base 16,
 * index_levels 3, fg565 0xFFFF, fg888 0xFFFFFF, bg 0, the buffer cleared to 0 once; the checksum covers
 * rows * stride. */
static void packed_case(const char *name, svf_target_kind kind, const svf_chain *c, int16_t w, int16_t h,
                        int16_t baseline, uint16_t bpp)
{
	svf_target t;
	svf_err e = SVF_OK;
	uint16_t stride = (uint16_t)(w * bpp);
	uint32_t i;

	check(svf_target_init(&t, kind, screen, sizeof screen, w, h, stride), 7);
	t.index_base = 16;
	t.index_levels = 3;
	t.fg565 = 0xFFFF;
	t.bg565 = 0;
	t.fg888 = 0xFFFFFFu;
	t.bg888 = 0;
	if (svf_chain_scratch_bytes(c) > sizeof scratch)
		bench_end(96);
	memset(screen, 0, sizeof screen);
	bench_start();
	for (i = 0; i < BENCH_LINE_N; ++i)
		e = svf_draw_utf8(c, line_text, sizeof line_text - 1, 0, baseline, &t, scratch, sizeof scratch);
	bench_stop();
	check(e, 8);
	bench_report(name, BENCH_LINE_N, fnv1a(screen, (size_t)h * stride));
}

/* The five kinds (the last two of @p full only when @p full), named PREFIX_<kind>. */
static void packed_kinds(const char *const names[5], const svf_chain *c, int16_t h, int16_t baseline, int full)
{
	static const svf_target_kind kind[5] = {SVF_T_INDEXED8, SVF_T_RGB555, SVF_T_RGB565, SVF_T_XRGB8888, SVF_T_RGB888};
	static const uint16_t bpp[5] = {1, 2, 2, 4, 3};
	int k;

	for (k = 0; k < 5; ++k)
		if (full || k == 0 || k == 2 || k == 3)
			packed_case(names[k], kind[k], c, LINE_W, h, baseline, bpp[k]);
}

static void packed_cases(const svf_chain *c16_18)
{
	static const char *const n16[5] = {"line40_indexed8", "line40_rgb555", "line40_rgb565", "line40_xrgb8888",
	                                   "line40_rgb888"};
	static const char *const n24[5] = {"line40_24_indexed8", "line40_24_rgb555", "line40_24_rgb565",
	                                   "line40_24_xrgb8888", "line40_24_rgb888"};
	static const char *const n24m[5] = {"line40_24m_indexed8", "line40_24m_rgb555", "line40_24m_rgb565",
	                                    "line40_24m_xrgb8888", "line40_24m_rgb888"};
	static svf_face f24a, f24m;
	svf_face *fa[1] = {&f24a}, *fm[1] = {&f24m};
	svf_chain ca, cm;

	packed_kinds(n16, c16_18, LINE_H, LINE_Y, 1);
	check(svf_open_mapped(&f24a, data24a, len24a), 9);
	check(svf_open_mapped(&f24m, data24m, len24m), 10);
	memset(&ca, 0, sizeof ca);
	memset(&cm, 0, sizeof cm);
	ca.faces = fa;
	ca.count = 1;
	cm.faces = fm;
	cm.count = 1;
	packed_kinds(n24, &ca, PACKED_H, 25, 1);
	packed_kinds(n24m, &cm, PACKED_H, 25, 0);
}
#endif

/* Opens @p f streamed from @p src (file length @p len): tables in @p tables, a block cache of @p slots 1 KB blocks
 * in @p cache (none with 0). */
static void open_stream(svf_face *f, source *src, uint32_t len, uint8_t *tables, size_t tables_len, uint8_t *cache,
                        uint16_t slots)
{
	svf_err e;
	if (svf_stream_tables_size(read_src, src, len, &e) > tables_len)
		bench_end(92);
	check(svf_open_stream(f, read_src, src, len, tables, tables_len, cache, (size_t)slots * (1024 + 8), 1024), 6);
}

int main(void)
{
	static uint8_t tables16[4096], tables18[32768], cache16[16 * (1024 + 8)],
	    cache18[64 * (1024 + 8)];
	svf_face *faces[2] = {&f16, &f18};
	source s16, s18;
	svf_chain c;

#if defined(BENCH_DOS)
	data16 = slurp("PAPLG16.SVF", &len16);
	data18 = slurp("PAPLG18.SVF", &len18);
	data24a = slurp("MARUS24A.SVF", &len24a);
	data24m = slurp("MARUS24.SVF", &len24m);
#endif
#if defined(BENCH_M33) || defined(BENCH_RP2350)
	bench_calibrate();
#endif
	memset(&c, 0, sizeof c);
	c.faces = faces;
	c.count = 2;
	check(svf_target_init(&target, BENCH_LINE_KIND, screen, sizeof screen, LINE_W, LINE_H, LINE_W), 1);
	if (svf_chain_scratch_bytes(&c) > sizeof scratch)
		bench_end(93);

	check(svf_open_mapped(&f16, data16, len16), 2);
	check(svf_open_mapped(&f18, data18, len18), 3);
	line_case("line40_mapped", &c, BENCH_LINE_N);
	check(svf_chain_cache(&c, syllables, sizeof syllables), 4);
	line_case("line40_mapped_cache", &c, BENCH_LINE_N);
	check(svf_chain_cache(&c, NULL, 0), 4);
	scaled_case(&c);
#if defined(BENCH_DOS) || defined(BENCH_HOST)
	packed_cases(&c);
#endif

	memset(&s16, 0, sizeof s16);
	memset(&s18, 0, sizeof s18);
#if defined(BENCH_DOS)
	s16.fp = fopen("PAPLG16.SVF", "rb");
	s18.fp = fopen("PAPLG18.SVF", "rb");
	if (!s16.fp || !s18.fp)
		bench_end(94);
#else
	s16.data = data16;
	s18.data = data18;
#endif
	/* Caches that hold the line's blocks (PAPLG16's whole glyph data, PAPLG18's 37 blocks), then smaller ones. */
	open_stream(&f16, &s16, len16, tables16, sizeof tables16, cache16, 16);
	open_stream(&f18, &s18, len18, tables18, sizeof tables18, cache18, 64);
	line_case("line40_stream_cold", &c, 1);
	line_case("line40_stream_warm", &c, BENCH_LINE_N);
	open_stream(&f16, &s16, len16, tables16, sizeof tables16, cache16, 4);
	open_stream(&f18, &s18, len18, tables18, sizeof tables18, cache18, 16);
	line_case("line40_stream_small", &c, BENCH_LINE_N);

	open_stream(&f16, &s16, len16, tables16, sizeof tables16, NULL, 0);
	open_stream(&f18, &s18, len18, tables18, sizeof tables18, NULL, 0);
	if (svf_chain_scratch_bytes(&c) > sizeof scratch)
		bench_end(95);
	line_case("line40_stream_nocache", &c, BENCH_LINE_N / 10);
	layout_probe();
	bench_end(0);
	return 0;
}
#endif
