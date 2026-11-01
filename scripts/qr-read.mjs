// Reads the text a QR code image carries, with no dependency: the deck's door QR is checked by what it encodes, not by
// what a file name or a caption says it encodes. It handles what the deck uses: a clean, axis-aligned PNG (8-bit grey,
// RGB or RGBA) of a version 1-4 code in byte mode, drawn with a quiet zone. The Reed-Solomon syndromes of every block must
// be zero, so a misread module fails loudly instead of returning wrong text.
import { inflateSync } from "node:zlib";

export function decodePng(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error("not a PNG");
  let off = 8, w, h, type;
  const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off), kind = buf.toString("latin1", off + 4, off + 8), data = buf.subarray(off + 8, off + 8 + len);
    if (kind === "IHDR") {
      [w, h, type] = [data.readUInt32BE(0), data.readUInt32BE(4), data[9]];
      if (data[8] !== 8 || data[12] !== 0) throw new Error("only 8-bit, non-interlaced PNGs");
    } else if (kind === "IDAT") idat.push(data);
    off += 12 + len;
  }
  const bpp = { 0: 1, 2: 3, 6: 4 }[type];
  if (!bpp) throw new Error(`PNG colour type ${type}`);
  const raw = inflateSync(Buffer.concat(idat)), stride = w * bpp, px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[y * (stride + 1)], line = y * (stride + 1) + 1, row = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? px[row + x - bpp] : 0, b = y ? px[row - stride + x] : 0, c = y && x >= bpp ? px[row - stride + x - bpp] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      px[row + x] = (raw[line + x] + [0, a, b, (a + b) >> 1, pa <= pb && pa <= pc ? a : pb <= pc ? b : c][filter]) & 255;
    }
  }
  return { w, h, bpp, px };
}

