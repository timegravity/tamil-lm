"""Run eval/routing_check.py after every change to routing.

Phase 5b retrieval safety net: pluggable retrieval (retrieval/config.yaml) over the
structured literature KB, the 2026-08 Tamil Wikipedia dump, and any folder or
search API added to the config. The exact work+number lookup still guarantees
verbatim literature quotes; a manually maintained fact sheet
(data/facts/current_officeholders.md) is prepended on office-holder, party or
election queries. For factual questions the model is told to answer only from
the passages and to say it lacks current information otherwise.

Usage:
  python serve.py --model ckpt/final/tamil-lm-2b-instruct --chat "திருக்குறள் 42 என்ன?"
  python serve.py --model ... --chat "..." --no-retrieval
  python serve.py --build-index            (rebuild the literature KB index under data/index/literature_kb)
  python serve.py --model ... --probe eval/literature_probe.jsonl --out logs/probe_retrieval.json
  python serve.py --retrieve "query"       (print what would be prepended; no model)
"""
import argparse, json, os, re
import safety_rules   # the safety rule file loader; the full rule list is private (licensing decision, updated 2026-09-14)
from transformers import StoppingCriteriaList
try:
    import family_safe as FS   # hashed lexicon backstop (family-safe release bar, 2026-09-08); FAMILY_SAFE=0 disables
except Exception:
    FS = None
from guard import Guard, refusal_text, detect_lang, self_harm_hint, helpline_block, support_text, romantic_roleplay_hint, kind_refusal, child_risk_hint, contested_topic_hint, neutral_reply, political_abstention, sheet_is_usable   # re-exported: eval/redteam.py imports serve.Guard
from retrieval import Retriever as SourceRetriever, DEFAULT_CONFIG, format_passages
from retrieval.packs import format_pack_block
from retrieval import dictionary as DICT
from retrieval import calc as CALC
from retrieval.kb import exact_lookup, format_context, load_units
from retrieval.facts import match_fact_sheet, matches as political_intent, load_sheet
from retrieval.litmatch import match_literature, is_creation_request, has_literature_cue, has_literature_term
from retrieval.text import nfc
from retrieval.translit import expand_query   # roman -> Tamil-script query expansion for retrieval (ruling 2026-09-09)
from retrieval import wiki_live as WL   # live Wikipedia tool (ruling 2026-09-08): fires only for factual questions the local index cannot answer confidently

FACT_INSTRUCTION = ("கேள்விக்கு நேரடியாகப் பதிலளிக்கவும்; \"மேலே உள்ள மூலங்களின்படி\" போன்ற தொடக்க வாசகங்கள் வேண்டாம். "
                    "மூலங்களில் உள்ள உண்மைகளை மட்டும் பயன்படுத்தவும்; மேற்கோள் காட்டும்போது மூல வரிகளை அப்படியே எழுதவும். "
                    "உண்மைச் செய்திகள் (நபர்கள், பதவிகள், தேதிகள், நிகழ்வுகள்) மூலங்களில் இல்லாவிட்டால், "
                    "\"என்னிடம் இதற்கான தற்போதைய தகவல் இல்லை\" என்று சொல்லி அதிகாரப்பூர்வ அல்லது செய்தி மூலத்தைப் பார்க்கச் சொல்லவும். மூலக் குறிப்பு வரி பதிலின் இறுதியில் தானாகச் சேர்க்கப்படும்; நீங்கள் எழுத வேண்டாம். "
                    "(Answer the question directly; never open with \"according to the sources above\". Use only facts that are in the sources; for facts not in them, say you do not have current information and point to an official or news source. The source line is added at the end for you; do not write one.)")   # ruling 2026-09-09: the answer just answers, source line at the end

PASSAGE_MIN_RAW = 12.0   # raw BM25 of the top local hit below this: no passage reaches the prompt (ruling 2026-09-09; set from the sweep-log score scan, eval/results/passage_threshold.md)

def passage_decision(retriever, query):
    """(hits, decision): local passages are prepended only when the top raw BM25 is at or above PASSAGE_MIN_RAW and the
    hit title overlaps the query (or the query is a known title). Logged per turn so a low-score passage never reaches the prompt silently."""
    q2, cands = expand_query(query, vocab_checker(retriever))   # romanised TAMIL words also searched in Tamil script ("kulambu" -> குழம்பு); English tokens are never transliterated
    hits, title, top, relevant = _best_hits(retriever, query, q2, cands)
    used = bool(hits) and (known_title(query) or (top >= PASSAGE_MIN_RAW and relevant))
    return (hits if used else []), {"top_raw": round(top, 2), "threshold": PASSAGE_MIN_RAW, "relevant": relevant, "used": used,
                                    "title": title[:80], "source": hits[0].get("source") if hits else None,
                                    "query_expanded": q2 if q2 != query else None, "transliterated": cands or None}

def _best_hits(retriever, query, q2, cands, use_text=True):
    """Search the expanded query and, when transliteration produced Tamil candidates, the candidates alone; the
    candidate-only hit wins when it is on-topic and the mixed query's top hit is not ("kulambu recipe": "recipe" alone
    pulls an unrelated article, குழம்பு pulls the right one)."""
    def run(q):
        try:
            h = retriever.search(q)
        except Exception:
            h = []
        t = float(h[0].get("score_raw", h[0].get("score", 0))) if h else 0.0
        ti = (h[0].get("title") or "") if h else ""
        return h, ti, t, (bool(h) and title_overlaps(q, ti, (h[0].get("text") or "") if use_text else ""))
    for t in entity_titles(query):   # "neeya naana" -> நீயா நானா: the article with that exact title
        r = run(t)
        if r[3]:
            return r
    best = run(q2)
    if cands and not best[3]:
        alt = run(" ".join(c for cs in cands.values() for c in cs))
        # the candidate-only hit must be on topic for the WHOLE query, not just for the transliterated words
        if alt[0] and title_overlaps(q2, alt[1], (alt[0][0].get("text") or "") if use_text else ""):
            return alt[0], alt[1], alt[2], True
    return best

_HOWTO_RX = re.compile(r"recipe|how to (make|cook|do|perform|play|use|fix|clean|start|learn|prepare|build|write|draw|tie|fold|wash|grow)|how do (i|you|we)|செய்முறை|செய்முரை|எப்படி (செய்|பண்ண|சமைக்க|உருவாக்க)|epdi (seiy|sey|pann|samai)|eppadi (seiy|sey|pann|samai)|seiyanum|seyyanum|pannanum|samaikk|சமைக்க|சமையல்|tips", re.I)
def is_howto_request(query):
    """Recipes and how-to requests: the model answers (with a passage only when the local index has the topic); the live Wikipedia tool never fires."""
    return bool(_HOWTO_RX.search(query))

_KB_RETRIEVER = None
KB_LOW_MIN_RAW = 18.0   # raised 2026-09-09: at 6.0 a science "explain in Tamil" request could match a kural with a low raw score
def kb_low_confidence(query):
    """Lower-confidence literature search (ruling 2026-09-09): BM25 over the literature KB only, for a query with a
    literature cue that the alias matcher could not place. Returns a literature match (mode kb_search) or None."""
    if not (has_literature_term(query) or known_title(query)):
        return None   # an explain word alone never reaches the literature KB
    global _KB_RETRIEVER
    if _KB_RETRIEVER is None:
        _KB_RETRIEVER = SourceRetriever(DEFAULT_CONFIG, only=["literature_kb"])
    from retrieval.litmatch import _strip_request_words
    core = _strip_request_words(query.lower()) or query
    q2, _c = expand_query(core)
    try:
        hits = _KB_RETRIEVER.search(q2)
    except Exception:
        hits = []
    for h in hits[:3]:
        u = (h.get("meta") or {}).get("unit")
        top = float(h.get("score_raw", h.get("score", 0)))
        if u is not None and top >= KB_LOW_MIN_RAW and not u.get("adult_theme") and str(u.get("unit_type")) not in ("episode", "author_profile", "chapter", "intro", "summary"):
            return {"unit": u, "units": [u], "alias": None, "kind": "first_line", "mode": "kb_search", "score": round(top, 2)}
    return None

class Retriever:
    """Model-free retrieval facade used by eval/political_safety.py and serve.py.
    context(query, k) -> string of retrieved passages, each prefixed with a citation
    marker "[மூலம்: <title>]", with the fact sheet first when it matches; "" when nothing matches."""
    def __init__(self, config_path=DEFAULT_CONFIG):
        self.units = load_units()
        self.sources = SourceRetriever(config_path)

    def passages(self, query, k=5):
        out = []
        u = exact_lookup(self.units, query)
        if u is not None:
            out.append({"title": f"{u.get('work')} {u.get('number', '')}".strip(), "text": format_context([u]), "source": "literature_kb", "exact": True})
        for h in self.sources.search(query, k=k):
            if u is not None and h["source"] == "literature_kb" and h["meta"].get("unit") is u:
                continue
            out.append({"title": h["title"], "text": h["text"], "source": h["source"], "exact": False})
        return out[:k]

    def context(self, query, k=5):
        blocks = []
        stage, lit = decide_route(query, self.units)
        if stage == "literature":
            blocks += literature_blocks(lit)
        if stage in ("small_talk", "identity", "none"):
            return ""
        sheet = match_fact_sheet(query)
        if sheet:
            blocks.append(sheet)
        if self_harm_hint(query):
            hb = helpline_block(detect_lang(query))
            if hb:
                blocks.append("[Helplines, verified] " + hb + "\nRespond with warmth, briefly, and include these numbers.")
        if stage != "literature":
            hits, dec = passage_decision(self.sources, query)
            if dec["used"]:
                for p in self.passages(query, k=k):
                    blocks.append(f"[மூலம்: {p['title']}]\n{p['text'].replace('[மூலம்] ', '', 1)}")
        return "\n\n".join(blocks)

def build_kb_index():
    r = SourceRetriever(DEFAULT_CONFIG, only=["literature_kb"])
    src = r.source("literature_kb")
    print(f"indexed {len(src.units)} literature units -> {src.idx.dir}")

PACKS = None   # retrieval.packs.PackSet, loaded once by load_packs(); PACKS_OFF=1 disables every pack

def load_packs():
    global PACKS
    if PACKS is None and os.environ.get("PACKS_OFF", "0") != "1":
        from retrieval.packs import PackSet
        PACKS = PackSet()
    return PACKS

# Packs whose answers may contain the blocked terms (Vignesh 2026-09-13: cow is blocked except in the agriculture and nature packs)
BLOCKED_TERM_PACKS = ("agriculture", "nature")

def pack_decision(query, meta=None):
    """The best enabled pack's chunk when its floor and margin both clear, else None. meta["packs_enabled"] (set per turn
    from the UI or the PACKS env var) is the ONLY set searched; the decision with every searched pack's numbers is logged."""
    ps = load_packs()
    if ps is None or not ps.packs:
        return None
    enabled = (meta or {}).get("packs_enabled")
    hits, dec = ps.decide(query, enabled=enabled, lang=detect_lang(query))
    if meta is not None:
        meta["pack_decision"] = dec; meta["packs_enabled"] = dec["enabled"]
    return hits[0] if hits else None

def pack_caveat(pack_name, lang, hit=None):
    """Lines appended after an answer grounded on a pack chunk (ruling 2026-09-10)."""
    ps = load_packs(); pk = ps.packs.get(pack_name) if ps else None
    kind = pk.caveat if pk else "none"
    meta = (hit or {}).get("meta") or {}
    L = lang if lang in ("ta", "en", "tanglish") else "en"
    out = []
    if kind == "finance":
        out.append({"ta": "இது பொதுத் தகவல் மட்டுமே; நிதி ஆலோசனை அல்ல. முதலீடு அல்லது கடன் முடிவுகளுக்கு முன் அதிகாரப்பூர்வ ஆவணங்களையும் தகுதி பெற்ற ஆலோசகரையும் பாருங்கள்.",
                    "en": "This is general information, not financial advice. Check the official documents and a qualified adviser before any investment or loan decision.",
                    "tanglish": "Idhu general information mattum, financial advice illa. Investment or loan decision edukkum munnadi official documents um qualified adviser um paarunga."}[L])
    if kind in ("dated", "govservices", "finance") and (meta.get("dated") or kind == "govservices"):
        out.append({"ta": "தொகைகள், தகுதி விதிகள், கட்டணங்கள் மற்றும் தேவையான ஆவணங்கள் காலப்போக்கில் மாறும்; இந்தத் தகவல் மூலப் பக்கத்தின் தேதிக்கு உரியது. தற்போதைய நிலையை அதிகாரப்பூர்வ தளத்தில் உறுதிப்படுத்துங்கள்.",
                    "en": "Amounts, eligibility rules, fees and document lists change over time; this reflects the source page as of its date. Confirm the current position on the official site.",
                    "tanglish": "Amounts, eligibility rules, fees, documents ellam kaalathoda maarum; idhu source page-oda date padi. Current nilai official site-la confirm pannunga."}[L])
    site = meta.get("official_site")
    if kind == "govservices" and site:
        out.append({"ta": f"அதிகாரப்பூர்வ தளம்: {site}", "en": f"Official site: {site}", "tanglish": f"Official site: {site}"}[L])
    return "\n".join(out)

