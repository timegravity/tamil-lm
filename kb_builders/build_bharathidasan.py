"""Build data/kb/bharathidasan.jsonl.

Bharathidasan (Kanaka Subburathinam, 1891-04-29 to 1964-04-21). Indian
copyright = life + 60 years, counted from 1 Jan following death: public
domain in India since 2025-01-01. Sources: Project Madurai UTF-8 etexts
  pmuni0037 அழகின் சிரிப்பு (poem collection, every poem)
  pmuni0166_01 புரட்சிக் கவிதைகள் பாகம் 2 (poem collection, every poem)
  pmuni0089 குடும்ப விளக்கு, pmuni0104 பாண்டியன் பரிசு (kaviyams: opening
  excerpt only)
Author profile from Tamil Wikipedia intro.
"""
import html as htmllib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (KB, clean_em_dashes, fetch_url, make_unit, nfc,
                    wp_extract, write_jsonl)

PM = "https://www.projectmadurai.org/pm_etexts/utf8/"
AUTHOR, AUTHOR_EN = "பாரதிதாசன்", "Bharathidasan"
PERIOD = "1891 to 1964 (20th century)"
THEMES = ["தமிழ்", "பகுத்தறிவு", "சமூக சீர்திருத்தம்"]


def pm_text_lines(fname):
    h = fetch_url(PM + fname, fname).replace("&nbsp;", " ")
    h = h[h.find("provided this header page is kept intact"):]
    h = re.sub(r"<br\b[^>\n]*>?", "\n", h, flags=re.I)
    h = re.sub(r"<(strong|b)\b[^>]*>", "\n@@H ", h, flags=re.I)
    h = re.sub(r"</(strong|b)>", " @@E\n", h, flags=re.I)
    h = re.sub(r"<h3\b[^>]*>", "\n@@H3 ", h, flags=re.I)
    h = re.sub(r"</h3>", " @@E\n", h, flags=re.I)
    h = htmllib.unescape(re.sub(r"<[^>\n]{0,120}>", "\n", h))
    return [nfc(x) for x in h.split("\n")]


def parse_collection(fname, work, work_en):
    lines = pm_text_lines(fname)
    poems = []
    cur = None
    started = False
    for l in lines:
        if not l:
            continue
        if "webpage" in l or "webmaster" in l or "This file" in l:
            break
        if l.startswith("@@H"):
            title = nfc(re.sub(r"@@H3?|@@E", "", l))
            if not title or "Acknowledg" in title or "Etext" in title:
                continue
            if re.match(r"^\d+\.\s*", title) or started:
                started = True
                if cur and len(cur["lines"]) >= 4:
                    poems.append(cur)
                cur = {"title": re.sub(r"^\d+\.\s*", "", title), "lines": []}
            continue
        if cur is None:
            continue
        if re.fullmatch(r"[-~=_]{3,}", l) or l == "@@E":
            continue
        cur["lines"].append(l.replace("@@E", "").strip())
    if cur and len(cur["lines"]) >= 4:
        poems.append(cur)
    units = []
    for i, p in enumerate(poems, 1):
        note = None
        if len(p["lines"]) > 120:  # long narrative section: keep an excerpt
            p["lines"] = p["lines"][:60]
            note = "தொடக்கப் பகுதி (opening excerpt of a long section)"
        units.append(make_unit(
            work, work_en, "poem", i,
            {"collection": work, "collection_en": work_en, "poem_no": i,
             "title": p["title"], **({"note": note} if note else {})},
            p["lines"], True, [PM + fname],
            author=AUTHOR, author_en=AUTHOR_EN, period=PERIOD, themes=THEMES))
    print(f"{work}: {len(units)} poems")
    return units


def parse_kaviyam_excerpt(fname, work, work_en, n_lines=40):
    lines = pm_text_lines(fname)
    out = []
    started = False
    for l in lines:
        if not l:
            continue
        if not started:
            if work in l:
                started = True
            continue
        if l.startswith("@@H") or "@@E" in l and len(l) < 40:
            continue
        if re.fullmatch(r"[-~=_]{3,}", l) or not re.search(r"[஀-௿]", l):
            continue
        if "webpage" in l:
            break
        out.append(l.replace("@@E", "").strip())
        if len(out) >= n_lines:
            break
    if len(out) < 8:
        print("WARN kaviyam excerpt failed", work)
        return []
    print(f"{work}: excerpt {len(out)} lines")
    return [make_unit(work, work_en, "verse", 1,
                      {"kaviyam": work, "note": "தொடக்கப் பகுதி (opening excerpt)"},
                      out, True, [PM + fname], author=AUTHOR, author_en=AUTHOR_EN,
                      period=PERIOD, themes=THEMES)]


def main():
    units = []
    ext = wp_extract("பாரதிதாசன்")
    prof = clean_em_dashes(nfc(ext or ""))[:1500] or (
        "பாரதிதாசன் (கனக சுப்புரத்தினம், 1891-1964): புதுச்சேரியில் பிறந்த தமிழ்க் கவிஞர்; புரட்சிக் கவிஞர் என அழைக்கப்பட்டவர்.")
    units.append(make_unit(
        "பாரதிதாசன் படைப்புகள்", "Works of Bharathidasan", "author_profile", None,
        {"born": "1891-04-29", "died": "1964-04-21", "birthplace": "புதுச்சேரி",
         "public_domain_india_from": "2025-01-01"},
        [prof], False, ["ta.wikipedia.org:பாரதிதாசன்"], author=AUTHOR,
        author_en=AUTHOR_EN, period=PERIOD, themes=THEMES))
    units += parse_collection("pmuni0037.html", "அழகின் சிரிப்பு", "Azhagin Sirippu")
    units += parse_collection("pmuni0166_01.html", "புரட்சிக் கவிதைகள்", "Puratchik Kavithaigal")
    units += parse_kaviyam_excerpt("pmuni0089.html", "குடும்ப விளக்கு", "Kudumba Vilakku")
    units += parse_kaviyam_excerpt("pmuni0104.html", "பாண்டியன் பரிசு", "Pandiyan Parisu")
    write_jsonl(os.path.join(KB, "bharathidasan.jsonl"), units)


if __name__ == "__main__":
    main()
