/* Host check for c/ports/grey_pack.h. Prints port-check-grey-pack: OK. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "grey_pack.h"

static void fail(int line)
{
    fprintf(stderr, "port-check-grey-pack: FAIL at line %d\n", line);
    exit(1);
}
#define CHECK(c) do { if (!(c)) fail(__LINE__); } while (0)

int main(void)
{
    static const uint8_t want4[8] = {0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF};
    uint8_t src[64], out[32], *p;
    int i, r, c;

    /* 4 x 4 at stride 4 and stride 7 */
    for (i = 0; i < 16; ++i) src[i] = (uint8_t)(i * 0x10 + (i & 7));  /* low nibble ignored */
    memset(out, 0xA5, sizeof out);
    CHECK(grey_pack_rows(src, 4, 4, 4, out) == 8);
    CHECK(memcmp(out, want4, 8) == 0);
    CHECK(out[8] == 0xA5);
    memset(src, 0x77, sizeof src);
    for (r = 0; r < 4; ++r) for (c = 0; c < 4; ++c) src[r * 7 + c] = (uint8_t)((r * 4 + c) * 0x10);
    memset(out, 0xA5, sizeof out);
    CHECK(grey_pack_rows(src, 7, 4, 4, out) == 8);
    CHECK(memcmp(out, want4, 8) == 0);

    /* 6 x 3 at stride 6 and 9: values 0x00,0x10,...; row r col c = (r*6+c)*0x10 & 0xFF with wrap check by hand */
    {
        static const uint8_t in6[18] = {0x00,0x10,0x20,0x30,0x40,0x50, 0x60,0x70,0x80,0x90,0xA0,0xB0, 0xC0,0xD0,0xE0,0xF0,0xFF,0x0F};
        static const uint8_t want6[9] = {0x01,0x23,0x45, 0x67,0x89,0xAB, 0xCD,0xEF,0xF0};
        memset(out, 0xA5, sizeof out);
        CHECK(grey_pack_rows(in6, 6, 6, 3, out) == 9);
        CHECK(memcmp(out, want6, 9) == 0);
        CHECK(out[9] == 0xA5);
        memset(src, 0x55, sizeof src);
        for (r = 0; r < 3; ++r) memcpy(src + r * 9, in6 + r * 6, 6);
        memset(out, 0xA5, sizeof out);
        CHECK(grey_pack_rows(src, 9, 6, 3, out) == 9);
        CHECK(memcmp(out, want6, 9) == 0);
        CHECK(out[9] == 0xA5);

        /* exact-size input: (rows - 1) * stride + w = 24 bytes, ASan catches an over-read */
        p = malloc(24);
        CHECK(p);
        for (r = 0; r < 3; ++r) memcpy(p + r * 9, in6 + r * 6, 6);
        memset(out, 0xA5, sizeof out);
        CHECK(grey_pack_rows(p, 9, 6, 3, out) == 9);
        CHECK(memcmp(out, want6, 9) == 0);
        free(p);
    }

    /* w = 2 and rows = 1 */
    {
        static const uint8_t two[2] = {0xAB, 0xCD};
        memset(out, 0xA5, sizeof out);
        CHECK(grey_pack_rows(two, 2, 2, 1, out) == 1);
        CHECK(out[0] == 0xAC && out[1] == 0xA5);
        memset(out, 0xA5, sizeof out);
        CHECK(grey_pack_rows(src, 8, 4, 1, out) == 2);
        CHECK(out[2] == 0xA5);
    }

    /* refusals: return 0 and write nothing */
#define REFUSE(call) do { memset(out, 0xA5, sizeof out); CHECK((call) == 0); \
    for (i = 0; i < 32; ++i) CHECK(out[i] == 0xA5); } while (0)
    REFUSE(grey_pack_rows(src, 8, 5, 2, out));
    REFUSE(grey_pack_rows(src, 8, 0, 2, out));
    REFUSE(grey_pack_rows(src, 3, 4, 2, out));
    REFUSE(grey_pack_rows(src, 8, 4, 0, out));
    REFUSE(grey_pack_rows(src, 8, 4, -1, out));
    REFUSE(grey_pack_rows(NULL, 8, 4, 2, out));
    CHECK(grey_pack_rows(src, 8, 4, 2, NULL) == 0);

    puts("port-check-grey-pack: OK");
    return 0;
}