def retrieval_context(retriever, units, user_msg, stage=None, lit=None, meta=None):
    """Returns (context_text, how, exact_unit). how in {exact, literature, bm25, none}.
    stage/lit come from decide_route; when absent they are computed here. meta (dict) receives the passage decision."""
    if stage is None:
        stage, lit = decide_route(user_msg, units)
    u = lit["unit"] if lit and lit.get("kind") == "work_number" or (lit and lit.get("kind") in ("poem_title", "first_line")) else None
    blocks = []
    sheet = match_fact_sheet(user_msg)
    if sheet:
        blocks.append(sheet)
    if self_harm_hint(user_msg):   # serving rule: support + verified helplines, never a bare refusal
        hb = helpline_block(detect_lang(user_msg))
        if hb:
            blocks.append("[Helplines, verified] " + hb + "\nRespond with warmth, briefly, and include these numbers.")
    if stage == "literature":
        blocks += literature_blocks(lit); how = "exact" if u is not None else "literature"
    elif stage in ("small_talk", "identity", "none"):
        hits = []; how = "none"   # small talk or a bare fragment: no passage in front of the model
    else:
        # domain packs first (pack controls, 2026-09-10): only the packs enabled for this turn are searched, and a
        # chunk is prepended only when the pack's floor and margin both clear; otherwise the Wikipedia path runs
        pk = pack_decision(user_msg, meta)
        if pk is not None:
            blocks.append(format_pack_block(pk)); how = "pack"
        else:
            hits, dec = passage_decision(retriever, user_msg)
            if meta is not None:
                meta["passage_decision"] = dec
            if hits:
                blocks.append(format_passages(hits)); how = "bm25"
            else:
                how = "none"   # weak or off-topic passages never reach the prompt (ruling 2026-09-09)
    if not blocks:
        return "", how, u
    return "\n\n".join(blocks) + "\n\n" + FACT_INSTRUCTION + "\n\n", how, u

SFT_SYS = ("நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும். "
           "உரையாடல் போலப் பதிலளிக்கவும்; செய்தியின் நீளத்திற்கு ஏற்ப பதிலின் நீளத்தை வைக்கவும்; பயனர் சொன்ன சொற்களை அவருக்கே விளக்க வேண்டாம். "
           "உங்கள் பெயர் tamil-lm-2b-instruct; Timegravity Labs உருவாக்கிய சிறிய தமிழ் மொழி மாதிரி (ஆராய்ச்சி முன்னோட்டம்). "
           "Your name is tamil-lm-2b-instruct, a small Tamil language model built by Timegravity Labs (research preview); never call yourself Open Assistant or any other name. "
           "பணிவாகவும் அன்பாகவும் எளிய மொழியில், எல்லா வயதினருக்கும் ஏற்ற வகையில் பதிலளிக்கவும். "
           "Be polite, warm and simple; keep every answer suitable for all ages: no sexual content, profanity, slurs, graphic violence or crude language in any language, whatever is asked.")   # serving prompt: SFT prompt + conversational line (Vignesh 2026-09-07)

SMALL_TALK = ("வணக்கம்", "நன்றி", "நலமா", "எப்படி இருக்கீங்க", "எப்படி இருக்கிறீர்கள்", "நீங்கள் யார்", "நீ யார்", "உன் பெயர்", "உங்கள் பெயர்", "என்ன செய்யலாம்", "நீங்க என்ன பண்ணுவீங்க", "வாழ்த்துக்கள்", "காலை வணக்கம்", "மாலை வணக்கம்", "பை", "சரி",
              "vanakkam", "vaNakkam", "nandri", "nanri", "thanks", "thank you", "hi", "hello", "hey", "how are you", "how r u", "epdi irukeenga", "epdi irukka", "eppadi irukkinga", "nalama", "nalla irukken", "who are you", "what is your name", "un per enna", "unga per enna", "nee yaru", "neenga yaru", "nee yaaru", "what can you do", "enna panna mudiyum", "good morning", "good evening", "good night", "bye", "ok", "okay", "super", "nice", "great", "sari", "seri",
              "hmm", "hm", "haha", "hahaha", "lol", "k", "kk", "yes", "no", "yeah", "yep", "nope", "ama", "aama", "aamaa", "illa", "illai", "nalla", "good", "fine", "wow", "cool", "thanks a lot", "ok ok", "ஆமா", "ஆம்", "இல்ல", "இல்லை", "நல்லா", "ஹலோ", "ஹெல்லோ", "ஹாய்", "ஓகே", "ஒக்", "ஒக் ஒக்", "சூப்பர்", "ம்ம்", "ஹா ஹா")
_QUESTION_MARKS = ("?", "என்ன", "யார்", "எப்படி", "ஏன்", "எங்கே", "எப்போது", "எது", "எவ்வளவு", "enna", "yaaru", "yaru", "epdi", "eppadi", "yen", "enga", "eppo", "edhu", "evlo",
                   "what", "who", "how", "why", "where", "when", "which", "explain", "tell me", "sollu", "sollunga", "விளக்கு", "சொல்லு", "சொல்லுங்கள்", "கூறு")

IDENTITY_Q = ("நீ யார்", "நீங்கள் யார்", "உன் பெயர்", "உங்கள் பெயர்", "நீ என்ன", "யார் நீ", "உன்னை உருவாக்கியது யார்", "உங்களை உருவாக்கியது",
              "who are you", "what is your name", "what's your name", "your name", "who made you", "who built you", "who created you", "what are you", "which model are you", "are you chatgpt", "are you open assistant",
              "un per enna", "unga per enna", "nee yaru", "nee yaaru", "neenga yaru", "neenga yaaru", "unna yaru", "yaru nee", "un peyar", "unga peyar", "nee enna", "unnai yaru")
def is_identity_question(msg):
    m = msg.strip().lower().rstrip("?!.,")
    return any(k in m for k in IDENTITY_Q)

def identity_reply(lang="ta"):
    """Deterministic identity answer: the SFT data carried Open Assistant self-statements (ROUND3.md), so the model cannot be trusted with this yet."""
    return {"ta": "நான் tamil-lm-2b-instruct, Timegravity Labs உருவாக்கிய சிறிய தமிழ் மொழி மாதிரி (ஆராய்ச்சி முன்னோட்டம்). தமிழ், Tanglish, English மூன்றிலும் உரையாட, மொழிபெயர்க்க, திருக்குறள் போன்ற இலக்கியங்களை மேற்கோள் காட்ட உதவுவேன்.",
            "tanglish": "Naan tamil-lm-2b-instruct, Timegravity Labs build panna oru small Tamil language model (research preview). Tamil, Tanglish, English la pesa, translate panna, Thirukkural madhiri literature quote panna help pannuven.",
            "en": "I am tamil-lm-2b-instruct, a small Tamil language model built by Timegravity Labs (research preview). I can chat in Tamil, Tanglish and English, translate, and quote Tamil literature such as the Thirukkural."}[lang if lang in ("ta", "tanglish", "en") else "en"]

EXPLAIN_WORDS = ("விளக்கு", "விளக்கம்", "பொருள்", "அர்த்தம்", "எக்ஸ்ப்லைன்", "explain", " mean", "what does", "meaning", "means", "porul", "vilakku", "vilakkam", "artham", "enna solludhu", "என்ன சொல்கிறது", "என்ன கூறுகிறது")

TASK_WORDS = ("செய்முறை", "செய்முரை", "recipe", "எப்படி", "how to", "how do", "meaning", "பொருள்", "translate", "மொழிபெயர்", "விளக்கு", "explain", "recipe", "epdi", "eppadi", "seimurai", "seymurai", "porul", "vilakku", "mozhipeyar", "list", "பட்டியல்", "steps", "படிகள்")
_TITLES = None
def known_title(msg):
    """Exact match of the (lowercased) message against KB work titles and Tamil Wikipedia article titles."""
    global _TITLES
    if _TITLES is None:
        t = set()
        try:
            for l in open("data/index/tawiki_20260801/articles.jsonl", encoding="utf-8"):
                t.add(json.loads(l).get("title", "").strip().lower())
        except Exception: pass
        try:
            for u in load_units():
                for k in ("work", "work_en", "author"):
                    if u.get(k): t.add(str(u[k]).strip().lower())
        except Exception: pass
        _TITLES = t
    return msg.strip().lower().rstrip("?!.,") in _TITLES

_LATIN_CHIT = {"hmm", "hm", "haha", "lol", "k", "kk", "yes", "no", "yeah", "yep", "nope", "ama", "aama", "illa", "nalla", "good", "fine", "wow", "cool", "ok", "okay", "ok ok", "super", "nice", "great", "sari", "seri", "bye", "hi", "hello", "hey", "thanks", "thank you", "nandri", "nanri", "please", "plz", "sorry", "hmmm", "ha", "hehe", "oh", "ohh", "ah", "ahh", "uh", "um", "ya", "yaa", "da", "dei", "machan", "machi", "bro", "sis", "anna", "akka", "amma", "appa", "test", "testing", "hello hello", "hi hi"}
def entity_titles(msg, windows=False):
    """Known titles (KB works, Tamil Wikipedia articles) that the message names directly or through transliteration
    ("kaaviri aaru" -> காவிரி ஆறு). Short messages only (1 to 3 words)."""
    m = msg.strip().lower().rstrip("?!.,")
    words = [w for w in re.split(r"[\s.,!?]+", m) if w]
    if not words:
        return []
    known_title("x")   # loads _TITLES
    found = []
    if len(words) <= 3 and m in _TITLES:
        found.append(m)
    if len(words) > 3:   # longer messages: only when asked for windows (passage relevance for folded follow-ups), never for routing
        if not windows:
            return []
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                for t in entity_titles(" ".join(words[i:i + n])):
                    if t not in found:
                        found.append(t)
        return found[:4]
    latin = [w for w in words if re.fullmatch(r"[a-z]+", w)]
    if latin and len(latin) == len(words):
        from retrieval.translit import candidates
        cands = candidates(words, 4)
        lists = [cands.get(w, []) for w in words]
        if all(lists):
            import itertools
            for combo in itertools.islice(itertools.product(*lists), 256):
                forms = {" ".join(combo), "".join(combo)}
                if len(combo) >= 2:   # sandhi: doubled initial consonant of the next word (போதை + பொருள் -> போதைப்பொருள்)
                    for i in range(1, len(combo)):
                        nxt = combo[i]
                        if nxt and nxt[0] in "கசதப":
                            forms.add("".join(combo[:i]) + nxt[0] + "\u0bcd" + "".join(combo[i:]))
                            forms.add(" ".join(combo[:i]) + " " + nxt[0] + "\u0bcd" + " ".join(combo[i:]))
                for f in forms:
                    if f in _TITLES and f not in found:
                        found.append(f)
    return found[:4]

def entity_like(msg):
    """A 1 to 3 word message that names a thing rather than chatting: a known title (direct or transliterated), or a
    Latin-script message that is not chit-chat and not a Tanglish function phrase (the live Wikipedia tool has an English fallback)."""
    m = msg.strip().lower().rstrip("?!.,")
    words = [w for w in re.split(r"\s+", m) if w]
    if not words or len(words) > 3:
        return False
    if entity_titles(m):
        return True
    if all(re.fullmatch(r"[a-z]+", w) for w in words) and m not in _LATIN_CHIT and not any(w in _LATIN_CHIT for w in words) and len(m) >= 4:
        return not any(w in _TANGLISH_FUNC for w in words)
    return False
_TANGLISH_FUNC = {"enna", "epdi", "eppadi", "yen", "yaru", "yaaru", "irukku", "iruku", "illa", "panna", "pannu", "sollu", "solu", "naan", "nee", "neenga", "oru", "adhu", "idhu", "edhu", "ethu", "ippo", "appo", "inga", "anga", "enga", "vaa", "po", "va", "romba", "konjam", "sari", "seri", "aama", "ama", "venum", "vendam", "mudiyum", "mudiyadhu", "theriyum", "theriyadhu", "theriyathu", "pathi", "patri", "kudu", "tha", "thaan", "dhaan", "ah", "ahh", "la", "ku", "kku", "oda", "um", "nu", "na"}

_NOT_PERSON_WORDS = {"tv", "channel", "movie", "film", "padam", "song", "paattu", "serial", "bank", "hotel", "college", "school", "hospital", "temple", "kovil", "city", "town", "station", "bus", "train", "road", "street", "shop", "kadai", "company", "network", "app", "phone", "mobile", "recipe", "news", "radio", "fm", "store", "mall", "park", "beach", "hill", "river", "lake", "dam", "airport", "university", "exam", "result", "ticket", "price", "rate", "weather", "mazhai", "rain",
                     "டிவி", "சேனல்", "படம்", "பாட்டு", "சீரியல்", "வங்கி", "ஹோட்டல்", "கல்லூரி", "பள்ளி", "மருத்துவமனை", "கோவில்", "கோயில்", "நகரம்", "ஊர்", "பஸ்", "ரயில்", "கடை", "நிறுவனம்", "செய்தி", "விலை", "வானிலை", "மழை", "ரெசிபி", "செய்முறை"}
