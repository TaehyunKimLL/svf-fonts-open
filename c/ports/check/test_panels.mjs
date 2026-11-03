// test_panels.mjs - node --test c/ports/check/test_panels.mjs
// The panel models against fake i2c/spi/mcu objects that record the complete* calls the real peripherals would get.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Ssd1306I2C, Ssd1327I2C, St7789Spi, NackI2C, attachPanel } from './panels.mjs';

const I2CMode = { Write: 0, Read: 1 };
const GPIOPinState = { Low: 0, High: 1, Input: 2 };

function fakeI2c() {
  const calls = [];
  return {
    calls,
    completeStart: () => calls.push('start'),
    completeConnect: (ack) => calls.push('connect:' + ack),
    completeWrite: (ack) => calls.push('write:' + ack),
    setInterrupts: (mask) => calls.push('int:' + mask),
    completeStop: () => calls.push('stop'),
  };
}
// One bus transaction as the controller shows it: [repeated] START, address, bytes, optional STOP.
function txn(i2c, bytes, { addr = 0x3C, repeated = false, stop = true } = {}) {
  i2c.onStart(repeated);
  i2c.onConnect(addr, I2CMode.Write);
  for (const b of bytes) i2c.onWriteByte(b);
  if (stop) i2c.onStop();
}
const cmds = (i2c, list) => list.forEach((b) => txn(i2c, [0x00, b]));

function oledFill(i2c, frameBytes, rowLen) {
  for (let o = 0; o < frameBytes.length; o += rowLen) txn(i2c, [0x40, ...frameBytes.subarray(o, o + rowLen)]);
}
const pattern = (n, seed) => Uint8Array.from({ length: n }, (_, i) => (i * 7 + seed) & 0xff);

test('SSD1306: window, eight page writes, one show', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0x21, 0x00, 0x7f, 0x22, 0, 7]);
  const frame = pattern(1024, 1);
  oledFill(i2c, frame, 128);
  assert.deepEqual(Array.from(p.memory), Array.from(frame));
  assert.equal(p.memory.length, 1024);
  assert.equal(p.shows, 1);
  assert.equal(p.transfers, 8);
  assert.ok(i2c.calls.every((c) => c !== 'connect:false' && c !== 'write:false'));
});

test('SSD1306: a window that is not the whole panel (commands one byte a transaction)', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0x21, 10, 13, 0x22, 1, 2]);
  txn(i2c, [0x40, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.deepEqual(Array.from(p.memory.subarray(128 + 10, 128 + 14)), [9, 2, 3, 4]); // 9 wrapped to the start
  assert.deepEqual(Array.from(p.memory.subarray(256 + 10, 256 + 14)), [5, 6, 7, 8]);
  assert.equal(p.memory[10], 0);
  assert.equal(p.memory[384 + 10], 0, 'page 3 untouched');
  assert.equal(p.shows, 1);
});

test('SSD1306: another address is NACKed and nothing is written', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  txn(i2c, [0x40, 1, 2, 3], { addr: 0x3D });
  assert.ok(i2c.calls.includes('connect:false'));
  assert.equal(p.memory.every((b) => b === 0), true);
  assert.equal(p.transfers, 0);
});

// rp2040js 1.4.0 raises TX_ABRT but never TX_EMPTY after a NACK, so the pico-sdk's i2c_write_blocking would spin for ever:
// every NACK is followed by setInterrupts(TX_EMPTY = 1 << 4)
const TX_EMPTY = 1 << 4;
test('SSD1306: a NACK raises TX_EMPTY and is logged', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  txn(i2c, [0x40, 1], { addr: 0x3D });
  const k = i2c.calls.indexOf('connect:false');
  assert.ok(k >= 0 && i2c.calls[k + 1] === 'int:' + TX_EMPTY, i2c.calls.join());
  assert.ok(p.log.some((l) => l.includes('nack 0x3d')), p.log.join('\n'));
  i2c.calls.length = 0;
  txn(i2c, [0x00, 0xaf]); // an ACKed address raises nothing
  assert.ok(!i2c.calls.some((c) => c.startsWith('int:')));
});

