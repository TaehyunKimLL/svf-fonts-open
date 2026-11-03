// panels.mjs - models of the three Pico panels on rp2040js's I2C and SPI hooks (ESM). The rp2040js exports are passed
// in (I2CMode, GPIOPinState), so this module needs no import path.
//
// Every model keeps `memory` (the panel's RAM as the controller holds it), `shows` (complete fills of the window, or
// RAMWR commands), `transfers` (data writes) and `log` (one string a command or transfer the panel saw, prefixed by
// `stamp()`, which attachPanel points at the emulated clock). Unknown commands are logged, never thrown, so a
// datasheet mistake shows as a diff, not as a crash.

const LOG_LIMIT = 1024 * 1024; // bytes of log a model keeps; then one "log truncated" line

// rp2040js 1.4.0 raises TX_ABRT on a NACK but never TX_EMPTY (abort() empties the FIFO; TX_EMPTY is only raised after a
// FIFO entry is pulled), so the pico-sdk's i2c_write_blocking, which waits for TX_EMPTY after every byte, spins for
// ever. On hardware the flushed FIFO raises TX_EMPTY and the call returns an error. Every NACK therefore raises it.
const TX_EMPTY = 1 << 4;
function nack(i2c) {
  i2c.setInterrupts(TX_EMPTY);
}

class Base {
  constructor() {
    this.shows = 0;
    this.transfers = 0;
    this.log = [];
    this.logLimit = LOG_LIMIT;
    this.logBytes = 0;
    this.stamp = () => '';
  }
  note(msg) {
    if (this.logBytes < 0) return; // already truncated
    const line = this.stamp() + msg;
    this.logBytes += line.length + 1;
    if (this.logBytes > this.logLimit) {
      this.log.push('log truncated');
      this.logBytes = -1;
      return;
    }
    this.log.push(line);
  }
}

const hex = (v) => v.toString(16).padStart(2, '0');

// The common part of the two OLED controllers: the I2C framing. The first byte after every address phase (repeated
// START included) is a control byte: bit 7 (Co) set means one byte follows and then another control byte, clear means
// everything up to the next address phase is command (bit 6 clear) or data (bit 6 set). Bits 5..0 must be zero.
class OledI2C extends Base {
  constructor(i2c, addr, { I2CMode }, argCounts) {
    super();
    this.i2c = i2c;
    this.argCounts = argCounts;
    this.expectControl = true;
    this.control = 0;
    this.cmdq = []; // a command may span transactions: the drivers send every command byte as its own [0x00, byte] write
    this.run = 0; // data bytes of the transaction so far
    this.acked = false;
    i2c.onStart = () => {
      this.flush();
      this.acked = false; // no byte is accepted until the next address phase is ACKed
      i2c.completeStart();
    };
    i2c.onConnect = (address, mode) => {
      this.flush();
      this.expectControl = true;
      this.acked = address === addr && mode === I2CMode.Write;
      i2c.completeConnect(this.acked);
      if (!this.acked) {
        this.note('nack 0x' + hex(address) + (mode === I2CMode.Write ? ' write' : ' read'));
        nack(i2c);
      }
    };
    i2c.onWriteByte = (b) => {
      // a NACKed transaction never reaches the controller logic, and its bytes are NACKed
      if (this.acked) this.write(b);
      i2c.completeWrite(this.acked);
      if (!this.acked) nack(i2c); // a refused byte too: the blocking write waits for TX_EMPTY
    };
    i2c.onStop = () => {
      this.flush();
      this.acked = false;
      i2c.completeStop();
    };
  }
  flush() {
    if (this.run > 0) {
      this.transfers++;
      this.note('data ' + this.run + ' bytes');
    }
    this.run = 0;
  }
  write(b) {
    if (this.expectControl) {
      this.control = b;
      this.expectControl = false;
      if (b & 0x3f) this.note('control 0x' + hex(b));
      return;
    }
    if (this.control & 0x40) {
      if (this.cmdq.length) {
        this.note('cmd ' + this.cmdq.map(hex).join(' ') + ' incomplete (data follows)');
        this.cmdq = [];
      }
      this.data(b);
      this.run++;
    } else {
      this.command(b);
    }
    if (this.control & 0x80) {
      this.flush();
      this.expectControl = true;
    }
  }
  command(b) {
    this.cmdq.push(b);
    const need = this.argCounts[this.cmdq[0]] || 1;
    if (this.cmdq.length < need) return;
    const q = this.cmdq;
    this.cmdq = [];
    this.note('cmd ' + q.map(hex).join(' '));
    this.apply(q);
  }
}

