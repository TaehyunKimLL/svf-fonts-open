/* main.c - YD-CH582M firmware: system clock, status LED, panel, the profile's screen once, then the LED loop.
 * No stdio, no interrupts. The LED codes are in led.h. */
#include "CH58x_common.h"
#include "display.h"
#include "led.h"
#include "profile.h"

/* never returns; an own, non-inlined symbol (the screen runner looks it up) */
__attribute__((noinline)) void svf_port_idle(void)
{
	uint32_t period;

	if (display_state() == DISPLAY_SHOWN) {
		led_on();
		for (;;)
			DelayMs(LED_STEADY_MS);
	}
	period = display_state() == DISPLAY_I2C_FAILED ? LED_I2C_FAIL_MS : LED_SVF_FAIL_MS;
	for (;;) {
		led_toggle();
		DelayMs(period);
	}
}

int main(void)
{
	/* 24 MHz: the I2C module clock must be 2..36 MHz (I2C_Init writes the system clock in MHz into its FREQ field) and
	 * with I2C_DutyCycle_2 (disp_sh1106.c) the SDK's divider gives CCR = 24e6 / (400e3 * 3) = 20, exactly 400 kHz SCL.
	 * Must match FREQ_SYS in the Makefile (the SDK's delay loops are calibrated by it). */
	SetSysClock(CLK_SOURCE_PLL_24MHz);
	led_init();
	display_init();
	profile_run();
	svf_port_idle();
	return 0; /* not reached */
}
