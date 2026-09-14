"""Shared helpers for KB builders: cached, rate-limited fetches from
ta.wikisource.org / ta.wikipedia.org APIs and Project Madurai, plus
schema-conformant record construction.
"""
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "literature")
WS_CACHE = os.path.join(RAW, "ws_pages")
API_CACHE = os.path.join(RAW, "api_cache")
PM_CACHE = os.path.join(RAW, "pm_etexts")
KB = os.path.join(ROOT, "data", "kb")
for d in (WS_CACHE, API_CACHE, PM_CACHE, KB):
    os.makedirs(d, exist_ok=True)

UA = "tamil-lm-research/0.1 (contact: contact@timegravity.ai)"
_session = requests.Session()
_session.headers["User-Agent"] = UA
_last_req = {}  # host -> timestamp


def _throttle(host):
    now = time.time()
    prev = _last_req.get(host, 0)
    if now - prev < 1.0:
        time.sleep(1.0 - (now - prev))
    _last_req[host] = time.time()


def nfc(s):
    if s is None:
        return None
    return unicodedata.normalize("NFC", s).strip()


def _cache_key(url, params):
    blob = url + "?" + urllib.parse.urlencode(sorted((params or {}).items()))
    return hashlib.sha1(blob.encode()).hexdigest()


def api_get(url, params, cache_dir=API_CACHE, tag=""):
    """GET a JSON API endpoint with disk caching (1 req/s per host)."""
    key = _cache_key(url, params)
    path = os.path.join(cache_dir, (tag + "_" if tag else "") + key + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    host = urllib.parse.urlparse(url).netloc
    for attempt in range(4):
        _throttle(host)
        try:
            r = _session.get(url, params=params, timeout=60)
            r.raise_for_status()
            break
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    data = r.json()
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


WS_API = "https://ta.wikisource.org/w/api.php"
WP_API = "https://ta.wikipedia.org/w/api.php"


def _safe_name(title):
    return re.sub(r"[/\\\s:]+", "_", title)[:180]


def ws_wikitext(title, api=WS_API, cache_dir=WS_CACHE):
    """Fetch raw wikitext of one page, cached under ws_pages/<title>.txt."""
    path = os.path.join(cache_dir, _safe_name(title) + ".txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    data = api_get(api, {
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "titles": title, "format": "json",
        "formatversion": "2", "redirects": "1",
    }, tag="rv")
    pages = data.get("query", {}).get("pages", [])
    if not pages or "missing" in pages[0] or not pages[0].get("revisions"):
        return None
    text = pages[0]["revisions"][0]["slots"]["main"]["content"]
    with open(path, "w") as f:
        f.write(text)
    return text


def ws_parse_text(title, api=WS_API, cache_dir=WS_CACHE):
    """action=parse wikitext with templates/transclusions expanded, then strip
    HTML to plain text lines. Cached."""
    path = os.path.join(cache_dir, _safe_name(title) + ".parsed.html")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    data = api_get(api, {
        "action": "parse", "page": title, "prop": "text", "format": "json",
        "formatversion": "2", "redirects": "1",
    }, tag="parse")
    if "error" in data:
        return None
    html = data["parse"]["text"]
    with open(path, "w") as f:
        f.write(html)
    return html


def ws_allpages(prefix, api=WS_API, namespace=0):
    """Enumerate all page titles with the given prefix."""
    titles = []
    cont = {}
    while True:
        params = {
            "action": "query", "list": "allpages", "apprefix": prefix,
            "aplimit": "500", "apnamespace": str(namespace),
            "format": "json", "formatversion": "2",
        }
        params.update(cont)
        data = api_get(api, params, tag="ap")
        titles += [p["title"] for p in data["query"]["allpages"]]
        if "continue" in data:
            cont = {"apcontinue": data["continue"]["apcontinue"]}
        else:
            break
    return titles


