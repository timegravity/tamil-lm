"""Agriculture passages from the Tamil University encyclopedias on Tamil Wikisource (ruling 2026-09-14, item 15).

Sources: அறிவியல் களஞ்சியம் (19 volumes) and வாழ்வியற் களஞ்சியம் (15 volumes), published by Tamil University, Thanjavur, scanned in
2022 and hosted as proofreading pages (namespace பக்கம்) on ta.wikisource.org. Licence basis: each volume's Wikimedia Commons file page
states "The Tamil university released all its publications under CC-BY-SA", tags the file {{cc-by-sa-1.0+}}, and cites the Tamil
Nadu Tamil Development Department order (Commons file dated 2016-08-12). The Commons licence review ({{LicenseReview}}) is pending
(checked 2026-09-14); data/LICENSES.md and data/packs/agriculture/LICENSES.md record that so the decision can be revisited.

Steps (every API request is cached under data/raw/packs/tamil_university/, one request per second, User-Agent with contact@timegravity.ai):
1. Search the proofreading pages of both series for each agriculture topic (TOPICS: crops, pests and diseases, practices).
2. Fetch the pages' wikitext and proofreading level; a page whose running header names the topic also pulls the following pages while
   the header keeps naming it (an entry spans several pages).
3. Clean: drop page furniture (noinclude blocks, templates, markup), join words that the two-column print broke across lines (a line
   that starts with a Tamil vowel sign always joins; otherwise the pieces join when the joined word is commoner in the Tamil Wikipedia
   vocabulary than either piece), collapse whitespace.
4. OCR quality: a page is kept when at least VOCAB_MIN of its Tamil words are known words of the Tamil Wikipedia vocabulary and
   OCR noise characters stay under NOISE_MAX; a volume is skipped entirely (raw OCR, unusable) when fewer than VOLUME_MIN of its
   fetched pages pass. Per-volume figures go to the report.
5. Entries: pages are cut at entry boundaries (an author signature line or a bibliography block ends an entry; the next line starts
   one, its short first lines are the heading); a page's first segment continues the previous page's entry and keeps its title, and a heading after a boundary replaces the
   title only when it agrees with the page's running header (otherwise it is a sub-section of the same entry).
6. Relevance: an entry segment is kept for a topic when its title names the topic or its text names the topic at least MENTION_MIN
   times as a word (a Tamil word may carry up to 4 suffix characters) with at least AGRI_MIN farming terms (AGRI_RX), any kept segment has
   at least 2 farming terms, and its title is not a cross-reference (காண்க) or a
   medical, human, fish, bird or institution entry; at most PER_TOPIC segments per topic, best first (title, mentions, procedure markers).
7. Family-safe scan (pack_scan.scan_text, as every pack): a chunk with any lexicon hit other than the "blocked" severity (allowed in the
   agriculture and nature packs, ruling 2026-09-13) is dropped and counted.

Writes data/packs/agriculture/chunks_tamil_university.jsonl (one chunk per entry segment: title = the entry,
section = series, volume and printed page; build_app_packs.py splits long chunks) and data/packs/agriculture/tamil_university_report.md.

  .venv/bin/python build_pack_tamil_university.py [--no-fetch]
"""
import argparse, collections, hashlib, json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
CACHE = os.path.join(ROOT, "data", "raw", "packs", "tamil_university")
OUT = os.path.join(ROOT, "data", "packs", "agriculture", "chunks_tamil_university.jsonl")
REPORT = os.path.join(ROOT, "data", "packs", "agriculture", "tamil_university_report.md")
API = "https://ta.wikisource.org/w/api.php"
UA = "timegravity-tamil-lm-packs/1.0 (https://timegravity.ai; contact@timegravity.ai)"
SERIES = ("அறிவியல் களஞ்சியம்", "வாழ்வியற் களஞ்சியம்")
LICENCE = "CC BY-SA (Tamil University publications; Tamil Nadu Tamil Development Department order, Commons file dated 2016-08-12; Commons licence review pending, checked 2026-09-14)"
VOCAB_MIN, NOISE_MAX, VOLUME_MIN, MENTION_MIN, AGRI_MIN, PER_TOPIC, FOLLOW_MAX = 0.80, 0.006, 0.5, 5, 6, 10, 14
# (search word, label, kind): crops carry the pack's crop label so the phone's margin rule treats pages of one crop as one answer
TOPICS = [(w, w, "crop") for w in ["நெல்", "தென்னை", "வாழை", "மஞ்சள்", "கரும்பு", "நிலக்கடலை", "தக்காளி", "கத்தரி", "வெண்டை", "மிளகாய்", "பருத்தி",
                                   "சோளம்", "கேழ்வரகு", "உளுந்து", "துவரை", "எள்", "இஞ்சி", "வெங்காயம்", "மரவள்ளி", "பச்சைப் பயறு", "மா மரம்", "பலா", "மிளகு"]] + \
         [(w, None, "pest") for w in ["காண்டாமிருக வண்டு", "சிவப்புக் கூன் வண்டு", "குலை நோய்", "தண்டுத் துளைப்பான்", "இலைச் சுருட்டுப் புழு", "புகையான்", "சாம்பல் நோய்", "நூற்புழு", "பூச்சிக்கொல்லி"]] + \
         [(w, None, "practice") for w in ["மண்புழு உரம்", "உயிர் உரம்", "பசுந்தாள் உரம்", "சொட்டு நீர்ப் பாசனம்", "நாற்றங்கால்", "ஊடுபயிர்", "களைக் கட்டுப்பாடு", "பூச்சி மேலாண்மை", "மண் பரிசோதனை", "விதை நேர்த்தி", "அறுவடை", "பயிர்ச் சுழற்சி"]]
