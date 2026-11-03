/* avr-run.c ELF - runs a c/bench/bench.c build (-DBENCH_AVR) on simavr's ATmega328P at 16 MHz and prints one line a
 * case: "case=NAME iters=N cycles=C per_iter_cycles=P sum=S". A host program linked with libsimavr
 * (c/bench/run-avr.sh builds it).
 *
 * The program marks each case by writing GPIOR0: 1 start, 2 stop, 3 report (after the name, a NUL, the iterations and
 * the checksum, u32 little-endian, written byte by byte to GPIOR1), 4 end (after the exit code on GPIOR1). The cycles
 * are simavr's cycle counter (avr->cycle: the AVR instruction timings) at the start and stop writes. The program ends
 * by sleeping with interrupts off, which stops simavr (cpu_Done).
 */
#include <simavr/sim_avr.h>
#include <simavr/sim_elf.h>
#include <simavr/sim_io.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define GPIOR0_ADDR 0x3E /* data-space addresses (I/O + 0x20) on the ATmega328P */
#define GPIOR1_ADDR 0x4A

static avr_cycle_count_t start, stop;
static uint8_t buf[80];
static size_t used;
static int exit_code = -1;

static void on_data(struct avr_t *avr, avr_io_addr_t addr, uint8_t v, void *param)
{
	(void)avr, (void)addr, (void)param;
	if (used < sizeof buf)
		buf[used++] = v;
}

static uint32_t u32_at(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void on_mark(struct avr_t *avr, avr_io_addr_t addr, uint8_t v, void *param)
{
	(void)addr, (void)param;
	if (v == 1) {
		start = avr->cycle;
	} else if (v == 2) {
		stop = avr->cycle;
	} else if (v == 3) {
		size_t n = strnlen((const char *)buf, used);
		if (n + 9 != used) {
			fprintf(stderr, "avr-run: bad report (%zu bytes)\n", used);
			exit_code = 99;
			avr->state = cpu_Done;
		} else {
			uint32_t iters = u32_at(buf + n + 1), sum = u32_at(buf + n + 5);
			unsigned long long cycles = (unsigned long long)(stop - start);
			printf("case=%s iters=%lu cycles=%llu per_iter_cycles=%.1f sum=%08lx\n", (const char *)buf,
			       (unsigned long)iters, cycles, (double)cycles / iters, (unsigned long)sum);
		}
	} else if (v == 4) {
		exit_code = used ? buf[used - 1] : 98;
	}
	if (v >= 3)
		used = 0;
}

int main(int argc, char **argv)
{
	elf_firmware_t fw;
	avr_t *avr;
	int state;

	if (argc != 2) {
		fprintf(stderr, "usage: avr-run ELF\n");
		return 2;
	}
	memset(&fw, 0, sizeof fw);
	if (elf_read_firmware(argv[1], &fw)) {
		fprintf(stderr, "avr-run: cannot read %s\n", argv[1]);
		return 2;
	}
	avr = avr_make_mcu_by_name("atmega328p");
	if (!avr) {
		fprintf(stderr, "avr-run: no atmega328p core\n");
		return 2;
	}
	avr_init(avr);
	avr->frequency = 16000000;
	avr->log = LOG_WARNING;
	avr_load_firmware(avr, &fw);
	avr_register_io_write(avr, GPIOR0_ADDR, on_mark, NULL);
	avr_register_io_write(avr, GPIOR1_ADDR, on_data, NULL);
	do
		state = avr_run(avr);
	while (state != cpu_Done && state != cpu_Crashed && exit_code < 0);
	printf("end=%d total_cycles=%llu\n", exit_code, (unsigned long long)avr->cycle);
	return exit_code == 0 && state != cpu_Crashed ? 0 : 1;
}
