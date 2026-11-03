/* fix_wfi.c - main waits for an interrupt with no alarm and no interrupt enabled: the core sleeps for ever. */
#include "hardware/sync.h"
#include "pico/stdlib.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	__wfi();
	svf_port_idle();
	return 0;
}
