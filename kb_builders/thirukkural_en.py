#!/usr/bin/env python3
"""Build data/kb/thirukkural_en.jsonl: public-domain English translation of
the Thirukkural with named translators.

Primary source (cached at data/raw/literature/pm_etexts/pmuni0153.html):
  https://www.projectmadurai.org/pm_etexts/utf8/pmuni0153.html
  "tirukkuRaL of tiruvaLLuvar, English Translation and Commentary by
   Rev. Dr. G. U. Pope, Rev W. H. Drew, Rev. John Lazarus and Mr F. W. Ellis"
  (G.U. Pope's verse translation, first published by W.H. Allen & Co, 1886,
   with the Drew / Lazarus prose rendering in italics).

Layout per kural: a bare number line, two lines of Pope's verse couplet,
then the prose translation inside <i>/<em>. Chapter headings sit in <h3>.

Cross-check: the tk120404 GitHub dataset (data/raw/literature/
tk120404_thirukkural.json) carries the same translation as its unattributed
"couplet" field; a unit is marked verified_second_source only when Pope's
verse matches it letter-for-letter after case/punctuation normalisation.

Output fields follow the spirit of data/kb/SCHEMA.md. translation_en holds
Pope's verse; the Drew/Lazarus prose is kept in translation_en_prose.
This file does NOT touch data/kb/thirukkural.jsonl (join on number).
"""
import html as H
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/literature/pm_etexts/pmuni0153.html"
TK = ROOT / "data/raw/literature/tk120404_thirukkural.json"
OUT = ROOT / "data/kb/thirukkural_en.jsonl"
URL = "https://www.projectmadurai.org/pm_etexts/utf8/pmuni0153.html"
TK_SRC = "github:tk120404/thirukkural (couplet field, cross-check only)"

IT_ON, IT_OFF = "\x01", "\x02"

def nfc(s):
    return unicodedata.normalize("NFC", s)

def fetch():
    import requests
    r = requests.get(URL, headers={"User-Agent": "tamil-lm-research/0.1 "
                                   "(contact: contact@timegravity.ai)"},
                     timeout=60)
    r.raise_for_status()
    RAW.write_bytes(r.content)

