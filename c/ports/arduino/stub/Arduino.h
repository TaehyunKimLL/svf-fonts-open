/* Compile-check stub of the Arduino core for arduino.ino (c/cross/build-all.sh --ports); not the core. It supplies the
 * main() the core would (setup, then loop forever). */
#ifndef STUB_ARDUINO_H
#define STUB_ARDUINO_H
#include <avr/pgmspace.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
void setup(void);
void loop(void);
int main(void)
{
	setup();
	for (;;)
		loop();
}
#endif
