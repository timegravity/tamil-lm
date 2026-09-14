"""Literature-first matching for serving (Vignesh 2026-09-07): a query that names a KB work,
section, poem title or first line fires literature retrieval before any other routing,
regardless of query length.

match_literature(query, units) -> {"unit": u, "units": [u, ...], "alias": row, "kind": ..., "mode": "exact" | "fuzzy"} | None

Order of attempts:
  1. work + number ("thirukkural 1", "குறள் 42", "kural 7"): exact unit (retrieval.kb.exact_lookup).
  2. exact: normalised query == alias_ta / alias_en / alias_roman.
  3. fuzzy: skeleton equality (retrieval/roman.py), then containment (title contains query, or query
     contains title) with length guards so greetings and fragments cannot hit a first line.
  4. work + keyword ("Bharathiyar kannamma"): a work alias in the query, the rest matched against
     that work's poem titles and first lines.
Manual aliases from data/kb/aliases_manual.jsonl (alias, work_en, number optional) are honoured
when the file exists. No node, no network: the roman side is precomputed in aliases.jsonl.
"""
import json
import os
import re

from .kb import exact_lookup
from .roman import skeleton, normalise_ta, nfc

ALIASES = "data/kb/aliases.jsonl"
MANUAL = "data/kb/aliases_manual.jsonl"
KIND_RANK = {"work": 0, "poem_title": 1, "first_line": 2, "section": 3}
# tie-break between identical section names in different works (கடவுள் வாழ்த்து opens many works)
WORK_PRIORITY = {"Thirukkural": 0, "Bharathiyar Padalgal (Songs of Subramania Bharati)": 1, "Aathichudi": 2, "Konrai Vendhan": 3, "Naaladiyar": 4}
_WHO = ("யார்", "who is", "who was", "yaru", "yaaru", "yaar", "யாரு", "பற்றி", "about")
# literature cue words: a query carrying one of these is a literature request even when the title
# is only a section name or a keyword inside a song title (a chapter name followed by "குறள்", a song keyword followed by "paattu")
_CUES = ("குறள்", "அதிகார", "kural", "adhikaram", "athikaram", "பாட்டு", "பாடல்", "paattu", "pattu", "paatu", "paadal", "padal", "song", "poem", "கவிதை", "செய்யுள்", "வரி", "lines")
_CUE_SECTION = ("அதிகார", "adhikaram", "athikaram", "chapter")
_WORK_NAME_WORDS = {"சிலப்பதிகாரம்", "silappathikaram", "கம்பராமாயணம்", "kambaramayanam", "மணிமேகலை", "manimekalai", "ஆத்திசூடி", "aathichudi", "நாலடியார்", "naaladiyar", "புறநானூறு", "purananuru", "பெரியபுராணம்", "periyapuranam"}
def _has_cue(qn):
    """Word-level cue test: a cue must be a word or its prefix/suffix, and a work name is never a cue
    ("silappathikaram" ends with "athikaram" but names a work)."""
    for w in re.split(r"\s+", qn):
        w = w.strip(".,!?:;\"'()")
        if not w or w in _WORK_NAME_WORDS:
            continue
        if any(w == c or w.startswith(c) or w.endswith(c) for c in _CUES):
            return True
    return False
# creation requests ("write a poem about love") are not lookups: literature fires only when a work,
# section or unit is actually named or quoted
_CREATE = ("எழுது", "எழுதுங்கள்", "எழுதவும்", "எழுதி", "ezhudhu", "ezhudhunga", "ezhuthu", "ezhuthunga", "ezhudhi", "ezhuthi", "write", "compose", "create", "make me", "generate",
           "ஒரு கவிதை", "oru kavithai", "oru kavidhai", "a poem about", "poem about", "story about", "ஒரு கதை", "oru kadhai", "oru kathai", "புதிய", "puthiya", "pudhiya", "new poem", "new song",
           "joke", "riddle", "story for", "a story", "விடுகதை", "vidukadhai", "vidukathai", "நகைச்சுவை", "kadhai sollu", "kathai sollu", "கதை சொல்")
_THEME_WORDS = {"காதல்", "அன்பு", "நட்பு", "இயற்கை", "வாழ்க்கை", "கடவுள்", "தாய்", "நாடு", "மழை", "கடல்", "love", "life", "friendship", "nature", "god", "mother", "rain", "sea", "kadhal", "kaadhal", "anbu", "natpu"}
def is_creation_request(query):
    qn = normalise_ta(query)
    qn = re.sub(r"எழுதி(ய|ன|னார்|யவர்)\S*|ezhu(dh|th)i(ya|na)\S*", " ", qn)   # "written by" forms are lookups, not requests to write
    return any(c in qn for c in _CREATE)
_PROSE_TYPES = ("episode", "author_profile", "chapter", "intro", "summary")
def _lookup_ok(r, units_by_key):
    """Rows usable for keyword/cue matching: verse units only, never tier-3 or intro units, and only short first lines."""
    if str(r.get("tier")) == "3":
        return False
    if r["kind"] == "first_line":
        u = units_by_key.get((r["work_en"], str(r.get("number"))))
        if u is None or str(u.get("number")) in ("0", "None") or str(u.get("unit_type")) in _PROSE_TYPES:
            return False
        if len((r.get("alias_ta") or "").split()) > 10:
            return False
    return True
