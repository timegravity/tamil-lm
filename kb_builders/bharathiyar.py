#!/usr/bin/env python3
"""Build data/kb/bharathiyar.jsonl from Project Madurai UTF-8 etexts.

Sources (all fetched from https://www.projectmadurai.org/pm_etexts/utf8/,
cached under data/raw/literature/pm_etexts/, robots.txt allows crawling,
1 request per second):

  pmuni0012_01  தேசிய கீதங்கள்            (National songs)
  pmuni0012_02  தெய்வப் பாடல்கள்          (Devotional songs)
  pmuni0021     ஞானப் பாடல்கள், பல்வகைப் பாடல்கள், சுயசரிதை
  pmuni0049     கண்ணன் பாட்டு, குயில் பாட்டு
  pmuni0091     பாஞ்சாலி சபதம் முதற் பாகம் (சருக்கம் 1, 2)
  pmuni0888     பாஞ்சாலி சபதம் இரண்டாம் பாகம் (சருக்கம் 3, 4, 5)
  pmuni0245     விநாயகர் நான்மணிமாலை

Subramania Bharati died in 1921; his works were nationalised by the state in
1949 and are in the public domain.

Layout: poems are marked by <strong>N. Title</strong> headings (or, in
pmuni0888, by <h3> headings; in pmuni0245, by verse-form names in <strong>),
verse lines separated by <br>. We keep the printed song apparatus (ராகம்,
பல்லவி, சரணங்கள் markers) since it is part of the printed source; English
boilerplate, dividers and colophons are dropped.
"""
import html as H
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/raw/literature/pm_etexts"
OUT = ROOT / "data/kb/bharathiyar.jsonl"
BASE = "https://www.projectmadurai.org/pm_etexts/utf8/"

TAMIL = re.compile(r"[஀-௿]")

FILES = [
    {"id": "pmuni0012_01", "collection": "தேசிய கீதங்கள்"},
    {"id": "pmuni0012_02", "collection": "தெய்வப் பாடல்கள்"},
    {"id": "pmuni0021", "collections": {
        r"ஞானப்\s*பாடல்கள்": "ஞானப் பாடல்கள்",
        r"பல்வகைப்\s*பாடல்கள்": "பல்வகைப் பாடல்கள்",
        r"சுயசரிதை": "சுயசரிதை"}, "orphan": True},
    {"id": "pmuni0049", "collections": {
        r"கண்ணன்\s*பாட்டு": "கண்ணன் பாட்டு",
        r"குயில்\s*பாட்டு": "குயில் பாட்டு"}},
    {"id": "pmuni0091", "collection": "பாஞ்சாலி சபதம் முதற் பாகம்",
     "section_re": r"சருக்கம்"},
    {"id": "pmuni0888", "collection": "பாஞ்சாலி சபதம் இரண்டாம் பாகம்",
     "mode": "h3"},
    {"id": "pmuni0245", "collection": "விநாயகர் நான்மணிமாலை",
     "title_re": r"^(வெண்பா|கலித்துறை|விருத்தம்|அகவல்)$"},
]

def nfc(s):
    return unicodedata.normalize("NFC", s)

