"""Family-safe hashed lexicon backstop (ruling 2026-09-08). The plain lexicon is private; this module
ships only salted SHA-256 hashes (data/lexicon.hashed) and checks model output against them.

Normalisation: lowercase; leetspeak digits/symbols back to letters; Tamil script to canonical roman via
retrieval.roman.to_roman; letters only (no doubled-letter collapse, so butt is not but; doubled forms are enumerated
as variants). Tamil script stays in a separate namespace and is never transliterated for matching. check() tests every token on its own
(never joined with its neighbours), every 2-word window against two-word entries only, and runs of three or more
single-character tokens joined among themselves (spaced-out words). Hash lines carry a "1:" (single-word) or "2:"
(two-word) prefix; entries of three or more words are not part of the backstop (the classifier handles them).

FAMILY_SAFE=1 by default; a developer sets FAMILY_SAFE=0 to disable.
  python family_safe.py --build data/private/lexicon/lexicon.jsonl   (regenerates data/lexicon.hashed)
  python family_safe.py --selftest
"""
import hashlib, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retrieval.roman import to_roman

HASHED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lexicon.hashed")
SEVERITY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lexicon.severity")   # "<hash> <severity>" per line, same salt
SEVERE = ("slur", "sexual")
SALT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lexicon.salt")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
_SET = None; _SET2 = None; _SALT = None; _SEV = None

def _salt():
    global _SALT
    if _SALT is None:
        _SALT = open(SALT_FILE).read().strip() if os.path.exists(SALT_FILE) else ""
    return _SALT

def normalise(s):
    """Two namespaces so Tamil words never collide with English/roman entries through transliteration:
    Tamil script -> "ta:" + Tamil letters only (repeated signs collapsed); everything else -> "rom:" + lowercase,
    leetspeak reversed, letters only, repeated letters collapsed. Spelling equivalences (th/dh, zh/l, long
    vowels) come from the enumerated variants, not from a lossy skeleton."""
    s = (s or "").lower().translate(_LEET)
    if re.search(r"[஀-௿]", s):
        s = re.sub(r"[^஀-௿]+", "", s)
        return "ta:" + s
    s = re.sub(r"[^a-z]+", "", s)
    return "rom:" + s   # no doubled-letter collapse: butt must not equal but; doubled forms are enumerated as variants

_SET3 = set()   # context-only entries, consulted by check_context() only

def _h(norm):
    return hashlib.sha256((_salt() + ":" + norm).encode("utf-8")).hexdigest()

def load(path=HASHED):
    global _SET, _SET2, _SET3, _SEV
    _SET = set(); _SET2 = set(); _SET3 = set(); _SEV = {}
    if os.path.exists(path):
        for l in open(path, encoding="utf-8"):
            l = l.strip()
            if not l or l.startswith("#"): continue
            if l.startswith("2:"): _SET2.add(l[2:])
            if l.startswith("3:"): _SET3.add(l[2:])
            elif l.startswith("1:"): _SET.add(l[2:])
            else: _SET.add(l)   # v1 file without prefixes: single-word semantics
    sev_path = path.replace(".hashed", ".severity") if path.endswith(".hashed") else SEVERITY
    if os.path.exists(sev_path):
        for l in open(sev_path, encoding="utf-8"):
            p = l.strip().split()
            if len(p) == 2 and not l.startswith("#"): _SEV[p[0]] = p[1]
    return _SET

def severity_of(norm):
    """Severity of a normalised form (slur | sexual | profanity | mild), or None when unknown."""
    if _SET is None: load()
    return (_SEV or {}).get(_h(norm))

def normalise_words(words):
    """Normalised form of a two-word entry: each word normalised on its own, joined by one space."""
    return " ".join(normalise(w) for w in words)

def check_context(text):
    """Like check() but against the context-only entries (all severities): used only when the request asks to
    spell, repeat, translate or explain a word, where reproducing it is the point of the request."""
    global _SET, _SET2
    saved = (_SET, _SET2)
    try:
        _SET, _SET2 = _SET3, set()
        return [dict(h, severity="context") for h in check(text)]
    finally:
        _SET, _SET2 = saved

