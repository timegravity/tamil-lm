"""Build data/kb/kambaramayanam.jsonl.

Structure: every kandam/padalam from the ta.wikisource index page
'கம்பராமாயணம்' (chapter records, verbatim_text false).
Verses: all stanzas from a selection of well-known padalams, fetched from
their ta.wikisource pages (<poem> blocks, stanza = lines ending in a number).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KB, make_unit, nfc, ws_wikitext, write_jsonl

WORK, WORK_EN = "கம்பராமாயணம்", "Kambaramayanam"
AUTHOR, AUTHOR_EN = "கம்பர்", "Kambar"
PERIOD = "c. 12th century CE"
KANDAM_EN = {"பால காண்டம்": "Bala Kandam", "அயோத்தியா காண்டம்": "Ayodhya Kandam",
             "ஆரணிய காண்டம்": "Aranya Kandam", "கிட்கிந்தா காண்டம்": "Kishkindha Kandam",
             "சுந்தர காண்டம்": "Sundara Kandam", "யுத்த காண்டம்": "Yuddha Kandam"}

FAMOUS = [
    "கம்பராமாயணம்/பாயிரம்",
    "கம்பராமாயணம்/பால காண்டம்/ஆற்றுப் படலம்",
    "கம்பராமாயணம்/பால காண்டம்/நாட்டுப் படலம்",
    "கம்பராமாயணம்/பால காண்டம்/திரு அவதாரப் படலம்",
    "கம்பராமாயணம்/பால காண்டம்/மிதிலைக் காட்சிப் படலம்",
    "கம்பராமாயணம்/அயோத்தியா காண்டம்/கைகேயி சூழ்ச்சிப் படலம்",
    "கம்பராமாயணம்/அயோத்தியா காண்டம்/நகர் நீங்கு படலம்",
    "கம்பராமாயணம்/அயோத்தியா காண்டம்/குகப் படலம்",
    "கம்பராமாயணம்/ஆரணிய காண்டம்/சூர்ப்பணகைப் படலம்",
    "கம்பராமாயணம்/ஆரணிய காண்டம்/சடாயு உயிர் நீத்த படலம்",
    "கம்பராமாயணம்/கிட்கிந்தா காண்டம்/வாலி வதைப் படலம்",
    "கம்பராமாயணம்/சுந்தர காண்டம்/கடல் தாவு படலம்",
    "கம்பராமாயணம்/சுந்தர காண்டம்/காட்சிப் படலம்",
    "கம்பராமாயணம்/சுந்தர காண்டம்/இலங்கை எரியூட்டு படலம்",
    "கம்பராமாயணம்/யுத்த காண்டம்/வீடணன் அடைக்கலப் படலம்",
    "கம்பராமாயணம்/யுத்த காண்டம்/கும்பகருணன் வதைப் படலம்",
    "கம்பராமாயணம்/யுத்த காண்டம்/இராவணன் வதைப் படலம்",
    "கம்பராமாயணம்/யுத்த காண்டம்/மீட்சிப் படலம்",
]


def parse_index():
    wt = ws_wikitext("கம்பராமாயணம்")
    kandam = None
    out = []  # (kandam, idx, name, page)
    idx = 0
    for line in wt.split("\n"):
        m = re.match(r"^==\s*(.+?)\s*==$", line)
        if m:
            kandam = nfc(m.group(1))
            idx = 0
            continue
        m = re.match(r"^[#*]\s*\[\[([^\]|]+)\|?([^\]]*)\]\]", line)
        if m and kandam:
            page = nfc(m.group(1))
            name = nfc(m.group(2) or page.split("/")[-1])
            if line.startswith("#"):
                idx += 1
                out.append((kandam, idx, name, page))
            else:
                out.append((kandam, 0, name, page))
    return out


def parse_verses(page):
    wt = ws_wikitext(page)
    if not wt:
        return []
    verses = []
    for blk in re.finditer(r"<poem[^>]*>(.*?)</poem>", wt, re.S):
        cur = []
        subtitle = None
        for raw in blk.group(1).split("\n"):
            l = raw.strip()
            if not l:
                continue
            mt = re.match(r"^'''(.+?)'''$", l)
            if mt:
                subtitle = nfc(mt.group(1))
                continue
            l = re.sub(r"<[^>]+>|'''|''|\{\{[^}]*\}\}", "", l)
            mn = re.match(r"^(.*?)\s+(\d{1,4})\s*$", l)
            if mn:
                if nfc(mn.group(1)):
                    cur.append(nfc(mn.group(1)))
                if cur:
                    verses.append((int(mn.group(2)), subtitle, cur))
                cur = []
            else:
                if nfc(l):
                    cur.append(nfc(l))
        if cur and len(cur) >= 2:
            verses.append((None, subtitle, cur))
    if verses:
        return verses
    # plain-text layout: stanzas separated by blank lines, trailing number
    body = re.sub(r"\{\{[^}]*\}\}|<[^>]+>|'{2,3}", "", wt)
    subtitle = None
    for para in re.split(r"\n\s*\n", body):
        lines = [nfc(x) for x in para.split("\n") if nfc(x)]
        lines = [x for x in lines if not x.startswith(("[[", "{{", "{|", "|", "----"))]
        if not lines:
            continue
        mh = re.match(r"^=+\s*(.+?)\s*=+$", lines[0])
        if mh:
            subtitle = nfc(mh.group(1))
            lines = lines[1:]
            if not lines:
                continue
        if len(lines) == 1 and not re.search(r"\d\s*$", lines[0]):
            subtitle = lines[0]
            continue
        n = None
        mn = re.match(r"^(.*?)[\s.]*(\d{1,4})\s*$", lines[-1])
        if mn:
            n = int(mn.group(2))
            lines[-1] = nfc(mn.group(1))
            if not lines[-1]:
                lines = lines[:-1]
        if 2 <= len(lines) <= 8:
            verses.append((n, subtitle, lines))
    if verses:
        return verses
    # one-line-per-paragraph layout: accumulate until a numbered line
    cur, subtitle = [], None
    for raw in body.split("\n"):
        l = nfc(raw)
        if not l or l.startswith(("[[", "{{", "{|", "|", "----")):
            continue
        mh = re.match(r"^=+\s*(.+?)\s*=+$", l)
        if mh:
            subtitle = nfc(mh.group(1)); cur = []
            continue
        mn = re.match(r"^(.*?)[\s.]*(\d{1,4})\s*$", l)
        if mn:
            if nfc(mn.group(1)):
                cur.append(nfc(mn.group(1)))
            if 2 <= len(cur) <= 8:
                verses.append((int(mn.group(2)), subtitle, cur))
            cur = []
        else:
            cur.append(l)
            if len(cur) > 8:
                cur = []
    return verses


def main():
    units = []
    index = parse_index()
    print("index entries:", len(index))
    for kandam, idx, name, page in index:
        ken = KANDAM_EN.get(kandam, kandam)
        units.append(make_unit(
            WORK, WORK_EN, "chapter", f"{kandam}/{idx}" if idx else name,
            {"kandam": kandam, "kandam_en": ken, "padalam": name,
             "padalam_no": idx or None},
            [f"கம்பராமாயணம் {kandam}, படலம் {idx}: {name}." if idx
             else f"கம்பராமாயணம்: {name} ({kandam})."],
            False, ["ta.wikisource.org:கம்பராமாயணம்"], author=AUTHOR,
            author_en=AUTHOR_EN, period=PERIOD, themes=["காப்பியம்", "இராமாயணம்"]))
    pages = {p: (k, i, n) for k, i, n, p in index}
    total = 0
    for page in FAMOUS:
        if page not in pages and page != "கம்பராமாயணம்/பாயிரம்":
            print("WARN not in index:", page)
        verses = parse_verses(page)
        if not verses:
            print("WARN no verses:", page)
            continue
        kandam, idx, name = pages.get(page, ("பாயிரம்", 0, "பாயிரம்"))
        for n, sub, lines in verses:
            sec = {"kandam": kandam, "kandam_en": KANDAM_EN.get(kandam, kandam),
                   "padalam": name, "padalam_no": idx or None, "verse_no": n}
            if sub:
                sec["subsection"] = sub
            units.append(make_unit(
                WORK, WORK_EN, "verse", f"{name}/{n}" if n else f"{name}/x{len(units)}",
                sec, lines, True, ["ta.wikisource.org:" + page], author=AUTHOR,
                author_en=AUTHOR_EN, period=PERIOD, themes=["காப்பியம்", "இராமாயணம்"]))
        total += len(verses)
        print(f"{page}: {len(verses)} verses")
    print("verse units:", total)
    write_jsonl(os.path.join(KB, "kambaramayanam.jsonl"), units)


if __name__ == "__main__":
    main()
