"""Build the BM25 and dense indexes for a retrieval pack (design: docs/retrieval_packs.md).

A pack is a directory with chunks.jsonl, a manifest, a licence file and a family-safe scan record.
This writes index/bm25 and index/dense_<tag> inside the pack, and refuses to build when the pack is
missing any of the three required records, so an unlicensed or unscanned pack cannot be indexed.

  .venv/bin/python build_pack_index.py --pack data/packs/cooking [--model BAAI/bge-m3] [--no-dense]

GPU: the dense build loads the embedder; it refuses to start while a trainer is running unless
--allow-gpu-busy is passed.
"""
import argparse, json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from retrieval.bm25 import build as build_bm25
from retrieval.text import toks

REQUIRED = ("chunks.jsonl", "manifest.json", "LICENSES.md", "family_safe_report.json")

def trainer_running():
    try:
        out = subprocess.run(["pgrep", "-f", r"[s]ft\.py --base"], capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--allow-gpu-busy", action="store_true")
    ap.add_argument("--batch-size", type=int, default=48)
    a = ap.parse_args()

    missing = [f for f in REQUIRED if not os.path.exists(os.path.join(a.pack, f))]
    if missing:
        raise SystemExit(f"pack {a.pack} is missing {missing}; a pack without a licence file and a family-safe record is not indexed")
    chunks = [json.loads(l) for l in open(os.path.join(a.pack, "chunks.jsonl"), encoding="utf-8") if l.strip()]
    man = json.load(open(os.path.join(a.pack, "manifest.json"), encoding="utf-8"))
    # pack controls (2026-09-10): the scan record must be the one produced from this exact chunks.jsonl
    rep = json.load(open(os.path.join(a.pack, "family_safe_report.json"), encoding="utf-8"))
    if rep.get("chunks_sha256"):
        import hashlib
        cur = hashlib.sha256(open(os.path.join(a.pack, "chunks.jsonl"), "rb").read()).hexdigest()
        if cur != rep["chunks_sha256"]:
            raise SystemExit("chunks.jsonl does not match the family-safe scan record; run pack_scan.py first")
    else:
        raise SystemExit("family_safe_report.json carries no chunks_sha256; run pack_scan.py (any-hit policy) before indexing")
    if man.get("chunks") not in (None, len(chunks)):
        raise SystemExit(f"manifest says {man.get('chunks')} chunks but chunks.jsonl has {len(chunks)}")
    print(f"[pack] {a.pack}: {len(chunks)} chunks")

    # BM25 over "title + section + text", the same shape the Wikipedia index uses
    idx_dir = os.path.join(a.pack, "index")   # BM25 files and passages.jsonl live together, the layout WikiDumpSource reads
    os.makedirs(idx_dir, exist_ok=True)
    def text_of(c):
        return " ".join(str(c.get(k) or "") for k in ("title", "section", "text"))
    t0 = time.time()
    build_bm25(idx_dir, (toks(text_of(c)) for c in chunks))
    # passages file in the same format the retriever reads, with byte offsets
    pj = os.path.join(a.pack, "index", "passages.jsonl")
    offs = []
    with open(pj, "wb") as f:
        for c in chunks:
            offs.append(f.tell())
            f.write((json.dumps({"title": c.get("title", ""), "text": c.get("text", ""), "meta": {k: c.get(k) for k in ("id", "lang", "source", "url", "license", "machine_translated", "dish", "section", "topic", "crop", "service", "official_site", "dated", "as_of") if k in c}}, ensure_ascii=False) + "\n").encode("utf-8"))
    import numpy as np
    np.save(os.path.join(a.pack, "index", "passage_offsets.npy"), np.array(offs, dtype=np.int64))
    print(f"[pack] bm25 built in {time.time()-t0:.0f}s -> {idx_dir}")

    if a.no_dense:
        print("[pack] dense build skipped (--no-dense)")
        return
    if trainer_running() and not a.allow_gpu_busy:
        raise SystemExit("a trainer is on the GPU; rerun after it finishes or pass --allow-gpu-busy")
    from retrieval.dense import build as build_dense, index_dir_for
    out = index_dir_for(os.path.join(a.pack, "index"), a.model)
    t0 = time.time()
    build_dense(os.path.join(a.pack, "index"), a.model, out_dir=out, batch_size=a.batch_size)
    print(f"[pack] dense built in {time.time()-t0:.0f}s -> {out}")
    man["indexes"] = {"bm25": idx_dir, "dense": out, "dense_model": a.model, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    man["chunks"] = len(chunks)
    json.dump(man, open(os.path.join(a.pack, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