def is_enabled():
    return os.environ.get("FAMILY_SAFE", "1") != "0"

def _tokens(text):
    """Whitespace and punctuation split tokens; an apostrophe splits too, so "Who 're" becomes two tokens and is never read as one joined word."""
    return re.findall(r"[a-zA-Z0-9@$!]+|[஀-௿]+", text or "")

def check(text, min_len=3):
    """Return the offending spans (deduplicated) or []; empty when disabled or no lexicon loaded.
    Single tokens are tested on their own (never concatenated with neighbours); 2-word windows are tested only
    against two-word entries; runs of three or more single-character tokens are joined among themselves."""
    if not is_enabled(): return []
    if _SET is None: load()
    if not _SET and not _SET2: return []
    toks = _tokens(text)
    hits = []
    seen = set()
    def test(norm, span, kind, table):
        if len(norm) - norm.index(":") - 1 < min_len: return
        h = _h(norm)
        if h in table and norm not in seen:
            seen.add(norm); hits.append({"span": span, "kind": kind, "severity": (_SEV or {}).get(h)})
    for tk in toks:
        test(normalise(tk), tk, "token", _SET)
        # Tamil case suffixes on romanised words (-yai, -oda, -kku, -la, -um): retry the stem when the stem is long enough
        low = tk.lower()
        for suf in ("yai", "oda", "kku", "um"):   # unambiguous case markers only: bare -ai / -ku / -la / -ya cut ordinary words into false stems
            if low.endswith(suf) and len(low) - len(suf) >= 4:
                test(normalise(low[:-len(suf)]), tk, "token_stem", _SET); break
    if _SET2:
        for i in range(len(toks) - 1):
            test(normalise_words((toks[i], toks[i + 1])), toks[i] + " " + toks[i + 1], "bigram", _SET2)
    run = []
    for tk in toks + [""]:
        if len(tk) == 1: run.append(tk)
        else:
            if len(run) >= 3: test(normalise("".join(run)), " ".join(run), "spaced", _SET)
            run = []
    return hits

def fallback_text(lang="ta"):
    return {"ta": "மன்னிக்கவும், அதை நான் சொல்ல முடியாது. வேறு எதிலாவது உதவட்டுமா?",
            "tanglish": "Sorry, adha naan solla mudiyaadhu. Vera edhavadhu help pannattuma?",
            "en": "Sorry, I cannot say that. Can I help with something else?"}.get(lang if lang in ("ta", "tanglish", "en") else "en")

RANK = {"slur": 3, "sexual": 2, "blocked": 2, "profanity": 1, "mild": 0}   # "blocked": terms blocked by ruling that are not offensive language (cow, 2026-09-13)

