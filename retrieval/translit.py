"""Roman -> Tamil-script query expansion for retrieval (ruling 2026-09-09).

The UI's bundled transliterator (ui/transliterate.js, MIT) is the single source of truth for phonetic typing, so the
server calls the same code through a persistent node process instead of re-implementing it in Python. For every
romanised content word in a query the top candidates are appended in Tamil script, so "kulambu recipe" can reach
குழம்பு in the index. If node or the script is missing, expansion is a no-op and search proceeds on the raw query.

expand_query(query) -> (expanded_query, {"word": [candidates...]})
"""
import json
import os
import re
import subprocess
import threading

JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "transliterate.js")
_TA = re.compile(r"[஀-௿]")
_WORD = re.compile(r"[A-Za-z]{3,}")
# English function words and request words: never transliterated (they would only add noise)
_SKIP = {"the", "and", "for", "with", "how", "what", "who", "why", "when", "where", "which", "give", "tell", "make", "recipe", "please", "plz", "can", "you",
         "about", "step", "steps", "way", "best", "some", "any", "all", "from", "this", "that", "into", "want", "need", "like", "help", "sollu", "sollunga",
         "solu", "enna", "epdi", "eppadi", "pathi", "patri", "pathy", "yen", "yaru", "yaaru", "yaar", "yar", "irukku", "iruku", "illa", "illai", "panna", "pannu", "pannunga", "periya", "chinna", "nalla", "kettha", "romba", "konjam", "innoru", "vera", "enga", "anga", "inga",
         "oru", "onnu", "naan", "nee", "neenga", "enakku", "unakku", "namma", "avan", "aval", "avanga", "idhu", "adhu", "edhu", "ethu", "innaiku", "inniki",
         "quick", "easy", "simple", "short", "long", "small", "big", "good", "bad", "new", "old", "home", "house", "one", "two", "three", "and", "not"}
_MAX = 2   # candidates per word

