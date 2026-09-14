"""Reverse transliteration (Tamil script -> roman) and a tolerant skeleton normaliser.

to_roman follows the conventions of ui/README.md (the typing side): aa/ii/uu for long
vowels, E/O for ஏ/ஓ, zh for ழ, L for ள, N for ண, R for ற, th for த, t for ட, ng for ங்க,
nj for ஞ்ச, ndr for ன்ற, RR for ற்ற, grantha j/sh/S/h, q for ஃ. skeleton collapses the
spelling choices a typist makes (long vs short vowels, doubled letters, dental vs
retroflex, l/L/zh, r/R, s/sh/ch, v/w, b/p, g/k, d/t, dh/th) so that a roman query and a
KB title agree when they are the same word spelled differently. Word-final sandhi
consonants (a doubled sandhi consonant before the next word) collapse too, because spaces are dropped
and doubled letters are merged.
"""
import re
import unicodedata

VOWELS = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu", "எ": "e", "ஏ": "E",
          "ஐ": "ai", "ஒ": "o", "ஓ": "O", "ஔ": "au"}
SIGNS = {"ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu", "ெ": "e", "ே": "E", "ை": "ai",
         "ொ": "o", "ோ": "O", "ௌ": "au"}
CONS = {"க": "k", "ங": "ng", "ச": "ch", "ஞ": "nj", "ட": "t", "ண": "N", "த": "th", "ந": "n",
        "ப": "p", "ம": "m", "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "zh", "ள": "L",
        "ற": "R", "ன": "n", "ஜ": "j", "ஷ": "sh", "ஸ": "S", "ஹ": "h", "க்ஷ": "ksh"}
PULLI = "்"
AYTHAM = "ஃ"


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def to_roman(text):
    """Tamil script -> roman per ui/README.md conventions. Non-Tamil characters pass through."""
    s = nfc(text)
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in VOWELS:
            out.append(VOWELS[ch]); i += 1; continue
        if ch == AYTHAM:
            out.append("q"); i += 1; continue
        if ch in CONS:
            base = CONS[ch]
            nxt = s[i + 1] if i + 1 < n else ""
            # cluster rules that mirror the forward transliterator
            if nxt == PULLI:
                nn = s[i + 2] if i + 2 < n else ""
                if ch == "ங" and nn == "க":
                    out.append("ng"); i += 3
                    # the க after ங் keeps its own vowel sign, handled by the next loop step
                    # (we emit the consonant part as nothing: ng already covers it)
                    nn2 = s[i] if i < n else ""
                    if nn2 in SIGNS:
                        out.append(SIGNS[nn2]); i += 1
                    elif nn2 == PULLI:
                        i += 1
                    else:
                        out.append("a")
                    continue
                if ch == "ஞ" and nn == "ச":
                    out.append("nj"); i += 3
                    nn2 = s[i] if i < n else ""
                    if nn2 in SIGNS:
                        out.append(SIGNS[nn2]); i += 1
                    elif nn2 == PULLI:
                        i += 1
                    else:
                        out.append("a")
                    continue
                if ch == "ன" and nn == "ற":
                    out.append("ndr"); i += 3
                    nn2 = s[i] if i < n else ""
                    if nn2 in SIGNS:
                        out.append(SIGNS[nn2]); i += 1
                    elif nn2 == PULLI:
                        i += 1
                    else:
                        out.append("a")
                    continue
                if ch == "ற" and nn == "ற":
                    out.append("RR"); i += 3
                    nn2 = s[i] if i < n else ""
                    if nn2 in SIGNS:
                        out.append(SIGNS[nn2]); i += 1
                    elif nn2 == PULLI:
                        i += 1
                    else:
                        out.append("a")
                    continue
                out.append(base); i += 2; continue
            if nxt in SIGNS:
                out.append(base + SIGNS[nxt]); i += 2; continue
            out.append(base + "a"); i += 1; continue
        if ch in SIGNS or ch == PULLI:
            i += 1; continue   # stray sign: skip
        out.append(ch); i += 1
    return "".join(out)


_TA = re.compile(r"[஀-௿]")
_MULTI = [("ksh", "ks"), ("sh", "s"), ("ch", "s"), ("zh", "l"), ("th", "t"), ("dh", "t"), ("ttr", "r"), ("ndr", "nr")]
_SINGLE = {"w": "v", "b": "p", "g": "k", "d": "t", "c": "s", "j": "j"}
_VOWEL = [("aa", "a"), ("ii", "i"), ("ee", "i"), ("uu", "u"), ("oo", "u")]


def skeleton(text):
    """Tolerant key for matching a roman or Tamil string against KB titles."""
    s = nfc(text)
    if _TA.search(s):
        s = to_roman(s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)      # punctuation, spaces, apostrophes gone
    for a, b in _MULTI:
        s = s.replace(a, b)
    s = "".join(_SINGLE.get(c, c) for c in s)
    for a, b in _VOWEL:
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)       # doubled letters (kk, tt, pp, nn, and sandhi pairs across the dropped space)
    return s


def normalise_ta(text):
    """Exact-match key for Tamil or roman titles: NFC, trimmed, trailing punctuation removed, lowercase, single spaces."""
    s = nfc(text).strip().lower()
    s = re.sub(r"[\.\!\?\,\:\;\"'\(\)\[\]]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s
