"""Live Wikipedia lookup through the MediaWiki API (serving ruling 2026-09-08).

lookup(query) -> {title, extract, url, lang, score, categories} or None.
Tamil Wikipedia first, English Wikipedia as fallback. Lead section only, plain text (no infobox,
no navbox: prop=extracts with exintro and explaintext). Family-safe filtering happens here, before
any text can enter a prompt: category blocklist (retrieval/wiki_blocklist.py), then the callbacks the
caller passes for the lexicon backstop and the guard. A drop returns None and is logged.

Limits: 3-second timeout per request, a 24-hour on-disk cache (data/index/wiki_live_cache.json),
and the kill switch WIKI_LIVE=0 (default 1) that makes lookup() return None. At most one call per
turn is enforced by the caller (serve.py). Every call is logged to logs/wiki_live.jsonl.
Wikipedia text is CC BY-SA: the caller attributes the article title and the site in the answer.
The offline Android app never uses this module.
"""
import json, os, re, time, unicodedata, urllib.parse, urllib.request

from .wiki_blocklist import blocked

CACHE = "data/index/wiki_live_cache.json"
LOG = "logs/wiki_live.jsonl"
USER_AGENT = "tamil-lm-serve/1.0 (https://github.com/Timegravity/tamil-lm; contact@timegravity.ai)"
CACHE_TTL = 24 * 3600
_cache = None


def is_enabled():
    return os.environ.get("WIKI_LIVE", "1") != "0"


def _key(query, lang):
    q = unicodedata.normalize("NFC", clean_query(query)).lower().strip()
    q = re.sub(r"\s+", " ", q)
    return f"{lang}:{q}"


def _load_cache():
    global _cache
    if _cache is None:
        try:
            _cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            _cache = {}
    return _cache


def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        json.dump(_cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, CACHE)
    except Exception:
        pass


def _log(rec):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        rec = dict(rec); rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


_STOP = ("என்றால் என்ன", "என்றால்", "என்ன", "யார்", "எது", "எங்கே", "எப்படி", "ஏன்", "எவ்வளவு", "பற்றி", "சொல்லுங்கள்", "சொல்லு", "விவரிக்கவும்", "விளக்கு", "கூறுங்கள்", "தெரியுமா",
         "yaaru", "yaru", "yaar", "enna", "aana", "kattinaanga", "kattinanga", "kattina", "yaarunga", "epdi", "eppadi", "enga", "evlo", "pathi", "sollu", "sollunga", "irukku", "irukaru", "paakalam", "la", "oda", "ah", "ku",
         "what is", "what are", "what does", "what was", "who is", "who was", "who are", "where is", "how tall is", "how many", "tell me about", "explain", "describe", "the", "of", "a", "an", "is", "do", "does", "for", "known", "about", "please")
def clean_query(query):
    """Strip question words so the search sees the entity or topic words only."""
    q = " " + query.lower().replace("?", " ").replace(",", " ") + " "
    for st in sorted(_STOP, key=len, reverse=True):
        q = q.replace(" " + st + " ", " ")
    return re.sub(r"\s+", " ", q).strip() or query

_TITLE_STOP = {"of", "the", "and", "a", "an", "in", "on", "de", "la", "le"}
_MEDIA = ("film", "movie", "song", "album", "band", "group", "tv series", "television", "video game", "novel", "comics", "episode", "discography", "single", "musical", "manga",
          "character", "company", "magazine", "newspaper", "singer", "rapper", "actor", "actress", "wrestler", "footballer", "cricketer")
_MEDIA_Q = _MEDIA + ("padam", "paattu", "paadal", "படம்", "பாடல்", "திரைப்படம்", "நாவல்")

def _tok(s):
    return [x for x in re.split(r"[\s,.;:!?()\"'\-]+", s.lower()) if x]

def _match(a, b):
    """Fuzzy token equality. Latin/Latin: exact, or the longer is the shorter (5+ chars) plus at most two characters
    (numbers/number, indian/india). Tamil: skeleton equality, containment of a 4+ char token, or a shared stem
    (sandhi and case suffixes)."""
    if not a or not b:
        return False
    if not re.search(r"[\u0b80-\u0bff]", a + b):
        a, b = a.lower(), b.lower()
        if a == b:
            return True
        s, l = sorted((a, b), key=len)
        return len(s) >= 5 and len(l) - len(s) <= 2 and l.startswith(s)
    try:
        from .roman import skeleton
        a, b = skeleton(a), skeleton(b)
    except Exception:
        pass
    if a == b:
        return True
    s, l = sorted((a, b), key=len)
    if len(s) >= 4 and s in l:
        return True
    return len(s) >= 5 and l.startswith(s[:-2])

