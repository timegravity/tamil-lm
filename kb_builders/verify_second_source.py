#!/usr/bin/env python3
"""Cross-check KB verbatim text against an independent second source and set
verified_second_source=true ONLY for units whose text matches exactly after
removing whitespace and punctuation (word-splitting and layout differ between
editions; letters must not).

Second sources (Project Madurai, cached under data/raw/literature/pm_etexts/):
  aathichudi.jsonl      vs pmuni0002.html (Works of Auvaiyar)
  konrai_vendhan.jsonl  vs pmuni0002.html
  naaladiyar.jsonl      vs pmuni0016.html (Naaladiyar, 400 verses)

Units that do not match (genuine edition variants or OCR differences) are left
with verified_second_source=false and are reported. No text is modified.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PM = ROOT / "data/raw/literature/pm_etexts"
KB = ROOT / "data/kb"

PM0002_URL = "https://www.projectmadurai.org/pm_etexts/utf8/pmuni0002.html"
PM0016_URL = "https://www.projectmadurai.org/pm_etexts/utf8/pmuni0016.html"

def norm(s):
    s = unicodedata.normalize("NFC", s)
    # keep only Tamil letters/digits; drop spaces, punctuation, latin digits
    return "".join(ch for ch in s if "஀" <= ch <= "௿")

def pm_lines(fname):
    t = (PM / fname).read_bytes().decode("utf-8", errors="replace")
    # kill the file's own newlines first so that line breaks come only from
    # markup; a lone <br> on a blank line then marks a verse separator
    t = t.replace("\r", "").replace("\n", " ")
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</?(p|h3|center|strong|font)[^>]*>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    import html as H
    t = H.unescape(t).replace("\xa0", " ")
    return [l.strip() for l in t.split("\n")]

def parse_pm0002():
    """Return (aathichudi_map, konrai_map): number -> normalized text.
    Number 0 is the invocation."""
    lines = pm_lines("pmuni0002.html")
    works = {}
    current = None
    inv = []
    for l in lines:
        if re.fullmatch(r"\d+\.\s*ஆத்திசூடி\s*", l):
            current = "aathichudi"
            works[current] = {}
            inv = []
            continue
        if re.fullmatch(r"\d+\.\s*கொன்றை\s*வேந்தன்\s*", l):
            current = "konrai"
            works[current] = {}
            inv = []
            continue
        if l.startswith("மூதுரை") or l.startswith("நல்வழி"):
            current = None
            continue
        if current is None:
            continue
        m = re.match(r"^(\d+)\.\s*(.+)$", l)
        if m:
            works[current][int(m.group(1))] = norm(m.group(2))
        elif l and "வருக்கம்" not in l and "வாழ்த்து" not in l \
                and norm(l) and 0 not in works[current]:
            inv.append(l)
            if len(inv) == 2:
                works[current][0] = norm("".join(inv))
    return works.get("aathichudi", {}), works.get("konrai", {})

def parse_pm0016():
    """Return number -> normalized quatrain text for naaladiyar (1..400)."""
    lines = pm_lines("pmuni0016.html")
    verses = {}
    cur_no, buf = None, []
    started = False

    def close():
        nonlocal cur_no, buf
        if cur_no is not None and buf:
            if cur_no in verses:
                print(f"WARN pm0016: duplicate verse {cur_no}",
                      file=sys.stderr)
            else:
                verses[cur_no] = norm("".join(buf))
        cur_no, buf = None, []

    for l in lines:
        # chapter headings look like "1.1 செல்வம் நிலையாமை"
        if re.match(r"^\d+\.\d+\s", l):
            started = True
            close()
            continue
        if not started:
            continue
        m = re.match(r"^(\d{1,3})\.\s+(\S.*)$", l)
        if m and 1 <= int(m.group(1)) <= 400:
            close()
            cur_no = int(m.group(1))
            buf = [m.group(2)]
        elif cur_no is not None:
            if not l or "---" in l or not norm(l):
                close()
            else:
                buf.append(l)
    close()
    return verses

def apply(kb_file, second, url, label):
    path = KB / kb_file
    recs = [json.loads(l) for l in path.open(encoding="utf-8")]
    ok, miss, absent = 0, [], []
    for r in recs:
        r["verified_second_source"] = False
        if url in r["sources"]:
            r["sources"].remove(url)
        n = r["number"]
        ours = norm("".join(r["text"]))
        theirs = second.get(n)
        if theirs is None:
            absent.append(n)
            continue
        if ours == theirs:
            r["verified_second_source"] = True
            if url not in r["sources"]:
                r["sources"].append(url)
            ok += 1
        else:
            miss.append(n)
    with path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{label}: {ok}/{len(recs)} verified; "
          f"{len(miss)} edition mismatches {miss[:15]}"
          f"{'...' if len(miss) > 15 else ''}; "
          f"{len(absent)} absent in second source {absent[:10]}")

def main():
    aat, kon = parse_pm0002()
    print(f"pmuni0002: aathichudi units {len(aat)}, konrai units {len(kon)}")
    naal = parse_pm0016()
    print(f"pmuni0016: naaladiyar verses {len(naal)}")
    apply("aathichudi.jsonl", aat, PM0002_URL, "aathichudi")
    apply("konrai_vendhan.jsonl", kon, PM0002_URL, "konrai_vendhan")
    apply("naaladiyar.jsonl", naal, PM0016_URL, "naaladiyar")

if __name__ == "__main__":
    main()