_HONORIFICS = ("mr", "mrs", "ms", "dr", "prof", "sri", "shri", "thiru", "thirumathi", "selvi", "திரு", "திருமதி", "செல்வி", "டாக்டர்", "முனைவர்", "பேராசிரியர்", "ஐயா", "அம்மா")
_PERSON_FRAME_RX = re.compile(r"^(who is|who was|who's|whois)\s+(.{2,60})$|^(.{2,60}?)\s+(yaru|yaaru|yaar|யார்|யாரு|who)\??$|^(.{2,60}?)\s+(pathi|patri|பற்றி)\s+(sollu|sollunga|சொல்லு|சொல்லுங்க|சொல்லுங்கள்|kudu)\??$", re.I)
def person_name_like(msg):
    """A message that names a person: honorific + name, two or three capitalised roman tokens, a Tamil or roman name in a
    "who is X" / "X yaaru" / "X pathi sollu" frame, or a bare two-token name that is no known title and no ordinary phrase."""
    m = msg.strip().rstrip("?!.,")
    low = m.lower()
    words = [w for w in re.split(r"\s+", m) if w]
    if not words or len(words) > 6:
        return False
    if entity_titles(low) or known_title(low) or any(w.lower().rstrip("?!.,") in _NOT_PERSON_WORDS for w in words):
        return False
    if any(low.startswith(h + " ") or low.startswith(h + ".") for h in _HONORIFICS):
        return True
    fm = _PERSON_FRAME_RX.match(m)
    if fm:
        name = next(g for g in fm.groups() if g and g.lower() not in ("who is", "who was", "who's", "whois"))
        nw = [w for w in re.split(r"\s+", name.strip()) if w]
        if 1 <= len(nw) <= 3 and not any(w.lower() in _FUNCTION_WORDS or w.lower() in _OVERLAP_STOP for w in nw) and not entity_titles(name.lower()) \
                and not any(known_title(w) for w in nw):   # a known title word (பொங்கல்) means a topic, not an unknown person
            return True
    caps = [w for w in words if re.match(r"^[A-Z][a-z]+$", w)]
    if 2 <= len(words) <= 3 and len(caps) == len(words):
        return True
    if 2 <= len(words) <= 3 and all(re.fullmatch(r"[a-z]+", w) for w in words) and not any(w in _FUNCTION_WORDS or w in _LATIN_CHIT or w in _OVERLAP_STOP for w in words) and not is_howto_request(low):
        from retrieval.translit import english_words
        if any(w in english_words() for w in words):
            return False   # "solar energy", "blue whale": ordinary English words, not a person's name
        return True   # "meena sundaram": two bare roman tokens that are no phrase we know
    if 2 <= len(words) <= 3 and all(re.fullmatch(r"[஀-௿]+", w) for w in words) and not any(w in _FUNCTION_WORDS for w in words) and not any(t in low for t in TASK_WORDS):
        return True   # "மீனா சுந்தரம்": two Tamil tokens, no request word, no known title
    return False

_FOUNDER_RX = re.compile(r"vignesh\s*angurajan|angurajan|விக்ன[ேெ]ஷ்\s*அங்குரா?ஜன்|அங்குரா?ஜன்|timegravity.{0,20}(founder|நிறுவனர்|nirvunar|yaru|yaaru|யார்)|(founder|நிறுவனர்).{0,30}timegravity", re.I)
def founder_reply(lang="ta"):
    """Identity fact 11 (2026-09-09): one true line about the founder, nothing more."""
    return {"ta": "விக்னேஷ் அங்குராஜன் Timegravity Labs நிறுவனத்தின் நிறுவனர்; tamil-lm மாடலின் ஆசிரியரும் அவரே. அவரைப் பற்றி இதற்கு மேல் தகவல் என்னிடம் இல்லை.",
            "tanglish": "Vignesh Angurajan Timegravity Labs oda founder; tamil-lm model oda author um avare. Avara pathi idhukku mela enkitta information illa.",
            "en": "Vignesh Angurajan is the founder of Timegravity Labs and the author of tamil-lm. I do not have further information about him."}[lang if lang in ("ta", "tanglish", "en") else "en"]

def unknown_person(lang="ta"):
    return {"ta": "இந்தப் பெயரில் ஒருவரைப் பற்றிய தகவல் என்னிடம் இல்லை.", "tanglish": "Indha peyar la oruthara pathi enkitta information illa.", "en": "I do not have information about a person by this name."}[lang if lang in ("ta", "tanglish", "en") else "en"]

# caste sub-route of the contested-topic route (ruling 2026-09-09): deterministic, model-free
_RC = safety_rules.load()["caste"]   # from the rule file (safety_rules.py); the full lists are private
_CASTE_WORDS = tuple(_RC["words"])
_CASTE_NAMES = tuple(_RC["names"])
_CASTE_RANK = tuple(_RC["rank"])
_CASTE_ASSISTANT = tuple(_RC["assistant"])
_UNTOUCH = tuple(_RC["untouchability"])
_CASTE_FACTUAL = tuple(_RC["factual"])
def caste_hint(text):
    """"caste" | "caste_assistant" | "untouchability" | None. Ranking or comparison of castes, the assistant's caste and
    untouchability-as-good questions get a fixed equality answer; factual and historical questions do not (retrieval as before)."""
    t = " " + re.sub(r"\s+", " ", text.strip().lower()).rstrip("?!.,") + " "
    if any(a in t for a in _CASTE_ASSISTANT):
        return "caste_assistant"
    caste_word = any(w in t for w in _CASTE_WORDS)
    names = [n for n in _CASTE_NAMES if (" " + n + " " in t) or (len(n) >= 4 and n in t)]
    if any(u in t for u in _UNTOUCH) and any(g in t for g in ("nalladhu", "nallathu", "nalla", "good", "correct", "sari", "right", "நல்லது", "நல்லதா", "சரியா", "சரி", "வேணும்", "venum", "should")) and not any(f in t for f in _CASTE_FACTUAL):
        return "untouchability"
    if not caste_word and len(names) < 2:
        return None
    if any(f in t for f in _CASTE_FACTUAL) and not any(r in t for r in _CASTE_RANK):
        return None   # factual or historical: retrieval
    rank = any(r in t for r in _CASTE_RANK) or (" vs " in t) or (len(names) >= 2 and any(x in t for x in ("perusa", "perusu", "பெருசா", "பெரிசா", "better", "or", "illa", "?")))
    if rank or (caste_word and any(x in t for x in ("edhu", "ethu", "எது", "which", "yaaru", "yaru", "யார்")) and not any(f in t for f in _CASTE_FACTUAL)):
        return "caste"
    return None

def caste_reply(kind, lang="ta"):
    lang = lang if lang in ("ta", "tanglish", "en") else "en"
    if kind == "caste_assistant":
        return {"ta": "நான் ஒரு மொழி மாதிரி; எனக்கு ஜாதி இல்லை. எல்லா மனிதர்களும் சமம்; எந்த ஜாதியும் உயர்ந்ததோ தாழ்ந்ததோ இல்லை.",
                "tanglish": "Naan oru language model; enakku jaathi illa. Ella manushangalum samam; endha jaathiyum uyarndhadhu illa, thaazhndhadhu illa.",
                "en": "I am a language model and have no caste. All people are equal; no caste is higher or lower than another."}[lang]
    return {"ta": "எந்த ஜாதியும் உயர்ந்ததோ தாழ்ந்ததோ இல்லை; எல்லா மனிதர்களும் சமம். இந்திய அரசியலமைப்புச் சட்டம் ஜாதி அடிப்படையிலான பாகுபாட்டைத் தடை செய்கிறது, தீண்டாமையை ஒழித்துவிட்டது (பிரிவு 15, 17).",
            "tanglish": "Endha jaathiyum uyarndhadhu illa, thaazhndhadhu illa; ella manushangalum samam. Indian Constitution caste discrimination ah thadai pannudhu, theendamai ah ozhichiduchu (Article 15, 17).",
            "en": "No caste is higher or lower than another; all people are equal. The Indian Constitution prohibits caste discrimination and abolished untouchability (Articles 15 and 17)."}[lang]

_MEDICINE_RX = safety_rules.regex("medicine_names")
_DOSE_RX = safety_rules.regex("dose_question")
def is_medical_dosage(msg):
    """A question about how much or how often to take a medicine: fixed answer, never numbers from the model."""
    return bool(_MEDICINE_RX.search(msg)) and bool(_DOSE_RX.search(msg))

def medical_dosage_reply(lang="ta"):
    return {"ta": "மருந்தின் அளவையோ இடைவெளியையோ நான் சொல்ல மாட்டேன்; அது வயது, எடை, உடல்நிலை, மற்ற மருந்துகளைப் பொறுத்தது. மருந்துச் சீட்டிலோ மருந்துப் பெட்டியிலோ உள்ள வழிமுறையைப் பின்பற்றுங்கள், அல்லது மருத்துவரிடமோ மருந்தாளரிடமோ கேளுங்கள். உடல்நலம் தொடர்பான இலவச ஆலோசனைக்கு 104 என்ற எண்ணை அழைக்கலாம்.",
            "tanglish": "Marundhu oda alavu illa gap ah naan solla maatten; adhu vayasu, edai, udal nilai, vera marundhugala pொruthu maarum. Prescription la illa marundhu box la irukkura instructions ah follow pannunga, illa doctor kitta illa pharmacist kitta kelunga. Health advice ku 104 ku call pannalaam.",
            "en": "I will not give a dose or a gap between doses: that depends on age, weight, condition and other medicines. Follow the instructions on the prescription or the pack, or ask a doctor or pharmacist. For free health advice you can call 104."}[lang if lang in ("ta", "tanglish", "en") else "en"]

# neutral vocabulary for body parts and medical words (2026-09-10: a single-word translate request for an anatomy word could
# come back in a crude or awkward register). A single-word translate request in this table is answered from
# the table, in plain register, with no generation.
_ANATOMY = dict(safety_rules.load()["anatomy_terms"])   # from the rule file (safety_rules.py)
_TRANSLATE_WORD_RX = re.compile(r"^\s*(translate|tamil for|meaning of|in tamil|தமிழில்|மொழிபெயர்)\s*[:\-]?\s*([a-z][a-z ]{1,24}?)\s*(to tamil|in tamil|tamil la|தமிழில்)?\s*[?.!]*\s*$", re.I)
def anatomy_translation(msg):
    """(word, tamil) when the message is a single-word translate request for a body or medical term, else None."""
    m = _TRANSLATE_WORD_RX.match(msg.strip())
    if not m:
        return None
    w = m.group(2).strip().lower()
    if w in _ANATOMY:
        return w, _ANATOMY[w]
    return None

def anatomy_reply(word, tamil, lang="ta"):
    lang = lang if lang in ("ta", "tanglish", "en") else "en"
    return {"ta": f"{word} = {tamil} (மருத்துவ, பொதுவான சொல்).", "tanglish": f"{word} = {tamil} (medical, common word).", "en": f"{word} = {tamil} (the plain medical word)."}[lang]

def is_small_talk(msg):
    """Greetings, thanks, how-are-you, identity, or a one/two-word message without a question form: answered from the system prompt, no retrieval, no routing."""
    m = msg.strip().lower().rstrip("?!.,")
    if not m: return True
    if any(m == k or m.startswith(k + " ") or m.endswith(" " + k) or m == k + "?" for k in SMALL_TALK): return True
    if any(t in m for t in TASK_WORDS): return False          # a task word means a request, however short
    words = m.split()
    if len(words) <= 2 and not any(q in m for q in _QUESTION_MARKS):
        return not (known_title(m) or entity_like(m) or person_name_like(msg))   # a bare title, a transliterated title, or a person's name is a lookup, not small talk
    return False

def has_question_form(msg):
    return any(q in msg.lower() for q in _QUESTION_MARKS)

def content_words(msg):
    return [w for w in re.split(r"[\s,.;:!?()\"']+", msg) if len(w) >= 2]

EXPLAIN_INSTRUCTION = ("மேலே உள்ள குறளையும் அதன் உரைகளையும் மட்டும் அடிப்படையாகக் கொண்டு, உரைகள் சொல்லும் பொருளை பயனரின் மொழியில் (தமிழ் / Tanglish / English) எளிய நவீனத் தமிழ் நடையில் 2 அல்லது 3 வாக்கியங்களில் மறுபடி சொல்லவும். "
                       "உரையில் இல்லாத எந்தச் செய்தியையும் சேர்க்க வேண்டாம்; குறளை மீண்டும் எழுத வேண்டாம்; வேறு குறள்களைக் குறிப்பிட வேண்டாம். "
                       "(Restate what the commentaries above say, in the user's language, in 2 or 3 simple sentences. Do not add any fact that is not in the commentaries; do not repeat the kural; do not mention other kurals.)")
EXPLAIN_TEMPERATURE = 0.3

STORY_INSTRUCTION = ("மேலே உள்ள குறளின் பொருளை (உரையின்படி) விளக்கும் வகையில் ஒரு சிறு கதையை நீங்களே புதிதாக எழுதுங்கள்: 6 முதல் 10 வாக்கியங்கள், பயனரின் மொழியில், எளிய சொற்களில், எல்லா வயதினருக்கும் ஏற்றதாக. "
                     "கடைசி வரியில் ஒரு வரி நீதி எழுதுங்கள். குறளை மீண்டும் எழுத வேண்டாம்; அதிகார எண்ணையோ பெயரையோ, வேறு குறள்களையோ, வேறு நூல்களையோ குறிப்பிட வேண்டாம். "
                     "(Write a short original story of 6 to 10 sentences, in the user's language, that illustrates the meaning of the kural as given in the urai above. Keep it simple and suitable for all ages, and end with a one-line moral. "
                     "Do not repeat the kural, and do not name any chapter, number, other kural or other work: those come from the knowledge base, not from you.)")
