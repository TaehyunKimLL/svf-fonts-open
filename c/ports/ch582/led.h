/* led.h - the status LED of the YD-CH582M: PB4, active low (the board's assumption: the LED sits between 3V3 and
 * the pin). It is the only output of the firmware besides the panel: no stdio, no interrupts.
 * Blink codes (main.c, svf_port_idle): steady on = the screen was shown; 2 Hz = an I2C write failed (no panel, wrong
 * address, stuck bus); 8 Hz = the drawing failed (an svf_* error). */
#ifndef CH582_LED_H
#define CH582_LED_H

#include "CH58x_common.h"

#define LED_PIN GPIO_Pin_4
#define LED_STEADY_MS 1000  /* the shown state sleeps in steps of this */
#define LED_I2C_FAIL_MS 250 /* toggle period: 2 Hz */
#define LED_SVF_FAIL_MS 62  /* toggle period: 8 Hz */

static inline void led_init(void)
{
	GPIOB_SetBits(LED_PIN); /* off, before the pin drives */
	GPIOB_ModeCfg(LED_PIN, GPIO_ModeOut_PP_5mA);
}
static inline void led_on(void) { GPIOB_ResetBits(LED_PIN); }
static inline void led_toggle(void) { GPIOB_InverseBits(LED_PIN); }

#endif
