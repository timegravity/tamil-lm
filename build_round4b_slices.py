"""Round-4b data changes (ruling 2026-09-10). Three slices, everything else identical to round 4.

1. c19_abstention_v2: the round-4 abstention slice restricted to dated-fact triggers (prices, office holders, election
   results, live events such as sports results, scheme amounts). The passage-grounded categories are dropped and any
   row whose question is historical or encyclopaedic (a past year, a war, a king, who wrote, when built, history) is
   removed. Served at half the round-4 weight by build_sft_r4.py --variant 4b.
2. c23_history_benign: 400 rows answered normally in Tamil, Tanglish and English about kings, wars, dates, authors and
   buildings, drawn from Wikipedia leads (Tamil Wikipedia offline for Tamil and Tanglish questions; English Wikipedia
   extracts through the API for English questions). CC BY-SA 4.0, attribution in the model card.
3. c24_extractive_qa: 300 short-answer extractive QA rows in the IndicQA shape (passage plus question, answer is a span
   of the passage), built with high-precision patterns over Tamil Wikipedia leads (birth year, death year, district,
   author of a work, year founded or built). Never from IndicQA itself (benchmark rule).

  .venv/bin/python build_round4b_slices.py
"""
import json, os, random, re, sys, time, urllib.parse, urllib.request, collections

rng = random.Random(20260910)
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT)
BUILD = os.path.join(ROOT, "data", "round3", "build")
PASSAGES = os.path.join(ROOT, "data", "index", "tawiki_20260801_fs", "passages.jsonl")
SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
UA = "tamil-lm-research (contact@timegravity.ai)"

# ---------------------------------------------------------------- 1. c19 v2
HIST_RX = re.compile(r"\b(1[0-9]{3}|20[01][0-9]|202[0-3])\b|history|historic|war\b|battle|king|emperor|dynasty|empire|who wrote|written by|author|built in|when was .* built|founded|century|independence|freedom struggle|ancient|"
                     r"வரலாறு|போர்|மன்னர்|அரசர்|பேரரசு|சாம்ராஜ்ய|எழுதினார்|எழுதிய|ஆசிரியர்|கட்டப்பட்ட|நிறுவப்பட்ட|நூற்றாண்டு|சுதந்திர|பண்டைய|"
                     r"varalaru|varalaaru|por\b|mannar|arasar|ezhudhina|ezhuthina|kattapatta|nootrandu|sudhandhira", re.I)
KEEP_CATS = {"office_holders_elections", "prices_markets", "government_schemes", "sports_results", "dated_events"}

def build_c19_v2():
    rows = [json.loads(l) for l in open(os.path.join(BUILD, "c19_abstention_clean.jsonl"), encoding="utf-8")]
    out = []; dropped = collections.Counter()
    for r in rows:
        if r.get("category") not in KEEP_CATS:
            dropped["category:" + str(r.get("category"))] += 1; continue
        q = r["messages"][1]["content"]
        if HIST_RX.search(q):
            dropped["historical_or_encyclopaedic"] += 1; continue
        r = dict(r, slice="c19_abstention_v2"); out.append(r)
    with open(os.path.join(BUILD, "c19_abstention_v2.jsonl"), "w", encoding="utf-8") as f:
        for r in out: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"c19 v2: kept {len(out)} of {len(rows)}; dropped {dict(dropped)}; by category {dict(collections.Counter(r['category'] for r in out))}; by lang {dict(collections.Counter(r['lang'] for r in out))}")
    return out

# ---------------------------------------------------------------- shared: Tamil Wikipedia leads
def load_leads(min_len=250):
    leads = {}
    with open(PASSAGES, encoding="utf-8") as f:
        for l in f:
            d = json.loads(l); t = d.get("title", ""); txt = re.sub(r"\s+", " ", d.get("text", "")).strip()
            if t in leads or len(txt) < min_len or not txt.startswith(t[:2]):
                continue
            leads[t] = txt
    return leads

def first_sentences(txt, limit=450):
    out = ""
    for x in re.split(r"(?<=[.!?])\s+", txt):
        if len(out) + len(x) > limit and out:
            break
        out += (" " if out else "") + x
    return out

