"""What each shipped knowledge pack can and cannot answer, from the chunks it actually holds (2026-09-14).

Reads the shipped pack files dist/app_packs/packs/<name>.sqlite (the docs table is what the phone searches) and the pack's
data/packs/<name>/chunks.jsonl for each chunk's page URL and section names (same rows, same order; checked). All shares and verdicts
are on the shipped text, which build_app_packs.py cuts to the first 2,000 characters of each chunk; the phone then puts only the first
1,500 characters of the chosen chunk into the prompt (RetrievalLayer.kt, text.take(1500)). Both cuts are reported. For every pack:

1. Text shares. Lead: the part of a page's first chunk before its first section heading (Wikipedia and Wikibooks pages start with a
   lead); section body: everything else. Procedural: a chunk with at least PROC_MIN procedure markers per 100 words (imperative and
   obligative verb forms, quantities and units, step words, sowing, planting, dosing, applying or filing words, numbered lines),
   counted separately from lead or body. Full article: the pack's text for a Tamil Wikipedia page compared with the whole article in
   the offline dump data/index/tawiki_20260801_fs/articles.jsonl.
2. What it can answer: chunk groups by the pack's own topic label (crop, dish, finance topic, nature kind), each with template example
   questions backed by a chunk id: a definition question on an article's lead, and a procedure question on a procedural chunk.
3. What it cannot answer: a fixed list of obvious questions for the topic (GAPS below), each checked by a direct full-text search of
   the question's topic terms over the whole pack (not the phone's gate): "answers" when a chunk whose title names the topic is of the
   right kind (procedural for a how question, a definition for a what question), "topic only" when on-topic chunks exist (title names
   the topic, or the body names it three times) but none of that kind, "not covered" when no chunk is on topic. The verdicts are heuristic; the report prints the chunk each verdict rests on.

  .venv/bin/python eval/pack_content_audit.py   -> eval/results/pack_content_audit.md and eval/results/pack_content_audit.json
"""
import collections, json, os, re, sqlite3, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKS = ["cooking", "agriculture", "finance", "nature"]
PROC_MIN = 3.0   # procedure markers per 100 words for a chunk to count as procedural

PROC_RX = re.compile("|".join([
    # Tamil imperative and obligative forms, step words
    r"[க-ஹ]வும்(?=[\s,.;:]|$)", r"வேண்டும்", r"முதலில்", r"பின்னர்", r"பிறகு", r"அடுத்து", r"இறுதியாக",
    # quantities and units
    r"\d+\s*(?:கிலோ|கி\.?கி|கிராம்|லிட்டர்|மி\.?லி|தேக்கரண்டி|மேசைக்கரண்டி|கப்|டம்ளர்|எக்டேர்|ஹெக்டேர்|ஏக்கர்|செ\.?மீ|மீ\b|நாட்கள்|நாள்|வாரம்|%)",
    r"(?i:\b\d+(?:\.\d+)?\s*(?:kg|g|mg|ml|l|litres?|liters?|cups?|tsp|tbsp|teaspoons?|tablespoons?|ha|hectares?|acres?|cm|days?|minutes?|mins?|%)\b)",
    # farming, cooking and filing actions
    r"விதைப்பு|விதைக்க|நடவு|நடுதல்|நாற்றங்கால்|உரமிட|இட வேண்டும்|தெளிக்க|தெளிப்பு|பாய்ச்ச|களை எடு|அறுவடை செய்|இடைவெளி|கலந்து|வறுத்து|அரைத்து|வேக வை|தாளி|ஊற வை|சேர்த்து|விண்ணப்பி|சமர்ப்பி|பதிவு செய்",
    r"(?m:^\s*(?:\d+[.)]|[-*•])\s)", r"(?i:\b(?:add|mix|stir|heat|boil|fry|soak|grind|serve|sow|plant|apply|spray|irrigate|submit|click|select|log ?in|visit|fill)\b)",
    r"(?i:\bingredients\b|\bprocedure\b|\bmethod\b|\bstep\s*\d)",
]))

