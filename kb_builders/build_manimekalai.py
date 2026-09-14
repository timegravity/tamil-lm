"""Build data/kb/manimekalai.jsonl.

Source: Project Madurai pmuni0141 (complete moolam, canto headers as <h3>),
ta.wikisource 'மணிமேகலை' page cached as second reference (not cross-checked).
30 canto chapter records (verbatim_text false) + one verbatim opening excerpt
per canto + pathigam excerpt. Tamil Wikipedia has no per-canto articles; the
overall story paragraph from 'மணிமேகலை (காப்பியம்)' is stored once as an
episode record.
"""
import html as htmllib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (KB, clean_em_dashes, fetch_url, make_unit, nfc,
                    wp_full_extract, write_jsonl)

PM = "https://www.projectmadurai.org/pm_etexts/utf8/pmuni0141.html"
WORK, WORK_EN = "மணிமேகலை", "Manimekalai"
AUTHOR, AUTHOR_EN = "சீத்தலைச் சாத்தனார்", "Sithalai Sathanar"
PERIOD = "c. 6th century CE (dating debated)"
EXCERPT = 25


def canto_blocks():
    h = fetch_url(PM, "pmuni0141.html").replace("&nbsp;", " ")
    parts = re.split(r"<h3>", h)
    blocks = []
    for p in parts[1:]:
        m = re.match(r"\s*<font[^>]*>\s*(.*?)</font>\s*</h3>(.*)", p, re.S)
        if not m:
            continue
        title = nfc(re.sub(r"<[^>]+>", "", m.group(1)))
        body = m.group(2)
        body = re.sub(r"<td valign=bottom>[^<]*", "", body)
        body = re.sub(r"<br\b[^>\n]*>?", "\n", body, flags=re.I)
        body = re.sub(r"<[^>\n]{0,120}>", "", body)
        body = htmllib.unescape(body)
        lines = []
        for raw in body.split("\n"):
            l = nfc(re.sub(r"[\s.\-]{2,}[0-9\-]{1,7}\s*$", "", raw))
            if not l or re.fullmatch(r"[\d\s.\-]+", l) or "முற்றிற்று" in l:
                continue
            if "webpage" in l or "webmaster" in l:
                break
            lines.append(l)
        blocks.append((title, lines))
    return blocks


def main():
    units = []
    blocks = canto_blocks()
    cantos = []
    pathigam = None
    for title, lines in blocks:
        m = re.match(r"^(\d{1,2})?\.?\s*(.*க\S*தை)\s*$", title)
        if m:
            cantos.append((m.group(1), nfc(m.group(2)), lines))
        elif "பதிகம்" in title:
            pathigam = lines
    # fill missing numbers by order (one header lacks its number)
    numbered = []
    for i, (n, name, lines) in enumerate(cantos, 1):
        numbered.append((int(n) if n else i, name, lines))
    assert len(numbered) == 30, [c[:2] for c in numbered]
    story = wp_full_extract("மணிமேகலை (காப்பியம்)") or ""
    ms = re.search(r"^=+ ?கதை ?=+\n(.*?)(?=^=+ )", story, re.S | re.M)
    if ms:
        units.append(make_unit(
            WORK, WORK_EN, "episode", 0, {"section_name": "கதைச் சுருக்கம்"},
            [clean_em_dashes(nfc(" ".join(x.strip() for x in ms.group(1).split("\n") if x.strip())))],
            False, ["ta.wikipedia.org:மணிமேகலை (காப்பியம்)"], author=AUTHOR,
            author_en=AUTHOR_EN, period=PERIOD, themes=["காப்பியம்", "பௌத்தம்"]))
    for n, name, lines in numbered:
        units.append(make_unit(
            WORK, WORK_EN, "chapter", n,
            {"kaathai": name, "kaathai_no": n, "line_count": len(lines)},
            [f"மணிமேகலை காதை {n}: {name}. மணிமேகலைக் காப்பியத்தின் முப்பது காதைகளில் ஒன்று; இக்காதை {len(lines)} அடிகள் கொண்டது. "
             "தமிழ் விக்கிப்பீடியாவில் தனிக் காதைச் சுருக்கம் இல்லை."],
            False, [PM + " (canto structure)"], author=AUTHOR, author_en=AUTHOR_EN,
            period=PERIOD, themes=["காப்பியம்", "பௌத்தம்"]))
    if pathigam:
        units.append(make_unit(
            WORK, WORK_EN, "verse", "பதிகம்",
            {"section_name": "பதிகம்", "note": "தொடக்கப் பகுதி (excerpt)"},
            pathigam[:EXCERPT], True, [PM], author=AUTHOR, author_en=AUTHOR_EN,
            period=PERIOD, themes=["காப்பியம்"]))
    for n, name, lines in numbered:
        units.append(make_unit(
            WORK, WORK_EN, "verse", n,
            {"kaathai": name, "kaathai_no": n,
             "note": "காதையின் தொடக்கப் பகுதி (opening excerpt)"},
            lines[:EXCERPT], True, [PM], author=AUTHOR, author_en=AUTHOR_EN,
            period=PERIOD, themes=["காப்பியம்"]))
    write_jsonl(os.path.join(KB, "manimekalai.jsonl"), units)


if __name__ == "__main__":
    main()
