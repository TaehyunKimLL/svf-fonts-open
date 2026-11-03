/* Host check for the display drivers: each build links ONE driver (-DDRV_<X>) against the recording stubs
 * (-DSVF_STUB_RECORD) and compares the event log with the byte tables of the spec. Prints
 * port-check-driver-<TEST_ID>: OK (TEST_ID, a string, comes from the command line, e.g. "pico-st7789").
 * Drivers: DRV_ST7789 DRV_SSD1327 DRV_SSD1306 (Pico), DRV_ILI9341 DRV_ESP_SSD1327 DRV_ESP_SSD1306 DRV_ESP_RGB (ESP32;
 * add -DSVF_ESP32S3=1 for the ESP32-S3 pins), DRV_SH1106 (CH582; the test defines ch582_i2c_write itself, so i2c.c is
 * not linked; -DSH1106_COL_OFFSET=<n> -DSH1106_REMAP=<0|1> -DOLED_SSD1306=<0|1> select the module variant). DRV_ESP_RGB has no recording stub: the test includes disp_esp_rgb.c as
 * one translation unit, after defining the register and VRAM arrays and a counting ESP_RGB_STORE. */
#ifdef DRV_ESP_RGB
#define _POSIX_C_SOURCE 200809L
#include <unistd.h>
#endif
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "display.h"
#include "grey_pack.h"
#include "svf_stub_record.h"

#ifndef TEST_ID
#error "pass -DTEST_ID=\"<port>-<driver>\""
#endif

static void fail(int line)
{
    fprintf(stderr, "port-check-driver-%s: FAIL at line %d\n", TEST_ID, line);
    exit(1);
}
#define CHECK(c) do { if (!(c)) fail(__LINE__); } while (0)

#if defined(DRV_ILI9341) || defined(DRV_ESP_SSD1327) || defined(DRV_ESP_SSD1306)
#define DRV_ESP_SPI 1
#include "driver/spi_master.h"
#include "freertos/FreeRTOS.h" /* SVF_STUB_TICK_MS */
#endif
#if defined(DRV_ST7789) || defined(DRV_ILI9341) || defined(DRV_ESP_SSD1327) || defined(DRV_ESP_SSD1306)
#define DRV_SPI_ANY 1
#endif
enum { K_SPI = 1, K_GPIO, K_I2C, K_SLEEP, K_CFG, K_BUS };
typedef struct { int kind, a, b, c, d, e; size_t off, n; } ev;

static ev evs[8192];
static int nev;
static uint8_t arena[1 << 18];
static size_t arena_n;
static int any_nostop, bad_i2c;
int svf_stub_dc_pin;

/* Capacity: the largest legal show is a full 320 x 240 RGB565 frame (153,600 data bytes) plus a few command bytes; the
 * longest event list is a 128-row SSD1327 show (6 commands + 32 chunks) or an init. A transfer set that does not fit
 * fails here at compile time, not as a silent truncation. */
typedef char arena_holds_a_full_frame[sizeof arena >= (size_t)PORT_LCD_W * 2 * PORT_LCD_H + 4096 ? 1 : -1];
typedef char events_hold_the_longest_show[sizeof evs / sizeof evs[0] >= 256 ? 1 : -1];

static void add(int kind, int a, int b, const uint8_t *p, size_t n)
{
    CHECK(nev < (int)(sizeof evs / sizeof evs[0]));
    CHECK(arena_n + n <= sizeof arena);
    evs[nev].kind = kind; evs[nev].a = a; evs[nev].b = b; evs[nev].off = arena_n; evs[nev].n = n;
    if (n) memcpy(arena + arena_n, p, n);
    arena_n += n;
    ++nev;
}
void svf_rec_bytes(int dc, const uint8_t *p, size_t n) { add(K_SPI, dc, 0, p, n); }
void svf_rec_gpio(int pin, int level) { add(K_GPIO, pin, level, NULL, 0); }
void svf_rec_sleep(uint32_t ms) { add(K_SLEEP, (int)ms, 0, NULL, 0); }
void svf_rec_cfg(int what, int a, int b, int c, int d)
{
    add(K_CFG, what, a, NULL, 0);
    evs[nev - 1].c = b; evs[nev - 1].d = c; evs[nev - 1].e = d;
}
#if defined(DRV_ESP_SPI)
/* ESP32 SPI: c, d, e of a K_SPI event = CS level before, CS level after, bus held (spi_master.h's model) */
void svf_rec_spi_cs(int cs_before, int cs_after, int bus_held)
{
    CHECK(nev > 0 && evs[nev - 1].kind == K_SPI);
    evs[nev - 1].c = cs_before; evs[nev - 1].d = cs_after; evs[nev - 1].e = bus_held;
}
void svf_rec_bus(int acquired) { add(K_BUS, acquired, 0, NULL, 0); }
#endif
void svf_rec_i2c(uint8_t addr, const uint8_t *p, size_t n, int nostop)
{
    if (nostop) any_nostop = 1;
    if (addr != 0x3C) bad_i2c = 1;
    add(K_I2C, addr, nostop, p, n);
}

