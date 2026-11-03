/* test_esp_rst.c - ESP_RST_LOW_TICKS (esp32/main/esp_rst.h) must make the RST low pulse at least 10 ms at the tick rate
 * the stub is built for (-DSVF_STUB_TICK_MS=<ms per tick>). vTaskDelay(n) returns after between n - 1 and n ticks, so the
 * shortest pulse is (n - 1) ticks. Build: once per tick length (host-checks.sh: every length 1..20 ms; 10 = 100 Hz, 1 = 1000 Hz). */
#include <stdio.h>
#include "esp_rst.h"

int main(void)
{
	unsigned shortest_ms = (unsigned)(ESP_RST_LOW_TICKS - 1) * SVF_STUB_TICK_MS;

	if (shortest_ms < 10) {
		fprintf(stderr, "port-check-esp-rst: FAIL %u ms per tick: %u ticks, shortest pulse %u ms < 10\n",
		        (unsigned)SVF_STUB_TICK_MS, (unsigned)ESP_RST_LOW_TICKS, shortest_ms);
		return 1;
	}
	return 0;
}
