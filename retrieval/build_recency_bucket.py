"""Ruling A data: recency bucket from the 2026-08 Tamil Wikipedia dump (CC BY-SA 4.0)
plus Tamil Wikinews (CC BY 4.0), fetched via the MediaWiki API. Writes
data/clean/recency_v1.jsonl with {text, source_id, license, fetched, title}.
Does not run prepare.py or build shards.

  python retrieval/build_recency_bucket.py [--articles data/index/tawiki_20260801/articles.jsonl]
      [--no-wikinews] [--max-wikinews 0]
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.text import strip_wikitext

API = "https://ta.wikinews.org/w/api.php"
UA = "tamil-lm-recency/1.0 (research; contact via repo)"

def api(params, retries=8):
    """Polite MediaWiki API call: maxlag, >= 1 s spacing, Retry-After honoured on 429/503."""
    params = dict(params, format="json", formatversion="2", maxlag=5)
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(1.0)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and i < retries - 1:
                wait = e.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.isdigit() else 10 * (i + 1)); continue
            raise
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))

def fetch_wikinews(max_pages=0, min_chars=200):
    """All namespace-0 pages of ta.wikinews.org with their latest revision text."""
    out, cont, n = [], {}, 0
    while True:
        p = {"action": "query", "generator": "allpages", "gapnamespace": 0, "gaplimit": 50, "gapfilterredir": "nonredirects",
             "prop": "revisions", "rvprop": "content|timestamp", "rvslots": "main"}
        p.update(cont)
        d = api(p)
        for pg in d.get("query", {}).get("pages", []):
            revs = pg.get("revisions") or []
            if not revs:
                continue
            src = revs[0].get("slots", {}).get("main", {}).get("content", "")
            plain = strip_wikitext(src)
            if len(plain) < min_chars:
                continue
            out.append({"title": pg.get("title", ""), "text": plain, "revision_time": revs[0].get("timestamp")})
            n += 1
            if max_pages and n >= max_pages:
                return out
        if "continue" not in d:
            return out
        cont = d["continue"]
        if len(out) % 500 < 50:
            print(f"  wikinews: {len(out)} pages", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", default="data/index/tawiki_20260801/articles.jsonl")
    ap.add_argument("--out", default="data/clean/recency_v1.jsonl")
    ap.add_argument("--no-wikinews", action="store_true"); ap.add_argument("--max-wikinews", type=int, default=0)
    ap.add_argument("--min-chars", type=int, default=200)
    a = ap.parse_args()
    fetched = time.strftime("%Y-%m-%d")
    docs = chars = 0; per = {}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    tmp = a.out + ".building"
    with open(tmp, "w", encoding="utf-8") as w:
        if os.path.exists(a.articles):
            sid = "tawiki_20260801"
            for l in open(a.articles, encoding="utf-8"):
                d = json.loads(l)
                if len(d["text"]) < a.min_chars:
                    continue
                w.write(json.dumps({"text": d["title"] + "\n\n" + d["text"], "title": d["title"], "source_id": sid,
                                    "license": "CC BY-SA 4.0 (Wikimedia dump tawiki-20260801)", "fetched": fetched}, ensure_ascii=False) + "\n")
                docs += 1; chars += len(d["text"]); per[sid] = per.get(sid, 0) + 1
        else:
            print(f"articles file missing: {a.articles} (run retrieval/build_wiki_index.py first); wiki part skipped")
        if not a.no_wikinews:
            sid = "tawikinews_api"
            try:
                pages = fetch_wikinews(a.max_wikinews, a.min_chars)
            except Exception as e:
                print(f"wikinews fetch failed: {type(e).__name__}: {e}"); pages = []
            for d in pages:
                w.write(json.dumps({"text": d["title"] + "\n\n" + d["text"], "title": d["title"], "source_id": sid,
                                    "license": "CC BY 4.0 (ta.wikinews.org, latest revision " + str(d.get("revision_time")) + ")",
                                    "fetched": fetched}, ensure_ascii=False) + "\n")
                docs += 1; chars += len(d["text"]); per[sid] = per.get(sid, 0) + 1
    os.replace(tmp, a.out)
    print(f"wrote {a.out}: {docs} docs, {chars / 1e6:.1f}M chars, per source {per}, fetched {fetched}")

if __name__ == "__main__":
    main()