TOPIC_KIND = {"crop": "crop", "pest": "pest", "practice": "general"}
# segments read and rejected (2026-09-14): (page, topic) -> reason; the relevance rules above keep them, the text is not about the topic
REVIEWED_DROP = {
    ('பக்கம்:அறிவியல் களஞ்சியம் 2.pdf/674', 'அறுவடை'): 'a surgery entry runs into the page before the harvest machines entry',
    ('பக்கம்:அறிவியல் களஞ்சியம் 4.pdf/100', 'பூச்சிக்கொல்லி'): 'an electrical engineering entry (coupling); the pesticide word is incidental',
    ('பக்கம்:அறிவியல் களஞ்சியம் 5.pdf/777', 'உளுந்து'): 'a psychology entry runs through most of the page',
    ('பக்கம்:அறிவியல் களஞ்சியம் 6.pdf/261', 'அறுவடை'): 'a printing entry runs through most of the page',
    ('பக்கம்:அறிவியல் களஞ்சியம் 13.pdf/170', 'மஞ்சள்'): 'Indian rhubarb, a medicinal plant named நாட்டு மஞ்சள், not turmeric',
    ('பக்கம்:வாழ்வியற் களஞ்சியம் 2.pdf/139', 'அறுவடை'): 'a religion entry and a harvest song, not farming',
    ('பக்கம்:வாழ்வியற் களஞ்சியம் 9.pdf/870', 'பருத்தி'): 'a district geography entry; cotton is only listed among crops',
}
# titles corrected by reading (the detected heading or page header names a neighbouring entry)
REVIEWED_TITLE = {
    ('பக்கம்:அறிவியல் களஞ்சியம் 2.pdf/679', 'நிலக்கடலை'): 'அறுவடை எந்திரங்கள்',
    ('பக்கம்:அறிவியல் களஞ்சியம் 4.pdf/859', 'இலைச் சுருட்டுப் புழு'): 'இலைச்சுருட்டுப் புழுக்கள்',
    ('பக்கம்:அறிவியல் களஞ்சியம் 7.pdf/454', 'கத்தரி'): 'கத்தரி',
    ('பக்கம்:அறிவியல் களஞ்சியம் 12.pdf/462', 'துவரை'): 'துவரை',
    ('பக்கம்:அறிவியல் களஞ்சியம் 12.pdf/856', 'கத்தரி'): 'தோட்டக்கலைப் பயிர்களைத் தாக்கும் பூச்சிகள்',
}
TAMIL = re.compile(r"[஀-௿]+")
MARK = re.compile(r"^[ா-்ௗ]")
NOISE = re.compile(r"[$#@^~|\\{}<>�௦-௯]|[A-Za-z][஀-௿]|[஀-௿][A-Za-z]")

_last = [0.0]
def get(params, no_fetch=False):
    key = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path): return json.load(open(path, encoding="utf-8"))
    if no_fetch: return None
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    body = urllib.parse.urlencode(dict(params, format="json")).encode()   # POST: long title lists exceed the GET URL limit
    for attempt in range(4):
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(API, data=body, headers={"User-Agent": UA}), timeout=60)); break
        except Exception as e:
            err = e; time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"fetch failed ({err}): {params.get('action')} {str(params)[:200]}")
    _last[0] = time.time()
    os.makedirs(CACHE, exist_ok=True); json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return d