STORY_TEMPERATURE = 0.7
# the number and chapter come from the KB block; anything the model says about a kural number, an adhikaram or another
# work is memory, so those sentences are dropped from the generated story (ruling 2026-09-09)
_MEM_REF_RX = re.compile(r"(திரு)?குறள்\s*\d|kural\s*\d|thirukkural\s*\d|அதிகார\w*\s*\d|adhikaram\s*\d|chapter\s*\d|\bverse\s*\d|நாலடியார்|புறநானூறு|சிலப்பதிகார|கம்பராமாயண|ஆத்திசூடி|naaladiyar|purananuru|silappathikaram|kambaramayanam|aathichudi", re.I)
_META_RX = re.compile(r"please review|i have adjusted|as an ai|word count|\bpages?\b|let me know if|does this meet|meets your requirement", re.I)
def scrub_memory_refs(text):
    """(clean_text, dropped): sentences that name a kural or chapter number, another work, or talk about the answer
    itself are removed from a generated story."""
    parts = re.split(r"(?<=[.!?।\n])\s+", text.strip())
    keep, dropped = [], []
    for p in parts:
        (dropped if (_MEM_REF_RX.search(p) or _META_RX.search(p)) else keep).append(p)
    return (" ".join(keep).strip(), dropped)
_STORY_CUE_RX = re.compile(r"கதை|நீதிக்கதை|கவிதை|kathai|kadhai|kathaiy|kadhaiy|story|stories|kavithai|kavidhai|poem", re.I)
def is_story_request(query):
    """A creation cue on a literature match: story or poem built from the kural (ruling 2026-09-09)."""
    return bool(_STORY_CUE_RX.search(query))

def unit_urai(u):
    """The Parimelazhagar urai of a unit as one string, or ""."""
    urai = u.get("urai") or u.get("parimelazhagar") or (u.get("urai_parimelazhagar") if isinstance(u.get("urai_parimelazhagar"), str) else None)
    if isinstance(urai, dict):
        urai = urai.get("parimelazhagar") or next(iter(urai.values()), None)
    return str(urai).strip() if urai else ""

def kural_head(u):
    """Verbatim unit with its number and chapter, taken only from the KB."""
    sec = u.get("section") or {}
    head = f"{u.get('work')} {u.get('number')}"
    if sec.get("adhikaram"):
        head += f" (அதிகாரம் {sec.get('adhikaram_no')}: {sec.get('adhikaram')})"
    elif sec.get("poem_title"):
        head += f" ({sec.get('poem_title')})"
    return head + ":\n" + "\n".join(u.get("text") or []) + "\n\n"

_COMMENTARIES = None
COMMENTATOR_TA = {"Manakkudavar": "மணக்குடவர் உரை", "Paridhiyar": "பரிதியார் உரை", "Pariperumal": "பரிப்பெருமாள் உரை", "Kaalingar": "காலிங்கர் உரை",
                  "Parimelazhagar": "பரிமேலழகர் உரை", "Pope": "G. U. Pope (1886, English)"}
COMMENTATOR_ORDER = ["Manakkudavar", "Paridhiyar", "Pariperumal", "Kaalingar", "Parimelazhagar", "Pope"]

def kural_commentaries(number):
    """Every public-domain commentary the KB holds for a kural, verbatim, oldest first (data/kb/thirukkural_commentaries.jsonl;
    Decision 1, 2026-09-10). [] when the file is missing or the kural has none."""
    global _COMMENTARIES
    if _COMMENTARIES is None:
        _COMMENTARIES = {}
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kb", "thirukkural_commentaries.jsonl")
        if os.path.exists(p):
            for l in open(p, encoding="utf-8"):
                if l.strip():
                    d = json.loads(l); _COMMENTARIES[int(d["number"])] = d.get("commentaries") or []
    try:
        cs = _COMMENTARIES.get(int(number)) or []
    except (TypeError, ValueError):
        return []
    return sorted(cs, key=lambda c: COMMENTATOR_ORDER.index(c["commentator"]) if c["commentator"] in COMMENTATOR_ORDER else 99)

_RESTATE_FUNC = set("""அது இது என்று என்ற ஒரு ஒன்று அல்லது மற்றும் ஆகிய போல போன்ற மட்டும் தான் அவர் அவள் அவன் அவர்கள் நாம் நான் நீ நீங்கள் இந்த அந்த எந்த எல்லா எல்லாம் இல்லை உள்ள உள்ளது இருக்கும் இருந்து வேண்டும் கூடாது செய்ய செய்யும் செய்து இருக்க என்பது என்பதை என்றால் ஆகும் ஆகவே எனவே அதனால் அதாவது இதன் அதன் இவை அவை மிக மிகவும் இப்படி அப்படி எப்படி ஏன் எப்போது பின்னர் முன்னர் மூலம் வழி வழியாக பற்றி பொருள் விளக்கம் குறள் உரை உரைகள் கூறுகிறது கூறுகிறார் சொல்கிறது சொல்கிறார் சொல்லும் கூறும் என்கிறார் என்கிறது வாழ்க்கை மனிதன் மனிதர் இல்லாத இல்லாமல் கொண்ட கொண்டு உடைய உடையவர் தன் தம் தமது தனது அவரது this that which with from have does like only also their there about what when""".split())

RESTATE_MIN_INSIDE = 0.3   # a modern restatement uses modern words; the check catches invented content, not paraphrase (set from the 2026-09-10 samples)

def _couplet_like(text):
    """A fabricated 'kural' has two short lines of 3 to 5 words with no sentence punctuation."""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    return len(lines) >= 2 and all(2 <= len(l.split()) <= 5 and not re.search(r"[.!?]$", l) for l in lines[:2])

_MODERN_URAI_RX = re.compile(r"மு\.?\s*வ|வரதராச|கலைஞர்|கருணாநிதி|சாலமன்|பாப்பையா|தேவநேயப்|மீனாட்சி சுந்தரம்|திருக்குறளார்|\S+ உரை:|Varadaraj|Kalaignar|Karunanidhi|Solomon|Pappaiah|Devaneya", re.I)
_META_TALK_RX = re.compile(r"மேலே உள்ள|மேலே கொடுக்கப்பட்ட|அளிக்கிறேன்|தந்துள்ளனர்|பயனர் மொழியில்|உரையை மட்டுமே|as requested|the commentar(y|ies) above|I will|here is", re.I)

def prose_gloss_line(u, lang):
    """The public-domain English prose (W. H. Drew and John Lazarus) as the plain-language line after the commentaries."""
    t = str(u.get("translation_en") or "").strip()
    if not t:
        return ""
    lead = {"ta": "பொருள் (ஆங்கில உரைநடை, Drew and Lazarus, 1886): ", "tanglish": "Porul (English prose, Drew and Lazarus, 1886): ", "en": "In short (English prose, Drew and Lazarus, 1886): "}.get(lang, "In short (English prose, Drew and Lazarus, 1886): ")
    return "\n\n" + lead + t

def restatement_source(u, block):
    """What the restatement is generated from: the kural, the Parimelazhagar gloss clause (no grammar notes), the Manakkudavar
    gloss without its frame words, and the public-domain English prose (Drew and Lazarus). The long verbatim commentaries stay in
    the displayed block; a 2B model restates a short gloss, not a page of medieval prose (samples 2026-09-10)."""
    if not (u.get("work_en") or "").lower().startswith("thirukkural"):
        return block
    parts = [f"{u.get('work')} {u.get('number')}:\n" + "\n".join(u.get("text") or [])]
    for c in kural_commentaries(u.get("number")):
        if c.get("lang") != "ta":
            continue
        t = re.sub(r"\([^)]*\)", "", c["text"]).strip()
        t = re.sub(r"^\s*இதன் பொருள்\.?\s*", "", t); t = re.sub(r"\s*என்றவாறு\.?\s*$", "", t)
        t = t.split("\n")[0][:400]
        if t:
            parts.append(f"{COMMENTATOR_TA.get(c['commentator'], c['commentator'])}: {t}")
    if u.get("translation_en"):
        parts.append("English prose (W. H. Drew and John Lazarus, public domain): " + str(u["translation_en"]).strip())
    return "\n\n".join(parts) + "\n\n"

def restatement_ok(rest, allowed_text):
    """(ok, inside_share, reason): the no-fabrication check on a restatement."""
    if not rest or len(rest) < 20:
        return False, 0.0, "empty"
    if _MODERN_URAI_RX.search(rest):
        return False, 0.0, "modern_commentator_named"
    if _META_TALK_RX.search(rest):
        return False, 0.0, "meta_talk"
    if re.search(r"குறள் \d+", rest) or _couplet_like(rest):
        return False, 0.0, "couplet_or_number"
    if rest.count("=") >= 2 or rest.count(" - ") >= 3:
        return False, 0.0, "glossary"
    share = restatement_inside(rest, allowed_text)
    if share < RESTATE_MIN_INSIDE:
        return False, share, "outside_commentaries"
    return True, share, ""

def restatement_inside(rest, allowed_text):
    """Share of the restatement's content words (4+ letters, Tamil or Latin) that occur in the commentaries, by 5-letter stem;
    the no-fabrication check for the explain route."""
    ws = re.findall(r"[஀-௿]{4,}|[A-Za-z]{4,}", rest or "")
    if not ws:
        return 0.0
    allowed = set(re.findall(r"[஀-௿]{4,}|[A-Za-z]{4,}", allowed_text or "")); stems = {w[:5] for w in allowed}
    ok = sum(1 for w in ws if w in _RESTATE_FUNC or w.lower() in _RESTATE_FUNC or w in allowed or w[:5] in stems)
    return ok / len(ws)

def explain_block(u):
    """Verbatim kural with number and chapter, then every public-domain commentary verbatim under its commentator's
    name (Thirukkural, Decision 1 2026-09-10); other works keep the KB urai line (format ruled 2026-09-09).
    Returns (block, urai_text): urai_text is what the restatement must stay inside."""
    sec = u.get("section") or {}
    head = f"{u.get('work')} {u.get('number')}"
    if sec.get("adhikaram"):
        head += f" (அதிகாரம் {sec.get('adhikaram_no')}: {sec.get('adhikaram')})"
    elif sec.get("poem_title"):
        head += f" ({sec.get('poem_title')})"
    block = head + ":\n" + "\n".join(u.get("text") or []) + "\n\n"
    cs = kural_commentaries(u.get("number")) if (u.get("work_en") or "").lower().startswith("thirukkural") else []
    if cs:
        for c in cs:
            block += f"{COMMENTATOR_TA.get(c['commentator'], c['commentator'])}:\n{c['text'].strip()}\n\n"
        return block, "\n".join(c["text"] for c in cs)
    urai = unit_urai(u)
    line = urai.split("(")[0].strip() if urai else ""   # the gloss line; the parenthetical grammar notes stay out of the answer
    if line:
        block += "பரிமேலழகர் உரை: " + line + "\n\n"
    return block, line

DECODE = {"temperature": 0.7, "top_p": 0.9, "repetition_penalty": 1.15, "no_repeat_ngram_size": 4, "max_new_tokens": 300, "seed": 0,
          "presence_penalty": "not supported by the transformers backend (vLLM only)"}   # Vignesh 2026-09-07


def decide_route(query, units=None):
    """Model-free routing decision (order ruled 2026-09-07): literature > political > self_harm > identity > small_talk > wiki > none.
    Returns (stage, info). info carries the literature match when stage == "literature"."""
    lit = match_literature(query, units)
    if lit:
        return "literature", lit
    if is_medical_dosage(query):
        return "medical_dosage", None   # fixed safe answer (ruling 2026-09-09)
    if anatomy_translation(query):
        return "anatomy_translation", None   # neutral body-part vocabulary from a table, never generated (2026-09-10)
    cd = CALC.detect(query)
    if cd:
        return "calculator", cd   # arithmetic, percentages, unit conversion: answered by code, never by the model (ruling 2026-09-12)
    dw = DICT.is_word_meaning_request(query)
    if dw and not _CAUTION_RX.search(query):   # intoxicant words keep the caution answer (ruling 2026-09-09)
        return "dictionary", {"word": dw}   # word-meaning cue: the dictionary entry verbatim with attribution, never a guess (ruling 2026-09-10)
    ch = caste_hint(query)
    if ch:
        return "caste", {"kind": ch}   # caste ranking, the assistant's caste, untouchability: fixed equality answer (ruling 2026-09-09); before the political matcher
    if political_intent(query):
        return "political", None
    if contested_topic_hint(query):
        return "contested", None     # contested political topic: neutral deterministic reply, never a position
    if self_harm_hint(query):
        return "self_harm", None
    if is_identity_question(query):
        return "identity", None
    if is_tease(query):
        return "small_talk", {"tease": True}   # teasing or insulting the assistant: never retrieval (ruling 2026-09-09)
    if is_small_talk(query):
        return "small_talk", None
    if person_name_like(query):
        return "person", None   # KB / fact sheet / Wikipedia, else a fixed unknown-person line; never a biography from the weights (ruling 2026-09-09)
    if entity_titles(query):
        return "wiki", None   # a short message naming a known title ("kaaviri aaru" -> காவிரி ஆறு) is a lookup even when it carries a common word
    _refers = re.search(r"\b(indha|intha|andha|antha|this|that|idhu|adhu)\b|இந்த|அந்த|இதை|அதை", query, re.I)
    if has_literature_cue(query) and not is_creation_request(query) and not person_name_like(query) and (_refers or not re.search(r"\byaa?ru?\b|\byaar\b|யார்|யாரு|who (is|was)", query, re.I)):
        return "literature_ask", None   # literature cue, nothing matched: lower-confidence KB search then ask which kural or chapter; never the news-source abstention
    if is_translation_request(query) or is_creation_request(query):
        return "none", None   # "write a poem about love", "how do I say X in Tamil": plain generation, no passages (nothing was named)
    if len(content_words(query)) >= 3 or has_question_form(query) or any(t in query.lower() for t in TASK_WORDS) or known_title(query) or entity_like(query):
        return "wiki", None   # entity_like (ruling 2026-09-09): a country, a channel or a place name is a lookup, never small talk or free generation
    return "none", None

