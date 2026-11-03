# sums.inc.sh - the expected checksums of the cases of c/bench/bench.c, per target kind (python3 -I c/bench/sums.py,
# i.e. tools/svfline.py), sourced by run-pico.sh, run-esp32.sh, run-m33.sh, run-rp2350.sh and run-wasm.sh
# (run-dos.sh keeps its line sums as literals); sums_for_faces (below) recomputes them for other
# faces. tools/test_c_renderer.py TestBenchSums keeps them equal to sums.py and to the host build of bench.c.
SUMS_MONO_PAGE="syl_ga:64b1ad7b syl_bwelk:1aaf98c2 compose_bwelk:9b1093a3 screen32:f4079faf line8:6cc46c87 layout_probe:00040404"
SUMS_GRAY8="syl_ga:4f8976a1 syl_bwelk:506da3da compose_bwelk:9b1093a3 screen32:a3e38628 line8:13f4737d aa_syl_ga:868f3420 aa_syl_bwelk:087e0af1 aa_line12:8a1e14e9 aa_screen10:ff58266a layout_probe:00040404"
SUMS_RGB565="syl_ga:011f2f55 syl_bwelk:99b5c4e7 compose_bwelk:9b1093a3 screen32:ea7ca7ff line8:8eaa5f79 aa_syl_ga:b0a50bda aa_syl_bwelk:2176bfa9 aa_line12:18680583 aa_screen10:d1cd559a layout_probe:00040404"
SUMS_LINE40="line40_mapped:d88e20f9 line40_mapped_cache:d88e20f9 line40_stream_cold:d88e20f9 line40_stream_warm:d88e20f9 line40_stream_small:d88e20f9 line40_stream_nocache:d88e20f9 line40_scaled32:13e5d91d layout_probe:00040404"
# layout_probe (bench.c): every sum above ends in the default build's; a build with -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT
# (run-avr.sh) swaps in the strict one.
SUMS_LAYOUT_DEFAULT="layout_probe:00040404"
SUMS_LAYOUT_STRICT="layout_probe:00080804"

# sums_for_faces TAG ROOT: with FACE, FACE16 or FACE18 other than the defaults under ROOT/svf (dos/NEODG16G.SVF,
# dos/PAPLG16.SVF, dos/PAPLG18.SVF) the SUMS_<name> above are not theirs: sums.py computes them (needs HERE). Exits 1
# ("TAG: sums.py failed") when it cannot.
sums_for_faces() {
	[ "$FACE" != "$2/svf/dos/NEODG16G.SVF" ] || [ "$FACE16" != "$2/svf/dos/PAPLG16.SVF" ] ||
		[ "$FACE18" != "$2/svf/dos/PAPLG18.SVF" ] || return 0
	_sums=$(python3 -I "$HERE/sums.py" --face "$FACE" --face16 "$FACE16" --face18 "$FACE18") ||
		{ echo "$1: sums.py failed"; exit 1; }
	for _k in MONO_PAGE GRAY8 RGB565 LINE40; do
		eval "SUMS_$_k=\$(printf '%s\n' \"\$_sums\" | sed -n 's/^SUMS_${_k}=\"\(.*\)\"\$/\1/p')"
	done
}
