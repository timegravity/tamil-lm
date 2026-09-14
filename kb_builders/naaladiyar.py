#!/usr/bin/env python3
"""Build data/kb/naaladiyar.jsonl (400 quatrains, 40 chapters).

Source: ta.wikisource series "நாலடியார் - செய்யுளும் செய்திகளும்". The per-chapter
subpages of that series transclude only the modern prose retellings (செய்திகள்)
by Prof. Ra. Seenivasan, which are a modern author's work and are NOT included.
The three paal subpages transclude the verse (செய்யுள்) section of the same book
with global verse numbers 1..400, which is what we extract:

  /அறத்துப்பால்    verses 1..130  (chapters 1..13)
  /பொருட்பால்      verses 131..390 (chapters 14..39)
  /காமத்துப் பால்  verses 391..400 (chapter 40)

Pages are PDF transclusions, so we fetch RENDERED HTML via action=parse and
cache the JSON under data/raw/literature/ws_pages/.
"""
import html as H
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/raw/literature/ws_pages"
OUT = ROOT / "data/kb/naaladiyar.jsonl"

# (page, cache file, paal, global number of the page's first verse)
# The printed verse-number annotations contain two typos (116 printed as 114,
# 172 printed as 173), so sequential position within each page is
# authoritative; mismatching annotations are logged.
PAGES = [
    ("நாலடியார் - செய்யுளும் செய்திகளும்/அறத்துப்பால்",
     "நாலடியார்_செய்யுளும்_அறத்துப்பால்_parsed.json", "அறத்துப்பால்", 1),
    ("நாலடியார் - செய்யுளும் செய்திகளும்/பொருட்பால்",
     "நாலடியார்_செய்யுளும்_பொருட்பால்_parsed.json", "பொருட்பால்", 131),
    ("நாலடியார் - செய்யுளும் செய்திகளும்/காமத்துப் பால்",
     "நாலடியார்_செய்யுளும்_காமத்துப்பால்_parsed.json", "காமத்துப்பால்", 391),
]

def nfc(s):
    return unicodedata.normalize("NFC", s)

def fetch(page, path):
    import requests
    r = requests.get(
        "https://ta.wikisource.org/w/api.php",
        params={"action": "parse", "page": page, "format": "json",
                "redirects": 1},
        headers={"User-Agent":
                 "tamil-lm-research/0.1 (contact: contact@timegravity.ai)"},
        timeout=60)
    r.raise_for_status()
    path.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
    time.sleep(1)

NUM = "\x01"
HEAD = "\x02"

def to_lines(page_html):
    h = page_html
    i = h.find("prp-pages-output")
    if i >= 0:
        h = h[i:]
    h = re.sub(r"<style.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<!--.*?-->", "", h, flags=re.S)
    h = re.sub(r'<span[^>]*class="pagenum[^>]*>.*?</span></span></span>', "",
               h, flags=re.S)
    # chapter/paal headings
    h = re.sub(r"<center>(.*?)</center>",
               lambda m: "\n" + HEAD + re.sub(r"<[^>]+>", "", m.group(1)) + HEAD + "\n",
               h, flags=re.S)
    # verse number spans
    h = re.sub(r'<span[^>]*id="line(\d+)"[^>]*>\s*\d+\s*</span>',
               lambda m: NUM + m.group(1) + NUM, h)
    h = re.sub(r"<br\s*/?>", "\n", h)
    h = re.sub(r"</?(p|div)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = H.unescape(h)
    h = h.replace("⁠", "").replace("​", "").replace("﻿", "")
    return [l.strip() for l in h.split("\n")]

def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    verses = {}  # number -> {"chapter_no","chapter_name","paal","lines"}
    for page, fname, paal, start in PAGES:
        path = CACHE / fname
        if not path.exists():
            print(f"fetching {page}")
            fetch(page, path)
        d = json.loads(path.read_text(encoding="utf-8"))
        lines = to_lines(d["parse"]["text"]["*"])
        chapter_no, chapter_name = None, None
        counter = start
        buf = []
        for line in lines:
            hm = re.fullmatch(HEAD + r"(.*?)" + HEAD, line)
            if hm:
                title = nfc(hm.group(1).strip())
                cm = re.match(r"^(\d+)[\.\s]\s*(.+)$", title)
                if cm:
                    chapter_no = int(cm.group(1))
                    chapter_name = cm.group(2).strip()
                buf = []
                continue
            if not line:
                continue
            nm = re.search(NUM + r"(\d+)" + NUM, line)
            if nm:
                annotated = int(nm.group(1))
                number = counter
                counter += 1
                if annotated != number:
                    print(f"NOTE: annotation {annotated} at position {number}"
                          f" (using position)", file=sys.stderr)
                last = nfc(re.sub(NUM + r"\d+" + NUM, "", line))
                last = re.sub(r"\s+", " ", last).strip()
                text = buf + ([last] if last else [])
                text = [nfc(re.sub(r"\s+", " ", t)).strip() for t in text]
                if number in verses:
                    print(f"WARN: duplicate verse {number}", file=sys.stderr)
                if len(text) != 4:
                    print(f"NOTE: verse {number} has {len(text)} lines",
                          file=sys.stderr)
                verses[number] = {"chapter_no": chapter_no,
                                  "chapter_name": chapter_name,
                                  "paal": paal, "lines": text}
                buf = []
            elif "★" not in line:
                buf.append(line)

    missing = [n for n in range(1, 401) if n not in verses]
    if missing:
        print(f"WARN: missing verses: {missing}", file=sys.stderr)
    empty = [n for n, v in verses.items() if not v["lines"]]
    assert not empty, f"empty verses: {empty}"
    chapters = {v["chapter_no"] for v in verses.values()}
    print(f"parsed {len(verses)} verses across {len(chapters)} chapters")

    with OUT.open("w", encoding="utf-8") as f:
        for n in sorted(verses):
            v = verses[n]
            rec = {
                "work": "நாலடியார்",
                "work_en": "Naaladiyar",
                "tier": 1,
                "unit_type": "verse",
                "number": n,
                "section": {"paal": v["paal"], "chapter_no": v["chapter_no"],
                            "chapter_name": v["chapter_name"]},
                "text": v["lines"],
                "verbatim_text": True,
                "urai": {},
                "translation_en": None,
                "transliteration": None,
                "themes": ["அறம்", "நீதி", "ethics", "didactic"],
                "author": "சமண முனிவர்கள் (தொகுப்பு: பதுமனார்)",
                "author_en": "unknown (Jain monks, compiled by Pathumanar)",
                "period": "c. 100 to 500 CE",
                "sources": ["https://ta.wikisource.org/wiki/நாலடியார்_-_செய்யுளும்_செய்திகளும்"],
                "verified_second_source": False,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(verses)} units to {OUT}")

if __name__ == "__main__":
    main()