/* The pins of the driver under test (the ESP32 ones by chip). */
#if defined(DRV_ST7789)
#define PIN_CS 17
#define PIN_DC 16
#define PIN_RST 20
#elif defined(DRV_ESP_SPI)
/* ESP32: chip select belongs to the SPI peripheral, so no gpio event may name it; the pins by chip */
#define PIN_CS (-1)
#if SVF_ESP32S3
#define E_MOSI 11
#define E_SCLK 12
#define E_CS 10
#define PIN_DC 4
#define PIN_RST 5
#else
#define E_MOSI 7
#define E_SCLK 6
#define E_CS 10
#define PIN_DC 2
#define PIN_RST 3
#endif
#else
#define PIN_CS (-1)
#define PIN_DC (-1)
#define PIN_RST (-1)
#endif

#if defined(DRV_ESP_RGB)
/* The register block and VRAM of the driver, in host memory; the driver sees them through the overridden pointer
 * macros and tells the device ESP_RGB_VRAM_ADDR (default 0x20000000), which is not their address. */
static volatile uint32_t test_regs[7];
/* The driver's writes all go through ESP_RGB_STORE (which writes test_regs); ESP_RGB_REGS itself is a trap: any other
 * use of it, in particular a register read, counts here, and the checks below require zero. */
static volatile uint32_t trap_regs[7];
static int reg_traps;
static volatile uint32_t *rgb_trap(void) { ++reg_traps; return trap_regs; }
static uint8_t test_vram[153600];
static int stores, store_idx[16];
static uint32_t store_val[16];
static const uint8_t *vram_expect; /* when set, the first register store of a show finds the band already in VRAM */
static size_t vram_expect_off, vram_expect_n;
static void rgb_store(int i, uint32_t v)
{
    CHECK(i >= 1 && i <= 6);                   /* never RGB_VERSION, never past the block */
    CHECK(stores < 16);
    if (stores == 0 && vram_expect) CHECK(memcmp(test_vram + vram_expect_off, vram_expect, vram_expect_n) == 0);
    store_idx[stores] = i;
    store_val[stores] = v;
    ++stores;
    test_regs[i] = v;
}
#define ESP_RGB_REGS rgb_trap()
#define ESP_RGB_VRAM test_vram
#define ESP_RGB_STORE(i, v) rgb_store((i), (v))
#include "disp_esp_rgb.c"
static void log_clear(void)
{
    stores = 0;
    reg_traps = 0;
    vram_expect = NULL;
    memset(test_vram, 0, sizeof test_vram);
}
#else
/* The cursor: gpio events on pins other than the expected one are consumed here (CS and DC levels are tracked). */
static int cur, cs_level = 1, dc_level, cs_changes;
static void log_clear(void) { nev = 0; arena_n = 0; cur = 0; cs_changes = 0; }

static const ev *nx(void)
{
    while (cur < nev) {
        const ev *e = &evs[cur++];
        if (e->kind == K_BUS) continue;       /* bus acquire / release: ordered by bus_around, not by the cursor */
        if (e->kind == K_GPIO && e->a != PIN_RST) {
            CHECK(e->a == PIN_CS || e->a == PIN_DC); /* only the control lines may be driven, and only CS and DC here */
            if (e->a == PIN_CS) { cs_level = e->b; ++cs_changes; }
            if (e->a == PIN_DC) dc_level = e->b;
            continue;
        }
        return e;
    }
    fail(__LINE__);
    return NULL;
}
#if defined(DRV_ST7789)
static int nx_gpio(void)
{
    const ev *e = &evs[cur++];
    CHECK(e->kind == K_GPIO && (e->a == PIN_CS || e->a == PIN_DC));
    if (e->a == PIN_CS) { cs_level = e->b; ++cs_changes; }
    if (e->a == PIN_DC) dc_level = e->b;
    return 1;
}
#endif
static void ex_end(void)
{
    while (cur < nev) {
        const ev *e = &evs[cur++];
        if (e->kind == K_BUS) continue;
        CHECK(e->kind == K_GPIO && (e->a == PIN_CS || e->a == PIN_DC));
        if (e->a == PIN_CS) { cs_level = e->b; ++cs_changes; }
        if (e->a == PIN_DC) dc_level = e->b;
    }
}
#define EV_BYTES(e) (arena + (e)->off)
#if defined(DRV_SSD1327) || defined(DRV_SSD1306) || defined(DRV_SH1106)
static void ex_i2c(const uint8_t *p, size_t n)
{
    const ev *e = nx();
    CHECK(e->kind == K_I2C && e->a == 0x3C && e->b == 0 && e->n == n);
    CHECK(memcmp(EV_BYTES(e), p, n) == 0);
}
static void ex_i2c_cmd(uint8_t c)
{
    uint8_t w[2];
    w[0] = 0x00; w[1] = c;
    ex_i2c(w, 2);
}
#endif
#if defined(DRV_SPI_ANY)
/* before / after: the chip-select level the ESP32 stub reports around the transmit (the Pico builds ignore them) */
static void ex_spi_cs(int dc, const uint8_t *p, size_t n, int before, int after)
{
    const ev *e = nx();
    CHECK(e->kind == K_SPI && e->a == dc && e->n == n);
#if defined(DRV_ESP_SPI)
    CHECK(e->c == before && e->d == after);
    CHECK(!after || e->e);              /* CS kept active only with the bus acquired */
#else
    (void)before; (void)after;
#endif
    if (PIN_CS >= 0) CHECK(cs_level == 0); /* every SPI write inside a chip-select transaction (GPIO CS only) */
    CHECK(dc_level == dc);         /* the stub reported the level the driver set on the DC pin */
    CHECK(memcmp(EV_BYTES(e), p, n) == 0);
}
static void ex_spi(int dc, const uint8_t *p, size_t n) { ex_spi_cs(dc, p, n, 0, 0); } /* its own CS frame */
static void ex_sleep(int ms)
{
    const ev *e = nx();
    CHECK(e->kind == K_SLEEP && e->a == ms);
    CHECK(cs_level == 1);          /* never asleep inside a chip-select transaction */
}
#if defined(DRV_ESP_SPI)
/* the RST low pulse: at least ms whatever the tick phase, so the recorded ticks minus one tick still cover ms (a
 * 10 ms vTaskDelay at a 100 Hz tick can end at once) */
