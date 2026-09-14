"""Audit and fix the entity matching of the nature pack (data/packs/nature).

  .venv/bin/python audit_pack_nature.py            # audit, fix, rewrite the pack files, write AUDIT.md
  .venv/bin/python audit_pack_nature.py --dry-run  # audit only, print what would change
  .venv/bin/python audit_pack_nature.py --no-fetch # use the cache only, never call an API

The first build (build_pack_nature.py) read the English and scientific names out of the Tamil article's own
lead and picked the coverage-list articles by an offline score. Both steps mis-fire: a bracketed word in
the lead is not always the English name, a Latin-looking pair of words is not always a binomial, and an
offline score can pick an article about a different species, or about a chemical, a drink or a piece of
software. This pass makes the English Wikipedia interlanguage link the authoritative name index:

  1. ta.wikipedia prop=langlinks (lllang=en) plus prop=pageprops (wikibase_item), 50 titles a request, for
     every entity's source article. The English title says what the article is about.
  2. Wikidata wbgetentities, 50 items a request: taxon name (P225), instance-of (P31), English label,
     English aliases and the one-line description. P225 verifies or corrects the scientific name; P31 and
     the description catch articles that are not about a living thing.
  3. en.wikipedia prop=langlinks (lllang=ta) with redirects followed, for the 278 coverage-list species: the
     canonical English article of each seed and the Tamil article it links to.
  4. ta.wikipedia list=search on the quoted scientific name for a seed the links do not resolve; a hit is
     accepted only when its own Wikidata taxon name or English link is the seed's.
  5. en.wikipedia prop=extracts (intro only, 20 a request) for the few entities whose scientific name
     neither Wikidata nor the Tamil lead gives; the binomial is read and the text is discarded.

Every request carries the User-Agent tamil-lm-research (contact@timegravity.ai) and is spaced to stay under
two a second (the builder's api_post and CK.api). Responses are cached under AUDIT_CACHE (default: the
session scratchpad), so a rerun costs no requests.

Never invents a Tamil name: name_ta is the article title (or the title without its bracketed qualifier),
exactly as the builder set it. CPU only: no model, no embeddings, no torch.
"""
import argparse, json, os, re, sys
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build_pack_nature as N
import build_pack_cooking as CK
import family_safe as FS

