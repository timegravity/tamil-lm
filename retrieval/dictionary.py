"""Dictionary route (ruling 2026-09-10): a word-meaning request returns the dictionary entry verbatim with attribution
before any generation; an unknown word gets the nearest entries, never a guess.

Data: data/packs/dictionary/chunks.jsonl (after pack_scan.py), one entry per row with the structured fields
{word, script, direction, pos, meanings, examples, translit, source, url, license, edition}. Loaded lazily into an
exact index (normalised headword), a transliteration index (romanised headword) and a sorted list for nearest lookup.

Cue detection (is_word_meaning_request) is rule-based: "X meaning", "X porul", "X என்றால் என்ன", "X அர்த்தம்", "meaning of X",
"translate the word X", "X in English", "X தமிழில்". A cue with more than four content words is not a dictionary
request (that is a sentence translation or a question) and falls through to the normal routes.
"""
import bisect, json, os, re, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS = os.path.join(ROOT, "data", "packs", "dictionary", "chunks.jsonl")

_ENTRIES = None; _EXACT = None; _TRANSLIT = None; _WORDS = None

def norm(w):
    w = unicodedata.normalize("NFC", (w or "").strip().lower())
    return re.sub(r"[\s​‌‍.,;:!?\"'()\[\]]+", "", w)

def load():
    global _ENTRIES, _EXACT, _TRANSLIT, _WORDS
    if _ENTRIES is not None:
        return bool(_ENTRIES)
    _ENTRIES = []; _EXACT = {}; _TRANSLIT = {}
    if not os.path.exists(CHUNKS):
        _WORDS = []; return False
    for l in open(CHUNKS, encoding="utf-8"):
        if not l.strip():
            continue
        d = json.loads(l)
        if not d.get("word"):
            continue
        _ENTRIES.append(d)
        _EXACT.setdefault(norm(d["word"]), []).append(d)
        if d.get("translit"):
            _TRANSLIT.setdefault(norm(d["translit"]), []).append(d)
    _WORDS = sorted(_EXACT)
    return bool(_ENTRIES)

# ---------------------------------------------------------------- cue detection
_TA_WORD = r"[஀-௿]{2,}"
_LAT_WORD = r"[A-Za-z]{2,}"
_CUES = [
    re.compile(rf"^\s*(?:the\s+)?(?:word\s+)?(?P<w>{_TA_WORD}|{_LAT_WORD})\s+(?:meaning|artham|arththam|porul|porull|nu\s+artham|oda\s+meaning|oda\s+porul)\s*(?:enna|na|sollu|sollunga|\?)*\s*$", re.I),
    re.compile(rf"^\s*(?:what\s+is\s+the\s+|what's\s+the\s+)?meaning\s+of\s+(?:the\s+word\s+)?['\"]?(?P<w>{_TA_WORD}|{_LAT_WORD})['\"]?\s*\??\s*$", re.I),
    re.compile(rf"^\s*(?:what\s+does\s+)['\"]?(?P<w>{_TA_WORD}|{_LAT_WORD})['\"]?\s+mean\s*(?:in\s+(?:tamil|english))?\s*\??\s*$", re.I),
    re.compile(rf"^\s*(?:translate|translation\s+of)\s+(?:the\s+word\s+)?['\"]?(?P<w>{_TA_WORD}|{_LAT_WORD})['\"]?\s*(?:to|into|in)?\s*(?:tamil|english)?\s*\??\s*$", re.I),
    re.compile(rf"^\s*['\"]?(?P<w>{_TA_WORD}|{_LAT_WORD})['\"]?\s+(?:in\s+english|in\s+tamil|english\s+la|tamil\s+la|tamil\s+word|english\s+word)\s*(?:enna|\?)*\s*$", re.I),
    re.compile(rf"^\s*(?P<w>{_TA_WORD}|{_LAT_WORD})\s+(?:என்றால்\s+என்ன|என்பதன்\s+பொருள்(?:\s+என்ன)?|அர்த்தம்(?:\s+என்ன)?|பொருள்(?:\s+என்ன)?|என்பதன்\s+அர்த்தம்(?:\s+என்ன)?|ஆங்கிலத்தில்(?:\s+என்ன)?|தமிழில்(?:\s+என்ன)?)\s*\??\s*$"),
    re.compile(rf"^\s*(?P<w>{_TA_WORD}|{_LAT_WORD})\s+(?:meaning|porul|artham)\s+(?:in\s+)?(?:tamil|english)\s*\??\s*$", re.I),
]

_EN_WORDS = None
def _is_english_word(w):
    global _EN_WORDS
    if _EN_WORDS is None:
        p = os.path.join(ROOT, "data", "english_words.txt")
        _EN_WORDS = {l.strip().lower() for l in open(p, encoding="utf-8")} if os.path.exists(p) else set()
    return w.lower() in _EN_WORDS