def vocab():
    path = os.path.join(CACHE, "tawiki_vocab.json")
    if os.path.exists(path): return collections.Counter(json.load(open(path, encoding="utf-8")))
    c = collections.Counter()
    with open(os.path.join(ROOT, "data", "index", "tawiki_20260801_fs", "passages.jsonl"), encoding="utf-8") as f:
        for i, l in enumerate(f):
            if i >= 200000: break
            c.update(TAMIL.findall(json.loads(l).get("text", "")))
    c = collections.Counter({w: n for w, n in c.items() if n >= 2})
    os.makedirs(CACHE, exist_ok=True); json.dump(c, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return c

def page_title(series, vol, n):
    return f"பக்கம்:{series} {vol}.pdf/{n}"

def parse_title(t):
    m = re.match(r"^பக்கம்:(அறிவியல் களஞ்சியம்|வாழ்வியற் களஞ்சியம்) (\d+)\.pdf/(\d+)$", t)
    return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None

def search(word, no_fetch):
    out = []
    for series in SERIES:
        d = get({"action": "query", "list": "search", "srsearch": f'"{word}" intitle:"{series}"', "srnamespace": "250", "srlimit": "50"}, no_fetch)
        if d: out += [x["title"] for x in d["query"]["search"] if parse_title(x["title"])]
    return out

def fetch_pages(titles, no_fetch):
    res = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 20):
        d = get({"action": "query", "prop": "revisions|proofread", "rvprop": "content", "rvslots": "main", "titles": "|".join(titles[i:i + 20])}, no_fetch)
        if not d: continue
        norm = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for p in d["query"]["pages"].values():
            if "revisions" not in p: continue
            t = norm.get(p["title"], p["title"])
            res[t] = {"wikitext": p["revisions"][0]["slots"]["main"]["*"], "quality": (p.get("proofread") or {}).get("quality")}
    return res

def running_header(wt):
    m = re.search(r"\{\{rh\|([^}]*)\}\}", wt)
    if not m:   # no header template: the printed header is the first text line ("542 தென்னை" or "தென்னை 543")
        first = next((l.strip() for l in re.sub(r"<noinclude>.*?</noinclude>", "", wt, flags=re.S).split("\n") if l.strip()), "")
        mm = re.match(r"^[0-9]+\s+(\S.{0,40})$", first) or re.match(r"^(\S.{0,40}?)\s+[0-9]+$", first)
        return mm.group(1).strip() if mm and TAMIL.search(mm.group(1)) else ""
    parts = [re.sub(r"\s+", " ", x).strip(" ‌") for x in m.group(1).split("|")]
    parts = [re.sub(r"^\d+\s*|\s*\d+$", "", x).strip(" ‌") for x in parts if x.strip()]
    return " ".join(x for x in parts if x and not x.isdigit())

BIB_RX = re.compile(r"^\s*(நூலோதி|துணைநூல்|துணை\s*நூல்|துணை\s*நூல்கள்)")
SIGN_RX = re.compile(r"^\s*[-–—]\s*\S.{0,40}$")
AGRI_RX = re.compile(r"சாகுபடி|பயிரிட|பயிராகி|பயிர்|விதைப்பு|விதைக்க|நடவு|நாற்று|உரம்|உரமி|உரங்|அறுவடை|மகசூல்|வேளாண்|விளைச்சல்|பாசன|களைக்|களைகள்|பூச்சிக்கொல்லி|ஹெக்டேர்|எக்டேர்")
NOT_AGRI_TITLE = re.compile(r"மருத்துவம்|மனிதர்|மீன்|பறவை|அறுவை|வானியல்|நிறுவனம்|தொழில்கள்")

def raw_lines(wt):
    t = re.sub(r"<noinclude>.*?</noinclude>", "", wt, flags=re.S)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t); t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"<[^>]+>", "", t); t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = t.replace("\'\'\'", "").replace("\'\'", "").replace("\u200c", "")
    return [l.strip() for l in t.split("\n")]

