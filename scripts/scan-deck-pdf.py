# Scans exported PDFs, bound to their exact bytes, for names that must not appear (root's P2, 12:55:54Z, and 13:30:15Z):
# the source guard (checkUnnamed) does not run on the exporter's output, so each PDF gets its own scan here, and the
# result is recorded next to the sha256 of the bytes that were scanned.
#
# Verdicts: CLEAN only when every extractor succeeded, returned every page, and found "SentiLab" on every page, the
# metadata was fully read, and no name was found anywhere. FOUND when a name is found on any surface. INCOMPLETE
# (refused) when any extraction failed, dropped a page, came back blind, or the metadata could not be fully read: that is
# neither clean nor proof of a name.
#
# Read from the one byte string whose sha256 is recorded: the text of every page by PyMuPDF, pypdf, and pdftotext (Poppler,
# on a hash-checked temporary copy; its exit status must be 0); the Info metadata; the XMP and any other XML stream, both
# raw and decoded once (character references and the five predefined entities, CDATA literal, attribute values too; a
# DTD or entity declaration is not expanded and makes the metadata INCOMPLETE); links, annotations, the outline; and every
# object (its dictionary with literal and hex strings decoded, and its stream where it can be decoded).
#
# Usage: python -I scripts/scan-deck-pdf.py <V4.json> <out.jsonl> <pdf>...
#   names: V4.json teams.unnamed, matched case-insensitively at word boundaries; "vortex" also as a bare substring.
import hashlib, io, json, os, re, subprocess, sys, tempfile


class Incomplete(Exception):
    pass


def patterns(names):
    return [(n, re.compile(r"\b" + re.escape(n) + r"\b", re.I)) for n in names] + [("vortex (substring)", re.compile("vortex", re.I))]


def hits(pats, text):
    return {n: len(p.findall(text)) for n, p in pats if p.search(text)}


_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def decode_xml(s):
    # One pass: numeric character references and the five predefined entities; nothing else is expanded.
    def one(m):
        if m.group(3):
            return _NAMED[m.group(3).lower()]
        cp = int(m.group(1)) if m.group(1) is not None else int(m.group(2), 16)
        return chr(cp) if 0 < cp <= 0x10FFFF else m.group(0)
    return re.sub(r"&(?:#(\d+)|#[xX]([0-9a-fA-F]+)|(amp|lt|gt|quot|apos));", one, s, flags=re.I)


def xml_readable(x):
    # An XML document as a reader gets it, with no parser: comments as written, character data decoded once with CDATA
    # literal, tag and attribute names, and attribute values decoded once. A DTD or an entity declaration is refused.
    if re.search(r"<!DOCTYPE|<!ENTITY", x, re.I):
        raise Incomplete("an XML stream declares a DTD or an entity; not expanded")
    comments = re.findall(r"<!--(.*?)-->", x, re.S)
    doc = re.sub(r"<!--.*?-->", " ", x, flags=re.S)
    text = "".join(p[9:-3] if p.startswith("<![CDATA[") else decode_xml(re.sub(r"<[^>]*>", " ", p)) for p in re.split(r"(<!\[CDATA\[.*?\]\]>)", doc, flags=re.S))
    markup = re.sub(r"<!\[CDATA\[.*?\]\]>", " ", doc, flags=re.S)
    tags = re.findall(r"<[A-Za-z?][^>\"']*(?:(?:\"[^\"]*\"|'[^']*')[^>\"']*)*>", markup)
    values = [decode_xml(a or b) for t in tags for a, b in re.findall(r"[\w:.-]+\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", t)]
    names = [re.sub(r"\"[^\"]*\"|'[^']*'", " ", t) for t in tags]
    return "\n".join([text, *comments, *names, *values])


def pdf_strings(src):
    # Literal strings with their escapes, and hex strings (UTF-16BE with a BOM, else Latin-1).
    out = []
    for m in re.finditer(r"\((?:\\.|[^\\()])*\)", src, re.S):
        s = m.group(0)[1:-1]
        s = re.sub(r"\\([0-7]{1,3})", lambda k: chr(int(k.group(1), 8)), s)
        s = re.sub(r"\\(.)", lambda k: {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}.get(k.group(1), k.group(1)), s)
        out.append(s)
    for m in re.finditer(r"<([0-9A-Fa-f\s]{4,})>", src):
        h = re.sub(r"\s", "", m.group(1))
        if len(h) % 2:
            h += "0"
        b = bytes.fromhex(h)
        out.append(b[2:].decode("utf-16-be", "replace") if b[:2] == b"\xfe\xff" else b.decode("latin-1"))
    return out


def poppler_pages(stdout):
    # pdftotext ends every page with a form feed; the text after the last one is not a page.
    t = stdout.decode("utf-8", "replace")
    return t.split("\f")[:-1] if "\f" in t else ([t] if t else [])