test('OLED: no byte is accepted after an address NACK until the next START', () => {
  for (const Cls of [Ssd1306I2C, Ssd1327I2C]) {
    const i2c = fakeI2c();
    const p = new Cls(i2c, 0x3C, { I2CMode });
    i2c.onStart(false);
    i2c.onConnect(0x3D, I2CMode.Write);
    i2c.onWriteByte(0x40);
    i2c.onWriteByte(0x55);
    assert.deepEqual(i2c.calls.filter((c) => c.startsWith('write:')), ['write:false', 'write:false']);
    // a refused data byte raises TX_EMPTY as the address NACK does (the blocking write must return)
    assert.equal(i2c.calls.filter((c, i) => c === 'write:false' && i2c.calls[i + 1] === 'int:' + TX_EMPTY).length, 2);
    assert.equal(p.transfers, 0);
    assert.ok(p.memory.every((b) => b === 0));
    i2c.onStop();
    i2c.calls.length = 0;
    txn(i2c, [0x40, 0x55]); // the next transaction works
    assert.deepEqual(i2c.calls.filter((c) => c.startsWith('write:')), ['write:true', 'write:true']);
    assert.equal(p.memory[0], 0x55);
  }
});

test('NackI2C: NACKs every address, raises TX_EMPTY, refuses bytes', () => {
  const i2c = fakeI2c();
  new NackI2C(i2c, { I2CMode });
  txn(i2c, [0x40, 1, 2], { addr: 0x3C });
  assert.deepEqual(i2c.calls, ['start', 'connect:false', 'int:' + TX_EMPTY, ...Array(3).fill(['write:false', 'int:' + TX_EMPTY]).flat(), 'stop']);
});

test('SSD1306: a NACKed address with the wrong mode (read)', () => {
  const i2c = fakeI2c();
  new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  i2c.onStart(false);
  i2c.onConnect(0x3C, I2CMode.Read);
  assert.ok(i2c.calls.includes('int:' + TX_EMPTY));
});

test('a read of the right address is NACKed', () => {
  const i2c = fakeI2c();
  new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  i2c.onStart(false);
  i2c.onConnect(0x3C, I2CMode.Read);
  assert.ok(i2c.calls.includes('connect:false'));
});

test('SSD1306: a nostop split reads the first frame byte as a control byte', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0x21, 0x00, 0x7f, 0x22, 0, 7]);
  const frame = pattern(1024, 9);
  frame[0] = 0xa5; // not a valid control byte
  txn(i2c, [0x40], { stop: false });
  txn(i2c, frame.subarray(0, 128), { repeated: true });
  assert.notDeepEqual(Array.from(p.memory.subarray(0, 128)), Array.from(frame.subarray(0, 128)));
  assert.ok(p.log.some((l) => l.includes('control 0xa5')), p.log.join('\n'));
});

test('SSD1306: control byte 0xC0 / 0x80 alternate control and one byte', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  txn(i2c, [0x80, 0x21, 0x80, 0x05, 0x80, 0x09, 0xc0, 0x11, 0x40, 0x22]);
  assert.equal(p.memory[5], 0x11); // window columns 5..9: the data byte lands in column 5
  assert.equal(p.memory[6], 0x22);
});

test('SSD1306: unknown commands are logged, never thrown', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0xe3]);
  assert.ok(p.log.some((l) => l.includes('e3')));
});

test('SSD1306: a second fill is a second show', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0x21, 0x00, 0x7f, 0x22, 0, 7]);
  oledFill(i2c, pattern(1024, 3), 128);
  cmds(i2c, [0x21, 0x00, 0x7f, 0x22, 0, 7]);
  oledFill(i2c, pattern(1024, 4), 128);
  assert.equal(p.shows, 2);
  assert.equal(p.transfers, 16);
});

