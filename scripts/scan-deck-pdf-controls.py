# Root's follow-up (13:30:15Z) on the PDF scan: runs controlled extractor responses through each scanner version's own
# scan(), with PyMuPDF, pypdf and pdftotext replaced by fakes that return exactly the controlled pages, status and XMP.
# Usage: python -I scripts/scan-deck-pdf-controls.py <V4.json> <scanner .py> <scratch dir> [<an older scanner .py>]
#   With an older scanner, its verdicts are shown beside the scanner's, for a before/after table.
import importlib.util, json, os, subprocess, sys, types

sys.stdout.reconfigure(encoding="utf-8")
v4_path, new_path, scratch = sys.argv[1:4]
old_path = sys.argv[4] if len(sys.argv) > 4 else None
os.makedirs(scratch, exist_ok=True)
dummy = os.path.join(scratch, "control.pdf")
open(dummy, "wb").write(b"%PDF-1.7 control bytes; the extractors are fakes\n")

CASE = {}  # the current control's responses


class Page:
    def __init__(s, t): s.t = t
    def get_text(s): return s.t
    def get_links(s): return []
    def annots(s): return []


class Doc:
    def __init__(s): s.pages = [Page(t) for t in CASE["fitz"]]
    page_count = property(lambda s: len(s.pages))
    def __iter__(s): return iter(s.pages)
    metadata = property(lambda s: {"title": "SentiLab deck"})
    def get_xml_metadata(s): return CASE.get("xmp", "")
    def get_toc(s): return []
    def xref_length(s): return 1


class PyPage:
    def __init__(s, t): s.t = t
    def extract_text(s): return s.t


class Reader:
    def __init__(s, _): s.pages = [PyPage(t) for t in CASE["pypdf"]]; s.metadata = {}


fitz = types.ModuleType("fitz"); fitz.open = lambda stream=None, filetype=None: Doc()
pypdf = types.ModuleType("pypdf"); pypdf.PdfReader = Reader
sys.modules["fitz"], sys.modules["pypdf"] = fitz, pypdf
real_run = subprocess.run
subprocess.run = lambda args, capture_output=True: types.SimpleNamespace(returncode=CASE["rc"], stdout=CASE["poppler"].encode("utf-8"), stderr=b"")


def load(path, name, argv):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, argv
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass  # the old script runs its CLI at import; with no PDFs it exits at once
    finally:
        sys.argv = saved
    return m


old = load(old_path, "scan_old", ["scan", v4_path, os.path.join(scratch, "old-import.jsonl")]) if old_path else None
new = load(new_path, "scan_new", ["scan", v4_path, os.path.join(scratch, "new-import.jsonl")])
pats = new.patterns(json.load(open(v4_path, encoding="utf-8"))["teams"]["unnamed"])
good = ["SentiLab page 1", "SentiLab page 2", "SentiLab page 3"]
ff = lambda pages: "".join(p + "\f" for p in pages)
xmp = lambda inner: f'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description>{inner}</rdf:Description></rdf:RDF></x:xmpmeta>'
cases = [
    ("clean: three extractors, every page", dict(fitz=good, pypdf=good, poppler=ff(good), rc=0), "CLEAN"),
    ("root 1: pypdf page 2 blank", dict(fitz=good, pypdf=[good[0], "", good[2]], poppler=ff(good), rc=0), "INCOMPLETE"),
    ("root 2: pypdf misses a page", dict(fitz=good, pypdf=good[:2], poppler=ff(good), rc=0), "INCOMPLETE"),
    ("root 3: Poppler misses a page (no final form feed)", dict(fitz=good, pypdf=good, poppler="SentiLab page 1\fSentiLab page 2", rc=0), "INCOMPLETE"),
    ("Poppler misses a page (final form feed)", dict(fitz=good, pypdf=good, poppler=ff(good[:2]), rc=0), "INCOMPLETE"),
    ("root 4: Poppler exits 99 with output", dict(fitz=good, pypdf=good, poppler=ff(good), rc=99), "INCOMPLETE"),
    ("name in the drawn text", dict(fitz=[good[0], "SentiLab page 2 Vortex", good[2]], pypdf=good, poppler=ff(good), rc=0), "FOUND"),
    ("root 5: XMP title, entity-encoded", dict(fitz=good, pypdf=good, poppler=ff(good), rc=0, xmp=xmp('<dc:title><rdf:Alt><rdf:li xml:lang="x-default">Vor&#116;ex</rdf:li></rdf:Alt></dc:title>')), "FOUND"),
    ("XMP attribute, entity-encoded", dict(fitz=good, pypdf=good, poppler=ff(good), rc=0, xmp=xmp('<rdf:li dc:title="Vor&#x74;ex"/>')), "FOUND"),
    ("XMP declares a DTD and an entity", dict(fitz=good, pypdf=good, poppler=ff(good), rc=0, xmp='<!DOCTYPE x [<!ENTITY t "x">]>' + xmp("&t;")), "INCOMPLETE"),
    ("XMP literal CDATA stays literal", dict(fitz=good, pypdf=good, poppler=ff(good), rc=0, xmp=xmp("<dc:title><![CDATA[Vor&#116;ex]]></dc:title>")), "CLEAN"),
]
wrong = {"old": 0, "new": 0}
for name, c, want in cases:
    CASE.clear(); CASE.update(c)
    got_old = old.scan(dummy)["verdict"] if old else want
    got_new = new.scan(dummy, pats)["verdict"]
    wrong["old"] += got_old != want
    wrong["new"] += got_new != want
    before = f"older {got_old:<10}{'' if got_old == want else ' WRONG'}  " if old else ""
    print(f"want {want:<10}  {before}this {got_new:<10}{'' if got_new == want else ' WRONG'}  {name}")
print((f"older: {wrong['old']} of {len(cases)} wrong; " if old else "") + f"this: {wrong['new']} of {len(cases)} wrong")
subprocess.run = real_run
sys.exit(1 if wrong["new"] else 0)