static void ex_sleep_at_least(int ms)
{
    const ev *e = nx();
    CHECK(e->kind == K_SLEEP && e->a - SVF_STUB_TICK_MS >= ms);
    CHECK(cs_level == 1);
}
#endif
static void ex_rst(int level)
{
    const ev *e = nx();
    CHECK(e->kind == K_GPIO && e->a == PIN_RST && e->b == level);
}
#endif
static void ex_cfg(int what, int a, int b, int c, int d)
{
    const ev *e = nx();
    CHECK(e->kind == K_CFG && e->a == what && e->b == a && e->c == b && e->d == c && e->e == d);
}
#endif /* !DRV_ESP_RGB */
static uint8_t pattern[1 << 18]; /* 262,144: a full 320 x 240 RGB565 frame (153,600) fits */
static void fill_pattern(size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) pattern[i] = (uint8_t)(i + (i >> 8) * 5 + 1);
}

/* ---- refusals, shared: the cases of the brief, each sends zero events ---- */
static void refused(const uint8_t *buf, int y, int rows)
{
    log_clear();
    display_show(buf, (int16_t)y, (int16_t)rows);
#if defined(DRV_ESP_RGB)
    CHECK(stores == 0 && reg_traps == 0);   /* no register access and no byte in VRAM */
    {
        size_t i;
        for (i = 0; i < sizeof test_vram; ++i) CHECK(test_vram[i] == 0);
    }
#else
    CHECK(nev == 0);
#endif
}

#if defined(DRV_ST7789) || defined(DRV_ILI9341)
static void ex_cmd1(uint8_t c) { ex_spi(0, &c, 1); }
static void ex_cmd_arg(uint8_t c, const uint8_t *a, size_t n) { ex_cmd1(c); ex_spi(1, a, n); }
#endif
#if defined(DRV_ST7789)
/* an init command: its own chip-select transaction, CS low once and high once around exactly these writes */
static void ex_txn(uint8_t c, const uint8_t *a, size_t n)
{
    cs_changes = 0;
    if (n) ex_cmd_arg(c, a, n); else ex_cmd1(c);
    while (cs_level == 0 && cur < nev && evs[cur].kind == K_GPIO && evs[cur].a != PIN_RST) (void)nx_gpio();
    CHECK(cs_level == 1 && cs_changes == 2);
}

static void init_sequence(void)
{
    static const uint8_t colmod[] = {0x55}, madctl[] = {0x00};
    int i;
    log_clear();
    display_init();
    /* reset pulse, then SWRESET + 120 ms, SLPOUT + 120 ms, COLMOD, MADCTL, INVON, DISPON; every command in its own
     * chip-select transaction (CS low around it, high after) */
    ex_cfg(SVF_CFG_SPI_INIT, 32 * 1000 * 1000, 0, 0, 0);
    ex_cfg(SVF_CFG_SPI_FORMAT, 8, 0, 0, 1);                    /* 8 bits, CPOL 0, CPHA 0, MSB first */
    ex_cfg(SVF_CFG_GPIO_FUNC, 19, 1, 0, 0);                    /* MOSI GP19, GPIO_FUNC_SPI */
    ex_cfg(SVF_CFG_GPIO_FUNC, 18, 1, 0, 0);                    /* SCK GP18 */
    ex_cfg(SVF_CFG_GPIO_INIT, PIN_CS, 0, 0, 0); ex_cfg(SVF_CFG_GPIO_DIR, PIN_CS, 1, 0, 0);
    ex_cfg(SVF_CFG_GPIO_INIT, PIN_DC, 0, 0, 0); ex_cfg(SVF_CFG_GPIO_DIR, PIN_DC, 1, 0, 0);
    ex_cfg(SVF_CFG_GPIO_INIT, PIN_RST, 0, 0, 0); ex_cfg(SVF_CFG_GPIO_DIR, PIN_RST, 1, 0, 0);
    ex_rst(0); ex_sleep(1); ex_rst(1); ex_sleep(1);
    ex_txn(0x01, NULL, 0); ex_sleep(120);
    ex_txn(0x11, NULL, 0); ex_sleep(120);
    ex_txn(0x3A, colmod, 1);
    ex_txn(0x36, madctl, 1);
    ex_txn(0x21, NULL, 0);
    ex_txn(0x29, NULL, 0);
    ex_end();
    CHECK(cs_level == 1);
    /* the RST pin saw exactly 0 then 1 */
    {
        int n = 0, want = 0;
        for (i = 0; i < nev; ++i)
            if (evs[i].kind == K_GPIO && evs[i].a == PIN_RST) { CHECK(evs[i].b == want); want = 1; ++n; }
        CHECK(n == 2);
    }
    CHECK(display_565_bigendian == 1);
}

