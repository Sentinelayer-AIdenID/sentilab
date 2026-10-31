# cad-05..12: cascadio, FreeCAD, pythonocc-core, trimesh, occt-import-js

Khronos glTF-Validator and glTF-Transform licenses are covered by the web-stack evidence (web-10-*).

## cad-05 cascadio 0.1.1 (STEP -> GLB)

- PyPI https://pypi.org/pypi/cascadio/json retrieved 2026-10-31T19:11:32Z, HTTP 200, SHA-256 `bf69f9165e88a6fbaab3231e9a8c817bd9edef273680990af922eae8f8410a64`; info.version 0.1.1; repository moved to github.com/trimesh/cascadio.
- GitHub API listing of LICENSE/ at 0.1.1: LICENSE-cascadio.md, LICENSE-opencascade.md, README.md (body SHA-256 `0a3b6b979ad6c513b50f1870c3c7f9edba91b3319d92e67dbc7acd1906057bdc`).

### Source: https://raw.githubusercontent.com/trimesh/cascadio/0.1.1/README.md

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:39Z
- HTTP status: 200
- SHA-256 of the downloaded body: `8103290c1328d290a44680b94e07da0570920488a8b11c6c0163d7b504741ae5`
- Bytes: 3442

Lines 1,7 (verbatim, line-numbered):

```text
    1  # cascadio
    2  
    3  A Python library which uses [OpenCASCADE](https://github.com/Open-Cascade-SAS/OCCT) to convert STEP files to a GLB file which can quickly be loaded by [trimesh](https://github.com/mikedh/trimesh) and other libraries.
    4  
    5  The primary effort here is build and packaging using the wonderful work done recently on [scikit-build-core](https://github.com/scikit-build/scikit-build-core) and [cibuildwheel](https://github.com/pypa/cibuildwheel). The goal is to produce wheels that don't require users to build OpenCASCADE themselves.
    6  
    7  This is *not* intended to be a full binding of OpenCASCADE like [OCP](https://github.com/CadQuery/OCP) or [PythonOCC](https://github.com/tpaviot/pythonocc-core). Rather it is intended to be an easy minimal way to load boundary representation files into a triangulated scene in Python. There are a few options for loading STEP geometry in the open-source ecosystem: GMSH, FreeCAD, etc. However nearly all of them use OpenCASCADE under the hood as it is pretty much the only open-source BREP kernel.
```

### Source: https://raw.githubusercontent.com/trimesh/cascadio/0.1.1/LICENSE/LICENSE-cascadio.md

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:49Z
- HTTP status: 200
- SHA-256 of the downloaded body: `0d550038f3829d9ee8a2886eb6f13a9989f34d6329925e1e425525340ade660c`
- Bytes: 1090

Lines 1,4 (verbatim, line-numbered):

```text
    1  The MIT License (MIT)
    2  
    3  Copyright (c) 2024 Michael Dawson-Haggerty
    4  
```

### Source: https://raw.githubusercontent.com/trimesh/cascadio/0.1.1/pyproject.toml

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:44Z
- HTTP status: 200
- SHA-256 of the downloaded body: `b78d3155dbf7a2761a3a6077bf8d2b392354435e77816737d6b9ce3133266074`
- Bytes: 3208

Lines 8,11 (verbatim, line-numbered):

```text
    8  requires-python = ">=3.9"
    9  authors = [{name = "Michael Dawson-Haggerty", email = "mikedh@kerfed.com"}]
   10  license = {file = "LICENSE/LICENSE-cascadio.md"}
   11  description = "Convert STEP files to GLB using OpenCASCADE"
```

Reading: cascadio's own code is MIT; its wheels bundle OCCT (it ships LICENSE-opencascade.md), so the OCCT LGPL-2.1 terms apply to that binary.

## cad-06 FreeCAD 1.1.4

- Latest release tag from https://api.github.com/repos/FreeCAD/FreeCAD/releases/latest : 1.1.4 (body SHA-256 `5b63b33163491455c0eef0f134a16ae95bfcc62c4d29ba010296676557aa2581`).

### Source: https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.1.4/LICENSE

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:04Z
- HTTP status: 200
- SHA-256 of the downloaded body: `7ffe1954587c77dfba1cf8eb9b2ea743671fa6e63f9e7a2f258119d42e14eefe`
- Bytes: 27030

Lines 1,3 (verbatim, line-numbered):

```text
    1                    GNU LESSER GENERAL PUBLIC LICENSE
    2                         Version 2.1, February 1999
    3  
```

- Official wiki https://wiki.freecad.org/Import_Export retrieved 2026-10-31T19:14:16Z, HTTP 200, SHA-256 `cf9a72eb1b327404be8cb61f615fc50c89a3266d4d01724b167f6054bf4fe41f`. Tag-stripped text around the entry (verbatim after stripping markup):
```text
adImage" title="Std ViewLoadImage">Std ViewLoadImage | | | no | | | | | *.glb | | | | GL Transmission Format | | | | Std Import | | | | Std Export | | | | | | *.gltf | | |
```

Reading: FreeCAD is LGPL-2.1 (license header) and lists *.glb / *.gltf under Std Import and Std Export.