def is_bib_line(l):
    latin = sum(1 for c in l if c.isascii() and c.isalpha()); tamil = len("".join(TAMIL.findall(l)))
    return bool(re.match(r"^\s*[0-9]+\s*[.)]", l)) or latin > tamil or bool(re.search(r"(19|20)[0-9]{2}\s*\.?\s*$", l)) or "வெளியீடு" in l or "பதிப்பு" in l

def segments(lines):
    """A page cut at entry boundaries: an author signature line (-name) or a bibliography block (நூலோதி, துணைநூல் and its items) ends an
    entry; the next Tamil line starts one, and its first short lines are the entry's heading. Returns [(starts_entry, heading, lines)]."""
    segs = []; cur = []; starts = False; bib = False
    def close():
        nonlocal cur
        if any(x.strip() for x in cur): segs.append([starts, cur])
        cur = []
    for l in lines:
        if BIB_RX.match(l):
            close(); bib = True; continue
        if bib:
            if not l or is_bib_line(l): continue
            bib = False; starts = True; cur = [l]; continue
        if SIGN_RX.match(l) and len(TAMIL.findall(l)) <= 4:
            close(); starts = True; continue
        if not cur and segs == [] and not starts: starts = False
        cur.append(l)
    close()
    out = []
    for st, ls in segs:
        heading = ""
        if st:
            head = []
            for l in ls:
                if l and len(l) <= 45 and TAMIL.search(l) and not re.search(r"[.,;:]$", l) and len(head) < 2: head.append(l)
                else: break
            heading = " ".join(head)
        out.append((st, heading, ls))
    return out

def join_lines(lines, V):
    out = ""
    for l in lines:
        if not l:
            out += "\n\n"; continue
        if not out or out.endswith("\n\n"):
            out += l; continue
        a = TAMIL.findall(out[-40:]); b = TAMIL.findall(l[:40])
        ends_tamil = bool(re.search(r"[\u0B80-\u0BFF]$", out)); starts_tamil = bool(re.match(r"^[\u0B80-\u0BFF]", l))
        join = False
        if ends_tamil and starts_tamil and a and b:
            w1, w2 = a[-1], b[0]
            if MARK.match(l): join = True
            else:
                j = V.get(w1 + w2, 0)
                join = j > 0 and (j >= min(V.get(w1, 0), V.get(w2, 0)))
        out += (l if join else " " + l)
    out = re.sub(r"[ \t]+", " ", out); out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()

def clean(wt, V):
    return join_lines(raw_lines(wt), V)

def mentions(text, w):
    if " " in w:
        return len(re.findall(re.escape(w).replace("\\ ", r"\s*"), text))
    return sum(1 for t in TAMIL.findall(text) if t.startswith(w) and len(t) - len(w) <= 4)

def quality(text, V):
    words = [w for w in TAMIL.findall(text) if len(w) >= 2]
    known = sum(1 for w in words if w in V) / max(1, len(words))
    noise = len(NOISE.findall(text)) / max(1, len(text))
    return known, noise, len(words)

LICENCE_SECTION = """
## AG-TU: Tamil University encyclopedias on Tamil Wikisource (added 2026-09-14, ruling item 15)

| # | source | url | licence (as stated, quoted) | verified at | decision | what was taken |
|---|---|---|---|---|---|---|
| AG-TU | Tamil University, Thanjavur: அறிவியல் களஞ்சியம் (science encyclopedia, 19 volumes) and வாழ்வியற் களஞ்சியம் (social science encyclopedia, 15 volumes), proofreading pages on Tamil Wikisource | https://ta.wikisource.org/wiki/அட்டவணை:அறிவியல்_களஞ்சியம்_14.pdf (one index per volume) | Wikimedia Commons file page of each volume (checked for volumes 5 and 14 of the science encyclopedia and volume 1 of the social science encyclopedia): "The Tamil university released all its publications under CC-BY-SA. refer the below document."; licence template {{cc-by-sa-1.0+}}; Permission field: [[File:GoTN Tamil Development Departments order on creative commons cc by sa.pdf]], whose Commons page reads "Government Order of Department of Tamil Development Government of Tamil Nadu declared books publications under CC-BY-SA" with date 2016-08-12 | https://commons.wikimedia.org/wiki/File:அறிவியல்_களஞ்சியம்_14.pdf, https://commons.wikimedia.org/wiki/File:அறிவியல்_களஞ்சியம்_5.pdf, https://commons.wikimedia.org/wiki/File:வாழ்வியற்_களஞ்சியம்_1.pdf and https://commons.wikimedia.org/wiki/File:GoTN_Tamil_Development_Departments_order_on_creative_commons_cc_by_sa.pdf, fetched 2026-09-14 | include (Vignesh, 2026-09-14: on the strength of the government order) | entry text on crops, pests and farming practice (build_pack_tamil_university.py, data/packs/agriculture/chunks_tamil_university.jsonl) |

- Pending review, to revisit: every volume's Commons file page carries {{LicenseReview}}, meaning the Commons licence review of the
  CC BY-SA claim has not been completed (checked 2026-09-14). The inclusion rests on the Tamil Nadu government order as cited on those
  pages. If the review fails, or the order is found not to cover these volumes, remove chunks_tamil_university.jsonl from the pack
  (PACK_EXTRA in build_app_packs.py) and rebuild.
- Attribution: every chunk carries the entry title, the series, volume and printed page (section), the Wikisource page URL, and the
  licence line; the published pack keeps them.
- Share-alike: the chunks are redistributed under CC BY-SA 4.0 (the {{cc-by-sa-1.0+}} tag permits later versions) with that attribution.
"""

