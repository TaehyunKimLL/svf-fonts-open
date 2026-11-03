/* Compile-check stub of the pico-sdk calls main.c makes (c/cross/build-all.sh --ports); not the SDK.
 * Under SVF_STUB_RECORD i2c_write_blocking reports the write (svf_stub_record.h). */
#ifndef STUB_HARDWARE_I2C_H
#define STUB_HARDWARE_I2C_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef SVF_STUB_RECORD
#include "svf_stub_record.h"
#endif
typedef struct i2c_inst i2c_inst_t;
#define i2c0 ((i2c_inst_t *)0)
static inline unsigned i2c_init(i2c_inst_t *i2c, unsigned baudrate)
{
	(void)i2c;
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_I2C_INIT, (int)baudrate, 0, 0, 0);
#endif
	return baudrate;
}
static inline int i2c_write_blocking(i2c_inst_t *i2c, uint8_t addr, const uint8_t *src, size_t len, bool nostop)
{
	(void)i2c; (void)addr; (void)nostop;
#ifdef SVF_STUB_RECORD
	svf_rec_i2c(addr, src, len, nostop);
#endif
	return src ? (int)len : 0;
}
#endif