# ---------------------------------------------------------------- 2. c23 history and encyclopaedic, benign
KINDS = {
    "king": (re.compile(r"மன்னர்|அரசர்|பேரரசர்|சக்கரவர்த்தி|அரசி|ராணி"), {"ta": ["{t} யார்?", "{t} பற்றிச் சொல்லுங்கள்.", "{t} எந்தக் காலத்தில் ஆட்சி செய்தார்?"], "tanglish": ["{t} yaaru?", "{t} pathi sollu", "{t} eppo aatchi senjaru?"], "en": ["Who was {t}?", "Tell me about {t}.", "When did {t} rule?"]}),
    "war": (re.compile(r"போர்|யுத்தம்|படையெடுப்பு|கலகம்|புரட்சி"), {"ta": ["{t} எப்போது நடந்தது?", "{t} பற்றிச் சொல்லுங்கள்.", "{t} இல் என்ன நடந்தது?"], "tanglish": ["{t} eppo nadandhadhu?", "{t} la enna aachu?", "{t} pathi sollu"], "en": ["When did {t} happen?", "What happened in {t}?", "Tell me about {t}."]}),
    "book": (re.compile(r"நூல்|காப்பியம்|நாவல்|கவிதைத் தொகுப்பு|இலக்கணம்"), {"ta": ["{t} யார் எழுதினார்?", "{t} பற்றிச் சொல்லுங்கள்.", "{t} என்ன நூல்?"], "tanglish": ["{t} yaar ezhudhinaanga?", "{t} pathi sollu", "{t} enna nool?"], "en": ["Who wrote {t}?", "Tell me about {t}.", "What is {t}?"]}),
    "building": (re.compile(r"கோயில்|கோவில்|கோட்டை|அரண்மனை|மசூதி|தேவாலயம்|அணை|பாலம்|நினைவுச்சின்னம்"), {"ta": ["{t} எப்போது கட்டப்பட்டது?", "{t} யார் கட்டினார்?", "{t} பற்றிச் சொல்லுங்கள்."], "tanglish": ["{t} eppo kattapattadhu?", "{t} yaar kattinaanga?", "{t} pathi sollu"], "en": ["When was {t} built?", "Who built {t}?", "Tell me about {t}."]}),
    "date": (re.compile(r"பிறந்தார்|இறந்தார்|நிறுவப்பட்டது|தொடங்கப்பட்டது|நடைபெற்றது"), {"ta": ["{t} எப்போது?", "{t} பற்றிச் சொல்லுங்கள்."], "tanglish": ["{t} eppo?", "{t} pathi sollu"], "en": ["When was {t}?", "Tell me about {t}."]}),
}

def en_extract(ta_title):
    """English Wikipedia lead for a Tamil title through the ta.wikipedia langlinks API, then the English extract API. None when absent."""
    try:
        u = "https://ta.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "query", "prop": "langlinks", "lllang": "en", "titles": ta_title, "format": "json"})
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=10))
        pages = list(d["query"]["pages"].values()); ll = (pages[0].get("langlinks") or [{}])[0].get("*") if pages else None
        if not ll:
            return None, None
        time.sleep(0.55)
        u = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "titles": ll, "format": "json", "redirects": 1})
        d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=10))
        pages = list(d["query"]["pages"].values()); ext = (pages[0].get("extract") or "").strip() if pages else ""
        time.sleep(0.55)
        return (ll, re.sub(r"\s+", " ", ext)) if len(ext) > 200 else (ll, None)
    except Exception:
        return None, None

