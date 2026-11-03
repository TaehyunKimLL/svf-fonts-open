#!/bin/sh
# profiles.cmake in script and include mode against the spec's three rows (hard-coded) and profiles.txt; exit 1 on failure.
here=$(cd "$(dirname "$0")" && pwd)
ports=$here/..
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "profiles-cmake: FAIL: $1" >&2; exit 1; }
F="dos/PAPLG16.SVF,dos/PAPLG18.SVF"

# expected: profile port -> line (spec "One table, read by every build")
expect() {
  case "$1/$2" in
    colour/pico)  echo "kind=RGB565 targets=0x08 faces=$F driver=st7789 bus=spi";;
    colour/esp32) echo "kind=RGB565 targets=0x08 faces=$F driver=ili9341 bus=spi";;
    grey/pico)    echo "kind=GRAY8 targets=0x01 faces=$F driver=ssd1327 bus=i2c";;
    grey/esp32)   echo "kind=GRAY8 targets=0x01 faces=$F driver=ssd1327 bus=spi";;
    mono/pico)    echo "kind=MONO_PAGE targets=0x02 faces=dos/NEODG16G.SVF driver=ssd1306 bus=i2c";;
    mono/esp32)   echo "kind=MONO_PAGE targets=0x02 faces=dos/NEODG16G.SVF driver=ssd1306 bus=spi";;
  esac
}

cat > "$tmp/probe.cmake" <<'EOP'
include("${PROFILES}")
string(REPLACE ";" "," _f "${SVF_FACES}")
list(LENGTH SVF_FACES _n)
execute_process(COMMAND ${CMAKE_COMMAND} -E echo
  "kind=${SVF_KIND} targets=${SVF_TARGETS_BIT} faces=${_f} n=${_n} driver=${SVF_DRIVER} bus=${SVF_BUS} def=${SVF_GREY_KIND_DEFINE}")
EOP

for prof in colour grey mono; do
  for port in pico esp32; do
    want=$(expect $prof $port)
    got=$(cmake -DSVF_PROFILE=$prof -DSVF_PORT=$port -P "$ports/profiles.cmake") || fail "$prof/$port: cmake exit"
    [ "$got" = "$want" ] || fail "$prof/$port: script got '$got' want '$want'"
    # the table itself (awk reading) agrees with the hard-coded values
    if [ "$port" = pico ]; then dc=5; bc=7; else dc=6; bc=8; fi
    aw=$(awk -v p=$prof -v dc=$dc -v bc=$bc '/^#/ {next} $1 == p { printf "kind=%s targets=%s faces=%s driver=%s bus=%s\n", $2, $3, $4, $(dc), $(bc) }' "$ports/profiles.txt")
    [ "$aw" = "$want" ] || fail "$prof/$port: profiles.txt gives '$aw' want '$want'"
    # include mode: from another script, nothing printed by profiles.cmake itself, every variable set
    nfaces=2; [ $prof = mono ] && nfaces=1
    def=; [ $prof = grey ] && def=SVF_GREY_KIND_GRAY8=1
    inc=$(cmake -DPROFILES="$ports/profiles.cmake" -DSVF_PROFILE=$prof -DSVF_PORT=$port -P "$tmp/probe.cmake") || fail "$prof/$port: include probe exit"
    [ "$(echo "$inc" | wc -l)" -eq 1 ] || fail "$prof/$port: include mode printed extra output: $inc"
    [ "$inc" = "$(echo "$want" | sed "s/ driver=/ n=$nfaces driver=/") def=$def" ] || fail "$prof/$port: include got '$inc'"
  done
done
err=$(cmake -DSVF_PROFILE=color -DSVF_PORT=pico -P "$ports/profiles.cmake" 2>&1 >/dev/null) && fail "colour typo accepted"
case $err in *"choose one of colour, grey, mono"*) ;; *) fail "typo message: $err";; esac
err=$(cmake -DSVF_PROFILE=grey -DSVF_PORT=avr -P "$ports/profiles.cmake" 2>&1 >/dev/null) && fail "port avr accepted"
case $err in *"SVF_PORT avr: pico or esp32"*) ;; *) fail "avr message: $err";; esac
err=$(cmake -DSVF_PROFILE=grey -DSVF_PORT=pico -DSVF_GREY_KIND=GRAY4 -P "$ports/profiles.cmake" 2>&1 >/dev/null) && fail "GRAY4 accepted"
case $err in *t_8e7da3c1*) ;; *) fail "GRAY4 message: $err";; esac
for p in colour mono; do
  cmake -DSVF_PROFILE=$p -DSVF_PORT=pico -DSVF_GREY_KIND=GRAY4 -P "$ports/profiles.cmake" >/dev/null 2>&1 || fail "$p should ignore SVF_GREY_KIND"
done
# omitting a required variable is an error that names it; a path with a space and a semicolon works in include mode
err=$(cmake -DSVF_PORT=pico -P "$ports/profiles.cmake" 2>&1 >/dev/null) && fail "missing SVF_PROFILE accepted"
case $err in *"choose one of colour, grey, mono"*) ;; *) fail "missing SVF_PROFILE message: $err";; esac
err=$(cmake -DSVF_PROFILE=colour -P "$ports/profiles.cmake" 2>&1 >/dev/null) && fail "missing SVF_PORT accepted"
case $err in *"pico or esp32"*) ;; *) fail "missing SVF_PORT message: $err";; esac
mkdir "$tmp/with space;semi"
cp "$ports/profiles.cmake" "$ports/profiles.txt" "$tmp/with space;semi/"
inc=$(cmake -DPROFILES="$tmp/with space;semi/profiles.cmake" -DSVF_PROFILE=mono -DSVF_PORT=pico -P "$tmp/probe.cmake") || fail "path with a space and a semicolon: include probe exit"
case $inc in "kind=MONO_PAGE "*) ;; *) fail "path with a space and a semicolon: got '$inc'";; esac
# a short row is a clear error; a comment indented with spaces is skipped
mkdir "$tmp/short" "$tmp/indent"
cp "$ports/profiles.cmake" "$tmp/short/"; cp "$ports/profiles.cmake" "$tmp/indent/"
printf 'colour RGB565 0x08\n' > "$tmp/short/profiles.txt"
err=$(cmake -DSVF_PROFILE=colour -DSVF_PORT=pico -P "$tmp/short/profiles.cmake" 2>&1 >/dev/null) && fail "short row accepted"
case $err in *"columns"*) ;; *) fail "short row message: $err";; esac
{ printf '   # indented comment with words\n'; cat "$ports/profiles.txt"; } > "$tmp/indent/profiles.txt"
got=$(cmake -DSVF_PROFILE=mono -DSVF_PORT=esp32 -P "$tmp/indent/profiles.cmake") || fail "indented comment broke the parse"
[ "$got" = "$(expect mono esp32)" ] || fail "indented comment: '$got'"
echo "profiles-cmake: OK"