# obvious questions for each pack's topic: (question, kind, topic terms any of which marks a chunk as on topic)
GAPS = {
    "agriculture": [
        ("நெல் சாகுபடி முறைகள் என்ன?", "how", ["நெல்"]),
        ("வாழை சாகுபடி செய்வது எப்படி?", "how", ["வாழை"]), ("கரும்பு சாகுபடி செய்வது எப்படி?", "how", ["கரும்பு"]),
        ("நிலக்கடலை சாகுபடி செய்வது எப்படி?", "how", ["நிலக்கடலை", "வேர்க்கடலை"]), ("மஞ்சள் சாகுபடி செய்வது எப்படி?", "how", ["மஞ்சள்"]),
        ("தக்காளி சாகுபடி செய்வது எப்படி?", "how", ["தக்காளி"]), ("மண்புழு உரம் தயாரிப்பது எப்படி?", "how", ["மண்புழு"]),
        ("மண் பரிசோதனைக்கு மாதிரி எடுப்பது எப்படி?", "how", ["மண் பரிசோதனை", "மண்மாதிரி"]), ("சொட்டு நீர்ப் பாசனம் அமைப்பது எப்படி?", "how", ["சொட்டு நீர்"]),
        ("தென்னையில் காண்டாமிருக வண்டைக் கட்டுப்படுத்துவது எப்படி?", "how", ["காண்டாமிருக வண்டு"]), ("நெல் குலை நோயைக் கட்டுப்படுத்துவது எப்படி?", "how", ["குலை நோய்"]),
        ("பிஎம் கிசான் திட்டத்தில் விண்ணப்பிப்பது எப்படி?", "how", ["கிசான் சம்மான்", "PM-KISAN"]), ("பயிர்க் காப்பீட்டில் பதிவு செய்வது எப்படி?", "how", ["பயிர்க் காப்பீடு", "பசல் பீமா"]),
        ("இயற்கை உரம் என்றால் என்ன?", "what", ["இயற்கை உரம்"]), ("சொட்டு நீர்ப் பாசனம் என்றால் என்ன?", "what", ["சொட்டு நீர்"]),
        ("செம்மை நெல் சாகுபடி என்றால் என்ன?", "what", ["செம்மை நெல்"]), ("உயிர் உரம் என்றால் என்ன?", "what", ["உயிர் உர"]),
    ],
    "finance": [
        ("நிலை வைப்பு (FD) என்றால் என்ன?", "what", ["நிலை வைப்பு"]), ("யுபிஐ என்றால் என்ன?", "what", ["யுபிஐ", "UPI", "ஒருங்கிணைந்த பணப்பரிமாற்ற"]),
        ("யுபிஐ பின் அமைப்பது அல்லது மாற்றுவது எப்படி?", "how", ["யுபிஐ", "UPI"]), ("பான் அட்டைக்கு விண்ணப்பிப்பது எப்படி?", "how", ["நிரந்தர கணக்கு எண்", "பான்"]),
        ("இபிஎஃப் பணத்தை எடுப்பது எப்படி?", "how", ["EPF", "வருங்கால வைப்பு நிதி", "provident fund"]), ("இபிஎஃப் இருப்பைப் பார்ப்பது எப்படி?", "how", ["EPF", "passbook", "UAN"]),
        ("வருமான வரிக் கணக்கைத் தாக்கல் செய்வது எப்படி?", "how", ["வருமான வரி"]), ("கடன் EMI கணக்கிடுவது எப்படி?", "how", ["EMI", "மாதத் தவணை"]),
        ("KYC என்றால் என்ன?", "what", ["KYC", "வாடிக்கையாளரை அறிந்து"]), ("ஏடிஎம் அல்லது OTP மோசடியைத் தவிர்ப்பது எப்படி?", "how", ["மோசடி", "OTP"]),
        ("சுகன்யா சம்ரிதி திட்டம் என்றால் என்ன?", "what", ["சுகன்யா"]), ("பரஸ்பர நிதி என்றால் என்ன?", "what", ["பரஸ்பர நிதி"]),
        ("ஆயுள் காப்பீடு என்றால் என்ன?", "what", ["ஆயுள் காப்பீடு"]),
    ],
    "cooking": [
        ("சாம்பார் செய்வது எப்படி?", "how", ["சாம்பார்", "sambar"]), ("ரசம் செய்வது எப்படி?", "how", ["ரசம்", "rasam"]),
        ("இட்லி மாவு அரைப்பது எப்படி?", "how", ["இட்லி", "idli"]), ("தோசை செய்வது எப்படி?", "how", ["தோசை", "dosa"]),
        ("வெண் பொங்கல் செய்வது எப்படி?", "how", ["பொங்கல்", "pongal"]), ("தேங்காய்ச் சட்னி செய்வது எப்படி?", "how", ["சட்னி", "chutney"]),
        ("பிரியாணி செய்வது எப்படி?", "how", ["பிரியாணி", "biryani"]), ("பாயசம் செய்வது எப்படி?", "how", ["பாயசம்", "payasam", "kheer"]),
        ("முறுக்கு செய்வது எப்படி?", "how", ["முறுக்கு", "murukku"]), ("புளியோதரை செய்வது எப்படி?", "how", ["புளியோதரை", "tamarind rice"]),
        ("கேசரி செய்வது எப்படி?", "how", ["கேசரி", "kesari"]), ("சப்பாத்தி செய்வது எப்படி?", "how", ["சப்பாத்தி", "chapati"]),
        ("இட்லி என்றால் என்ன?", "what", ["இட்லி"]), ("செட்டிநாடு சமையல் என்றால் என்ன?", "what", ["செட்டிநாடு"]),
    ],
    "nature": [
        ("மயில் பற்றிச் சொல்லுங்கள்", "what", ["மயில்"]), ("வேப்ப மரத்தின் பயன்கள் என்ன?", "what", ["வேம்பு", "வேப்ப"]),
        ("காகம் பற்றிச் சொல்லுங்கள்", "what", ["காகம்", "காக்கை"]), ("தாமரை பற்றிச் சொல்லுங்கள்", "what", ["தாமரை"]),
        ("மைனா பற்றிச் சொல்லுங்கள்", "what", ["மைனா"]), ("துளசி பற்றிச் சொல்லுங்கள்", "what", ["துளசி"]),
        ("ஆலமரம் பற்றிச் சொல்லுங்கள்", "what", ["ஆலமரம்", "ஆல மரம்"]), ("கிளி பற்றிச் சொல்லுங்கள்", "what", ["கிளி"]),
        ("வீட்டில் துளசி வளர்ப்பது எப்படி?", "how", ["துளசி"]), ("பறவைகளை அடையாளம் காண்பது எப்படி?", "how", ["பறவை"]),
    ],
}
# reviewed by reading the chunks (2026-09-14): question -> (verdict, note); the heuristic verdict is printed next to it
REVIEWED = {
    "நெல் சாகுபடி முறைகள் என்ன?": ("partial", "SRI method nursery and planting steps (agri-000090, agri-000576); no general transplanted-paddy guide; the heuristic's pick is a variety article"),
    "வாழை சாகுபடி செய்வது எப்படி?": ("partial", "the banana article has soil, suckers and planting (agri-000155) and harvest (agri-000157) paragraphs, not a stepwise guide"),
    "கரும்பு சாகுபடி செய்வது எப்படி?": ("partial", "ratoon cultivation (agri-000351) and sustainable sugarcane initiative; no planting guide for a fresh crop"),
    "தக்காளி சாகுபடி செய்வது எப்படி?": ("partial", "integrated plant protection with nursery practices (agri-000346), not a cultivation guide"),
    "சொட்டு நீர்ப் பாசனம் அமைப்பது எப்படி?": ("partial", "components of the system (agri-000335) and clogging fixes (agri-000336); no installation steps"),
    "மஞ்சள் சாகுபடி செய்வது எப்படி?": ("not covered", "turmeric chunks are variety and geographical-indication articles"),
    "நிலை வைப்பு (FD) என்றால் என்ன?": ("answers", "the term-deposit article defines fixed and cumulative deposits (fin-000156)"),
    "யுபிஐ என்றால் என்ன?": ("answers", "the UPI article lead (fin-000216, titled ஒருமித்த செலுத்துகை இணைப்பிடைமுகம்)"),
    "யுபிஐ பின் அமைப்பது அல்லது மாற்றுவது எப்படி?": ("not covered", "no UPI how-to"),
    "பான் அட்டைக்கு விண்ணப்பிப்பது எப்படி?": ("partial", "form 49A and the accepted identity and address proofs (fin-000147, section விண்ணப்பித்தல்); no online steps"),
    "இபிஎஃப் பணத்தை எடுப்பது எப்படி?": ("partial", "EPFO scheme and FAQ passages in English describe withdrawal rules; no claim steps; the Tamil article is general"),
    "இபிஎஃப் இருப்பைப் பார்ப்பது எப்படி?": ("not covered", "UAN is defined in the EPFO FAQ; no passbook or balance steps"),
    "வருமான வரிக் கணக்கைத் தாக்கல் செய்வது எப்படி?": ("not covered", "articles on the department and on tax evasion only"),
    "ஏடிஎம் அல்லது OTP மோசடியைத் தவிர்ப்பது எப்படி?": ("not covered", "the heuristic's pick is the Prevention of Money Laundering Act; no consumer fraud advice"),
    "பரஸ்பர நிதி என்றால் என்ன?": ("answers", "the mutual fund article lead (fin-000024); later chunks are US-centric (IRAs, S&P 500)"),
    "ஆயுள் காப்பீடு என்றால் என்ன?": ("answers", "a section of the insurance article (fin-000172)"),
    "இட்லி மாவு அரைப்பது எப்படி?": ("answers", "the Tamil Wikibooks idli recipe (cooking-00004, section செய்முறை: rice and urad ratio, soaking); the heuristic's pick is idli podi"),
    "தேங்காய்ச் சட்னி செய்வது எப்படி?": ("answers", "Tamil Wikibooks coconut chutney (cooking-00009) and the English Wikibooks recipe (cooking-00591)"),
    "செட்டிநாடு சமையல் என்றால் என்ன?": ("answers", "the Chettinad cuisine article (cooking-00142)"),
    "சாம்பார் செய்வது எப்படி?": ("answers, English", "English Wikibooks sambar recipes (cooking-00673 and others); the Tamil article is encyclopedic with a short preparation section"),
    "ரசம் செய்வது எப்படி?": ("answers, English", "English Wikibooks rasam recipe (cooking-00667); the Tamil article (cooking-00101) describes rasam without steps"),
    "தோசை செய்வது எப்படி?": ("answers, English", "English Wikibooks Dosa I and II recipes; the Tamil chunks with steps are variants (neer dosa, cooking-00320)"),
    "வெண் பொங்கல் செய்வது எப்படி?": ("answers, English", "English Wikibooks Khara Pongal and Chakarai Pongal recipes; the Tamil article (cooking-00030) has no steps"),
    "பிரியாணி செய்வது எப்படி?": ("answers, English", "English Wikibooks Simple Biryani (cooking-00678); Tamil biryani chunks are about styles and restaurants"),
    "பாயசம் செய்வது எப்படி?": ("answers, English", "English Wikibooks kheer (cooking-00632); the Tamil chunk with steps is a Kerala fruit payasam variant"),
    "முறுக்கு செய்வது எப்படி?": ("answers", "a short Tamil method (cooking-00102, section செயல் முறை) and an English Wikibooks recipe"),
    "புளியோதரை செய்வது எப்படி?": ("answers, English", "English Wikibooks Puliyodarai (cooking-00662); the Tamil article lists ingredients without steps"),
    "கேசரி செய்வது எப்படி?": ("answers", "a Tamil stepwise recipe (cooking-00103) and an English one"),
    "தாமரை பற்றிச் சொல்லுங்கள்": ("answers", "the lotus article (nature-00135); the heuristic's pick is a different plant named ஓரிதழ் தாமரை"),
    "கிளி பற்றிச் சொல்லுங்கள்": ("answers", "rose-ringed parakeet (nature-00086); the heuristic's pick is an African starling"),
    "ஆலமரம் பற்றிச் சொல்லுங்கள்": ("answers", "the banyan article, titled ஆல் (nature-00205)"),
    "பறவைகளை அடையாளம் காண்பது எப்படி?": ("not covered", "species articles only; no identification guide"),
    "வீட்டில் துளசி வளர்ப்பது எப்படி?": ("not covered", "the tulsi article has names and uses, no growing steps"),
}
TOPIC_KEY = {"cooking": "dish", "agriculture": "crop", "finance": "topic", "nature": "kind"}

