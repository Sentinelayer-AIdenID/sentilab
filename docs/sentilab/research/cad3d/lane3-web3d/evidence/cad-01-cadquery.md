# cad-01: CadQuery (glTF/GLB export path)

Question: latest version, license, Assembly export formats, which OCCT class writes glTF, tessellation parameters, binary GLB, names.

## PyPI metadata

- URL: https://pypi.org/pypi/cadquery/json
- Retrieved (UTC): 2026-10-31T19:11:31Z; HTTP 200; SHA-256 `381f96f748486f693c3d01aeba8a74691f63262a7e02e0292fc0fd8f8c8e27a3`
- info.version: `2.8.0`
- info.license (first line): `Apache Public License 2.0`
- license classifiers: ['License :: OSI Approved :: Apache Software License']
- earliest upload_time of this version: 2026-06-21T13:33:04.392203Z

## Release tag list (GitHub API)

- URL: https://api.github.com/repos/CadQuery/cadquery/tags?per_page=10 ; first entries: v2.8.0, v2.7.0, v2.6.1 (SHA-256 of body `0ee7e55c13e5a9705d1bc601470db35a3b762ecfb4de2e6f5487331ed91c41cd`)

## LICENSE at tag v2.8.0

### Source: https://raw.githubusercontent.com/CadQuery/cadquery/v2.8.0/LICENSE

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:11:51Z
- HTTP status: 200
- SHA-256 of the downloaded body: `7345486c76eb0160046e06c9c77797294979e15fc7cd1502d5c9cb650931bb84`
- Bytes: 11485

Lines 1,8 (verbatim, line-numbered):

```text
    1  CadQuery
    2  
    3  This library is free software; you can redistribute it and/or
    4  modify it under the terms of the Apache Public License, v 2.0
    5  
    6  
    7                                   Apache License
    8                             Version 2.0, January 2004
```

## Exporter source at tag v2.8.0

### Source: https://raw.githubusercontent.com/CadQuery/cadquery/v2.8.0/cadquery/occ_impl/exporters/assembly.py

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:11:52Z
- HTTP status: 200
- SHA-256 of the downloaded body: `a187e7fbad05ce8eb00e14df2739350464899f5a4375aeb1195367c378ec8a19`
- Bytes: 18171

Lines 43,43 (verbatim, line-numbered):

```text
   43  from OCP.RWGltf import RWGltf_CafWriter
```

Lines 440,477 (verbatim, line-numbered):

```text
  440  def exportGLTF(
  441      assy: AssemblyProtocol,
  442      path: str,
  443      binary: Optional[bool] = None,
  444      tolerance: float = 1e-3,
  445      angularTolerance: float = 0.1,
  446  ):
  447      """
  448      Export an assembly to a gltf file.
  449      """
  450  
  451      # If the caller specified the binary option, respect it
  452      if binary is None:
  453          # Handle the binary option for GLTF export based on file extension
  454          binary = True
  455          path_parts = path.split(".")
  456  
  457          # Binary will be the default if the user specified a non-standard file extension
  458          if len(path_parts) > 0 and path_parts[-1] == "gltf":
  459              binary = False
  460  
  461      # map from CadQuery's right-handed +Z up coordinate system to glTF's right-handed +Y up coordinate system
  462      # https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#coordinate-system-and-units
  463      orig_loc = assy.loc
  464      assy.loc *= Location((0, 0, 0), (1, 0, 0), -90)
  465  
  466      _, doc = toCAF(assy, True, True, tolerance, angularTolerance)
  467  
  468      writer = RWGltf_CafWriter(TCollection_AsciiString(path), binary)
  469      result = writer.Perform(
  470          doc, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange()
  471      )
  472  
  473      # restore coordinate system after exporting
  474      assy.loc = orig_loc
  475  
  476      return result
```

## Assembly.export dispatch at tag v2.8.0

### Source: https://raw.githubusercontent.com/CadQuery/cadquery/v2.8.0/cadquery/assembly.py

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:11:52Z
- HTTP status: 200
- SHA-256 of the downloaded body: `749f5ac94978cc99b17a4b232731adcede2dc71994fe398366ce89335086f5e6`
- Bytes: 27099

Lines 47,48 (verbatim, line-numbered):

```text
   47  ImportLiterals = Literal["STEP", "XML", "XBF"]
   48  ExportLiterals = Literal["STEP", "XML", "XBF", "GLTF", "VTKJS", "VRML", "STL"]
```

Lines 599,616 (verbatim, line-numbered):

```text
  599          if exportType is None:
  600              t = path.split(".")[-1].upper()
  601              if t in ("STEP", "XML", "XBF", "VRML", "VTKJS", "GLTF", "GLB", "STL"):
  602                  exportType = cast(ExportLiterals, t)
  603              else:
  604                  raise ValueError("Unknown extension, specify export type explicitly")
  605  
  606          if exportType == "STEP":
  607              exportAssembly(self, path, mode, unit, outputUnit, **kwargs)
  608          elif exportType == "XML":
  609              exportCAF(self, path, False)
  610          elif exportType == "XBF":
  611              exportCAF(self, path, True)
  612          elif exportType == "VRML":
  613              exportVRML(self, path, tolerance, angularTolerance)
  614          elif exportType == "GLTF" or exportType == "GLB":
  615              exportGLTF(self, path, None, tolerance, angularTolerance)
  616          elif exportType == "VTKJS":
```

## Reading (facts only)

- CadQuery 2.8.0 is Apache-2.0. Assembly.export accepts GLTF and GLB (and STEP, XML, XBF, VRML, VTKJS, STL).
- glTF export is OCCT's RWGltf_CafWriter via OCP; binary GLB is chosen by extension unless 'binary' is given; tolerance default 1e-3, angularTolerance default 0.1.
- CadQuery rotates the assembly -90 deg about X before writing (Z-up to glTF Y-up), then restores it.
