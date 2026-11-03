#!/bin/sh
# check-sizes-md.sh ROWS SIZES.md - the "Port examples" table of SIZES.md must hold the sizes just measured.
# ROWS has one line a port: "port profile faces text data bss kind targets" (build-all.sh --ports writes OUT/ports/rows.txt).
# Compared per row: the kind and SVF_TARGETS column, faces, text, data, bss, and text without faces (= text - faces).
# A line "program NAME BYTES" (dos, web: whole programs) is compared with the "(dos: `F` N bytes; web: `F` N bytes.)"
# line of the same section: every program measured must be named there with its bytes, and no other.
# Rows whose first token is "info" (e.g. "info program sdl2 N") are informational and skipped.
# Silent on success; on a mismatch names the row and exits 1.
# check-sizes-md.sh --pico-sdk ROWS SIZES.md - the same for the "Pico SDK images" table (link sizes of the real pico-sdk
# images, which run-screens.sh measures with arm-none-eabi-size). ROWS has one line a profile: "profile text data bss".
# check-sizes-md.sh --ch582-sdk ROWS SIZES.md - the same for the "CH582 SDK image" table (build-all.sh's make of
# c/ports/ch582). ROWS has one line an image: "image text data bss highcode libISP583 stack ram"; all seven numbers are compared.
# check-sizes-md.sh --switches ROWS VROWS SIZES.md - the same for the two tables of "Size switches" (Cortex-M0+ and AVR):
# ROWS and VROWS are build-all.sh's rows.md and rows-switches.md ("| toolchain | version | profile [switch] | text | data | bss |").
# Every cell of a switch column (and of the default column) is compared with the measured text; the AVR "P4 data + bss" row
# with data + bss. On AVR the columns of SVF_MERGE_WORDS=0 and SVF_GRAY8_LUT1=0 (not built: both default to 0) are the default's. A cell "N (default)" is the default build's number. A table cell with no measured build fails.
# A variant whose link overflowed (build-all.sh's row "| P4 [LABEL] | overflow N | - | - |") is the cell "overflow N" in a
# text row and "-" in the data + bss row; a number there, or "overflow" where the build linked, fails.
# check-sizes-md.sh --features ROWS SIZES.md - the "Minimal config" table (check-features.sh). ROWS has one line a build:
# "toolchain config text rodata data bss". The gated rows (avr minimal, m0plus minimal, m0plus default) must equal the table
# exactly in all four numbers (a difference is printed as "avr minimal 12920 -> 12921 (+1)", table -> measured, for the text;
# "avr minimal data A -> B (+d)" for the others) and must all be measured; every other row is printed as an "info" line
# with the table's text (or "no table row") and not gated.
set -u
usage() { echo "usage: check-sizes-md.sh ROWS SIZES.md | check-sizes-md.sh --pico-sdk ROWS SIZES.md | check-sizes-md.sh --ch582-sdk ROWS SIZES.md | check-sizes-md.sh --switches ROWS VROWS SIZES.md | check-sizes-md.sh --features ROWS SIZES.md" >&2; exit 2; }
if [ "${1:-}" = "--features" ]; then
	[ $# -eq 3 ] || usage
	awk -v rows="$2" '
		BEGIN {
			gated["avr minimal"] = 1; gated["m0plus minimal"] = 1; gated["m0plus default"] = 1
			split("text rodata data bss", name, " ")
			while ((getline l < rows) > 0) {
				if (split(l, f, " ") != 6) { print "SIZES.md: unreadable features row: " l; bad = 1; continue }
				k = f[1] " " f[2]; m[k] = f[3] " " f[4] " " f[5] " " f[6]; order[++n] = k
			}
		}
		/^## Minimal config/ { on = 1; next }
		/^## / { on = 0 }
		on && /^\| (avr|m0plus) \|/ {
			split($0, c, "|")
			for (i = 2; i <= 7; i++) { gsub(/[ ,]/, "", c[i]) }
			k = c[2] " " c[3]; t[k] = c[4] " " c[5] " " c[6] " " c[7]; seen[k] = 1
		}
		END {
			for (k in gated) {
				if (!(k in m)) { print "SIZES.md: " k " was not measured"; bad = 1 }
				if (!(k in seen)) { print "SIZES.md: Minimal config has no row " k; bad = 1 }
			}
			for (j = 1; j <= n; j++) {
				k = order[j]; split(m[k], g, " ")
				if (!(k in gated)) {
					split(t[k], w, " ")
					print "info: " k " text " g[1] " rodata " g[2] " data " g[3] " bss " g[4] ((k in seen) ? " (table text " w[1] ")" : " (no table row)")
					continue
				}
				if (!(k in seen)) continue
				split(t[k], w, " ")
				for (i = 1; i <= 4; i++) if (w[i] != g[i]) {
					printf "SIZES.md: %s %s%s -> %s (%+d)\n", k, (i == 1 ? "" : name[i] " "), w[i], g[i], g[i] - w[i]
					bad = 1
				}
			}
			exit bad
		}' "$3"
	exit
fi
if [ "${1:-}" = "--ch582-sdk" ]; then
	[ $# -eq 3 ] || usage
	rows=$2 md=$3
	awk -v rows="$rows" '
		BEGIN { while ((getline l < rows) > 0) { split(l, f, " "); m[f[1]] = f[2] " " f[3] " " f[4] " " f[5] " " f[6] " " f[7] " " f[8]; n++ } }
		/^## CH582 SDK image/ { on = 1; next }
		/^## / { on = 0 }
		on && /^\| svf_[A-Za-z0-9_]* \|/ {
			split($0, c, "|")
			for (i = 2; i <= 9; i++) { gsub(/[ ,]/, "", c[i]) }
			got = c[3] " " c[4] " " c[5] " " c[6] " " c[7] " " c[8] " " c[9]
			seen++
			if (!(c[2] in m)) { print "SIZES.md: CH582 SDK image " c[2] " was not measured"; bad = 1 }
			else if (m[c[2]] != got) { print "SIZES.md: CH582 SDK image " c[2] " says text/data/bss/highcode/libISP583/stack/RAM " got ", measured " m[c[2]]; bad = 1 }
		}
		END { if (seen != n) { print "SIZES.md: " seen+0 " CH582 SDK image rows, " n+0 " measured"; bad = 1 } exit bad }' "$md"
	exit
fi
if [ "${1:-}" = "--switches" ]; then
	[ $# -eq 4 ] || usage
	awk -v rows="$2" -v vrows="$3" '
		function trim(s) { gsub(/^ +| +$/, "", s); return s }
		function load(file, isv,    l, c, n, pr, sw, k) {
			while ((getline l < file) > 0) {
				n = split(l, c, "|")
				if (n < 7 || c[2] !~ /(cortex-m0plus|avr-atmega328p)/) continue
				pr = trim(c[4]); sw = "default"
				if (match(pr, / \[.*\]$/)) { sw = substr(pr, RSTART + 2, RLENGTH - 3); pr = substr(pr, 1, RSTART - 1) }
				k = (c[2] ~ /cortex/ ? "m0" : "avr") " " pr " " sw
				raw[k] = trim(c[5]); text[k] = raw[k] + 0; ds[k] = trim(c[6]) + trim(c[7])
				if (raw[k] ~ /^overflow [0-9]+$/) { text[k] = raw[k]; ds[k] = "-" }
			}
			close(file)
		}
		BEGIN { load(rows); load(vrows) }
		/^## / { on = ($0 ~ /^## Size switches/); tab = ""; next }
		on && /^\| (Cortex-M0\+|AVR) \(/ {
			tab = ($0 ~ /^\| Cortex/ ? "m0" : "avr")
			ncol = split($0, h, "|")
			for (i = 3; i < ncol; i++) { x = trim(h[i]); gsub(/`/, "", x); col[i] = x }
			next
		}
		on && tab != "" && /^\|/ && !/^\|[-| :]*$/ {
			n = split($0, c, "|")
			lab = trim(c[2]); what = "text"
			if (tab == "avr") {
				if (lab ~ /^P[0-9]\*? text$/) sub(/ text$/, "", lab)
				else if (lab == "P4 data + bss") { lab = "P4"; what = "ds" }
				else next
			}
			for (i = 3; i < n; i++) {
				cell = trim(c[i]); gsub(/,/, "", cell)
				isdef = (cell ~ /\(default\)/); sub(/ *\(default\).*/, "", cell)
				k = tab " " lab " " (isdef ? "default" : col[i])
				seen++
				# AVR defaults of these two switches are 0 (compiled out): not built as variants, the default build stands for them
				if (!(k in text) && tab == "avr" && col[i] ~ /SVF_(MERGE_WORDS|GRAY8_LUT1)=0/) k = tab " " lab " default"
				if (!(k in text)) { print "SIZES.md: Size switches " tab " " lab " [" col[i] "] was not measured"; bad = 1; continue }
				got = (what == "ds" ? ds[k] : text[k])
				if (got ~ /^(overflow|-)/) { if (cell != got) { print "SIZES.md: Size switches " tab " " lab " [" col[i] "] says " cell " (" what "), measured " got; bad = 1 } continue }
				if (cell + 0 != got || cell !~ /^[0-9]+$/) { print "SIZES.md: Size switches " tab " " lab " [" col[i] "] says " cell " (" what "), measured " got; bad = 1 }
			}
		}
		END { if (seen == 0) { print "SIZES.md: no Size switches cells found"; bad = 1 } exit bad }' "$4"
	exit
fi
if [ "${1:-}" = "--pico-sdk" ]; then
	[ $# -eq 3 ] || usage
	rows=$2 md=$3
	awk -v rows="$rows" '
		BEGIN { while ((getline l < rows) > 0) { split(l, f, " "); m[f[1]] = f[2] " " f[3] " " f[4]; n++ } }
		/^## Pico SDK images/ { on = 1; next }
		/^## / { on = 0 }
		on && /^\| (colour|grey|mono) \|/ {
			split($0, c, "|")
			for (i = 2; i <= 5; i++) { gsub(/[ ,]/, "", c[i]) }
			got = c[3] " " c[4] " " c[5]
			seen++
			if (!(c[2] in m)) { print "SIZES.md: Pico SDK image " c[2] " was not measured"; bad = 1 }
			else if (m[c[2]] != got) { print "SIZES.md: Pico SDK image " c[2] " says text/data/bss " got ", measured " m[c[2]]; bad = 1 }
		}
		END { if (seen != n) { print "SIZES.md: " seen+0 " Pico SDK image rows, " n " measured"; bad = 1 } exit bad }' "$md"
	exit
fi
[ $# -eq 2 ] || usage
rows=$1 md=$2
awk -v rows="$rows" '
	BEGIN { while ((getline l < rows) > 0) { split(l, f, " ")
		if (f[1] == "info") continue # informational rows (SDL programs): measured, not gated
		if (f[1] == "program") { prog[f[2]] = f[3]; np++; continue }
		k = f[1] " " f[2]; m[k] = f[3] " " f[4] " " f[5] " " f[6]; kt[k] = f[7] f[8]; wo[k] = f[4] - f[3]; n++ } }
	/^## Port examples/ { on = 1; next }
	/^## / { on = 0 }
	on && /^\((dos|web): / {
		line = $0
		sub(/^\(/, "", line); sub(/\.?\)$/, "", line)
		k = split(line, parts, "; ")
		for (j = 1; j <= k; j++) {
			if (split(parts[j], p, " ") != 4 || p[4] != "bytes") { print "SIZES.md: program sizes line unreadable: " parts[j]; bad = 1; continue }
			name = p[1]; sub(/:$/, "", name); b = p[3]; gsub(/,/, "", b)
			pseen++
			if (!(name in prog)) { print "SIZES.md: program " name " was not measured"; bad = 1 }
			else if (prog[name] != b) { print "SIZES.md: program " name " says " b " bytes, measured " prog[name]; bad = 1 }
		}
	}
	on && /^\| (pico|pico-small|esp32c3|esp32s3|arduino|arduino-small|arduino-mega|arduino-mega-rich|ch582) \|/ {
		split($0, c, "|")
		for (i = 2; i <= 9; i++) { gsub(/[ ,]/, "", c[i]) }
		key = c[2] " " c[3]
		got = c[5] " " c[6] " " c[7] " " c[8]
		kind = c[4]
		seen++
		if (!(key in m)) { print "SIZES.md: row " key " was not measured"; bad = 1 }
		else {
			if (m[key] != got) { print "SIZES.md: row " key " says faces/text/data/bss " got ", measured " m[key]; bad = 1 }
			if (kt[key] != kind) { print "SIZES.md: row " key " says kind/SVF_TARGETS " kind ", measured " kt[key]; bad = 1 }
			if (wo[key] != c[9]) { print "SIZES.md: row " key " says text without faces " c[9] ", measured " wo[key]; bad = 1 }
		}
	}
	END { if (seen != n) { print "SIZES.md: " seen+0 " Port examples rows, " n+0 " measured"; bad = 1 }
		if (pseen != np) { print "SIZES.md: " pseen+0 " program sizes, " np+0 " measured"; bad = 1 }
		exit bad }' "$md"
