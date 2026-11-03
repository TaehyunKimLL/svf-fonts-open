#!/bin/sh
# check-esp32-cal.sh RUN.txt [LOOPS] - checks the calibration lines of an ESP32-S3 bench run (bench.c, -DBENCH_ESP32S3):
#   exactly one  cal=nop1000 ccount=N               1,000 NOPs: N within 1280 +- 2 (the 25 ns tick against 32 ns an instruction)
#   exactly LOOPS (default 4)  cal=loop1m icount=I ccount=C
#                                                   a loop of 1,000,000 instructions: I (the ICOUNT advance, the counter the
#                                                   cases use) within 1,000,000 +- 0.1 %. Each loop is longer than the other
#                                                   core's scheduling slice (390,630 instructions): a measurement that
#                                                   includes core 1's spinning (CCOUNT converted, the first version of this
#                                                   bench) reads about 2,170,000 in every second loop and fails here.
# Every line starting "cal=" must be one of those, in exactly that form (no extra fields, only digits). Prints the
# reason and exits 1 on any deviation, 0 when the calibration is sound.
LOOPS=${2:-4}
[ $# -ge 1 ] && [ -f "$1" ] || { echo "usage: check-esp32-cal.sh RUN.txt [LOOPS]" >&2; exit 2; }
awk -v loops="$LOOPS" '
/^cal=/ {
	if ($0 ~ /^cal=nop1000 ccount=[0-9]+$/) {
		split($2, a, "=")
		++nops
		if (a[2] + 0 < 1278 || a[2] + 0 > 1282) {
			print "cal: nop1000 read " a[2] " ticks, expected 1280 +- 2"
			bad = 1
		}
	} else if ($0 ~ /^cal=loop1m icount=[0-9]+ ccount=[0-9]+$/) {
		split($2, a, "=")
		++lps
		if (a[2] + 0 < 999000 || a[2] + 0 > 1001000) {
			print "cal: loop1m icount " a[2] " is not 1,000,000 +- 0.1 % (" $3 ")"
			bad = 1
		}
	} else {
		print "cal: malformed line: " $0
		bad = 1
	}
}
END {
	if (nops != 1) { print "cal: expected exactly one cal=nop1000 line, found " nops + 0; bad = 1 }
	if (lps != loops) { print "cal: expected exactly " loops " cal=loop1m lines, found " lps + 0; bad = 1 }
	exit bad
}' "$1"