test('SSD1327: window, 32 chunks of 256, one show; a second fill is the second', () => {
  const i2c = fakeI2c();
  const p = new Ssd1327I2C(i2c, 0x3C, { I2CMode });
  assert.equal(p.memory.length, 8192);
  cmds(i2c, [0xa0, 0x51]);
  const fill = (seed) => {
    cmds(i2c, [0x15, 0x00, 0x3f, 0x75, 0x00, 0x7f]);
    const frame = pattern(8192, seed);
    oledFill(i2c, frame, 256);
    return frame;
  };
  const f1 = fill(5);
  assert.deepEqual(Array.from(p.memory), Array.from(f1));
  assert.equal(p.shows, 1);
  assert.equal(p.transfers, 32);
  assert.ok(p.log.some((l) => l.includes('a0 51')));
  const f2 = fill(6);
  assert.equal(p.shows, 2);
  assert.deepEqual(Array.from(p.memory), Array.from(f2));
});

test('SSD1327: a nostop split is a diff here too', () => {
  const i2c = fakeI2c();
  const p = new Ssd1327I2C(i2c, 0x3C, { I2CMode });
  cmds(i2c, [0x15, 0x00, 0x3f, 0x75, 0x00, 0x7f]);
  const frame = pattern(256, 2);
  frame[0] = 0x33;
  txn(i2c, [0x40], { stop: false });
  txn(i2c, frame, { repeated: true });
  assert.ok(p.log.some((l) => l.includes('control 0x33')));
});

function fakeSpi(cs = 0, dc = 0) {
  const calls = [];
  const spi = { calls, completeTransmit: (v) => calls.push(v) };
  const mcu = { spi: [spi], gpio: { 16: { value: dc }, 17: { value: cs } } };
  return { spi, mcu };
}
function send(f, bytes, dc, cs = GPIOPinState.Low) {
  f.mcu.gpio[16].value = dc ? GPIOPinState.High : GPIOPinState.Low;
  f.mcu.gpio[17].value = cs;
  for (const b of bytes) f.spi.onTransmit(b);
}

test('ST7789: window, RAMWR rows 16..39, one show', () => {
  const f = fakeSpi();
  const p = new St7789Spi(f.mcu, 0, { dc: 16, cs: 17 }, { GPIOPinState });
  assert.equal(p.memory.length, 240 * 240 * 2);
  send(f, [0x2a], 0); send(f, [0, 0, 0, 0xef], 1);
  send(f, [0x2b], 0); send(f, [0, 0x10, 0, 0x27], 1);
  send(f, [0x2c], 0);
  const data = pattern(11520, 3);
  send(f, data, 1);
  assert.equal(p.shows, 1);
  assert.equal(p.transfers, 1);
  assert.deepEqual(Array.from(p.memory.subarray(16 * 480, 40 * 480)), Array.from(data));
  assert.ok(p.memory.subarray(0, 16 * 480).every((b) => b === 0));
  assert.ok(p.memory.subarray(40 * 480).every((b) => b === 0));
  assert.equal(f.spi.calls.length, 1 + 4 + 1 + 4 + 1 + 11520); // every byte completed
});

test('ST7789: bytes with CS high are ignored (and still completed)', () => {
  const f = fakeSpi();
  const p = new St7789Spi(f.mcu, 0, { dc: 16, cs: 17 }, { GPIOPinState });
  send(f, [0x2c], 0, GPIOPinState.High);
  send(f, [1, 2, 3, 4], 1, GPIOPinState.High);
  assert.equal(p.shows, 0);
  assert.ok(p.memory.every((b) => b === 0));
  assert.equal(f.spi.calls.length, 5);
});

test('ST7789: the write wraps at the window end', () => {
  const f = fakeSpi();
  const p = new St7789Spi(f.mcu, 0, { dc: 16, cs: 17 }, { GPIOPinState });
  send(f, [0x2a], 0); send(f, [0, 2, 0, 3], 1); // columns 2..3
  send(f, [0x2b], 0); send(f, [0, 5, 0, 6], 1); // rows 5..6
  send(f, [0x2c], 0);
  send(f, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 1); // 4 pixels fill the window, the fifth wraps to (2, 5)
  const at = (x, y) => Array.from(p.memory.subarray((y * 240 + x) * 2, (y * 240 + x) * 2 + 2));
  assert.deepEqual(at(2, 5), [9, 10]);
  assert.deepEqual(at(3, 5), [3, 4]);
  assert.deepEqual(at(2, 6), [5, 6]);
  assert.deepEqual(at(3, 6), [7, 8]);
});

