/* main.c - Raspberry Pi Pico (pico-sdk): the profile chosen at build time (SVF_PROFILE: colour, grey or mono) drawn on
 * its display. Pins, bus set-up and the panel's start-up live in the display driver (disp_*.c). No stdio and no
 * semihosting: under rp2040js a BKPT fails the screen run. */
#include "display.h"
#include "pico/stdlib.h"
#include "profile.h"

/* Never returns. Its own symbol (the screen runner looks it up with nm), so the compiler must not inline it. */
__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	display_init();
	profile_run();
	svf_port_idle();
	return 0;
}
