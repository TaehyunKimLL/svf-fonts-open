/* Host check of ch582_i2c_write (c/ports/ch582/i2c.c): the seven I2C_* functions of the SDK are defined here as a
 * scripted peripheral that counts every poll and logs START, address byte, data bytes, CLEAR_AF and STOP. Every wait of
 * the function has to end within CH582_I2C_SPIN polls (AF reads counted apart: the loop reads AF once per poll), a NACK
 * has to end the wait at once, and STOP has to follow every failure that began a transfer. Prints
 * port-check-ch582-i2c: OK. Build: -I c/ports/ch582/stub -I c/ports/ch582 test_ch582_i2c.c c/ports/ch582/i2c.c */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "CH58x_common.h"
#include "i2c.h"

/* the stub header's recording hooks: unused here, but declared there */
void svf_rec_bytes(int dc, const uint8_t *p, size_t n) { (void)dc; (void)p; (void)n; }
void svf_rec_gpio(int pin, int level) { (void)pin; (void)level; }
void svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop) { (void)addr; (void)p; (void)n; (void)nostop; }
void svf_rec_sleep(uint32_t ms) { (void)ms; }
void svf_rec_cfg(int what, int a, int b, int c, int d) { (void)what; (void)a; (void)b; (void)c; (void)d; }
int svf_stub_dc_pin;

static void fail(int line)
{
	fprintf(stderr, "port-check-ch582-i2c: FAIL at line %d\n", line);
	exit(1);
}
#define CHECK(c) do { if (!(c)) fail(__LINE__); } while (0)

/* the script of one case */
static struct {
	int busy_stuck;      /* BUSY never clears */
	int modesel_never;   /* MODE_SELECT never completes */
	int addr_nack;       /* after the address byte: AF set, TRANSMITTER_MODE_SELECTED never */
	int data_nack;       /* after the first data byte: AF set, BYTE_TRANSMITTED never; TXE stays set (the CH58x TxE
			      * does not clear on a NACK) */
	int last_nack;       /* after the LAST data byte: AF set, BYTE_TRANSMITTED never */
	int txe_af;          /* after the first data byte: AF set while TXE stays set, BYTE_TRANSMITTED never */
	int tm_never;        /* TRANSMITTER_MODE_SELECTED never completes, AF clear */
	int txe_never;       /* TXE never sets, AF clear */
	int bt_never;        /* BYTE_TRANSMITTED never completes, AF clear */
	int delay;           /* every wait is ready only from its (delay + 1)th poll on */
} script;
/* the state */
static int started, addr_sent, ndata, af, txe_seen, nbytes;
static char log_[256];
static int polls, max_polls, af_polls, max_af_polls, polls_after_af; /* in the current wait: reset by every action */

static void act(const char *fmt, unsigned v)
{
	char tmp[32];

	snprintf(tmp, sizeof tmp, fmt, v);
	CHECK(strlen(log_) + strlen(tmp) + 2 < sizeof log_);
	if (log_[0]) strcat(log_, ",");
	strcat(log_, tmp);
	polls = af_polls = 0;
}
static void note_poll(void)
{
	if (++polls > max_polls) max_polls = polls;
	if (af) ++polls_after_af;
}

void I2C_GenerateSTART(FunctionalState s) { CHECK(s == ENABLE); act("START%u", 0); started = 1; }
void I2C_GenerateSTOP(FunctionalState s) { CHECK(s == ENABLE); act("STOP%u", 0); }
void I2C_Send7bitAddress(uint8_t a, uint8_t dir)
{
	CHECK(dir == I2C_Direction_Transmitter);
	act("ADDR%02X", a);
	addr_sent = 1;
	if (script.addr_nack) af = 1;
}
void I2C_SendData(uint8_t d)
{
	act("D%02X", d);
	++ndata;
	CHECK(txe_seen); /* a byte goes out only after its TXE wait came ready */
	txe_seen = 0;
	if (script.data_nack || script.txe_af || (script.last_nack && ndata == nbytes)) af = 1;
}
void I2C_ClearFlag(uint32_t f) { CHECK(f == I2C_FLAG_AF); act("CLRAF%u", 0); af = 0; }
/* a wait that came ready starts the next one from poll 0 (the delay applies to every wait) */
static int came(int ready)
{
	if (ready) polls = 0;
	return ready;
}
uint8_t I2C_CheckEvent(uint32_t e)
{
	note_poll();
	if (polls <= script.delay) return 0;
	if (e == I2C_EVENT_MASTER_MODE_SELECT) return came(started && !script.modesel_never);
	if (e == I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED)
		return came(addr_sent && !script.addr_nack && !script.tm_never);
	if (e == I2C_EVENT_MASTER_BYTE_TRANSMITTED)
		return came(ndata > 0 && !script.data_nack && !script.last_nack && !script.txe_af && !script.bt_never);
	CHECK(0);
	return 0;
}
FlagStatus I2C_GetFlagStatus(uint32_t f)
{
	if (f == I2C_FLAG_AF) {
		if (++af_polls > max_af_polls) max_af_polls = af_polls;
		return af ? SET : RESET;
	}
	note_poll();
	if (f == I2C_FLAG_BUSY) return script.busy_stuck || polls <= script.delay ? SET : (came(1), RESET);
	if (f == I2C_FLAG_TXE) { /* TXE stays set next to AF after a NACK: the driver's AF check has to win */
		if (addr_sent && polls > script.delay && !script.txe_never) {
			came(1);
			txe_seen = 1;
			return SET;
		}
		return RESET;
	}
	CHECK(0);
	return RESET;
}

