"""Build data/kb/thevaram_thiruvasagam.jsonl.

Thevaram: Project Madurai etexts pmuni0150 (T1), 0157 (T2), 0173 (T3)
  Sambandar; 0181 (T4), 0186 (T5), 0192 (T6) Appar; 0207 (T7) Sundarar.
  First PATHIGAMS_PER_MURAI pathigams of each thirumurai, every verse a unit.
Thiruvasagam: every section page under ta.wikisource 'திருவாசகம்/...',
  one unit per section (full text).
"""
import html as htmllib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import KB, fetch_url, make_unit, nfc, ws_wikitext, write_jsonl

PM = "https://www.projectmadurai.org/pm_etexts/utf8/"
PATHIGAMS_PER_MURAI = 12
MURAI = [  # file, thirumurai no, saint ta, saint en
    ("pmuni0150.html", 1, "திருஞானசம்பந்தர்", "Thirugnana Sambandar"),
    ("pmuni0157.html", 2, "திருஞானசம்பந்தர்", "Thirugnana Sambandar"),
    ("pmuni0173.html", 3, "திருஞானசம்பந்தர்", "Thirugnana Sambandar"),
    ("pmuni0181.html", 4, "திருநாவுக்கரசர்", "Thirunavukkarasar (Appar)"),
    ("pmuni0186.html", 5, "திருநாவுக்கரசர்", "Thirunavukkarasar (Appar)"),
    ("pmuni0192.html", 6, "திருநாவுக்கரசர்", "Thirunavukkarasar (Appar)"),
    ("pmuni0207.html", 7, "சுந்தரர்", "Sundarar"),
]
PERIOD_TH = "c. 7th to 8th century CE"


def parse_thevaram(fname, murai):
    h = fetch_url(PM + fname, fname).replace("&nbsp;", " ")
    parts = re.split(r'<a name="?dt\d+"?', h)
    out = []
    if len(parts) < 3:
        return parse_thevaram_by_ids(h, fname, murai)
    for p in parts[1:]:
        mh = re.search(r"<h3>(.*?)</h3>", p, re.S)
        if not mh:
            continue
        head = next((nfc(x) for x in re.sub(r"<[^>]+>", " ", mh.group(1)).split("\n") if nfc(x)), "")
        mnum = re.match(r"^(\d+)\.\s*(\d+)\.?\s*(.*)$", head)
        if not mnum:
            continue
        pno, place = int(mnum.group(2)), nfc(mnum.group(3))
        mpan = re.search(r"பண்\s*[-:]\s*([^<\n]+)", p)
        pan = nfc(mpan.group(1)) if mpan else None
        body = p[mh.end():]
        body = re.sub(r"<br\b[^>\n]*>?", "\n", body, flags=re.I)
        # verse id cells like <td valign=bottom>1.1.5</tr>
        body = re.sub(r"<td[^>]*valign=\"?bottom\"?[^>]*>\s*([\d.]+)", r"\n@@\1\n", body)
        body = re.sub(r"<[^>\n]{0,120}>", "\n", body)
        body = htmllib.unescape(body)
        cur = []
        verses = []
        for raw in body.split("\n"):
            l = nfc(raw)
            if not l:
                continue
            if l.startswith("@@"):
                vid = l[2:]
                if "." not in vid:
                    vid = f"{murai}.{pno}.{int(vid):02d}"
                if cur:
                    verses.append((vid, cur))
                cur = []
                continue
            if re.fullmatch(r"\d{1,3}\s*\.?", l) or l.startswith("பண்") or "திருச்சிற்றம்பலம்" in l:
                continue
            l = re.sub(r"^\d{1,3}\s*\.\s*", "", l)
            if "webpage" in l or "மின்பதிப்பு" in l:
                break
            cur.append(l)
        out.append((pno, place, pan, verses))
        if len(out) >= PATHIGAMS_PER_MURAI:
            break
    return out