static void show_window(int y, int rows)
{
    uint8_t caset[4] = {0x00, 0x00, 0x00, 0xEF}, raset[4];
    int e = y + rows - 1;
    raset[0] = (uint8_t)(y >> 8); raset[1] = (uint8_t)y; raset[2] = (uint8_t)(e >> 8); raset[3] = (uint8_t)e;
    fill_pattern((size_t)rows * 480);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmd_arg(0x2A, caset, 4);
    ex_cmd_arg(0x2B, raset, 4);
    ex_cmd1(0x2C);
    {
        const ev *d = nx();
        CHECK(d->kind == K_SPI && d->a == 1 && d->n == (size_t)rows * 480);
        CHECK(cs_level == 0 && dc_level == 1);
        CHECK(memcmp(EV_BYTES(d), pattern, d->n) == 0);
    }
    ex_end();
    CHECK(cs_level == 1);
    CHECK(cs_changes == 2);       /* one transaction: CS low once, high once */
}
static void shows(void)
{
    show_window(0, 24);
    show_window(16, 24);
    show_window(128, 24);
    show_window(216, 24);
    show_window(0, 240);   /* the largest legal transfer: a full frame in one write */
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 24);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, -1, 24);
    refused(pattern, 232, 24);
    refused(pattern, 0, 241);
}
#endif

#if defined(DRV_SSD1327) || defined(DRV_SSD1306)
static void ex_cmds(const uint8_t *c, size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) ex_i2c_cmd(c[i]);
}
#endif

#if defined(DRV_SSD1327)
static void init_sequence(void)
{
    static const uint8_t init[] = {0xAE, 0xA0, 0x51, 0xA8, 0x7F, 0xA1, 0x00, 0xA2, 0x00,
                                   0x81, 0x7F, 0xB1, 0xF1, 0xBC, 0x08, 0xA4, 0xAF};
    log_clear();
    display_init();
    ex_cfg(SVF_CFG_I2C_INIT, 400 * 1000, 0, 0, 0);
    ex_cfg(SVF_CFG_GPIO_FUNC, 4, 3, 0, 0);                     /* SDA GP4, GPIO_FUNC_I2C */
    ex_cfg(SVF_CFG_GPIO_FUNC, 5, 3, 0, 0);                     /* SCL GP5 */
    ex_cfg(SVF_CFG_GPIO_PULL_UP, 4, 0, 0, 0);
    ex_cfg(SVF_CFG_GPIO_PULL_UP, 5, 0, 0, 0);
    ex_cmds(init, sizeof init);
    ex_end();
}
static void show_window(int y, int rows)
{
    uint8_t win[6], chunk[257];
    int c;
    win[0] = 0x15; win[1] = 0x00; win[2] = 0x3F; win[3] = 0x75; win[4] = (uint8_t)y; win[5] = (uint8_t)(y + rows - 1);
    fill_pattern((size_t)rows * GREY_W);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmds(win, sizeof win);
    chunk[0] = 0x40;
    for (c = 0; c < rows / 4; ++c) {
        CHECK(grey_pack_rows(pattern + (size_t)c * 4 * GREY_W, GREY_W, GREY_W, 4, chunk + 1) == 256);
        ex_i2c(chunk, sizeof chunk);
    }
    ex_end();
    CHECK(nev == 6 + rows / 4);
}
static void shows(void)
{
    show_window(0, 128);   /* 32 chunks */
    show_window(64, 4);    /* 1 chunk */
    show_window(0, 4);
    show_window(124, 4);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 4);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, 0, 6);
    refused(pattern, 128, 4);
    refused(pattern, 124, 8);
    refused(pattern, -4, 4);
}
#endif

#if defined(DRV_SSD1306)
static void init_sequence(void)
{
    static const uint8_t init[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8,
                                   0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
    log_clear();
    display_init();
    ex_cfg(SVF_CFG_I2C_INIT, 400 * 1000, 0, 0, 0);
    ex_cfg(SVF_CFG_GPIO_FUNC, 4, 3, 0, 0);                     /* SDA GP4, GPIO_FUNC_I2C */
    ex_cfg(SVF_CFG_GPIO_FUNC, 5, 3, 0, 0);                     /* SCL GP5 */
    ex_cfg(SVF_CFG_GPIO_PULL_UP, 4, 0, 0, 0);
    ex_cfg(SVF_CFG_GPIO_PULL_UP, 5, 0, 0, 0);
    ex_cmds(init, sizeof init);
    ex_end();
}
static void show_window(int y, int rows)
{
    uint8_t win[6], page[129];
    int c;
    win[0] = 0x21; win[1] = 0x00; win[2] = 0x7F; win[3] = 0x22; win[4] = (uint8_t)(y / 8);
    win[5] = (uint8_t)((y + rows) / 8 - 1);
    fill_pattern((size_t)rows * OLED_W / 8);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmds(win, sizeof win);
    page[0] = 0x40;
    for (c = 0; c < rows / 8; ++c) {
        memcpy(page + 1, pattern + (size_t)c * OLED_W, OLED_W);
        ex_i2c(page, sizeof page);
    }
    ex_end();
    CHECK(nev == 6 + rows / 8);
}
static void shows(void)
{
    show_window(0, 64);   /* 8 page writes */
    show_window(8, 16);   /* 2 page writes */
    show_window(56, 8);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 8);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, 0, 12);
    refused(pattern, 4, 8);      /* y not a page boundary */
    refused(pattern, 64, 8);
    refused(pattern, 56, 16);
    refused(pattern, -8, 8);
}
#endif

