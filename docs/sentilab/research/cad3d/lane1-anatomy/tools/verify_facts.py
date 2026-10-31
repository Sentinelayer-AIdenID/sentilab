"""Verify that every FACTS.jsonl quote appears verbatim (whitespace/case/dash-normalised)
in the evidence text file it cites.

Usage: python -I verify_facts.py <evidence_root>
Each FACTS.jsonl line: {"fact_id", "value", "unit", "quote", "file", "url", ...}
"file" is relative to <evidence_root>. Prints PASS/FAIL per fact and a summary;
exit 1 if any FAIL.
"""
import json
import os
import re
import sys
import unicodedata


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("‐", "-").replace("‑", "-").replace("‒", "-")
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace("µ", "μ")  # micro sign -> greek mu
    s = re.sub(r"-\s*\n\s*", "-", s)  # hyphenated line breaks keep the hyphen
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def main(root):
    bad = 0
    total = 0
    cache = {}
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name != "FACTS.jsonl":
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        fact = json.loads(line)
                    except json.JSONDecodeError as exc:
                        bad += 1
                        print(f"FAIL {path}:{lineno} bad json: {exc}")
                        continue
                    rel = fact.get("file", "")
                    target = os.path.join(root, rel)
                    if not os.path.isfile(target):
                        bad += 1
                        print(f"FAIL {fact.get('fact_id')} missing file {rel}")
                        continue
                    if target not in cache:
                        with open(target, encoding="utf-8", errors="replace") as tf:
                            cache[target] = norm(tf.read())
                    render = fact.get("render")
                    if render and not os.path.isfile(os.path.join(root, render)):
                        bad += 1
                        print(f"FAIL {fact.get('fact_id')} missing render {render}")
                        continue
                    quote = norm(fact.get("quote", ""))
                    is_visual = fact.get("capture_method") == "render"
                    if quote and quote not in cache[target]:
                        bad += 1
                        print(f"FAIL {fact.get('fact_id')} quote not found in {rel}: {fact.get('quote', '')[:120]!r}")
                    elif is_visual:
                        if not render:
                            bad += 1
                            print(f"FAIL {fact.get('fact_id')} visual fact without render")
                        else:
                            print(f"VISUAL {fact.get('fact_id')} (value read from {render}; anchor quote {'ok' if quote else 'none'})")
                    elif quote:
                        print(f"PASS {fact.get('fact_id')}")
                    else:
                        bad += 1
                        print(f"FAIL {fact.get('fact_id')} empty quote")
    print(f"SUMMARY total={total} fail={bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1])
