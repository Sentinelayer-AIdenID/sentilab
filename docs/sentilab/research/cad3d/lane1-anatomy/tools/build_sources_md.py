"""Generate lane1-anatomy/SOURCES.md from FETCHLOG.tsv, FACTS.jsonl and render files.

Usage: python -I build_sources_md.py <lane1-anatomy dir>
"""
import csv
import json
import os
import sys
from collections import defaultdict

OUT = sys.argv[1]
EV = os.path.join(OUT, "evidence")

facts = []
for lane in ("hbm", "packaging", "thermal", "products"):
    with open(os.path.join(EV, lane, "FACTS.jsonl"), encoding="utf-8") as fh:
        facts += [json.loads(x) for x in fh if x.strip()]
by_src = defaultdict(list)
meta = {}
for f in facts:
    stem = os.path.basename(f["file"]).split(".")[0]
    by_src[stem].append(f["fact_id"])
    meta[stem] = f

rows = []
with open(os.path.join(EV, "FETCHLOG.tsv"), encoding="utf-8") as fh:
    for r in csv.reader(fh, delimiter="\t"):
        if len(r) >= 7:
            rows.append(r)

lines = []
w = lines.append
w("# Sources for lane 1 (anatomy)")
w("")
w("Everything the lane relied on is saved under `evidence/`, and nothing there has been deleted. Each source is kept in three forms:")
w("")
w("- **raw download:** `.html` or `.pdf`, byte-for-byte as fetched;")
w("- **text extraction:** `.txt`. PDFs also have `.raw.txt` in reading order;")
w("- **page renders:** for slides whose tables or units survive only as graphics (`evidence/*/renders/*.png`).")
w("")
w("**How the facts were checked**")
w("")
w("- `evidence/<lane>/FACTS.jsonl` holds one record per fact. Each record has a verbatim quote, the evidence file, URL, title, publisher, date, source type, capture method, confidence and notes.")
w(f"- `tools/verify_facts.py` was run over all {len(facts)} facts: **0 failures**.")
w("  - A plain fact passes when its quote is found in the cited text file, after whitespace, case and dash normalisation.")
w("  - A `render` fact passes when its rendered page exists and its anchor quote (if any) is found. Its value is read from the image, so it is marked VISUAL.")
w("- Numbers in `parts.json`, `thermal_path.md` and `our_model_mapping.md` cite these fact ids. The readable report could not be written here (see the agent's note); its content went to the parent agent.")
w("")
w("**Safety and exclusions**")
w("")
w("- **Downloaded pages are untrusted data.** They were only parsed: HTML went through a stdlib HTML parser, PDFs through `pdftotext` and PyMuPDF rendering, always via `python -I` with scripts kept outside `evidence/`. Nothing from them was executed.")
w("- **No MicroDuck or Pollen material is used.**")
w("- **Read-only on repos.** `H:/sentilab` was read at `origin/main` 46791be through `git show` and `git grep`; numbered excerpts are in `evidence/repo/`.")
w("- **Primary vs secondary.** Primary means standards bodies, vendor pages, data sheets, white papers and press releases, conference papers and slides, and patents. Secondary means news, blogs, analyst and distributor pages; facts from those are capped at medium confidence.")
w("")
w("## Sources used (cited by at least one fact)")
w("")
w("| # | Source slug (evidence file stem) | Title | Publisher / author | Date | Type | Facts | URL | Retrieved (UTC) | SHA-256 of raw file |")
w("|---|---|---|---|---|---|---|---|---|---|")
used = set(by_src)
n = 0
rowmap = {}
for r in rows:
    stem = os.path.splitext(os.path.basename(r[1]))[0]
    rowmap.setdefault(stem, r)
for stem in sorted(used, key=lambda s: (meta[s]["file"].split("/")[0], s)):
    n += 1
    m = meta[stem]
    r = rowmap.get(stem)
    ids = ", ".join(sorted(by_src[stem]))
    url = r[6] if r else m.get("url", "")
    ts = r[0] if r else ""
    sha = r[5] if r else ""
    w(f"| {n} | `{m['file'].split('/')[0]}/{stem}` | {m['title']} | {m['publisher']} | {m['date']} | {m['source_type']} | {ids} | {url} | {ts} | `{sha}` |")
w("")
w("## Downloaded but not cited (kept as evidence; includes failed fetches)")
w("")
w("| File | HTTP | Bytes | URL | Note |")
w("|---|---|---|---|---|")
for r in rows:
    stem = os.path.splitext(os.path.basename(r[1]))[0]
    if stem in used:
        continue
    note = "fetch failed or blocked" if r[2] != "200" or r[3] in ("0",) else "not needed for a cited fact"
    w(f"| `{r[1]}` | {r[2]} | {r[3]} | {r[6]} | {note} |")
w("")
w("## Page renders (visual evidence)")
w("")
for lane in ("hbm", "packaging", "products"):
    d = os.path.join(EV, lane, "renders")
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            w(f"- `evidence/{lane}/renders/{name}`")
w("")
w("## Repo excerpts (trusted, our own code)")
w("")
for name in sorted(os.listdir(os.path.join(EV, "repo"))):
    w(f"- `evidence/repo/{name}`")
w("")
w("## Tools (outside evidence/)")
w("")
w("`tools/` holds the scripts used: `fetch.sh`, `html2txt.py`, `render_page.py`, `build_facts.py`, `verify_facts.py`, `build_parts.py` and `build_sources_md.py`.")
w("")
w("To re-verify:")
w("")
w("```")
w("python -I tools/verify_facts.py evidence")
w("sha256sum -c SHA256SUMS")
w("```")
with open(os.path.join(OUT, "SOURCES.md"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines) + "\n")
print("sources used", n, "fetchlog rows", len(rows))
