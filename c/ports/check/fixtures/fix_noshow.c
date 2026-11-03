/* fix_noshow.c - the SSD1306 is started (display_init) and nothing is shown: the panel's show count stays 0. */
#include "display.h"
#include "pico/stdlib.h"

__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		sleep_ms(1000);
}

int main(void)
{
	display_init();
	svf_port_idle();
	return 0;
}
