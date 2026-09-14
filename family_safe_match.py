"""Conservative document-level lexicon matcher shared by the SFT scan and prepare.py.
Rules (Vignesh 2026-09-08): a single-token entry matches only a whole token; a two-word entry matches only
a whole word bigram; no concatenation across word boundaries. Uses family_safe.check when that module
carries the token-boundary fix (attribute TOKEN_BOUNDARY_FIX); otherwise the local matcher below, which
reads the reviewed plain-text lexicon (private, never shipped) and applies family_safe.normalise."""
import json, os, re
import family_safe as FS

LEXICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "private", "lexicon", "lexicon.jsonl")
_ONE = None; _TWO = None; _SEV = {}

def _load():
    global _ONE, _TWO, _SEV
    _ONE, _TWO, _SEV = {}, {}, {}
    if not os.path.exists(LEXICON):
        return
    for l in open(LEXICON, encoding="utf-8"):
        e = json.loads(l)
        if not e.get("standalone", True):
            continue
        term_words = len(FS._tokens(e["term"]))
        forms = [e["term"]] + list(e.get("variants") or [])
        for f in forms:
            toks = FS._tokens(f)
            if not toks:
                continue
            if len(toks) == 1 and term_words == 1:
                n = FS.normalise(toks[0])
                if len(n) - 3 >= 3: _ONE[n] = e["severity"]
            elif len(toks) == 2 and term_words == 2:   # bigram forms only for entries that are themselves two words
                n = FS.normalise(toks[0]) + "|" + FS.normalise(toks[1])
                _TWO[n] = e["severity"]
            # spaced/punctuated variants with 3+ single-letter pieces are covered by the joined form of the base term

def match(text):
    """Return list of {span, kind, severity}; empty when FAMILY_SAFE=0."""
    if not FS.is_enabled():
        return []
    if getattr(FS, "TOKEN_BOUNDARY_FIX", False):
        return FS.check(text)
    if _ONE is None:
        _load()
    toks = FS._tokens(text)
    hits, seen = [], set()
    for t in toks:
        n = FS.normalise(t)
        if n in _ONE and n not in seen:
            seen.add(n); hits.append({"span": t, "kind": "token", "severity": _ONE[n]})
    for i in range(len(toks) - 1):
        n = FS.normalise(toks[i]) + "|" + FS.normalise(toks[i + 1])
        if n in _TWO and n not in seen:
            seen.add(n); hits.append({"span": toks[i] + " " + toks[i + 1], "kind": "bigram", "severity": _TWO[n]})
    return hits

def density(text):
    """Lexicon hits per 1,000 tokens (all occurrences, not deduplicated)."""
    if _ONE is None:
        _load()
    toks = FS._tokens(text)
    if not toks:
        return 0.0, 0
    n_hits = sum(1 for t in toks if FS.normalise(t) in _ONE)
    n_hits += sum(1 for i in range(len(toks) - 1) if FS.normalise(toks[i]) + "|" + FS.normalise(toks[i + 1]) in _TWO)
    return 1000.0 * n_hits / len(toks), len(toks)

def entry_counts():
    if _ONE is None:
        _load()
    return len(_ONE), len(_TWO)