test('ST7789: each RAMWR is a show; unknown commands are logged', () => {
  const f = fakeSpi();
  const p = new St7789Spi(f.mcu, 0, { dc: 16, cs: 17 }, { GPIOPinState });
  send(f, [0x2c], 0); send(f, [1, 2], 1);
  send(f, [0x2c], 0); send(f, [3, 4], 1);
  send(f, [0xb2], 0); send(f, [0x0c], 1);
  send(f, [0x36], 0); send(f, [0x00], 1);
  assert.equal(p.shows, 2);
  assert.equal(p.transfers, 2);
  assert.ok(p.log.some((l) => l.includes('b2')));
  assert.ok(p.log.some((l) => l.includes('36')));
});

test('attachPanel picks the model of the profile', () => {
  const i2c = fakeI2c();
  const f = fakeSpi();
  const mcu = { i2c: [i2c], spi: f.spi ? [f.spi] : [], gpio: f.mcu.gpio, clock: { nanos: 5 } };
  const rp = { I2CMode, GPIOPinState };
  assert.ok(attachPanel('mono', mcu, rp) instanceof Ssd1306I2C);
  assert.ok(attachPanel('grey', mcu, rp) instanceof Ssd1327I2C);
  assert.ok(attachPanel('colour', mcu, rp) instanceof St7789Spi);
  // the colour profile's unused I2C bus NACKs everything (and raises TX_EMPTY)
  i2c.calls.length = 0;
  i2c.onStart(false);
  i2c.onConnect(0x3c, I2CMode.Write);
  assert.deepEqual(i2c.calls, ['start', 'connect:false', 'int:' + TX_EMPTY]);
  // the NACK is in the stub's log, stamped with the emulated clock
  const colour = attachPanel('colour', mcu, rp);
  i2c.onStart(false);
  i2c.onConnect(0x3c, I2CMode.Write);
  assert.ok(colour.others[0].log.some((l) => /^\[5 ns\] nack 0x3c write$/.test(l)), colour.others[0].log.join('|'));  assert.throws(() => attachPanel('nope', mcu, rp), /profile/);
});

test('ST7789: a window past the panel is clamped, never smeared into the next row', () => {
  const f = fakeSpi();
  const p = new St7789Spi(f.mcu, 0, { dc: 16, cs: 17 }, { GPIOPinState });
  send(f, [0x2a], 0); send(f, [0, 238, 0x01, 0xff], 1); // columns 238..511
  send(f, [0x2b], 0); send(f, [0, 0, 0, 1], 1);
  send(f, [0x2c], 0);
  send(f, [1, 2, 3, 4, 5, 6, 7, 8], 1);
  assert.deepEqual(Array.from(p.memory.subarray(238 * 2, 240 * 2)), [1, 2, 3, 4]);
  assert.deepEqual(Array.from(p.memory.subarray(480 + 476, 480 + 480)), [5, 6, 7, 8]); // the wrap is at column 239, then row 1 from column 238
  assert.ok(p.log.some((l) => l.includes('clamp')));
});

test('the log is capped: a "log truncated" line, then nothing more', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  p.logLimit = 100;
  for (let i = 0; i < 100; i++) cmds(i2c, [0xe3]);
  assert.ok(p.log.length < 20, 'log has ' + p.log.length + ' lines');
  assert.equal(p.log[p.log.length - 1], 'log truncated');
  assert.equal(p.log.filter((l) => l === 'log truncated').length, 1);
});

test('an incomplete command is noted when data arrives', () => {
  const i2c = fakeI2c();
  const p = new Ssd1306I2C(i2c, 0x3C, { I2CMode });
  txn(i2c, [0x00, 0x21]); // 0x21 wants two arguments
  txn(i2c, [0x40, 1]);
  assert.ok(p.log.some((l) => l.includes('incomplete')), p.log.join('\n'));
});
