#ifndef SVF_PORTS_GREY_PACK_H
#define SVF_PORTS_GREY_PACK_H

#include <stddef.h>
#include <stdint.h>

/* c/ports/grey_pack.h: grey_pack_rows packs @p rows GRAY8 rows of @p w pixels (@p stride bytes apart) into w / 2
 * bytes a row at @p out, the left pixel in the high nibble: the order the SSD1327
 * shows with remap 0xA0 = 0x51 (bit 0, column address remap, set; bit 1, the nibble remap, clear; bit 4 the COM
 * remap, bit 6 the odd/even split), the same convention as Adafruit's SSD1327 code. Level = coverage >> 4: 2 bpp
 * coverage 0/85/170/255 lands on 0/5/10/15.
 * Returns the bytes written, rows * w / 2; 0 and writes nothing unless w is even and >= 2, stride >= w and
 * rows >= 0 (no byte outside gray8[0 .. (rows - 1) * stride + w) is read). */
static inline size_t grey_pack_rows(const uint8_t *gray8, size_t stride, int w, int rows, uint8_t *out)
{
    int r, x;
    if (!gray8 || !out || w < 2 || (w & 1) || stride < (size_t)w || rows < 0)
        return 0;
    for (r = 0; r < rows; ++r) {
        const uint8_t *row = gray8 + (size_t)r * stride; /* no pointer past one-past-the-end is formed */
        for (x = 0; x < w; x += 2)
            *out++ = (uint8_t)((row[x] & 0xF0) | (row[x + 1] >> 4));
    }
    return (size_t)rows * (size_t)(w / 2);
}

#endif