def build(lexicon_path, out=HASHED):
    if not os.path.exists(SALT_FILE):
        open(SALT_FILE, "w").write(os.urandom(16).hex() + "\n")
    hs1 = set(); hs2 = set(); hs3 = set(); n_entries = 0; sev = {}; skipped3 = 0
    def keep(s, h):
        if RANK.get(s, 0) >= RANK.get(sev.get(h, "mild"), -1): sev[h] = s   # worst severity wins for shared forms
    for l in open(lexicon_path, encoding="utf-8"):
        e = json.loads(l); n_entries += 1
        ctx_only = not e.get("standalone", True)   # context-dependent entries: a separate "3:" set consulted only when the request asks to spell / repeat / translate / explain the word
        s = e.get("severity", "mild")
        for v in [e["term"]] + e.get("variants", []):
            for alt in str(v).split("|"):
                forms = [alt.split()]
                if any(c in alt for c in "-_"):
                    forms = [alt.replace("-", " ").replace("_", " ").split(), [alt.replace("-", "").replace("_", "")]]
                for words in forms:
                    if not words: continue
                    if ctx_only:
                        if all(len(w) == 1 for w in words) and len(words) >= 3: words = ["".join(words)]
                        n = normalise(words[0]) if len(words) == 1 else (normalise_words(words) if len(words) == 2 else None)
                        if n and len(n[n.index(":") + 1:].replace(" ", "")) >= 3: hs3.add(_h(n))
                        continue
                    if all(len(w) == 1 for w in words) and len(words) >= 3:
                        words = ["".join(words)]                       # spaced-out spelling: the joined single word
                    if len(words) == 1:
                        n = normalise(words[0]); body = n[n.index(":") + 1:]
                        if (n.startswith("ta:") and len(body) >= 3) or (n.startswith("rom:") and len(body) >= 4) or (n.startswith("rom:") and len(body) == 3 and s in ("slur", "sexual", "profanity", "blocked")):
                            h = _h(n); hs1.add(h); keep(s, h)
                    elif len(words) == 2:
                        n = normalise_words(words)
                        parts = [p[p.index(":") + 1:] for p in n.split(" ")]
                        if all(len(p) >= 2 for p in parts) or (any(c in alt for c in "-_") and all(len(p) >= 1 for p in parts) and sum(len(p) for p in parts) >= 4):
                            h = _h(n); hs2.add(h); keep(s, h)
                    else:
                        skipped3 += 1
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# family-safe lexicon hashes v3 {time.strftime('%Y-%m-%d')} n1={len(hs1)} n2={len(hs2)} n3={len(hs3)} (1: single word, 2: two words, 3: context-only, repeat/spell/translate requests only)\n")
        for h in sorted(hs1): f.write("1:" + h + "\n")
        for h in sorted(hs2): f.write("2:" + h + "\n")
        for h in sorted(hs3): f.write("3:" + h + "\n")
    sev_out = out.replace(".hashed", ".severity") if out.endswith(".hashed") else SEVERITY
    with open(sev_out, "w", encoding="utf-8") as f:
        f.write(f"# family-safe lexicon severities v2 {time.strftime('%Y-%m-%d')} n={len(sev)} (hash severity; same salt as lexicon.hashed)\n")
        for h in sorted(sev): f.write(f"{h} {sev[h]}\n")
    print(f"wrote {out}: {len(hs1)} single-word + {len(hs2)} two-word hashes from {n_entries} entries ({skipped3} forms of 3+ words skipped); {sev_out}: {len(sev)} severities")

def selftest():
    load()
    # the known-hit terms are lexicon entries, so they live with the private lexicon; without that file only the benign half runs
    kp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "private", "lexicon", "rules", "selftest_known.json")
    known = json.load(open(kp, encoding="utf-8"))["known"] if os.path.exists(kp) else []
    benign = ["வணக்கம், இன்று நான் உங்களுக்கு எப்படி உதவ முடியும்?", "திருக்குறள் 42 என்ன?", "தக்காளி சட்னி செய்வது எப்படி?", "Windows la stuck aana app ah kill panna epdi?", "தீபாவளி பண்டிகை ஏன் கொண்டாடுகிறோம்?",
              "naalai kaalai sandhippom", "enakku Tamil la konjam thaan theriyum", "How does paracetamol work?", "The cat sat on the mat.", "தமிழ் இலக்கியம் மிகவும் பழமையானது", "kovai la mazhai peyudhu", "அகர முதல எழுத்தெல்லாம் ஆதி பகவன் முதற்றே உலகு",
              "pandu vilaiyaadu", "college ku leave letter ezhudhanum", "amma appa thambi", "sandhosham", "punnagai", "kanmani", "Can you translate this to Tamil?", "பாரதியார் பாடல்கள் 155",
              "Who're you?", "who 're you", "Who 're good indeed, on earth begirt by ocean's gruesome tide", "Mr S Mutt wrote the novel", "S mutt", "the class assembles at nine", "cum laude", "a s s e m b l y line"]
    fp = [b for b in benign if check(b)]; fn = [k for k in known if not check(k)]
    print(f"selftest: known hit {len(known)-len(fn)}/{len(known)} (missed {fn}); benign clean {len(benign)-len(fp)}/{len(benign)} (false positives {fp})")
    return not fn and not fp

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--build": build(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--selftest": sys.exit(0 if selftest() else 1)
    else: print(__doc__)
