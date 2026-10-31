# extra-01: OffscreenCanvas WebGL2 support (mdn/browser-compat-data, main)

Used for the optional design of running the renderer in a dedicated Worker (separate realm from the verifier).

### Source: https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/OffscreenCanvas.json

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:20:06Z
- HTTP status: 200
- SHA-256 of the downloaded body: `383555e750113a4a8f3d162f89eaeb6d338af4162f0ff248eb2ce4145625bb50`
- Bytes: 22011

Lines 391,429 (verbatim, line-numbered):

```text
  391          "webgl2_context": {
  392            "__compat": {
  393              "description": "`webgl2` context",
  394              "spec_url": "https://html.spec.whatwg.org/multipage/canvas.html#canvas-context-webgl2",
  395              "tags": [
  396                "web-features:offscreen-canvas"
  397              ],
  398              "support": {
  399                "chrome": {
  400                  "version_added": "69"
  401                },
  402                "chrome_android": "mirror",
  403                "deno": {
  404                  "version_added": false
  405                },
  406                "edge": "mirror",
  407                "firefox": {
  408                  "version_added": "105"
  409                },
  410                "firefox_android": "mirror",
  411                "oculus": "mirror",
  412                "opera": "mirror",
  413                "opera_android": "mirror",
  414                "safari": {
  415                  "version_added": "17"
  416                },
  417                "safari_ios": "mirror",
  418                "samsunginternet_android": "mirror",
  419                "webview_android": "mirror",
  420                "webview_ios": "mirror"
  421              },
  422              "status": {
  423                "experimental": false,
  424                "standard_track": true,
  425                "deprecated": false
  426              }
  427            }
  428          },
  429          "webgpu_context": {
```

Parsed summary (version_added; 'mirror' = mirrors the desktop engine's data):

```text
OffscreenCanvas: chrome=69; chrome_android=mirror; firefox=105; firefox_android=mirror; safari=16.4; safari_ios=mirror
getContext.webgl2_context: chrome=69; chrome_android=mirror; firefox=105; firefox_android=mirror; safari=17; safari_ios=mirror
```
