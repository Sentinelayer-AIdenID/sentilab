"""Convert a saved HTML file to plain text (stdlib only; never executes page content).

Usage: python -I html2txt.py <in.html> <out.txt>
Drops <script>, <style>, <noscript>, <svg>; inserts newlines at block tags;
collapses runs of blank lines. Output is UTF-8.
"""
import html
import re
import sys
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "svg", "template"}
BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "h1", "h2", "h3",
         "h4", "h5", "h6", "section", "article", "header", "footer", "dd", "dt", "figcaption",
         "caption", "blockquote", "pre", "hr"}


class Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def main(src, dst):
    raw = open(src, "rb").read()
    text = None
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    parser = Extract()
    parser.feed(text)
    out = html.unescape("".join(parser.parts))
    out = re.sub(r"[ \t\r\f\v]+", " ", out)
    out = re.sub(r"\n\s*\n+", "\n\n", out)
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out.strip() + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: html2txt.py <in.html> <out.txt>")
    main(sys.argv[1], sys.argv[2])
