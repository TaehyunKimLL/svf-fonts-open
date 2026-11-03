#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
extern int bench_main(void);
void app_main(void)
{
	vTaskDelay(pdMS_TO_TICKS(4000));
	bench_main();
}