PACK = N.PACK
SCRATCH = os.environ.get("AUDIT_SCRATCH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "packs", "nature", "audit_scratch")   # a local cache folder
CACHE = os.environ.get("AUDIT_CACHE") or os.path.join(SCRATCH, "audit_cache")
BUILD_CACHE = N.CACHE                                    # data/raw/packs/nature, the builder's own cache
VERSION = "2026-09-09"
SEEDS = N.SEEDS

# ------------------------------------------------------------------ romanisation via retrieval/roman.py

def _load_roman():
    """retrieval/roman.py loaded by file path, so retrieval/__init__ is never imported."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nature_roman", os.path.join(ROOT, "retrieval", "roman.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.to_roman

try:
    to_roman = _load_roman()
except Exception as exc:                                  # noqa: BLE001
    print("retrieval/roman.py not importable (%s); only the builder's romaniser is used" % exc)
    to_roman = None

# ------------------------------------------------------------------ cached fetch layer

def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)

def _load(name, default):
    p = _cache_path(name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default

def _save(name, d):
    json.dump(d, open(_cache_path(name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def _chain(q):
    chain = {}
    for m in q.get("normalized", []) + q.get("redirects", []):
        chain[m["from"]] = m["to"]
    return chain

def _final(t, chain):
    cur, seen = t, set()
    while cur in chain and cur not in seen:
        seen.add(cur); cur = chain[cur]
    return cur

REQUESTS = Counter()

def ta_langlinks(titles, no_fetch=False):
    """{Tamil title: {"en": English title or None, "qid": Wikidata id or None, "final": page title}}."""
    d = _load("ta_langlinks.json", {})
    todo = [t for t in dict.fromkeys(titles) if t and t not in d]
    if todo and not no_fetch:
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            r = N.api_post({"action": "query", "titles": "|".join(batch), "prop": "langlinks|pageprops",
                            "lllang": "en", "lllimit": "max", "ppprop": "wikibase_item", "redirects": "1"})
            REQUESTS["ta.wikipedia langlinks"] += 1
            q = r.get("query", {})
            chain = _chain(q)
            pages = {pg["title"]: pg for pg in q.get("pages", {}).values()}
            for t in batch:
                pg = pages.get(_final(t, chain))
                if not pg or "missing" in pg:
                    d[t] = {"en": None, "qid": None, "final": None, "missing": True}
                    continue
                lls = pg.get("langlinks", [])
                d[t] = {"en": (lls[0].get("*") or lls[0].get("title")) if lls else None,
                        "qid": pg.get("pageprops", {}).get("wikibase_item"),
                        "final": pg["title"], "missing": False}
            _save("ta_langlinks.json", d)
    return {t: d.get(t, {"en": None, "qid": None, "final": None, "missing": None}) for t in titles if t}

def _claim_vals(c, prop):
    out = []
    for x in c.get(prop, []):
        v = x.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            out.append(v["id"])
        elif isinstance(v, str):
            out.append(v)
    return out

EMPTY_WD = {"sci": None, "p31": [], "rank": None, "label_en": None, "label_ta": None, "desc_en": None, "aliases_en": []}

def wikidata(qids, no_fetch=False):
    d = _load("wikidata.json", {})
    todo = [q for q in dict.fromkeys(q for q in qids if q) if q not in d]
    if todo and not no_fetch:
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            r = N.api_post({"action": "wbgetentities", "ids": "|".join(batch),
                            "props": "claims|labels|aliases|descriptions", "languages": "en|ta"},
                           host="www.wikidata.org")
            REQUESTS["wikidata wbgetentities"] += 1
            for q, e in r.get("entities", {}).items():
                c = e.get("claims", {})
                d[q] = {"sci": (_claim_vals(c, "P225") or [None])[0],
                        "p31": _claim_vals(c, "P31"),
                        "rank": (_claim_vals(c, "P105") or [None])[0],
                        "label_en": e.get("labels", {}).get("en", {}).get("value"),
                        "label_ta": e.get("labels", {}).get("ta", {}).get("value"),
                        "desc_en": e.get("descriptions", {}).get("en", {}).get("value"),
                        "aliases_en": [a["value"] for a in e.get("aliases", {}).get("en", [])][:12]}
            for q in batch:
                d.setdefault(q, dict(EMPTY_WD))
            _save("wikidata.json", d)
    return {q: (d.get(q) or dict(EMPTY_WD)) for q in qids if q}

def en_resolve(titles, no_fetch=False):
    """{English title: {"canonical": title after redirects, "ta": Tamil interlanguage link or None}}."""
    d = _load("en_resolve.json", {})
    todo = [t for t in dict.fromkeys(titles) if t not in d]
    if todo and not no_fetch:
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            r = N.api_post({"action": "query", "titles": "|".join(batch), "prop": "langlinks",
                            "lllang": "ta", "lllimit": "max", "redirects": "1"}, host="en.wikipedia.org")
            REQUESTS["en.wikipedia langlinks"] += 1
            q = r.get("query", {})
            chain = _chain(q)
            pages = {pg["title"]: pg for pg in q.get("pages", {}).values()}
            for t in batch:
                pg = pages.get(_final(t, chain))
                if not pg or "missing" in pg:
                    d[t] = {"canonical": None, "ta": None}
                    continue
                lls = pg.get("langlinks", [])
                d[t] = {"canonical": pg["title"], "ta": (lls[0].get("*") or lls[0].get("title")) if lls else None}
            _save("en_resolve.json", d)
    return {t: d.get(t, {"canonical": None, "ta": None}) for t in titles}

def en_extracts(titles, no_fetch=False):
    """Intro text of English articles, 20 a request, read only for a scientific name."""
    d = _load("en_extracts.json", {})
    todo = [t for t in dict.fromkeys(titles) if t not in d]
    if todo and not no_fetch:
        for i in range(0, len(todo), 20):
            batch = todo[i:i + 20]
            r = N.api_post({"action": "query", "titles": "|".join(batch), "prop": "extracts", "exintro": "1",
                            "explaintext": "1", "exlimit": "20", "redirects": "1"}, host="en.wikipedia.org")
            REQUESTS["en.wikipedia extracts"] += 1
            q = r.get("query", {})
            chain = _chain(q)
            pages = {pg["title"]: pg for pg in q.get("pages", {}).values()}
            for t in batch:
                pg = pages.get(_final(t, chain))
                d[t] = (pg or {}).get("extract", "") or ""
            _save("en_extracts.json", d)
    return {t: d.get(t, "") for t in titles}

def ta_search(terms, no_fetch=False):
    d = _load("ta_search.json", {})
    for term in terms:
        if term in d or no_fetch:
            continue
        d[term] = N.api_search('"%s"' % term, limit=5)
        REQUESTS["ta.wikipedia search"] += 1
        _save("ta_search.json", d)
    return {t: d.get(t, []) for t in terms}

# ------------------------------------------------------------------ what is the article about

TAXON_CLASSES = {"Q16521", "Q310890", "Q713623", "Q23038290", "Q47487597", "Q19851232", "Q2568288",
                 "Q6884670", "Q16887380", "Q7432", "Q34740", "Q35409", "Q36602", "Q37517", "Q68947",
                 "Q10861678", "Q41825", "Q57451", "Q767728"}
ORGANISM_LIKE = {"Q55983715", "Q4886", "Q39614", "Q1153785", "Q3181348", "Q11004", "Q3314483", "Q1364",
                 "Q25403900", "Q756", "Q42295", "Q17361902", "Q207123", "Q28107", "Q11002", "Q46255",
                 "Q16038001", "Q5090", "Q2225641", "Q30017383", "Q26529", "Q8063", "Q10884", "Q506",
                 "Q19088", "Q7860", "Q136772238", "Q58051350", "Q136343650", "Q133305909", "Q140646522",
                 "Q502895", "Q15731356", "Q2118683", "Q29957571", "Q31839438", "Q140358161", "Q21484471",
                 "Q5113", "Q281721", "Q5368822"}
NOT_ORGANISM = {
    "Q5": "person", "Q11424": "film", "Q532": "village", "Q486972": "human settlement", "Q515": "city",
    "Q7366": "song", "Q482994": "album", "Q571": "book", "Q8261": "novel", "Q5398426": "television series",
    "Q4830453": "business", "Q43229": "organisation", "Q29300714": "organisation", "Q44539": "temple",
    "Q3918": "university", "Q1656682": "event", "Q41710": "ethnic group", "Q4167410": "disambiguation page",
    "Q13442814": "scholarly article", "Q7889": "video game", "Q8502": "mountain", "Q4022": "river",
    "Q23397": "lake", "Q34770": "language", "Q11862829": "academic discipline", "Q12136": "disease",
    "Q7278": "political party", "Q6256": "country", "Q3957": "town", "Q47461344": "written work",
    "Q7725634": "literary work", "Q1371849": "temple", "Q23413": "castle", "Q4989906": "monument",
    "Q839954": "archaeological site", "Q2221906": "geographic location", "Q13226383": "facility",
    "Q16970": "church", "Q9174": "religion", "Q101352": "family name", "Q202444": "given name",
    "Q1190554": "occurrence", "Q132241": "festival", "Q35127": "website", "Q11446": "ship",
    "Q2424752": "product", "Q431289": "brand", "Q7397": "software", "Q17155032": "software",
    "Q17537576": "creative work", "Q3305213": "painting", "Q838948": "work of art",
    "Q95074": "fictional character", "Q22988604": "mythological figure", "Q178885": "deity",
    "Q11173": "chemical compound", "Q113145171": "chemical compound", "Q47154513": "class of chemical compounds",
    "Q79529": "chemical substance", "Q407595": "metabolite", "Q12140": "medication",
    "Q28885102": "pharmaceutical product", "Q40050": "drink", "Q427626": "taxonomic rank",
    "Q4389865": "taxonomic rank", "Q1138178": "classification system", "Q2355817": "plant life-cycle term",
    "Q20056177": "egg", "Q13406463": "list article", "Q4167836": "category", "Q811534": "individual tree",
    "Q1099": "musical instrument", "Q112085": "medical procedure", "Q2668072": "collection",
    "Q1004": "comics", "Q7187": "gene", "Q8054": "protein", "Q3184121": "cemetery",
}
FOOD_CLASSES = {"Q2095", "Q19861951", "Q746549", "Q57657878", "Q1778821"}
SOFT_CLASSES = {"Q12140", "Q28885102", "Q2095", "Q19861951"}
DESC_NOT_ORGANISM = re.compile(
    r"\b(chemical|compound|software|organi[sz]ation|association|classification|taxonomic rank|rank in|"
    r"drink|beverage|infusion|sugar\b|liquid|term for|botanical term|individual (?:tree|plant|banyan)|"
    r"incarcerate|scales of|facility|line of silk|physiological|disorder|Wikimedia|list of|journal|"
    r"magazine|company|institute|university|festival|ritual|technique|method|concept|process|theory|"
    r"study of|branch of|field of|film|village|town|city|district|politician|actor|singer|writer|poet|"
    r"novel|song|album|temple|deity|language|river|mountain|lake|award|dynasty|caste|surname|given name)\b",
    re.I)
EN_LIST = re.compile(r"^(?:List of|Lists of|Butterflies of|Birds of|Flora of|Fauna of|Mammals of|Fishes of|"
                     r"Reptiles of|Trees of|Plants of|Amphibians of|Insects of)\b")
TA_NOT_ORGANISM = re.compile(r"பட்டியல்|கட்டுப்பாடு|இடர்பாடு|குடிநீர்|தேநீர்|மையம்|சங்கம்|செதில்கள்|சர்க்கரை|"
                             r"விளையாட்டு|உணவு$|வகைப்பாடு$")

def subject_of(ll, wd, kind, title, desc_ta):
    """('taxon' | 'organism_like' | 'not_organism' | 'unknown', label)."""
    en = (ll or {}).get("en")
    if en and EN_LIST.search(en):
        return "not_organism", "list article"
    if TA_NOT_ORGANISM.search(title):
        return "not_organism", "not an organism by title (%s)" % title
    if desc_ta.startswith("="):
        return "not_organism", "broken stub"
    if not wd:
        return "unknown", None
    p31 = set(wd.get("p31") or [])
    if wd.get("sci") or (p31 & TAXON_CLASSES):
        return "taxon", "taxon"
    desc = wd.get("desc_en") or ""
    # a medication or a food whose description names a plant or animal part (ginseng: "root of plants in
    # the genus Panax") is a living thing for this pack; a chemical, a drink or a piece of software is not
    soft = p31 & SOFT_CLASSES
    hard = [NOT_ORGANISM[q] for q in p31 if q in NOT_ORGANISM and q not in SOFT_CLASSES]
    if hard:
        return "not_organism", hard[0]
    if soft:
        if kind_family_from_desc(desc) == "p" and not DESC_NOT_ORGANISM.search(desc):
            return "organism_like", desc
        return "not_organism", NOT_ORGANISM.get(next(iter(soft)), "food")
    if any(q in FOOD_CLASSES for q in p31) and kind not in ("fruit", "vegetable", "plant"):
        return "not_organism", "food"
    if p31 & ORGANISM_LIKE and not DESC_NOT_ORGANISM.search(desc):
        return "organism_like", desc
    m = DESC_NOT_ORGANISM.search(desc)
    if m:
        return "not_organism", "%s (%s)" % (m.group(1).lower(), desc)
    if kind_family_from_desc(desc) or p31 & ORGANISM_LIKE:
        return "organism_like", desc
    return "unknown", desc or None

KIND_WORDS = [
    ("bird",   re.compile(r"\b(bird|birds|passerine|raptor|owl|owls|duck|ducks|parrot|parrots|pigeon|pigeons|dove|"
                          r"doves|eagle|eagles|hawk|hawks|vulture|vultures|heron|herons|stork|storks)\b", re.I)),
    ("insect", re.compile(r"\b(insect|insects|butterfly|butterflies|moth|moths|beetle|beetles|ant|ants|bee|bees|"
                          r"wasp|wasps|fly|flies|dragonfly|damselfly|bug|bugs|cricket|grasshopper|termite|"
                          r"cockroach|mosquito|spider|spiders|scorpion|arachnid|mantis|cicada|weevil|hemiptera|"
                          r"lepidoptera|coleoptera|hymenoptera|diptera|odonata|orthoptera|arthropod|caterpillar|larvae)\b", re.I)),
    ("animal", re.compile(r"\b(mammal|mammals|reptile|reptiles|snake|snakes|lizard|lizards|frog|frogs|toad|toads|"
                          r"amphibian|amphibians|fish|fishes|turtle|tortoise|crocodile|rodent|rodents|bat|bats|"
                          r"primate|primates|marsupial|carnivore|ungulate|antelope|deer|monkey|shark|crab|crabs|"
                          r"shrimp|prawn|mollusc|mollusk|snail|snails|worm|worms|cetacean|dolphin|whale|gecko|"
                          r"skink|agamid|viper|cobra|loach|catfish|carp|cichlid|goby|eel|animal|animals|canid|"
                          r"herbivores|hybrid)\b", re.I)),
    ("p",      re.compile(r"\b(plant|plants|tree|trees|shrub|shrubs|herb|herbs|grass|grasses|vine|vines|"
                          r"flowering plant|flowering plants|fern|ferns|moss|mosses|palm|palms|orchid|orchids|"
                          r"legume|legumes|fruit|fruits|vegetable|vegetables|cultivar|cereal|crop|crops|"
                          r"seaweed|alga|algae|fungus|fungi|mushroom|mushrooms|lichen|lichens|cactus|cacti|"
                          r"succulent|bamboo|flower|flowers|spice|seed|seeds|nut|nuts|bean|beans|gourd|"
                          r"melon|berry|berries|tuber|root|leaf|leaves|wood|grain)\b", re.I)),
]
PLANT_KINDS = {"tree", "plant", "flower", "fruit", "vegetable"}

def family_of(kind):
    return "p" if kind in PLANT_KINDS else kind

def kind_family_from_desc(desc):
    if not desc:
        return None
    for k, rx in KIND_WORDS:
        if rx.search(desc):
            return k
    return None

# ------------------------------------------------------------------ names

LATIN_EPITHET = N.EPITHET
BINOMIAL = re.compile(r"^([A-Z][a-z]{2,})\s+([a-z][a-z\-]{2,})$")
GENUS_ONLY = re.compile(r"^[A-Z][a-z]{2,}$")
RANK_SUFFIX = re.compile(r"(?:aceae|idae|inae|ales|ineae|oidea|oideae|iformes|phyta|mycota)$", re.I)
ENGLISH_STOP = {"the", "and", "of", "for", "with", "from", "in", "on", "or", "a", "an", "stone", "tree",
                "plant", "bird", "fish", "leaf", "root", "white", "black", "red", "green", "blue", "grey",
                "gray", "brown", "yellow", "great", "little", "common", "indian", "giant", "small", "large",
                "wild", "true", "water", "sea", "house", "garden", "hill", "forest", "river", "tamil",
                "english", "north", "south", "east", "west", "family", "genus", "species", "order", "class",
                "cum", "nitric", "oxide", "scale", "mole", "tit", "call", "fir", "created", "database"}

def looks_binomial(s):
    """Two or three Latin words, the epithet with a Latin ending; not an English phrase."""
    s = (s or "").strip()
    parts = s.split()
    if len(parts) == 3 and re.fullmatch(r"[a-z][a-z\-]{2,}", parts[2]):
        parts = parts[:2]
    if len(parts) != 2:
        return False
    m = BINOMIAL.match(" ".join(parts))
    if not m:
        return False
    g, e = m.group(1), m.group(2)
    if g in N.GENUS_BAD or g.lower() in ENGLISH_STOP or e in ENGLISH_STOP:
        return False
    return bool(LATIN_EPITHET.search(e))

def is_taxon_name(s, wd_sci=None, genera=()):
    """A binomial, the very name Wikidata gives as the taxon name (a genus is one word), or a two-word
    name whose first word is a genus already known for this entity ('Rhabdophis plumbicolor')."""
    s = (s or "").strip()
    if not s:
        return False
    if wd_sci and s.lower() == wd_sci.lower():
        return True
    if looks_binomial(s):
        return True
    parts = s.split()
    known = {g.lower() for g in genera if g} | ({genus_of(wd_sci)} if wd_sci else set())
    if 2 <= len(parts) <= 3 and GENUS_ONLY.match(parts[0]) and parts[0].lower() in known \
            and all(re.fullmatch(r"[a-z][a-z\-]{2,}", p) for p in parts[1:]):
        return True
    return False

def clean_en_title(t, wd_sci=None, genera=()):
    """'Koel (bird)' -> 'koel'; a taxon-name title is returned as it is; 'Lutra (Aonyx)', where the bracket
    holds the taxon name, is not a common name at all."""
    if not t:
        return None
    if is_taxon_name(t, wd_sci, genera):
        return t
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", t)
    if m and wd_sci and m.group(2).strip().lower() == wd_sci.lower() and len(m.group(1).split()) == 1:
        return None
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
    return t.lower() if t else None

TA_ALT_STOP = {"இலங்கை", "இந்தியா", "தமிழ்நாடு", "தமிழ்", "ஆங்கிலம்", "இந்திய", "இலங்கைத் தமிழ்", "கேரளா",
               "ஆசியா", "ஆப்பிரிக்கா", "ஐரோப்பா", "அமெரிக்கா", "ஆத்திரேலியா", "சீனா", "சப்பான்", "மலேசியா"}

def clean_alts(alts, name_ta):
    out = []
    for a in alts or []:
        a = re.sub(r"\s+", " ", a).strip(" .,;:")
        if a and a != name_ta and a not in TA_ALT_STOP and a not in out:
            out.append(a)
    return out

def norm_en(s):
    return re.sub(r"\s+'", "'", re.sub(r"\s+", " ", (s or ""))).strip().lower()

def sane_en_name(s, sci, wd_sci=None):
    """An article-text English name is kept only when it reads like an English common name."""
    if not s:
        return False
    s = s.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z '\-]{2,44}", s):
        return False
    words = s.lower().split()
    if len(words) > 5 or max(len(w) for w in words) < 4:
        return False
    if len(words) == 1 and (RANK_SUFFIX.search(words[0]) or len(words[0]) < 5):
        return False
    if is_taxon_name(s, wd_sci) or is_taxon_name(s.title(), wd_sci) or GENUS_ONLY.match(s) and RANK_SUFFIX.search(s):
        return False
    for ref in (sci, wd_sci):
        if ref and (s.lower() == ref.lower() or s.lower() in [w.lower() for w in ref.split()]):
            return False
    if any(w in ENGLISH_STOP for w in words) and len(words) == 1:
        return False
    return True

def sane_sci(s, name_en):
    if not s or not looks_binomial(s):
        return False
    if name_en and name_en.lower().startswith(s.lower()):
        return False                                        # "Slender stone" cut from "Slender stone loach"
    return True

def sci_from_extract(text):
    """A binomial written in brackets in the first sentence of the English intro ('the seed of a palm
    (Areca catechu)'); anything looser reads 'Foxes are' as a species."""
    first = re.split(r"(?<=[a-z\)])\.\s", (text or "").strip(), maxsplit=1)[0]
    for inner in re.findall(r"\(([^()]{5,120})\)", first):
        m = N.BINOMIAL.search(inner)
        if m and looks_binomial(m.group(1) + " " + m.group(2)):
            return m.group(1) + " " + m.group(2)
    return None

def sci_key(s):
    return " ".join((s or "").lower().split()[:2])

def genus_of(s):
    return (s or "").split()[0].lower() if s else ""

def epithet_of(s):
    p = (s or "").split()
    return p[1].lower() if len(p) > 1 else ""

def decide_sci(seed, wd_sci, en_title, text_sci, text_en, trusted, extract):
    """(name_sci, source, name_sci_alt). The article's own binomial is kept when Wikidata's differs only
    by synonymy (same genus or same epithet); Wikidata's wins when they disagree altogether."""
    if seed:
        return seed["sci"], "langlink", None
    text_ok = trusted and sane_sci(text_sci, text_en)
    if wd_sci:
        if text_ok:
            if sci_key(text_sci) == sci_key(wd_sci):
                return text_sci, "article_text", None
            if genus_of(text_sci) == genus_of(wd_sci) or (epithet_of(text_sci) and epithet_of(text_sci) == epithet_of(wd_sci)):
                return text_sci, "article_text", wd_sci
            return wd_sci, "wikidata", None
        return wd_sci, "wikidata", None
    if en_title and looks_binomial(en_title):
        return en_title, "langlink", None
    if text_ok:
        return text_sci, "article_text", None
    s = sci_from_extract(extract) if extract else None
    if s:
        return s, "en_lead", None
    return None, None, None

def decide_en(seed, wd, en_title, text_en, sci, trusted, genera=()):
    """(name_en, source, name_en_alt)."""
    wd_sci = (wd or {}).get("sci")
    text_ok = trusted and sane_en_name(text_en, sci, wd_sci) and not is_taxon_name(text_en, wd_sci, genera)
    alt = norm_en(text_en) if text_ok else None
    if seed:
        name = seed["en"]
        return name, "langlink", (alt if alt != name else None)
    if en_title and not is_taxon_name(en_title, wd_sci, genera):
        name = clean_en_title(en_title, wd_sci, genera)
        if name and not is_taxon_name(name.title(), wd_sci, genera):
            return name, "langlink", (alt if alt != name else None)
    label = (wd or {}).get("label_en")
    if label and sane_en_name(label, sci, wd_sci) and not is_taxon_name(label, wd_sci, genera):
        return label.lower(), "wikidata", (alt if alt != label.lower() else None)
    if text_ok:
        return alt, "article_text", None
    return None, None, None

# ------------------------------------------------------------------ seeds

def seeds_of_entity(e):
    """Which coverage-list rows the first build attached to this entity (recovered from its fields)."""
    if not e.get("lists"):
        return []
    terms = set(e.get("match_terms", []))
    keys = {sci_key(e.get("name_sci")), sci_key(e.get("name_sci_alt"))} - {""}
    return [i for i, s in enumerate(SEEDS)
            if s["list"] in e["lists"] and sci_key(s["sci"]) in keys and s["en"] in terms]

def seed_match(i, ll, wd, seed_canon, seed_ta, title, desc_ta):
    """How the article at `title` relates to seed i: 'species', 'genus', or None."""
    s = SEEDS[i]
    en_title = (ll or {}).get("en")
    wd_sci = (wd or {}).get("sci")
    if en_title and en_title in seed_canon[i]:
        return "species"
    if wd_sci and sci_key(wd_sci) == sci_key(s["sci"]):
        return "species"
    if seed_ta.get(i) and seed_ta[i] == title:
        return "species"
    if not en_title and not wd_sci and sci_key(s["sci"]) in (desc_ta or "").lower():
        return "species"                                     # no interlanguage link at all: the lead is the only witness
    if wd_sci and len(wd_sci.split()) == 1 and wd_sci.lower() == genus_of(s["sci"]):
        return "genus"
    return None

# ------------------------------------------------------------------ bodies from the dump

def bodies_for(titles):
    titles = set(t for t in titles if t)
    if not titles:
        return {}, set()
    got = N.fetch_dump_titles(titles)
    from_dump = set(got)
    p = os.path.join(BUILD_CACHE, "gapfill_extracts.json")
    extra = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    for t in titles - from_dump:
        if t in extra:
            got[t] = N.strip_wikitext(extra[t])
    return got, from_dump

# ------------------------------------------------------------------ match terms

def build_terms(seed_rows, name_en, name_ta, alts, sci, kind, en_title, aliases_en, latin_redirects, extra, wd_sci=None):
    seed = seed_rows[0] if seed_rows else None
    terms = N.match_terms(seed, name_en, name_ta, alts, sci, kind)
    def add(t):
        t = re.sub(r"\s+", " ", (t or "")).strip().lower()
        if t and t not in terms:
            terms.append(t)
    for s2 in seed_rows[1:]:
        for t in [s2["en"]] + s2["syn"]:
            add(t)
            p = N.plural(t)
            if p:
                add(p)
    if en_title:
        c = clean_en_title(en_title, wd_sci)
        add(c)
        add(en_title)
        p = N.plural(c or "")
        if p:
            add(p)
    for t in extra:
        add(t)
        p = N.plural(t or "")
        if p:
            add(p)
    for a in (aliases_en or [])[:8]:
        if re.fullmatch(r"[A-Za-z][A-Za-z '\-]{2,40}", a) and len(a.split()) <= 4:
            add(a)
    if to_roman:
        for t in [name_ta] + list(alts):
            r = to_roman(t)
            if r and re.fullmatch(r"[A-Za-z ]{3,}", r):
                add(r)
                add(r.replace(" ", ""))
    for rd in (latin_redirects or [])[:6]:
        add(rd)
    return [t for t in terms if t]

# ------------------------------------------------------------------ audit

def load_pack():
    ents = [json.loads(l) for l in open(os.path.join(PACK, "entities.jsonl"), encoding="utf-8")]
    chunks = [json.loads(l) for l in open(os.path.join(PACK, "chunks.jsonl"), encoding="utf-8")]
    return ents, chunks

def audit(ents, no_fetch=False):
    titles = [e["source_title"] for e in ents]
    ll = ta_langlinks(titles, no_fetch)
    wd = wikidata([v.get("qid") for v in ll.values()], no_fetch)
    seed_names = sorted({s["sci"] for s in SEEDS} | {s["en"] for s in SEEDS})
    enr = en_resolve(seed_names, no_fetch)
    seed_canon, seed_ta = {}, {}
    for i, s in enumerate(SEEDS):
        seed_canon[i] = {x for x in (enr[s["sci"]]["canonical"], enr[s["en"]]["canonical"]) if x}
        seed_ta[i] = enr[s["sci"]]["ta"] or enr[s["en"]]["ta"]
    verdicts = OrderedDict()
    for e in ents:
        t = e["source_title"]
        l = ll[t]
        w = wd.get(l.get("qid")) if l.get("qid") else None
        subj, label = subject_of(l, w, e["kind"], t, e["description_ta"])
        v = {"ll": l, "wd": w, "subject": subj, "subject_label": label, "seeds": seeds_of_entity(e),
             "seed_ok": [], "seed_bad": [], "seed_level": {}}
        for i in v["seeds"]:
            lvl = seed_match(i, l, w, seed_canon, seed_ta, t, e["description_ta"]) if subj != "not_organism" else None
            if lvl:
                v["seed_ok"].append(i); v["seed_level"][i] = lvl
            else:
                v["seed_bad"].append(i)
        verdicts[e["id"]] = v
    return verdicts, seed_canon, seed_ta, ll, wd

def find_seed_articles(missing, seed_canon, seed_ta, by_title, no_fetch=False):
    """For each seed without a verified entity: the Tamil article the English article links to, or a
    ta.wikipedia search hit on the quoted scientific name that its own Wikidata item or English link
    confirms. Returns {seed index: (title, how)}."""
    def check(i, t, how, ll, wd):
        l = ll.get(t) or {}
        w = wd.get(l.get("qid")) if l.get("qid") else None
        desc = by_title[t]["description_ta"] if t in by_title else ""
        if subject_of(l, w, SEEDS[i]["kind"], t, desc)[0] == "not_organism":
            return None
        lvl = seed_match(i, l, w, seed_canon, seed_ta, t, desc)
        if lvl == "species" or (lvl == "genus" and how == "en_langlink"):
            return (t, how, lvl)
        return None

    out = {}
    first = {i: seed_ta[i] for i in missing if seed_ta.get(i) and not N.BAD_TITLE.search(seed_ta[i])}
    ll = ta_langlinks(sorted(set(first.values())), no_fetch)
    wd = wikidata([v.get("qid") for v in ll.values()], no_fetch)
    for i, t in first.items():
        r = check(i, t, "en_langlink", ll, wd)
        if r:
            out[i] = r
    need_search = [i for i in missing if i not in out]
    hits = ta_search(sorted({SEEDS[i]["sci"] for i in need_search}), no_fetch)
    cands = {i: [t for t in hits.get(SEEDS[i]["sci"], [])[:5] if not N.BAD_TITLE.search(t)] for i in need_search}
    ll2 = ta_langlinks(sorted({t for c in cands.values() for t in c}), no_fetch)
    wd2 = wikidata([v.get("qid") for v in ll2.values()], no_fetch)
    ll.update(ll2); wd.update(wd2)
    for i, c in cands.items():
        for t in c:
            r = check(i, t, "ta_search", ll, wd)
            if r:
                out[i] = r; break
    return out, ll, wd

# ------------------------------------------------------------------ fix

def fixed_kind(e, v):
    """The kind stays unless Wikidata's one-liner puts the subject in another family altogether."""
    w = v["wd"] or {}
    fam = kind_family_from_desc(w.get("desc_en"))
    if not fam or fam == family_of(e["kind"]):
        return e["kind"], False
    return {"bird": "bird", "insect": "insect", "animal": "animal", "p": "plant"}[fam], True

def entity_row(e, v, seed_idx, seed_levels, extracts, redirects, trusted):
    l, w = v["ll"], (v["wd"] or {})
    en_title = l.get("en")
    seed_rows = [SEEDS[i] for i in seed_idx]
    seed = seed_rows[0] if seed_rows else None
    text_en, text_sci = e.get("name_en"), e.get("name_sci")
    if not trusted:                                         # the first build wrote the seed's names here; re-read the lead
        text_sci = N.sci_of(e["description_ta"])
        text_en = N.en_of(e["description_ta"], text_sci)
        trusted = True
    sci, sci_src, sci_alt = decide_sci(seed, w.get("sci"), en_title, text_sci, text_en, trusted,
                                       extracts.get(en_title) if en_title else None)
    if seed and seed_levels.get(seed_idx[0]) == "genus" and w.get("sci"):
        sci, sci_src, sci_alt = w["sci"], "wikidata", seed["sci"]
    genera = [genus_of(x) for x in (sci, sci_alt, w.get("sci"), text_sci) if x]
    if en_title and not sci_alt and sci and sci_key(en_title) != sci_key(sci) \
            and len(en_title.split()) >= 2 and is_taxon_name(en_title, w.get("sci"), genera):
        sci_alt = en_title                                  # the English article's (often newer) binomial
    name_en, en_src, en_alt = decide_en(seed, w, en_title, text_en, sci, trusted, genera)
    kind, kind_changed = fixed_kind(e, v)
    if seed:
        kind = seed["kind"]
    alts = clean_alts(e.get("names_ta_alt", []), e["name_ta"])
    t = e["source_title"]
    latin_redirects = [rd for rd in redirects.get(t, []) if not N.TA_TOK.search(rd)]
    extra_terms = [x for x in (en_alt, sci_alt) if x]
    row = OrderedDict()
    row["kind"] = kind
    row["name_ta"] = e["name_ta"]
    row["names_ta_alt"] = alts
    row["name_en"] = name_en
    row["name_sci"] = sci
    row["name_en_alt"] = en_alt
    row["name_sci_alt"] = sci_alt
    row["description_ta"] = e["description_ta"]
    row["description_en"] = N.describe_en(seed, name_en, e["name_ta"], N.romanise(e["name_ta"]), kind, sci, alts)
    row["source_title"] = t
    row["source_url"] = e["source_url"]
    row["license"] = e["license"]
    row["match_terms"] = build_terms(seed_rows, name_en, e["name_ta"], alts, sci, kind, en_title,
                                     w.get("aliases_en"), latin_redirects, extra_terms, w.get("sci"))
    row["lists"] = sorted({SEEDS[i]["list"] for i in seed_idx})
    row["description_en_written"] = bool(seed)
    row["text_from"] = e.get("text_from", "dump")
    row["name_source"] = en_src
    row["name_sci_source"] = sci_src
    row["langlink_en"] = en_title
    row["wikidata_id"] = l.get("qid")
    row["verified"] = bool(en_title) or bool(w.get("sci"))
    row["_seeds"] = seed_idx
    row["_seed_levels"] = {i: seed_levels.get(i, "species") for i in seed_idx}
    row["_changed"] = (name_en != e.get("name_en") or sci != e.get("name_sci") or kind != e["kind"]
                       or row["lists"] != e.get("lists", []) or bool(en_alt) or bool(sci_alt))
    row["_kind_changed"] = kind_changed
    return row

def new_entity_row(t, body, seed_idx, seed_levels, l, w, redirects, from_dump):
    seed_rows = [SEEDS[i] for i in seed_idx]
    seed = seed_rows[0]
    name_ta = N.clean_title(t)
    alts = N.alt_ta_of(t, body)
    if t != name_ta:
        alts.insert(0, t)
    for rd in redirects.get(t, []):
        if N.TA_TOK.search(rd) and not re.search(r"[A-Za-z0-9]", rd) and rd not in alts and rd != name_ta:
            alts.append(rd)
    alts = clean_alts(alts, name_ta)[:10]
    kind, sci = seed["kind"], seed["sci"]
    sci_alt = None
    if seed_levels.get(seed_idx[0]) == "genus" and (w or {}).get("sci"):
        sci, sci_alt = w["sci"], seed["sci"]
    row = OrderedDict()
    row["kind"] = kind
    row["name_ta"] = name_ta
    row["names_ta_alt"] = alts
    row["name_en"] = seed["en"]
    row["name_sci"] = sci
    row["name_en_alt"] = None
    row["name_sci_alt"] = sci_alt
    row["description_ta"] = N.describe_ta(body, kind, sci)
    row["description_en"] = N.describe_en(seed, seed["en"], name_ta, N.romanise(name_ta), kind, sci, alts)
    row["source_title"] = t
    row["source_url"] = CK.wiki_url(N.HOST, t)
    row["license"] = N.LICENSE
    row["match_terms"] = build_terms(seed_rows, seed["en"], name_ta, alts, sci, kind, (l or {}).get("en"),
                                     (w or {}).get("aliases_en"),
                                     [rd for rd in redirects.get(t, []) if not N.TA_TOK.search(rd)],
                                     [sci_alt] if sci_alt else [])
    row["lists"] = sorted({SEEDS[i]["list"] for i in seed_idx})
    row["description_en_written"] = True
    row["text_from"] = "dump" if from_dump else "api"
    row["name_source"] = "langlink"
    row["name_sci_source"] = "wikidata" if sci_alt else "langlink"
    row["langlink_en"] = (l or {}).get("en")
    row["wikidata_id"] = (l or {}).get("qid")
    row["verified"] = True
    row["_seeds"] = seed_idx
    row["_seed_levels"] = {i: seed_levels.get(i, "species") for i in seed_idx}
    row["_changed"] = True
    row["_kind_changed"] = False
    return row

def coverage_table(rows, list_name, reasons):
    out = []
    for i, s in enumerate(SEEDS):
        if s["list"] != list_name:
            continue
        e = next((x for x in rows if i in x["_seeds"]), None)
        out.append(OrderedDict([
            ("english", s["en"]), ("scientific", s["sci"]), ("kind", s["kind"]),
            ("entity", bool(e)),
            ("name_ta", (e or {}).get("name_ta")),
            ("name_sci", (e or {}).get("name_sci")),
            ("description", bool(e and e.get("description_ta"))),
            ("source_title", (e or {}).get("source_title")),
            ("entity_id", (e or {}).get("id")),
            ("match", (e or {}).get("_seed_levels", {}).get(i)),
            ("langlink_en", (e or {}).get("langlink_en")),
            ("gap", None if e else reasons.get(i, "no Tamil article found")),
        ]))
    return out

def summarise(table):
    s = N.summarise(table)
    s["genus_level"] = [r["english"] for r in table if r["match"] == "genus"]
    return s

def run(dry_run=False, no_fetch=False):
    ents, chunks = load_pack()
    before_by_kind = Counter(e["kind"] for e in ents)
    verdicts, seed_canon, seed_ta, ll, wd = audit(ents, no_fetch)
    by_title = {e["source_title"]: e for e in ents}
    redirects_path = os.path.join(BUILD_CACHE, "redirects.json")
    redirects = json.load(open(redirects_path, encoding="utf-8"))["map"] if os.path.exists(redirects_path) else {}

    # --- seeds that need a (new) article: detached from a wrong one, or never filled
    had = {i for v in verdicts.values() for i in v["seeds"]}
    detached = sorted({i for v in verdicts.values() for i in v["seed_bad"]})
    unfilled = [i for i in range(len(SEEDS)) if i not in had]
    found, ll2, wd2 = find_seed_articles(sorted(set(detached) | set(unfilled)), seed_canon, seed_ta, by_title, no_fetch)

    seeds_attached, seed_levels = {}, {}
    for e in ents:
        v = verdicts[e["id"]]
        for i in v["seed_ok"]:
            seeds_attached.setdefault(e["source_title"], []).append(i)
            seed_levels[i] = v["seed_level"][i]
    for i, (t, how, lvl) in found.items():
        seeds_attached.setdefault(t, []).append(i)
        seed_levels[i] = lvl

    # --- bodies: new articles, and pack articles that gain a coverage-list slot (they get up to 3 chunks)
    new_titles = {t for t in seeds_attached if t not in by_title}
    regrow = {t for t in seeds_attached if t in by_title and not by_title[t].get("lists")}
    bodies, from_dump = bodies_for(new_titles | regrow)
    for t in list(new_titles):
        if t not in bodies or len(bodies[t].split()) < N.MIN_GAP_WORDS:
            new_titles.discard(t)
            for i in seeds_attached.pop(t, []):
                found.pop(i, None)

    # --- English intros for entities that still have no scientific name
    need_lead = []
    for e in ents:
        v = verdicts[e["id"]]
        if v["subject"] == "not_organism" or not v["ll"].get("en"):
            continue
        trusted = not v["seed_bad"]
        text_sci, text_en = e.get("name_sci"), e.get("name_en")
        if not trusted:
            text_sci = N.sci_of(e["description_ta"]); text_en = N.en_of(e["description_ta"], text_sci)
        seed = SEEDS[seeds_attached.get(e["source_title"], [None])[0]] if seeds_attached.get(e["source_title"]) else None
        sci, _s, _a = decide_sci(seed, (v["wd"] or {}).get("sci"), v["ll"]["en"], text_sci, text_en, True, None)
        if not sci:
            need_lead.append(v["ll"]["en"])
    extracts = en_extracts(sorted(set(need_lead)), no_fetch) if need_lead else {}

    # --- rows
    old_chunks = {}
    for c in chunks:
        old_chunks.setdefault(c["entity_id"], []).append(c)
    rows, dropped, seed_log = [], [], []
    for e in ents:
        v = verdicts[e["id"]]
        t = e["source_title"]
        if v["subject"] == "not_organism":
            dropped.append({"id": e["id"], "title": t, "kind": e["kind"], "was": v["subject_label"],
                            "en": v["ll"].get("en"), "old_name_en": e.get("name_en"), "old_name_sci": e.get("name_sci"),
                            "seeds": [SEEDS[i]["en"] for i in v["seeds"]]})
            continue
        seed_idx = sorted(set(seeds_attached.get(t, [])))
        row = entity_row(e, v, seed_idx, seed_levels, extracts, redirects, trusted=not v["seed_bad"])
        row["_old_id"] = e["id"]
        row["_old"] = e
        row["_chunks"] = old_chunks.get(e["id"], [])
        row["_body"] = bodies.get(t) if t in regrow and seed_idx else None
        if v["seed_bad"]:
            seed_log.append({"id": e["id"], "title": t, "en": v["ll"].get("en"), "wd_sci": (v["wd"] or {}).get("sci"),
                             "seeds_lost": [SEEDS[i]["en"] + " (" + SEEDS[i]["sci"] + ")" for i in v["seed_bad"]],
                             "now": row["name_en"] or row["name_sci"]})
        rows.append(row)
    new_rows = []
    for t in sorted(new_titles):
        idx = sorted(set(seeds_attached.get(t, [])))
        if not idx:
            continue
        l2 = ll2.get(t) or {}
        w2 = wd2.get(l2.get("qid")) if l2.get("qid") else None
        row = new_entity_row(t, bodies[t], idx, seed_levels, l2, w2, redirects, t in from_dump)
        row["_old_id"], row["_old"], row["_chunks"], row["_body"] = None, None, [], bodies[t]
        new_rows.append(row)
    rows.extend(new_rows)

    # --- family safe over every changed row and every rebuilt chunk
    #     visible text (both descriptions, the three names) drops the row on a severe hit; a match term is an
    #     index key, so a flagged term is removed from the list instead ("yellow tit" keeps its entity, the
    #     builder's plural "tits" does not survive)
    fs_scanned, fs_dropped_rows, fs_hits, kept, terms_removed = 0, [], Counter(), [], []
    for r in rows:
        if r["_changed"] or r["_body"] is not None:
            fs_scanned += 1
            hits = []
            for field in ("description_ta", "description_en", "name_ta", "name_en", "name_sci", "name_en_alt"):
                if r.get(field):
                    hits += FS.check(r[field])
            for h in hits:
                fs_hits[h.get("severity") or "profanity"] += 1
            if N.severe(hits):
                fs_dropped_rows.append({"title": r["source_title"], "kind": r["kind"], "seeds": r["_seeds"],
                                        "severities": sorted({h.get("severity") or "profanity" for h in hits})})
                continue
            clean = []
            for t in r["match_terms"]:
                if N.severe(FS.check(t)):
                    terms_removed.append((r["source_title"], t))
                else:
                    clean.append(t)
            r["match_terms"] = clean
        kept.append(r)
    rows = kept
    rows.sort(key=lambda r: (0 if r["_seeds"] else 1, r["kind"], r["source_title"]))
    for i, r in enumerate(rows, 1):
        r["id"] = "nature-e%05d" % i
    counter = [0]
    new_chunk_scanned, new_chunk_dropped = 0, 0
    for r in rows:
        if r["_body"] is not None:
            fake = dict(r); fake["_seed"] = bool(r["_seeds"])
            good = []
            for c in N.make_chunks([fake], counter):
                new_chunk_scanned += 1
                if N.severe(FS.check(c["text"])):
                    new_chunk_dropped += 1
                else:
                    good.append(c)
            r["_chunks"] = good
    rows = [r for r in rows if r["_chunks"]]
    for i, r in enumerate(rows, 1):
        r["id"] = "nature-e%05d" % i
    final_chunks = []
    for r in rows:
        ids = []
        for c in r["_chunks"]:
            c = dict(c)
            c["entity_id"] = r["id"]
            c["kind"] = r["kind"]
            c["id"] = "nature-%05d" % (len(final_chunks) + 1)
            final_chunks.append(c); ids.append(c["id"])
        r["chunk_ids"] = ids

    # --- coverage after the fix
    reasons = {}
    for d in fs_dropped_rows:
        for i in d["seeds"]:
            reasons[i] = "article found (%s) but dropped by the family-safe lexicon" % d["title"]
    for i in range(len(SEEDS)):
        if i in found:
            continue
        t = seed_ta.get(i)
        where = ("the English article links to '%s', which is not in the offline dump" % t) if t else \
                "the English article has no Tamil interlanguage link, and the quoted scientific-name search on ta.wikipedia finds no article whose Wikidata taxon name is this species"
        if i in detached:
            reasons.setdefault(i, "first build pointed at the wrong article; " + where)
        elif i in unfilled:
            reasons.setdefault(i, "no Tamil article: " + where)
    cov = OrderedDict()
    for name in ("birds_100", "plants_trees_100", "fruits_vegetables_78"):
        table = coverage_table(rows, name, reasons)
        cov[name] = OrderedDict([("summary", summarise(table)), ("items", table)])

    # requests, counted from the cache so a cached rerun reports the same numbers as the first run
    import math
    requests = OrderedDict([
        ("ta.wikipedia langlinks+pageprops (50 titles a request)", math.ceil(len(_load("ta_langlinks.json", {})) / 50)),
        ("wikidata wbgetentities (50 items a request)", math.ceil(len(_load("wikidata.json", {})) / 50)),
        ("en.wikipedia langlinks for the seeds (50 titles a request)", math.ceil(len(_load("en_resolve.json", {})) / 50)),
        ("ta.wikipedia search (one a seed)", len(_load("ta_search.json", {}))),
        ("en.wikipedia extracts (20 a request)", math.ceil(len(_load("en_extracts.json", {})) / 20)),
    ])
    dropped_titles = {d["title"] for d in dropped}
    for i in list(reasons):
        t = seed_ta.get(i)
        if t and t in dropped_titles and i not in found:
            reasons[i] = ("the English article's Tamil link is '%s', which this audit dropped as not a living thing "
                          "(%s); the quoted scientific-name search on ta.wikipedia finds no article whose Wikidata "
                          "taxon name is this species" % (t, next(d["was"] for d in dropped if d["title"] == t)))
    for name in cov:
        table = coverage_table(rows, name, reasons)
        cov[name] = OrderedDict([("summary", summarise(table)), ("items", table)])
    res = {
        "before": {"entities": len(ents), "by_kind": dict(before_by_kind), "chunks": len(chunks),
                   "seeds_on_wrong_article_by_list": dict(Counter(SEEDS[i]["list"] for i in detached))},
        "requests": requests,
        "verdicts": verdicts, "dropped": dropped, "seed_log": seed_log, "found": found, "detached": detached,
        "unfilled": unfilled, "rows": rows, "chunks": final_chunks, "cov": cov,
        "fs": {"rows_scanned": fs_scanned, "rows_dropped": fs_dropped_rows, "hits": dict(fs_hits),
               "new_chunks_scanned": new_chunk_scanned, "new_chunks_dropped": new_chunk_dropped,
               "terms_removed": terms_removed},
        "extracts_read": len(extracts), "new_rows": [r["source_title"] for r in new_rows], "seed_ta": seed_ta,
    }
    res["name_changes"] = name_changes(rows)
    if not dry_run:
        write_pack(res)
        write_audit_md(res)
    return res

def name_changes(rows):
    """What happened to name_en and name_sci on the entities that survived: filled where the first build had
    nothing, corrected where it had something else, or only re-cased ('Ethiopian swallow' -> 'ethiopian
    swallow' is not a correction)."""
    c = Counter()
    ex = {"name_en": [], "name_sci": []}
    for r in rows:
        o = r.get("_old")
        if not o:
            continue
        old, new = o.get("name_en"), r["name_en"]
        if not old and new:
            c["name_en_filled"] += 1
        elif old and not new:
            c["name_en_emptied"] += 1
        elif old and new and norm_en(old) != norm_en(new):
            c["name_en_corrected"] += 1
            if len(ex["name_en"]) < 14:
                ex["name_en"].append((r["source_title"], old, new, r["name_source"]))
        elif old and new and old != new:
            c["name_en_recased"] += 1
        old, new = o.get("name_sci"), r["name_sci"]
        if not old and new:
            c["name_sci_filled"] += 1
        elif old and not new:
            c["name_sci_emptied"] += 1
        elif old and new and sci_key(old) != sci_key(new):
            c["name_sci_corrected"] += 1
            if len(ex["name_sci"]) < 14:
                ex["name_sci"].append((r["source_title"], old, new, r["name_sci_source"]))
    return {"counts": dict(c), "examples": ex}

# ------------------------------------------------------------------ write

ENTITY_FIELDS = ("id", "kind", "name_ta", "names_ta_alt", "name_en", "name_sci", "name_en_alt", "name_sci_alt",
                 "description_ta", "description_en", "source_title", "source_url", "license", "match_terms",
                 "lists", "description_en_written", "text_from", "name_source", "name_sci_source", "langlink_en",
                 "wikidata_id", "verified", "chunk_ids")

def write_pack(res):
    rows, chunks = res["rows"], res["chunks"]
    with open(os.path.join(PACK, "entities.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(OrderedDict([(k, r.get(k)) for k in ENTITY_FIELDS]), ensure_ascii=False) + "\n")
    with open(os.path.join(PACK, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    man_path = os.path.join(PACK, "manifest.json")
    man = json.load(open(man_path, encoding="utf-8"), object_pairs_hook=OrderedDict)
    before_cov = man.get("audit", {}).get("coverage_before") or man.get("coverage", OrderedDict())
    by_kind = Counter(r["kind"] for r in rows)
    words = [len(c["text"].split()) for c in chunks]
    terms = sum(len(r["match_terms"]) for r in rows)
    man["version"] = VERSION + ".1"
    man["audit"] = OrderedDict([
        ("script", "audit_pack_nature.py"),
        ("date", VERSION),
        ("method", "ta.wikipedia prop=langlinks (lllang=en) and prop=pageprops (wikibase_item), 50 titles a "
                   "request, for every entity's source article; Wikidata wbgetentities for the taxon name (P225), "
                   "class (P31), English label, aliases and description; en.wikipedia prop=langlinks (lllang=ta) "
                   "with redirects for the coverage-list species; ta.wikipedia list=search on the quoted "
                   "scientific name for the seeds the links do not resolve, accepted only when the hit's own "
                   "Wikidata taxon name is the species; en.wikipedia prop=extracts (intro) only for entities "
                   "still without a scientific name"),
        ("requests", res["requests"]),
        ("entities_before", res["before"]["entities"]),
        ("entities_by_kind_before", res["before"]["by_kind"]),
        ("entities_after", len(rows)),
        ("entities_dropped_not_organism", len(res["dropped"])),
        ("entities_dropped_family_safe", len(res["fs"]["rows_dropped"])),
        ("entities_added", len(res["new_rows"])),
        ("name_changes", res["name_changes"]["counts"]),
        ("seeds_on_wrong_article_by_list_before", res["before"]["seeds_on_wrong_article_by_list"]),
        ("kind_corrected", sum(1 for r in rows if r.get("_kind_changed"))),
        ("seeds_detached_from_wrong_article", len(res["detached"])),
        ("seeds_repointed", len(res["found"])),
        ("entities_verified_by_langlink_or_wikidata", sum(1 for r in rows if r["verified"])),
        ("entities_unverified", sum(1 for r in rows if not r["verified"])),
        ("name_en_source", dict(Counter(r["name_source"] for r in rows if r["name_source"]))),
        ("name_sci_source", dict(Counter(r["name_sci_source"] for r in rows if r["name_sci_source"]))),
        ("dropped", [{"title": d["title"], "en": d["en"], "was": d["was"]} for d in res["dropped"]]),
        ("coverage_before", before_cov),
    ])
    man["entities"] = len(rows)
    man["entities_by_kind"] = dict(by_kind)
    man["entities_on_a_coverage_list"] = sum(1 for r in rows if r["lists"])
    man["entities_with_name_en"] = sum(1 for r in rows if r["name_en"])
    man["entities_with_name_sci"] = sum(1 for r in rows if r["name_sci"])
    man["entities_with_alt_names"] = sum(1 for r in rows if r["names_ta_alt"])
    man["match_terms_total"] = terms
    man["match_terms_mean"] = round(terms / max(1, len(rows)), 1)
    man["chunks"] = len(chunks)
    man["chunks_by_language"] = dict(Counter(c["lang"] for c in chunks))
    man["words"] = {"total": sum(words), "mean": round(sum(words) / max(1, len(words)), 1),
                    "min": min(words) if words else 0, "max": max(words) if words else 0}
    man["family_safe"]["audit_rows_scanned"] = res["fs"]["rows_scanned"]
    man["family_safe"]["audit_rows_dropped"] = len(res["fs"]["rows_dropped"])
    man["family_safe"]["audit_new_chunks_scanned"] = res["fs"]["new_chunks_scanned"]
    man["family_safe"]["audit_new_chunks_dropped"] = res["fs"]["new_chunks_dropped"]
    man["coverage"] = OrderedDict([(k, v["summary"]) for k, v in res["cov"].items()])
    man["coverage_detail"] = res["cov"]
    for s in man["sources"]:
        if s["name"].startswith("Tamil Wikipedia, dump"):
            s["articles_kept"] = sum(1 for r in rows if r["text_from"] == "dump")
        if s["name"].startswith("Tamil Wikipedia live"):
            s["articles_kept"] = sum(1 for r in rows if r["text_from"] == "api")
        if s["name"].startswith("English Wikipedia"):
            s["how_obtained"] = ("prop=langlinks in both directions as the authoritative name index: lllang=ta on "
                                 "the coverage-list scientific names, and (audit) lllang=en through ta.wikipedia on "
                                 "every entity's Tamil title; prop=extracts intro only for entities whose scientific "
                                 "name was not on Wikidata, read for the binomial and discarded. No English sentence "
                                 "enters the pack")
            s["titles_resolved"] = sum(1 for r in rows if r["langlink_en"])
            s["intros_read_for_scientific_name"] = res["extracts_read"]
    if not any(s["name"].startswith("Wikidata") for s in man["sources"]):
        man["sources"].append(OrderedDict([
            ("name", "Wikidata (name index only, no text taken)"),
            ("url", "https://www.wikidata.org/w/api.php"),
            ("license", "CC0 1.0"),
            ("license_verified_on", VERSION),
            ("how_obtained", "wbgetentities, 50 items a request, on the wikibase_item of each Tamil article: "
                             "taxon name P225, instance-of P31, English label, English aliases and the one-line "
                             "description. Used to verify the subject and to fill or check name_sci; nothing else "
                             "is taken"),
            ("items_read", sum(1 for r in rows if r["wikidata_id"])),
        ]))
    man["built_by"] = "build_pack_nature.py, then audit_pack_nature.py"
    json.dump(man, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    rep_path = os.path.join(PACK, "family_safe_report.json")
    rep = json.load(open(rep_path, encoding="utf-8"), object_pairs_hook=OrderedDict)
    rep["audit"] = OrderedDict([
        ("date", VERSION),
        ("what_was_scanned", "every entity whose name_en, name_sci, kind or list membership changed (both "
                             "descriptions, the Tamil name and the rebuilt match_terms), every added entity, and "
                             "every chunk rebuilt for an added or newly listed entity"),
        ("rows_scanned", res["fs"]["rows_scanned"]),
        ("rows_dropped", len(res["fs"]["rows_dropped"])),
        ("hits_by_severity", res["fs"]["hits"]),
        ("chunks_scanned", res["fs"]["new_chunks_scanned"]),
        ("chunks_dropped", res["fs"]["new_chunks_dropped"]),
        ("dropped_examples", res["fs"]["rows_dropped"][:20]),
        ("match_terms_removed", len(res["fs"]["terms_removed"])),
        ("match_terms_removed_examples", [{"title": t, "term": x} for t, x in res["fs"]["terms_removed"][:20]]),
        ("match_terms_policy", "a match term is an index key, not visible text: a term with a severe hit is "
                               "removed from the list and the entity stays; the descriptions and names are "
                               "scanned as before and a severe hit there drops the entity"),
    ])
    rep["kept_entities"] = len(rows)
    rep["kept_chunks"] = len(chunks)
    json.dump(rep, open(rep_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def write_audit_md(res):
    rows = res["rows"]
    before, after = res["before"], Counter(r["kind"] for r in rows)
    kinds = ["bird", "animal", "insect", "tree", "plant", "flower", "fruit", "vegetable"]
    L = []
    L.append("# Nature pack: entity audit (%s)" % VERSION)
    L.append("")
    L.append("Method: the English Wikipedia interlanguage link of each Tamil source article (ta.wikipedia "
             "prop=langlinks, lllang=en, 50 titles a request) and the Wikidata item behind it (taxon name P225, "
             "class P31, English label and description) are the authoritative name index. An entity is kept when "
             "the link or the taxon name says the article is about a living thing; its English and scientific "
             "names are taken from the link and Wikidata, or from the Tamil lead only when those agree with it. "
             "The coverage-list species are checked from the English side too (en.wikipedia prop=langlinks, "
             "lllang=ta, redirects followed), and a species whose link fails is searched on ta.wikipedia by its "
             "quoted scientific name and accepted only when the hit's own Wikidata taxon name is that species. "
             "Script: `audit_pack_nature.py`. Requests made: %s." % ", ".join("%s %d" % (k, v) for k, v in res["requests"].items()))
    L.append("")
    L.append("## Counts")
    L.append("")
    L.append("| | before | after |")
    L.append("|---|---|---|")
    L.append("| entities | %d | %d |" % (before["entities"], len(rows)))
    for k in kinds:
        L.append("| %s | %d | %d |" % (k, before["by_kind"].get(k, 0), after.get(k, 0)))
    L.append("| chunks | %d | %d |" % (before["chunks"], len(res["chunks"])))
    L.append("")
    verified = sum(1 for r in rows if r["verified"])
    L.append("Entities checked: %d (every entity of the first build). Verified by an interlanguage link or a Wikidata "
             "taxon name after the fix: %d of %d; %d have neither and rest on the Tamil lead alone (they are marked "
             "`verified: false`)." % (before["entities"], verified, len(rows), len(rows) - verified))
    L.append("")
    L.append("## Mis-picks")
    L.append("")
    L.append("**Articles that are not about a living thing: %d, dropped.** The first build kept them because the "
             "lead matched a kind word (பூச்சி, தாவரம், மரம்) and a Latin-looking pair of words." % len(res["dropped"]))
    L.append("")
    L.append("| Tamil article | English link | what it is | first build said |")
    L.append("|---|---|---|---|")
    for d in res["dropped"]:
        L.append("| %s | %s | %s | %s |" % (d["title"], d["en"] or "-", d["was"],
                                           ", ".join(x for x in (d["old_name_en"], d["old_name_sci"], (", ".join(d["seeds"]) if d["seeds"] else "")) if x) or d["kind"]))
    L.append("")
    L.append("**Coverage-list species pointed at the wrong article: %d seeds on %d entities, detached.**" %
             (len(res["detached"]), len(res["seed_log"])))
    L.append("")
    L.append("| Tamil article | is really | seed it was carrying |")
    L.append("|---|---|---|")
    for l in res["seed_log"]:
        L.append("| %s | %s (%s) | %s |" % (l["title"], l["en"] or "-", l["wd_sci"] or "-", "; ".join(l["seeds_lost"])))
    L.append("")
    rep = [(SEEDS[i]["en"], t, how, lvl) for i, (t, how, lvl) in sorted(res["found"].items())]
    L.append("**Re-pointed or newly filled: %d seeds.**" % len(rep))
    L.append("")
    L.append("| seed | now on | how | level |")
    L.append("|---|---|---|---|")
    for en, t, how, lvl in rep:
        L.append("| %s | %s | %s | %s |" % (en, t, how, lvl))
    L.append("")
    nc = res["name_changes"]["counts"]
    L.append("**Mis-named, kept and corrected.** The article was about a living thing but the name the first build "
             "read out of the Tamil lead was wrong (an English name in the scientific field, a family name or a "
             "stray bracketed word in the English field): name_en corrected on %d entities, name_sci on %d. "
             "Besides that, name_en was filled on %d entities that had none and emptied on %d whose old value did "
             "not survive the check; name_sci filled on %d, emptied on %d; %d English names only changed case. "
             "Examples of corrections:" % (nc.get("name_en_corrected", 0), nc.get("name_sci_corrected", 0),
                                          nc.get("name_en_filled", 0), nc.get("name_en_emptied", 0),
                                          nc.get("name_sci_filled", 0), nc.get("name_sci_emptied", 0),
                                          nc.get("name_en_recased", 0)))
    L.append("")
    L.append("| Tamil article | field | first build | now | source |")
    L.append("|---|---|---|---|---|")
    for t, old, new, src in res["name_changes"]["examples"]["name_en"][:12]:
        L.append("| %s | name_en | %s | %s | %s |" % (t, old, new, src))
    for t, old, new, src in res["name_changes"]["examples"]["name_sci"][:12]:
        L.append("| %s | name_sci | %s | %s | %s |" % (t, old, new, src))
    L.append("")
    kc = [r for r in rows if r.get("_kind_changed")]
    L.append("**Kind corrected: %d** (the Tamil lead's kind word put a pangolin and a crab among the insects, and "
             "carnivorous plants too): %s." % (len(kc), "; ".join("%s %s to %s" % (r["source_title"], r["_old"]["kind"], r["kind"]) for r in kc)))
    L.append("")
    syn = [r for r in rows if r.get("name_sci_alt") and not r["_seeds"]]
    L.append("Scientific-name synonyms: on %d entities the Tamil article's binomial and Wikidata's taxon name differ "
             "only by synonymy (same genus or same epithet); the article's name is kept in `name_sci`, Wikidata's in "
             "`name_sci_alt`, and both are match terms." % len(syn))
    L.append("")
    L.append("## Coverage")
    L.append("")
    L.append("| list | items | before, as reported | before, on the right article | after | genus-level | still missing |")
    L.append("|---|---|---|---|---|---|---|")
    man = json.load(open(os.path.join(PACK, "manifest.json"), encoding="utf-8"))
    bc = man.get("audit", {}).get("coverage_before", {})
    wrong = res["before"]["seeds_on_wrong_article_by_list"]
    for k, v in res["cov"].items():
        s = v["summary"]
        b = bc.get(k, {}).get("entity")
        L.append("| %s | %d | %s | %s | %d | %s | %s |" % (k, s["items"], b if b is not None else "?",
                                                           (b - wrong.get(k, 0)) if b is not None else "?", s["entity"],
                                                           ", ".join(s["genus_level"]) or "-", ", ".join(s["missing"]) or "-"))
    L.append("")
    L.append("\"Before, as reported\" is the first build's own count; %d of those slots were on the wrong article "
             "(%s), so \"before, on the right article\" is the honest baseline." %
             (len(res["detached"]), ", ".join("%s %d" % (k, n) for k, n in wrong.items())))
    L.append("")
    L.append("Still missing entirely, with the reason:")
    L.append("")
    for k, v in res["cov"].items():
        for en, why in v["summary"]["missing_reason"].items():
            L.append("- %s (%s): %s" % (en, k, why))
    L.append("")
    L.append("## Family safe")
    L.append("")
    fs = res["fs"]
    L.append("`family_safe.check` was run again over every changed or added entity (%d rows: both descriptions and "
             "the three names) and every rebuilt chunk (%d). Rows dropped: %d; chunks dropped: %d. "
             "Hits by severity in the visible text: %s." % (fs["rows_scanned"], fs["new_chunks_scanned"], len(fs["rows_dropped"]),
                                        fs["new_chunks_dropped"], json.dumps(fs["hits"]) if fs["hits"] else "none"))
    L.append("")
    L.append("Match terms were scanned one by one: %d terms with a severe hit were removed and their entities kept "
             "(a match term is an index key, not text a person sees). Nearly all of them are the builder's plural "
             "of the bird name \"tit\": %s." % (len(fs["terms_removed"]),
                                               "; ".join("%s: %s" % (t, x) for t, x in fs["terms_removed"][:8]) or "none"))
    L.append("")
    L.append("The five coverage-list articles the first build lost to the lexicon (Eurasian collared dove, common "
             "sandpiper, Indian robin, chaste tree, mountain knotgrass) were tried again from the dump and are "
             "dropped again for the same reason, so they stay missing.")
    L.append("")
    L.append("## What the langlink route still leaves open")
    L.append("")
    noen = sum(1 for r in rows if not r["name_en"])
    L.append("- %d entities have no English common name: their English article is titled by the scientific name and "
             "Wikidata has no English label other than it. `name_sci` is filled on %d of them." %
             (noen, sum(1 for r in rows if not r["name_en"] and r["name_sci"])))
    L.append("- %d entities have no interlanguage link and no Wikidata taxon name; they are kept on the strength of "
             "the Tamil lead alone and marked `verified: false`." % (len(rows) - verified))
    L.append("- %d coverage-list species sit on a genus-level Tamil article (the Tamil Wikipedia has no species "
             "article): the entity carries the genus name in `name_sci` and the species in `name_sci_alt`." %
             sum(len(v["summary"]["genus_level"]) for v in res["cov"].values()))
    L.append("- The English \"Coconut\" article has no Tamil interlanguage link on the audit date, so the coconut "
             "seeds were resolved by the scientific-name search and Wikidata, not by the link.")
    L.append("- Kind is corrected only when Wikidata's one-line description names another family outright; a "
             "species with no description keeps the kind the Tamil lead gave it.")
    L.append("")
    open(os.path.join(PACK, "AUDIT.md"), "w", encoding="utf-8").write("\n".join(L))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run, no_fetch=a.no_fetch)
    print("requests:", dict(res["requests"]))
    print("before: %d entities %s" % (res["before"]["entities"], res["before"]["by_kind"]))
    print("dropped (not an organism): %d" % len(res["dropped"]))
    for d in res["dropped"]:
        print("   ", d["id"], d["kind"], d["title"], "->", d["en"], "(%s)" % d["was"], d["seeds"])
    print("seeds detached: %d, re-pointed or filled: %d, new entities: %d"
          % (len(res["detached"]), len(res["found"]), len(res["new_rows"])))
    for l in res["seed_log"]:
        print("   ", l["id"], l["title"], "->", l["en"], "|", l["wd_sci"], "| lost:", l["seeds_lost"])
    for i, (t, how, lvl) in sorted(res["found"].items()):
        print("    +", SEEDS[i]["en"], "->", t, how, lvl)
    print("family safe: rows scanned %d dropped %d, chunks scanned %d dropped %d" %
          (res["fs"]["rows_scanned"], len(res["fs"]["rows_dropped"]), res["fs"]["new_chunks_scanned"], res["fs"]["new_chunks_dropped"]))
    for d in res["fs"]["rows_dropped"]:
        print("    fs drop", d)
    print("after: %d entities %s, %d chunks" % (len(res["rows"]), dict(Counter(r["kind"] for r in res["rows"])), len(res["chunks"])))
    for k, v in res["cov"].items():
        s = v["summary"]
        print("  %-22s entity %d/%d, genus-level: %s, missing: %s" % (k, s["entity"], s["items"], ", ".join(s["genus_level"]) or "-", ", ".join(s["missing"])))

if __name__ == "__main__":
    main()
