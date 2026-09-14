"""Build the dictionary retrieval pack (serving side only; nothing trains).

  .venv/bin/python build_pack_dictionary.py             # fetch (cached, resumable) and build data/packs/dictionary/
  .venv/bin/python build_pack_dictionary.py --no-fetch  # rebuild from the cache in data/raw/packs/dictionary only
  .venv/bin/python build_pack_dictionary.py --fetch-only

Sources and the licence decision for each are in data/packs/dictionary/LICENSES.md. In short:

  ta.wiktionary   the 2026-09-01 pages-articles dump (CC BY-SA 4.0, read from the wiki's own siteinfo
                  rightsinfo API). Tamil headwords with Tamil meanings and English glosses (ta-en), and
                  English headwords with Tamil meanings (en-ta).
  en.wiktionary   every page in Category:Tamil lemmas, fetched through the MediaWiki API (CC BY-SA 4.0).
                  Tamil headwords with English meanings (ta-en); the English glosses are inverted into
                  en-ta rows as a second, derived source.
  DSAL            the University of Chicago editions of the Tamil Lexicon, Winslow and Fabricius were
                  checked and are NOT used: the Lexicon page carries CC BY-NC-ND 2.0, the Winslow page
                  carries no licence statement, and the Fabricius edition there is the 1972 revision.
                  The archive.org scans of the public-domain originals were checked too; their OCR text
                  is unusable. The pages are fetched and cached so the quotes in LICENSES.md are reproducible.

CPU only: no model, no embeddings, no family-safe scan (the coordinator runs the pack scan over
chunks_unscanned.jsonl) and no index. Fetch helpers are imported from build_pack_cooking.py (same
User-Agent, same request gap, same cache_json and html_to_text).
"""
import argparse, bz2, collections, hashlib, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build_pack_cooking as C   # _get, api, rightsinfo, cache_json, html_to_text, normalise_dashes, UA, MIN_GAP

PACK = os.path.join(ROOT, "data", "packs", "dictionary")
CACHE = os.path.join(ROOT, "data", "raw", "packs", "dictionary")
C.CACHE = CACHE                  # cache_json reads the module global at call time; nothing in the cooking cache is touched
EVAL_200 = os.path.join(ROOT, "eval", "dictionary_common_200.jsonl")
VERSION = "2026-09-10"
LICENSE = "CC BY-SA 4.0"

TAWIKT_DUMP = "20260901"
DUMP_URL = ("https://dumps.wikimedia.org/tawiktionary/%s/tawiktionary-%s-pages-articles.xml.bz2"
            % (TAWIKT_DUMP, TAWIKT_DUMP))
DUMP_PATH = os.path.join(CACHE, os.path.basename(DUMP_URL))
EN_PAGES = os.path.join(CACHE, "enwiktionary_tamil_lemmas.jsonl")
EN_STATE = os.path.join(CACHE, "enwiktionary_tamil_lemmas.state.json")
EN_CATEGORY = "Category:Tamil lemmas"

DSAL_PAGES = {
    "tamil-lex": "https://dsal.uchicago.edu/dictionaries/tamil-lex/",
    "winslow": "https://dsal.uchicago.edu/dictionaries/winslow/",
    "fabricius": "https://dsal.uchicago.edu/dictionaries/fabricius/",
    "about": "https://dsal.uchicago.edu/about.html",
    "ddsa_about": "https://dsal.uchicago.edu/dictionaries/about.html",
    "footer": "https://dsal.uchicago.edu/revamp/dico_footer_include.html",
}
ARCHIVE_ITEMS = ["tamil-lexicon", "winslow-a-comprehensive-tamil-and-english-dictionary",
                 "AcomprehensiveTamilandEnglishDictionaryofHighandLowTamil",
                 "bim_eighteenth-century_a-dictionary-malabar-an_1779"]
ARCHIVE_OCR_SAMPLES = {   # (item, file, byte range): a 4 KB slice of the OCR text, enough to judge it
    "tamil-lexicon": ("Tamil Lexicon-1939_djvu.txt", 1000000),
    "AcomprehensiveTamilandEnglishDictionaryofHighandLowTamil":
        ("AcomprehensiveTamilandEnglishDictionaryofHighandLowTamil_djvu.txt", 4000000),
    "winslow-a-comprehensive-tamil-and-english-dictionary":
        ("Winslow, A comprehensive Tamil and English Dictionary (1862)_djvu.txt", 3000000),
}

TA = r"\u0b80-\u0bff"
TA_RE = re.compile("[" + TA + "]")
LAT_RE = re.compile(r"[A-Za-z]")
LATIN_TITLE = re.compile(r"^[A-Za-z][A-Za-z' \-]*$")

# ---------------------------------------------------------------- fetch (all cached, all resumable)

def _get_range(url, start, length):
    """Byte-range GET with the project User-Agent and the same request gap as build_pack_cooking._get
    (which has no Range support). Used only for the archive.org OCR samples."""
    gap = C.MIN_GAP - (time.time() - C._last[0])
    if gap > 0:
        time.sleep(gap)
    req = urllib.request.Request(url, headers={"User-Agent": C.UA, "Range": "bytes=%d-%d" % (start, start + length)})
    with urllib.request.urlopen(req, timeout=90) as r:
        body = r.read().decode("utf-8", "replace")
    C._last[0] = time.time()
    return body

def _meta(html, name):
    m = re.search(r'<meta\s+name="%s"\s+content="([^"]*)"' % re.escape(name), html, re.I)
    return m.group(1) if m else None

def fetch_licences():
    """Licence evidence, read from each source itself and cached verbatim."""
    ri = C.cache_json("rightsinfo.json", lambda: {
        "ta.wiktionary.org": C.rightsinfo("ta.wiktionary.org"),
        "en.wiktionary.org": C.rightsinfo("en.wiktionary.org"),
        "verified_on": VERSION})
    def dsal():
        out = {}
        for k, url in DSAL_PAGES.items():
            html = C._get(url)
            out[k] = {"url": url, "text": C.html_to_text(html),
                      "cc_links": sorted(set(re.findall(r'href="(https?://creativecommons\.org/[^"]+)"', html))),
                      "dc_rights": _meta(html, "DC.Rights"), "fetched_on": VERSION}
        return out
    ds = C.cache_json("dsal_pages.json", dsal)
    def archive():
        out = {}
        for item in ARCHIVE_ITEMS:
            d = json.loads(C._get("https://archive.org/metadata/" + item))
            md = d.get("metadata", {})
            out[item] = {k: md.get(k) for k in ("identifier", "title", "date", "licenseurl", "rights", "publisher", "language")}
            out[item]["files"] = [f["name"] for f in d.get("files", []) if f["name"].endswith((".txt", ".pdf"))]
            if item in ARCHIVE_OCR_SAMPLES:
                fn, start = ARCHIVE_OCR_SAMPLES[item]
                url = "https://archive.org/download/%s/%s" % (item, urllib.parse.quote(fn))
                out[item]["ocr_sample"] = {"file": fn, "byte_offset": start, "text": _get_range(url, start, 3000)}
        return out
    ar = C.cache_json("archive_org_items.json", archive)
    return ri, ds, ar

