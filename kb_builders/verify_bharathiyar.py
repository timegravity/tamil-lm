#!/usr/bin/env python3
"""Cross-check data/kb/bharathiyar.jsonl (built from Project Madurai etexts)
against ta.wikisource.org as an independent second source.

Match rule: a unit is verified only if its full text, normalised to the bare
Tamil letter sequence (all whitespace, punctuation, digits and markup
removed), appears contiguously in the corresponding wikisource page. Units
that do not match stay verified_second_source=false. No text is modified.

Wikisource pages used (fetched as wikitext in batches of 50 via the API,
cached at data/raw/literature/ws_bharathiyar_texts.json):
  பாரதியாரின் தேசிய கீதங்கள்/N. ...      (per poem)
  பாரதியாரின் தெய்வப்பாடல்கள்/N. ...     (per poem)
  பாரதியாரின் பல்வகைப் பாடல்கள்/N. ...   (per poem)
  பாரதியாரின் ஞானப் பாடல்கள்             (one page)
  பாரதியாரின் சுயசரிதை                  (one page)
  கண்ணன் பாட்டு/N. ...                   (per poem)
  குயில் பாட்டு                          (one page)
  பாஞ்சாலி சபதம்/N. ...                  (per poem, 1..73)
  விநாயகர் நான்மணிமாலை                   (one page, if it exists)
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "data/kb/bharathiyar.jsonl"
PAGELIST = ROOT / "data/raw/literature/ws_bharathiyar_pages.json"
TEXTCACHE = ROOT / "data/raw/literature/ws_bharathiyar_texts.json"
API = "https://ta.wikisource.org/w/api.php"
UA = {"User-Agent": "tamil-lm-research/0.1 (contact: contact@timegravity.ai)"}

SERIES = {
    "தேசிய கீதங்கள்": "பாரதியாரின் தேசிய கீதங்கள்",
    "தெய்வப் பாடல்கள்": "பாரதியாரின் தெய்வப்பாடல்கள்",
    "பல்வகைப் பாடல்கள்": "பாரதியாரின் பல்வகைப் பாடல்கள்",
    "கண்ணன் பாட்டு": "கண்ணன் பாட்டு",
}
SINGLE = {
    "ஞானப் பாடல்கள்": "பாரதியாரின் ஞானப் பாடல்கள்",
    "சுயசரிதை": "பாரதியாரின் சுயசரிதை",
    "குயில் பாட்டு": "குயில் பாட்டு",
    # standalone விநாயகர் நான்மணிமாலை page does not exist on ta.wikisource;
    # the text lives at தெய்வப்பாடல்கள்/1
    "விநாயகர் நான்மணிமாலை":
        "பாரதியாரின் தெய்வப்பாடல்கள்/1. விநாயகர் நான்மணி மாலை",
}
PANCHALI = ("பாஞ்சாலி சபதம் முதற் பாகம்", "பாஞ்சாலி சபதம் இரண்டாம் பாகம்")

def norm(s):
    s = unicodedata.normalize("NFC", s)
    return "".join(ch for ch in s if "஀" <= ch <= "௿")

def api_get(params, post=False):
    import requests
    payload = {"format": "json", "formatversion": 2, **params}
    if post:
        r = requests.post(API, data=payload, headers=UA, timeout=60)
    else:
        r = requests.get(API, params=payload, headers=UA, timeout=60)
    r.raise_for_status()
    time.sleep(1)
    return r.json()

def allpages(prefix):
    out, cont = [], {}
    while True:
        d = api_get({"action": "query", "list": "allpages",
                     "apprefix": prefix, "aplimit": 500, **cont})
        out += [p["title"] for p in d["query"]["allpages"]]
        if "continue" in d:
            cont = {"apcontinue": d["continue"]["apcontinue"]}
        else:
            return out

def fetch_texts(titles):
    if TEXTCACHE.exists():
        cache = json.loads(TEXTCACHE.read_text(encoding="utf-8"))
    else:
        cache = {}
    todo = [t for t in titles if t not in cache]
    for i in range(0, len(todo), 50):
        batch = todo[i:i + 50]
        d = api_get({"action": "query", "prop": "revisions",
                     "rvslots": "main", "rvprop": "content",
                     "redirects": 1, "titles": "|".join(batch)}, post=True)
        for p in d["query"]["pages"]:
            if "revisions" in p:
                cache[p["title"]] = p["revisions"][0]["slots"]["main"]["content"]
            else:
                cache[p["title"]] = None
        for r in d["query"].get("redirects", []):
            cache[r["from"]] = cache.get(r["to"])
        print(f"fetched {min(i+50, len(todo))}/{len(todo)} pages")
        TEXTCACHE.write_text(json.dumps(cache, ensure_ascii=False),
                             encoding="utf-8")
    return cache

def subpage_map(pages, series):
    m = {}
    for t in pages:
        if t.startswith(series + "/"):
            mm = re.match(r"^(\d+)\.?\s*", t[len(series) + 1:])
            if mm:
                m[int(mm.group(1))] = t
    return m

def main():
    recs = [json.loads(l) for l in KB.open(encoding="utf-8")]

    pages = json.loads(PAGELIST.read_text(encoding="utf-8"))
    pages += allpages("கண்ணன் பாட்டு/")
    pages += allpages("பாஞ்சாலி சபதம்/")

    maps = {coll: subpage_map(pages, series)
            for coll, series in SERIES.items()}
    panchali_map = subpage_map(pages, "பாஞ்சாலி சபதம்")

    wanted = set(SINGLE.values())
    for m in maps.values():
        wanted |= set(m.values())
    wanted |= set(panchali_map.values())
    texts = fetch_texts(sorted(wanted))

    # குயில் பாட்டு is a PDF transclusion; use the rendered HTML instead
    for title, wt in list(texts.items()):
        if wt and "<pages index=" in wt:
            key = "rendered:" + title
            if key not in texts:
                d = api_get({"action": "parse", "page": title,
                             "redirects": 1})
                html_text = d.get("parse", {}).get("text", {})
                if isinstance(html_text, dict):
                    html_text = html_text.get("*", "")
                texts[key] = re.sub(r"<[^>]+>", " ", html_text or "")
                TEXTCACHE.write_text(json.dumps(texts, ensure_ascii=False),
                                     encoding="utf-8")
            texts[title] = texts[key]

    stats = {}
    for r in recs:
        r["verified_second_source"] = False
        r["sources"] = [s for s in r["sources"]
                        if not s.startswith("https://ta.wikisource.org")]
        coll = r["section"]["collection"]
        no = r["section"].get("no_in_collection")
        title = None
        if coll in maps and no in maps[coll]:
            title = maps[coll][no]
        elif coll in PANCHALI and no in panchali_map:
            title = panchali_map[no]
        elif coll in SINGLE:
            title = SINGLE[coll]
        stats.setdefault(coll, [0, 0, 0])  # verified, mismatched, no page
        ours = norm("".join(r["text"]))
        matched = None
        wt = texts.get(title) if title else None
        if wt and ours and ours in norm(wt):
            matched = title
        elif ours and len(ours) >= 60:
            # numbering differs between the PM and wikisource editions in
            # some collections (e.g. தெய்வப் பாடல்கள்); fall back to scanning
            # the sibling pages of the same series, then all fetched pages
            series = SERIES.get(coll)
            candidates = []
            if series:
                candidates = [t for t in texts
                              if t and t.startswith(series + "/")]
            elif coll in PANCHALI:
                candidates = [t for t in texts
                              if t and t.startswith("பாஞ்சாலி சபதம்/")]
            for t in candidates:
                w = texts.get(t)
                if w and ours in norm(w):
                    matched = t
                    break
        if matched:
            r["verified_second_source"] = True
            url = "https://ta.wikisource.org/wiki/" + matched.replace(" ", "_")
            r["sources"].append(url)
            stats[coll][0] += 1
        elif wt is None:
            stats[coll][2] += 1
        else:
            stats[coll][1] += 1

    with KB.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_v = sum(v for v, _, _ in stats.values())
    for coll, (v, mm, np_) in stats.items():
        print(f"{coll}: verified {v}, mismatched {mm}, no ws page {np_}")
    print(f"TOTAL verified: {total_v}/{len(recs)}")

if __name__ == "__main__":
    main()
