/* display.h - the ESP32 port's display interface: one driver per build (disp_ili9341.c, disp_ssd1327.c, disp_ssd1306.c, disp_esp_rgb.c).
 * The Pico port has a display.h with the same names (PORT_LCD_W 240). */
#ifndef PORT_DISPLAY_H
#define PORT_DISPLAY_H

#include <stdint.h>

#define PORT_LCD_W 320 /* colour panel size (240 on the Pico) */
#define PORT_LCD_H 240
#define OLED_W 128 /* mono panel */
#define OLED_H 64
#define GREY_W 128 /* grey panel */
#define GREY_H 128
#define LINE_H 24 /* a colour band: PORT_LCD_W x LINE_H pixels */

void display_init(void);
/* Show @p rows rows of the profile's frame format at panel row @p y: RGB565 bytes (PORT_LCD_W * 2 a row), GRAY8
 * (GREY_W a row) or MONO_PAGE pages (OLED_W bytes per 8 rows). Refuses, sending nothing, when buf is NULL, rows <= 0,
 * y < 0, y + rows is past the panel height, or rows is not a multiple of 8 (SSD1306, y too) / 4 (SSD1327). */
void display_show(const uint8_t *buf, int16_t y, int16_t rows);
extern const uint8_t display_565_bigendian; /* colour drivers only: 1 when the panel takes RGB565 high byte first */

#endif
