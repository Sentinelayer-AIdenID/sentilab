# Checks an exported deck PDF, page by page, for a slide title whose ink (descenders included: the font's own glyph
# boxes, not the CSS line box) runs into a figure's box (aneta's read of final-2's page 3, 15:18Z: plain14's dark box
# clipped the title's g, y and commas). The figure boxes are the large filled shapes and images drawn below the title.
# Usage: python -I scripts/check-deck-pdf-layout.py <pdf>...   (exit 1 on any overlap)
import sys

import fitz

bad = 0
for path in sys.argv[1:]:
    doc = fitz.open(path)
    for n, page in enumerate(doc, 1):
        W, H = page.rect.width, page.rect.height
        spans = [s for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
        # The title: the topmost large text line under the header (the 60 or 72 px h1: 45 or 54 pt on a 1440 pt page),
        # with any line it wraps onto; a figure's own big numbers sit lower and are not the title.
        big = [s for s in spans if s["text"].strip() and s["size"] >= 0.03 * W and s["bbox"][1] < H * 0.2]
        if not big:
            continue
        first = min(big, key=lambda s: s["bbox"][1])
        title = [fitz.Rect(s["bbox"]) for s in big if abs(s["size"] - first["size"]) < 0.5 and s["bbox"][1] < first["bbox"][1] + 2.2 * first["size"]]
        ink = fitz.Rect(title[0])
        for r in title[1:]:
            ink |= r
        # Figure boxes: big filled shapes (a picture's background) and images, starting below the slide's header.
        boxes = [fitz.Rect(d["rect"]) for d in page.get_drawings() if d.get("fill") is not None and d["rect"].width > W * 0.3 and d["rect"].height > H * 0.3]
        boxes += [fitz.Rect(i["bbox"]) for i in page.get_image_info() if i["bbox"][2] - i["bbox"][0] > W * 0.1]
        hits = [b for b in boxes if b.y0 > H * 0.08 and (b & ink).height > 0.25 and (b & ink).width > 0.25]
        gap = min((b.y0 - ink.y1 for b in boxes if b.y0 > H * 0.08 and b.x0 < ink.x1 and b.x1 > ink.x0 and b.y0 >= ink.y1 - 0.25), default=None)
        if hits:
            bad += 1
            depth = max(ink.y1 - b.y0 for b in hits)
            print(f"OVERLAP  {path.split('/')[-1]} page {n}: the title's ink (bottom {ink.y1:.1f} pt) runs {depth:.1f} pt into a figure box starting at {min(b.y0 for b in hits):.1f} pt")
        else:
            print(f"clear    {path.split('/')[-1]} page {n}: title ink bottom {ink.y1:.1f} pt{'' if gap is None else f', nearest figure box {gap:.1f} pt below'}")
print("OVERLAP FOUND" if bad else "NO OVERLAP")
sys.exit(1 if bad else 0)
