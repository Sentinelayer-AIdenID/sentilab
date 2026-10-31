# cad-04: Open CASCADE Technology (OCCT) V8_0_1: license, glTF writer, mesher

## Tags (GitHub API): V8_0_1, V8.0.1, V8_0_0 ... (body SHA-256 `55ca805c67b8f6c80560975a216d2e89d13960dad0c3f97436334f3987046083`)

## License

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/LICENSE_LGPL_21.txt

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:46Z
- HTTP status: 200
- SHA-256 of the downloaded body: `e237fa56668030e928551ddd60f05df5fe957f75eab874bbd017e085ed722e7c`
- Bytes: 26434

Lines 1,8 (verbatim, line-numbered):

```text
    1  		  GNU LESSER GENERAL PUBLIC LICENSE
    2  		       Version 2.1, February 1999
    3  
    4   Copyright (C) 1991, 1999 Free Software Foundation, Inc.
    5   51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
    6   Everyone is permitted to copy and distribute verbatim copies
    7   of this license document, but changing it is not allowed.
    8  
```

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/OCCT_LGPL_EXCEPTION.txt

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:46Z
- HTTP status: 200
- SHA-256 of the downloaded body: `04580a884ea6cea294402649ff7b5cbb167d47462d1340a4ed33e550db10a81b`
- Bytes: 663

Lines 1,12 (verbatim, line-numbered):

```text
    1  Open CASCADE exception (version 1.0) to GNU LGPL version 2.1.
    2  
    3  The object code (i.e. not a source) form of a "work that uses the Library"
    4  can incorporate material from a header file that is part of the Library.
    5  As a special exception to the GNU Lesser General Public License version 2.1,
    6  you may distribute such object code incorporating material from header files
    7  provided with the Open CASCADE Technology libraries (including code of CDL
    8  generic classes) under terms of your choice, provided that you give
    9  prominent notice in supporting documentation to this code that it makes use
   10  of or is based on facilities provided by the Open CASCADE Technology software.
```

## RWGltf_CafWriter.hxx

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/src/DataExchange/TKDEGLTF/RWGltf/RWGltf_CafWriter.hxx

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:02Z
- HTTP status: 200
- SHA-256 of the downloaded body: `a76a61cf3716b051862476b33207273bda1605a26eadbed338c96182f3bc11a6`
- Bytes: 28009

Lines 65,68 (verbatim, line-numbered):

```text
   65    //! Main constructor.
   66    //! @param[in] theFile      path to output glTF file
   67    //! @param[in] theIsBinary  flag to write into binary glTF format (.glb)
   68    Standard_EXPORT RWGltf_CafWriter(const TCollection_AsciiString& theFile, bool theIsBinary);
```

Lines 85,86 (verbatim, line-numbered):

```text
   85    //! Return flag to write into binary glTF format (.glb), specified within class constructor.
   86    bool IsBinary() const { return myIsBinary; }
```

Lines 95,105 (verbatim, line-numbered):

```text
   95    //! Return name format for exporting Nodes; RWMesh_NameFormat_InstanceOrProduct by default.
   96    RWMesh_NameFormat NodeNameFormat() const { return myNodeNameFormat; }
   97  
   98    //! Set name format for exporting Nodes.
   99    void SetNodeNameFormat(RWMesh_NameFormat theFormat) { myNodeNameFormat = theFormat; }
  100  
  101    //! Return name format for exporting Meshes; RWMesh_NameFormat_Product by default.
  102    RWMesh_NameFormat MeshNameFormat() const { return myMeshNameFormat; }
  103  
  104    //! Set name format for exporting Meshes.
  105    void SetMeshNameFormat(RWMesh_NameFormat theFormat) { myMeshNameFormat = theFormat; }
```

Lines 145,158 (verbatim, line-numbered):

```text
  145    //! Return TRUE if multithreaded optimizations are allowed; FALSE by default.
  146    bool ToParallel() const { return myToParallel; }
  147  
  148    //! Setup multithreaded execution.
  149    void SetParallel(bool theToParallel) { myToParallel = theToParallel; }
  150  
  151    //! Return Draco parameters
  152    const RWGltf_DracoParameters& CompressionParameters() const { return myDracoParameters; }
  153  
  154    //! Set Draco parameters
  155    void SetCompressionParameters(const RWGltf_DracoParameters& theDracoParameters)
  156    {
  157      myDracoParameters = theDracoParameters;
  158    }
```

## RWGltf_CafWriter.cxx

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/src/DataExchange/TKDEGLTF/RWGltf/RWGltf_CafWriter.cxx

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:13:10Z
- HTTP status: 200
- SHA-256 of the downloaded body: `17871de2456967f048428da53025d7ca06ab925f3ab7430877ccfa359f0631ec`
- Bytes: 93518