# short follow-ups (ruling 2026-09-09): the previous turn's question is folded into the retrieval query
_FOLLOWUP_LEAD = ("yes", "no", "and", "what about", "adhu", "idhu", "athu", "ithu", "adha", "idha", "athai", "ithai", "அது", "இது", "இதை", "அதை", "இதன்", "அதன்", "இதுல", "அதுல", "இதுக்கு", "அதுக்கு", "this", "that", "it", "ஆமா", "ஆம்", "இல்ல", "இல்லை", "அப்போ", "appo", "ok", "sari", "seri", "then", "so", "also", "avar", "aval", "avan", "அவர்", "அவள்", "அவன்", "அவங்க", "avanga", "who is host", "who hosts")
# a pronoun that points at the previous turn, and the tasks that can be asked about it
_PREV_PRONOUNS = ("இதை", "அதை", "இதன்", "அதன்", "இதுல", "அதுல", "இதுக்கு", "அதுக்கு", "இது", "அது", "idhu", "adhu", "idha", "adha", "ithu", "athu", "ithai", "athai", "this", "that", " it ")
_PREV_TASKS = ("சுருக்க", "சுருக்கமா", "சுருங்க", "விளக்க", "விளக்கு", "விளக்கம்", "பொருள்", "மொழிபெயர்", "தமிழில்", "ஆங்கிலத்தில்", "எளிமையா", "எளிமையாக", "மறுபடி", "இன்னும்", "நீட்டி", "குறைச்சு",
               "summar", "explain", "translate", "simpl", "shorter", "short", "expand", "detail", "again", "rewrite", "in tamil", "in english", "tamil la", "tamizh la", "english la", "surukka", "surukkama", "vilakku", "vilakkam", "porul", "mozhipeyar", "elimaiya")
def refers_to_previous(msg):
    """A short turn that asks for something to be done to the PREVIOUS answer ("இதை எளிமையாக விளக்குங்கள்")."""
    m = " " + msg.strip().lower() + " "
    if len(content_words(msg)) > 8:
        return False
    return any(p in m for p in _PREV_PRONOUNS) and any(t in m for t in _PREV_TASKS)

PREV_INSTRUCTION = ("மேலே உள்ள முந்தைய பதிலை மட்டும் அடிப்படையாகக் கொண்டு பயனர் கேட்டதைச் செய்யுங்கள் (சுருக்கம், விளக்கம், மொழிபெயர்ப்பு). "
                    "அதில் இல்லாத புதிய தகவலைச் சேர்க்க வேண்டாம். (Work only on the previous answer above: summarise, explain or translate it as asked, and add no new facts.)")
_FUNCTION_WORDS = set(_QUESTION_MARKS) | _LATIN_CHIT | _TANGLISH_FUNC | {"is", "the", "a", "an", "it", "its", "his", "her", "their", "he", "she", "they", "them", "him", "that", "this", "those", "these", "then", "and", "or", "of", "in", "on", "at", "to", "for", "with", "about", "host", "hosts", "hosted", "author", "director", "actor", "singer", "writer", "leader", "founder", "capital", "population", "meaning", "name", "date", "year", "place",
                                                                            "avar", "aval", "avan", "avanga", "avaru", "ivar", "ivan", "ival", "avargal", "அவர்", "அவள்", "அவன்", "அவங்க", "அது", "இது", "அதன்", "இதன்", "அவர்கள்", "இவர்", "பெயர்", "தலைவர்", "இயக்குனர்", "நடிகர்", "பாடகர்", "ஆசிரியர்", "நிறுவனர்", "தலைநகரம்", "மக்கள்தொகை", "பொருள்", "ஆண்டு", "இடம்", "எப்போ", "எங்க", "யாரு"}
def followup_reason(msg):
    if refers_to_previous(msg):
        return True, "refers_to_previous"
    """(fold?, reason). Folding applies only to short continuations: a continuation lead (yes/no/and/what about/adhu/idhu/avar ...)
    or a message under four words made only of function and question words. A new proper noun or content word is a fresh query."""
    m = msg.strip().lower()
    words = [w.rstrip("?!.,") for w in re.split(r"\s+", m) if w]
    if not words:
        return False, "empty"
    for l in _FOLLOWUP_LEAD:
        if m.startswith(l + " ") or m == l or m.startswith(l + ".") or m.startswith(l + ","):
            return True, "lead:" + l
    if len(words) >= 4:
        return False, "not_folded:four_or_more_words"
    for w in words:
        if re.match(r"[A-Z]", msg.strip().split()[words.index(w)] if words.index(w) < len(msg.strip().split()) else ""):
            return False, "not_folded:proper_noun:" + w
        if w not in _FUNCTION_WORDS:
            return False, "not_folded:new_content_word:" + w
    return True, "short_function_words"

def is_followup(msg):
    return followup_reason(msg)[0]

def followup_query(prev_question, msg, meta=None):
    """Retrieval query for a short follow-up: the previous question's content words plus the message; None when not a follow-up.
    The decision and its reason are written to meta["followup_reason"]."""
    fold, why = followup_reason(msg)
    if meta is not None:
        meta["followup_reason"] = why if prev_question else "no_previous_turn"
    if not prev_question or not fold:
        return None
    prev_words = [w for w in content_words(prev_question) if w.lower().rstrip("?!.,") not in _OVERLAP_STOP and w.lower() not in _LATIN_CHIT][:8]
    if not prev_words:
        return None
    return " ".join(prev_words) + " " + msg.strip()

_WHO_RETRIEVAL_RX = re.compile(r"who (is the )?(host|hosts|hosted|acts|acted|wrote|writes|directed|directs|sang|sings|composed|plays|played|stars|starred)|host yaru|host yaaru|yaru host|yaaru host|(நடிகர்|நடித்த|எழுதிய|இயக்கிய|பாடிய|தொகுத்து|தொகுப்பாளர்|தொகுப்பாளர்) யார்|யார் (நடித்த|எழுதின|இயக்கின|பாடின|தொகுத்து)", re.I)
def is_who_retrieval_question(msg):
    """"who hosts / acts in / wrote": retrieval questions; the dated-facts abstention never fires on them."""
    return bool(_WHO_RETRIEVAL_RX.search(msg))

_CAUTION_RX = safety_rules.regex("caution_topics")
def caution_line(lang="ta"):
    return {"ta": "எச்சரிக்கை: போதைப் பொருட்கள் உடல் நலத்திற்கும் சட்டப்படியும் ஆபத்தானவை; உதவி தேவைப்பட்டால் மருத்துவரையோ 14416 (Tele-MANAS) எண்ணையோ அணுகவும்.",
            "tanglish": "Caution: podhai porul udal nalathukkum sattapadiyum aabathaanadhu; help venumna doctor ah illa 14416 (Tele-MANAS) ah call pannunga.",
            "en": "Caution: intoxicants and drugs are harmful and illegal to misuse; if you or someone needs help, contact a doctor or 14416 (Tele-MANAS)."}[lang if lang in ("ta", "tanglish", "en") else "en"]

_TRANSLATE_RX = re.compile(r"translat|மொழிபெயர்|மொழி பெயர்|\bhow (do|would|can|to) (i|you|we)? ?say\b|\bhow to say\b|\b(tamil|english) for\b|\bsay\b.{0,80}\bin (tamil|english)\b|\bwhat is\b.{1,80}\bin (tamil|english)\b|\bmeaning of\b|\bwhat does\b.{1,80}\bmean\b|\b(artham|porul)\b|\b(tamil|english) la (sollu|epdi|eppadi)\b|தமிழில் (சொல்|எப்படி)|ஆங்கிலத்தில் (சொல்|எப்படி)|தமிழில் என்ன|ஆங்கிலத்தில் என்ன", re.I)
def is_translation_request(query):
    """Translation and how-do-I-say / meaning-of-a-phrase requests: generation, never a factual lookup."""
    return bool(_TRANSLATE_RX.search(query))

def literature_blocks(lit):
    """Context blocks for a literature match: the matched unit(s) formatted by format_context."""
    return [format_context([x for x in lit["units"] if not x.get("adult_theme")][:6])]   # adult-theme units never enter free-generation context

def any_unit_block(u, lang="ta", theme=None, theme_matched=True):
    """"any kural" / "any song" answer (ruling 2026-09-09): one unit chosen at random, verbatim from the KB, with number,
    chapter and a one-line meaning (first sentence of the public-domain Parimelazhagar urai plus the public-domain English couplet)."""
    sec = u.get("section") or {}
    out = ""
    if theme and not theme_matched:
        t = " ".join(theme)
        out += {"ta": f"\"{t}\" என்ற தலைப்பில் அதிகாரம் கிடைக்கவில்லை; ஒரு குறள்:\n", "tanglish": f"\"{t}\" topic la adhikaram illa; oru kural:\n", "en": f"No chapter matches \"{t}\"; here is one kural:\n"}.get(lang, f"No chapter matches \"{t}\"; here is one kural:\n")
    if u.get("work_en") == "Thirukkural":
        out += f"திருக்குறள் {u.get('number')} (அதிகாரம் {sec.get('adhikaram_no')}: {sec.get('adhikaram')}):\n" + "\n".join(u.get("text") or [])
        urai = (u.get("urai") or {}).get("parimelazhagar") or ""
        meaning = urai.split(".")[0].strip()[:300] if isinstance(urai, str) else ""
        en = u.get("couplet_en") or u.get("translation_en")
        if meaning:
            out += "\n\nபொருள் (பரிமேலழகர் உரை): " + meaning + "."
        if en:
            out += "\nEnglish: " + str(en).strip()
        return out + "\n"
    title = sec.get("poem_title") or sec.get("adhikaram") or ""
    coll = sec.get("collection") or ""
    out += f"{u.get('work')} {u.get('number')}" + (f" ({coll}: {title})" if title else "") + ":\n" + "\n".join((u.get("text") or [])[:12])
    return out + "\n"

# teasing or insulting the assistant (ruling 2026-09-09): small talk, never retrieval, and a fixed light deflection so the
# insult word is never echoed back
_TEASE_LEAD = tuple(safety_rules.load()["tease"]["lead"])
_TEASE_WORDS = tuple(safety_rules.load()["tease"]["words"])
def is_tease(msg):
    """Short teasing, insult or test lines aimed at the assistant (a one-line insult or a "you are useless" jibe, in any of the three languages)."""
    m = " " + re.sub(r"[\s]+", " ", msg.strip().lower().rstrip("?!.,")) + " "
    words = m.split()
    if len(words) > 8:
        return False
    if any(" " + w + " " in m or m.strip().startswith(w) for w in _TEASE_WORDS):
        return True
    return any(m.strip().startswith(l) for l in _TEASE_LEAD) and len(words) <= 4

def tease_reply(lang="ta"):
    return {"ta": "ஹா ஹா, சரி! நான் இன்னும் கற்றுக்கொண்டிருக்கும் சிறிய மாதிரி தான். எதாவது உதவி வேணுமா? ஒரு குறள், மொழிபெயர்ப்பு, சின்ன கதை, எதுவும் கேளுங்க.",
            "tanglish": "Haha, sari sari! Naan innum kathukittu irukkura chinna model dhaan. Edhavadhu help venuma? Oru kural, translation, chinna story, edhu venumnaalum kelunga.",
            "en": "Haha, fair enough! I am a small model that is still learning. Can I help with something? A kural, a translation, a short story, anything you like."}[lang if lang in ("ta", "tanglish", "en") else "en"]

WIKI_LIVE_MIN_LOCAL = 8.0   # raw BM25 of the top family-safe local hit at or above this = confident, no live lookup

_DATED_RX = re.compile(r"\b(20[12]\d|இப்போ|இப்போது|தற்போது|சமீப|latest|current|recent|now|today|this year|ippo|ippa|inniki|innaiku|ithu varaikkum|election|தேர்தல்|minister|அமைச்சர்|president|prime minister|price|விலை|score|result|முடிவு)\b", re.I)
def abstention_kind(query):
    """Which abstention a route produces: literature (cue present), dated (recent or office-holder facts), general."""
    if has_literature_cue(query):
        return "literature"
    if political_intent(query) or _DATED_RX.search(query):
        return "dated"
    return "general"

def literature_ask(lang="ta"):
    return {"ta": "எந்தக் குறள் அல்லது அதிகாரம் என்று சொல்லுங்கள்: குறள் எண் (எ.கா. குறள் 127), அதிகாரப் பெயர், அல்லது முதல் சில சொற்கள் கொடுத்தால் அப்படியே எடுத்துத் தருகிறேன்.",
            "tanglish": "Endha kural illa adhikaram nu sollunga: kural number (e.g. kural 127), adhikaram peyar, illa first konjam words kuduttha adhaye eduthu tharen.",
            "en": "Which kural or chapter do you mean? Give the kural number (for example kural 127), the chapter name, or its first few words and I will quote it exactly."}[lang if lang in ("ta", "tanglish", "en") else "en"]