def record_licence():
    for path in (os.path.join(ROOT, "data", "packs", "agriculture", "LICENSES.md"), os.path.join(ROOT, "data", "LICENSES.md")):
        text = open(path, encoding="utf-8").read()
        if "## AG-TU: Tamil University encyclopedias" not in text:
            open(path, "a", encoding="utf-8").write(("\n" if not text.endswith("\n") else "") + LICENCE_SECTION)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-fetch", action="store_true"); a = ap.parse_args()
    V = vocab()
    import pack_scan
    sys.path.insert(0, os.path.join(ROOT, "eval"))
    from pack_content_audit import proc_score
    hits = {w: search(w, a.no_fetch) for w, _, _ in TOPICS}
    pages = fetch_pages([t for v in hits.values() for t in v], a.no_fetch)
    # follow an entry across pages while the running header keeps naming the topic
    for w, _, _ in TOPICS:
        for t in list(hits[w]):
            if t not in pages or w not in running_header(pages[t]["wikitext"]): continue
            s, vol, n = parse_title(t); nxt = n
            for _ in range(FOLLOW_MAX):
                nxt += 1; tt = page_title(s, vol, nxt)
                if tt not in pages: pages.update(fetch_pages([page_title(s, vol, nxt + k) for k in range(8)], a.no_fetch))
                if tt not in pages or w not in running_header(pages[tt]["wikitext"]): break
                if tt not in hits[w]: hits[w].append(tt)
    # clean and score every page; volume verdicts
    info = {}
    for t, p in pages.items():
        s, vol, n = parse_title(t); txt = clean(p["wikitext"], V); known, noise, nw = quality(txt, V)
        info[t] = {"series": s, "vol": vol, "page": n, "text": txt, "header": running_header(p["wikitext"]), "known": known, "noise": noise, "words": nw, "level": p["quality"],
                   "ok": nw >= 40 and known >= VOCAB_MIN and noise <= NOISE_MAX}
    volumes = collections.defaultdict(list)
    for t, x in info.items(): volumes[(x["series"], x["vol"])].append(x)
    vol_ok = {k: sum(1 for x in v if x["ok"]) / len(v) >= VOLUME_MIN for k, v in volumes.items()}
    # cut pages into entries; carry an entry's title across page turns (a page's first segment continues the previous page's entry)
    seg_rows = []
    for (s_, vol), v in sorted(volumes.items()):
        if not vol_ok[(s_, vol)]: continue
        prev_title, prev_page = None, None
        for x in sorted(v, key=lambda x: x["page"]):
            if not x["ok"]: prev_title, prev_page = None, None; continue
            segs = segments(raw_lines(pages[page_title(s_, vol, x["page"])]["wikitext"]))
            for k, (st, heading, ls) in enumerate(segs):
                hn = re.sub(r"\s+", "", heading); hd = re.sub(r"\s+", "", x["header"])
                plausible = bool(hn) and not re.search(r"[.0-9]|காண்க", heading) and (not hd or hn in hd or hd in hn)
                continuing = prev_title if (prev_page == x["page"] - 1 or k > 0) else None
                if st and plausible: title = heading
                elif continuing: title = continuing   # a sub-section (uses, pests) by another contributor, or a page turn
                else: title = x["header"]
                text = join_lines(ls, V)
                if len(text) >= 300: seg_rows.append({"t": page_title(s_, vol, x["page"]), "series": s_, "vol": vol, "page": x["page"], "title": re.sub(r"\s+", " ", title or "").strip(), "text": text, "level": x["level"], "known": x["known"]})
                prev_title = re.sub(r"\s+", " ", title or "").strip()
            prev_page = x["page"]
    chosen = {}; per_topic = {}
    for w, label, kind in TOPICS:
        cands = []
        for i, r in enumerate(seg_rows):
            if r["t"] not in hits[w] and w not in r["title"]: continue
            if NOT_AGRI_TITLE.search(r["title"]): continue
            in_title = w in r["title"]; m = mentions(r["text"], w); agri = len(AGRI_RX.findall(r["text"]))
            if not (in_title or (m >= MENTION_MIN and agri >= AGRI_MIN)) or m < 1 or agri < 3 or "காண்க" in r["title"]: continue
            if (r["t"], w) in REVIEWED_DROP: continue
            cands.append((in_title, m, proc_score(r["text"]), i))
        cands.sort(key=lambda c: (-c[0], -c[1], -c[2]))
        per_topic[w] = [c[3] for c in cands[:PER_TOPIC]]
        for c in cands[:PER_TOPIC]: chosen.setdefault(c[3], (w, label, kind))
    rows = []; dropped = collections.Counter()
    for i in sorted(chosen):
        r = seg_rows[i]; w, label, kind = chosen[i]
        hits_fs = [h for h in pack_scan.scan_text(r["text"]) if h.get("severity") != "blocked"]
        if hits_fs:
            dropped[str(sorted({str(h.get("severity")) for h in hits_fs}))] += 1; continue
        hdr = info[r["t"]]["header"]
        title = REVIEWED_TITLE.get((r["t"], w)) or (hdr if w in hdr else (r["title"] or w))
        title = re.sub(r"\s+", " ", title.replace("\u200c", "")).strip()
        half = title.split(" "); n2 = len(half) // 2
        if len(half) % 2 == 0 and n2 and half[:n2] == half[n2:]: title = " ".join(half[:n2])   # a running header printed twice (first and last entry)   # the printed header names the entry more reliably than a detected heading
        section = f"தமிழ்ப் பல்கலைக்கழகம், {r['series']} {r['vol']}, பக்கம் {r['page']}"
        rows.append({"id": f"tu-agri-{len(rows) + 1:05d}", "title": title, "section": section, "text": f"{title}\n{section}\n\n{r['text']}", "lang": "ta",
                     "source": "ta.wikisource (Tamil University encyclopedia)", "url": "https://ta.wikisource.org/wiki/" + urllib.parse.quote(r["t"].replace(" ", "_")),
                     "license": LICENCE, "machine_translated": False, "topic": TOPIC_KIND[kind] if (kind != "crop" or w in title) else "general", "crop": label if (label and w in title) else None, "search_word": w,
                     "proofread_level": r["level"], "ocr_known_words": round(r["known"], 3)})
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    L = [f"# Tamil University encyclopedia passages for the agriculture pack ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Generated by build_pack_tamil_university.py. Licence basis and pending Commons review: data/packs/agriculture/LICENSES.md.", "",
         f"Pages fetched: {len(info)}; pages passing the OCR check (known Tamil words >= {VOCAB_MIN}, noise <= {NOISE_MAX}, at least 40 words): {sum(1 for x in info.values() if x['ok'])}.", "",
         "| series | volume | pages fetched | pages passing | volume used |", "|---|---|---|---|---|"]
    for (s, vol), v in sorted(volumes.items()):
        L.append(f"| {s} | {vol} | {len(v)} | {sum(1 for x in v if x['ok'])} | {'yes' if vol_ok[(s, vol)] else 'no (raw OCR, unusable)'} |")
    L += ["", "| topic | entry segments kept | entries |", "|---|---|---|"]
    for w, _, _ in TOPICS:
        L.append(f"| {w} | {len(per_topic[w])} | {'; '.join(sorted({seg_rows[i]['title'] for i in per_topic[w]}))[:300]} |")
    L += ["", f"Chunks written: {len(rows)} ({sum(len(r['text']) for r in rows):,} characters). Dropped by the family-safe scan: {sum(dropped.values())} {dict(dropped)}."]
    open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L))
    record_licence()

if __name__ == "__main__":
    main()
