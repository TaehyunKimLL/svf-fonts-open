"""image_sizes.py --size SIZE --readelf READELF ELF MAP - the size line and the gates of the CH582 image.

Prints one line: NAME: text T data D bss B highcode H libISP583 K stack S ram R
 - text, data and bss follow c/cross/build-all.sh's sizes_a on `size -A`: .highcode counts in text; .stack, debug, note
   and attribute sections are left out; ram = highcode + data + bss + stack (the link script puts .stack at the top of
   the 32 KB, so the linker's own RAM line reads 100%);
 - K = the bytes of the input sections taken from libISP583.a(...) in the map's "Linker script and memory map" part
   (the one-line and the wrapped form of an input section; only allocated output sections count; the
   discarded-sections list comes before it and is ignored).
Exit 1 with "image_sizes: ..." when a PT_LOAD segment with file size > 0 ends past 0x70000 at its load address (wchisp
programs the segments at p_paddr: .highcode and .data must be loaded in flash, not at their RAM address), when
ram > 32768 or over the port's budget of 8192 bytes, or when the map has no "Linker script and memory map".
"""
import argparse
import os
import re
import subprocess
import sys

FLASH_END = 0x70000
RAM_SIZE = 32768
RAM_BUDGET = 8192  # the port's plan: the image's RAM total stays well under 8 KB
MAP_HEADER = "Linker script and memory map"

# size -A: "name size addr" lines
_SKIP = re.compile(r"^\.(comment|debug|note|stack|ARM\.attributes|riscv\.attributes|xtensa\.info|xt\.)")
_LOAD = re.compile(r"^\s*LOAD\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+0x[0-9a-fA-F]+")
# an input section of the memory map: " .name  0xADDR  0xSIZE  FILE" or the name alone and the rest on the next line
_ONE = re.compile(r"^ (\S+)\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)\s+(\S.*)$")
_NAME = re.compile(r"^ (\S+)\s*$")
_REST = re.compile(r"^\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)\s+(\S.*)$")
_LIB = "libISP583.a("


class ImageSizesError(Exception):
    pass


def library_bytes(map_text):
    """The bytes of the allocated input sections from libISP583.a(...) in the memory map (not the discarded ones, not
    .comment / .debug / attributes)."""
    pos = map_text.find(MAP_HEADER)
    if pos < 0:
        raise ImageSizesError('the map has no "%s"' % MAP_HEADER)
    total, pending, counted = 0, False, True
    for line in map_text[pos:].splitlines():
        if line[:1] not in (" ", "\t", ""):
            # an output section: only allocated ones count (not .comment, .debug_*, attributes)
            counted = not _SKIP.match(line.split()[0])
            pending = False
            continue
        if not counted:
            continue
        m = _ONE.match(line)
        if m:
            pending = False
            if _LIB in m.group(3):
                total += int(m.group(2), 16)
            continue
        if pending:
            m = _REST.match(line)
            if m and _LIB in m.group(2):
                total += int(m.group(1), 16)
        pending = bool(_NAME.match(line))
    return total


def analyse(size_text, readelf_text, map_text):
    text = data = bss = highcode = stack = 0
    for line in size_text.splitlines():
        f = line.split()
        if len(f) != 3 or f[0] == "section" or _SKIP.match(f[0]) and f[0] != ".stack":
            continue
        if not f[1].isdigit():
            continue
        n = int(f[1])
        if f[0] == ".stack":
            stack += n
        elif f[0].startswith(".data"):
            data += n
        elif f[0].startswith((".bss", ".noinit")):
            bss += n
        else:
            text += n
            if f[0] == ".highcode":
                highcode += n
    loads = 0
    for line in readelf_text.splitlines():
        m = _LOAD.match(line)
        if not m:
            continue
        paddr, filesz = int(m.group(1), 16), int(m.group(2), 16)
        if filesz == 0:
            continue
        loads += 1
        if paddr + filesz > FLASH_END:
            raise ImageSizesError("a loadable segment ends at 0x%x, past 0x%x (flash end)"
                                  % (paddr + filesz, FLASH_END))
    if not loads:
        raise ImageSizesError("the program headers show no loadable segment")
    lib = library_bytes(map_text)
    ram = highcode + data + bss + stack
    if ram > RAM_SIZE:
        raise ImageSizesError("ram %d bytes is more than %d" % (ram, RAM_SIZE))
    if ram > RAM_BUDGET:
        raise ImageSizesError("ram %d bytes is over the budget of %d" % (ram, RAM_BUDGET))
    return {"text": text, "data": data, "bss": bss, "highcode": highcode, "libisp": lib, "stack": stack, "ram": ram}


def format_line(name, r):
    return "%s: text %d data %d bss %d highcode %d libISP583 %d stack %d ram %d" % (
        name, r["text"], r["data"], r["bss"], r["highcode"], r["libisp"], r["stack"], r["ram"])


def _run(argv):
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise ImageSizesError("%s failed: %s" % (argv[0], e))


def main(argv):
    ap = argparse.ArgumentParser(prog="image_sizes.py")
    ap.add_argument("--size", required=True)
    ap.add_argument("--readelf", required=True)
    ap.add_argument("elf")
    ap.add_argument("map")
    a = ap.parse_args(argv)
    try:
        with open(a.map, encoding="latin-1") as f:
            map_text = f.read()
        r = analyse(_run([a.size, "-A", a.elf]), _run([a.readelf, "-lW", a.elf]), map_text)
    except (ImageSizesError, OSError) as e:
        print("image_sizes: %s" % e, file=sys.stderr)
        return 1
    print(format_line(os.path.splitext(os.path.basename(a.elf))[0], r))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
