#!/usr/bin/env python3
"""Build data/kb/konrai_vendhan.jsonl.

Source: https://ta.wikisource.org/wiki/கொன்றை_வேந்தன் (the plain page transcludes
pages 8-11 of "நீதிக் களஞ்சியம்.pdf", so we fetch the RENDERED page through the
MediaWiki parse API and strip the HTML).

Cached raw: data/raw/literature/ws_pages/கொன்றை_வேந்தன்_parsed.json
(re-fetched if absent).

Structure: an invocation couplet (கடவுள் வாழ்த்து, unnumbered) followed by 91
single-line aphorisms in Tamil alphabetical order under the heading நூல்.
Line-number annotations in the source contain a typo (line 20 is labelled 22),
so sequential position is authoritative; mismatches are logged.
"""
import html as H
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAWJ = ROOT / "data/raw/literature/ws_pages/கொன்றை_வேந்தன்_parsed.json"
OUT = ROOT / "data/kb/konrai_vendhan.jsonl"
PAGE_URL = "https://ta.wikisource.org/wiki/கொன்றை_வேந்தன்"

def nfc(s):
    return unicodedata.normalize("NFC", s)

def fetch():
    import requests
    r = requests.get(
        "https://ta.wikisource.org/w/api.php",
        params={"action": "parse", "page": "கொன்றை வேந்தன்",
                "format": "json", "redirects": 1},
        headers={"User-Agent":
                 "tamil-lm-research/0.1 (contact: contact@timegravity.ai)"},
        timeout=30)
    r.raise_for_status()
    RAWJ.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")

def strip_line(fragment):
    """Return (clean_text, annotated_number_or_None) for one <br/>-split line."""
    num = None
    m = re.search(r'<span[^>]*id="line(\d+)"[^>]*>\s*\d+\s*</span>', fragment)
    if m:
        num = int(m.group(1))
        fragment = fragment.replace(m.group(0), "")
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = H.unescape(fragment)
    fragment = fragment.replace("⁠", "").replace("​", "")
    fragment = re.sub(r"\s+", " ", fragment).strip()
    return nfc(fragment), num

def main():
    if not RAWJ.exists():
        fetch()
    d = json.loads(RAWJ.read_text(encoding="utf-8"))
    page_html = d["parse"]["text"]["*"]

    # All poem divs, in document order.
    poems = re.findall(r'<div class="poem">\s*<p>(.*?)</p>\s*</div>',
                       page_html, flags=re.S)
    if not poems:
        sys.exit("no poem blocks found; source layout changed")

    invocation = None
    aphorisms = []  # (position, annotated_num, text)
    for block in poems:
        for frag in re.split(r"<br\s*/?>", block):
            text, num = strip_line(frag)
            if not text:
                continue
            if num is None and invocation is not None and aphorisms == [] \
               and len(invocation) < 2:
                invocation.append(text)
            elif num is None and invocation is None:
                invocation = [text]
            elif num is None and len(invocation or []) < 2 and not aphorisms:
                invocation.append(text)
            else:
                pos = len(aphorisms) + 1
                if num is not None and num != pos:
                    print(f"NOTE: source line annotation {num} at position {pos}"
                          f" (using position): {text}", file=sys.stderr)
                aphorisms.append((pos, text))

    assert invocation and len(invocation) == 2, f"invocation parse failed: {invocation}"
    print(f"invocation lines: {len(invocation)}, aphorisms: {len(aphorisms)}")
    if len(aphorisms) != 91:
        print(f"WARN: expected 91 aphorisms, got {len(aphorisms)}", file=sys.stderr)

    def rec(number, section, text_lines):
        return {
            "work": "கொன்றை வேந்தன்",
            "work_en": "Konrai Vendhan",
            "tier": 1,
            "unit_type": "aphorism",
            "number": number,
            "section": {"part": section},
            "text": text_lines,
            "verbatim_text": True,
            "urai": {},
            "translation_en": None,
            "transliteration": None,
            "themes": ["அறம்", "நீதி", "ethics", "didactic"],
            "author": "ஔவையார்",
            "author_en": "Avvaiyar",
            "period": "c. 12th century CE",
            "sources": [PAGE_URL],
            "verified_second_source": False,
        }

    with OUT.open("w", encoding="utf-8") as f:
        f.write(json.dumps(rec(0, "கடவுள் வாழ்த்து", invocation),
                           ensure_ascii=False) + "\n")
        for pos, text in aphorisms:
            f.write(json.dumps(rec(pos, "நூல்", [text]),
                               ensure_ascii=False) + "\n")
    print(f"wrote {1 + len(aphorisms)} units to {OUT}")

if __name__ == "__main__":
    main()