def html_to_lines(html):
    """Strip an action=parse HTML fragment to text lines."""
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)
    # drop nav/edit/reference cruft
    html = re.sub(r"<span class=\"mw-editsection\">.*?</span>", "", html, flags=re.S)
    html = re.sub(r"<(br|BR)\s*/?>", "\n", html)
    html = re.sub(r"</(p|div|li|tr|h[1-6]|td|table|blockquote)>", "\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    import html as _h
    text = _h.unescape(html)
    lines = [nfc(l) for l in text.split("\n")]
    return [l for l in lines if l]


def strip_wikitext(wt):
    """Best-effort wikitext -> plain text lines."""
    if wt is None:
        return []
    t = wt
    t = re.sub(r"<noinclude>.*?</noinclude>", "", t, flags=re.S)
    t = re.sub(r"<includeonly>|</includeonly>", "", t)
    t = re.sub(r"<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<ref[^>]*/>", "", t)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"\{\|.*?\|\}", "", t, flags=re.S)  # tables
    # nested templates: remove innermost repeatedly
    for _ in range(6):
        t2 = re.sub(r"\{\{[^{}]*\}\}", "", t)
        if t2 == t:
            break
        t = t2
    # links: [[target|label]] -> label ; [[target]] -> target
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"\[https?://\S+\]", "", t)
    t = re.sub(r"<(br|BR)\s*/?>", "\n", t)
    t = re.sub(r"<poem[^>]*>|</poem>", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"^[=]+\s*(.*?)\s*[=]+\s*$", r"\1", t, flags=re.M)
    lines = [nfc(l) for l in t.split("\n")]
    return [l for l in lines if l]


def fetch_url(url, cache_name, cache_dir=PM_CACHE, encoding="utf-8"):
    """Fetch an arbitrary URL (e.g. Project Madurai etext) with caching."""
    path = os.path.join(cache_dir, cache_name)
    if os.path.exists(path):
        with open(path, encoding=encoding, errors="replace") as f:
            return f.read()
    host = urllib.parse.urlparse(url).netloc
    _throttle(host)
    r = _session.get(url, timeout=120)
    r.raise_for_status()
    r.encoding = encoding
    text = r.text
    with open(path, "w", encoding=encoding) as f:
        f.write(text)
    return text


def wp_extract(title):
    """Tamil Wikipedia plain-text intro extract for a title (cached)."""
    data = api_get(WP_API, {
        "action": "query", "prop": "extracts", "explaintext": "1",
        "exintro": "1", "titles": title, "format": "json",
        "formatversion": "2", "redirects": "1",
    }, tag="wpext")
    pages = data.get("query", {}).get("pages", [])
    if not pages or "missing" in pages[0]:
        return None
    return nfc(pages[0].get("extract") or "") or None


def wp_full_extract(title):
    data = api_get(WP_API, {
        "action": "query", "prop": "extracts", "explaintext": "1",
        "titles": title, "format": "json",
        "formatversion": "2", "redirects": "1",
    }, tag="wpfull")
    pages = data.get("query", {}).get("pages", [])
    if not pages or "missing" in pages[0]:
        return None
    return nfc(pages[0].get("extract") or "") or None


def make_unit(work, work_en, unit_type, number, section, text, verbatim,
              sources, author=None, author_en=None, period=None,
              urai=None, translation_en=None, transliteration=None,
              themes=None, verified=False):
    assert isinstance(text, list) and all(isinstance(l, str) for l in text)
    text = [nfc(l) for l in text if nfc(l)]
    unit = {
        "work": nfc(work), "work_en": work_en, "tier": 2,
        "unit_type": unit_type, "number": number,
        "section": section, "text": text, "verbatim_text": bool(verbatim),
        "urai": urai or {}, "translation_en": translation_en,
        "transliteration": transliteration, "themes": themes or [],
        "author": nfc(author) if author else author,
        "author_en": author_en, "period": period, "sources": sources,
        "verified_second_source": bool(verified),
    }
    for k, v in unit.items():
        _no_emdash(v)
    return unit


def _no_emdash(v):
    if isinstance(v, str):
        assert "—" not in v, "em dash found: " + v[:80]
    elif isinstance(v, list):
        for x in v:
            _no_emdash(x)
    elif isinstance(v, dict):
        for k, x in v.items():
            _no_emdash(k)
            _no_emdash(x)


def write_jsonl(path, units):
    with open(path, "w") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    print(f"wrote {len(units)} units -> {path}")


def clean_em_dashes(s):
    return (s or "").replace("—", "-")
