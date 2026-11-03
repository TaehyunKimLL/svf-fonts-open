/* main.c - ESP32 (ESP-IDF): the profile chosen at build time (SVF_PROFILE: colour, grey or mono; SVF_DISPLAY for colour:
 * ili9341 over SPI or esp_rgb) drawn on its display. Pins, bus set-up and the panel's start-up (reset pulse, one chip
 * select frame a memory write) live in the display driver (disp_*.c); the drawing lives in profile_<p>.c. */
#include "display.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "profile.h"

/* Never returns. Its own symbol, so the compiler must not inline it. */
__attribute__((noinline)) void svf_port_idle(void)
{
	for (;;)
		vTaskDelay(pdMS_TO_TICKS(1000));
}

void app_main(void)
{
	display_init();
	profile_run();
	svf_port_idle();
}
