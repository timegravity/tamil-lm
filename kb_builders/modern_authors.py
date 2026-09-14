"""Build data/kb/modern_authors.jsonl (tier 3: modern Tamil authors).

Copyright rule: modern authors are copyrighted. This builder stores ONLY
author profiles and plot/work summaries written in our own words from
Tamil and English Wikipedia content. verbatim_text is false on every record.

Stages:
  fetch  - pull author + work pages from ta/en Wikipedia API, cache raw JSON
           under data/raw/literature/wiki_authors/ (1 request/second).
  digest - write compact per-author digest text files (intro + plot section)
           for a human to read before authoring the summary prose.
  build  - assemble records from kb_builders/modern_authors_content.py
           (hand-written prose based on the digests), validate, write jsonl.

Usage: .venv/bin/python kb_builders/modern_authors.py [fetch|digest|build|all]
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "literature", "wiki_authors")
DIGESTS = os.path.join(RAW, "digests")
KB_OUT = os.path.join(ROOT, "data", "kb", "modern_authors.jsonl")
UA = "tamil-lm-research/0.1 (contact: contact@timegravity.ai)"
HEADERS = {"User-Agent": UA}

API = {
    "ta": "https://ta.wikipedia.org/w/api.php",
    "en": "https://en.wikipedia.org/w/api.php",
}

_last_req = {"t": 0.0}


def nfc(s):
    if s is None:
        return None
    return unicodedata.normalize("NFC", s)


def throttle():
    dt = time.time() - _last_req["t"]
    if dt < 1.0:
        time.sleep(1.0 - dt)
    _last_req["t"] = time.time()


def api_get(lang, params, cache_name):
    """GET from the wiki API with caching of the raw JSON response."""
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, cache_name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    throttle()
    r = requests.get(API[lang], params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def safe_name(s):
    return re.sub(r"[^\w஀-௿-]+", "_", s)[:80]


def fetch_extract(lang, title, key):
    """Fetch full plain-text extract for a title (with redirect + search fallback).

    Returns dict {title, url, extract} or None if the page does not exist.
    """
    params = {
        "action": "query", "format": "json", "prop": "extracts",
        "explaintext": 1, "redirects": 1, "titles": title, "exlimit": 1,
    }
    cache = f"{lang}_{safe_name(key)}.json"
    data = api_get(lang, params, cache)
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if "missing" in page or not page.get("extract"):
        # search fallback
        sparams = {
            "action": "query", "format": "json", "list": "search",
            "srsearch": title, "srlimit": 1,
        }
        sdata = api_get(lang, sparams, f"{lang}_{safe_name(key)}_search.json")
        hits = sdata.get("query", {}).get("search", [])
        if not hits:
            return None
        hit_title = hits[0]["title"]
        params["titles"] = hit_title
        data = api_get(lang, params, f"{lang}_{safe_name(key)}_hit.json")
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "missing" in page or not page.get("extract"):
            return None
    real_title = page.get("title", title)
    url = f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(
        real_title.replace(" ", "_"))
    return {"title": real_title, "url": url, "extract": nfc(page["extract"])}


# key: (ta title guess, en title guess)
AUTHOR_PAGES = {
    "kalki": ("கல்கி கிருஷ்ணமூர்த்தி", "Kalki Krishnamurthy"),
    "jayakanthan": ("ஜெயகாந்தன்", "Jayakanthan"),
    "sujatha": ("சுஜாதா (எழுத்தாளர்)", "Sujatha (writer)"),
    "pudhumaipithan": ("புதுமைப்பித்தன்", "Pudhumaipithan"),
    "akilan": ("அகிலன்", "Akilan"),
    "mu_va": ("மு. வரதராசன்", "M. Varadarajan"),
    "na_parthasarathy": ("நா. பார்த்தசாரதி", "Na. Parthasarathy"),
    "indira_parthasarathy": ("இந்திரா பார்த்தசாரதி", "Indira Parthasarathy"),
    "ashokamitran": ("அசோகமித்திரன்", "Ashokamitran"),
    "ki_rajanarayanan": ("கி. ராஜநாராயணன்", "Ki. Rajanarayanan"),
    "thi_janakiraman": ("தி. ஜானகிராமன்", "T. Janakiraman"),
    "la_sa_ramamirtham": ("லா. ச. ராமாமிருதம்", "La. Sa. Ramamirtham"),
    "devan": ("தேவன் (எழுத்தாளர்)", "Devan (writer)"),
    "sandilyan": ("சாண்டில்யன்", "Sandilyan"),
    "balakumaran": ("பாலகுமாரன்", "Balakumaran"),
    "sivasankari": ("சிவசங்கரி", "Sivasankari"),
    "anuthama": ("அனுத்தமா", "Anuthama"),
    "rajam_krishnan": ("ராஜம் கிருஷ்ணன்", "Rajam Krishnan"),
    "vaali": ("வாலி (கவிஞர்)", "Vaali (poet)"),
    "kannadasan": ("கண்ணதாசன்", "Kannadasan"),
    "mu_metha": ("மு. மேத்தா", "Mu. Metha"),
    "sundara_ramaswamy": ("சுந்தர ராமசாமி", "Sundara Ramaswamy"),
    "bharathidasan": ("பாரதிதாசன்", "Bharathidasan"),
    "jeyamohan": ("ஜெயமோகன்", "Jeyamohan"),
}

# author key -> list of (work key, ta title guess or None, en title guess or None)
WORK_PAGES = {
    "kalki": [
        ("ponniyin_selvan", "பொன்னியின் செல்வன்", "Ponniyin Selvan"),
        ("sivagamiyin_sabatham", "சிவகாமியின் சபதம்", "Sivagamiyin Sabatham"),
        ("parthiban_kanavu", "பார்த்திபன் கனவு", "Parthiban Kanavu"),
        ("alai_osai", "அலை ஓசை", "Alai Osai"),
    ],
    "jayakanthan": [
        ("sila_nerangalil", "சில நேரங்களில் சில மனிதர்கள்",
         "Sila Nerangalil Sila Manidhargal (novel)"),
        ("oru_manithan", "ஒரு மனிதன் ஒரு வீடு ஒரு உலகம்",
         "Oru Manithan Oru Veedu Oru Ulagam"),
        ("unnaipol_oruvan", "உன்னைப்போல் ஒருவன் (புதினம்)", None),
    ],
    "sujatha": [
        ("en_iniya_iyanthira", "என் இனிய இயந்திரா", "En Iniya Iyanthira"),
        ("srirangathu_devathaigal", "ஸ்ரீரங்கத்து தேவதைகள்",
         "Srirangathu Devathaigal"),
        ("kanavu_thozhirchalai", "கனவுத் தொழிற்சாலை", None),
    ],
    "pudhumaipithan": [
        ("kadavulum_kandasami", "கடவுளும் கந்தசாமிப்பிள்ளையும்", None),
        ("saba_vimosanam", "சாப விமோசனம்", None),
        ("ponnagaram", "பொன்னகரம் (சிறுகதை)", None),
    ],
    "akilan": [
        ("vengaiyin_maindhan", "வேங்கையின் மைந்தன்", "Vengaiyin Maindhan"),
        ("chithirappavai", "சித்திரப்பாவை", "Chithirappavai"),
        ("pavai_vilakku", "பாவை விளக்கு", "Pavai Vilakku"),
    ],
    "mu_va": [
        ("agal_vilakku", "அகல் விளக்கு (புதினம்)", None),
        ("karithundu", "கரித்துண்டு", None),
        ("petra_manam", "பெற்ற மனம்", None),
    ],
    "na_parthasarathy": [
        ("kurinji_malar", "குறிஞ்சி மலர் (புதினம்)", "Kurinji Malar"),
        ("samudaya_veedhi", "சமுதாய வீதி", None),
        ("aathmavin_ragangal", "ஆத்மாவின் ராகங்கள்", None),
    ],
    "indira_parthasarathy": [
        ("kuruthippunal", "குருதிப்புனல்", "Kuruthippunal"),
        ("ramanujar_play", "ராமானுஜர் (நாடகம்)", "Ramanujar (play)"),
    ],
    "ashokamitran": [
        ("thanneer", "தண்ணீர் (புதினம்)", "Thanneer (novel)"),
        ("18th_parallel", "பதினெட்டாவது அட்சக்கோடு", "The 18th Parallel"),
        ("karaindha_nizhalgal", "கரைந்த நிழல்கள்", None),
    ],
    "ki_rajanarayanan": [
        ("gopalla_gramam", "கோபல்ல கிராமம்", "Gopalla Grammam"),
        ("gopallapurathu_makkal", "கோபல்லபுரத்து மக்கள்", None),
    ],
    "thi_janakiraman": [
        ("mogamul", "மோகமுள்", "Mogamul"),
        ("amma_vandhal", "அம்மா வந்தாள்", "Amma Vandhal"),
        ("sembaruthi", "செம்பருத்தி (புதினம்)", None),
    ],
    "la_sa_ramamirtham": [
        ("sindhanadhi", "சிந்தாநதி", None),
        ("apitha", "அபிதா (புதினம்)", None),
        ("putra", "புத்ர", None),
    ],
    "devan": [
        ("thuppariyum_sambu", "துப்பறியும் சாம்பு", "Thuppariyum Sambu"),
        ("justice_jagannathan", "ஜஸ்டிஸ் ஜகந்நாதன்", None),
        ("mister_vedantham", "மிஸ்டர் வேதாந்தம்", None),
    ],
    "sandilyan": [
        ("kadal_pura", "கடல் புறா", "Kadal Pura"),
        ("yavana_rani", "யவன ராணி", "Yavana Rani"),
        ("mannan_magal", "மன்னன் மகள்", None),
    ],
    "balakumaran": [
        ("mercury_pookkal", "மெர்க்குரி பூக்கள்", "Mercury Pookkal"),
        ("udaiyar", "உடையார் (புதினம்)", "Udaiyar (novel)"),
        ("irumbu_kudhiraigal", "இரும்புக் குதிரைகள்", "Irumbu Kudhiraigal"),
    ],
    "sivasankari": [
        ("47_natkal", "47 நாட்கள்", "47 Natkal"),
        ("palangal", "பாலங்கள் (புதினம்)", None),
    ],
    "anuthama": [],
    "rajam_krishnan": [
        ("kurinjithen", "குறிஞ்சித் தேன்", "Kurinjithen"),
        ("verukku_neer", "வேருக்கு நீர்", "Verukku Neer"),
        ("karippu_manigal", "கரிப்பு மணிகள்", None),
    ],
    "vaali": [
        ("pandavar_bhoomi", "பாண்டவர் பூமி", None),
        ("ramanuja_kaviyam", "இராமானுச காவியம்", None),
    ],
    "kannadasan": [
        ("arthamulla_indhu_matham", "அர்த்தமுள்ள இந்து மதம்",
         "Arthamulla Indhu Matham"),
        ("yesu_kaviyam", "இயேசு காவியம்", "Yesu Kaviyam"),
        ("cheraman_kadhali", "சேரமான் காதலி", "Cheraman Kadhali"),
    ],
    "mu_metha": [
        ("kanneer_pookkal", "கண்ணீர்ப் பூக்கள்", None),
        ("oorvalam", "ஊர்வலம் (கவிதை நூல்)", None),
    ],
    "sundara_ramaswamy": [
        ("puliyamarathin_kathai", "ஒரு புளிய மரத்தின் கதை",
         "Oru Puliya Marathin Kathai"),
        ("jj_sila_kurippugal", "ஜே. ஜே. சில குறிப்புகள்",
         "J. J. Silakurippukal"),
    ],
    "bharathidasan": [
        ("azhagin_sirippu", "அழகின் சிரிப்பு", None),
        ("pandiyan_parisu", "பாண்டியன் பரிசு", None),
        ("kudumba_vilakku", "குடும்ப விளக்கு", None),
    ],
    "jeyamohan": [
        ("vishnupuram", "விஷ்ணுபுரம் (புதினம்)", "Vishnupuram"),
        ("venmurasu", "வெண்முரசு", "Venmurasu"),
    ],
}

PLOT_HEADINGS = re.compile(
    r"^==+\s*(Plot|Story|Storyline|Synopsis|Summary|Plot summary|"
    r"கதை|கதைச் சுருக்கம்|கதைச்சுருக்கம்|கதைச் சுருக்கம|கதை சுருக்கம்|"
    r"கதாபாத்திரங்கள்|உள்ளடக்கம்)\s*==+\s*$",
    re.IGNORECASE | re.MULTILINE)


def sections(extract):
    """Split a plain-text extract into (heading, body) pairs; '' = intro."""
    parts = re.split(r"^(==+[^=\n]+==+)\s*$", extract, flags=re.MULTILINE)
    out = [("", parts[0])]
    for i in range(1, len(parts) - 1, 2):
        head = parts[i].strip("= \t")
        out.append((head, parts[i + 1]))
    return out


def digest_text(extract, is_work):
    secs = sections(extract)
    intro = secs[0][1].strip()
    chunks = [intro[:1400 if is_work else 2600]]
    if is_work:
        for head, body in secs[1:]:
            if re.search(r"plot|story|synopsis|summary|கதை|உள்ளடக்கம்",
                         head, re.IGNORECASE):
                chunks.append(f"[{head}] " + body.strip()[:2600])
    else:
        for head, body in secs[1:]:
            if re.search(r"works|படைப்புகள்|நூல்கள்|awards|விருது|இலக்கிய",
                         head, re.IGNORECASE):
                chunks.append(f"[{head}] " + body.strip()[:900])
    return "\n\n".join(c for c in chunks if c.strip())


def fetch_and_digest():
    os.makedirs(DIGESTS, exist_ok=True)
    manifest = {}
    for key, (ta_t, en_t) in AUTHOR_PAGES.items():
        entry = {"author": {}, "works": {}}
        lines = [f"### AUTHOR {key}"]
        for lang, title in (("ta", ta_t), ("en", en_t)):
            if not title:
                continue
            res = fetch_extract(lang, title, f"author_{key}")
            if res is None:
                lines.append(f"[{lang}] MISSING: {title}")
                entry["author"][lang] = None
                continue
            entry["author"][lang] = {"title": res["title"], "url": res["url"]}
            lines.append(f"[{lang}] {res['title']} <{res['url']}>")
            lines.append(digest_text(res["extract"], is_work=False))
        for wkey, wta, wen in WORK_PAGES.get(key, []):
            lines.append(f"\n### WORK {key}/{wkey}")
            got = False
            for lang, title in (("ta", wta), ("en", wen)):
                if not title:
                    continue
                res = fetch_extract(lang, title, f"work_{key}_{wkey}")
                if res is None:
                    lines.append(f"[{lang}] MISSING: {title}")
                    continue
                got = True
                entry["works"].setdefault(wkey, {})[lang] = {
                    "title": res["title"], "url": res["url"]}
                lines.append(f"[{lang}] {res['title']} <{res['url']}>")
                lines.append(digest_text(res["extract"], is_work=True))
            if not got:
                lines.append("NO PAGE FOUND on either wiki")
        with open(os.path.join(DIGESTS, f"{key}.txt"), "w") as f:
            f.write("\n".join(lines))
        manifest[key] = entry
        print(f"digested {key}: works found "
              f"{sorted(entry['works'])}", flush=True)
    with open(os.path.join(RAW, "manifest.json"), "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


def validate(rec):
    required = ["work", "work_en", "tier", "unit_type", "number", "section",
                "text", "verbatim_text", "urai", "translation_en",
                "transliteration", "themes", "author", "author_en", "period",
                "sources", "verified_second_source"]
    for k in required:
        assert k in rec, f"missing field {k}: {rec.get('work_en')}"
    assert rec["tier"] == 3
    assert rec["verbatim_text"] is False, "tier 3 must not be verbatim"
    assert rec["unit_type"] in ("author_profile", "episode")
    assert isinstance(rec["text"], list) and rec["text"], "text must be a list"
    for para in rec["text"]:
        assert isinstance(para, str) and para.strip()
    blob = json.dumps(rec, ensure_ascii=False)
    assert "\u2014" not in blob, f"em dash in record {rec.get('work_en')}"
    return rec


def deep_nfc(x):
    if isinstance(x, str):
        return unicodedata.normalize("NFC", x)
    if isinstance(x, list):
        return [deep_nfc(v) for v in x]
    if isinstance(x, dict):
        return {deep_nfc(k): deep_nfc(v) for k, v in x.items()}
    return x


def build():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from modern_authors_content import RECORDS
    with open(KB_OUT, "w") as f:
        for rec in RECORDS:
            rec = deep_nfc(rec)
            validate(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    profiles = sum(1 for r in RECORDS if r["unit_type"] == "author_profile")
    episodes = sum(1 for r in RECORDS if r["unit_type"] == "episode")
    print(f"wrote {len(RECORDS)} records to {KB_OUT} "
          f"({profiles} author_profile, {episodes} episode)")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    if stage in ("fetch", "digest", "all"):
        fetch_and_digest()
    if stage in ("build", "all"):
        build()