/* one case: reset the peripheral, run the write, compare result and log, bound the polls */
static void run_s(const char *name, const char *flags, int delay, const uint8_t *buf, size_t n, int want,
		  const char *want_log)
{
	int r;

	memset(&script, 0, sizeof script);
	script.busy_stuck = !!strstr(flags, "busy"); script.modesel_never = !!strstr(flags, "modesel");
	script.addr_nack = !!strstr(flags, "addrnack"); script.data_nack = !!strstr(flags, "datanack");
	script.txe_af = !!strstr(flags, "txeaf"); script.tm_never = !!strstr(flags, "tm");
	script.txe_never = !!strstr(flags, "txe_never"); script.bt_never = !!strstr(flags, "bt");
	script.delay = delay; script.last_nack = !!strstr(flags, "lastnack");
	nbytes = (int)n;
	started = addr_sent = ndata = af = txe_seen = 0;
	log_[0] = 0;
	polls = max_polls = af_polls = max_af_polls = polls_after_af = 0;
	r = ch582_i2c_write(0x3C, buf, n);
	if (r != want || strcmp(log_, want_log)) {
		fprintf(stderr, "port-check-ch582-i2c: FAIL %s: result %d (want %d), log \"%s\" (want \"%s\")\n", name, r, want,
			log_, want_log);
		exit(1);
	}
	CHECK(max_polls <= CH582_I2C_SPIN + 1);
	CHECK(max_af_polls <= CH582_I2C_SPIN + 1);
	if (script.addr_nack || script.data_nack || script.txe_af || script.last_nack)
		CHECK(polls_after_af == 0); /* AF is read first: the wait that follows the NACK ends on its first read */
	if (want == -1 && *flags && !strstr(flags, "nack") && !strstr(flags, "af"))
		CHECK(max_polls >= CH582_I2C_SPIN); /* no AF: the wait ran the whole spin count */
	if (delay) CHECK(max_polls == delay + 1); /* waited until ready, no longer */
}

static void run(const char *name, int busy_stuck, int modesel_never, int addr_nack, int data_nack, const uint8_t *buf,
		size_t n, int want, const char *want_log)
{
	char f[64] = "";

	if (busy_stuck) strcat(f, "busy,");
	if (modesel_never) strcat(f, "modesel,");
	if (addr_nack) strcat(f, "addrnack,");
	if (data_nack) strcat(f, "datanack,");
	run_s(name, f, 0, buf, n, want, want_log);
}

int main(void)
{
	alarm(30); /* a regressed bound hangs: fail instead */
	static const uint8_t cmd[2] = {0x00, 0xAE}, cmd3[3] = {0x00, 0xAE, 0xAF};

	run("all ready", 0, 0, 0, 0, cmd, 2, 0, "START0,ADDR78,D00,DAE,STOP0");
	run("busy stuck", 1, 0, 0, 0, cmd, 2, -1, "STOP0");
	run("no mode select", 0, 1, 0, 0, cmd, 2, -1, "START0,STOP0");
	run("address nack", 0, 0, 1, 0, cmd, 2, -1, "START0,ADDR78,CLRAF0,STOP0");
	run("data nack", 0, 0, 0, 1, cmd, 2, -1, "START0,ADDR78,D00,CLRAF0,STOP0");
	run_s("TXE with AF", "txeaf", 0, cmd3, 3, -1, "START0,ADDR78,D00,CLRAF0,STOP0");
	run_s("last byte nack", "lastnack", 0, cmd, 2, -1, "START0,ADDR78,D00,DAE,CLRAF0,STOP0");
	run_s("no transmitter mode", "tm", 0, cmd, 2, -1, "START0,ADDR78,STOP0");
	run_s("TXE never", "txe_never", 0, cmd, 2, -1, "START0,ADDR78,STOP0");
	run_s("byte transmitted never", "bt", 0, cmd, 2, -1, "START0,ADDR78,D00,DAE,STOP0");
	run_s("delayed ready", "", 5, cmd, 2, 0, "START0,ADDR78,D00,DAE,STOP0");
	run("null buffer", 0, 0, 0, 0, NULL, 2, -1, "");
	run("empty", 0, 0, 0, 0, cmd, 0, -1, "");
	CHECK(ch582_i2c_write(0x80, cmd, 2) == -1 && log_[0] == 0); /* not a 7-bit address */
	printf("port-check-ch582-i2c: OK\n");
	return 0;
}
