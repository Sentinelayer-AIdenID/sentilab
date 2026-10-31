# Evidence index (lane 3: web 3D + live simulation)

Sealed evidence for ARCHITECTURE.md, PSEUDOCODE.md, ACCEPTANCE.md and RISKS.md. Never delete; add new files
instead. Hashes of every file are in `../SHA256SUMS`. Each third-party file records the source URL, the UTC
retrieval time, the HTTP status, the SHA-256 of the downloaded body and verbatim excerpts. Raw downloads were
kept outside the lane, in `H:/sl-temp/cad3d-lane3-scratch/`, and were treated as untrusted data (read, hashed and
compressed for size only; never executed).

## Our code (origin/main 46791be360555d0e24b4ad5f906abafb71f07118)

| File | Contents |
|---|---|
| repo-01-code-excerpts-46791be.md | Verbatim, line-numbered excerpts (with git blob ids) of every file:line cited in the lane documents: web/src (CSP, Worker), the Package and Lab views, temperature-label.mjs and its test, view-core and paging, the site-rule tests, licenses page, view-envelope contracts v0.5 and v0.6.2, the API (app/view.py, app/main.py), the producer (conductor.py), the solver wrapper (tap_oracle_worker.py, passive_interposer.py), requirements, the scope disposition, the scene CLI, the deck exporter's checks, CI |

## Offline CAD and conversion tools (gathered by this lane)

| File | Contents |
|---|---|
| cad-01-cadquery.md | CadQuery 2.8.0: Apache-2.0; Assembly.export formats incl. GLTF/GLB; glTF via OCCT RWGltf_CafWriter; tolerance defaults; Z-up to Y-up rotation |
| cad-02-build123d.md | build123d 0.13.0: Apache-2.0; export_gltf / export_step signatures; length unit set on the XDE document; STEP header timestamp; parallel meshing in Shape.mesh |
| cad-03-ocp.md | OCP 8.0.1.1: Apache-2.0; conda recipe pins OCCT 8.0.1 |
| cad-04-occt.md | OCCT V8_0_1: LGPL-2.1 + Open CASCADE exception 1.0; RWGltf_CafWriter (GLB, metres, glTF axes, name formats, Draco option, parallel flag); BRepMesh_IncrementalMesh parallel flag; no determinism statement found |
| cad-05-12-other-converters.md | cascadio 0.1.1 (MIT, bundles OCCT), FreeCAD 1.1.4 (LGPL-2.1; glb/gltf import and export), pythonocc-core 8.0.1.2 (LGPL-3.0), trimesh 5.2.0 (MIT; STEP via cascadio), occt-import-js 0.0.23 (LGPL-2.1, WebAssembly) |

## Extra checks (this lane)

| File | Contents |
|---|---|
| extra-01-bcd-offscreencanvas.md | mdn/browser-compat-data: OffscreenCanvas and its webgl2 context (Chrome 69, Firefox 105, Safari 17) |
| extra-02-site-rule-scans.md | Our public-names and control-byte rules run over three.js r187 `three.module.js` and `three.core.js` (one public-names hit in three.core.js) |
| extra-03-gltf-spec-units.md | Khronos glTF 2.0 specification section 3.4: right-handed, +Y up, linear distances in metres |
| extra-04-blender-license.md | Blender's official license page: GPL (GPL-2.0-or-later for its own code); why a Blender step is excluded |
| extra-05-field-size-and-colouring.md | Measured (synthetic data, our code): field artifact sizes; per-cell `heatColor()` vs a lookup table built from it (speed, ≤ 1/255 difference); parse and SHA-256 time |
| extra-06-regl-function-constructor.md | regl 2.1.1 `dist/regl.js` lines 6000-6017: commands compiled with `Function.apply` (refused by our CSP) |

## Browser stack (gathered by a research sub-agent; this file is their index)

| File | Contents |
|---|---|
| web-01-threejs-release-sizes-importmap.md | three@0.187.0 (MIT, integrity verified); no minified builds since r186; measured sizes; addons import bare 'three'; HTML spec: no external import maps |
| web-02-threejs-csp-grep.md | three.js r187 build and addons scanned for eval, Function constructor, blob:, WebAssembly, style injection (none, except GLTFLoader's blob: images) |
| web-03-threejs-webgl1-removal-webgpu-fallback.md | WebGL 1 removed in r163; WebGPURenderer falls back to a WebGL 2 backend; entry points |
| web-04-threejs-api-r187.md | InstancedMesh, DataTexture, clipping planes, CSS2DRenderer (CSSOM property writes only), renderer info, context loss, quoted at r187 |
| web-05-webgl2-float-texture-filtering.md | R32F not linearly filterable without OES_texture_float_linear; R16F filterable in core WebGL 2 |
| web-06-csp3.md | CSP3: worker-src fallback chain; 'self' never matches blob:; wasm-unsafe-eval; CSSOM vs style-src (inference, marked unverified); connect-src covers EventSource and WebSocket |
| web-07-sse-whatwg.md | WHATWG server-sent events: reconnection, retry:, Last-Event-ID; non-200 or wrong type fails the connection for good |
| web-08-alternatives.md | Babylon.js, PlayCanvas, OGL, regl, model-viewer: versions, licenses, measured sizes; model-viewer bundles three.js r183 |
| web-09-bcd-webgl2-webgpu.md | mdn/browser-compat-data: WebGL2 and WebGPU support by browser |
| web-10-gltf-transform-validator.md | @gltf-transform/core 4.5.1 (MIT) builds and writes GLB in Node; Khronos gltf-validator 2.0.0-dev.3.10 (Apache-2.0) |

Caveat from the sub-agent: its per-file gzip sizes come from `gzip -9 -c`, which stores the file name in the header, so each is `len(name) + 1` bytes larger than a server's gzip; brotli and concatenated sizes are unaffected.
