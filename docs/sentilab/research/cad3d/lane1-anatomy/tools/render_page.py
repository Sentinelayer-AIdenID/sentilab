"""Render one PDF page to PNG with PyMuPDF (parsing only; no embedded JS/actions are run).

Usage: python -I render_page.py <in.pdf> <page_1based> <out.png> [zoom=2.0]
"""
import sys

import fitz  # PyMuPDF


def main():
    src, page, dst = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    zoom = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
    doc = fitz.open(src)
    pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(dst)
    print(f"{dst} {pix.width}x{pix.height} (page {page}/{doc.page_count})")


if __name__ == "__main__":
    main()