def _alias_words(r):
    return [skeleton(w) for x in (r.get("alias_ta"), r.get("alias_en"), r.get("alias_roman")) if x
            for w in re.split(r"[\s\-]+", x) if skeleton(w)]
_NUM = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")
_TA = re.compile(r"[஀-௿]")
_STOP_ROMAN = {"the", "a", "of", "song", "songs", "poem", "poems", "by", "in", "from", "about", "pattu", "paattu", "paatu", "padal", "paadal", "sollu", "sollunga", "solu", "explain", "meaning", "quote", "recite", "tell", "me", "please", "full", "complete"}
_STOP_TA = {"பாடல்", "பாட்டு", "சொல்லு", "சொல்லுங்கள்", "சொல்", "கூறு", "எழுது", "விளக்கு", "பொருள்", "முழுவதும்", "தருக", "தா", "பற்றி", "பத்தி", "குறித்து", "ஒரு", "ஒன்று"}
_STOP_ROMAN |= {"about", "pathi", "patthi", "patri", "oru", "onnu", "one", "il", "la", "irundhu", "from"}
_KURAL_NUM = re.compile(r"(thirukkural|thirukural|kural|குறள்|திருக்குறள்)\s*(?:no\.?|number|எண்)?\s*(\d{1,4})", re.I)

# ---- fuzzy literature cues (ruling 2026-09-09) ---------------------------------------------------
# A misspelt cue word or work name is corrected before matching: edit distance 1 in Tamil script,
# 2 in romanised form (1 for short roman words). Only cue words and work names are corrected, never
# generic words (பாட்டு is one edit from பாட்டி, so song cues stay exact). Explicit misspellings live
# in the alias table (data/kb/aliases_manual.jsonl, kind "cue") and are applied first.
_CANON_TA = ("குறள்", "திருக்குறள்", "அதிகாரம்", "பாரதியார்", "சிலப்பதிகாரம்", "ஆத்திசூடி", "கம்பராமாயணம்", "திருவள்ளுவர்")
_CANON_ROMAN = ("kural", "thirukkural", "adhikaram", "bharathiyar", "silappathikaram", "aathichudi", "kambaramayanam", "thiruvalluvar")
_ROMAN_BLOCK = {"rural", "mural", "moral", "plural", "coral", "natural", "kernel", "kerala", "kurta", "koran", "quran", "burial", "aural", "karal",
                "bharat", "bharath", "bharathi", "bharati", "bharatha", "bharatham", "adhikari", "athikari", "adhikar"}
_TA_SUFFIXES = ("ையும்", "ிலும்", "ுக்கு", "ோட", "ில்", "கள்", "ை", "ும்", "ா")
_ROMAN_SUFFIXES = ("galum", "ilum", "kku", "oda", "gal", "kal", "la", "il", "ai", "um", "a", "s")
_TA_SHORT = {"குறள்": "kural", "திருக்குறள்": "thirukkural", "அதிகாரம்": "adhikaram", "பாரதியார்": "bharathiyar", "சிலப்பதிகாரம்": "silappathikaram", "ஆத்திசூடி": "aathichudi", "கம்பராமாயணம்": "kambaramayanam", "திருவள்ளுவர்": "thiruvalluvar"}


def edit_distance(a, b, limit=3):
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _strip_suffix(w, suffixes):
    for s in suffixes:
        if w.endswith(s) and len(w) - len(s) >= 3:
            return w[: -len(s)]
    return w


def _alias_applies(entry, query_norm):
    """An alias row may carry "context": the alias only counts when one of those strings is also in the query
    (குரல் means voice; it is a kural misspelling only next to சொல்லு / பற்றி / a number)."""
    ctx = entry.get("context") if isinstance(entry, dict) else None
    if not ctx:
        return True
    return any((c == "<number>" and re.search(r"\d", query_norm)) or (c != "<number>" and c in query_norm) for c in ctx)


def correct_cue_word(word, cue_aliases=None, query_norm=""):
    """Canonical cue/work name for a (possibly misspelt) word, or None. Tamil: distance <= 1 (words of 4+ code points);
    roman: distance <= 2 for 7+ letters, <= 1 for 5-6 letters; a blocklist keeps real words (rural, moral) out."""
    w = nfc(word).strip().lower().strip(".,!?:;\"'()")
    if not w:
        return None
    if cue_aliases and w in cue_aliases:
        e = cue_aliases[w]
        if _alias_applies(e, query_norm):
            return e["canonical"] if isinstance(e, dict) else e
        return None
    if _TA.search(w):
        if w in _CANON_TA:
            return None   # already canonical
        cands = {w, _strip_suffix(w, _TA_SUFFIXES)}
        for c in cands:
            if len(c) < 4:
                continue
            for canon in _CANON_TA:
                if edit_distance(c, canon, 1) <= 1:
                    return canon
        return None
    if w in _CANON_ROMAN or w in _ROMAN_BLOCK:
        return None
    cands = {w, _strip_suffix(w, _ROMAN_SUFFIXES)}
    for c in cands:
        if len(c) < 5 or c in _ROMAN_BLOCK:
            continue
        lim = 2 if len(c) >= 7 else 1
        for canon in _CANON_ROMAN:
            if edit_distance(c, canon, lim) <= lim:
                return canon
    return None