def norm_en(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(ch for ch in s if ch.isalnum())

def main():
    if not RAW.exists():
        fetch()
    t = RAW.read_bytes().decode("utf-8", errors="replace")
    m = re.search(r"header page is kept intact", t)
    t = t[m.end():] if m else t
    t = t.replace("\r", "").replace("\n", " ")
    t = re.sub(r"<(i|em)\b[^>]*>", IT_ON, t, flags=re.I)
    t = re.sub(r"</(i|em)>", IT_OFF, t, flags=re.I)
    # Heading blocks sit inside <center>...</center>; note the file's own
    # <h3> closing tags are malformed ("<h3>" instead of "</h3>"), so match
    # the well-formed <center> wrapper instead.
    def h3line(mm):
        inner = re.sub(r"<br\s*/?>", "\n", mm.group(1), flags=re.I)
        inner = re.sub(r"<[^>]+>", "", inner)
        return "".join("\n\x03" + l.strip() + "\n"
                       for l in inner.split("\n") if l.strip())
    t = re.sub(r"<center>(.*?)</center>", h3line, t, flags=re.I | re.S)
    # kurals 692 and 1182 have a "<\nbr>" tag broken across a source line
    t = re.sub(r"<\s*br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = H.unescape(t).replace("\xa0", " ")

    part_en, chapter_en = None, None
    kurals = {}  # n -> {verse:[], prose:[], part, chapter}
    cur = None
    italic = False
    for raw_line in t.split("\n"):
        line = raw_line.strip()
        if line.startswith("\x03"):
            head = line[1:].strip().strip(".").strip()
            pm = re.match(r"^PART\s+[IVX]+\.?\s*(.+)$", head)
            if pm:
                part_en = pm.group(1).strip().title()
            cm = re.match(r"^\d\s*\.\s*\d+\s*\.\s*\d*\s*(\D.+)$", head)
            if cm:
                chapter_en = cm.group(1).strip().lstrip(". ").strip()
            cur = None
            continue
        has_on, has_off = IT_ON in line, IT_OFF in line
        text = line.replace(IT_ON, "").replace(IT_OFF, "").strip()
        was_italic = italic
        if has_on:
            was_italic = True
        if has_off:
            italic = False
        elif has_on:
            italic = True
        # number line; the source has "77," (comma) and "11 35" (the number
        # 1135 broken across a source line), so accept those forms too
        nm = re.fullmatch(r"(\d{1,4})(?:\s+(\d{1,4}))?\s*[.,;:]?", text)
        if nm and not was_italic:
            n = int(nm.group(1) + (nm.group(2) or ""))
            if 1 <= n <= 1330:
                cur = kurals.setdefault(
                    n, {"verse": [], "prose": [], "part": part_en,
                        "chapter": chapter_en})
                if cur["verse"]:
                    print(f"WARN: number {n} seen twice", file=sys.stderr)
                    cur = None
                continue
        if cur is None or not text:
            continue
        if re.fullmatch(r"[-=_.\s]+", text):
            continue
        if "End of tirukkuRaL" in text or "webpage was last revised" in text:
            cur = None
            continue
        text = nfc(re.sub(r"\s+", " ", text))
        if was_italic:
            cur["prose"].append(text)
        else:
            cur["verse"].append(text)

    # Four kurals (116, 126, 131, 1266) lack the opening <i> tag in the
    # source, so their prose landed after the couplet. Pope's couplet is
    # always exactly two lines; move any extra lines to the prose.
    for n, k in kurals.items():
        # kurals 692 and 1182: the source opens <i> one line early, so the
        # couplet's second line sits at the head of the prose; restore it.
        if len(k["verse"]) == 1 and len(k["prose"]) >= 2:
            print(f"NOTE: kural {n}: second couplet line recovered from "
                  f"italic block (misplaced <i> in source)", file=sys.stderr)
            k["verse"].append(k["prose"].pop(0))
        if len(k["verse"]) > 2:
            print(f"NOTE: kural {n}: {len(k['verse'])-2} extra verse line(s) "
                  f"moved to prose (missing <i> in source)", file=sys.stderr)
            k["prose"] = k["verse"][2:] + k["prose"]
            k["verse"] = k["verse"][:2]

    missing = [n for n in range(1, 1331) if n not in kurals]
    noverse = [n for n, k in kurals.items() if not k["verse"]]
    noprose = [n for n, k in kurals.items() if not k["prose"]]
    print(f"parsed {len(kurals)} kurals; missing {missing}; "
          f"no verse {noverse}; no prose {noprose[:10]}"
          f"{'...' if len(noprose) > 10 else ''} ({len(noprose)})")

    # cross-check against tk120404 couplet field
    tk = {row["Number"]: row
          for row in json.loads(TK.read_text(encoding="utf-8"))["kural"]}
    verified = 0
    with OUT.open("w", encoding="utf-8") as f:
        for n in sorted(kurals):
            k = kurals[n]
            verse = " ".join(k["verse"])
            ok = norm_en(verse) == norm_en(tk.get(n, {}).get("couplet", "")) \
                and bool(k["verse"])
            verified += ok
            rec = {
                "work": "திருக்குறள்",
                "work_en": "Thirukkural",
                "tier": 1,
                "unit_type": "kural",
                "number": n,
                "section": {"part_en": k["part"],
                            "adhikaram_no": (n - 1) // 10 + 1,
                            "adhikaram_en_pope": k["chapter"]},
                "text": k["verse"],
                "verbatim_text": True,
                "urai": {},
                "translation_en": verse,
                "translation_en_prose": " ".join(k["prose"]) or None,
                "translator": "G.U. Pope (verse); W.H. Drew and "
                              "John Lazarus (prose)",
                "transliteration": None,
                "themes": [],
                "author": "திருவள்ளுவர்",
                "author_en": "Thiruvalluvar",
                "period": "translation published 1886",
                "sources": [URL] + ([TK_SRC] if ok else []),
                "verified_second_source": bool(ok),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {len(kurals)} units to {OUT}; "
          f"verified vs tk120404: {verified}/{len(kurals)}")

if __name__ == "__main__":
    main()
