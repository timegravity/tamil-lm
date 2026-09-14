"""Build the BM25 index over a Wikipedia pages-articles dump (no external libs).

  python retrieval/build_wiki_index.py --dump data/raw/wiki/tawiki-20260801-pages-articles.xml.bz2 \
      --out data/index/tawiki_20260801

Stage 1 (resumable, idempotent): stream-parse the bz2 XML, keep namespace-0
non-redirect pages, strip wikitext, write articles.jsonl (title, text) and
passages.jsonl (~200-word chunks with title). Written to *.building then renamed.
Stage 2: BM25 CSR index over title + passage tokens (retrieval/bm25.py), plus
passage_offsets.npy for random access. Skipped when meta.json already exists.
"""
import argparse, bz2, json, os, sys, time
import xml.etree.ElementTree as ET
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retrieval.text import strip_wikitext, chunk_words, toks
from retrieval.bm25 import build as build_bm25

REDIRECT_PREFIXES = ("#redirect", "#வழிமாற்று", "#திருப்பிவிடு")

def parse_dump(dump, out_dir, min_chars=200):
    art_fn = os.path.join(out_dir, "articles.jsonl"); pas_fn = os.path.join(out_dir, "passages.jsonl")
    if os.path.exists(art_fn) and os.path.exists(pas_fn):
        print("stage 1: articles.jsonl and passages.jsonl exist; skipping parse"); return
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time(); pages = kept = redirects = other_ns = short = npass = 0
    with open(art_fn + ".building", "w", encoding="utf-8") as wa, open(pas_fn + ".building", "w", encoding="utf-8") as wp:
        with bz2.open(dump, "rb") as fh:
            for ev, el in ET.iterparse(fh, events=("end",)):
                tag = el.tag.rsplit("}", 1)[-1]
                if tag != "page":
                    continue
                pages += 1
                ns = el.findtext("{*}ns") or "0"
                title = el.findtext("{*}title") or ""
                if ns != "0":
                    other_ns += 1; el.clear(); continue
                if el.find("{*}redirect") is not None:
                    redirects += 1; el.clear(); continue
                text = ""
                rev = el.find("{*}revision")
                if rev is not None:
                    text = rev.findtext("{*}text") or ""
                if text.lstrip()[:20].lower().startswith(REDIRECT_PREFIXES):
                    redirects += 1; el.clear(); continue
                plain = strip_wikitext(text)
                el.clear()
                if len(plain) < min_chars:
                    short += 1; continue
                kept += 1
                wa.write(json.dumps({"title": title, "text": plain}, ensure_ascii=False) + "\n")
                for c in chunk_words(plain, target=200):
                    wp.write(json.dumps({"title": title, "text": c}, ensure_ascii=False) + "\n"); npass += 1
                if kept % 10000 == 0:
                    print(f"  {pages} pages, {kept} kept, {npass} passages, {time.time() - t0:.0f}s", flush=True)
    os.replace(art_fn + ".building", art_fn); os.replace(pas_fn + ".building", pas_fn)
    stats = {"pages": pages, "articles": kept, "redirects": redirects, "other_ns": other_ns, "short": short, "passages": npass,
             "dump": os.path.basename(dump), "parse_seconds": round(time.time() - t0)}
    json.dump(stats, open(os.path.join(out_dir, "parse_stats.json"), "w"), indent=1)
    print("stage 1 done:", stats)

def build_index(out_dir):
    if os.path.exists(os.path.join(out_dir, "meta.json")) and os.path.exists(os.path.join(out_dir, "passage_offsets.npy")):
        print("stage 2: index exists; skipping"); return
    pas_fn = os.path.join(out_dir, "passages.jsonl")
    t0 = time.time()
    offsets = []
    def token_iter():
        with open(pas_fn, "rb") as fh:
            pos = 0
            for line in fh:
                offsets.append(pos); pos += len(line)
                p = json.loads(line)
                yield toks(p["title"] + " " + p["text"])
    n, V, P = build_bm25(out_dir, token_iter())
    np.save(os.path.join(out_dir, "passage_offsets.npy"), np.array(offsets, dtype=np.int64))
    print(f"stage 2 done: {n} passages, vocab {V}, postings {P}, {time.time() - t0:.0f}s")

def build_family_safe(base_dir, out_dir):
    """Family-safe index (ruling 2026-09-08): copy the base index's passages and articles, dropping any passage
    (or article) with a severe lexicon hit (severity slur or sexual per family_safe.check), then build BM25 over
    the survivors. Writes <out_dir>/family_safe_report.json with counts."""
    import family_safe as FS
    FS.load()
    if not FS._SET:
        raise SystemExit("family_safe: data/lexicon.hashed missing or empty")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time(); stats = {"base": base_dir, "passages_in": 0, "passages_dropped": 0, "articles_in": 0, "articles_dropped": 0, "dropped_by_severity": {}}
    def severe(text):
        hs = [h for h in FS.check(text) if (h.get("severity") or "profanity") in FS.SEVERE]
        return hs
    for name, key in (("passages.jsonl", "passages"), ("articles.jsonl", "articles")):
        src = os.path.join(base_dir, name); dst = os.path.join(out_dir, name)
        with open(src, encoding="utf-8") as fi, open(dst + ".building", "w", encoding="utf-8") as fo:
            for line in fi:
                stats[key + "_in"] += 1
                d = json.loads(line)
                hs = severe(d.get("title", "") + " " + d.get("text", ""))
                if hs:
                    stats[key + "_dropped"] += 1
                    for h in hs: stats["dropped_by_severity"][h.get("severity")] = stats["dropped_by_severity"].get(h.get("severity"), 0) + 1
                    continue
                fo.write(line if line.endswith("\n") else line + "\n")
        os.replace(dst + ".building", dst)
    stats["filter_seconds"] = round(time.time() - t0)
    json.dump(stats, open(os.path.join(out_dir, "family_safe_report.json"), "w"), indent=1)
    print("family-safe filter:", stats)
    build_index(out_dir)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="data/raw/wiki/tawiki-20260801-pages-articles.xml.bz2")
    ap.add_argument("--out", default="data/index/tawiki_20260801")
    ap.add_argument("--family-safe", action="store_true", help="build <out>_fs from the base index with severe-hit passages dropped (needs data/lexicon.hashed)")
    a = ap.parse_args()
    if a.family_safe:
        build_family_safe(a.out, a.out + "_fs")
        print("FAMILY-SAFE WIKI INDEX DONE")
    else:
        parse_dump(a.dump, a.out)
        build_index(a.out)
        print("WIKI INDEX DONE")