Lines 48,51 (verbatim, line-numbered):

```text
   48  #ifdef HAVE_DRACO
   49    #include <Standard_WarningsDisable.hxx>
   50    #include <draco/compression/encode.h>
   51    #include <Standard_WarningsRestore.hxx>
```

Lines 244,259 (verbatim, line-numbered):

```text
  244  RWGltf_CafWriter::RWGltf_CafWriter(const TCollection_AsciiString& theFile, bool theIsBinary)
  245      : myFile(theFile),
  246        myTrsfFormat(RWGltf_WriterTrsfFormat_Compact),
  247        myNodeNameFormat(RWMesh_NameFormat_InstanceOrProduct),
  248        myMeshNameFormat(RWMesh_NameFormat_Product),
  249        myIsBinary(theIsBinary),
  250        myIsForcedUVExport(false),
  251        myToEmbedTexturesInGlb(true),
  252        myToMergeFaces(false),
  253        myToSplitIndices16(false),
  254        myBinDataLen64(0),
  255        myToParallel(false)
  256  {
  257    myCSTrsf.SetOutputLengthUnit(1.0); // meters
  258    myCSTrsf.SetOutputCoordinateSystem(RWMesh_CoordinateSystem_glTF);
  259  
```

Lines 645,649 (verbatim, line-numbered):

```text
  645    double aLengthUnit = 1.;
  646    if (XCAFDoc_DocumentTool::GetLengthUnit(theDocument, aLengthUnit))
  647    {
  648      myCSTrsf.SetInputLengthUnit(aLengthUnit);
  649    }
```

Lines 1118,1118 (verbatim, line-numbered):

```text
 1118      OSD_Parallel::For(0, int(aMeshes.Size()), aFunctor, !myToParallel);
```

## BRepMesh_IncrementalMesh.hxx and IMeshTools_Parameters.hxx (determinism)

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/src/ModelingAlgorithms/TKMesh/BRepMesh/BRepMesh_IncrementalMesh.hxx

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:25Z
- HTTP status: 200
- SHA-256 of the downloaded body: `27d880c846f81f6a28061956045438e65dce7dcbb1b93c5aaacd9f5310e55f78`
- Bytes: 5487

Lines 32,45 (verbatim, line-numbered):

```text
   32    //! Constructor.
   33    //! Automatically calls method Perform.
   34    //! @param theShape shape to be meshed.
   35    //! @param theLinDeflection linear deflection.
   36    //! @param isRelative if TRUE deflection used for discretization of
   37    //! each edge will be <theLinDeflection> * <size of edge>. Deflection
   38    //! used for the faces will be the maximum deflection of their edges.
   39    //! @param theAngDeflection angular deflection.
   40    //! @param isInParallel if TRUE shape will be meshed in parallel.
   41    Standard_EXPORT BRepMesh_IncrementalMesh(const TopoDS_Shape& theShape,
   42                                             const double        theLinDeflection,
   43                                             const bool          isRelative       = false,
   44                                             const double        theAngDeflection = 0.5,
   45                                             const bool          isInParallel     = false);
```

### Source: https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V8_0_1/src/ModelingAlgorithms/TKMesh/IMeshTools/IMeshTools_Parameters.hxx

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:14:25Z
- HTTP status: 200
- SHA-256 of the downloaded body: `7252a2021e7b9d1fa17dc559c385d00bb2042fa798ff7a5c0805f541e5eb65e3`
- Bytes: 3485

Lines 30,36 (verbatim, line-numbered):

```text
   30          Deflection(0.001),
   31          AngleInterior(-1.0),
   32          DeflectionInterior(-1.0),
   33          MinSize(-1.0),
   34          InParallel(false),
   35          Relative(false),
   36          InternalVerticesMode(true),
```

Lines 68,71 (verbatim, line-numbered):

```text
   68  
   69    //! Switches on/off multi-thread computation
   70    bool InParallel;
   71  
```

## Reading (facts only)

- OCCT V8_0_1 is LGPL-2.1 with the Open CASCADE exception 1.0 (object code may incorporate header material under terms of your choice, with prominent notice).
- RWGltf_CafWriter(file, isBinary) writes .glb when isBinary is true; outputs metres (SetOutputLengthUnit(1.0)) in the glTF coordinate system; converts from the document length unit when the XDE document declares one; node names default to InstanceOrProduct and mesh names to Product (XCAF labels); Draco compression is available when built with Draco; parallel work is off by default (SetParallel).
- Determinism: neither BRepMesh_IncrementalMesh.hxx nor IMeshTools_Parameters.hxx states that output is deterministic; they expose only an in-parallel flag (default false). No primary-source determinism guarantee was found. Treat CAD-exported GLB bytes as not reproducible; compare geometry semantically.
