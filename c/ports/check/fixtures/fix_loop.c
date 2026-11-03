/* fix_loop.c - main spins on a volatile flag that is never cleared: no WFI, no alarm, the host iteration bound ends it. */
#include "pico/stdlib.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	volatile int go = 1;

	while (go)
		;
	svf_port_idle();
	return 0;
}