def correct_cues(query, cue_aliases=None):
    """(corrected_query, [(wrong, canonical), ...]): every misspelt cue word replaced by its canonical form."""
    fixes = []
    out = []
    qn = normalise_ta(query)
    if cue_aliases:   # multi-word aliases first ("kamba ramayanam")
        for a, e in cue_aliases.items():
            if " " in a and a in qn and _alias_applies(e, qn):
                canon = e["canonical"] if isinstance(e, dict) else e
                query = re.sub(re.escape(a), canon, nfc(query), flags=re.I); fixes.append((a, canon))
    for tok in re.split(r"(\s+)", nfc(query)):
        if not tok or tok.isspace():
            out.append(tok); continue
        core = tok.strip(".,!?:;\"'()")
        canon = correct_cue_word(core, cue_aliases, qn) if core else None
        if canon and canon.lower() == core.lower():
            canon = None
        if canon:
            fixes.append((core, canon))
            out.append(tok.replace(core, canon, 1))
        else:
            out.append(tok)
    return "".join(out), fixes


_REQUEST_WORDS = {"explain", "explanation", "meaning", "means", "porul", "vilakku", "vilakkam", "artham", "sollu", "sollunga", "solu", "sol", "quote", "recite", "complete", "full", "tell", "me", "please", "plz", "the", "this", "that", "of", "kural", "thirukkural", "thirukural", "kuralai", "yaar", "yaaru", "yaru", "sonnadhu", "sonnathu", "sonnaru", "sonnar", "who", "said", "wrote", "line", "lines", "vari", "varigal", "padal", "paadal", "song", "poem", "enna", "what", "is", "in", "la", "il",
                  "விளக்கு", "விளக்கம்", "பொருள்", "அர்த்தம்", "எக்ஸ்ப்லைன்", "சொல்லு", "சொல்லுங்கள்", "சொல்", "கூறு", "முழுவதும்", "முழுசா", "குறள்", "திருக்குறள்", "குறளை", "திருக்குறல்", "குறல்",
                  "கதை", "கதையா", "கதையாக", "நீதிக்கதை", "கவிதை", "கதைய", "இந்தக்", "இந்த", "அந்த", "குறளுக்கு", "குறளுக்கான", "குறளை", "பாடலுக்கு", "எழுது", "எழுதுங்கள்", "உதாரணம்", "உதாரணமா",
                  "kathai", "kadhai", "kathaiya", "kadhaiya", "story", "kavithai", "kavidhai", "indha", "intha", "andha", "antha", "kuralukku", "kuraluku", "kuralukkaana", "kural_ukku", "vechu", "vaichu", "vachu", "using", "based", "ezhudhu", "ezhuthu", "example", "யார்", "சொன்னது", "சொன்னார்", "எழுதியது", "வரி", "வரிகள்", "பாடல்", "என்ன", "இது", "அது", "எந்த", "எழுது", "தருக", "தா"}
def _strip_request_words(qn):
    words = [w.strip(".,!?:;\"'()") for w in qn.split()]
    core = [w for w in words if w and w not in _REQUEST_WORDS and not w.isdigit()]
    return " ".join(core)

# A literature TERM must be present: an explain word on its own is not a literature cue (ruling 2026-09-09,
# a science "explain in Tamil" request must never reach a kural).
_LIT_TERMS = ("kural", "thirukkural", "thirukural", "kuralai", "adhikaram", "athikaram", "adhigaram", "thiruvalluvar", "valluvar", "venba", "paadal", "padal", "paattu", "seyyul",
              "குறள்", "திருக்குறள்", "குறளை", "குறளின்", "அதிகாரம்", "அதிகாரத்த", "திருவள்ளுவர்", "வள்ளுவர்", "வெண்பா", "பாடல்", "பாட்டு", "செய்யுள்", "பாரதியார்", "bharathiyar", "silappathikaram", "சிலப்பதிகாரம்", "kambaramayanam", "கம்பராமாயணம்", "aathichudi", "ஆத்திசூடி", "naaladiyar", "நாலடியார்")
def has_literature_term(query):
    qn = normalise_ta(query)
    return any(t in qn for t in _LIT_TERMS)

def has_literature_cue(query):
    """A literature request: a literature term must be present. An explain or meaning word alone is not enough."""
    return has_literature_term(query)