// [blocks, data codewords per block, EC codewords per block] for versions 1-4, by EC level.
const BLOCKS = {
  1: { L: [1, 19, 7], M: [1, 16, 10], Q: [1, 13, 13], H: [1, 9, 17] },
  2: { L: [1, 34, 10], M: [1, 28, 16], Q: [1, 22, 22], H: [1, 16, 28] },
  3: { L: [1, 55, 15], M: [1, 44, 26], Q: [2, 17, 18], H: [2, 13, 22] },
  4: { L: [1, 80, 20], M: [2, 32, 18], Q: [2, 24, 26], H: [4, 9, 16] },
};
const ALIGN = { 1: null, 2: 18, 3: 22, 4: 26 };
const EC_BITS = { 1: "L", 0: "M", 3: "Q", 2: "H" };
const MASKS = [
  (r, c) => (r + c) % 2 === 0, (r) => r % 2 === 0, (r, c) => c % 3 === 0, (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0, (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0, (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];
// GF(256) with the QR polynomial, for the syndrome check.
const EXP = new Array(512), LOG = new Array(256);
for (let i = 0, x = 1; i < 255; i++, x = (x << 1) ^ (x & 0x80 ? 0x11d : 0)) { EXP[i] = x; LOG[x] = i; }
for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
const mul = (a, b) => (a && b ? EXP[LOG[a] + LOG[b]] : 0);

export const readQr = (pngBytes) => readQrPixels(decodePng(pngBytes));
// The same, from decoded pixels ({ w, h, bpp, px }), so a test can damage a module and see the read fail.
export function readQrPixels({ w, h, bpp, px }) {
  const dark = (x, y) => { const i = (y * w + x) * bpp; return (bpp === 1 ? px[i] : (px[i] + px[i + 1] + px[i + 2]) / 3) < 128; };
  // The top-left finder: its first dark pixel, and its 7-module width.
  let x0 = -1, y0 = -1;
  outer: for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (dark(x, y)) { x0 = x; y0 = y; break outer; }
  if (x0 < 0) throw new Error("no dark pixel");
  let run = 0;
  while (x0 + run < w && dark(x0 + run, y0)) run++;
  const scale = run / 7;
  const N = Math.round((w - 2 * x0) / scale);
  const V = (N - 17) / 4;
  if (!Number.isInteger(scale) || !BLOCKS[V]) throw new Error(`unsupported code: ${N} modules at ${scale} px`);
  const m = (r, c) => dark(Math.floor(x0 + (c + 0.5) * scale), Math.floor(y0 + (r + 0.5) * scale));
  // Function patterns: finders with separators, timing, alignment, the dark module, the format areas.
  const fn = Array.from({ length: N }, () => new Array(N).fill(false));
  const box = (r0, c0, r1, c1) => { for (let r = Math.max(0, r0); r <= Math.min(N - 1, r1); r++) for (let c = Math.max(0, c0); c <= Math.min(N - 1, c1); c++) fn[r][c] = true; };
  box(0, 0, 8, 8); box(0, N - 8, 8, N - 1); box(N - 8, 0, N - 1, 8);
  for (let i = 0; i < N; i++) { fn[6][i] = true; fn[i][6] = true; }
  if (ALIGN[V]) box(ALIGN[V] - 2, ALIGN[V] - 2, ALIGN[V] + 2, ALIGN[V] + 2);
  fn[4 * V + 9][8] = true;
  // Format information beside the top-left finder, checked against all 32 valid BCH codewords.
  const fmtCoords = [[8, 0], [8, 1], [8, 2], [8, 3], [8, 4], [8, 5], [8, 7], [8, 8], [7, 8], [5, 8], [4, 8], [3, 8], [2, 8], [1, 8], [0, 8]];
  let raw = 0;
  for (const [r, c] of fmtCoords) raw = (raw << 1) | (m(r, c) ? 1 : 0);
  let format = null;
  for (let d = 0; d < 32; d++) {
    let rem = d << 10;
    for (let b = 14; b >= 10; b--) if (rem & (1 << b)) rem ^= 0x537 << (b - 10);
    if ((((d << 10) | rem) ^ 0x5412) === raw) format = { ec: EC_BITS[d >> 3], mask: d & 7 };
  }
  if (!format) throw new Error("format information does not read as a valid codeword");
  const mask = MASKS[format.mask];
  // Data bits in the zigzag order, unmasked.
  const bits = [];
  for (let col = N - 1, up = true; col > 0; col -= 2, up = !up) {
    if (col === 6) col--;
    for (let k = 0; k < N; k++) {
      const r = up ? N - 1 - k : k;
      for (const c of [col, col - 1]) if (!fn[r][c]) bits.push((m(r, c) ? 1 : 0) ^ (mask(r, c) ? 1 : 0));
    }
  }
  const [blocks, dataPer, ecPer] = BLOCKS[V][format.ec];
  const total = blocks * (dataPer + ecPer);
  const cw = [];
  for (let i = 0; i < total; i++) { let v = 0; for (let b = 0; b < 8; b++) v = (v << 1) | bits[i * 8 + b]; cw.push(v); }
  // De-interleave (every block the same size in versions 1-4) and require a zero syndrome for each block.
  const data = [];
  for (let b = 0; b < blocks; b++) {
    const block = [];
    for (let i = 0; i < dataPer; i++) block.push(cw[i * blocks + b]);
    for (let i = 0; i < ecPer; i++) block.push(cw[blocks * dataPer + i * blocks + b]);
    for (let s = 0; s < ecPer; s++) {
      let syn = 0;
      for (const v of block) syn = mul(syn, EXP[s]) ^ v;
      if (syn) throw new Error(`block ${b + 1}: Reed-Solomon syndrome ${s} is not zero`);
    }
    data.push(...block.slice(0, dataPer));
  }
  // Byte mode only: a 4-bit mode, an 8-bit count (versions 1-9), then the bytes.
  const dbits = data.flatMap((v) => [7, 6, 5, 4, 3, 2, 1, 0].map((b) => (v >> b) & 1));
  const take = (n, at) => dbits.slice(at, at + n).reduce((a, b) => (a << 1) | b, 0);
  if (take(4, 0) !== 4) throw new Error(`mode ${take(4, 0)}: only byte mode is read here`);
  const count = take(8, 4);
  const bytes = Buffer.from(Array.from({ length: count }, (_, i) => take(8, 12 + i * 8)));
  return { text: bytes.toString("utf8"), version: V, ec: format.ec, mask: format.mask, modules: N, scale };
}