#if defined(DRV_ESP_SPI)
static int setup_host;
static void ex_dev_host(void)
{
    ex_cfg(SVF_CFG_SPI_DEV_HOST, setup_host, 0, 0, 0);   /* the device sits on the bus that was initialised */
}
/* what the three ESP drivers set up: bus (MOSI, SCLK, max transfer, no MISO), device (clock, mode 0, CS, queue 1), DC and
 * RST as outputs; then the reset pulse is the caller's */
static void ex_setup(int max_transfer, int hz)
{
    setup_host = SPI2_HOST;
    ex_cfg(SVF_CFG_SPI_HOST, SPI2_HOST, SPI_DMA_CH_AUTO, 0, 0);
    ex_cfg(SVF_CFG_SPI_BUS, E_MOSI, E_SCLK, max_transfer, -1);
    ex_dev_host();
    ex_cfg(SVF_CFG_SPI_DEV, hz, 0, E_CS, 1);
    ex_cfg(SVF_CFG_GPIO_OUT, (1 << PIN_DC) | (1 << PIN_RST), 0, GPIO_MODE_OUTPUT, 0);
}
static void rst_pulse_seen(void)
{
    int i, n = 0, want = 0;
    for (i = 0; i < nev; ++i)
        if (evs[i].kind == K_GPIO && evs[i].a == PIN_RST) { CHECK(evs[i].b == want); want = 1; ++n; }
    CHECK(n == 2);                 /* the RST pin saw exactly 0 then 1 */
}
/* bus acquire / release around SPI events first_spi .. last_spi (ordinals among the SPI events): exactly one acquire
 * and one release, nothing outside held, everything inside held. first_spi < 0: no bus use at all */
static void bus_around(int first_spi, int last_spi)
{
    int i, ord = 0, acq = -1, rel = -1, nbus = 0;
    for (i = 0; i < nev; ++i) {
        if (evs[i].kind == K_BUS) {
            ++nbus;
            if (evs[i].a == 1) { CHECK(acq < 0); acq = ord; } else { CHECK(acq >= 0 && rel < 0); rel = ord; }
        } else if (evs[i].kind == K_SPI) {
            CHECK((evs[i].e != 0) == (first_spi >= 0 && ord >= first_spi && ord <= last_spi));
            ++ord;
        }
    }
    if (first_spi < 0) { CHECK(nbus == 0); return; }
    CHECK(nbus == 2 && acq == first_spi && rel == last_spi + 1);   /* released after the last, not before */
}
static int spi_events(void)
{
    int i, n = 0;
    for (i = 0; i < nev; ++i) n += evs[i].kind == K_SPI;
    return n;
}
#if defined(DRV_ESP_SSD1327) || defined(DRV_ESP_SSD1306)
/* every byte of an OLED command list: its own transmit, DC low */
static void ex_cmds_spi(const uint8_t *c, size_t n)
{
    size_t i;
    for (i = 0; i < n; ++i) ex_spi(0, &c[i], 1);
}
#endif
#endif

#if defined(DRV_ILI9341)
static void init_sequence(void)
{
    static const uint8_t colmod[] = {0x55}, madctl[] = {0x28};
    log_clear();
    display_init();
    ex_setup(PORT_LCD_W * LINE_H * 2, 40 * 1000 * 1000);
    ex_rst(0); ex_sleep_at_least(10); ex_rst(1); ex_sleep(120);
    ex_cmd1(0x11); ex_sleep(120);
    ex_cmd_arg(0x3A, colmod, 1);
    ex_cmd_arg(0x36, madctl, 1);
    ex_cmd1(0x29);
    ex_end();
    rst_pulse_seen();
    bus_around(-1, 0);
    CHECK(display_565_bigendian == 1);
}
static void show_window(int y, int rows)
{
    uint8_t caset[4] = {0x00, 0x00, 0x01, 0x3F}, raset[4];
    int e = y + rows - 1, r, n;
    raset[0] = (uint8_t)(y >> 8); raset[1] = (uint8_t)y; raset[2] = (uint8_t)(e >> 8); raset[3] = (uint8_t)e;
    fill_pattern((size_t)rows * PORT_LCD_W * 2);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmd_arg(0x2A, caset, 4);
    ex_cmd_arg(0x2B, raset, 4);
    ex_spi_cs(0, (const uint8_t[]){0x2C}, 1, 0, 1);   /* RAMWR: CS stays asserted for the pixels that follow */
    /* the pixels in transmits of at most LINE_H rows (max_transfer_sz), in order, each with DC high, inside the one
     * RAMWR CS frame: CS held through every chunk, released only after the last */
    for (r = 0; r < rows; r += n) {
        n = rows - r < LINE_H ? rows - r : LINE_H;
        ex_spi_cs(1, pattern + (size_t)r * PORT_LCD_W * 2, (size_t)n * PORT_LCD_W * 2, 1, r + n < rows);
    }
    ex_end();
    CHECK(spi_events() == 3 + 2 + (rows + LINE_H - 1) / LINE_H);
    bus_around(0, spi_events() - 1);   /* the bus held from the CASET command to the last pixel chunk */
}
static void shows(void)
{
    show_window(0, 24);
    show_window(16, 24);
    show_window(128, 24);
    show_window(216, 24);
    show_window(0, 240);   /* a full frame: ten band-sized transmits */
    show_window(100, 30);  /* more than a band, not a multiple of it */
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 24);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, -1, 24);
    refused(pattern, 232, 24);
    refused(pattern, 0, 241);
}
#endif

