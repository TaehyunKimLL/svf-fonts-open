/* fix_sleep.c - main sleeps 20 s (alarm-driven: a few host iterations): the run ends at the 10 s emulated-time cap. */
#include "pico/stdlib.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	sleep_ms(20000);
	svf_port_idle();
	return 0;
}