def words(s): return len(s.split())
def proc_score(body):
    return 100.0 * len(PROC_RX.findall(body)) / max(40, words(body))
def body_of(text):
    return text.split("\n\n", 1)[1] if "\n\n" in text else text

def lead_chars(row, first):
    """Characters of the lead in a chunk: only a page's first chunk has one; it ends at the first section heading written into the body."""
    if not first: return 0
    body = body_of(row["text"]); secs = [s for s in (row.get("section") or "").split(" | ") if s]
    if not secs: return len(body)
    cut = [body.find(s + ":") for s in secs if body.find(s + ":") > 0]
    return min(cut) if cut else len(body)   # no heading written into the body: the chunk's sections start after it (short tail merge)

def load(name):
    con = sqlite3.connect(os.path.join(ROOT, "dist", "app_packs", "packs", f"{name}.sqlite"))
    docs = con.execute("SELECT id, title, text, meta FROM docs ORDER BY id").fetchall()
    rows = [json.loads(l) for l in open(os.path.join(ROOT, "data", "packs", name, "chunks.jsonl"), encoding="utf-8") if l.strip()]
    # build_app_packs.py writes each chunk's text cut to its first 2,000 characters; the rows must otherwise be the same, in order
    if len(rows) != len(docs) or any(r["title"] != d[1] or r["text"][:2000] != d[2] for r, d in zip(rows, docs)):
        raise SystemExit(f"{name}: chunks.jsonl does not match the shipped pack file row for row")
    for r, d in zip(rows, docs):
        r["doc_id"] = d[0]; r["meta"] = json.loads(d[3] or "{}"); r["built_chars"] = len(r["text"]); r["text"] = d[2]
    return con, rows