#if defined(DRV_ESP_SSD1327)
static void init_sequence(void)
{
    static const uint8_t init[] = {0xAE, 0xA0, 0x51, 0xA8, 0x7F, 0xA1, 0x00, 0xA2, 0x00,
                                   0x81, 0x7F, 0xB1, 0xF1, 0xBC, 0x08, 0xA4, 0xAF};
    log_clear();
    display_init();
    ex_setup(256, 10 * 1000 * 1000);
    ex_rst(0); ex_sleep_at_least(10); ex_rst(1); ex_sleep(10);
    ex_cmds_spi(init, sizeof init);
    ex_end();
    rst_pulse_seen();
    CHECK(spi_events() == (int)sizeof init);
    bus_around(-1, 0);
}
static void show_window(int y, int rows)
{
    uint8_t win[6], chunk[256];
    int c;
    win[0] = 0x15; win[1] = 0x00; win[2] = 0x3F; win[3] = 0x75; win[4] = (uint8_t)y; win[5] = (uint8_t)(y + rows - 1);
    fill_pattern((size_t)rows * GREY_W);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmds_spi(win, sizeof win);
    for (c = 0; c < rows / 4; ++c) {   /* 256 packed bytes a transmit, DC high, no prefix */
        CHECK(grey_pack_rows(pattern + (size_t)c * 4 * GREY_W, GREY_W, GREY_W, 4, chunk) == 256);
        ex_spi_cs(1, chunk, sizeof chunk, c > 0, c < rows / 4 - 1);   /* the split data write is one CS frame */
    }
    ex_end();
    CHECK(spi_events() == 6 + rows / 4);
    bus_around(6, 6 + rows / 4 - 1);
}
static void shows(void)
{
    show_window(0, 128);   /* 32 chunks */
    show_window(64, 4);    /* 1 chunk */
    show_window(0, 4);
    show_window(124, 4);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 4);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, 0, 6);
    refused(pattern, 128, 4);
    refused(pattern, 124, 8);
    refused(pattern, -4, 4);
}
#endif

#if defined(DRV_ESP_SSD1306)
static void init_sequence(void)
{
    static const uint8_t init[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8,
                                   0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
    log_clear();
    display_init();
    ex_setup(1024, 10 * 1000 * 1000);
    ex_rst(0); ex_sleep_at_least(10); ex_rst(1); ex_sleep(10);
    ex_cmds_spi(init, sizeof init);
    ex_end();
    rst_pulse_seen();
    CHECK(spi_events() == (int)sizeof init);
    bus_around(-1, 0);
}
static void show_window(int y, int rows)
{
    uint8_t win[6];
    win[0] = 0x21; win[1] = 0x00; win[2] = 0x7F; win[3] = 0x22; win[4] = (uint8_t)(y / 8);
    win[5] = (uint8_t)((y + rows) / 8 - 1);
    fill_pattern((size_t)rows * OLED_W / 8);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    ex_cmds_spi(win, sizeof win);
    ex_spi(1, pattern, (size_t)rows * 16);   /* one transmit of all the pages, DC high, no prefix */
    ex_end();
    CHECK(spi_events() == 7);
    bus_around(-1, 0);                       /* one data transmit: no split, no bus hold */
}
static void shows(void)
{
    show_window(0, 64);   /* 1024 bytes */
    show_window(8, 16);
    show_window(56, 8);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 8);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, 0, 12);
    refused(pattern, 4, 8);      /* y not a page boundary */
    refused(pattern, 64, 8);
    refused(pattern, 56, 16);
    refused(pattern, -8, 8);
}
#endif