def download_dump():
    if os.path.exists(DUMP_PATH):
        return
    os.makedirs(CACHE, exist_ok=True)
    tmp = DUMP_PATH + ".part"
    req = urllib.request.Request(DUMP_URL, headers={"User-Agent": C.UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(tmp, DUMP_PATH)

def fetch_en_wiktionary():
    """Every page in Category:Tamil lemmas with its wikitext, 50 pages per request, resumable through
    the API continue token kept in EN_STATE."""
    os.makedirs(CACHE, exist_ok=True)
    state = json.load(open(EN_STATE)) if os.path.exists(EN_STATE) else {"continue": None, "done": False, "pages": 0}
    if state["done"]:
        return state["pages"]
    with open(EN_PAGES, "a", encoding="utf-8") as out:
        while True:
            p = {"action": "query", "generator": "categorymembers", "gcmtitle": EN_CATEGORY, "gcmnamespace": 0,
                 "gcmlimit": 50, "prop": "revisions", "rvprop": "content", "rvslots": "main", "formatversion": 2}
            if state["continue"]:
                p.update(state["continue"])
            d = C.api("en.wiktionary.org", p)
            for pg in d.get("query", {}).get("pages", []):
                revs = pg.get("revisions") or []
                if not revs:
                    continue
                out.write(json.dumps({"pageid": pg["pageid"], "title": pg["title"],
                                      "content": revs[0]["slots"]["main"]["content"]}, ensure_ascii=False) + "\n")
                state["pages"] += 1
            out.flush()
            state["continue"] = d.get("continue")
            state["done"] = not state["continue"]
            json.dump(state, open(EN_STATE, "w"), indent=1)
            if state["done"]:
                break
            if state["pages"] % 1000 < 50:
                print("  en.wiktionary pages so far:", state["pages"], flush=True)
    return state["pages"]

# ---------------------------------------------------------------- wikitext cleaning

CITE_TPL = re.compile(r"^(?:[\u0b80-\u0bff]+\.(?:\s*[\u0b80-\u0bff]+\.)*|\(W\.\)|Loc\.|W\.|Tp\.|Loc\. Tp\.)$")

def strip_markup(s, title):
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"<ref[^>/]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\[\[(?:File|Image|படிமம்|பகுப்பு|Category|கோப்பு):[^\[\]]*(?:\[\[[^\]]*\]\][^\[\]]*)*\]\]", "", s)
    s = s.replace("{{PAGENAME}}", title).replace("{{pagename}}", title)
    for _ in range(3):
        s = re.sub(r"\[\[([^\[\]|]*)\|([^\[\]]*)\]\]", r"\2", s)
        s = re.sub(r"\[\[([^\[\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    s = s.replace("&nbsp;", " ")
    return s

def ta_template(m):
    inner = m.group(1)
    name = inner.split("|")[0].strip()
    if name in ("ஆங்கி", "ஆங்", "ஆங்கிலம்"):
        return "ஆங்கிலம்"
    if CITE_TPL.match(name):
        return "(" + name + ")"
    return ""

def clean_ta(s, title):
    s = strip_markup(s, title)
    for _ in range(4):
        s = re.sub(r"\{\{([^{}]*)\}\}", ta_template, s)
    return tidy(s, title)

def tidy(s, title):
    s = C.normalise_dashes(s)
    s = re.sub(r"^[\s#*:;]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[\s,;:\-.)]+|[\s,;:\-(]+$", "", s).strip()
    s = s.replace("((", "(").replace("))", ")").replace("( ", "(").replace(" )", ")")
    if not s or not re.search(r"[\w\u0b80-\u0bff]", s) or s == title:
        return ""
    if re.fullmatch(r"[.\s…]+", s):
        return ""
    return s

def script_of(text):
    t = len(TA_RE.findall(text)); l = len(LAT_RE.findall(text))
    return "ta" if t >= l else "en"

# ---------------------------------------------------------------- Tamil Wiktionary (dump)

LANG_NAMES = {"ஆங்கிலம்": "en", "தமிழ்": "ta"}
OTHER_LANG_NAMES = set("""பிரெஞ்சு எசுப்பானியம் ஜெர்மன் இத்தாலியம் இடாய்ச்சு மலகாசியம் இந்தி மலையாளம் தெலுங்கு கன்னடம் சமசுகிருதம்
சமஸ்கிருதம் வடமொழி உருது அரபு அரபி சிங்களம் இலத்தீன் லத்தீன் கிரேக்கம் சப்பானியம் யப்பானியம் ஜப்பானியம் சீனம் போர்த்துகீசம்
போர்த்துக்கீசம் உருசியம் ரஷ்யம் ரசியம் எஸ்பெராண்டோ மலாய் இந்தோனேசியம் துருக்கியம் பாரசீகம் பாலி பிராகிருதம் கொரியம் டச்சு
ஒல்லாந்தம் சுவீடியம் பின்னியம் வியட்நாமியம் தாய் வங்காளம் வங்காளி குசராத்தி மராத்தி பஞ்சாபி நேபாளி ஒடியா அசாமியம் துளு
கொங்கணி இந்தோனேசியன் எபிரேயம் ஹீப்ரு பிரஞ்சு ஸ்பானிஷ் ஜெர்மானியம் கிரேக்கு""".split())
LANG_CODE = {"ta": "ta", "en": "en", "தமி": "ta", "ஆங்": "en", "ஆங்கில": "en", "ஆங்கிலம்": "en", "தமிழ்": "ta"}
LANG_MARK = re.compile(r"^==\s*(.*?)\s*==\s*$|\{\{=([^=}|]+)=(?:\|[^}]*)?\}\}|\{\{ஆங்தலை\}\}|\{\{மொழி\|([a-z\-]+)\}\}", re.M)

def lang_segments(text):
    """Split a page into (lang, text) at its language headers. lang is 'ta', 'en', 'other' or None for
    the text before the first header. Level-2 headings that are section names, not languages, are left in
    place."""
    segs = []; last = 0; cur = None
    for m in LANG_MARK.finditer(text):
        lang = None
        if m.group(2) is not None:
            lang = LANG_CODE.get(m.group(2).strip(), "other")
        elif m.group(3) is not None:
            lang = LANG_CODE.get(m.group(3), "other")
        elif m.group(0).startswith("{{ஆங்தலை"):
            lang = "en"
        else:
            h = m.group(1)
            if "மொழிபெயர்ப்பு" in h:
                continue
            hm = re.search(r"\{\{மொழி\|([a-z\-]+)\}\}", h)
            if hm:
                lang = LANG_CODE.get(hm.group(1), "other")
            else:
                hh = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", h).strip()
                hh = re.sub(r"\{\{PAGENAME\}\}|<[^>]+>|[()]", "", hh).strip()
                if hh in LANG_NAMES:
                    lang = LANG_NAMES[hh]
                elif hh in OTHER_LANG_NAMES:
                    lang = "other"
                else:
                    continue
        segs.append((cur, text[last:m.start()]))
        cur = lang; last = m.end()
    segs.append((cur, text[last:]))
    return segs

POS_TA = {
    "பெயர்ச்சொல்": "noun", "பெ": "noun", "பெயர்ச்சொல்-பகுப்பு": "noun", "பெயர்ச்சொற்கள்": "noun", "பெயர்ச் சொல்": "noun",
    "பெயர்ச் சொற்கள்": "noun", "பெயர்": "noun", "பெயர்ச்சொல்-பகு": "noun",
    "வினைச்சொல்": "verb", "வி": "verb", "வினைச்சொல்-பகுப்பு": "verb", "வினைச்சொற்கள்": "verb", "தனிவினைச்சொற்கள்": "verb",
    "வினை": "verb", "வினைச் சொல்": "verb",
    "உரிச்சொல்": "adjective", "பெயரடை": "adjective", "பெயருரிச்சொல்": "adjective", "உரிச்சொற்கள்": "adjective",
    "பெயரடைகள்": "adjective", "பெயர் உரிச்சொல்": "adjective", "பெயருரிச்சொற்கள்": "adjective", "உரி": "adjective",
    "வினையடை": "adverb", "வினையுரிச்சொல்": "adverb", "வினையடைகள்": "adverb", "வினையுரிச்சொற்கள்": "adverb",
    "பிரதிப்பெயர்": "pronoun", "சுட்டுப்பெயர்": "pronoun", "பிரதிப்பெயர்கள்": "pronoun", "பிரதிப் பெயர்": "pronoun",
    "இடைச்சொல்": "particle", "இடைச்சொற்கள்": "particle", "சுட்டுப்பெயர்கள்": "pronoun", "பெயருரிச்சொல்-பகுப்பு": "adjective",
}
POS_TA_RE = re.compile(r"\{\{(" + "|".join(sorted(map(re.escape, POS_TA), key=len, reverse=True)) + r")(?:\|[^}]*)?\}\}"
                       r"|^=+\s*\{?\{?(" + "|".join(sorted(map(re.escape, POS_TA), key=len, reverse=True)) + r")\}?\}?\s*=+\s*$"
                       r"|\[\[பகுப்பு:(?:ஆங்கிலம்-)?(" + "|".join(sorted(map(re.escape, POS_TA), key=len, reverse=True)) + r")\]\]", re.M)
MEANING_MARK = ("பொருள்", "சொல்:", "பொருள்:")
TRANS_MARK = ("பெயர்ப்பு", "பிறமொழிகளில்")      # மொழிபெயர்ப்பு, மொழிப்பெயர்ப்புகள், பெயர்ப்பு-மேல், மொழிபெயர்ப்பு-மேல் ...
KEEP_TPL = ("ஆங்கி", "ஆங்", "ஆங்கிலம்")
OTHER_MARK = {"விளக்கம்", "சொல்வளம்", "சொல் வளப்பகுதி", "சொல்வளப் பகுதி", "ஒத்த சொற்கள்", "தொடர்புடையச் சொற்கள்",
              "ஆதாரங்கள்", "ஆதாரம்", "தமிழ்-ஆதா", "தமிழ்ஆதாரங்கள்", "ஆதாரங்கள்-மொழி", "ஆதாரங்கள்-தஇககலை",
              "சித்தமருத்துவஅகராதி", "விக்கிபீடியா", "விக்கிப்பீடியா", "இலக்கணமை", "உசாத்துணை", "ஒத்த கருத்துள்ள சொற்கள்",
              "பார்க்க", "குறிப்புகள்", "இவற்றையும் பார்க்க", "சொல்வளம்3", "தமிழில் விளக்கவும்", "விரிவாக்குக",
              "மொழிபெயர்ப்புகளைச்சேர்", "எதிர்ச்சொற்கள்", "ஒப்பீடு", "சொற்பிறப்பியல்", "சொற்தோற்றம்", "சொற்பிறப்பு",
              "இணைச்சொற்கள்", "தொடர்புடைய சொற்கள்", "தொடர்புச் சொற்கள்", "படங்கள்", "ஒலிப்பு", "பலுக்கல்", "மருத்துவ குணங்கள்",
              "அறிவியல் பெயர்", "தொடர்புடையவை", "தகவலாதாரம்", "ஆங்கில ஆதாரங்கள்", "வரியமை", "gallery"}
LABEL_WORDS = set(POS_TA) | set(POS_TA.values()) | OTHER_MARK | set(MEANING_MARK) | {
    "பயன்பாடு", "எடுத்துக்காட்டு", "எடுத்துக்காட்டுகள்", "மொழிபெயர்ப்புகள்", "மொழிபெயர்ப்பு", "ஆங்கிலம்", "வினை", "பெயர்",
    "வரியமை", "இலக்கியமை", "மேற்கோள்", "மேற்கோள்கள்", "சொற்றொடர் எடுத்துக்காட்டு", "சொற்றொடர் பயன்பாடு"}
EXAMPLE_MARK = ("பயன்பாடு", "வரியமை", "இலக்கியமை", "எ. கா.", "எ.கா", "எ.கா.", "சொற்றொடர்", "எடுத்துக்காட்டு", "மேற்கோள்", "இலக்கியப் பயன்பாடு", "வாக்கியப் பயன்பாடு")
EN_LABEL = re.compile(r"ஆங்கிலம்|\{\{ஆங்கி\}\}|\{\{ஆங்\}\}|\{\{சிறு-மொழி\|en\}\}|\{\{en\}\}|^\s*[*#:]*\s*\(?english\)?\s*[:\-]", re.I)
# main-namespace pages that are not dictionary entries: the main page and its subpages, appendix and
# project pages kept under a title prefix, help and template pages
NON_ENTRY = re.compile(r"^(முதற் பக்கம்|முதற்பக்கம்|விக்சனரி|மீடியாவிக்கி|உதவி:|பகுப்பு:|வார்ப்புரு:|படிமம்:|பின்னிணைப்பு|பயனர்:|Wiktionary|Main Page)")
POS_LINK_RE = re.compile(r"\[\[(" + "|".join(sorted(map(re.escape, POS_TA), key=len, reverse=True)) + r")\|")
POS_EN_TAG = {"noun": "noun", "n": "noun", "verb": "verb", "v": "verb", "adjective": "adjective", "adj": "adjective",
              "adverb": "adverb", "adv": "adverb", "pronoun": "pronoun", "pro": "pronoun", "pron": "pronoun"}
POS_EN_TAG_RE = re.compile(r"\[\[(noun|verb|adjective|adverb|pronoun)\|[^\]]*\]\]|''\s*\[?\[?(n|v|adj|adv|pro|pron)\.?\s*\]?\]?''")
SLUR_CAT = re.compile(r"\[\[பகுப்பு:\s*(வசைச்சொற்கள்|ஆபாசச் சொற்கள்|இழிசொற்கள்)\s*\]\]")

def parse_ta_wiktionary_page(title, text, want_lang):
    """One entry from a Tamil Wiktionary page: meanings, English glosses (when want_lang is 'ta'),
    examples, part of speech. want_lang 'ta' means a Tamil headword page, 'en' an English headword page
    whose meanings are Tamil."""
    segs = lang_segments(text)
    langs = {l for l, _ in segs if l}
    if want_lang in langs:
        body = "\n".join(t for l, t in segs if l in (want_lang, None))
    elif not langs:
        body = text
    else:
        return None
    pos = None; pos_raw = ""
    m = POS_TA_RE.search(body) or POS_LINK_RE.search(body)
    if m:
        pos_raw = next(g for g in m.groups() if g)
        pos = POS_TA[pos_raw]
    else:
        m = POS_EN_TAG_RE.search(body)
        if m:
            pos_raw = next(g for g in m.groups() if g)
            pos = POS_EN_TAG[pos_raw.lower()]
    meanings, glosses, examples = [], [], []
    state = "pre"; sub = None
    for raw in body.split("\n"):
        s = raw.strip()
        if not s:
            continue
        is_heading = bool(re.match(r"^=+.*=+$", s))
        # labels: headings, templates, <u>pseudo headings</u> and bold-only lines such as '''எடுத்துக்காட்டுகள்'''
        labels = [re.sub(r"[=\[\]{}]", "", s).strip()] if is_heading else []
        # only the templates that lead the line change the state; a {{பெ}} after a translation does not
        lead = re.match(r"^[#*:\s]*((?:\{\{[^{}]*\}\}[\s:,]*)+)", s)
        labels += [x.strip() for x in re.findall(r"\{\{([^{}|]+)(?:\|[^{}]*)?\}\}", lead.group(1))] if lead else []
        if re.search(r"\{\{எ\.\s*கா\.?\}\}", s) and not lead and s.startswith(("#", "*")):
            # "# meaning {{எ.கா}} example" on one line
            before, after = re.split(r"\{\{எ\.\s*கா\.?\}\}", s, maxsplit=1)
            v = clean_ta(before, title); ex = clean_ta(after, title)
            if v and state in ("pre", "meaning"):
                meanings.append(v)
            if ex and 4 <= len(ex) <= 300:
                examples.append(ex)
            continue
        labels += [tidy(strip_markup(x, title), title) for x in re.findall(r"<u>(.*?)</u>", s)]
        if re.fullmatch(r"[#*:\s]*'''[^']*'''", s):
            labels.append(tidy(strip_markup(s, title), title))
        new_state = None
        for lab in labels:
            if any(k in lab for k in TRANS_MARK):
                new_state = "trans"; sub = None
            elif any(lab.startswith(k) or lab == k for k in EXAMPLE_MARK):
                new_state = "example"
            elif lab in MEANING_MARK or lab in POS_TA or lab.rstrip(":") in MEANING_MARK:
                new_state = "meaning"
            elif lab.startswith("சிறு-மொழி"):
                sub = "en" if lab == "சிறு-மொழி" and "{{சிறு-மொழி|en}}" in s else "other"
            elif lab in OTHER_MARK or (is_heading and lab not in KEEP_TPL):
                new_state = "other"
        if new_state:
            state = new_state
        if is_heading:
            continue
        # the remainder of the line once the structural markers are gone
        content = re.sub(r"\{\{(?!" + "|".join(re.escape(k) + r"\}" for k in KEEP_TPL) + r"|PAGENAME|[\u0b80-\u0bff]+\.)[^{}|]+(?:\|[^{}]*)?\}\}", "", s)
        content = re.sub(r"<u>.*?</u>", "", content)
        if re.fullmatch(r"[#*:\s]*'''[^']*'''", s) and new_state:
            content = ""
        s = content.strip()
        if not tidy(clean_ta(s, title), title):
            continue
        if state in ("pre", "meaning"):
            if s.startswith(("#:", "#*")):
                ex = clean_ta(s, title)
                if ex and 4 <= len(ex) <= 300:
                    examples.append(ex)
            elif re.search(r"'''|\{\{PAGENAME\}\}|^" + re.escape(title) + r"\b", s) and not s.startswith("#"):
                # headword line such as '''word''' - short gloss, or '''word''' = (forms)
                rest = re.split(r"\s[-:]\s", clean_ta(s, title), maxsplit=1)
                if len(rest) == 2 and tidy(rest[1], title):
                    meanings.append(tidy(rest[1], title))
            elif s.startswith("#") or ((state == "meaning" or want_lang == "en") and s.startswith(("*", ":"))):
                v = clean_ta(s, title)
                if v and (re.search(r"[\u0b80-\u0bff]", v) or want_lang == "ta" and LAT_RE.search(v)) and not re.fullmatch(r"\(?[A-Za-z .]+\)?", v):
                    meanings.append(v)
            elif state == "meaning" and want_lang == "en" and not re.search(r"\{\{|^=", s):
                v = clean_ta(s, title)
                if v and TA_RE.search(v) and len(v) < 200:
                    meanings.append(v)
        elif state == "trans":
            if want_lang != "ta":
                continue
            if EN_LABEL.search(s):
                sub = "en"
                rest = EN_LABEL.split(s, maxsplit=1)[-1]
                rest = re.sub(r"^[\s:\-\u2013\u2014)*#]+", "", rest)
                v = clean_ta(rest, title)
                if v and LAT_RE.search(v):
                    glosses.append(v)
                continue
            if s.startswith("*"):
                # a language label line ("*[[இந்தி]]: ...", "*<small>சீனம்</small>", "*Bosnian: ...") unless it is
                # a plain Latin gloss under the English label
                plain = clean_ta(s, title)
                if TA_RE.search(plain) or re.match(r"^[A-Z][A-Za-z ,()\-]*:", plain) or sub != "en":
                    sub = "other"; continue
                if LAT_RE.search(plain):
                    glosses.append(plain)
                continue
            if sub == "en" and s.startswith(("#", ":")):
                v = clean_ta(s, title)
                if v and LAT_RE.search(v) and not TA_RE.search(v):
                    glosses.append(v)
        elif state == "example":
            if s.startswith(("#", "*", ":")):
                ex = clean_ta(s, title)
                if ex and 4 <= len(ex) <= 300:
                    examples.append(ex)
    ok = lambda v: v not in LABEL_WORDS and not (v.startswith("(") and v.endswith(")") and len(v) < 16)
    meanings = dedupe(m for m in meanings if ok(m))[:12]
    glosses = dedupe(g for g in glosses if g not in ("..", "...") and len(g) < 200 and ok(g))[:8]
    examples = dedupe(e for e in examples if e not in meanings and ok(e))[:3]
    if not meanings and not glosses:
        return None
    return {"pos": pos or "other", "pos_raw": pos_raw, "meanings": meanings, "glosses_en": glosses, "examples": examples}

def dedupe(xs):
    seen = set(); out = []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def iter_dump(path):
    ns = "{http://www.mediawiki.org/xml/export-0.11/}"
    with bz2.open(path, "rb") as f:
        for _, el in ET.iterparse(f):
            if el.tag.endswith("}page"):
                if el.find(ns + "ns").text == "0":
                    t = el.find(ns + "title").text
                    txt = el.find(ns + "revision").find(ns + "text").text or ""
                    yield t, txt
                el.clear()

def build_ta_wiktionary(stats):
    """Both directions from the dump: Tamil headwords (ta-en) and English headwords (en-ta)."""
    rows = []
    seen = 0
    for title, text in iter_dump(DUMP_PATH):
        seen += 1
        if seen % 100000 == 0:
            print("  dump pages:", seen, flush=True)
        lt = text.lstrip()
        if lt.lower().startswith("#redirect") or lt.startswith("#வழிமாற்று"):
            stats["ta.wiktionary/redirects"] += 1; continue
        if SLUR_CAT.search(text):
            stats["ta.wiktionary/skipped_marked_slur"] += 1; continue
        if NON_ENTRY.search(title) or "/" in title:
            stats["ta.wiktionary/skipped_non_entry_page"] += 1; continue
        if re.search(r"[,;]$", title) or (title.endswith(".") and title.count(".") == 1 and " " not in title and len(title) > 6):
            stats["ta.wiktionary/skipped_punctuated_title"] += 1; continue
        if TA_RE.search(title):
            if re.search(r"[A-Za-z]", title):
                stats["ta.wiktionary/skipped_mixed_title"] += 1; continue
            want = "ta"
        elif LATIN_TITLE.match(title):
            want = "en"
        else:
            stats["ta.wiktionary/skipped_other_title"] += 1; continue
        stats["ta.wiktionary/pages_seen_" + want] += 1
        e = parse_ta_wiktionary_page(title, text, want)
        if not e:
            stats["ta.wiktionary/no_meaning_" + want] += 1; continue
        url = "https://ta.wiktionary.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        meanings = e["meanings"] + (["ஆங்கிலம்: " + ", ".join(e["glosses_en"])] if e["glosses_en"] else [])
        word = title
        if want == "ta" and re.search(r"[஀-௿]\d$", title):
            word = title[:-1]        # homonym pages are numbered (பால்2); the headword itself carries no digit
            stats["ta.wiktionary/homonym_digit_stripped"] += 1
        rows.append({"word": word, "script": want if want == "ta" else "latin", "direction": "ta-en" if want == "ta" else "en-ta",
                     "pos": e["pos"], "pos_raw": e["pos_raw"], "meanings": meanings, "examples": e["examples"], "translit": "",
                     "glosses_en": e["glosses_en"], "source": "ta.wiktionary", "url": url, "license": LICENSE,
                     "edition": "dump " + TAWIKT_DUMP})
    stats["ta.wiktionary/pages_total"] = seen
    return rows

# ---------------------------------------------------------------- English Wiktionary (API cache)

POS_EN = {"noun": "noun", "proper noun": "noun", "verb": "verb", "adjective": "adjective", "adverb": "adverb",
          "pronoun": "pronoun", "particle": "particle", "numeral": "other", "number": "other", "postposition": "other",
          "interjection": "other", "conjunction": "other", "determiner": "other", "suffix": "other", "prefix": "other",
          "phrase": "other", "proverb": "other", "idiom": "other", "adjectival noun": "adjective", "root": "other",
          "letter": "other", "symbol": "other", "prepositional phrase": "other", "contraction": "other", "affix": "other",
          "classifier": "other", "ordinal number": "other", "preposition": "other", "infix": "other"}
FORM_OF = {"alt form": "alternative form of", "alternative form of": "alternative form of", "alt sp": "alternative spelling of",
           "alternative spelling of": "alternative spelling of", "altform": "alternative form of", "syn of": "synonym of",
           "synonym of": "synonym of", "abbreviation of": "abbreviation of", "abbr of": "abbreviation of", "clipping of": "clipping of",
           "short for": "short for", "obsolete form of": "obsolete form of", "archaic form of": "archaic form of",
           "dated form of": "dated form of", "nonstandard form of": "nonstandard form of", "misspelling of": "misspelling of",
           "ellipsis of": "ellipsis of", "contraction of": "contraction of", "pronunciation spelling of": "pronunciation spelling of",
           "standard form of": "standard form of", "former name of": "former name of", "plural of": "plural of",
           "obsolete spelling of": "obsolete spelling of", "dialectal form of": "dialectal form of", "honorific form of": "honorific form of",
           "colloquial form of": "colloquial form of", "diminutive of": "diminutive of", "female equivalent of": "female equivalent of",
           "eye dialect of": "eye dialect of", "informal form of": "informal form of", "verbal noun of": "verbal noun of",
           "ta-verbal noun of": "verbal noun of", "alt case": "alternative letter-case form of", "rare form of": "rare form of",
           "rare spelling of": "rare spelling of", "less common spelling of": "less common spelling of"}

def en_template(m):
    inner = m.group(1)
    parts = inner.split("|")
    name = parts[0].strip()
    pos = [p for p in parts[1:] if "=" not in p]
    named = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    if name in ("lb", "label", "lbl", "tlb"):
        return "(" + ", ".join(x for x in pos[1:] if x and x != "_") + ")"
    if name in ("gloss", "gl", "q", "qual", "qualifier", "i", "sense", "s", "qualifier-lite", "q-lite"):
        return "(" + ", ".join(pos) + ")"
    if name in ("l", "m", "link", "mention", "ll", "l-lite", "m-lite"):
        if len(pos) < 2:
            return ""
        x = pos[2] if len(pos) > 2 and pos[2] else pos[1]
        g = named.get("t") or named.get("gloss") or (pos[3] if len(pos) > 3 else "")
        return x + (" (" + g + ")" if g else "")
    if name == "w":
        return pos[-1] if pos else ""
    if name in ("n-g", "ng", "non-gloss", "non-gloss definition", "n-g-lite", "ngd"):
        return pos[0] if pos else ""
    if name in ("taxlink", "taxfmt", "vern", "pedia", "pedlink", "specieslink"):
        return pos[0] if pos else ""
    if name in FORM_OF:
        if len(pos) < 2:
            return ""
        g = named.get("t") or named.get("gloss") or (pos[3] if len(pos) > 3 else "")
        return FORM_OF[name] + " " + pos[1] + (" (" + g + ")" if g else "")
    if name in ("given name", "surname"):
        return "a " + " ".join(x for x in pos[1:] if x) + " " + name
    if name in ("ux", "uxi", "usex", "ux-lite", "quote"):
        t = named.get("t") or named.get("translation") or (pos[2] if len(pos) > 2 else "")
        return (pos[1] if len(pos) > 1 else "") + (" = " + t if t else "")
    if name in ("SI-unit", "SI-unit-abb"):
        return " ".join(pos)
    if name in ("place",):
        return "place: " + ", ".join(x for x in pos[1:] if x)
    if len(pos) >= 2 and pos[0] in ("ta", "en"):
        return pos[1]
    return ""

def clean_en(s, title):
    s = strip_markup(s, title)
    for _ in range(4):
        s = re.sub(r"\{\{([^{}]*)\}\}", en_template, s)
    return tidy(s, title)

# The source's own marks for a slur or a sexual term. Page level: the vulgarities, offensive-terms and
# ethnic-slur categories and the Genitalia, Prostitution and Pornography topics. Sense level: a
# vulgar/offensive/slur label drops that sense; a term label ({{tlb}}) on the headword line drops the
# whole part-of-speech section. Topical "Sex" or "Sexuality" alone is not a mark (it also covers kiss,
# marriage and puberty); the coordinator's lexicon scan runs over every chunk afterwards.
EN_VULGAR_PAGE = re.compile(r"\[\[Category:Tamil (?:vulgarities|offensive terms|ethnic slurs)\]\]|\{\{cln\|ta\|[^}]*(vulgarities|offensive terms|ethnic slurs)"
                            r"|\{\{(?:C|c|top|topics)\|ta\|[^}]*\b(Genitalia|Prostitution|Pornography)\b", re.I)
EN_VULGAR_LABEL = re.compile(r"\{\{(?:lb|label|lbl|tlb)\|ta\|[^}]*\b(vulgar|offensive|slur|ethnic slur|profanity)\b[^}]*\}\}", re.I)

def parse_en_wiktionary_page(title, text):
    """Entries from the ==Tamil== section of an English Wiktionary page: one per part-of-speech section."""
    m = re.search(r"^==\s*Tamil\s*==\s*$", text, re.M)
    if not m:
        return [], "no_tamil_section"
    rest = text[m.end():]
    n = re.search(r"^==[^=].*?[^=]==\s*$", rest, re.M)
    body = rest[:n.start()] if n else rest
    if EN_VULGAR_PAGE.search(body):
        return [], "marked_vulgar_or_sexual"
    out = []; marked_sections = 0
    secs = list(re.finditer(r"^(={3,5})\s*([A-Za-z ]+?)\s*\1\s*$", body, re.M))
    for i, sm in enumerate(secs):
        name = sm.group(2).strip().lower()
        if name not in POS_EN:
            continue
        end = secs[i + 1].start() if i + 1 < len(secs) else len(body)
        sec = body[sm.end():end]
        translit = ""
        hw = re.search(r"\{\{(?:ta-[a-z\-]+|head\|ta[^}]*)\}\}[^\n]*", sec)
        if hw:
            tm = re.search(r"\|tr=([^|}]+)", hw.group(0))
            translit = tm.group(1).strip() if tm else ""
            if EN_VULGAR_LABEL.search(hw.group(0)):
                marked_sections += 1
                continue
        meanings, examples = [], []
        for line in sec.split("\n"):
            s = line.rstrip()
            if s.startswith("#:") or s.startswith("#*"):
                if re.search(r"\{\{(ux|uxi|usex|ux-lite)\|", s):
                    ex = clean_en(s, title)
                    if ex and len(ex) <= 300:
                        examples.append(ex)
                continue
            if s.startswith("#") and not s.startswith("##"):
                if "{{rfdef" in s:
                    continue
                if EN_VULGAR_LABEL.search(s):
                    continue
                v = clean_en(s, title)
                if v and not re.fullmatch(r"\([^)]*\)", v):
                    meanings.append(v)
        meanings = dedupe(meanings)[:12]
        if not meanings:
            if EN_VULGAR_LABEL.search(sec):
                marked_sections += 1
            continue
        out.append({"pos": POS_EN[name], "pos_raw": sm.group(2).strip(), "meanings": meanings,
                    "examples": dedupe(examples)[:3], "translit": translit})
    if not out and marked_sections:
        return [], "marked_vulgar_or_sexual"
    return out, ("ok" if out else "no_definitions")

def build_en_wiktionary(stats):
    rows = []
    for line in open(EN_PAGES, encoding="utf-8"):
        d = json.loads(line)
        stats["en.wiktionary/pages_seen"] += 1
        ents, why = parse_en_wiktionary_page(d["title"], d["content"])
        if not ents:
            stats["en.wiktionary/skipped_" + why] += 1; continue
        url = "https://en.wiktionary.org/wiki/" + urllib.parse.quote(d["title"].replace(" ", "_")) + "#Tamil"
        for e in ents:
            rows.append({"word": d["title"], "script": "ta" if TA_RE.search(d["title"]) else "latin", "direction": "ta-en",
                         "pos": e["pos"], "pos_raw": e["pos_raw"], "meanings": e["meanings"], "examples": e["examples"],
                         "translit": e["translit"], "glosses_en": e["meanings"], "source": "en.wiktionary", "url": url,
                         "license": LICENSE, "edition": "live " + VERSION})
    return rows

# ---------------------------------------------------------------- en-ta by inversion of English glosses

GLOSS_OK = re.compile(r"^[a-z][a-z' \-]{0,40}$")

def split_glosses(text):
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    for g in re.split(r"[,;]", text):
        g = g.strip().lower()
        g = re.sub(r"^(to|a|an|the)\s+", "", g)
        g = re.sub(r"\s+", " ", g).strip(" .")
        if g and GLOSS_OK.match(g) and len(g.split()) <= 3:
            yield g

def invert(rows, source_name):
    """en-ta rows: for each English gloss in a bilingual ta-en row, the Tamil headwords that carry it."""
    by = collections.OrderedDict()
    for r in rows:
        if r["direction"] != "ta-en" or not r.get("glosses_en"):
            continue
        for g in r["glosses_en"]:
            for gl in split_glosses(g):
                key = (gl, r["pos"])
                by.setdefault(key, {"words": [], "url": r["url"]})
                if r["word"] not in by[key]["words"]:
                    by[key]["words"].append(r["word"])
    out = []
    for (gl, pos), v in by.items():
        out.append({"word": gl, "script": "latin", "direction": "en-ta", "pos": pos, "pos_raw": "", "meanings": v["words"][:15],
                    "examples": [], "translit": "", "source": source_name, "url": v["url"], "license": LICENSE,
                    "edition": "inverted from " + source_name.split(" ")[0] + " ta-en rows, " + VERSION})
    return out

# ---------------------------------------------------------------- output

def chunk_text(r):
    t = "%s (%s): %s" % (r["word"], r["pos"], "; ".join(r["meanings"]))
    if r["examples"]:
        t += " [" + " | ".join(r["examples"]) + "]"
    return t

def write_outputs(rows, stats, coverage, licence_notes):
    os.makedirs(PACK, exist_ok=True)
    ent_path = os.path.join(PACK, "entries_unscanned.jsonl")
    chk_path = os.path.join(PACK, "chunks_unscanned.jsonl")
    by_src = collections.Counter(); by_dir = collections.Counter(); by_pos = collections.Counter()
    by_src_dir = collections.Counter(); by_lang = collections.Counter(); by_src_lang = collections.Counter()
    by_src_pos = collections.defaultdict(collections.Counter)
    words = 0
    with open(ent_path, "w", encoding="utf-8") as fe, open(chk_path, "w", encoding="utf-8") as fc:
        for i, r in enumerate(rows, 1):
            rid = "dict-%06d" % i
            e = {"id": rid, "word": r["word"], "script": r["script"], "direction": r["direction"], "pos": r["pos"],
                 "pos_raw": r["pos_raw"], "meanings": r["meanings"], "examples": r["examples"], "translit": r["translit"],
                 "source": r["source"], "url": r["url"], "license": r["license"], "edition": r["edition"]}
            fe.write(json.dumps(e, ensure_ascii=False) + "\n")
            text = chunk_text(r)
            lang = script_of(text)
            # chunk fields plus the structured entry fields, so the serving route can show the entry verbatim
            # from chunks.jsonl without a second file
            c = {"id": rid, "title": r["word"], "section": r["pos"], "text": text, "lang": lang, "source": r["source"],
                 "url": r["url"], "license": r["license"], "machine_translated": False, "topic": "dictionary",
                 "direction": r["direction"], "pos": r["pos"], "word": r["word"], "script": r["script"],
                 "meanings": r["meanings"], "examples": r["examples"], "translit": r["translit"], "edition": r["edition"]}
            fc.write(json.dumps(c, ensure_ascii=False) + "\n")
            by_src[r["source"]] += 1; by_dir[r["direction"]] += 1; by_pos[r["pos"]] += 1
            by_src_dir[r["source"] + "/" + r["direction"]] += 1; by_lang[lang] += 1
            by_src_lang[r["source"] + "/" + lang] += 1; by_src_pos[r["source"]][r["pos"]] += 1
            words += len(text.split())
    n = len(rows)
    manifest = collections.OrderedDict([
        ("pack", "dictionary"), ("version", VERSION), ("languages", ["ta", "en"]),
        ("sources", [
            {"name": "Tamil Wiktionary (விக்சனரி), dump tawiktionary-" + TAWIKT_DUMP,
             "url": "https://ta.wiktionary.org", "license": LICENSE, "license_verified_on": VERSION,
             "how_obtained": "pages-articles dump downloaded once from dumps.wikimedia.org and cached; parsed offline (Tamil headwords: "
                             "the பொருள் section and the English line of மொழிபெயர்ப்புகள்; English headwords: the Tamil meaning lines); "
                             "User-Agent " + C.UA,
             "rows": by_src["ta.wiktionary"], "pages_seen": stats["ta.wiktionary/pages_seen_ta"] + stats["ta.wiktionary/pages_seen_en"],
             "pages_used": stats["ta.wiktionary/pages_used"], "dump_sha256": stats["dump_sha256"]},
            {"name": "English Wiktionary, Category:Tamil lemmas", "url": "https://en.wiktionary.org/wiki/Category:Tamil_lemmas",
             "license": LICENSE, "license_verified_on": VERSION,
             "how_obtained": "MediaWiki API generator=categorymembers with prop=revisions content, 50 pages per request, at most 2 requests "
                             "per second, User-Agent " + C.UA + "; the ==Tamil== section parsed per part-of-speech heading",
             "rows": by_src["en.wiktionary"], "pages_seen": stats["en.wiktionary/pages_seen"], "pages_used": stats["en.wiktionary/pages_used"]},
            {"name": "English Wiktionary Tamil lemmas, English glosses inverted to en-ta", "url": "https://en.wiktionary.org/wiki/Category:Tamil_lemmas",
             "license": LICENSE, "license_verified_on": VERSION, "how_obtained": "derived offline from the en.wiktionary ta-en rows above",
             "rows": by_src["en.wiktionary (inverted)"], "pages_seen": 0, "pages_used": 0},
            {"name": "Tamil Wiktionary Tamil headwords, English glosses inverted to en-ta", "url": "https://ta.wiktionary.org",
             "license": LICENSE, "license_verified_on": VERSION, "how_obtained": "derived offline from the ta.wiktionary ta-en rows above",
             "rows": by_src["ta.wiktionary (inverted)"], "pages_seen": 0, "pages_used": 0},
        ]),
        ("excluded_sources", licence_notes),
        ("entries", n), ("chunks", n),
        ("entries_by_source", dict(by_src)), ("entries_by_direction", dict(by_dir)), ("entries_by_pos", dict(by_pos)),
        ("entries_by_source_direction", dict(by_src_dir)), ("entries_by_source_pos", {k: dict(v) for k, v in by_src_pos.items()}),
        ("chunks_by_language", dict(by_lang)), ("chunks_by_source", dict(by_src)), ("chunks_by_source_language", dict(by_src_lang)),
        ("words", {"total": words, "mean": round(words / max(n, 1), 1)}),
        ("skipped", {k: v for k, v in sorted(stats.items()) if "skipped" in k or "no_meaning" in k or "redirect" in k}),
        ("scan", "pending"),
        ("coverage_200", coverage),
        ("built_by", "build_pack_dictionary.py"),
        ("notes", "Dictionary pack: one entry per chunk, text is '<word> (<pos>): <meanings> [examples]'. Nothing is translated "
                  "(machine_translated is false on every chunk); meanings and examples are the source's own wording, wiki markup "
                  "removed, em and en dashes normalised to hyphens (project house rule). The three DSAL dictionaries were checked "
                  "and excluded on licence (see LICENSES.md). The family-safe scan is run by the coordinator over "
                  "chunks_unscanned.jsonl; entries whose headword the source itself marks as a slur or sexual term were skipped here."),
    ])
    json.dump(manifest, open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return manifest

# ---------------------------------------------------------------- coverage of the 200 common words

def coverage_200(rows):
    items = [json.loads(l) for l in open(EVAL_200, encoding="utf-8") if l.strip()]
    heads = collections.defaultdict(set)      # source -> headwords (ta-en rows)
    en_words = collections.defaultdict(set)   # source -> English headwords (en-ta rows)
    for r in rows:
        if r["direction"] == "ta-en":
            heads[r["source"]].add(r["word"])
        else:
            en_words[r["source"]].add(r["word"].lower())
    srcs = ["ta.wiktionary", "en.wiktionary"]
    variants = lambda w: [w, w + "தல்", w + "த்தல்", w + "ுதல்", w.rstrip("்") + "தல்", w + "ம்", w[:-1] if w.endswith("ம்") else w]
    per = collections.Counter(); per_variant = collections.Counter(); table = []; misses = []; overall = 0; overall_any = 0
    for it in items:
        w = it["word"]; row = {"word": w, "gloss": it["gloss"], "pos": it["pos"]}
        hit_any = False; hit_exact = False
        for s in srcs:
            if w in heads[s]:
                row[s] = "exact"; per[s] += 1; per_variant[s] += 1; hit_exact = True; hit_any = True
            elif any(v in heads[s] for v in variants(w)):
                row[s] = "variant:" + next(v for v in variants(w) if v in heads[s]); per_variant[s] += 1; hit_any = True
            else:
                row[s] = "-"
        row["en-ta gloss"] = "yes" if any(it["gloss"].lower() in en_words[s] for s in en_words) else "-"
        if hit_exact:
            overall += 1
        if hit_any:
            overall_any += 1
        else:
            misses.append(w + " (" + it["gloss"] + ")")
        table.append(row)
    return {"of": len(items), "covered_exact_any_source": overall, "covered_exact_or_variant_any_source": overall_any,
            "per_source_exact": dict(per), "per_source_exact_or_variant": dict(per_variant),
            "misses": misses, "table": table}

# ---------------------------------------------------------------- main

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def licence_notes(ds, ar):
    """Compact record of the excluded sources for manifest.json; the verbatim quotes are in LICENSES.md."""
    return [
        {"name": "University of Madras Tamil Lexicon (1924-1936), DSAL edition", "url": DSAL_PAGES["tamil-lex"],
         "license": "CC BY-NC-ND 2.0 (" + ", ".join(ds["tamil-lex"]["cc_links"]) + ")", "decision": "exclude",
         "reason": "non-commercial and no-derivatives; the project takes nothing NC-licensed, and a parsed entry file is a derivative"},
        {"name": "Winslow, A Comprehensive Tamil and English Dictionary (1862), DSAL edition", "url": DSAL_PAGES["winslow"],
         "license": "none stated on the page; DC.Rights meta: " + str(ds["winslow"]["dc_rights"]), "decision": "exclude",
         "reason": "the licence of the DSAL database cannot be verified from the source itself; the 1862 original is public domain but no usable machine-readable copy was found"},
        {"name": "Fabricius, Tamil and English Dictionary, DSAL edition", "url": DSAL_PAGES["fabricius"],
         "license": "none stated; the edition is the 4th, revised and enlarged, Tranquebar 1972", "decision": "exclude",
         "reason": "1972 revision is not public domain; the 1779 and 1786 originals exist only as scans"},
        {"name": "archive.org scans of Winslow 1862 and the Tamil Lexicon 1939 volume", "url": "https://archive.org/details/" + ARCHIVE_ITEMS[1],
         "license": ", ".join(sorted({str(v.get("licenseurl")) for v in ar.values()})), "decision": "exclude",
         "reason": "Public Domain Mark on the items, but the OCR text layer is unusable (mixed-script noise), see LICENSES.md"},
    ]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="build from data/raw/packs/dictionary only")
    ap.add_argument("--fetch-only", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if not a.no_fetch:
        print("licence evidence ...", flush=True)
        ri, ds, ar = fetch_licences()
        print("  ta.wiktionary:", ri["ta.wiktionary.org"]["text"], "|", ri["ta.wiktionary.org"]["url"])
        print("  en.wiktionary:", ri["en.wiktionary.org"]["text"], "|", ri["en.wiktionary.org"]["url"])
        for k in ("tamil-lex", "winslow", "fabricius"):
            print("  DSAL %s: cc_links=%s dc_rights=%s" % (k, ds[k]["cc_links"], ds[k]["dc_rights"]))
        print("dump ...", flush=True)
        download_dump()
        print("en.wiktionary Tamil lemmas ...", flush=True)
        n = fetch_en_wiktionary()
        print("  pages cached:", n)
        if a.fetch_only:
            return
    for p in (DUMP_PATH, EN_PAGES, os.path.join(CACHE, "rightsinfo.json"), os.path.join(CACHE, "dsal_pages.json")):
        if not os.path.exists(p):
            sys.exit("missing %s; run without --no-fetch" % p)
    ds = json.load(open(os.path.join(CACHE, "dsal_pages.json"), encoding="utf-8"))
    ar = json.load(open(os.path.join(CACHE, "archive_org_items.json"), encoding="utf-8"))
    stats = collections.Counter()
    stats["dump_sha256"] = sha256(DUMP_PATH)
    print("parsing ta.wiktionary dump ...", flush=True)
    ta_rows = build_ta_wiktionary(stats)
    stats["ta.wiktionary/pages_used"] = len(ta_rows)
    print("  rows:", len(ta_rows), {k: v for k, v in stats.items() if k.startswith("ta.wiktionary")})
    print("parsing en.wiktionary pages ...", flush=True)
    en_rows = build_en_wiktionary(stats)
    stats["en.wiktionary/pages_used"] = len({r["word"] for r in en_rows})
    print("  rows:", len(en_rows), {k: v for k, v in stats.items() if k.startswith("en.wiktionary")})
    inv_en = invert(en_rows, "en.wiktionary (inverted)")
    inv_ta = invert(ta_rows, "ta.wiktionary (inverted)")
    print("  inverted en-ta rows: en.wiktionary %d, ta.wiktionary %d" % (len(inv_en), len(inv_ta)))
    rows = [r for r in ta_rows if r["direction"] == "ta-en"] + en_rows + [r for r in ta_rows if r["direction"] == "en-ta"] + inv_en + inv_ta
    cov = coverage_200(rows)
    manifest = write_outputs(rows, stats, cov, licence_notes(ds, ar))
    json.dump(cov, open(os.path.join(CACHE, "coverage_200.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("entries:", manifest["entries"])
    print("by source:", manifest["entries_by_source"])
    print("by direction:", manifest["entries_by_direction"])
    print("by pos:", manifest["entries_by_pos"])
    print("by source/direction:", manifest["entries_by_source_direction"])
    print("coverage 200: exact %d, exact or variant %d, per source %s, per source with variants %s" % (
        cov["covered_exact_any_source"], cov["covered_exact_or_variant_any_source"], cov["per_source_exact"], cov["per_source_exact_or_variant"]))
    print("misses:", cov["misses"])
    print("done in %.0f s" % (time.time() - t0))

if __name__ == "__main__":
    main()
