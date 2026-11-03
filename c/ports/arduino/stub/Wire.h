/* Compile-check stub of the Arduino Wire library for arduino.ino (c/cross/build-all.sh --ports); not the library. */
#ifndef STUB_WIRE_H
#define STUB_WIRE_H
#include <stddef.h>
#include <stdint.h>
class TwoWire {
public:
	void begin(void) {}
	void setClock(uint32_t hz) { clock = hz; }
	void beginTransmission(uint8_t addr) { last = addr; }
	size_t write(uint8_t b) { last ^= b; return 1; }
	size_t write(const uint8_t *p, size_t n) { for (size_t i = 0; i < n; ++i) last ^= p[i]; return n; }
	uint8_t endTransmission(void) { return 0; }
	volatile uint8_t last; /* keeps the writes from being optimised away */
	uint32_t clock;
};
static TwoWire Wire;
#endif
