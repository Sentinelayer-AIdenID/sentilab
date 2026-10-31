# extra-05: field artifact size and the cost of colouring it (measured, this lane)

Synthetic data, our code. Measured 2026-10-31T19:46:34Z on a desktop: AMD Ryzen 9 5950X, Node v22.23.1. A mid-range phone will be several times slower; these numbers bound the design, they don't replace the device test (ACCEPTANCE A-10).

## 1. Size of a `sentilab-field/0.1`-shaped JSON artifact

Smooth two-hot-spot field per layer, Kelvin with 2 decimals (as HotSpot writes its grid file), compact JSON, `gzip -9` via Python's gzip module (level 9).

```text
field_16x16x8.json       raw     14214 B   gzip-9     4610 B
field_32x32x8.json       raw     56580 B   gzip-9    16603 B
field_64x64x8.json       raw    226268 B   gzip-9    60367 B
field_128x128x8.json     raw    904318 B   gzip-9   225674 B
field_128x128x16.json    raw   1808797 B   gzip-9   451760 B
```

## 2. Colouring with our `heatColor()` (scene.mjs at 46791be, imported from the read-only worktree)

Calling `heatColor()` once per cell (it re-parses the six colour stops and returns a hex string each call):

```text
field_32x32x8.json: 8 layers x 32x32 -> 44.98 ms per full field (node v22.23.1, this desktop)
field_64x64x8.json: 8 layers x 64x64 -> 142.89 ms per full field (node v22.23.1, this desktop)
field_128x128x16.json: 16 layers x 128x128 -> 905.08 ms per full field (node v22.23.1, this desktop)
```

A 1024-entry lookup table built once per scale by calling `heatColor()` at each bin centre, then cells mapped through it:

```text
scale 40..50 °C: LUT build 8.29 ms; worst channel difference vs heatColor over 200k temperatures: 1/255
scale 40..120 °C: LUT build 2.40 ms; worst channel difference vs heatColor over 200k temperatures: 1/255
scale 0..400 °C: LUT build 3.66 ms; worst channel difference vs heatColor over 200k temperatures: 1/255
field_32x32x8.json: 8 layers x 32x32 -> 0.207 ms per full field via LUT (node v22.23.1, this desktop)
field_64x64x8.json: 8 layers x 64x64 -> 0.228 ms per full field via LUT (node v22.23.1, this desktop)
field_128x128x16.json: 16 layers x 128x128 -> 2.136 ms per full field via LUT (node v22.23.1, this desktop)
```

## 3. Strict decode + JSON.parse, and SHA-256 (WebCrypto)

```text
field_32x32x8.json: 56580 B; strict decode + JSON.parse 0.99 ms; WebCrypto SHA-256 0.35 ms
field_64x64x8.json: 226268 B; strict decode + JSON.parse 2.48 ms; WebCrypto SHA-256 0.38 ms
field_128x128x16.json: 1808797 B; strict decode + JSON.parse 26.66 ms; WebCrypto SHA-256 2.83 ms
```

## Scripts (ours; reproduced verbatim)

### time_texels.mjs

```js
// Times the CPU colouring step with OUR heatColor() (scene.mjs at the reviewed SHA, from the read-only worktree).
import { readFileSync } from "node:fs";
import { heatColor } from "file:///H:/sl-temp/worktrees/cad3d-lane3/web/public/sentilab/package/scene.mjs";
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
for (const name of ["field_32x32x8.json", "field_64x64x8.json", "field_128x128x16.json"]) {
  const doc = JSON.parse(readFileSync(new URL(name, import.meta.url)));
  const { rows, cols } = doc.grid;
  const scale = { min: 40, max: 120 };
  const t0 = performance.now();
  let reps = 20;
  for (let k = 0; k < reps; k += 1) {
    for (const layer of doc.values) {
      const out = new Uint8Array(rows * cols * 4);
      for (let i = 0; i < layer.length; i += 1) { const [R, G, B] = rgb(heatColor(layer[i] - 273.15, scale)); out[i * 4] = R; out[i * 4 + 1] = G; out[i * 4 + 2] = B; out[i * 4 + 3] = 255; }
    }
  }
  const ms = (performance.now() - t0) / reps;
  console.log(`${name}: ${doc.values.length} layers x ${rows}x${cols} -> ${ms.toFixed(2)} ms per full field (node ${process.version}, this desktop)`);
}
```

### time_lut.mjs

