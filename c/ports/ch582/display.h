/* display.h - the CH582 port's display interface: the Pico port's names (the shared tests use them), one driver
 * (disp_sh1106.c). Only the mono names are meaningful here: the panel is the 128 x 64 SH1106; the colour and grey
 * names keep their Pico values so the shared sources compile. */
#ifndef PORT_DISPLAY_H
#define PORT_DISPLAY_H

#include <stdint.h>

#define PORT_LCD_W 240 /* colour panel size (unused here; the Pico values) */
#define PORT_LCD_H 240
#define OLED_W 128 /* mono panel */
#define OLED_H 64
#define GREY_W 128 /* grey panel (unused here) */
#define GREY_H 128
#define LINE_H 24 /* a colour band (unused here) */

void display_init(void);
/* Show @p rows rows of MONO_PAGE pages (OLED_W bytes per 8 rows) at panel row @p y. Refuses, sending nothing, when buf
 * is NULL, rows <= 0, y < 0, y + rows is past the panel height, or rows or y is not a multiple of 8. Sends nothing
 * either while display_state() is DISPLAY_I2C_FAILED. */
void display_show(const uint8_t *buf, int16_t y, int16_t rows);
extern const uint8_t display_565_bigendian; /* colour drivers only; not defined by this port */

/* What the last display_init / display_show did: nothing yet (or init done), a complete show, or an I2C write that
 * failed (timeout or NACK: no panel, wrong address, stuck bus). The failed state lasts until the next display_init. */
enum { DISPLAY_IDLE = 0, DISPLAY_SHOWN = 1, DISPLAY_I2C_FAILED = 2 };
int display_state(void);

#endif