#if defined(DRV_SH1106)
#include "i2c.h"
#ifndef OLED_SSD1306
#define OLED_SSD1306 0
#endif
#ifndef SH1106_COL_OFFSET
#define SH1106_COL_OFFSET (OLED_SSD1306 ? 0 : 2)
#endif
#ifndef SH1106_REMAP
#define SH1106_REMAP 1
#endif
/* ch582_i2c_write is the test's: it records the write and fails the write numbered i2c_fail_at (-1: never) */
static int i2c_calls, i2c_fail_at = -1;
int ch582_i2c_write(uint8_t addr, const uint8_t *p, size_t n)
{
    svf_rec_i2c(addr, p, n, 0);
    return i2c_calls++ == i2c_fail_at ? -1 : 0;
}
static void ex_cmd(uint8_t c) { ex_i2c_cmd(c); }
static void ex_cmd_arg(uint8_t c, uint8_t a)
{
    uint8_t w[3];
    w[0] = 0x00; w[1] = c; w[2] = a;
    ex_i2c(w, 3);
}
static void ex_delay(int ms)
{
    const ev *e = nx();
    CHECK(e->kind == K_SLEEP && e->a == ms);
}
/* the RAM clear: all 8 pages from column 0, each 0x40 and 132 zero bytes in one write */
static void ex_clear(void)
{
    uint8_t zeros[1 + 132];
    int c;
    memset(zeros, 0, sizeof zeros);
    zeros[0] = 0x40;
    for (c = 0; c < 8; ++c) {
        ex_cmd((uint8_t)(0xB0 + c));
        ex_cmd(0x00);
        ex_cmd(0x10);
        ex_i2c(zeros, sizeof zeros);
    }
}
static void init_sequence(void)
{
    log_clear();
    display_init();
    ex_cfg(SVF_CFG_PIN_REMAP, 1, 0x800, 0, 0);                 /* GPIOPinRemap(ENABLE, RB_PIN_I2C) */
    ex_cfg(SVF_CFG_GPIOB_MODE, 0x300000, 1, 0, 0);             /* PB20 | PB21, GPIO_ModeIN_PU */
    ex_cfg(SVF_CFG_CH58X_I2C, 400 * 1000, 0x0000, 0x0400, 0x4000);
    ex_delay(20);                                              /* the panel's reset recovery, before the first command */
    ex_cmd(0xAE);
    ex_cmd_arg(0xD5, 0x80);
    ex_cmd_arg(0xA8, 0x3F);
    ex_cmd_arg(0xD3, 0x00);
    ex_cmd(0x40);
#if OLED_SSD1306
    ex_cmd_arg(0x8D, 0x14);                                    /* the SSD1306's charge pump, not the SH1106's DC-DC */
    ex_cmd_arg(0x20, 0x02);                                    /* page addressing mode */
#else
    ex_cmd_arg(0xAD, 0x8B);
    ex_cmd(0x32);
#endif
#if SH1106_REMAP
    ex_cmd(0xA1);
    ex_cmd(0xC8);
#else
    ex_cmd(0xA0);
    ex_cmd(0xC0);
#endif
    ex_cmd_arg(0xDA, 0x12);
#if OLED_SSD1306
    ex_cmd_arg(0x81, 0xCF);
    ex_cmd_arg(0xD9, 0xF1);
    ex_cmd_arg(0xDB, 0x40);
#else
    ex_cmd_arg(0x81, 0x80);
    ex_cmd_arg(0xD9, 0x22);
    ex_cmd_arg(0xDB, 0x35);
#endif
    ex_cmd(0xA4);
    ex_cmd(0xA6);
    ex_clear();                                                /* the RAM is cleared before the display goes on */
    ex_cmd(0xAF);
    ex_delay(100);
    ex_end();
    CHECK(nev == 53);
    CHECK(display_state() == DISPLAY_IDLE);
}
static void show_window(int y, int rows)
{
    uint8_t page[1 + OLED_W];
    int c;
    fill_pattern((size_t)rows * OLED_W / 8);
    log_clear();
    display_show(pattern, (int16_t)y, (int16_t)rows);
    page[0] = 0x40;
    for (c = 0; c < rows / 8; ++c) {
        ex_cmd((uint8_t)(0xB0 + y / 8 + c));
        ex_cmd((uint8_t)(SH1106_COL_OFFSET & 0x0F));
        ex_cmd((uint8_t)(0x10 | (SH1106_COL_OFFSET >> 4)));
        memcpy(page + 1, pattern + (size_t)c * OLED_W, OLED_W);
        ex_i2c(page, sizeof page);
    }
    ex_end();
    CHECK(nev == rows / 8 * 4);
    CHECK(display_state() == DISPLAY_SHOWN);
}
static void shows(void)
{
    show_window(0, 64);   /* 8 pages, 32 writes */
    show_window(8, 16);
    show_window(56, 8);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 8);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, 0, 12);
    refused(pattern, 4, 8);      /* y not a page boundary */
    refused(pattern, 64, 8);
    refused(pattern, 56, 16);
    refused(pattern, -8, 8);
}
/* A write that fails stops the driver at once and sets DISPLAY_I2C_FAILED; display_init clears it. Each armed case
 * counts the writes from its own first one. */
static void errors(void)
{
    int sleeps = 0, cfgs = 0, i;

    fill_pattern(sizeof pattern);
    /* (a) the 4th write of the init fails: three set-up calls, the reset delay, four writes, then nothing is sent */
    log_clear();
    i2c_calls = 0; i2c_fail_at = 3;
    display_init();
    for (i = 0; i < nev; ++i) {
        sleeps += evs[i].kind == K_SLEEP;
        cfgs += evs[i].kind == K_CFG;
    }
    CHECK(nev == 8 && cfgs == 3 && sleeps == 1);
    CHECK(display_state() == DISPLAY_I2C_FAILED);
    log_clear();
    display_show(pattern, 0, 64);
    CHECK(nev == 0);
    CHECK(display_state() == DISPLAY_I2C_FAILED);
    /* (b) a good init clears the state; the data write of page 2 (the 12th write of the show) fails */
    log_clear();
    i2c_calls = 0; i2c_fail_at = -1;
    display_init();
    CHECK(display_state() == DISPLAY_IDLE);
    log_clear();
    i2c_calls = 0; i2c_fail_at = 11;
    display_show(pattern, 0, 64);
    CHECK(nev == 12);
    CHECK(evs[11].kind == K_I2C && evs[11].n == 1 + OLED_W);
    CHECK(display_state() == DISPLAY_I2C_FAILED);
    /* (c) the 3rd write of the RAM clear's first page fails (the 18th write): no display on, no 100 ms delay */
    log_clear();
    i2c_calls = 0; i2c_fail_at = 17;
    display_init();
    sleeps = 0;
    for (i = 0; i < nev; ++i) {
        sleeps += evs[i].kind == K_SLEEP;
        CHECK(!(evs[i].kind == K_I2C && evs[i].n == 2 && EV_BYTES(&evs[i])[1] == 0xAF));
    }
    CHECK(nev == 4 + 18 && sleeps == 1);
    CHECK(display_state() == DISPLAY_I2C_FAILED);
    i2c_fail_at = -1;
}
#endif

