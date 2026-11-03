/* i2c_stub.c - no-op stand-in for ports/ch582/i2c.c in the bare link of c/cross/build-all.sh: the SVF side of the port
 * (main.c, the profile, the SH1106 driver, the library, the face) links without the WCH SDK. The real image is the
 * Makefile's. */
#include "i2c.h"

int ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n)
{
	(void)addr;
	(void)buf;
	(void)n;
	return 0;
}