def fetch(fid):
    import requests
    path = CACHE / f"{fid}.html"
    if path.exists():
        return path
    r = requests.get(BASE + fid + ".html",
                     headers={"User-Agent": "tamil-lm-research/0.1 "
                              "(contact: contact@timegravity.ai)"},
                     timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    time.sleep(1)
    return path

def inner_lines(fragment):
    frag = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    frag = re.sub(r"</?p[^>]*>", "\n", frag, flags=re.I)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = H.unescape(frag).replace("\xa0", " ")
    frag = frag.replace("﻿", "").replace("​", "").replace("⁠", "")
    out = []
    for l in frag.split("\n"):
        l = nfc(re.sub(r"\s+", " ", l).strip())
        out.append(l)
    return out

def keep_line(l):
    if not l or not TAMIL.search(l):
        return False
    if re.fullmatch(r"[-_=\.\s\d\(\)]*", l):
        return False
    # colophons: "…சருக்கம் முற்றிற்று", "விநாயகர் நான்மணிமாலை முற்றும்" -
    # short lines ENDING in muRRiRRu/muRRum. The word முற்றும் ("entirely")
    # also occurs inside real verse lines, so require the line-final position
    # and a short line before dropping.
    if "முற்றிற்று" in l:
        return False
    if re.search(r"முற்றும்\W*$", l) and len(l.split()) <= 4:
        return False
    return True

def tokenize(body):
    """Yield ('h3'|'strong'|'line', text) tokens in document order."""
    parts = re.split(r"(<h3[^>]*>.*?</h3>|<strong[^>]*>.*?</strong>)",
                     body, flags=re.S | re.I)
    for part in parts:
        low = part.lower()
        if low.startswith("<h3"):
            yield ("h3", [l for l in inner_lines(part) if l])
        elif low.startswith("<strong"):
            yield ("strong", " ".join(l for l in inner_lines(part) if l))
        else:
            for l in inner_lines(part):
                yield ("line", l)

def parse_file(cfg):
    fid = cfg["id"]
    body = fetch(fid).read_bytes().decode("utf-8", errors="replace")
    m = re.search(r"header page is kept intact", body)
    if m:
        body = body[m.end():]

    poems = []
    collection = cfg.get("collection")
    coll_map = cfg.get("collections", {})
    if coll_map:
        collection = None
    section = None
    subsection = None
    title_re = cfg.get("title_re")
    cur = None  # {"title","no","lines"}

    def flush():
        nonlocal cur, subsection
        if cur is None:
            return
        lines = [l for l in cur["lines"] if keep_line(l)]
        if lines:
            poems.append({"collection": collection, "section": section,
                          "subsection": subsection, "title": cur["title"],
                          "no": cur["no"], "lines": lines})
        else:
            # a numbered heading with no verse body is a subsection header
            print(f"  {fid}: heading with no body -> subsection: "
                  f"{cur['title']}", file=sys.stderr)
            subsection = cur["title"]
        cur = None

    for kind, val in tokenize(body):
        if kind == "h3":
            text = " ".join(val)
            if cfg.get("mode") == "h3":
                flush()
                for l in val:
                    hm = re.match(r"^(\d+)\.\s*(.+)$", l)
                    if hm and "சருக்கம்" in l:
                        section = nfc(hm.group(0).strip())
                    elif hm:
                        cur = {"title": nfc(hm.group(2).strip()),
                               "no": int(hm.group(1)), "lines": []}
            else:
                matched = False
                for pat, name in coll_map.items():
                    if re.search(pat, text):
                        flush()
                        collection, section, subsection = name, None, None
                        matched = True
                        break
                if not matched and cfg.get("section_re") \
                        and re.search(cfg["section_re"], text) \
                        and TAMIL.search(text):
                    flush()
                    section = nfc(re.sub(r"\s+", " ", text).strip())
        elif kind == "strong":
            if cfg.get("mode") == "h3" or not TAMIL.search(val):
                continue
            if "முற்றிற்று" in val or "முற்றும்" in val \
               or val.startswith("உள்ளடக்கம்"):
                flush()
                continue
            if title_re:
                tm = re.match(title_re, val)
                if tm:
                    flush()
                    cur = {"title": nfc(val), "no": None, "lines": []}
                continue
            tm = re.match(r"^(\d+)\.\s*(.+)$", val)
            if tm:
                flush()
                cur = {"title": nfc(tm.group(2).strip()),
                       "no": int(tm.group(1)), "lines": []}
            elif cur is not None:
                cur["lines"].append(val)
        else:
            if cur is not None:
                cur["lines"].append(val)
            elif cfg.get("orphan") and collection and keep_line(val):
                cur = {"title": nfc(val), "no": None, "lines": [val]}
    flush()
    return poems

def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    all_poems = []
    for cfg in FILES:
        poems = parse_file(cfg)
        for p in poems:
            p["source"] = BASE + cfg["id"] + ".html"
        # The PM etext leaves the first piece of பல்வகைப் பாடல்கள் (the
        # famous புதிய ஆத்திசூடி: காப்பு + நூல்) without a numbered heading;
        # supply its conventional title as metadata (the text itself is
        # untouched and verbatim).
        for p in poems:
            if p["collection"] == "பல்வகைப் பாடல்கள்" \
               and p["title"].startswith("(காப்பு"):
                p["title"] = "புதிய ஆத்திசூடி"
                p["no"] = 1
                p["note"] = ("title supplied editorially; the PM etext "
                             "presents this first piece without a numbered "
                             "heading")
        colls = {}
        for p in poems:
            colls[p["collection"]] = colls.get(p["collection"], 0) + 1
        print(f"{cfg['id']}: {len(poems)} poems {colls}")
        all_poems.extend(poems)

    empty = [p for p in all_poems if not p["lines"]]
    assert not empty
    print(f"TOTAL: {len(all_poems)} poems")

    with OUT.open("w", encoding="utf-8") as f:
        for i, p in enumerate(all_poems, 1):
            sec = {"collection": p["collection"], "poem_title": p["title"]}
            if p["no"] is not None:
                sec["no_in_collection"] = p["no"]
            if p["section"]:
                sec["sarukkam"] = p["section"]
            if p["subsection"]:
                sec["subsection"] = p["subsection"]
            if p.get("note"):
                sec["note"] = p["note"]
            rec = {
                "work": "பாரதியார் பாடல்கள்",
                "work_en": "Bharathiyar Padalgal (Songs of Subramania Bharati)",
                "tier": 1,
                "unit_type": "poem",
                "number": i,
                "section": sec,
                "text": p["lines"],
                "verbatim_text": True,
                "urai": {},
                "translation_en": None,
                "transliteration": None,
                "themes": ["தேசியம்", "பக்தி", "விடுதலை", "patriotism",
                           "devotion", "modern Tamil poetry"],
                "author": "சி. சுப்பிரமணிய பாரதியார்",
                "author_en": "C. Subramania Bharati (Bharathiyar)",
                "period": "1882 to 1921",
                "sources": [p["source"]],
                "verified_second_source": False,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(all_poems)} units to {OUT}")

if __name__ == "__main__":
    main()
