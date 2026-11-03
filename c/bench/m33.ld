/* m33.ld - c/bench/bench.c -DBENCH_M33 on QEMU mps2-an505: everything in the 4 MB SSRAM1 alias at 0x10000000 (where the
 * vector table is fetched from at reset: the board sets the CPU's initial secure vector table base to it), the stack at
 * its top. .data is loaded in place (the ELF is loaded by -kernel), so there is no copy; reset_handler zeroes .bss. */
MEMORY { RAM (rwx) : ORIGIN = 0x10000000, LENGTH = 4M }
SECTIONS {
  .text : { KEEP(*(.vectors)) *(.text*) *(.rodata*) } > RAM
  .data : { *(.data*) } > RAM
  .bss (NOLOAD) : {
    . = ALIGN(4);
    __bss_start__ = .;
    *(.bss*) *(COMMON)
    . = ALIGN(4);
    __bss_end__ = .;
  } > RAM
  end = .; /* libnosys' _sbrk: the heap starts here */
  __stack_top = ORIGIN(RAM) + LENGTH(RAM);
}
