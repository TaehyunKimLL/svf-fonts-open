/* i2c.h - one bounded, polled I2C master write on the CH58x hardware I2C (see i2c.c). */
#ifndef CH582_I2C_H
#define CH582_I2C_H

#include <stddef.h>
#include <stdint.h>

/* Iterations per wait. One iteration makes two SDK calls (I2C_GetFlagStatus for AF, then I2C_CheckEvent or
 * I2C_GetFlagStatus for the awaited condition), each about 40 cycles with the call, the register read and the compare,
 * so about 80 cycles an iteration; 5,000 iterations are 400,000 cycles, 17 ms at the 24 MHz system clock. A wait that
 * gets no answer returns failure after this many iterations (about 17 ms; it only has to be bounded). */
#define CH582_I2C_SPIN 5000

/* Write @p n bytes to the 7-bit address @p addr: START, address, bytes, STOP. 0 when every byte was sent, -1 on a
 * timeout, a NACK (AF) or a bad argument (buf NULL, n 0, addr past 0x7F); after any failure that began a transfer the
 * bus has been given a STOP. The I2C peripheral must have been set up (GPIOPinRemap, GPIOB_ModeCfg, I2C_Init). */
int ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n);

#endif
