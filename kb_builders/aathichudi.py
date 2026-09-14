#!/usr/bin/env python3
"""Build data/kb/aathichudi.jsonl from cached ta.wikisource wikitext.

Source page: https://ta.wikisource.org/wiki/ஆத்திசூடி
Cached raw:  data/raw/literature/ws_pages/ஆத்திசூடி.txt

Format in the raw wikitext:
  ===<varukkam heading>===
  N.  {{green|<verbatim aphorism>}}<br /> <modern Tamil gloss, possibly multi-line>
The invocation (கடவுள் வாழ்த்து) has two {{green|:...}} lines and no gloss.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/literature/ws_pages/ஆத்திசூடி.txt"
OUT = ROOT / "data/kb/aathichudi.jsonl"

def nfc(s):
    return unicodedata.normalize("NFC", s)

def clean_gloss(s):
    s = s.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    lines = [l.strip() for l in s.split("\n")]
    return nfc("\n".join(l for l in lines if l)).strip()

def main():
    raw = nfc(RAW.read_text(encoding="utf-8"))
    lines = raw.split("\n")

    units = []
    section = None
    green_re = re.compile(r"\{\{green\|(.*?)\}\}")

    # Locate invocation block
    i = 0
    n = len(lines)
    pending = None  # dict being accumulated: {"number":..., "text":[...], "gloss_parts":[...]}

    def flush():
        nonlocal pending
        if pending is not None:
            units.append(pending)
            pending = None

    while i < n:
        line = lines[i]
        m = re.match(r"^===\s*(.+?)\s*===\s*$", line)
        if m:
            flush()
            section = nfc(m.group(1))
            i += 1
            continue
        if section is None:
            i += 1
            continue
        if line.startswith("==") and not line.startswith("==="):
            # end of நூல் section (e.g. ==இவற்றையும் பார்க்கவும்==)
            flush()
            section = None
            i += 1
            continue

        gm = green_re.search(line)
        if gm:
            verse = gm.group(1)
            # strip leading ':' used for indentation in invocation, stray markup '<'
            verse = verse.lstrip(":").strip()
            verse = verse.rstrip("<").strip()
            verse = nfc(re.sub(r"\s+", " ", verse))
            nm = re.match(r"^\s*(\d+)\s*\.", line)
            rest = line[gm.end():]
            if section == "கடவுள் வாழ்த்து":
                if pending is None:
                    pending = {"number": 0, "section": section,
                               "text": [], "gloss_parts": []}
                pending["text"].append(verse)
                i += 1
                continue
            flush()
            if not nm:
                print(f"WARN: numbered aphorism expected, none found: {line!r}",
                      file=sys.stderr)
                i += 1
                continue
            pending = {"number": int(nm.group(1)), "section": section,
                       "text": [verse], "gloss_parts": [rest]}
        elif pending is not None and line.strip():
            pending["gloss_parts"].append(line)
        i += 1
    flush()

    # sanity
    numbers = [u["number"] for u in units]
    assert numbers[0] == 0, "invocation missing"
    assert numbers[1:] == list(range(1, 110)), f"bad numbering: {numbers[:5]}...{numbers[-3:]}"
    assert len(units[0]["text"]) == 2, "invocation should have 2 lines"

    with OUT.open("w", encoding="utf-8") as f:
        for u in units:
            gloss = clean_gloss("\n".join(u["gloss_parts"])) if u["gloss_parts"] else ""
            rec = {
                "work": "ஆத்திசூடி",
                "work_en": "Aathichudi",
                "tier": 1,
                "unit_type": "aphorism",
                "number": u["number"],
                "section": {"varukkam": u["section"]},
                "text": u["text"],
                "verbatim_text": True,
                "urai": {"wikisource_gloss": gloss} if gloss else {},
                "translation_en": None,
                "transliteration": None,
                "themes": ["அறம்", "நீதி", "ethics", "didactic"],
                "author": "ஔவையார்",
                "author_en": "Avvaiyar",
                "period": "c. 12th century CE",
                "sources": ["https://ta.wikisource.org/wiki/ஆத்திசூடி"],
                "verified_second_source": False,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(units)} units to {OUT}")

if __name__ == "__main__":
    main()
