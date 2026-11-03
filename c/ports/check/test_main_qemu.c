/* test_main_qemu.c - main_qemu.c on the host, with recording stubs for display_init, profile_run, printf and fflush:
 * main runs display_init, then profile_run, then prints "screen=ready" and flushes it; svf_port_idle (a profile failure)
 * prints "screen=failed" and flushes. main_qemu.c is compiled with -include test_main_qemu_hooks.h and
 * -Dmain=qemu_main -Dsvf_port_idle=qemu_idle (this file calls them), and never returns: the flush stub leaves it by longjmp. */
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int qemu_main(void);
void qemu_idle(void);

static char events[256];
static jmp_buf out;
static int flushes;

static void note(const char *s)
{
	if (strlen(events) + strlen(s) < sizeof events)
		strcat(events, s);
}

void display_init(void) { note("display_init;"); }
void profile_run(void) { note("profile_run;"); }

int test_printf(const char *fmt, ...)
{
	char buf[64];
	va_list ap;

	va_start(ap, fmt);
	vsnprintf(buf, sizeof buf, fmt, ap);
	va_end(ap);
	note("printf:");
	note(buf);
	note(";");
	return 0;
}

int test_fflush(FILE *f)
{
	if (f != stdout)
		return -1;
	note("fflush;");
	flushes++;
	longjmp(out, 1);
}

static int failures;
#define CHECK(c, what) do { if (!(c)) { fprintf(stderr, "port-check-main-qemu: FAIL %s: events '%s'\n", what, events); failures++; } } while (0)

int main(void)
{
	events[0] = 0;
	if (setjmp(out) == 0)
		qemu_main();
	CHECK(strcmp(events, "display_init;profile_run;printf:screen=ready\n;fflush;") == 0, "main order and ready line");
	CHECK(flushes == 1, "ready line flushed");

	events[0] = 0;
	if (setjmp(out) == 0)
		qemu_idle();
	CHECK(strcmp(events, "printf:screen=failed\n;fflush;") == 0, "svf_port_idle failed line");
	CHECK(flushes == 2, "failed line flushed");
	if (failures)
		return 1;
	printf("port-check-main-qemu: OK\n");
	return 0;
}