# English and Tanglish theme words -> Tamil chapter vocabulary of the KB (ruling 2026-09-09)
THEME_SYNONYMS = {
 "death": ["நிலையாமை", "சாக்காடு"], "dying": ["நிலையாமை"], "saavu": ["நிலையாமை"], "maranam": ["நிலையாமை"], "சாவு": ["நிலையாமை"], "மரணம்": ["நிலையாமை"], "இறப்பு": ["நிலையாமை"],
 "love": ["அன்புடைமை", "காதல்", "புணர்ச்சி"], "kadhal": ["காதல்", "அன்புடைமை"], "kaadhal": ["காதல்", "அன்புடைமை"], "anbu": ["அன்புடைமை"], "affection": ["அன்புடைமை"], "காதல்": ["காதல்", "அன்புடைமை"], "அன்பு": ["அன்புடைமை"],
 "anger": ["வெகுளாமை"], "kobam": ["வெகுளாமை"], "kovam": ["வெகுளாமை"], "கோபம்": ["வெகுளாமை"], "rage": ["வெகுளாமை"],
 "friendship": ["நட்பு"], "friend": ["நட்பு"], "natpu": ["நட்பு"], "நட்பு": ["நட்பு"], "நண்பர்": ["நட்பு"],
 "learning": ["கல்வி"], "education": ["கல்வி"], "study": ["கல்வி"], "school": ["கல்வி"], "kalvi": ["கல்வி"], "படிப்பு": ["கல்வி"], "கல்வி": ["கல்வி"],
 "wealth": ["பொருள்", "செல்வம்"], "money": ["பொருள்", "செல்வம்"], "rich": ["செல்வம்"], "panam": ["பொருள்"], "porul": ["பொருள்"], "பணம்": ["பொருள்"], "செல்வம்": ["செல்வம்"],
 "truth": ["வாய்மை"], "honesty": ["வாய்மை"], "vaaimai": ["வாய்மை"], "unmai": ["வாய்மை"], "உண்மை": ["வாய்மை"], "வாய்மை": ["வாய்மை"],
 "kindness": ["அருளுடைமை", "ஈகை"], "charity": ["ஈகை"], "giving": ["ஈகை"], "donation": ["ஈகை"], "eegai": ["ஈகை"], "தானம்": ["ஈகை"], "கருணை": ["அருளுடைமை"],
 "patience": ["பொறையுடைமை"], "forgiveness": ["பொறையுடைமை"], "porumai": ["பொறையுடைமை"], "பொறுமை": ["பொறையுடைமை"],
 "effort": ["ஆள்வினையுடைமை", "ஊக்கம்"], "hardwork": ["ஆள்வினையுடைமை"], "work": ["ஆள்வினையுடைமை", "வினை"], "uzhaippu": ["ஆள்வினையுடைமை"], "உழைப்பு": ["ஆள்வினையுடைமை"], "முயற்சி": ["ஆள்வினையுடைமை"],
 "laziness": ["மடி இன்மை"], "somberi": ["மடி இன்மை"], "சோம்பல்": ["மடி இன்மை"],
 "children": ["மக்கட்பேறு"], "child": ["மக்கட்பேறு"], "family": ["மக்கட்பேறு", "இல்வாழ்க்கை"], "kuzhandhai": ["மக்கட்பேறு"], "குழந்தை": ["மக்கட்பேறு"], "பிள்ளை": ["மக்கட்பேறு"],
 "rain": ["வான்சிறப்பு"], "water": ["வான்சிறப்பு"], "mazhai": ["வான்சிறப்பு"], "மழை": ["வான்சிறப்பு"],
 "food": ["மருந்து", "விருந்தோம்பல்"], "medicine": ["மருந்து"], "health": ["மருந்து"], "மருந்து": ["மருந்து"],
 "gratitude": ["செய்ந்நன்றி"], "thanks": ["செய்ந்நன்றி"], "nandri": ["செய்ந்நன்றி"], "நன்றி": ["செய்ந்நன்றி"],
 "humility": ["அடக்கம்", "பணிவு"], "adakkam": ["அடக்கம்"], "அடக்கம்": ["அடக்கம்"], "பணிவு": ["அடக்கம்"],
 "king": ["இறைமாட்சி"], "leader": ["இறைமாட்சி"], "government": ["இறைமாட்சி"], "அரசன்": ["இறைமாட்சி"],
 "time": ["காலம்"], "kaalam": ["காலம்"], "காலம்": ["காலம்"],
 "speech": ["சொல்வன்மை", "பயனில சொல்லாமை"], "words": ["சொல்வன்மை"], "sol": ["சொல்வன்மை"], "பேச்சு": ["சொல்வன்மை"],
 "fear": ["அஞ்சாமை"], "courage": ["படைச்செருக்கு", "அஞ்சாமை"], "தைரியம்": ["அஞ்சாமை"],
 "farming": ["உழவு"], "agriculture": ["உழவு"], "vivasayam": ["உழவு"], "விவசாயம்": ["உழவு"], "உழவு": ["உழவு"],
 "guest": ["விருந்தோம்பல்"], "hospitality": ["விருந்தோம்பல்"], "விருந்து": ["விருந்தோம்பல்"],
 "wine": ["கள்ளுண்ணாமை"], "alcohol": ["கள்ளுண்ணாமை"], "gambling": ["சூது"], "சூது": ["சூது"],
 "thief": ["கள்ளாமை"], "stealing": ["கள்ளாமை"], "திருட்டு": ["கள்ளாமை"],
}
_PRONOUNS = {"avar", "aval", "avan", "avanga", "avargal", "naan", "nee", "neenga", "naama", "namma", "avaru", "ivar", "ivan", "ival", "அவர்", "அவள்", "அவன்", "அவங்க", "அவர்கள்", "இவர்", "இவன்", "இவள்", "நான்", "நீ", "நீங்கள்", "நாம்", "yaru", "yaaru", "yaar", "யார்", "யாரு", "enna", "என்ன", "edhu", "எது", "yen", "ஏன்", "eppo", "எப்போ", "enga", "எங்க"}
_REFER_WORDS = {"that", "this", "it", "adhu", "idhu", "athu", "ithu", "andha", "indha", "antha", "intha", "which", "endha", "entha", "அது", "இது", "அந்த", "இந்த", "எந்த", "same", "above", "previous", "last", "mela", "மேலே", "முந்தைய", "அதே"}
_NON_TITLE_WORDS = _REQUEST_WORDS | _REFER_WORDS | _PRONOUNS | set(_STOP_ROMAN) | set(_STOP_TA)
_KURAL_CUES = ("குறள்", "திருக்குறள்", "kural", "thirukkural", "thirukural", "thiruvalluvar", "திருவள்ளுவர்")
_SONG_CUES = ("பாட்டு", "பாடல்", "paattu", "pattu", "paatu", "paadal", "padal", "song")
_ANY_STOP = set(_STOP_TA) | set(_STOP_ROMAN) | {"ஒரு", "ஒன்று", "one", "a", "an", "the", "some", "any", "me", "please", "தயவுசெய்து", "sollunga", "sollu", "solluga", "sol", "சொல்லுங்க", "சொல்லுங்கள்", "சொல்லு", "சொல்", "கூறு", "கூறுங்கள்", "தா", "தாங்க", "தருக", "கொடு", "give", "tell", "recite", "quote", "share", "வேணும்", "venum", "vendum", "வேண்டும்", "read", "படி", "படிங்க", "random", "எதாவது", "ஏதாவது", "edhavadhu", "ethavathu", "எதுவும்", "any"}