def verdict(page_count, extractions, surfaces, pats, incomplete=()):
    # extractions: {name: {"ok": bool, "status": str, "pages": [str]}}; surfaces: {name: text}; incomplete: [reason]
    problems = list(incomplete)
    if not page_count:
        problems.append("no pages")
    for name, e in extractions.items():
        if not e["ok"]:
            problems.append(f"{name}: {e['status']}")
        if len(e["pages"]) != page_count:
            problems.append(f"{name}: {len(e['pages'])} pages of {page_count}")
        blind = [i + 1 for i, t in enumerate(e["pages"]) if "SentiLab" not in t]
        if blind:
            problems.append(f"{name}: no SentiLab on page(s) {blind}")
    found = {k: h for k, v in surfaces.items() for h in [hits(pats, v)] if h}
    return ("FOUND" if found else "INCOMPLETE" if problems else "CLEAN"), found, problems


def scan(path, pats):
    import fitz, pypdf
    data = open(path, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    rec = {"file": os.path.basename(path), "sha256": sha, "bytes": len(data)}
    extractions, surfaces, incomplete = {}, {}, []
    doc = fitz.open(stream=data, filetype="pdf")
    page_count = doc.page_count
    try:
        extractions["pymupdf"] = {"ok": True, "status": "ok", "pages": [p.get_text() for p in doc]}
    except Exception as e:
        extractions["pymupdf"] = {"ok": False, "status": f"failed: {e}", "pages": []}
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        extractions["pypdf"] = {"ok": True, "status": "ok", "pages": [p.extract_text() or "" for p in reader.pages]}
        info = {f"info{k}": str(v) for k, v in (reader.metadata or {}).items()}
    except Exception as e:
        extractions["pypdf"] = {"ok": False, "status": f"failed: {e}", "pages": []}
        info = {}
        incomplete.append(f"pypdf metadata: {e}")
    with tempfile.TemporaryDirectory() as d:
        copy = os.path.join(d, "scan.pdf")
        open(copy, "wb").write(data)
        if hashlib.sha256(open(copy, "rb").read()).hexdigest() != sha:
            raise RuntimeError("temporary copy differs")
        r = subprocess.run(["pdftotext", "-q", copy, "-"], capture_output=True)
        extractions["pdftotext"] = {"ok": r.returncode == 0, "status": f"exit {r.returncode}", "pages": poppler_pages(r.stdout)}
    for k, e in extractions.items():
        surfaces[f"text:{k}"] = "\n".join(e["pages"])
    meta = dict(doc.metadata or {})
    meta.update(info)
    surfaces["metadata:info"] = json.dumps(meta, ensure_ascii=False)
    try:
        xmp = doc.get_xml_metadata() or ""
    except Exception as e:
        xmp = ""
        incomplete.append(f"XMP: {e}")
    surfaces["metadata:xmp"] = xmp
    try:
        surfaces["metadata:xmp decoded"] = xml_readable(xmp)
    except Incomplete as e:
        incomplete.append(f"XMP: {e}")
    links, annots = [], []
    for p in doc:
        links += [json.dumps(l, default=str) for l in p.get_links()]
        annots += [json.dumps(a.info, ensure_ascii=False) for a in (p.annots() or [])]
    surfaces["links"] = "\n".join(links)
    surfaces["annotations"] = "\n".join(annots)
    surfaces["outline"] = json.dumps(doc.get_toc(), ensure_ascii=False)
    objs, xmls = [], []
    for x in range(1, doc.xref_length()):
        try:
            src = doc.xref_object(x, compressed=False)
        except Exception as e:
            incomplete.append(f"object {x}: {e}")
            continue
        objs.append(src)
        objs += pdf_strings(src)
        if doc.xref_is_stream(x):
            try:
                raw = (doc.xref_stream(x) or b"").decode("latin-1")
            except Exception:
                continue
            objs.append(raw)
            objs += pdf_strings(raw)
            if re.search(r"<\?xpacket|<x:xmpmeta|<rdf:RDF", raw):
                try:
                    xmls.append(xml_readable(raw.encode("latin-1").decode("utf-8", "replace")))
                except Incomplete as e:
                    incomplete.append(f"object {x}: {e}")
    surfaces["objects"] = "\n".join(objs)
    surfaces["objects: XML decoded"] = "\n".join(xmls)
    v, found, problems = verdict(page_count, extractions, surfaces, pats, incomplete)
    if hashlib.sha256(open(path, "rb").read()).hexdigest() != sha:
        v, problems = "INCOMPLETE", problems + ["the file changed during the scan"]
    rec.update({"pages": page_count, "verdict": v, "found": found, "problems": problems,
                "extractors": {k: {"status": e["status"], "pages": len(e["pages"])} for k, e in extractions.items()},
                "surfaces": {k: len(s) for k, s in surfaces.items()}})
    return rec


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    v4_path, out_path, pdfs = sys.argv[1], sys.argv[2], sys.argv[3:]
    pats = patterns(json.load(open(v4_path, encoding="utf-8"))["teams"]["unnamed"])
    bad = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for p in pdfs:
            r = scan(p, pats)
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
            bad += r["verdict"] != "CLEAN"
            print(f"{r['verdict']}  {r['file']}  sha256 {r['sha256']}  {r['bytes']} bytes, {r['pages']} pages  extractors {r['extractors']}  found {r['found']}  problems {r['problems']}")
    sys.exit(1 if bad else 0)