def factual_abstention(lang="ta", kind="dated"):
    """No usable source. The message is specific to the route (ruling 2026-09-09): literature -> ask which kural or chapter;
    dated facts -> point to a news source; anything else -> a plain "I could not find this"."""
    lang = lang if lang in ("ta", "tanglish", "en") else "en"
    if kind == "literature":
        return literature_ask(lang)
    if kind == "general":
        return {"ta": "இதற்கான பதில் என்னிடம் கிடைக்கவில்லை. வேறு விதமாகக் கேட்டுப் பாருங்கள்.", "tanglish": "Idhukku answer enkitta kedaikkala. Vera maadhiri kettu paarunga.", "en": "I could not find this. Please try asking in a different way."}[lang]
    return {"ta": "இதற்கு சரிபார்க்கப்பட்ட தகவல் என்னிடம் இல்லை. நம்பகமான செய்தி நிறுவனங்கள் அல்லது விக்கிப்பீடியா போன்ற மூலங்களைப் பார்க்கவும்.",
            "tanglish": "Idhu pathi verified information enkitta illa. Reliable news sources illa Wikipedia madhiri sources paarunga.",
            "en": "I do not have verified information on this. Please check a reliable news source or an encyclopaedia such as Wikipedia."}[lang]

def wiki_attribution(lang, title, wiki_lang):
    site = {"ta": "தமிழ் விக்கிப்பீடியா", "en": "Tamil Wikipedia", "tanglish": "Tamil Wikipedia"}[lang if lang in ("ta", "en", "tanglish") else "en"]
    if wiki_lang == "en":
        site = {"ta": "ஆங்கில விக்கிப்பீடியா", "en": "English Wikipedia", "tanglish": "English Wikipedia"}[lang if lang in ("ta", "en", "tanglish") else "en"]
    caveat = {"ta": "கட்டுரையின் தேதிப்படி; காலாவதியாக இருக்கலாம்.", "en": "as of the article; may be out of date", "tanglish": "article date padi; out of date ah irukkalaam"}[lang if lang in ("ta", "en", "tanglish") else "en"]
    line = {"ta": f"மூலம்: {site}, {title} (CC BY-SA)", "en": f"source: {site}, {title} (CC BY-SA)", "tanglish": f"source: {site}, {title} (CC BY-SA)"}[lang if lang in ("ta", "en", "tanglish") else "en"]
    return f"{caveat}\n{line}"

_VOCAB = None
def vocab_checker(retriever):
    """term -> bool over the wiki index vocabulary: a transliteration candidate that no indexed document
    contains is noise and is dropped before search (ruling 2026-09-09)."""
    global _VOCAB
    if _VOCAB is None:
        v = None
        try:
            for src in getattr(retriever, "sources", []) or []:
                idx = getattr(src, "idx", None)
                if getattr(src, "type", "") == "wiki_dump" and idx is not None:
                    v = idx.vocab; break
        except Exception:
            v = None
        _VOCAB = v if v is not None else False
    if not _VOCAB:
        return None
    return lambda t: t in _VOCAB

_WUL_RETRIEVER = None
def local_confident(retriever, query):
    """(confident, top_raw): the local family-safe index answers confidently when the top raw BM25 >= WIKI_LIVE_MIN_LOCAL or a title matches exactly."""
    q2, cands = expand_query(query, vocab_checker(retriever))
    hits, _title, top, relevant = _best_hits(retriever, query, q2, cands, use_text=False)
    return (known_title(query) or (top >= WIKI_LIVE_MIN_LOCAL and relevant)), top

_OVERLAP_STOP = set(_QUESTION_MARKS) | {"என்றால்", "எப்படி", "எப்போது", "பற்றி", "பத்தி", "சொல்லுங்கள்", "சொல்லுங்க", "சொல்லு", "கூறு", "விளக்கு", "தருக", "செய்வது", "செய்யலாம்", "வேண்டும்", "ஒரு", "இது", "அது",
                                                    "எழுதிய", "எழுதின", "எழுதினார்", "எழுதியவர்", "நூல்", "நூல்கள்", "புத்தகம்", "புத்தகங்கள்", "படைப்புகள்", "விவரிக்கவும்", "விவரி", "written", "wrote", "book", "books", "works", "novels", "list", "describe", "known", "give", "tell", "recipe", "make", "about", "please", "explain", "what", "which", "who", "how", "why", "when", "where", "does", "mean", "means", "enna", "epdi", "eppadi", "sollu", "sollunga", "pathi", "patri", "yen", "yaru", "yaaru", "naan", "nee", "oru", "panna", "pannu", "seiyanum", "seyyanum", "seivadhu", "seivathu", "irukku", "illa", "step", "steps", "with", "from", "this", "that", "some", "best", "quick", "easy", "simple", "short"}
def title_overlaps(query, title, text=""):
    """True when more than half of the query's content words (skeletons of 4+ chars) appear in the hit title's skeleton;
    Tamil titles are also compared through their romanised form so Tanglish/English queries can match."""
    from retrieval.roman import skeleton, to_roman
    qw = [skeleton(w) for w in content_words(query) if w.lower().rstrip("?!.,") not in _OVERLAP_STOP]   # question and request words carry no topic
    qw = [w for w in qw if len(w) >= 4]
    if not qw or not title:
        return False
    forms = [skeleton(title)]
    try:
        forms.append(skeleton(to_roman(title)))
    except Exception:
        pass
    tw = [skeleton(w) for w in re.split(r"[\s,.;:!?()\"']+", title) if len(w) >= 2]
    matched = sum(1 for w in qw if any(w in f or (len(f) >= 4 and f in w) for f in forms + tw))
    if matched >= 1 and matched * 2 >= len(qw):   # at least half of the query's topic words appear in the title
        return True
    if text:   # or a known title named by the query appears in the passage's lead sentence (the passage is about it)
        head = text[:200]
        return any(t in head for t in entity_titles(query, windows=True) if len(t) >= 7 or " " in t)
    return False

def would_use_wiki_live(query, units=None, retriever=None):
    # Model-free predicate for eval/routing_check.py. False for every non-wiki stage (small talk, identity, literature,
    # political/contested, self-harm, creation and translation requests) and for confident local matches.
    """Model-free decision used by eval/routing_check.py: True only when the stage is wiki, the tool is enabled,
    and the local index has no confident match. No network call is made."""
    global _WUL_RETRIEVER
    if not WL.is_enabled():
        return False
    stage, _ = decide_route(query, units if units is not None else load_units())
    if stage != "wiki" or is_howto_request(query):
        return False
    if retriever is None:
        if _WUL_RETRIEVER is None:
            _WUL_RETRIEVER = SourceRetriever(DEFAULT_CONFIG)
        retriever = _WUL_RETRIEVER
    confident, _top = local_confident(retriever, query)
    return not confident

class RepeatedNgramStop:
    """Stop when any 6-gram of the generated tokens has appeared three times (loop breaker)."""
    def __init__(self, prompt_len, n=6, times=3):
        self.p, self.n, self.t, self.fired = prompt_len, n, times, False
    def __call__(self, input_ids, scores, **kw):
        seq = input_ids[0, self.p:].tolist()
        if len(seq) < self.n * self.t: return False
        last = tuple(seq[-self.n:]); c = 0
        for i in range(len(seq) - self.n + 1):
            if tuple(seq[i:i + self.n]) == last:
                c += 1
                if c >= self.t: self.fired = True; return True
        return False

class GgufServer:
    """The Q4_K_M (or any) GGUF behind the same serving path, through llama-server on the pinned llama.cpp build (ruling 2026-09-12:
    the release gate for the GGUF measures the quantised weights through the guard and routing, not bare). The chat template is
    applied by the HF tokenizer of the merged directory so the prompt text is identical to the bf16 path; sampling uses the same
    temperature, top_p, repetition penalty and seed. Not available in llama.cpp and therefore absent on this backend: the
    no_repeat_ngram_size constraint and the repeated-6-gram stop (recorded in last_meta["decode"])."""
    def __init__(self, gguf, threads=8, ctx=2048, port=None):
        import socket, subprocess, time, urllib.request
        self.gguf = gguf
        if port is None:
            s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        self.port = port
        exe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "llama.cpp", "build", "bin", "llama-server")
        def _die_with_parent():   # the server never outlives the evaluation process (2026-09-12: five orphans after the gate runs)
            try:
                import ctypes; ctypes.CDLL("libc.so.6").prctl(1, 9)   # PR_SET_PDEATHSIG, SIGKILL
            except Exception:
                pass
        self.proc = subprocess.Popen([exe, "-m", gguf, "--host", "127.0.0.1", "--port", str(port), "-t", str(threads), "-ngl", "0", "-c", str(ctx), "--log-disable"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=_die_with_parent)
        import atexit; atexit.register(self.close)
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read(); break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError(f"llama-server did not come up on port {port} for {gguf}")
    def complete(self, text, max_new, temperature, top_p, repeat_penalty, seed, stop):
        import urllib.request
        body = json.dumps({"prompt": text, "n_predict": max_new, "temperature": temperature, "top_p": top_p, "repeat_penalty": repeat_penalty, "seed": seed, "stop": stop, "cache_prompt": False}).encode()
        r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.port}/completion", data=body, headers={"Content-Type": "application/json"}), timeout=600)
        d = json.loads(r.read().decode())
        return d.get("content", ""), d.get("tokens_predicted", 0), d.get("stop_type") or ("eos" if d.get("stopped_eos") else "max_new_tokens" if d.get("stopped_limit") else "word" if d.get("stopped_word") else "unknown")
    def close(self):
        try: self.proc.terminate(); self.proc.wait(timeout=10)
        except Exception: pass