# ---- English filter (ruling 2026-09-09) -----------------------------------------------------------
# The expansion is for romanised TAMIL. An English token transliterated letter by letter produces
# nonsense ("leave" -> லெஅவே, "history" -> ஹிச்டொர்ய்) which then pulls unrelated articles, so a token
# is expanded only when it is not a common English word, has a Tamil phonotactic shape, and its
# candidate actually exists in the index vocabulary (checked by the caller through in_vocab).
ENGLISH_WORDS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "english_words.txt")
_ENGLISH = None
def english_words():
    global _ENGLISH
    if _ENGLISH is None:
        try:
            _ENGLISH = {l.strip().lower() for l in open(ENGLISH_WORDS_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")}
        except Exception:
            _ENGLISH = set()
    return _ENGLISH

_NON_TAMIL_LETTERS = re.compile(r"[qwxz]")            # w, q, x, z do not occur in romanised Tamil (zh is handled below)
_ONSET_CLUSTERS = ("bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "sc", "sk", "sl", "sm", "sn", "sp", "st", "sw", "tw", "tr", "wh", "kn", "wr", "ps", "pn")
_ENGLISH_TAILS = ("tion", "sion", "ment", "ness", "able", "ible", "ance", "ence", "ship", "ology", "ing", "ed", "ly", "ry", "ty", "cy", "ce", "ge", "se", "ve", "ck", "ght", "ple", "tle", "ble", "dle", "gle", "ers", "ies", "ous", "ive", "ful", "est")
_VOWELS = set("aeiou")
def looks_romanised_tamil(w):
    """Phonotactic shape test: romanised Tamil is mostly open syllables, has no q/w/x/z (except zh),
    no English onset clusters and none of the common English endings."""
    w = w.lower()
    if len(w) < 3 or not (_VOWELS & set(w)):
        return False
    if _NON_TAMIL_LETTERS.search(w.replace("zh", "")):
        return False
    if w.startswith(_ONSET_CLUSTERS):
        return False
    if w.endswith(_ENGLISH_TAILS):
        return False
    if re.search(r"[bcdfghjklmnprstvy]{3}", w):          # three consonants in a row: English, not Tamil
        return False
    return True

def expandable(word):
    """(ok, reason) for logging: why a token was or was not transliterated."""
    w = word.lower().strip(".,!?:;\"'()")
    if not w or w in _SKIP:
        return False, "skip_list"
    if w in english_words():
        return False, "english_word"
    if not looks_romanised_tamil(w):
        return False, "not_tamil_shape"
    return True, "ok"

_proc = None
_lock = threading.Lock()


def _start():
    global _proc
    if not os.path.exists(JS):
        return None
    code = ("const T=require(process.argv[1]);const rl=require('readline').createInterface({input:process.stdin});"
            "rl.on('line',l=>{try{const q=JSON.parse(l);const out={};for(const w of q.words){out[w]=T.candidates(w,q.max);}console.log(JSON.stringify(out));}"
            "catch(e){console.log('{}');}});")
    try:
        _proc = subprocess.Popen(["node", "-e", code, JS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except Exception:
        _proc = None
    return _proc


def candidates(words, max_per_word=_MAX):
    """{word: [tamil candidates]} for the given roman words; {} when node is unavailable."""
    global _proc
    words = [w for w in dict.fromkeys(words) if w]
    if not words:
        return {}
    with _lock:
        if _proc is None or _proc.poll() is not None:
            if _start() is None:
                return {}
        try:
            _proc.stdin.write(json.dumps({"words": words, "max": max_per_word}) + "\n"); _proc.stdin.flush()
            line = _proc.stdout.readline()
            out = json.loads(line or "{}")
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
            _proc = None
            return {}
    clean = {}
    for w, cs in out.items():
        cs = [c if isinstance(c, str) else (c.get("text") or c.get("word") or "") for c in (cs or [])]
        cs = [c for c in cs if c and _TA.search(c) and not re.search(r"[A-Za-z]", c)]   # a Latin letter left over means the word is not Tamil
        cs = cs[:max_per_word]
        # Tanglish writes ழ as "l" (kulambu, vaalkai, tamil): add the ழ variant of the first candidate
        for c in list(cs):
            for src in ("ல", "ள"):
                if src in c:
                    v = c.replace(src, "ழ", 1)
                    if v not in cs:
                        cs.append(v)
                    break
        if cs:
            clean[w] = cs[: max_per_word + 2]
    return clean


def expand_query(query, in_vocab=None):
    """Append Tamil-script candidates for the romanised TAMIL words of a query (unchanged when the query is already
    Tamil). English words and tokens without a Tamil phonotactic shape are never expanded; when in_vocab is given
    (a callable term -> bool, normally the index vocabulary), only candidates that exist in the index survive."""
    if _TA.search(query) and not _WORD.search(query):
        return query, {}
    words, skipped = [], {}
    for w in _WORD.findall(query):
        ok, why = expandable(w)
        (words.append(w.lower()) if ok else skipped.setdefault(w.lower(), why))
    words = list(dict.fromkeys(words))
    if not words:
        return query, {}
    cands = candidates(words)
    if in_vocab is not None:
        kept = {}
        for w, cs in cands.items():
            cs2 = [c for c in cs if in_vocab(c)]
            if cs2:
                kept[w] = cs2
            else:
                skipped[w] = "no_candidate_in_index"
        cands = kept
    if not cands:
        return query, {}
    extra = " ".join(c for w in words for c in cands.get(w, []))
    return (query + " " + extra).strip(), cands


if __name__ == "__main__":
    import sys
    for q in sys.argv[1:] or ["tomato chutney recipe", "idli maavu epdi araikanum", "bus pass renew panna epdi",
                              "kaaviri aaru pathi", "birds list", "cough syrup dosage", "gravity explain pannu"]:
        print(q, "->", expand_query(q))
