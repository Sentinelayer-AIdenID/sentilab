# cad-02: build123d (export_gltf, export_step)

## PyPI metadata

- URL: https://pypi.org/pypi/build123d/json
- Retrieved (UTC): 2026-10-31T19:11:32Z; HTTP 200; SHA-256 `8c13e6be0a26237c646bc94663363c5f81abf31bcddabbfb8caa790c676f9e25`
- info.version: `0.13.0`
- info.license (first line): `Apache-2.0`
- license classifiers: ['License :: OSI Approved :: Apache Software License']
- earliest upload_time of this version: 2026-09-21T20:24:37.877067Z

## Tags (GitHub API): v0.13.0, v0.12.0, v0.11.1 (body SHA-256 `6f6881c6e40ecef049bb9938470c020a07936a3ac36d50fa7fdb452724bc0712`)

## LICENSE at v0.13.0

### Source: https://raw.githubusercontent.com/gumyr/build123d/v0.13.0/LICENSE

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:08Z
- HTTP status: 200
- SHA-256 of the downloaded body: `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`
- Bytes: 11358

Lines 1,4 (verbatim, line-numbered):

```text
    1  
    2                                   Apache License
    3                             Version 2.0, January 2004
    4                          http://www.apache.org/licenses/
```

## exporters3d.py at v0.13.0

### Source: https://raw.githubusercontent.com/gumyr/build123d/v0.13.0/src/build123d/exporters3d.py

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:08Z
- HTTP status: 200
- SHA-256 of the downloaded body: `739c15a20e3c335ee643ed1fd7537ea37b4cb1ac67a4c94974db4c3f4a14e4df`
- Bytes: 24693

Lines 51,51 (verbatim, line-numbered):

```text
   51  from OCP.RWGltf import RWGltf_CafWriter
```

Lines 110,113 (verbatim, line-numbered):

```text
  110      application.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)
  111      application.InitDocument(doc)
  112  
  113      XCAFDoc_DocumentTool.SetLengthUnit_s(doc, 1 / UNITS_PER_METER[unit])
```

Lines 260,267 (verbatim, line-numbered):

```text
  260  def export_gltf(
  261      to_export: Shape,
  262      file_path: PathLike | str | bytes,
  263      unit: Unit = Unit.MM,
  264      binary: bool = False,
  265      linear_deflection: float = 0.001,
  266      angular_deflection: float = 0.1,
  267  ) -> bool:
```

Lines 301,327 (verbatim, line-numbered):

```text
  301  
  302      # Map from OCCT's right-handed +Z up coordinate system to glTF's right-handed +Y
  303      # up coordinate system
  304      # https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html#coordinate-system-and-units
  305      original_location = to_export.location
  306      to_export.location *= Location((0, 0, 0), (1, 0, 0), -90)
  307  
  308      # Tessellate the object(s)
  309      node: Shape
  310      for node in PreOrderIter(to_export):
  311          if node.wrapped is not None:
  312              node.mesh(linear_deflection, angular_deflection)
  313  
  314      # Create the XCAF document
  315      doc: TDocStd_Document = _create_xde(to_export, unit, auto_naming=False)
  316  
  317      # Write the glTF file
  318      writer = RWGltf_CafWriter(
  319          theFile=TCollection_AsciiString(fsdecode(file_path)), theIsBinary=binary
  320      )
  321      writer.SetParallel(True)
  322      # Textures need UVs in the gltf export
  323      writer.SetForcedUVExport(True)
  324      index_map = IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString()
  325      progress = Message_ProgressRange()
  326  
  327      messenger = Message.DefaultMessenger_s()
```

Lines 364,371 (verbatim, line-numbered):

```text
  364  def export_step(
  365      to_export: Shape,
  366      file_path: PathLike | str | bytes | BytesIO | BinaryIO,
  367      unit: Unit = Unit.MM,
  368      write_pcurves: bool = True,
  369      precision_mode: PrecisionMode = PrecisionMode.AVERAGE,
  370      *,  # Too many positional arguments
  371      timestamp: str | datetime | None = None,
```

Lines 409,426 (verbatim, line-numbered):

```text
  409      header = APIHeaderSection_MakeHeader(writer.Writer().Model())
  410  
  411      if not header.IsDone():  # As in OCCT 7.9.x
  412          # Create an empty consistent header, i.e. IsDone() return True
  413          header = APIHeaderSection_MakeHeader(0)
  414          header.Apply(writer.Writer().Model())
  415  
  416      if to_export.label:
  417          header.SetName(TCollection_HAsciiString(to_export.label))
  418      if timestamp is not None:
  419          if isinstance(timestamp, datetime):
  420              header.SetTimeStamp(TCollection_HAsciiString(timestamp.isoformat()))
  421          else:
  422              header.SetTimeStamp(TCollection_HAsciiString(timestamp))
  423      # consider using e.g. the non *Value versions instead
  424      # header.SetAuthorValue(1, TCollection_HAsciiString("Volker"));
  425      # header.SetOrganizationValue(1, TCollection_HAsciiString("myCompanyName"));
  426      header.SetOriginatingSystem(TCollection_HAsciiString("build123d"))
```

## Shape.mesh at v0.13.0 (tessellation call)

### Source: https://raw.githubusercontent.com/gumyr/build123d/v0.13.0/src/build123d/topology/shape_core.py

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:30Z
- HTTP status: 200
- SHA-256 of the downloaded body: `0a9ba22f673a41ab539b59519ccbd9affaf4abfe03b3c401ae5d0d27039b2919`
- Bytes: 154042

Lines 1832,1832 (verbatim, line-numbered):

```text
 1832      def mesh(self, tolerance: float, angular_tolerance: float = 0.1):
```

Lines 1845,1848 (verbatim, line-numbered):

```text
 1845          if not BRepTools.Triangulation_s(self.wrapped, tolerance):
 1846              BRepMesh_IncrementalMesh(
 1847                  self.wrapped, tolerance, True, angular_tolerance, True
 1848              )
```

## Reading (facts only)

- build123d 0.13.0 is Apache-2.0. export_gltf(to_export, file_path, unit=Unit.MM, binary=False, linear_deflection=0.001, angular_deflection=0.1) writes through OCCT RWGltf_CafWriter with SetParallel(True).
- The XDE document gets SetLengthUnit(1/UNITS_PER_METER[unit]); with OCCT's writer reading the document length unit (see cad-04), lengths are converted to metres for glTF.
- export_step(to_export, file_path, unit=Unit.MM, write_pcurves=True, precision_mode=AVERAGE, *, timestamp=None): a fixed timestamp can be written into the STEP header.
- Shape.mesh() calls BRepMesh_IncrementalMesh(shape, tolerance, True, angular_tolerance, True): relative deflection and parallel meshing (parameter order in cad-04).