def build_c23(leads, n=400):
    cands = collections.defaultdict(list)
    for t, txt in leads.items():
        if not re.fullmatch(r"[஀-௿\s]{3,40}", t):
            continue
        for kind, (rx, _) in KINDS.items():
            if rx.search(txt[:300]):
                cands[kind].append(t); break
    print("c23 candidates by kind:", {k: len(v) for k, v in cands.items()})
    per_kind = n // len(KINDS) + 1
    picked = []
    for kind, titles in cands.items():
        rng.shuffle(titles); picked += [(kind, t) for t in titles[:per_kind * 2]]
    rng.shuffle(picked)
    rows = []; langs = ["ta", "tanglish", "en"]; i = 0; en_fail = 0
    for kind, t in picked:
        if len(rows) >= n:
            break
        lang = langs[i % 3]; i += 1
        q = rng.choice(KINDS[kind][1][lang]).format(t=t)
        if lang == "en":
            en_title, ext = en_extract(t)
            if not ext:
                en_fail += 1; i -= 1; continue
            ans = first_sentences(ext, 500); src = f"English Wikipedia: {en_title}"
        elif lang == "tanglish":
            ans = "Idhu pathi: " + first_sentences(leads[t], 420); src = f"Tamil Wikipedia: {t}"
        else:
            ans = first_sentences(leads[t], 450); src = f"Tamil Wikipedia: {t}"
        rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": q}, {"role": "assistant", "content": ans}],
                     "lang": lang, "slice": "c23_history_benign", "kind": kind, "title": t, "source": src, "license": "CC BY-SA 4.0", "needs_human_check": True})
        if len(rows) % 50 == 0:
            print(f"  c23 {len(rows)} rows", flush=True)
    with open(os.path.join(BUILD, "c23_history_benign.jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"c23: {len(rows)} rows; by lang {dict(collections.Counter(r['lang'] for r in rows))}; by kind {dict(collections.Counter(r['kind'] for r in rows))}; English extracts unavailable for {en_fail} titles")
    return rows

# ---------------------------------------------------------------- 3. c24 extractive QA (IndicQA shape)
PATTERNS = [
    # (regex over the lead, question templates by language, group name of the answer span)
    (re.compile(r"\((?:பிறப்பு|பி\.)\s*:?\s*([^)]*?(\d{4})[^)]*)\)"), {"ta": "{t} எப்போது பிறந்தார்?", "tanglish": "{t} eppo porandhaaru?", "en": "When was {t} born?"}, 2),
    (re.compile(r"(\d{4})\s*(?:ஆம்|-ஆம்|ம்)?\s*ஆண்டு(?:ல்|இல்)?\s*(?:நிறுவப்பட்டது|தொடங்கப்பட்டது|கட்டப்பட்டது|அமைக்கப்பட்டது|உருவாக்கப்பட்டது)"), {"ta": "{t} எந்த ஆண்டில் நிறுவப்பட்டது அல்லது கட்டப்பட்டது?", "tanglish": "{t} endha varusham nirvappattadhu / kattapattadhu?", "en": "In which year was {t} founded or built?"}, 1),
    (re.compile(r"([஀-௿]+)\s+மாவட்டத்தி(?:ல்|லுள்ள|ன்)"), {"ta": "{t} எந்த மாவட்டத்தில் உள்ளது?", "tanglish": "{t} endha maavattathula irukku?", "en": "In which district is {t}?"}, 1),
    (re.compile(r"([஀-௿]+(?:\s[஀-௿]+)?)\s+(?:எழுதிய|இயற்றிய)\s"), {"ta": "{t} யார் எழுதினார்?", "tanglish": "{t} yaar ezhudhinaanga?", "en": "Who wrote {t}?"}, 1),
    (re.compile(r"(\d{4})\s*(?:ஆம்|-ஆம்|ம்)?\s*ஆண்டு(?:ல்|இல்)?\s*(?:இறந்தார்|மறைந்தார்|காலமானார்)"), {"ta": "{t} எந்த ஆண்டில் இறந்தார்?", "tanglish": "{t} endha varusham irandhaaru?", "en": "In which year did {t} die?"}, 1),
]

def build_c24(leads, n=300):
    rows = []; titles = list(leads); rng.shuffle(titles); langs = ["ta", "tanglish", "en"]; per_pat = collections.Counter()
    for t in titles:
        if len(rows) >= n:
            break
        if not re.fullmatch(r"[஀-௿\s.]{3,40}", t):
            continue
        txt = leads[t][:900]
        for pi, (rx, qs, g) in enumerate(PATTERNS):
            m = rx.search(txt)
            if not m:
                continue
            span = m.group(g).strip()
            if not span or span not in txt or len(span) > 40 or per_pat[pi] >= n // len(PATTERNS) + 10:
                continue
            lang = langs[len(rows) % 3]
            q = qs[lang].format(t=t)
            user = f"பத்தி:\n{txt}\n\nகேள்வி: {q}\n(பத்தியில் உள்ள சொற்களால் மட்டும் சுருக்கமாகப் பதிலளிக்கவும்.)" if lang == "ta" else \
                   (f"Passage:\n{txt}\n\nQuestion: {q}\n(Answer briefly with words from the passage only.)" if lang == "en" else f"Passage:\n{txt}\n\nKelvi: {q}\n(Passage la irukkura vaarthai-la mattum short-a badhil sollu.)")
            rows.append({"messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}, {"role": "assistant", "content": span}],
                         "lang": lang, "slice": "c24_extractive_qa", "pattern": pi, "title": t, "answer_span": span, "source": "Tamil Wikipedia lead (tawiki_20260801_fs)", "license": "CC BY-SA 4.0", "needs_human_check": True})
            per_pat[pi] += 1
            break
    with open(os.path.join(BUILD, "c24_extractive_qa.jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"c24: {len(rows)} rows; by pattern {dict(per_pat)}; by lang {dict(collections.Counter(r['lang'] for r in rows))}; mean span chars {sum(len(r['answer_span']) for r in rows) / max(1, len(rows)):.1f}")
    return rows

if __name__ == "__main__":
    build_c19_v2()
    leads = load_leads()
    print("leads:", len(leads))
    build_c24(leads)
    build_c23(leads)