def fts(con, terms, k=40):
    q = " OR ".join('"' + t.replace('"', "") + '"*' for t in terms)   # prefix on the last word: Tamil case endings (உயிர் உரங்களின்)
    try: return [r[0] for r in con.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (q, k))]
    except sqlite3.OperationalError: return []

def titled(row, terms):
    return any(x.lower() in row["title"].lower() for x in terms)
def on_topic(row, terms):
    return titled(row, terms) or sum(body_of(row["text"]).lower().count(x.lower()) for x in terms) >= 3

def is_definition(row, terms):
    base = re.sub(r"\s*\(.*?\)\s*$", "", row["title"].split(":")[-1].split("/")[-1]).strip().lower()
    b = body_of(row["text"])[:400].lower()
    return any(base.startswith(x.lower()) for x in terms) or any(re.search(re.escape(x.lower()) + r"\S*\s+(?:என்பது|என்பவை|\(|is\b)", b) for x in terms)

def gap_row(con, byid, q, kind, terms, reviewed=None, note=None):
    ids = fts(con, terms); cand = [byid[i] for i in ids if i in byid and on_topic(byid[i], terms)]
    # "answers" needs a chunk whose title names the topic: a procedural one for a how question, a definition for a what question
    if kind == "how":
        good = sorted([r for r in cand if titled(r, terms) and r["proc"] >= PROC_MIN], key=lambda r: -r["proc"])
    else:
        good = [r for r in cand if titled(r, terms) and is_definition(r, terms)]
    verdict = "answers" if good else ("topic only" if cand else "not covered")
    best = (good or cand or [None])[0]
    bdesc = f"{best['id']}, {best['title']}, {(best.get('section') or '').split(' | ')[0] or 'lead'}, {best['proc']:.1f}" if best else "none"
    rv, note = (reviewed, note) if reviewed else (verdict, "heuristic verdict confirmed by reading the chunk")
    return ({"q": q, "kind": kind, "verdict": verdict, "reviewed": rv, "note": note, "on_topic": len(cand), "best": best["id"] if best else None},
            f"| {q} | {kind} | {verdict} | {len(cand)} | {bdesc} | {rv} | {note} |")