def _overlap(query, title):
    """True when the query covers the title: every content word of the title (final parenthetical stripped) matches a
    query word. A media-work parenthetical (film, song, album, ...) is accepted only when the query names that medium.
    A Tamil title is romanised when the query has no Tamil script."""
    m = re.search(r"\(([^)]*)\)\s*$", title)
    base = title[:m.start()].strip() if m else title
    paren = m.group(1).lower() if m else ""
    if paren and any(x in paren for x in _MEDIA) and not any(x in query.lower() for x in _MEDIA_Q):
        return False
    if re.search(r"[\u0b80-\u0bff]", base) and not re.search(r"[\u0b80-\u0bff]", query):
        try:
            from .roman import to_roman
            base = to_roman(base)
        except Exception:
            pass
    q = _tok(query)
    tw = [t for t in _tok(base) if t not in _TITLE_STOP and len(t) >= 3]
    if not tw or not q:
        return False
    anchor = 3 if re.search(r"[\u0b80-\u0bff]", base) else min(4, max(len(t) for t in tw))   # at least one matched title word must be a real content word ("Sun TV": all short, 2026-09-09)
    return all(any(_match(t, x) for x in q) for t in tw) and any(len(t) >= anchor for t in tw)

def _api(lang, params, timeout):
    params = dict(params); params["format"] = "json"
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch(query, lang, timeout):
    """Search, then fetch the lead extract and categories of the top match. Returns a dict or None."""
    q = clean_query(query)
    s = _api(lang, {"action": "query", "list": "search", "srsearch": q, "srlimit": 3}, timeout)
    hits = (s.get("query") or {}).get("search") or []
    if not hits:
        return None
    top = next((h for h in hits if _overlap(q, h.get("title", ""))), None)   # the query must cover the title (see _overlap)
    if top is None:
        return None
    title = top.get("title"); score = float(top.get("wordcount", 0) or 0)   # MediaWiki search gives no score; the article size is recorded as a proxy
    e = _api(lang, {"action": "query", "prop": "extracts|categories", "exintro": 1, "explaintext": 1, "titles": title,
                    "cllimit": 50, "redirects": 1}, timeout)
    pages = (e.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {}) if pages else {}
    extract = (page.get("extract") or "").strip()
    cats = [c.get("title", "").split(":", 1)[-1] for c in page.get("categories") or []]
    if not extract:
        return None
    return {"title": page.get("title") or title, "extract": extract, "url": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(str(page.get("title") or title).replace(" ", "_")),
            "lang": lang, "score": score, "categories": cats, "search_rank": 1, "search_hits": len(hits)}


def lookup(query, lang_order=("ta", "en"), timeout=3.0, lexicon_check=None, guard_check=None, max_chars=1500):
    """Return a family-safe lead-section passage for a factual query, or None. Callbacks:
    lexicon_check(text) -> list of hits (truthy = drop); guard_check(text) -> True when the guard says unsafe (drop)."""
    if not is_enabled():
        return None
    cache = _load_cache(); now = time.time()
    for lang in lang_order:
        k = _key(query, lang)
        entry = cache.get(k)
        cached = bool(entry and now - float(entry.get("ts", 0)) < CACHE_TTL)
        if cached:
            res = entry.get("result")
        else:
            try:
                res = _fetch(query, lang, timeout)
            except Exception as ex:
                _log({"query": query, "lang": lang, "title": None, "score": None, "cached": False, "drop": f"error:{type(ex).__name__}"})
                continue
            if res:   # misses are not cached: a transient API failure must not hide an article for a day
                cache[k] = {"ts": now, "result": res}; _save_cache()
        if not res:
            _log({"query": query, "lang": lang, "title": None, "score": None, "cached": cached, "drop": "no_result"})
            continue
        res = dict(res)
        res["extract"] = res["extract"][:max_chars]
        # family-safe filtering before the text can enter the prompt
        bad_cat = blocked(res.get("categories"))
        if bad_cat:
            _log({"query": query, "lang": lang, "title": res["title"], "score": res["score"], "cached": cached, "drop": "category:" + bad_cat}); return None
        if lexicon_check is not None:
            try:
                hits = lexicon_check(res["extract"])
            except Exception:
                hits = []
            if hits:
                _log({"query": query, "lang": lang, "title": res["title"], "score": res["score"], "cached": cached, "drop": "lexicon"}); return None
        if guard_check is not None:
            try:
                unsafe = bool(guard_check(res["extract"]))
            except Exception:
                unsafe = False
            if unsafe:
                _log({"query": query, "lang": lang, "title": res["title"], "score": res["score"], "cached": cached, "drop": "guard"}); return None
        _log({"query": query, "lang": lang, "title": res["title"], "score": res["score"], "cached": cached, "drop": None})
        return res
    return None
