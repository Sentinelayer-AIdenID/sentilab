# extra-03: glTF 2.0 coordinate system and units (Khronos specification)

- URL: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html (section 3.4)
- Retrieved (UTC): 2026-10-31T19:39:37Z; HTTP 200; SHA-256 of body `cd57db699804df42021ddfc9b1a89fee58537b530348e62648cc0b8754604d22`; 1549946 bytes
- Extraction: the whole of section 3.4, from its h3 to the next h3, HTML tags stripped and the inline figure replaced by [figure] (Python, isolated mode). Verbatim otherwise.

```text
3.4. Coordinate System and Units glTF uses a right-handed coordinate system. glTF defines +Y as up, +Z as 
forward, and -X as right; the front of a glTF asset faces +Z. [figure] Figure 2. glTF Coordinate System 
Orientation The units for all linear distances are meters. All angles are in radians. Positive rotation is 
counterclockwise. Red, Green, and Blue primary colors use Recommendation ITU-R BT.709 chromaticity 
coordinates. Implementation Note Chromaticity coordinates define the interpretation of each primary color 
channel of the color model. In the context of a typical display, color primaries describe the color of the 
red, green, and blue phosphors or filters. Unless a wide color gamut output is explicitly used, client 
implementations usually do not need to convert colors. Future specification versions or extensions may allow 
other color primaries (such as P3).
```

Reading: glTF is right-handed with +Y up, and all linear distances are metres. The twin's GLB therefore stores metres with Y up, while our model works in millimetres with Z up (lower-left-mm); the writer converts both. CadQuery and build123d do the same conversion before calling OCCT's writer (cad-01, cad-02).