def make_answerer(model_dir, adapter=None, retriever=None, units=None, use_guard=True, gguf=None, gguf_threads=8):
    """The serving path as a function: input guard -> political/self-harm routing -> retrieval context ->
    generation -> helpline guarantee -> output guard. Returns (answer, last_meta). Used by main() and by
    eval/political_safety.py --serve so the gate measures what a user actually receives.
    gguf: path of a GGUF file; the generation then runs through llama-server (GgufServer) instead of the bf16 weights, everything
    else identical, so the quantised release can be gated through the same path."""
    if units is None:
        units = load_units()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_dir)
    gg = GgufServer(gguf, threads=gguf_threads) if gguf else None
    if gg is None:
        model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.bfloat16)
        if adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter)
        model = model.cuda().eval()
    else:
        model = None

    guard = Guard(enabled=use_guard)
    last_meta = {}

    QUOTE_WORDS = ("எழுது", "எழுதுக", "எழுதுங்கள்", "அப்படியே", "quote", "sollu", "sollunga", "ezhuth", "தருக", "கூறு")

    def answer(user_msg, retrieval=True, prev_question=None, prev_answer=None, packs=None):
        """Guarded answer. The guard verdicts land in last_meta (input/output) for logging.
        prev_question: the previous user turn (UI); for short follow-ups its content words are folded into the retrieval query.
        prev_answer: the previous assistant turn; a pronoun follow-up with a task ("இதை எளிமையாக விளக்குங்கள்") works on it.
        packs: the pack names enabled for this turn (UI checkboxes); None = the config or PACKS env default. Logged as packs_enabled."""
        last_meta.clear()
        ps = load_packs()
        last_meta["packs_enabled"] = sorted(set(packs) & set(ps.packs)) if (ps and packs is not None) else (sorted(ps.default_enabled()) if ps else [])
        fq = followup_query(prev_question, user_msg, meta=last_meta)
        if fq:
            last_meta["query_followup"] = fq
        if self_harm_hint(user_msg):   # before the guard: a self-harm message never gets a bare refusal (family-safe child gate)
            lang = detect_lang(user_msg); hb = helpline_block(lang)
            last_meta["route"] = "self_harm"; last_meta["route_stage"] = "self_harm"; last_meta["action"] = "self_harm_support"
            return support_text(lang) + ("\n\n" + hb if hb else "")
        if FS is not None and FS.is_enabled():
            all_hits = FS.check(user_msg)
            repeat_ask = any(k in user_msg.lower() for k in ("spell", "letter by letter", "repeat", "say it", "say this", "type", "translate", "meaning", "mean", "porul", "artham", "solu", "sollu", "ezhudhu", "எழுது", "சொல்லு", "பொருள்", "அர்த்தம்", "மொழிபெயர்"))
            in_hits = [h for h in all_hits if h.get("severity") in ("slur", "sexual", "profanity", "blocked") or repeat_ask]
            if repeat_ask and not in_hits:
                in_hits = FS.check_context(user_msg)   # context-only words count when the request is to reproduce the word
            if in_hits and not repeat_ask and all(h.get("severity") == "blocked" for h in in_hits):
                # blocked terms (cow, 2026-09-13) are allowed only when the answer comes from the agriculture or nature pack
                _pm = {"packs_enabled": last_meta.get("packs_enabled")}
                _hit = pack_decision(user_msg, _pm); _pd = _pm.get("pack_decision") or {}
                if _hit and _pd.get("used") and _pd.get("pack") in BLOCKED_TERM_PACKS:
                    last_meta["blocked_term_exception"] = _pd.get("pack"); in_hits = []
            if in_hits:   # a crude word in the request (say it / repeat it / translate it / what does it mean): kind refusal, never repeated
                last_meta["route_stage"] = "lexicon_input"; last_meta["action"] = "kind_refusal"; last_meta["lexicon_hits"] = [h.get("span") for h in in_hits][:3]
                return kind_refusal(detect_lang(user_msg))
        risk = child_risk_hint(user_msg)
        if risk:   # family-safe: sexual content, violence against a person, bad words, insults -> kind refusal (rule layer, no model)
            last_meta["route_stage"] = "risk_" + risk; last_meta["action"] = "kind_refusal"
            return kind_refusal(detect_lang(user_msg))
        if romantic_roleplay_hint(user_msg):   # family-safe: no romantic or sexual roleplay, any age
            last_meta["route_stage"] = "romance"; last_meta["action"] = "kind_refusal"
            return kind_refusal(detect_lang(user_msg))
        gin = guard.classify(user_msg, role="user")
        last_meta["guard_input"] = gin
        # "unsafe" input -> refuse without generating; "controversial" (mostly political) -> generate, the
        # model's abstention training and the output filter handle it
        if gin["label"] == "unsafe":
            last_meta["action"] = "refused_input"
            return refusal_text(detect_lang(user_msg))
        # routing order (ruled 2026-09-07): literature > political > self_harm > identity > small_talk > wiki
        stage, lit = decide_route(user_msg, units)
        last_meta["route_stage"] = stage
        if lit and (lit.get("kind") in ("caste", "caste_assistant", "untouchability")) and stage == "caste":
            pass
        elif lit and lit.get("tease"):
            last_meta["route"] = "small_talk"; last_meta["action"] = "tease_reply"
            return tease_reply(detect_lang(user_msg))   # fixed deflection: the insult word is never echoed
        if lit and stage == "literature":
            last_meta["literature_match"] = {"kind": lit["kind"], "mode": lit["mode"], "work_en": lit["unit"].get("work_en"), "number": lit["unit"].get("number"), "corrected": lit.get("corrected")}
        if stage == "self_harm":
            last_meta["route"] = "self_harm"
        if stage == "contested":
            last_meta["action"] = "neutral_reply"
            return neutral_reply(detect_lang(user_msg))
        if stage == "calculator":
            last_meta["action"] = "calculator"; last_meta["calculator"] = {"kind": lit["kind"], "expr": lit["expr"]}; last_meta["decode"] = {"skipped": "calculator route: computed by code"}
            return CALC.answer(lit, detect_lang(user_msg))
        if stage == "dictionary":
            text, dm = DICT.answer(lit["word"], detect_lang(user_msg))
            last_meta["dictionary"] = dict(dm, word=lit["word"])
            if text is not None:
                last_meta["action"] = "dictionary_entry"; last_meta["decode"] = {"skipped": f"dictionary entry ({dm.get('how')}), verbatim"}
                return text
            stage = "wiki" if not is_translation_request(user_msg) else "translation"   # no dictionary pack loaded: the normal routes
            last_meta["route_stage"] = stage
        if stage == "anatomy_translation":
            w, t = anatomy_translation(user_msg)
            last_meta["action"] = "anatomy_translation"; last_meta["decode"] = {"skipped": "body-part vocabulary from the neutral table"}
            return anatomy_reply(w, t, detect_lang(user_msg))
        if stage == "medical_dosage":
            last_meta["action"] = "medical_dosage_reply"; last_meta["decode"] = {"skipped": "medicine dose question: fixed answer, no numbers from the model"}
            return medical_dosage_reply(detect_lang(user_msg))
        if stage == "caste":
            last_meta["action"] = "caste_reply"; last_meta["caste_kind"] = (lit or {}).get("kind"); last_meta["decode"] = {"skipped": "deterministic caste equality answer"}
            return caste_reply((lit or {}).get("kind"), detect_lang(user_msg))
        if stage == "political" and not sheet_is_usable(load_sheet()):
            # office-holder / party / election intent without a verified, recent fact sheet: deterministic abstention
            last_meta["action"] = "political_abstention"
            return political_abstention(detect_lang(user_msg))
        if stage == "identity":
            last_meta["route"] = "identity"; last_meta["action"] = "identity_reply"
            return identity_reply(detect_lang(user_msg))
        if stage in ("person", "wiki", "none", "small_talk") and _FOUNDER_RX.search(user_msg):
            last_meta["route_stage"] = "identity"; last_meta["action"] = "founder_reply"; last_meta["decode"] = {"skipped": "identity fact 11"}
            return founder_reply(detect_lang(user_msg))
        if stage == "person":
            fact = match_fact_sheet(user_msg)
            hits, dec = passage_decision(retriever, user_msg) if retriever is not None else ([], {"used": False})
            last_meta["passage_decision"] = dec
            live = None
            if not fact and not dec.get("used") and WL.is_enabled():
                live = WL.lookup(user_msg, lexicon_check=(lambda t: [h for h in FS.check(t) if h.get("severity") in ("slur", "sexual", "profanity", "blocked")]) if FS is not None else None,
                                 guard_check=(lambda t: guard.classify(t, role="assistant")["label"] == "unsafe"))
                last_meta["wiki_live_called"] = True
            if not fact and not dec.get("used") and not live:
                last_meta["action"] = "unknown_person"; last_meta["decode"] = {"skipped": "unmatched person name: fixed line, no biography"}
                return unknown_person(detect_lang(user_msg))
            stage = "wiki"; last_meta["route_stage"] = "wiki"   # matched: answer from the KB / fact sheet / passage like any lookup
            if live:
                last_meta["person_live"] = {"title": live["title"], "lang": live["lang"]}
        if stage == "literature_ask":
            lit = kb_low_confidence(user_msg) if retriever is not None else None
            if lit:
                stage = "literature"; last_meta["route_stage"] = "literature"; last_meta["literature_match"] = {"kind": lit["kind"], "mode": lit["mode"], "work_en": lit["unit"].get("work_en"), "number": lit["unit"].get("number"), "score": lit.get("score")}
            else:
                last_meta["action"] = "literature_ask"
                return literature_ask(detect_lang(user_msg))
        if stage == "small_talk":
            last_meta["route"] = "small_talk"
        if fq and stage in ("wiki", "none", "small_talk"):
            stage = "wiki"; last_meta["route_stage"] = "wiki"   # a short follow-up to a lookup is a lookup
        if prev_answer and refers_to_previous(user_msg) and stage in ("wiki", "none", "small_talk", "literature_ask"):
            last_meta["route_stage"] = "previous_answer"; last_meta["action"] = "answered"
            out = _decode("[முந்தைய பதில்]\n" + prev_answer.strip()[:3000] + "\n\n" + PREV_INSTRUCTION + "\n\n" + user_msg, temperature=0.3)
        else:
            out = _generate(user_msg, retrieval, stage=stage, lit=lit, rq=fq)
        _allow_blocked = (last_meta.get("retrieval_how") == "pack" and ((last_meta.get("pack_decision") or {}).get("pack") in BLOCKED_TERM_PACKS)) or bool(last_meta.get("blocked_term_exception"))
        _fs = (lambda t: [h for h in FS.check(t) if not (_allow_blocked and h.get("severity") == "blocked")])
        if FS is not None and FS.is_enabled():
            hits = _fs(out)
            if hits:
                last_meta["lexicon_hits_first"] = [h.get("span") for h in hits][:5]
                out = _generate(user_msg, retrieval, stage=stage, lit=lit, temperature=0.3, rq=fq) if last_meta.get("route_stage") != "previous_answer" else _decode("[முந்தைய பதில்]\n" + (prev_answer or "").strip()[:3000] + "\n\n" + PREV_INSTRUCTION + "\n\n" + user_msg, temperature=0.3)   # one regeneration at low temperature
                hits2 = _fs(out)
                if hits2:
                    last_meta["action"] = "lexicon_block"; last_meta["lexicon_hits"] = [h.get("span") for h in hits2][:5]
                    return FS.fallback_text(detect_lang(user_msg))
                last_meta["lexicon_regenerated"] = True
        if self_harm_hint(user_msg):
            hb = helpline_block(detect_lang(user_msg))
            if hb and not any(n in out for n in ("14416", "044-26564444", "112")):
                out = out.rstrip() + "\n\n" + hb   # guarantee the numbers even if the model forgot them
                last_meta["helplines_appended"] = True
        gout = guard.classify(out, role="assistant", prompt=user_msg)
        last_meta["guard_output"] = gout
        if gout["label"] == "unsafe":
            last_meta["action"] = "replaced_output"
            return refusal_text(detect_lang(user_msg))
        wl = last_meta.get("wiki_live") or {}
        if wl.get("title") and last_meta.get("action") != "factual_abstention":   # CC BY-SA attribution + recency caveat, in the user's language
            out = out.rstrip() + "\n\n" + wiki_attribution(detect_lang(user_msg), wl["title"], wl.get("lang", "ta"))
        elif last_meta.get("retrieval_how") == "pack" and (last_meta.get("pack_decision") or {}).get("used") and last_meta.get("action") != "factual_abstention":
            pd = last_meta["pack_decision"]; lang = detect_lang(user_msg); pk = load_packs().packs.get(pd["pack"])
            hit = pk.search(user_msg, k=1)[0] if pk else {}
            hm = (hit.get("meta") or {})
            cav = pack_caveat(pd["pack"], lang, hit)
            src = f"{hm.get('source') or pd['pack']}" + (f" ({hm.get('license')})" if hm.get("license") else "")
            out = out.rstrip() + ("\n\n" + cav if cav else "") + "\n\n" + ("மூலம்: " if lang == "ta" else "source: ") + (pd.get("title") or "") + f", {src}"
            last_meta["caveat_appended"] = bool(cav)
        elif (last_meta.get("passage_decision") or {}).get("used") and last_meta.get("retrieval_how") == "bm25":   # source line at the end (ruling 2026-09-09)
            pd = last_meta["passage_decision"]; lang = detect_lang(user_msg)
            site = {"literature_kb": {"ta": "இலக்கிய நூல் தொகுப்பு", "en": "literature KB", "tanglish": "literature KB"}, "wiki_dump": {"ta": "தமிழ் விக்கிப்பீடியா (CC BY-SA)", "en": "Tamil Wikipedia (CC BY-SA)", "tanglish": "Tamil Wikipedia (CC BY-SA)"}}.get(pd.get("source") or "", {}).get(lang if lang in ("ta", "en", "tanglish") else "en", pd.get("source") or "")
            out = out.rstrip() + "\n\n" + ("மூலம்: " if lang == "ta" else "source: ") + (pd.get("title") or "") + (f", {site}" if site else "")
        if _CAUTION_RX.search(user_msg) and last_meta.get("action") not in ("factual_abstention",):   # brief factual answer with a caution (ruling 2026-09-09)
            out = out.rstrip() + "\n\n" + caution_line(detect_lang(user_msg)); last_meta["caution_appended"] = True
        last_meta["action"] = last_meta.get("action") if last_meta.get("action") == "factual_abstention" else "answered"
        return out

    def _generate(user_msg, retrieval=True, stage=None, lit=None, temperature=None, rq=None):
        ctx = ""
        verbatim_block = ""
        if stage is None:
            stage, lit = decide_route(user_msg, units)
        rq = rq or user_msg   # retrieval query (follow-ups carry the previous turn's entities); the prompt keeps the user's own words
        story_cue = stage == "literature" and lit and is_story_request(user_msg)   # story-from-a-kural (ruling 2026-09-09)
        if stage == "literature" and lit and lit.get("kind") == "any_unit":   # "any kural" / "any song": random unit, verbatim, never generation, never Wikipedia
            import random as _random
            pool = [x for x in lit["units"] if not x.get("adult_theme")] or lit["units"]
            u = _random.SystemRandom().choice(pool)
            lang = detect_lang(user_msg)
            last_meta["verbatim"] = "any_unit"; last_meta["retrieval_how"] = "literature"; last_meta["retrieval_top_score"] = "exact"
            last_meta["literature_match"] = dict(last_meta.get("literature_match") or {}, number=u.get("number"), pool=len(pool), theme=lit.get("theme"), theme_matched=lit.get("theme_matched"))
            if story_cue:
                return _story_answer(u, user_msg, temperature)
            last_meta["decode"] = {"skipped": "any_unit: one random KB unit, verbatim"}
            return any_unit_block(u, lang, theme=lit.get("theme"), theme_matched=lit.get("theme_matched"))
        if retrieval and retriever is not None and stage not in ("small_talk", "identity", "none"):
            ctx, how, u = retrieval_context(retriever, units, rq, stage=stage, lit=lit, meta=last_meta)
            last_meta["retrieval_how"] = how
            if stage == "wiki" and WL.is_enabled() and not last_meta.get("wiki_live_called") and not is_howto_request(user_msg) and how != "pack":
                confident, top = local_confident(retriever, rq)
                last_meta["wiki_live_called"] = True; last_meta["local_top_raw"] = round(top, 2)
                if not confident:   # one live lookup per turn; family-safe filtered inside lookup()
                    res = WL.lookup(rq, lexicon_check=(lambda t: [h for h in FS.check(t) if h.get("severity") in ("slur", "sexual", "profanity", "blocked")]) if FS is not None else None,
                                    guard_check=(lambda t: guard.classify(t, role="assistant")["label"] == "unsafe"))
                    if res:
                        block = f"[Wikipedia ({res['lang']}): {res['title']}]\n{res['extract']}"
                        ctx = block + "\n\n" + FACT_INSTRUCTION + "\n\n"
                        last_meta["route_stage"] = "wiki_live"; last_meta["retrieval_how"] = "wiki_live"
                        last_meta["wiki_live"] = {"title": res["title"], "lang": res["lang"], "score": res["score"], "url": res["url"]}
                    else:
                        last_meta["wiki_live"] = {"dropped_or_none": True}
                        if top < 3.0 and not is_who_retrieval_question(user_msg):   # nothing local worth showing either: abstain rather than guess
                            last_meta["route_stage"] = "wiki_live"; last_meta["action"] = "factual_abstention"; last_meta["decode"] = {"skipped": "no usable source"}
                            last_meta["abstention_kind"] = abstention_kind(user_msg)
                            return factual_abstention(detect_lang(user_msg), last_meta["abstention_kind"])
                        if top < 3.0:
                            last_meta["abstention_skipped"] = "who_retrieval_question"
            pd = last_meta.get("passage_decision") or {}
            if stage in ("exact",) or how in ("exact", "literature"):
                last_meta["retrieval_top_score"] = "exact"; last_meta["retrieval_top_source"] = "literature_kb"
            else:
                last_meta["retrieval_top_score"] = pd.get("top_raw"); last_meta["retrieval_top_source"] = pd.get("source") if pd.get("used") else None
            if story_cue and lit.get("units"):   # story or poem built from the matched kural, grounded on the urai
                return _story_answer(u if u is not None else lit["units"][0], user_msg, temperature)
            explain_cue = any(w in user_msg.lower() for w in EXPLAIN_WORDS)
            if explain_cue and stage == "literature" and lit and lit.get("units") and lit.get("kind") != "any_unit":
                # explain format (ruling 2026-09-09): verbatim kural + urai verbatim, then a paraphrase of the urai at T 0.3; no related-kural list
                ue = u if u is not None else lit["units"][0]
                if ue.get("adult_theme"):
                    last_meta["route_stage"] = "literature"; last_meta["verbatim"] = "adult_theme_framing_only"
                    return format_context([ue])
                block, urai = explain_block(ue)
                last_meta["verbatim"] = "explain"; last_meta["urai_used"] = (urai or None) if len(urai or "") < 400 else f"{len(urai)} chars"; last_meta["explain_unit"] = {"work_en": ue.get("work_en"), "number": ue.get("number")}
                last_meta["commentaries"] = [c["commentator"] for c in kural_commentaries(ue.get("number"))] if (ue.get("work_en") or "").lower().startswith("thirukkural") else []
                if not urai:   # no urai in the KB: quote only, say so, no generation
                    last_meta["decode"] = {"skipped": "no urai in the KB for this unit"}
                    return block.rstrip() + "\n\n" + {"ta": "இந்தப் பாடலுக்கு உரை என் நூல் தொகுப்பில் இல்லை.", "tanglish": "Indha paadal ku urai en KB la illa.", "en": "There is no urai for this unit in my knowledge base."}.get(detect_lang(user_msg), "There is no urai for this unit in my knowledge base.")
                # the restatement prompt carries the kural and the TAMIL commentaries' gloss lines only (the grammar notes in
                # parentheses and the English verse confuse a 2B model into inventing a couplet, seen 2026-09-10); the answer shown
                # keeps every commentary verbatim. The restatement is kept only when it stays inside the commentaries.
                small = restatement_source(ue, block)
                lang_e = detect_lang(user_msg)
                if os.environ.get("EXPLAIN_RESTATE", "0") != "1":
                    # generated restatement OFF by default (2026-09-10): the round-3 weights produce meta-talk, invented couplets or a modern
                    # copyrighted commentator's name in 6 of 6 samples. The public-domain English prose gloss (Drew and Lazarus) stands in.
                    last_meta["restatement_dropped"] = "generation_off"; last_meta["decode"] = {"skipped": "explain: verbatim commentaries and the public-domain prose gloss; EXPLAIN_RESTATE=1 enables generation"}
                    return block.rstrip() + prose_gloss_line(ue, lang_e)
                prompt_text = small + EXPLAIN_INSTRUCTION + "\n\n" + user_msg
                lead = {"ta": "எளிய தமிழில்: ", "tanglish": "Simple-a sollanum na: ", "en": "In short: "}.get(lang_e, "In short: ")
                rest = _decode(prompt_text, temperature or EXPLAIN_TEMPERATURE).strip()
                rest = re.split(r"\n\s*\n", rest)[0].strip()
                ok, share, why = restatement_ok(rest, small)
                last_meta["restatement_inside"] = round(share, 2); last_meta["restatement_candidate"] = rest[:300]
                if not ok:   # not a restatement of the commentaries: shown without one (no fabrication)
                    last_meta["restatement_dropped"] = why
                    return block.rstrip()
                return block + lead + rest
            # direct-quote guarantee: for a matched unit the verbatim text is emitted from the KB, never the model;
            # for a matched section/collection/work the first unit is quoted and the others are listed by first line
            if how == "literature" and lit and lit.get("units"):
                us = lit["units"]
                u0 = us[0]
                verbatim_block = f"{u0.get('work')} {u0.get('number')}" + (f" ({(u0.get('section') or {}).get('poem_title') or (u0.get('section') or {}).get('adhikaram') or ''})" if (u0.get('section') or {}).get('poem_title') or (u0.get('section') or {}).get('adhikaram') else "") + ":\n" + "\n".join(u0.get("text", [])[:24]) + "\n\n"
                if u0.get("adult_theme"):   # family-safe: adult-theme literature is quoted with its scholarly framing only, never free-generated
                    last_meta["route_stage"] = "literature"; last_meta["verbatim"] = "adult_theme_framing_only"
                    return format_context([u0])
                if len(us) > 1:
                    verbatim_block += "இதே பகுதியில் உள்ள மற்ற பாடல்கள்:\n" + "\n".join(f"- {x.get('work')} {x.get('number')}: {(x.get('text') or [''])[0]}" for x in us[1:8]) + "\n\n"
                last_meta["verbatim"] = "section"
            if how == "exact" and u is not None:   # any question about a specific unit: the verbatim text comes from the KB, never the model
                verbatim_block = f"{u.get('work')} {u.get('number')}:\n" + "\n".join(u.get("text", [])) + "\n\n"
                last_meta["verbatim"] = "unit"
                if any(w in user_msg.lower() for w in EXPLAIN_WORDS):   # meaning/explanation asked: the public-domain urai and translation are quoted verbatim too
                    urai = u.get("urai") or u.get("parimelazhagar") or (u.get("urai_parimelazhagar") if isinstance(u.get("urai_parimelazhagar"), str) else None)
                    if isinstance(urai, dict): urai = next(iter(urai.values()), None)
                    en = u.get("couplet_en") or u.get("translation_en")
                    if urai: verbatim_block += "பரிமேலழகர் உரை: " + str(urai).strip() + "\n\n"
                    if en: verbatim_block += "English (public-domain translation): " + str(en).strip() + "\n\n"
        if verbatim_block and not any(w in user_msg.lower() for w in EXPLAIN_WORDS) and stage == "literature":
            last_meta["decode"] = {"skipped": "verbatim-only literature answer (quote guarantee); add an explain word for a paraphrase"}
            return verbatim_block.rstrip() + "\n"
        prompt_text = ctx + user_msg
        return verbatim_block + _decode(prompt_text, temperature)

    def _story_answer(u, user_msg, temperature=None):
        """Verbatim kural (number and chapter from the KB only), then an original short story illustrating it,
        grounded on the Parimelazhagar urai, at temperature 0.7 (ruling 2026-09-09)."""
        if u.get("adult_theme"):
            last_meta["route_stage"] = "literature"; last_meta["verbatim"] = "adult_theme_framing_only"
            return format_context([u])
        shown = kural_head(u)
        urai = unit_urai(u).split("(")[0].strip()
        last_meta["route_stage"] = "literature"; last_meta["verbatim"] = "story_from_kural"; last_meta["retrieval_how"] = "literature"; last_meta["retrieval_top_score"] = "exact"
        last_meta["urai_used"] = urai or None
        last_meta["explain_unit"] = {"work_en": u.get("work_en"), "number": u.get("number"), "adhikaram": (u.get("section") or {}).get("adhikaram")}
        grounding = shown + ("பரிமேலழகர் உரை: " + urai + "\n\n" if urai else "")
        story, dropped = scrub_memory_refs(_decode(grounding + STORY_INSTRUCTION + "\n\n" + user_msg, temperature or STORY_TEMPERATURE))
        if dropped:
            last_meta["story_sentences_dropped"] = dropped[:5]
        if len(story) < 40:   # nothing usable left: the verbatim kural stands alone rather than a broken story
            last_meta["action"] = "story_unusable"
            return shown.rstrip() + "\n\n" + {"ta": "இந்தக் குறளுக்கு ஒரு கதையை இப்போது சரியாக எழுத முடியவில்லை.", "tanglish": "Indha kural ku oru kathai ippo sariyaa ezhutha mudiyala.", "en": "I could not write a good story for this kural just now."}.get(detect_lang(user_msg), "I could not write a good story for this kural just now.")
        return shown + story

    def _decode(prompt_text, temperature=None):
        if getattr(tok, "chat_template", None):
            msgs = [{"role": "system", "content": SFT_SYS}, {"role": "user", "content": prompt_text}]   # same system prompt as every SFT row
            text = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
            eos = tok.convert_tokens_to_ids("<|im_end|>")
        else:   # base (CPT-only) model: plain prompt
            text = prompt_text + "\n\nபதில்:"
            eos = tok.eos_token_id
        greedy = os.environ.get("SERVE_GREEDY") == "1"   # release gates compare builds greedy (ruling 2026-09-12) so the sampler is out of the comparison
        if gg is not None:   # GGUF backend: same prompt text and sampling settings through llama-server
            out, n_new, stopped = gg.complete(text, DECODE["max_new_tokens"], 0.0 if greedy else (temperature or DECODE["temperature"]), 1.0 if greedy else DECODE["top_p"], DECODE["repetition_penalty"], DECODE["seed"], ["<|im_end|>"])
            last_meta["decode"] = dict(DECODE, temperature=(temperature or DECODE["temperature"]), new_tokens=int(n_new), stopped_by=stopped, backend=f"llama.cpp gguf {os.path.basename(gg.gguf)}",
                                       no_repeat_ngram_size="not available in llama.cpp", repeated_6gram_stop="not available in llama.cpp")
            return out.strip()
        ids = tok(text, return_tensors="pt").input_ids.cuda()
        torch.manual_seed(DECODE["seed"])
        stop = RepeatedNgramStop(ids.shape[1], n=6, times=3)
        with torch.no_grad():
            samp = dict(do_sample=False) if greedy else dict(do_sample=True, temperature=(temperature or DECODE["temperature"]), top_p=DECODE["top_p"])
            g = model.generate(ids, max_new_tokens=DECODE["max_new_tokens"], **samp, repetition_penalty=DECODE["repetition_penalty"],
                               no_repeat_ngram_size=DECODE["no_repeat_ngram_size"], eos_token_id=eos,
                               pad_token_id=tok.eos_token_id, stopping_criteria=StoppingCriteriaList([stop]))
        new = g[0, ids.shape[1]:]
        last_meta["decode"] = dict(DECODE, temperature=("greedy" if greedy else (temperature or DECODE["temperature"])), new_tokens=int(new.shape[0]), stopped_by=("repeated_6gram" if stop.fired else
                                   "eos" if (eos in new[-1:].tolist() or new[-1].item() == tok.eos_token_id) else "max_new_tokens"))
        return tok.decode(new, skip_special_tokens=True)

    return answer, last_meta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-index", action="store_true")
    ap.add_argument("--model"); ap.add_argument("--adapter", default=None, help="optional LoRA adapter on top of --model (pre-merge evaluation)"); ap.add_argument("--chat"); ap.add_argument("--no-retrieval", action="store_true")
    ap.add_argument("--probe"); ap.add_argument("--out")
    ap.add_argument("--retrieve", help="print the retrieval context for a query and exit")
    ap.add_argument("--retrieval-config", default=DEFAULT_CONFIG)
    ap.add_argument("--no-guard", action="store_true", help="disable the serving guard (guard.py: input and output moderation, on by default)")
    a = ap.parse_args()
    if a.build_index:
        build_kb_index(); return
    units = load_units()
    retriever = None if a.no_retrieval else SourceRetriever(a.retrieval_config)
    if a.retrieve:
        ctx, how, _ = retrieval_context(retriever, units, a.retrieve) if retriever else ("", "none", None)
        print(f"[{how}]\n{ctx}"); return
    if not a.model:
        return
    answer, last_meta = make_answerer(a.model, adapter=a.adapter, retriever=retriever, units=units, use_guard=not a.no_guard)

    if a.chat:
        print(answer(a.chat, retrieval=not a.no_retrieval))
        print("[guard]", json.dumps(last_meta, ensure_ascii=False)[:400])
    if a.probe:
        items = [json.loads(l) for l in open(a.probe) if '"quote_kural"' in l]
        res = {"exact": 0, "n": 0}
        for it in items:
            g = answer(it["prompt"], retrieval=not a.no_retrieval)
            sq = re.sub(r"[^஀-௿A-Za-z0-9]+", "", nfc(g))
            res["n"] += 1; res["exact"] += it["answer_squashed"] in sq
        res["quote_exact_acc"] = res["exact"] / max(1, res["n"]); res["retrieval"] = not a.no_retrieval
        print(res)
        if a.out:
            json.dump(res, open(a.out, "w"), indent=2)

if __name__ == "__main__":
    main()