def main():
    full_needed = collections.defaultdict(set); packs = {}
    for name in PACKS:
        con, rows = load(name); packs[name] = (con, rows)
        for r in rows:
            if r["source"] == "ta.wikipedia": full_needed[r["title"]].add(name)
    full = {}
    with open(os.path.join(ROOT, "data", "index", "tawiki_20260801_fs", "articles.jsonl"), encoding="utf-8") as f:
        for l in f:
            d = json.loads(l)
            if d["title"] in full_needed: full[d["title"]] = len(d["text"])
    out = {"generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "proc_min": PROC_MIN, "packs": {}}
    L = [f"# Knowledge pack content audit ({out['generated']})", "",
         "Generated by eval/pack_content_audit.py from the shipped pack files (dist/app_packs/packs). Lead: the part of a page's first chunk before its first section heading. "
         f"Procedural: a chunk with at least {PROC_MIN:g} procedure markers per 100 words (imperative or obligative verbs, quantities, step words, sowing, dosing, applying or filing words, numbered lines). "
         "Full article: the pack's text for a Tamil Wikipedia page against the whole article in the 2026-08-01 dump. Verdicts in the gap tables are heuristic and name the chunk they rest on.", "",
         "## Shares", "",
         "| pack | chunks | pages | sources (chunks) | lead share of text | section body share | procedural chunks | procedural share of text | built text shipped (2,000-character cut) | chunks cut | shipped text inside the 1,500-character prompt window | Tamil Wikipedia text shipped vs whole article |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for name in PACKS:
        con, rows = packs[name]
        pages = collections.OrderedDict()
        for r in rows: pages.setdefault(r["url"], []).append(r)
        tot = lead = proc_chars = 0; nproc = 0
        for url, rs in pages.items():
            for i, r in enumerate(rs):
                b = body_of(r["text"]); n = len(b); tot += n
                r["lead_chars"] = lead_chars(r, i == 0); lead += r["lead_chars"]
                r["proc"] = round(proc_score(b), 2)
                if r["proc"] >= PROC_MIN: nproc += 1; proc_chars += n
        kept = sum(len(body_of(r["text"])) for r in rows if r["source"] == "ta.wikipedia" and r["title"] in full)
        whole = sum(full[t] for t in {r["title"] for r in rows if r["source"] == "ta.wikipedia" and r["title"] in full})
        src = collections.Counter(r["source"] for r in rows)
        built = sum(r["built_chars"] for r in rows); shipped = sum(len(r["text"]) for r in rows); ncut = sum(1 for r in rows if r["built_chars"] > 2000)
        window = sum(min(len(r["text"]), 1500) for r in rows)
        L.append(f"| {name} | {len(rows)} | {len(pages)} | {', '.join(f'{k} {v}' for k, v in src.most_common())} | {lead / tot:.0%} | {1 - lead / tot:.0%} | {nproc} ({nproc / len(rows):.0%}) | {proc_chars / tot:.0%} | {shipped / built:.0%} ({shipped / 1e3:.0f}k of {built / 1e3:.0f}k characters) | {ncut} ({ncut / len(rows):.0%}) | {window / shipped:.0%} | {kept / max(1, whole):.0%} ({kept / 1e3:.0f}k of {whole / 1e3:.0f}k characters) |")
        pk = {"chunks": len(rows), "pages": len(pages), "sources": dict(src), "lead_share": round(lead / tot, 3), "procedural_chunks": nproc,
              "procedural_text_share": round(proc_chars / tot, 3), "built_chars": built, "shipped_chars": shipped, "chunks_cut_2000": ncut, "prompt_window_share": round(window / shipped, 3), "tawiki_kept_share": round(kept / max(1, whole), 3), "single_chunk_pages": sum(1 for v in pages.values() if len(v) == 1)}
        # what it can answer: groups by the pack's own topic label
        key = TOPIC_KEY[name]; groups = collections.defaultdict(list)
        for r in rows: groups[str(r.get(key) or r["meta"].get(key) or "unlabelled")].append(r)
        D = [f"## {name}", "", f"{len(rows)} chunks from {len(pages)} pages; {pk['single_chunk_pages']} pages fit in one chunk. The built chunks hold whole articles, not leads; the shipped file keeps {pk['shipped_chars'] / pk['built_chars']:.0%} of that text after the 2,000-character cut ({pk['chunks_cut_2000']} chunks cut), which is {pk['tawiki_kept_share']:.0%} of the Tamil Wikipedia text of its articles.", "",
             f"### What it can answer, by {key} label (largest groups; template questions, each backed by a chunk id)", "",
             f"| {key} | chunks | procedural | definition example (lead) | procedure example |", "|---|---|---|---|---|"]
        pk["groups"] = {}
        for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:25]:
            leads = sorted([r for r in rs if r["lead_chars"] >= 150], key=lambda r: -r["lead_chars"])
            procs = sorted([r for r in rs if r["proc"] >= PROC_MIN], key=lambda r: -r["proc"])
            dq = f"{re.sub(r'^Cookbook:', '', leads[0]['title'])} என்றால் என்ன? ({leads[0]['id']})" if leads else "none"
            pq = (f"{re.sub(r'^Cookbook:', '', procs[0]['title'])}: {(procs[0].get('section') or '').split(' | ')[0] or 'முறை'} எப்படி? ({procs[0]['id']}, {procs[0]['proc']:.1f} markers per 100 words)") if procs else "none"
            D.append(f"| {g} | {len(rs)} | {len(procs)} | {dq} | {pq} |")
            pk["groups"][g] = {"chunks": len(rs), "procedural": len(procs), "definition_example": dq, "procedure_example": pq}
        # gaps
        D += ["", "### Obvious questions checked against the whole pack (direct full-text search of the topic terms, no gate)", "",
              "| question | kind | heuristic verdict | on-topic chunks | best chunk (id, title, first section, markers per 100 words) | reviewed verdict | review note |", "|---|---|---|---|---|---|---|"]
        pk["gaps"] = []; byid = {r["doc_id"]: r for r in rows}
        for q, kind, terms in GAPS[name]:
            g, line = gap_row(con, byid, q, kind, terms, *REVIEWED.get(q, (None, None)))
            D.append(line); pk["gaps"].append(g)
        cnt = collections.Counter(g["reviewed"] for g in pk["gaps"])
        D += ["", "Reviewed gap check: " + ", ".join(f"{v} {cnt[v]}" for v in ("answers", "answers, English", "partial", "poor", "topic only", "not covered") if cnt.get(v)) + f", of {len(pk['gaps'])}.", ""]
        detail += D; out["packs"][name] = pk
    # the two packs without a topic question set
    extra = []
    for fn, what in [("dictionary_small.sqlite", "word entries (headword, meanings); answers word-meaning requests only"), ("wiki_leads.sqlite", "Tamil Wikipedia lead sections only, by construction")]:
        p = os.path.join(ROOT, "dist", "app_packs", fn)
        if os.path.exists(p):
            n = sqlite3.connect(p).execute("SELECT count(*) FROM docs").fetchone()[0]
            extra.append(f"| {fn} | {n} | {what} |")
    L += ["", "| other pack | rows | content |", "|---|---|---|"] + extra + [""] + detail
    os.makedirs(os.path.join(ROOT, "eval", "results"), exist_ok=True)
    open(os.path.join(ROOT, "eval", "results", "pack_content_audit.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    json.dump(out, open(os.path.join(ROOT, "eval", "results", "pack_content_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(L[:14 + len(extra) + 3]))
    for name in PACKS:
        print(name, "heuristic", dict(collections.Counter(g["verdict"] for g in out["packs"][name]["gaps"])), "reviewed", dict(collections.Counter(g["reviewed"] for g in out["packs"][name]["gaps"])))

if __name__ == "__main__":
    main()