## cad-07 pythonocc-core 8.0.1.2

- Latest release tag from https://api.github.com/repos/tpaviot/pythonocc-core/releases/latest : 8.0.1.2 (body SHA-256 `408e346c1618b049991ef599a12fdfdcd7ac12bd559945d4438338e5e8e4cc6f`).

### Source: https://raw.githubusercontent.com/tpaviot/pythonocc-core/8.0.1.2/LICENSE

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:15Z
- HTTP status: 200
- SHA-256 of the downloaded body: `f97bc4bb9b7ae8a653941073678b5c7775e8de44a01c3bcc21e7cdc148b90e61`
- Bytes: 7632

Lines 1,3 (verbatim, line-numbered):

```text
    1  GNU LESSER GENERAL PUBLIC LICENSE
    2                         Version 3, 29 June 2007
    3  
```

Reading: pythonocc-core is LGPL-3.0.

## cad-08 trimesh 5.2.0

- PyPI https://pypi.org/pypi/trimesh/json retrieved 2026-10-31T19:11:32Z, HTTP 200, SHA-256 `78659dcd17415a9bf953f5bc080bedc4591e2e40f888d23a6ff4e4537d5300f8`; info.version 5.2.0.

### Source: https://raw.githubusercontent.com/mikedh/trimesh/5.2.0/LICENSE.md

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:56Z
- HTTP status: 200
- SHA-256 of the downloaded body: `fe27b5ef8710676cc85255da28a32f394e2ef3f4ce47075a1c732a9ea1d7bd03`
- Bytes: 1090

Lines 1,3 (verbatim, line-numbered):

```text
    1  The MIT License (MIT)
    2  
    3  Copyright (c) 2023 Michael Dawson-Haggerty
```

### Source: https://raw.githubusercontent.com/mikedh/trimesh/5.2.0/trimesh/exchange/cascade.py

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:56Z
- HTTP status: 200
- SHA-256 of the downloaded body: `90e02940093aa6a1ff53277d17dfcf246bfa6d9d3adf6f40ef721a76f7d205f3`
- Bytes: 2097

Lines 11,30 (verbatim, line-numbered):

```text
   11  def load_step(
   12      file_obj: BinaryIO,
   13      file_type,
   14      tol_linear: Number | None = None,
   15      tol_angular: Number | None = None,
   16      tol_relative: bool | None = False,
   17      merge_primitives: bool = True,
   18      **kwargs,
   19  ) -> dict:
   20      """
   21      Use `cascadio` a packaged version of OpenCASCADE
   22      to load a STEP file using GLB as an intermediate.
   23  
   24      Parameters
   25      -----------
   26      file_obj
   27        STEP file to load.
   28      **kwargs
   29        Passed to `cascadio.step_to_glb`
   30  
```

Lines 66,74 (verbatim, line-numbered):

```text
   66  
   67  try:
   68      # wheels for most platforms: `pip install cascadio`
   69      import cascadio
   70  
   71      _cascade_loaders = {"stp": load_step, "step": load_step}
   72  except BaseException as E:
   73      wrapper = ExceptionWrapper(E)
   74      _cascade_loaders = {"stp": wrapper, "step": wrapper}
```

Reading: trimesh is MIT; STEP/STP loading goes through cascadio.step_to_glb (an optional install).

## cad-12 occt-import-js 0.0.23

- Latest tag from https://api.github.com/repos/kovacsv/occt-import-js/tags : 0.0.23 (body SHA-256 `ce9f749bbc481a28ddc7886b17780aca9c48c3286cefb4ca6b95821d62411b2b`).

### Source: https://raw.githubusercontent.com/kovacsv/occt-import-js/0.0.23/LICENSE.md

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:06Z
- HTTP status: 200
- SHA-256 of the downloaded body: `20c17d8b8c48a600800dfd14f95d5cb9ff47066a9641ddeab48dc54aec96e331`
- Bytes: 26526

Lines 1,3 (verbatim, line-numbered):

```text
    1                    GNU LESSER GENERAL PUBLIC LICENSE
    2                         Version 2.1, February 1999
    3  
```

### Source: https://raw.githubusercontent.com/kovacsv/occt-import-js/0.0.23/README.md

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:07Z
- HTTP status: 200
- SHA-256 of the downloaded body: `7bfa302f1974cd8b53f779ef93099ac21b0db9f65f3f3b2840ae26a710ac51f8`
- Bytes: 5581

Lines 3,3 (verbatim, line-numbered):

```text
    3  The [emscripten](https://emscripten.org) interface for [OpenCascade](https://www.opencascade.com) import functionalities. It runs entirely in the browser, and allows you to import brep, step and iges files and access the result in JSON format.
```

Lines 23,23 (verbatim, line-numbered):

```text
   23  You will need two files from the `dist` folder: `occt-import-js.js` and `occt-import-js.wasm`. The wasm file is loaded runtime by the js file. There are three public functions in the library:
```

Reading: occt-import-js is LGPL-2.1 and is an Emscripten WebAssembly build. In our pages it would need 'wasm-unsafe-eval' in script-src, which the CSP does not grant (see web-06).