def is_word_meaning_request(msg):
    """The headword when msg is a single-word meaning request, else None. An English headword in the English cue forms
    ("meaning of life", "what does honour mean") is a question, not a dictionary request, unless "in Tamil" follows."""
    m = (msg or "").strip()
    if len(m) > 80:
        return None
    for i, rx in enumerate(_CUES):
        g = rx.match(m)
        if g:
            w = g.group("w")
            if not w or w.lower() in ("this", "that", "word", "the", "இது", "அது"):
                return None
            if i in (1, 2) and not re.search(r"[஀-௿]", w) and _is_english_word(w) and not re.search(r"in\s+tamil", m, re.I):
                return None
            return w
    return None

# ---------------------------------------------------------------- lookup
def lookup(word, k=4):
    """Entries for the word: exact headword, then romanised headword, else the nearest entries (prefix, then edit distance)."""
    if not load():
        return [], "no_dictionary"
    n = norm(word)
    if n in _EXACT:
        return _EXACT[n][:k], "exact"
    if n in _TRANSLIT:
        return _TRANSLIT[n][:k], "translit"
    if re.fullmatch(r"[a-z]+", n):   # romanised Tamil ("kadhal", "yaanai"): the transliteration candidates that are headwords
        try:
            from .translit import looks_romanised_tamil, candidates
            if looks_romanised_tamil(n):
                out = []
                for c in (candidates([n], max_per_word=40).get(n) or []):
                    if norm(c) in _EXACT:
                        out += _EXACT[norm(c)][:2]
                    if len(out) >= k:
                        break
                if out:
                    return out[:k], "translit"
        except Exception:
            pass
    # nearest: shared prefix on the sorted headword list, then edit distance within a small window
    i = bisect.bisect_left(_WORDS, n)
    cands = _WORDS[max(0, i - 25): i + 25]
    def ed(a, b):
        if abs(len(a) - len(b)) > 3:
            return 99
        prev = list(range(len(b) + 1))
        for x, ca in enumerate(a, 1):
            cur = [x]
            for y, cb in enumerate(b, 1):
                cur.append(min(prev[y] + 1, cur[y - 1] + 1, prev[y - 1] + (ca != cb)))
            prev = cur
        return prev[-1]
    scored = sorted(((ed(n, c), -_common_prefix(n, c), c) for c in cands), key=lambda t: (t[0], t[1]))
    near = [c for d, p, c in scored if d <= max(2, len(n) // 3) or -p >= max(3, len(n) - 2)][:k]
    out = []
    for c in near:
        out += _EXACT[c][:1]
    return out, ("nearest" if out else "none")

def _common_prefix(a, b):
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i

# ---------------------------------------------------------------- rendering
_SRC_LINE = {"ta": "மூலம்", "en": "source", "tanglish": "source"}

_WIKI_JUNK = re.compile(r"\]\]|\[\[|={2,}|\{\{|\}\}|\|")
def clean(m):
    m = _WIKI_JUNK.sub(" ", str(m)); m = re.sub(r"\s+", " ", m).strip(" :;,")
    return m

def render(entries, how, word, lang="ta"):
    L = lang if lang in ("ta", "en", "tanglish") else "en"
    lines = []
    if how == "nearest":
        lines.append({"ta": f"\"{word}\" என்ற சொல் அகராதியில் இல்லை. அருகில் உள்ள சொற்கள்:", "en": f"\"{word}\" is not in the dictionary. Nearest entries:", "tanglish": f"\"{word}\" dictionary la illa. Nearest entries:"}[L])
    for e in entries:
        head = e.get("word", "")
        if e.get("translit") and re.search(r"[஀-௿]", head):
            head += f" ({e['translit']})"
        pos = f" [{e['pos']}]" if e.get("pos") else ""
        meanings = e.get("meanings") or []
        ms = [clean(m) for m in meanings[:6]]; ms = [m for m in ms if m]
        if not ms:
            continue
        lines.append(f"{head}{pos}: " + "; ".join(ms))
        for ex in (e.get("examples") or [])[:2]:
            ex = clean(ex)
            if ex:
                lines.append(f"  எ.கா.: {ex}" if L == "ta" else f"  e.g.: {ex}")
        src = e.get("source") or "dictionary"
        if e.get("edition"):
            src += f" ({e['edition']})"
        if e.get("license"):
            src += f", {e['license']}"
        lines.append(f"  {_SRC_LINE[L]}: {src}")
    return "\n".join(lines)

def answer(word, lang="ta", k=4):
    """(text, meta) for a word-meaning request; text is None when the dictionary is not loaded."""
    entries, how = lookup(word, k=k)
    if how == "no_dictionary":
        return None, {"how": how}
    if how == "none":
        text = {"ta": f"\"{word}\" என்ற சொல் அகராதியில் இல்லை; அருகில் உள்ள சொல்லும் இல்லை. எழுத்துப்பிழை உள்ளதா எனப் பாருங்கள்.",
                "en": f"\"{word}\" is not in the dictionary and no nearby entry was found. Please check the spelling.",
                "tanglish": f"\"{word}\" dictionary la illa, nearby word um illa. Spelling check pannunga."}[lang if lang in ("ta", "en", "tanglish") else "en"]
        return text, {"how": how, "entries": 0}
    return render(entries, how, word, lang), {"how": how, "entries": len(entries), "sources": sorted({e.get("source") or "" for e in entries})}