class LitIndex:
    def __init__(self, units, path=ALIASES, manual=MANUAL):
        self.units = units
        self.by_key = {}
        for u in units:
            self.by_key.setdefault((u.get("work_en"), str(u.get("number"))), u)
        self.rows = []
        self.cue_aliases = {}   # explicit misspellings -> canonical cue word (alias table rows with kind "cue")
        if os.path.exists(path):
            for l in open(path, encoding="utf-8"):
                if l.strip():
                    self.rows.append(json.loads(l))
        if os.path.exists(manual):
            for l in open(manual, encoding="utf-8"):
                if l.strip():
                    m = json.loads(l)
                    if m.get("kind") == "cue":
                        self.cue_aliases[normalise_ta(m["alias"])] = {"canonical": m["canonical"], "context": m.get("context")}
                        continue
                    self.rows.append({"alias_ta": m.get("alias") if _TA.search(m.get("alias", "")) else "",
                                      "alias_en": m.get("alias") if not _TA.search(m.get("alias", "")) else "",
                                      "alias_roman": "", "kind": m.get("kind", "poem_title" if m.get("number") is not None else "work"),
                                      "work_en": m.get("work_en"), "number": m.get("number"), "section_key": m.get("section_key"),
                                      "section_value": m.get("section_value"), "tier": m.get("tier", 1), "manual": True})
        for r in self.rows:
            r["_exact"] = {normalise_ta(x) for x in (r.get("alias_ta"), r.get("alias_en"), r.get("alias_roman")) if x}
            r["_skel"] = {skeleton(x) for x in (r.get("alias_ta"), r.get("alias_en"), r.get("alias_roman")) if x}
            r["_skel"] = {s for s in r["_skel"] if s}
        self.works = [r for r in self.rows if r["kind"] == "work"]
        # first-word index (ruling 2026-09-09): romanised openings of every verse unit, matched with a length-scaled edit distance
        self.first = []
        for u in units:
            if str(u.get("unit_type")) in _PROSE_TYPES or str(u.get("tier")) == "3":
                continue
            lines = [l for l in (u.get("text") or []) if l and not l.startswith("ராகம்")]
            if not lines:
                continue
            ws = [w for w in re.split(r"\s+", nfc(lines[0]).strip()) if w]
            if not ws:
                continue
            k1 = skeleton(ws[0]); k2 = skeleton(" ".join(ws[:2])); k3 = skeleton(" ".join(ws[:3]))
            kline = skeleton(lines[0]); kall = skeleton(" ".join(lines[:4]))
            self.first.append((k1, k2, k3, kline, kall, u))

    # ---- helpers -------------------------------------------------------------
    def units_for(self, r):
        """Units a row points at: one unit for poem_title/first_line, all units of the section or work otherwise."""
        if r.get("number") is not None and r["kind"] in ("poem_title", "first_line"):
            u = self.by_key.get((r["work_en"], str(r["number"])))
            return [u] if u else []
        if r["kind"] == "section" and r.get("section_key"):
            k, v = r["section_key"], r.get("section_value")
            out = [u for u in self.units if u.get("work_en") == r["work_en"]
                   and normalise_ta(str((u.get("section") or {}).get(k, ""))) == normalise_ta(str(v))]
            return out
        return [u for u in self.units if u.get("work_en") == r["work_en"]]

    @staticmethod
    def _rank(r, mode):
        return (0 if mode == "exact" else 1, KIND_RANK.get(r["kind"], 9), 0 if str(r.get("tier")) == "1" else 1,
                WORK_PRIORITY.get(r.get("work_en"), 5), len((r.get("alias_ta") or r.get("alias_en") or "")))

    def _result(self, r, mode, unit=None):
        us = self.units_for(r)
        if not us:
            return None
        us = sorted(us, key=lambda u: (str(u.get("unit_type")) == "chapter", _num(u.get("number"))))
        return {"unit": unit or us[0], "units": us[:12], "alias": r, "kind": r["kind"], "mode": mode}

    # ---- main entry ------------------------------------------------------------
    def match(self, query):
        q = nfc(query).strip()
        if not q:
            return None
        q, fixes = correct_cues(q, self.cue_aliases)   # misspelt cue words and work names corrected first (ruling 2026-09-09)
        res = self._match(q)
        if res is None:
            res = self.match_pasted(q)   # a KB unit quoted anywhere in the message, even followed by a request
        qn0 = normalise_ta(q)
        who = any(w in qn0 for w in _WHO)
        if res is None and not who and not is_creation_request(q):
            core = _strip_request_words(qn0)   # "explain <first word of a kural>" -> "<first word of a kural>"
            if core and all(w in _NON_TITLE_WORDS or any(c in w for c in _KURAL_CUES + _SONG_CUES) for w in core.split()):
                core = ""   # only request, cue or pronoun words left: nothing to match by opening words
            if core and core != qn0:
                res = self._match(core)
            # romanised opening words with a length-scaled edit distance: only for multi-word cores, long single words,
            # or when a literature cue is present (a greeting must never be one edit from a first line)
            if res is None and core and (len(core.split()) >= 2 or len(skeleton(core)) >= 10 or has_literature_cue(q)):
                res = self.match_first_words(core)
        if res is None and fixes:
            res = self._any_from_cue(q)   # a corrected cue must still claim the turn (never Wikipedia)
        if res is not None and fixes:
            res["corrected"] = fixes
        return res

    def match_first_words(self, core_query):
        """Verse whose opening words match the (romanised or Tamil) query within an edit distance scaled by length
        (1 per 6 characters, at least 1). Returns a literature result or None."""
        qs = skeleton(core_query)
        if len(qs) < 9:
            return None   # too short to identify an opening line
        lim = max(1, len(qs) // 6)
        best = None
        for k1, k2, k3, _kline, _kall, u in self.first:
            for k in (k1, k2, k3):
                if not k or abs(len(k) - len(qs)) > lim:
                    continue
                d = edit_distance(qs, k, lim)
                if d <= lim:
                    key = (d, WORK_PRIORITY.get(u.get("work_en"), 5), _num(u.get("number")))
                    if best is None or key < best[0]:
                        best = (key, u)
        if best is None:
            return None
        u = best[1]
        return {"unit": u, "units": [u], "alias": None, "kind": "first_line", "mode": "fuzzy_first_words", "distance": best[0][0]}

    def match_pasted(self, q):
        """A KB unit quoted ANYWHERE in the message (ruling 2026-09-09): a pasted kural followed by a request
        ("<kural text>" followed by a request about that kural) matches its unit. The quoted text must be at least
        14 skeleton characters, so an ordinary phrase cannot trigger it; the longest match wins."""
        qs = skeleton(q)
        if len(qs) < 14:
            return None
        best = None
        for _k1, _k2, _k3, kline, kall, u in self.first:
            for key in (kall, kline):
                if len(key) >= 14 and key in qs:
                    if best is None or len(key) > best[0]:
                        best = (len(key), u)
                    break
        if best is None:
            return None
        u = best[1]
        return {"unit": u, "units": [u], "alias": None, "kind": "pasted", "mode": "pasted_text", "matched_chars": best[0]}

    def theme_units(self, work, words):
        """Units of `work` whose adhikaram, English chapter name or themes match the query's theme words.
        A small synonym table maps common English and Tanglish theme words to the Tamil chapter vocabulary."""
        targets_ta, targets_en = [], []
        for w in words:
            w = w.strip(".,!?:;\"'()").lower()
            if not w:
                continue
            syn = THEME_SYNONYMS.get(w)
            if syn:
                targets_ta += syn
            if _TA.search(w):
                targets_ta.append(w)
            elif len(w) >= 4:
                targets_en.append(w)
        strong, weak = [], []
        for u in self.units:
            if u.get("work_en") != work or u.get("adult_theme"):
                continue
            sec = u.get("section") or {}
            ta_fields = [str(sec.get("adhikaram") or ""), str(sec.get("paal") or ""), str(sec.get("iyal") or "")] + [t for t in (u.get("themes") or []) if _TA.search(str(t))]
            en_fields = [str(sec.get("adhikaram_en") or "")] + [str(t) for t in (u.get("themes") or []) if not _TA.search(str(t))]
            if any(t and any(t in f or f in t for f in ta_fields if f) for t in targets_ta):
                strong.append(u)
            elif targets_en and any(t in " ".join(en_fields).lower() for t in targets_en):
                weak.append(u)
        return strong or weak

    def _any_from_cue(self, q):
        """"any kural" / "any song" intent: a literature cue with no unit, number, chapter or theme -> a unit chosen at
        serving time from the whole work (verbatim from the KB). A theme word narrows the pool through the unit themes."""
        qn = normalise_ta(q)
        words = [w.strip(".,!?:;\"'()") for w in qn.split()]
        words = [w for w in words if w]
        if is_creation_request(qn) or any(w in qn for w in ("யார்", "யாரு", "who is", "who was", "yaru", "yaaru", "yaar")):
            return None   # "who wrote this kural" is a lookup about a person, not a request for any kural
        kural = any(any(c in w for c in _KURAL_CUES) for w in words)
        song = (not kural) and any(any(c in w for c in _SONG_CUES) for w in words)
        if not (kural or song):
            return None
        work = "Thirukkural" if kural else "Bharathiyar Padalgal (Songs of Subramania Bharati)"
        cues = _KURAL_CUES if kural else _SONG_CUES
        leftover = [w for w in words if not any(c in w for c in cues) and w not in _ANY_STOP and not w.isdigit()]
        if leftover and all(w in _REFER_WORDS for w in leftover):
            return None   # "explain that kural", "andha kural": refers to something not named -> ask which one
        pool = [u for u in self.units if u.get("work_en") == work and not u.get("adult_theme") and str(u.get("unit_type")) not in _PROSE_TYPES]
        if not pool:
            return None
        if leftover and song:
            return None   # "Roja song": a song cue with other words is ambiguous (film songs); only a bare song cue means a Bharathiyar song
        theme_hit = []
        if leftover and kural:
            fw = self.match_first_words(" ".join(leftover))   # the leftover may be the opening words of a kural ("thirukkural porul ellarkkum nandram")
            if fw and fw["unit"].get("work_en") == work:
                return fw
        if leftover:
            theme_hit = self.theme_units(work, leftover)   # adhikaram names, English chapter names and the synonym table (ruling 2026-09-09)
        if leftover and not theme_hit:
            keys = [skeleton(w) for w in leftover if len(skeleton(w)) >= 3]
            for u in pool:
                th = [skeleton(t) for t in (u.get("themes") or [])] + [skeleton(str(v)) for v in (u.get("section") or {}).values() if isinstance(v, str)]
                if keys and all(any(t.startswith(k) or (len(k) >= 5 and k in t) for t in th) for k in keys):
                    theme_hit.append(u)
        units = theme_hit or pool
        return {"unit": units[0], "units": units, "alias": None, "kind": "any_unit", "mode": "cue", "work_en": work,
                "theme": leftover, "theme_matched": bool(theme_hit)}

    def _match(self, q):
        _ws = [w.strip(".,!?:;\"'()") for w in normalise_ta(q).split()]
        if all(w in _NON_TITLE_WORDS for w in _ws) and not any(any(c in w for c in _KURAL_CUES + _SONG_CUES) for w in _ws):
            return None   # "avar yaru", "explain that": nothing named (a bare kural/song cue still means "any kural")
        # 1. work + number
        m = _KURAL_NUM.search(q)
        if m:
            u = self.by_key.get(("Thirukkural", m.group(2)))
            if u:
                return {"unit": u, "units": [u], "alias": None, "kind": "work_number", "mode": "exact"}
        u = exact_lookup(self.units, q)
        if u is not None:
            return {"unit": u, "units": [u], "alias": None, "kind": "work_number", "mode": "exact"}
        qn = normalise_ta(q)
        qs = skeleton(q)
        # generalised work + number: "Purananuru 1", "நற்றிணை 5", "kurunthogai 12 sollu"
        nm = _NUM.search(qn)
        if nm:
            rest = normalise_ta(_NUM.sub(" ", qn))
            rest_words = [w for w in rest.split() if w not in _STOP_ROMAN and w not in _STOP_TA]
            rest_s = skeleton(" ".join(rest_words))
            for r in self.works:
                if rest_s and (rest in r["_exact"] or rest_s in r["_skel"]):
                    u = self.by_key.get((r["work_en"], nm.group(1)))
                    if u:
                        return {"unit": u, "units": [u], "alias": r, "kind": "work_number", "mode": "exact"}
        who = any(w in qn for w in _WHO)
        creation = is_creation_request(qn)
        single = len(qn.split()) == 1
        if single and qn in _THEME_WORDS:
            return None   # a bare theme word is a topic, not a title
        # "any kural" / "any song": a bare cue with nothing else named (ruling 2026-09-09)
        if not creation and not who:
            any_res = self._any_from_cue(q)
            if any_res and not any_res.get("theme"):
                return any_res
        # 2. exact
        cands = [r for r in self.rows if qn in r["_exact"]]
        if cands:
            r = min(cands, key=lambda r: self._rank(r, "exact"))
            res = self._result(r, "exact")
            if res:
                return res
        # 3. fuzzy: skeleton equality, then containment (a single short word is too lossy: காதல் vs கடல்)
        if len(qs) >= (7 if single else 4):
            cands = [r for r in self.rows if qs in r["_skel"]]
            if cands:
                r = min(cands, key=lambda r: self._rank(r, "fuzzy"))
                res = self._result(r, "fuzzy")
                if res:
                    return res
        words = [w for w in re.split(r"\s+", qn) if w]
        kural_cue = any(any(c in w for c in _KURAL_CUES) for w in words)   # a kural cue confines every later path to the Thirukkural
        rows_in_scope = [r for r in self.rows if r.get("work_en") == "Thirukkural"] if kural_cue else self.rows
        if kural_cue and not creation:   # a known theme word ("மழை பற்றி ஒரு குறள்", "death pathi oru kural") goes to the chapter lookup first
            lw = [w.strip(".,!?:;\"'()") for w in words if w not in _ANY_STOP and not any(c in w for c in _KURAL_CUES)]
            if any(w.lower() in THEME_SYNONYMS for w in lw):
                themed = self._any_from_cue(q)
                if themed and themed.get("theme_matched"):
                    return themed
        # cue-word path: section/adhikaram names and title keywords across all works (never for creation requests)
        if _has_cue(qn) and not creation:
            key_words = [w for w in words if not any(c in w for c in _CUES) and w not in _STOP_ROMAN and w not in _STOP_TA
                         and w not in ("ஒரு", "ஒன்று", "one", "a", "the", "from", "in", "il", "la", "irundhu", "இருந்து", "சொல்லு", "சொல்", "கூறு", "தா")]
            key_s = [skeleton(w) for w in key_words if len(skeleton(w)) >= 4]
            if key_s:
                want_section = any(c in qn for c in _CUE_SECTION) or kural_cue   # a theme word with a kural cue means the adhikaram, not a first line
                kinds = ("section", "poem_title", "first_line") if want_section else ("poem_title", "first_line", "section")
                cands = []
                for r in rows_in_scope:
                    if r["kind"] not in kinds or not _lookup_ok(r, self.by_key):
                        continue
                    aw = _alias_words(r)
                    if aw and all(any(a.startswith(k) or (len(k) >= 5 and k in a and a.index(k) <= 1) for a in aw) for k in key_s):
                        cands.append(r)
                if cands:
                    order = {k: i for i, k in enumerate(kinds)}
                    r = min(cands, key=lambda r: (order.get(r["kind"], 9), 0 if str(r.get("tier")) == "1" else 1,
                                                  WORK_PRIORITY.get(r.get("work_en"), 5), _num(r.get("number"))))
                    res = self._result(r, "fuzzy")
                    if res:
                        # gather the whole keyword group (e.g. all Kannamma songs) into units
                        extra = []
                        for c in sorted(cands, key=lambda c: (order.get(c["kind"], 9), _num(c.get("number"))))[:12]:
                            extra += self.units_for(c)
                        seen = set(); merged = []
                        for u in res["units"] + extra:
                            if id(u) not in seen:
                                seen.add(id(u)); merged.append(u)
                        res["units"] = merged[:12]
                        return res
        if kural_cue and not creation and not any(w in qn for w in ("யார்", "யாரு", "who is", "who was", "yaru", "yaaru", "yaar")):
            return self._any_from_cue(q)   # theme without a matching adhikaram: still a kural, never Wikipedia
        if len(qs) >= 6:
            # title contains the query: only for multi-word or long queries, never a bare greeting
            if (len(words) >= 2 or len(qs) >= 10) and not creation:
                ratio = 3.0 if len(words) >= 3 else 1.43   # a short query must cover at least 70% of the line; three or more words may cover a third
                cands = [r for r in self.rows if r["kind"] in ("poem_title", "first_line", "section", "work") and _lookup_ok(r, self.by_key)
                         and any(qs in s and len(s) <= ratio * len(qs) and len(qs) >= 8 for s in r["_skel"])]
                if cands:
                    r = min(cands, key=lambda r: self._rank(r, "fuzzy"))
                    res = self._result(r, "fuzzy")
                    if res:
                        return res
            # query contains a title: works and poem titles only, title skeleton at least 6 chars
            cands = [r for r in self.rows if r["kind"] in ("work", "poem_title")
                     and any(len(s) >= 6 and s in qs for s in r["_skel"])]
            if cands:
                r = min(cands, key=lambda r: (KIND_RANK.get(r["kind"], 9), -max(len(s) for s in r["_skel"] if s in qs)))
                # 4. work + keyword: refine inside the work with the leftover words
                if r["kind"] == "work":
                    refined = self._refine_in_work(r, words)
                    if refined:
                        return refined
                    if who:
                        return None   # "who is Bharathiyar" is about the poet: Wikipedia, not the poems
                res = self._result(r, "fuzzy")
                if res:
                    return res
        # a kural/song cue with a theme that matched no section or title still claims the turn (never Wikipedia)
        if not creation and not who:
            return self._any_from_cue(q)
        return None

    def _refine_in_work(self, work_row, words):
        work_skels = work_row["_skel"]
        rest = [w for w in words if w not in _STOP_ROMAN and w not in _STOP_TA
                and not any(skeleton(w) and (skeleton(w) in s or s in skeleton(w)) for s in work_skels)]
        rest = [w for w in rest if len(skeleton(w)) >= 4]
        if not rest:
            return None
        cands = []
        rest_s = [skeleton(w) for w in rest]
        for r in self.rows:
            if r["work_en"] != work_row["work_en"] or r["kind"] not in ("poem_title", "first_line", "section"):
                continue
            # match per alias WORD (skeleton of each word starts with the query word), never across a
            # word boundary: "vaazhka thilakan naamam" must not match "kannamma"
            alias_words = [skeleton(w) for x in (r.get("alias_ta"), r.get("alias_en"), r.get("alias_roman")) if x
                           for w in re.split(r"[\s\-]+", x) if skeleton(w)]
            if all(any(aw.startswith(ws) or (len(ws) >= 5 and ws in aw and aw.index(ws) <= 1) for aw in alias_words) for ws in rest_s):
                cands.append(r)
        if not cands:
            return None
        cands.sort(key=lambda r: (KIND_RANK.get(r["kind"], 9), _num(r.get("number"))))
        r = cands[0]
        res = self._result(r, "fuzzy")
        if res:
            others = []
            for c in cands[1:12]:
                others += self.units_for(c)
            res["units"] = (res["units"] + [u for u in others if u not in res["units"]])[:12]
        return res


def _num(x):
    try:
        return float(str(x).split("/")[-1])
    except Exception:
        return 1e9


_INDEX = None


def match_literature(query, units=None):
    global _INDEX
    if _INDEX is None:
        from .kb import load_units
        _INDEX = LitIndex(units or load_units())
    return _INDEX.match(query)
