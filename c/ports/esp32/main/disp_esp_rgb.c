/* disp_esp_rgb.c - QEMU's esp_rgb panel (Espressif QEMU 9.2.2, ESP32-C3 and ESP32-S3 machines): plain MMIO, no SDK call
 * and no SDK header, so it serves the IDF build on QEMU and the bare build alike. A 320 x 240 RGB565 window; the panel
 * takes native little-endian 16-bit words (display_565_bigendian = 0).
 *
 * Two things are kept apart so that this compiles under -Werror on the 32-bit chips and on a 64-bit host alike: where
 * the driver writes (ESP_RGB_REGS and ESP_RGB_VRAM, pointer-valued, overridable) and what it tells the device
 * (ESP_RGB_VRAM_ADDR, a uint32_t value, never a pointer cast). Every register store goes through ESP_RGB_STORE(i, v),
 * which defaults to a store through ESP_RGB_REGS; the host test overrides it to count the stores.
 *
 * The device copies at its next update (a refresh, or screendump under -display none), and RGB_UPDATE_STATUS stays 1
 * until then: this driver never reads a register, in particular never polls the status (esp_lcd_qemu_rgb does and
 * would hang under -display none). */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "display.h"

#ifndef ESP_RGB_REGS
#define ESP_RGB_REGS ((volatile uint32_t *)(uintptr_t)0x21000000u)
#endif
#ifndef ESP_RGB_VRAM
#define ESP_RGB_VRAM ((uint8_t *)(uintptr_t)0x20000000u)
#endif
#ifndef ESP_RGB_VRAM_ADDR
#define ESP_RGB_VRAM_ADDR 0x20000000u
#endif
#ifndef ESP_RGB_STORE
#define ESP_RGB_STORE(i, v) (ESP_RGB_REGS[i] = (v))
#endif

/* register indices (byte offset / 4); RGB_VERSION (0) is never touched */
#define RGB_WIN_SIZE 1
#define RGB_UPDATE_FROM 2
#define RGB_UPDATE_TO 3
#define RGB_UPDATE_CONTENT 4
#define RGB_UPDATE_STATUS 5
#define RGB_BPP_VALUE 6

#define WIN_SIZE_VALUE (((uint32_t)PORT_LCD_W << 16) | (uint32_t)PORT_LCD_H)

const char svf_port_driver_esp_rgb[] = "esp_rgb";
const uint8_t display_565_bigendian = 0;

void display_init(void)
{
	volatile const char *marker = svf_port_driver_esp_rgb;
	char keep = *marker; /* one volatile read: keeps the marker through -fdata-sections --gc-sections (nm check) */

	(void)keep;
	ESP_RGB_STORE(RGB_BPP_VALUE, 16u); /* r5g6b5 */
	ESP_RGB_STORE(RGB_WIN_SIZE, WIN_SIZE_VALUE);
}

void display_show(const uint8_t *buf, int16_t y, int16_t rows)
{
	if (!buf || rows <= 0 || y < 0 || (int)y + rows > PORT_LCD_H)
		return;
	memcpy(ESP_RGB_VRAM + (size_t)y * PORT_LCD_W * 2, buf, (size_t)rows * PORT_LCD_W * 2);
	/* the whole window, so whenever the update runs the surface shows all of VRAM, not the last band */
	ESP_RGB_STORE(RGB_UPDATE_FROM, 0u);
	ESP_RGB_STORE(RGB_UPDATE_TO, WIN_SIZE_VALUE);
	ESP_RGB_STORE(RGB_UPDATE_CONTENT, (uint32_t)ESP_RGB_VRAM_ADDR);
	ESP_RGB_STORE(RGB_UPDATE_STATUS, 1u);
}
