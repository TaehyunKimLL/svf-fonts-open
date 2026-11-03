/* fix_bkpt.c - main traps (a BKPT under the pico-sdk's fault handling); svf_port_idle follows it, so a runner that
 * ignored the BKPT would stop at the idle symbol and report ok. */
#include "pico/stdlib.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	volatile int go = 1; /* the compiler must keep the call below: the trap is not provably final */

	if (go)
		__builtin_trap();
	svf_port_idle();
	return 0;
}