// SSD1306 128 x 64: 1,024 bytes of pages (byte = 8 rows of one column, page = y >> 3, bit = y & 7), horizontal
// addressing in the window set by 0x21 (columns) and 0x22 (pages).
export class Ssd1306I2C extends OledI2C {
  constructor(i2c, addr, rp) {
    super(i2c, addr, rp, {
      0x20: 2, 0x21: 3, 0x22: 3, 0x81: 2, 0xa8: 2, 0xd3: 2, 0xd5: 2, 0xd9: 2, 0xda: 2, 0xdb: 2, 0x8d: 2,
    });
    this.memory = new Uint8Array(1024);
    this.c0 = 0; this.c1 = 127; this.p0 = 0; this.p1 = 7;
    this.cx = 0; this.cy = 0;
  }
  apply(q) {
    if (q[0] === 0x21) { this.c0 = q[1] & 127; this.c1 = q[2] & 127; this.cx = this.c0; }
    else if (q[0] === 0x22) { this.p0 = q[1] & 7; this.p1 = q[2] & 7; this.cy = this.p0; }
  }
  data(b) {
    this.memory[this.cy * 128 + this.cx] = b;
    if (++this.cx > this.c1) {
      this.cx = this.c0;
      if (++this.cy > this.p1) {
        this.cy = this.p0;
        this.shows++;
      }
    }
  }
}

// SSD1327 128 x 128, 4 bits a pixel: 8,192 bytes, 64 a row (two pixels a byte), window set by 0x15 (columns of two
// pixels) and 0x75 (rows). The remap byte (0xA0) is logged: the model does not mirror, the reference is in the
// panel's native order.
export class Ssd1327I2C extends OledI2C {
  constructor(i2c, addr, rp) {
    super(i2c, addr, rp, {
      0x15: 3, 0x75: 3, 0xa0: 2, 0xa8: 2, 0xa1: 2, 0xa2: 2, 0x81: 2, 0xb1: 2, 0xbc: 2, 0xb3: 2, 0xbe: 2, 0xb6: 2,
      0xd5: 2, 0xab: 2,
    });
    this.memory = new Uint8Array(8192);
    this.c0 = 0; this.c1 = 63; this.r0 = 0; this.r1 = 127;
    this.cx = 0; this.cy = 0;
  }
  apply(q) {
    if (q[0] === 0x15) { this.c0 = q[1] & 63; this.c1 = q[2] & 63; this.cx = this.c0; }
    else if (q[0] === 0x75) { this.r0 = q[1] & 127; this.r1 = q[2] & 127; this.cy = this.r0; }
  }
  data(b) {
    this.memory[this.cy * 64 + this.cx] = b;
    if (++this.cx > this.c1) {
      this.cx = this.c0;
      if (++this.cy > this.r1) {
        this.cy = this.r0;
        this.shows++;
      }
    }
  }
}