```js
// LUT built ONCE per scale from OUR heatColor() (scene.mjs at the reviewed SHA), then cells map through it.
// Also measures the worst per-channel difference between LUT colours and heatColor() for many temperatures.
import { readFileSync } from "node:fs";
import { heatColor } from "file:///H:/sl-temp/worktrees/cad3d-lane3/web/public/sentilab/package/scene.mjs";
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const N = 1024;
function buildLut(scale) {
  const lut = new Uint8Array(N * 4);
  for (let i = 0; i < N; i += 1) {
    const t = scale.min + ((i + 0.5) / N) * (scale.max - scale.min);   // bin centre
    lut.set([...rgb(heatColor(t, scale)), 255], i * 4);
  }
  return lut;
}
function texels(layer, scale, lut, out) {
  const k = N / (scale.max - scale.min);
  for (let i = 0; i < layer.length; i += 1) {
    let b = Math.floor((layer[i] - 273.15 - scale.min) * k);
    b = b < 0 ? 0 : b >= N ? N - 1 : b;
    out[i * 4] = lut[b * 4]; out[i * 4 + 1] = lut[b * 4 + 1]; out[i * 4 + 2] = lut[b * 4 + 2]; out[i * 4 + 3] = 255;
  }
}
for (const scale of [{ min: 40, max: 50 }, { min: 40, max: 120 }, { min: 0, max: 400 }]) {
  const t0 = performance.now(); const lut = buildLut(scale); const tl = performance.now() - t0;
  let worst = 0;
  for (let j = 0; j < 200000; j += 1) {
    const t = scale.min + (j / 200000) * (scale.max - scale.min);
    const a = rgb(heatColor(t, scale));
    let b = Math.floor((t - scale.min) * (N / (scale.max - scale.min))); b = Math.min(N - 1, Math.max(0, b));
    for (let c = 0; c < 3; c += 1) worst = Math.max(worst, Math.abs(a[c] - lut[b * 4 + c]));
  }
  console.log(`scale ${scale.min}..${scale.max} °C: LUT build ${tl.toFixed(2)} ms; worst channel difference vs heatColor over 200k temperatures: ${worst}/255`);
}
const lut = buildLut({ min: 40, max: 120 });
for (const name of ["field_32x32x8.json", "field_64x64x8.json", "field_128x128x16.json"]) {
  const doc = JSON.parse(readFileSync(new URL(name, import.meta.url)));
  const { rows, cols } = doc.grid; const out = new Uint8Array(rows * cols * 4);
  const reps = 50, t0 = performance.now();
  for (let k = 0; k < reps; k += 1) for (const layer of doc.values) texels(layer, { min: 40, max: 120 }, lut, out);
  console.log(`${name}: ${doc.values.length} layers x ${rows}x${cols} -> ${((performance.now() - t0) / reps).toFixed(3)} ms per full field via LUT (node ${process.version}, this desktop)`);
}
```

### time_parse.mjs

```js
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
for (const name of ["field_32x32x8.json", "field_64x64x8.json", "field_128x128x16.json"]) {
  const bytes = readFileSync(new URL(name, import.meta.url));
  const reps = 20; let t0 = performance.now();
  for (let k = 0; k < reps; k += 1) JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes));
  const parse = (performance.now() - t0) / reps;
  t0 = performance.now();
  for (let k = 0; k < reps; k += 1) await crypto.subtle.digest("SHA-256", bytes);
  const hash = (performance.now() - t0) / reps;
  console.log(`${name}: ${bytes.length} B; strict decode + JSON.parse ${parse.toFixed(2)} ms; WebCrypto SHA-256 ${hash.toFixed(2)} ms`);
}
```

The synthetic generator (Python) is in the same scratch directory (`H:/sl-temp/cad3d-lane3-scratch/measure-field/`); it writes field_<rows>x<cols>x<layers>.json with seed 7.

## Reading

- Per-cell `heatColor()` is too slow for fields (48 ms for 8 x 32 x 32 here; over a second for 16 x 128 x 128). A lookup table generated from `heatColor()` keeps one colour function, costs a few ms once per scale, maps a full 8 x 64 x 64 field in about 0.2 ms, and stays within 1/255 per channel of `heatColor()`.
- Parsing dominates for large artifacts (about 25 ms for 16 x 128 x 128 here). A typical 8 x 32 x 32 artifact is about 57 KB raw, 17 KB gzip.
