"""Tests for c/ports/ch582/image_sizes.py (the size line and the gates of the CH582 image)."""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "..", "ch582", "image_sizes.py")
spec = importlib.util.spec_from_file_location("image_sizes", PATH)
image_sizes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_sizes)

MAP = """Archive member included to satisfy reference by file (symbol)

/x/libISP583.a(ISP583.o)
                              /tmp/a.o (FLASH_ROM_ERASE)

Discarded input sections

 .text          0x00000000        0x0 /tmp/a.o
 .text.unused   0x00000000      0x100 /x/libISP583.a(ISP583.o)

Memory Configuration

Name             Origin             Length             Attributes
FLASH            0x00000000         0x00070000         xr
RAM              0x20000000         0x00008000         xrw

Linker script and memory map

.highcode       0x20000000      0x426
 *(.highcode)
 .highcode      0x2000061e      0x426 /x/libISP583.a(ISP583.o)
 .highcode      0x20000a44       0x20 /tmp/other.o

.text           0x00000100      0x200
 .text.FLASH_ROM_X
                0x00000100       0x10 /x/libISP583.a(ISP583.o)
 .text.main     0x00000110       0x40 /tmp/main.o
 .text.other
                0x00000150       0x30 /x/libgcc.a(div.o)

.data           0x20000a64        0x4

.comment        0x00000000       0x2b
 .comment       0x00000000       0x2b /x/libISP583.a(ISP583.o)

.debug_info     0x00000000      0x500
 .debug_info    0x00000000      0x500 /x/libISP583.a(ISP583.o)

.debug_line     0x00000000      0x300
 .debug_line
                0x00000000      0x300 /x/libISP583.a(ISP583.o)
"""

SIZE = """/tmp/x.elf  :
section              size         addr
.init                  16            0
.highcode            1100   536870912
.text                5000          256
.data                  40   536872000
.bss                  300   536872100
.stack               2048   536868864
.comment               64            0
.riscv.attributes      60            0
.debug_info          9000            0
Total                17628
"""

READELF = """
Elf file type is EXEC (Executable file)
Entry point 0x0

Program Headers:
  Type           Offset   VirtAddr   PhysAddr   FileSiz MemSiz  Flg Align
  LOAD           0x001000 0x00000000 0x00000000 0x01000 0x01000 R E 0x1000
  LOAD           0x002000 0x20000000 0x00001000 0x00500 0x00500 RWE 0x1000
  LOAD           0x003000 0x20000500 0x00001500 0x00000 0x00200 RW  0x1000
"""


class Tests(unittest.TestCase):
    def test_library_bytes(self):
        # 0x426 one-line .highcode + 0x10 wrapped .text; the discarded 0x100, main.o, other.o and libgcc are not counted
        self.assertEqual(image_sizes.library_bytes(MAP), 0x436)

    def test_no_memory_map(self):
        with self.assertRaises(image_sizes.ImageSizesError) as cm:
            image_sizes.library_bytes(MAP.replace("Linker script and memory map", "Something else"))
        self.assertIn("memory map", str(cm.exception))

    def test_line_and_ram(self):
        r = image_sizes.analyse(SIZE, READELF, MAP)
        # .highcode counts in text; .stack, comment, attributes and debug are left out
        self.assertEqual((r["text"], r["data"], r["bss"]), (16 + 1100 + 5000, 40, 300))
        self.assertEqual(r["highcode"], 1100)
        self.assertEqual(r["stack"], 2048)
        self.assertEqual(r["ram"], 1100 + 40 + 300 + 2048)
        self.assertEqual(r["libisp"], 0x436)
        self.assertEqual(image_sizes.format_line("svf_ch582_mono", r),
                         "svf_ch582_mono: text 6116 data 40 bss 300 highcode 1100 libISP583 1078 stack 2048 ram 3488")

    def test_segment_past_flash(self):
        bad = READELF.replace("0x00001000 0x00500", "0x0006fe00 0x00500")
        with self.assertRaises(image_sizes.ImageSizesError) as cm:
            image_sizes.analyse(SIZE, bad, MAP)
        self.assertIn("0x70000", str(cm.exception))

    def test_empty_segment_ignored(self):
        ok = READELF.replace("0x20000500 0x00001500 0x00000", "0x20000500 0x20000500 0x00000")
        image_sizes.analyse(SIZE, ok, MAP)  # filesz 0: not loaded, so its address does not matter

    def test_segment_at_ram_address(self):
        bad = READELF.replace("0x20000000 0x00001000", "0x20000000 0x20000000")
        with self.assertRaises(image_sizes.ImageSizesError):
            image_sizes.analyse(SIZE, bad, MAP)

    def test_ram_too_big(self):
        big = SIZE.replace(".bss                  300", ".bss                40000")
        with self.assertRaises(image_sizes.ImageSizesError) as cm:
            image_sizes.analyse(big, READELF, MAP)
        self.assertIn("32768", str(cm.exception))

    def test_ram_over_budget(self):
        big = SIZE.replace(".bss                  300", ".bss                 6000")
        with self.assertRaises(image_sizes.ImageSizesError) as cm:
            image_sizes.analyse(big, READELF, MAP)
        self.assertIn("8192", str(cm.exception))

    def test_no_load_segment(self):
        with self.assertRaises(image_sizes.ImageSizesError):
            image_sizes.analyse(SIZE, "Program Headers:\n", MAP)


if __name__ == "__main__":
    unittest.main()