def parse_thevaram_by_ids(h, fname, murai):
    """Files without per-pathigam anchors (T5): verse ids like 5.1.3 end lines,
    pathigam names come from the index list '5.001 கோயில் (1-11)'."""
    names = {int(m.group(1)): nfc(m.group(2))
             for m in re.finditer(r"\n\s*%d\.(\d{3})\s+([^(<\n]+)\(" % murai, h)}
    body = re.sub(r"<br\b[^>\n]*>?", "\n", h, flags=re.I)
    body = htmllib.unescape(re.sub(r"<[^>\n]{0,120}>", "\n", body))
    paths = {}
    cur = []
    started = False
    for raw in body.split("\n"):
        l = nfc(raw)
        if not l:
            continue
        m = re.match(r"^(.*?)\s*%d\.(\d+)\.(\d+)\s*$" % murai, l)
        if m:
            started = True
            if nfc(m.group(1)):
                cur.append(nfc(m.group(1)))
            pno = int(m.group(2))
            paths.setdefault(pno, []).append((f"{murai}.{pno}.{m.group(3)}", cur))
            cur = []
            continue
        if not started:
            continue
        if re.fullmatch(r"\d{1,2}\.?", l) or "திருச்சிற்றம்பலம்" in l or l.startswith("பண்"):
            continue
        if "webpage" in l or "webmaster" in l:
            break
        cur.append(re.sub(r"^\d{1,3}\s*\.\s*", "", l))
    out = []
    for pno in sorted(paths)[:PATHIGAMS_PER_MURAI]:
        out.append((pno, names.get(pno), None, paths[pno]))
    return out


def build_thevaram():
    units = []
    for fname, murai, saint, saint_en in MURAI:
        paths = parse_thevaram(fname, murai)
        nv = 0
        for pno, place, pan, verses in paths:
            for vid, lines in verses:
                if len(lines) < 2:
                    continue
                units.append(make_unit(
                    "தேவாரம்", "Thevaram", "verse", vid,
                    {"thirumurai": murai, "pathigam_no": pno, "pathigam": place,
                     "pan": pan, "saint": saint, "saint_en": saint_en},
                    lines, True, [PM + fname], author=saint, author_en=saint_en,
                    period=PERIOD_TH, themes=["சைவம்", "பக்தி", "பன்னிரு திருமுறை"]))
                nv += 1
        print(f"Thirumurai {murai} ({saint_en}): {len(paths)} pathigams, {nv} verses")
    return units


def build_thiruvasagam():
    idx = ws_wikitext("திருவாசகம்")
    pages = re.findall(r"\[\[/([^/\]|]+)/?\]\]", idx)
    units = []
    for i, name in enumerate(pages, 1):
        name = nfc(name.replace("_", " "))
        title = "திருவாசகம்/" + name
        wt = ws_wikitext(title)
        if not wt:
            print("WARN missing", title)
            continue
        lines = []
        for blk in re.finditer(r"<poem[^>]*>(.*?)</poem>", wt, re.S):
            for raw in blk.group(1).split("\n"):
                l = re.sub(r"\{\{Pline\|\d+\|?r?\}\}|\{\{[^}]*\}\}|<[^>]+>|'{2,3}", "", raw)
                l = re.sub(r"\s+\d{1,3}\s*$", "", l)
                l = nfc(l)
                if l and not re.fullmatch(r"[\d\s.]+", l):
                    lines.append(l)
        if not lines:
            # plain layout
            body = re.sub(r"\{\{[^}]*\}\}|<[^>]+>|'{2,3}", "", wt)
            for raw in body.split("\n"):
                l = nfc(re.sub(r"\s+\d{1,3}\s*$", "", raw))
                if l and not l.startswith(("=", "[[", "|", "{", "----")) and not re.fullmatch(r"[\d\s.]+", l):
                    lines.append(l)
        if len(lines) < 4:
            print("WARN short", title, len(lines))
            continue
        units.append(make_unit(
            "திருவாசகம்", "Thiruvasagam", "verse", i,
            {"section_name": name, "section_no": i, "thirumurai": 8,
             "saint": "மாணிக்கவாசகர்", "saint_en": "Manikkavasagar",
             "line_count": len(lines)},
            lines, True, ["ta.wikisource.org:" + title],
            author="மாணிக்கவாசகர்", author_en="Manikkavasagar",
            period="c. 9th century CE", themes=["சைவம்", "பக்தி", "பன்னிரு திருமுறை"]))
    print(f"Thiruvasagam: {len(units)} sections of {len(pages)}")
    return units


def main():
    units = build_thevaram() + build_thiruvasagam()
    write_jsonl(os.path.join(KB, "thevaram_thiruvasagam.jsonl"), units)


if __name__ == "__main__":
    main()