// ST7789 240 x 240 on SPI: bytes count while CS (an SIO output, readable from mcu.gpio) is low; DC low is a command
// byte, high a parameter or pixel byte. 0x2A / 0x2B take four parameters (big-endian halves); 0x2C starts pixel data
// at the window's origin, wrapping at the window's end; the bytes are stored as received (big-endian RGB565).
export class St7789Spi extends Base {
  constructor(mcu, spiIndex, { dc, cs }, { GPIOPinState }) {
    super();
    const spi = mcu.spi[spiIndex];
    this.memory = new Uint8Array(240 * 240 * 2);
    this.cmd = -1;
    this.params = [];
    this.writing = false;
    this.fresh = false;
    this.c0 = 0; this.c1 = 239; this.r0 = 0; this.r1 = 239;
    this.x = 0; this.y = 0; this.hi = true;
    spi.onTransmit = (v) => {
      if (mcu.gpio[cs].value === GPIOPinState.Low) {
        if (mcu.gpio[dc].value === GPIOPinState.High) this.dataByte(v);
        else this.commandByte(v);
      }
      spi.completeTransmit(0);
    };
  }
  commandByte(v) {
    this.cmd = v;
    this.params = [];
    this.writing = v === 0x2c;
    this.fresh = this.writing;
    if (this.writing) {
      this.x = this.c0;
      this.y = this.r0;
      this.hi = true;
      this.shows++;
      this.note('cmd 2c window x ' + this.c0 + '..' + this.c1 + ' y ' + this.r0 + '..' + this.r1);
    } else if (v !== 0x2a && v !== 0x2b) {
      this.note('cmd ' + hex(v));
    }
  }
  dataByte(v) {
    if (!this.writing) {
      if (this.params.length < 8) this.params.push(v); // the parameters of one command: nothing needs more (the log is capped too)
      if (this.params.length === 4 && (this.cmd === 0x2a || this.cmd === 0x2b)) {
        const lo = (this.params[0] << 8) | this.params[1], hi = (this.params[2] << 8) | this.params[3];
        const a = Math.min(lo, 239), b = Math.min(hi, 239);
        if (this.cmd === 0x2a) { this.c0 = a; this.c1 = b; }
        else { this.r0 = a; this.r1 = b; }
        this.note('cmd ' + hex(this.cmd) + ' ' + lo + '..' + hi + (a !== lo || b !== hi ? ' clamped to the panel: ' + a + '..' + b : ''));
      } else if (this.cmd !== 0x2a && this.cmd !== 0x2b) {
        this.note('param ' + hex(this.cmd) + ' ' + hex(v));
      }
      return;
    }
    if (this.fresh) {
      this.fresh = false;
      this.transfers++;
    }
    const o = (this.y * 240 + this.x) * 2 + (this.hi ? 0 : 1);
    if (o < this.memory.length) this.memory[o] = v;
    if (!this.hi) {
      if (++this.x > this.c1) {
        this.x = this.c0;
        if (++this.y > this.r1) this.y = this.r0;
      }
    }
    this.hi = !this.hi;
  }
}

// Everything that is not the profile's panel on an I2C bus: it NACKs every address (and, with the TX_EMPTY work-around
// above, lets the firmware's blocking write return), so a firmware built for another profile fails on the panel's show
// count instead of hanging.
export class NackI2C extends Base {
  constructor(i2c, { I2CMode }) {
    super();
    i2c.onStart = () => i2c.completeStart();
    i2c.onConnect = (address, mode) => {
      i2c.completeConnect(false);
      this.note('nack 0x' + hex(address) + (mode === I2CMode.Write ? ' write' : ' read'));
      nack(i2c);
    };
    i2c.onWriteByte = () => {
      i2c.completeWrite(false);
      nack(i2c);
    };
    i2c.onStop = () => i2c.completeStop();
  }
}

export function attachPanel(profile, mcu, rp) {
  let p;
  if (profile === 'colour') p = new St7789Spi(mcu, 0, { dc: 16, cs: 17 }, rp);
  else if (profile === 'grey') p = new Ssd1327I2C(mcu.i2c[0], 0x3c, rp);
  else if (profile === 'mono') p = new Ssd1306I2C(mcu.i2c[0], 0x3c, rp);
  else throw new Error('attachPanel: unknown profile ' + profile);
  // the I2C buses the panel is not on NACK (a firmware of another profile fails on its show count, fast)
  p.others = [];
  if (profile === 'colour') for (const i2c of mcu.i2c || []) p.others.push(new NackI2C(i2c, rp));
  if (mcu.clock) for (const m of [p, ...p.others]) m.stamp = () => '[' + mcu.clock.nanos + ' ns] ';
  return p;
}
