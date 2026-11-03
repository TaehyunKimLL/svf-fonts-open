/* main_qemu.c - the same profile for the QEMU screen run (c/ports/check/esp-screen.py): a bare-metal main over newlib
 * semihosting (the console is stdout), no IDF header. "screen=ready" tells the runner the profile has drawn and shown;
 * svf_port_idle (a profile failure) prints "screen=failed" instead, so the runner stops at once on an unexpected line. */
#include <stdio.h>
#include "display.h"
#include "profile.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	printf("screen=failed\n");
	fflush(stdout);
	for (;;)
		;
}

int main(void)
{
	display_init();
	profile_run();
	printf("screen=ready\n");
	fflush(stdout);
	for (;;)
		;
}