#if defined(DRV_ESP_RGB)
#define RGB_WIN ((uint32_t)(320u << 16 | 240u))
static void init_sequence(void)
{
    log_clear();
    memset((void *)test_regs, 0, sizeof test_regs);
    (void)rgb_trap;                                /* referenced only if the driver touches ESP_RGB_REGS */
    display_init();
    CHECK(stores == 2);                            /* BPP, then WIN_SIZE, nothing else */
    CHECK(reg_traps == 0);                         /* no register read, no store around ESP_RGB_STORE */
    CHECK(store_idx[0] == 6 && store_val[0] == 16);
    CHECK(store_idx[1] == 1 && store_val[1] == RGB_WIN);
    CHECK(test_regs[6] == 16 && test_regs[1] == RGB_WIN);
    CHECK(test_regs[0] == 0 && test_regs[2] == 0 && test_regs[3] == 0 && test_regs[4] == 0 && test_regs[5] == 0);
    CHECK(display_565_bigendian == 0);
}
static void show_window(int y, int rows)
{
    size_t off = (size_t)y * 640, n = (size_t)rows * 640, i;
    fill_pattern(n);
    log_clear();
    vram_expect = pattern; vram_expect_off = off; vram_expect_n = n;   /* in VRAM before the first register store */
    test_regs[5] = 1;                             /* a polling driver would hang here (alarm in main) */
    display_show(pattern, (int16_t)y, (int16_t)rows);
    CHECK(stores == 4);                            /* FROM, TO, CONTENT, STATUS */
    CHECK(reg_traps == 0);                         /* in particular never a read of the status */
    CHECK(store_idx[0] == 2 && store_val[0] == 0);
    CHECK(store_idx[1] == 3 && store_val[1] == RGB_WIN);
    CHECK(store_idx[2] == 4 && store_val[2] == 0x20000000u);   /* the device address, not the host pointer */
    CHECK(store_idx[3] == 5 && store_val[3] == 1);
    CHECK(test_regs[2] == 0 && test_regs[3] == RGB_WIN && test_regs[4] == 0x20000000u && test_regs[5] == 1);
    CHECK(memcmp(test_vram + off, pattern, n) == 0);
    for (i = 0; i < off; ++i) CHECK(test_vram[i] == 0);
    for (i = off + n; i < sizeof test_vram; ++i) CHECK(test_vram[i] == 0);
}
static void shows(void)
{
    show_window(16, 24);
    show_window(0, 24);
    show_window(216, 24);
    show_window(0, 240);
}
static void refusals(void)
{
    fill_pattern(sizeof pattern);
    refused(NULL, 0, 24);
    refused(pattern, 0, 0);
    refused(pattern, 0, -8);
    refused(pattern, -1, 24);
    refused(pattern, 232, 24);
    refused(pattern, 0, 241);
}
#endif

int main(void)
{
#if defined(DRV_ST7789) || defined(DRV_ESP_SPI)
    svf_stub_dc_pin = PIN_DC;
#endif
#if defined(DRV_ESP_RGB)
    alarm(10);                   /* a driver that polls a register (the status stays 1) hangs: fail rather than wait */
#endif
    init_sequence();
    shows();
    refusals();
#if defined(DRV_SH1106)
    errors();
#endif
#if defined(DRV_ESP_SPI)
    {   /* the stub's transmit refuses an empty transaction and does not record it */
        spi_transaction_t tr;
        memset(&tr, 0, sizeof tr);
        log_clear();
        CHECK(spi_device_polling_transmit(NULL, &tr) != ESP_OK && nev == 0);
        tr.length = 8;
        CHECK(spi_device_polling_transmit(NULL, &tr) != ESP_OK && nev == 0);   /* length but no buffer */
        tr.tx_buffer = pattern; tr.length = 0;
        CHECK(spi_device_polling_transmit(NULL, &tr) != ESP_OK && nev == 0);   /* buffer but no length */
        /* the flag is IDF's value, BIT(8); BIT(10) is SPI_TRANS_MODE_OCT, a different transaction mode */
        CHECK(SPI_TRANS_CS_KEEP_ACTIVE == 0x100u);
        /* as IDF: SPI_TRANS_CS_KEEP_ACTIVE needs the bus acquired, else ESP_ERR_INVALID_ARG and nothing sent */
        tr.length = 8; tr.flags = SPI_TRANS_CS_KEEP_ACTIVE;
        CHECK(spi_device_polling_transmit(NULL, &tr) == ESP_ERR_INVALID_ARG && nev == 0);
        /* with the bus held it is accepted, CS stays asserted, and releasing the bus does not change CS (as IDF) */
        CHECK(spi_device_acquire_bus(NULL, portMAX_DELAY) == ESP_OK);
        CHECK(spi_device_polling_transmit(NULL, &tr) == ESP_OK && svf_stub_cs == 1);
        spi_device_release_bus(NULL);
        CHECK(svf_stub_cs == 1 && svf_stub_bus == 0);
        tr.flags = 0;                                  /* a plain transmit ends the frame */
        CHECK(spi_device_polling_transmit(NULL, &tr) == ESP_OK && svf_stub_cs == 0);
    }
#endif
    CHECK(!any_nostop);          /* no_nostop_anywhere: never a write without STOP */
    CHECK(!bad_i2c);             /* every I2C write goes to 0x3C */
    printf("port-check-driver-%s: OK\n", TEST_ID);
    return 0;
}
