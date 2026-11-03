/* fix_banner.c - negative fixture of esp-screen.py: a guest that prints a line before "screen=ready". The runner must
 * fail with "unexpected line: boot banner" (bare build, built like the C3 colour image). */
#include <stdio.h>

int main(void)
{
	printf("boot banner\n");
	printf("screen=ready\n");
	fflush(stdout);
	for (;;)
		;
}
