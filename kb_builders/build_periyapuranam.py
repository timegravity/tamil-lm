"""Build data/kb/periyapuranam.jsonl.

- 63 Nayanmar episode records: list (name, kulam, nadu, pusai nal) from the
  Tamil Wikipedia table 'நாயன்மார் பட்டியல்', life summary = intro paragraph
  of each Nayanar's Tamil Wikipedia article (verbatim_text false).
- Sample verses: all verses of Project Madurai pmuni0209 (Kandam 1,
  Sarukkam 1-2: பாயிரம், திருமலைச் சிறப்பு, தடுத்தாட்கொண்ட புராணம்,
  தில்லைவாழ் அந்தணர் சருக்கம்), one unit per verse, verbatim.
"""
import html as htmllib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (KB, WP_API, WS_CACHE, clean_em_dashes, fetch_url,
                    make_unit, nfc, wp_extract, ws_wikitext, write_jsonl)

PM = "https://www.projectmadurai.org/pm_etexts/utf8/pmuni0209.html"
WORK, WORK_EN = "பெரியபுராணம்", "Periyapuranam"
AUTHOR, AUTHOR_EN = "சேக்கிழார்", "Sekkizhar"
PERIOD = "c. 12th century CE"
WP_CACHE = os.path.join(WS_CACHE, "..", "wp_pages")
os.makedirs(WP_CACHE, exist_ok=True)


def nayanmar_table():
    wt = ws_wikitext("நாயன்மார் பட்டியல்", api=WP_API, cache_dir=WP_CACHE)
    rows = []
    for row in wt.split("|-")[1:]:
        cells = [c for c in re.split(r"\n\|+\s*\|?|\|\|", row)]
        cells = [nfc(re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|align=\"left\"\|?", "", c, flags=re.S))
                 for c in cells]
        cells = [c for c in cells if c]
        if not cells or not re.fullmatch(r"\d{1,2}", cells[0]):
            continue
        m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cells[1])
        if not m:
            continue
        article, short = nfc(m.group(1)), nfc(m.group(2) or m.group(1))
        def plain(c):
            return nfc(re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", c))
        rows.append({"no": int(cells[0]), "article": article, "name": short,
                     "kulam": plain(cells[2]) if len(cells) > 2 else None,
                     "nadu": plain(cells[3]) if len(cells) > 3 else None,
                     "pusai_nal": plain(cells[4]) if len(cells) > 4 else None})
    return rows


def pm_verses():
    h = fetch_url(PM, "pmuni0209.html").replace("&nbsp;", " ")
    parts = re.split(r'<a name="?dt\d+"?', h)
    out = []
    for p in parts[1:]:
        mh = re.search(r"<h3>(.*?)</h3>", p, re.S)
        if not mh:
            continue
        head = next((nfc(x) for x in re.sub(r"<[^>]+>", " ", mh.group(1)).split("\n") if nfc(x)), "")
        mnum = re.match(r"^(\d+)\.\s*(\d+)\.?\s*(.*)$", head)
        if not mnum:
            continue
        sarukkam, pno, title = int(mnum.group(1)), int(mnum.group(2)), nfc(mnum.group(3))
        body = p[mh.end():]
        body = re.sub(r"<br\b[^>\n]*>?", "\n", body, flags=re.I)
        body = re.sub(r"<td[^>]*valign=\"?bottom\"?[^>]*>\s*([\d.]+)", r"\n@@\1\n", body)
        body = htmllib.unescape(re.sub(r"<[^>\n]{0,120}>", "\n", body))
        cur = []
        for raw in body.split("\n"):
            l = nfc(raw)
            if not l:
                continue
            if l.startswith("@@"):
                if cur:
                    out.append((sarukkam, pno, title, l[2:], cur))
                cur = []
                continue
            if re.fullmatch(r"\d{1,3}\s*\.?", l):
                continue
            if "webpage" in l or "webmaster" in l:
                break
            cur.append(re.sub(r"^\d{1,3}\s*\.?\s+", "", l))
    return out


SARUKKAM = {1: "திருமலைச் சருக்கம்", 2: "தில்லைவாழ் அந்தணர் சருக்கம்"}


def main():
    units = []
    rows = nayanmar_table()
    print("nayanmar rows:", len(rows))
    got = 0
    for r in rows:
        ext = wp_extract(r["article"])
        if ext:
            para = clean_em_dashes(nfc(ext.split("\n")[0]))[:1200]
            src = ["ta.wikipedia.org:" + r["article"], "ta.wikipedia.org:நாயன்மார் பட்டியல்"]
            got += 1
        else:
            para = f"{r['name']}: பெரிய புராணத்தில் கூறப்படும் அறுபத்து மூன்று நாயன்மார்களில் ஒருவர் (எண் {r['no']})."
            src = ["ta.wikipedia.org:நாயன்மார் பட்டியல்"]
        sec = {"nayanar_no": r["no"], "nayanar": r["name"], "article": r["article"]}
        for k in ("kulam", "nadu", "pusai_nal"):
            if r.get(k):
                sec[k] = r[k]
        units.append(make_unit(
            WORK, WORK_EN, "episode", r["no"], sec, [para], False, src,
            author=AUTHOR, author_en=AUTHOR_EN, period=PERIOD,
            themes=["சைவம்", "நாயன்மார்", "பக்தி"]))
    print(f"wikipedia summaries: {got}/{len(rows)}")
    verses = pm_verses()
    for sarukkam, pno, title, vid, lines in verses:
        if len(lines) < 2:
            continue
        units.append(make_unit(
            WORK, WORK_EN, "verse", vid,
            {"kandam": 1, "sarukkam_no": sarukkam, "sarukkam": SARUKKAM.get(sarukkam),
             "puranam_no": pno, "puranam": title}, lines, True, [PM],
            author=AUTHOR, author_en=AUTHOR_EN, period=PERIOD,
            themes=["சைவம்", "நாயன்மார்", "பக்தி"]))
    print("verses:", len(verses))
    write_jsonl(os.path.join(KB, "periyapuranam.jsonl"), units)


if __name__ == "__main__":
    main()
