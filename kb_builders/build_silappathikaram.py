"""Build data/kb/silappathikaram.jsonl.

- 30 canto (kaathai) chapter records with kandam + Tamil Wikipedia summary
  (verbatim_text false).
- One verbatim opening excerpt per canto from the ta.wikisource canto pages
  (unit_type verse, verbatim_text true), plus the pathigam.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (KB, clean_em_dashes, make_unit, nfc, strip_wikitext,
                    wp_extract, ws_wikitext, write_jsonl)

WORK = "சிலப்பதிகாரம்"
WORK_EN = "Silappathikaram"
AUTHOR = "இளங்கோவடிகள்"
AUTHOR_EN = "Ilango Adigal"
PERIOD = "c. 5th to 6th century CE (dating debated)"

CANTOS = [
    ("புகார்க் காண்டம்", 1, "மங்கல வாழ்த்துப் பாடல்", "1.மங்கல வாழ்த்துப் பாடல்"),
    ("புகார்க் காண்டம்", 2, "மனையறம்படுத்த காதை", "2.மனையறம்படுத்த காதை"),
    ("புகார்க் காண்டம்", 3, "அரங்கேற்று காதை", "3.அரங்கேற்று காதை"),
    ("புகார்க் காண்டம்", 4, "அந்திமாலைச் சிறப்புசெய் காதை", "4.அந்திமாலைச் சிறப்புசெய் காதை"),
    ("புகார்க் காண்டம்", 5, "இந்திரவிழவூரெடுத்த காதை", "5.இந்திரவிழவூரெடுத்த காதை"),
    ("புகார்க் காண்டம்", 6, "கடலாடு காதை", "6.கடலாடு காதை"),
    ("புகார்க் காண்டம்", 7, "கானல் வரி", "7.கானல் வரி"),
    ("புகார்க் காண்டம்", 8, "வேனிற் காதை", "8.வேனிற் காதை"),
    ("புகார்க் காண்டம்", 9, "கனாத்திறமுரைத்த காதை", "9.கனாத்திறமுரைத்த காதை"),
    ("புகார்க் காண்டம்", 10, "நாடுகாண் காதை", "10.நாடுகாண் காதை"),
    ("மதுரைக் காண்டம்", 11, "காடுகாண் காதை", "11.காடுகாண் காதை"),
    ("மதுரைக் காண்டம்", 12, "வேட்டுவ வரி", "12.வேட்டுவ வரி"),
    ("மதுரைக் காண்டம்", 13, "புறஞ்சேரியிறுத்த காதை", "13.புறஞ்சேரியிறுத்த காதை"),
    ("மதுரைக் காண்டம்", 14, "ஊர்காண் காதை", "14.ஊர்காண் காதை"),
    ("மதுரைக் காண்டம்", 15, "அடைக்கலக் காதை", "15.அடைக்கலக் காதை"),
    ("மதுரைக் காண்டம்", 16, "கொலைக்களக் காதை", "16.கொலைக்களக் காதை"),
    ("மதுரைக் காண்டம்", 17, "ஆய்ச்சியர் குரவை", "17.ஆய்ச்சியர் குரவை"),
    ("மதுரைக் காண்டம்", 18, "துன்ப மாலை", "18.துன்ப மாலை"),
    ("மதுரைக் காண்டம்", 19, "ஊர்சூழ் வரி", "19.ஊர்சூழ் வரி"),
    ("மதுரைக் காண்டம்", 20, "வழக்குரை காதை", "20.வழக்குரை காதை"),
    ("மதுரைக் காண்டம்", 21, "வஞ்சின மாலை", "21.வஞ்சின மாலை"),
    ("மதுரைக் காண்டம்", 22, "அழற்படு காதை", "22.அழற்படு காதை"),
    ("மதுரைக் காண்டம்", 23, "கட்டுரை காதை", "23.கட்டுரை காதை"),
    ("வஞ்சிக் காண்டம்", 24, "குன்றக் குரவை", "24.குன்றக் குரவை"),
    ("வஞ்சிக் காண்டம்", 25, "காட்சிக் காதை", "25.காட்சிக் காதை"),
    ("வஞ்சிக் காண்டம்", 26, "கால்கோட் காதை", "26.கால்கோட் காதை"),
    ("வஞ்சிக் காண்டம்", 27, "நீர்ப்படைக் காதை", "27.நீர்ப்படைக் காதை"),
    ("வஞ்சிக் காண்டம்", 28, "நடுகற் காதை", "28. நடுகற் காதை"),
    ("வஞ்சிக் காண்டம்", 29, "வாழ்த்துக் காதை", "29. வாழ்த்துக் காதை"),
    ("வஞ்சிக் காண்டம்", 30, "வரந்தரு காதை", "30. வரந்தரு காதை"),
]

KANDAM_EN = {"புகார்க் காண்டம்": "Puhar Kandam",
             "மதுரைக் காண்டம்": "Madurai Kandam",
             "வஞ்சிக் காண்டம்": "Vanji Kandam"}


def norm_name(s):
    return re.sub(r"[\s்]+", "", s)


_SECTIONS = None


def canto_sections():
    """Per-canto summary paragraphs from the main Tamil Wikipedia article."""
    global _SECTIONS
    if _SECTIONS is not None:
        return _SECTIONS
    from common import wp_full_extract
    e = wp_full_extract("சிலப்பதிகாரம்") or ""
    secs = {}
    heads = list(re.finditer(r"^=+ ?([^=\n]+?) ?=+$", e, re.M))
    for i, h in enumerate(heads):
        body = e[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(e)]
        body = nfc(body)
        if body:
            secs[norm_name(h.group(1))] = body
    _SECTIONS = secs
    return secs


def canto_summary(name):
    secs = canto_sections()
    import difflib
    key = norm_name(name)
    best, score = None, 0.0
    for k, v in secs.items():
        r = difflib.SequenceMatcher(None, k, key).ratio()
        if r > score:
            best, score = v, r
    if best and score >= 0.75:
        para = " ".join(x.strip() for x in best.split("\n") if x.strip())
        return clean_em_dashes(nfc(para[:900]))
    return None


def clean_line(raw):
    """Extract the original-text column from one wikitext line."""
    l = raw.strip()
    if (not l or l.startswith(("=", "{{", "{|", "|", "!", ";", "<!--", "----"))
            or l.startswith("[[") or l.startswith("*")):
        return None
    # dual-column layouts: keep original, drop word-split column
    l = re.split(r"\{\{green\|", l)[0]
    if "<FONT" in l or "<font" in l:
        l = re.split(r"<\s*[Ff][Oo][Nn][Tt]", l)[0]
    l = re.sub(r"<[^>]*>?", "", l)
    l = re.sub(r"'''|''", "", l)
    l = l.lstrip(":").rstrip("|").strip()
    l = re.split(r"\s{4,}", l)[0]
    l = re.sub(r"\[\d+\]\s*$", "", l)
    l = re.sub(r"[\s.]{2,}\d+\s*$", "", l)
    l = re.sub(r"\s+\d+\s*$", "", l)
    l = nfc(l)
    if not l or re.fullmatch(r"[\d\s.()\[\]]+", l):
        return None
    if l.startswith("(") and l.endswith(")"):
        return None
    if l.startswith("பாடல்") or l.endswith("ஆசிரியப்பா)"):
        return None
    # ordinal canto/kandam label lines, e.g. "முதற் காதை", "இரண்டாவது காதை"
    if len(l) < 30 and re.search(r"(காதை|காண்டம்|கருப்பம்)$", l) and " " in l:
        words = l.split()
        if len(words) <= 3 and not re.search(r"[,;.]", l):
            return None
    return l


def extract_excerpt(page_title, max_lines=30):
    wt = ws_wikitext(page_title)
    if not wt:
        return None
    wt = re.sub(r"<poem[^>]*>|</poem>", "", wt)
    wt = re.sub(r"\{\{தலை.*?\}\}", "", wt, flags=re.S)
    wt = re.sub(r"\{\{header.*?\}\}", "", wt, flags=re.S | re.I)
    # wikitable rows: keep the first cell (original text), split <br /> lines
    expanded = []
    for raw in wt.split("\n"):
        s = raw.strip()
        if s.startswith("|") and not s.startswith(("|-", "|}", "|+")):
            cell = s.lstrip("|").split("||")[0]
            cell = re.sub(r"<br\s*/?>", "\n", cell)
            expanded += cell.split("\n")
        else:
            expanded.append(raw)
    out = []
    for raw in expanded:
        l = clean_line(raw)
        if l is None:
            continue
        out.append(l)
        if len(out) >= max_lines:
            break
    return out or None


def table_first_col(tbl):
    rows = []
    for line in tbl.split("\n"):
        line = line.strip()
        if line.startswith("|") and not line.startswith(("|-", "|}", "!")):
            cell = line.lstrip("|").split("||")[0]
            rows.append(cell)
    return "\n".join(rows)


def main():
    units = []
    wp_main = wp_extract("சிலப்பதிகாரம்")
    for kandam, no, name, subpage in CANTOS:
        summary = canto_summary(name)
        if not summary:
            summary = (f"{WORK} {kandam} காதை {no}: {name}. "
                       f"சிலப்பதிகாரத்தின் முப்பது காதைகளில் இது ஒன்று.")
            src = ["ta.wikisource.org (canto structure)"]
        else:
            src = ["ta.wikipedia.org", "ta.wikisource.org (canto structure)"]
        units.append(make_unit(
            WORK, WORK_EN, "chapter", no,
            {"kandam": kandam, "kandam_en": KANDAM_EN[kandam],
             "kaathai": name, "kaathai_no": no},
            [summary], False, src, author=AUTHOR, author_en=AUTHOR_EN,
            period=PERIOD, themes=["காப்பியம்", "கண்ணகி", "கோவலன்"]))
    # pathigam excerpt
    pat = extract_excerpt("சிலப்பதிகாரம்/பதிகம்", max_lines=20)
    if pat:
        units.append(make_unit(
            WORK, WORK_EN, "verse", "பதிகம்",
            {"section_name": "பதிகம்", "note": "தொடக்கப் பகுதி (excerpt)"},
            pat, True,
            ["ta.wikisource.org:சிலப்பதிகாரம்/பதிகம்"], author=AUTHOR,
            author_en=AUTHOR_EN, period=PERIOD, themes=["காப்பியம்"]))
    got, miss = 0, []
    for kandam, no, name, subpage in CANTOS:
        title = f"சிலப்பதிகாரம்/{kandam}/{subpage}"
        exc = extract_excerpt(title)
        if not exc or len(exc) < 4:
            miss.append(name)
            continue
        got += 1
        units.append(make_unit(
            WORK, WORK_EN, "verse", no,
            {"kandam": kandam, "kaathai": name, "kaathai_no": no,
             "note": "காதையின் தொடக்கப் பகுதி (opening excerpt)"},
            exc, True, ["ta.wikisource.org:" + title], author=AUTHOR,
            author_en=AUTHOR_EN, period=PERIOD,
            themes=["காப்பியம்"]))
    print(f"canto excerpts: {got}/30; missing: {miss}")
    write_jsonl(os.path.join(KB, "silappathikaram.jsonl"), units)


if __name__ == "__main__":
    main()
