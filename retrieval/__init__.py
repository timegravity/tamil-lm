"""Pluggable retrieval for serve.py (Phase 5b).

Retriever(config_path) loads the sources listed in retrieval/config.yaml. Each
source implements search(query, k) -> list of passages
{"text", "title", "source", "score", "meta"}; the Retriever normalises scores
per source, applies the source weight, and returns the merged top-k.
Source types: kb (literature KB), wiki_dump (prebuilt BM25 over a Wikipedia
dump), folder (local .txt/.md/.jsonl, indexed lazily). Live Wikipedia lookups are a tool in
retrieval/wiki_live.py, not a source; general web search is not part of the design.
"""
import glob, json, os, time, urllib.parse, urllib.request
import yaml
from .bm25 import BM25Index, build as build_bm25
from .text import toks, chunk_words, nfc
from . import kb as kbmod

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(HERE, "config.yaml")

class Passage(dict):
    pass

class KBSource:
    type = "kb"
    def __init__(self, cfg):
        self.name = cfg["name"]; self.k = int(cfg.get("k", 3)); self.weight = float(cfg.get("weight", 1.0))
        self.units = kbmod.load_units(cfg.get("glob", "data/kb/*.jsonl"))
        d = cfg.get("index_dir", "data/index/literature_kb")
        marker = os.path.join(d, "meta.json")
        newest = max((os.path.getmtime(f) for f in glob.glob(cfg.get("glob", "data/kb/*.jsonl"))), default=0)
        if not BM25Index.exists(d) or os.path.getmtime(marker) < newest:
            build_bm25(d, (toks(kbmod.unit_text(u)) for u in self.units))
        self.idx = BM25Index(d)
    def search(self, query, k=None):
        out = []
        for i, s in self.idx.search(query, k or self.k):
            u = self.units[i]
            out.append(Passage(text=kbmod.format_unit(u), title=f"{u.get('work')} {u.get('number', '')}".strip(),
                               source=self.name, score=s, meta={"unit": u}))
        return out

_EMBEDDERS = {}   # model name -> Embedder, shared across sources

class WikiDumpSource:
    """BM25 over the Wikipedia passages, optionally fused with a dense index (retrieval/dense.py; ruling 2026-09-09).

    Config keys on the source: dense: {model, index_dir, weight, fusion: rrf | minmax, top_n}. The BM25-only path
    stays the default whenever the dense index or the embedder is missing, or DENSE_RETRIEVAL=0 is set. Every hit
    keeps the Passage contract: score is the (title-boosted) BM25 score of that passage, so Retriever.search's
    score_raw still carries what serve.py thresholds on; meta adds dense_score, fused_rank, bm25_rank, dense_rank
    and fusion (the method used: rrf, minmax or bm25)."""
    type = "wiki_dump"
    RRF_K = 60
    def __init__(self, cfg):
        self.name = cfg["name"]; self.k = int(cfg.get("k", 4)); self.weight = float(cfg.get("weight", 1.0))
        self.dir = cfg["index_dir"]
        fs_dir = cfg.get("family_safe_index_dir")
        if os.environ.get("FAMILY_SAFE", "1") != "0" and fs_dir and BM25Index.exists(fs_dir) and os.path.exists(os.path.join(fs_dir, "passages.jsonl")):
            self.dir = fs_dir   # family-safe index (severe lexicon hits dropped at build time) when FAMILY_SAFE=1
        self.ok = BM25Index.exists(self.dir) and os.path.exists(os.path.join(self.dir, "passages.jsonl"))
        self.dense = None; self.embedder = None; self.fusion = "bm25"; self.dense_weight = 1.0; self.dense_top_n = 50
        if not self.ok:
            print(f"[retrieval] source {self.name} disabled: index missing at {self.dir} (run retrieval/build_wiki_index.py)")
            return
        self.idx = BM25Index(self.dir)
        self.offsets = __import__("numpy").load(os.path.join(self.dir, "passage_offsets.npy"))
        self.fh = open(os.path.join(self.dir, "passages.jsonl"), "rb")
        self._init_dense(cfg.get("dense") or {})
    def _init_dense(self, dcfg):
        """Load the dense index and its query encoder; any failure leaves the BM25-only path (printed, never raised)."""
        if not dcfg or os.environ.get("DENSE_RETRIEVAL", "1") == "0":
            return
        try:
            from .dense import DenseIndex, Embedder, index_dir_for
            model = dcfg.get("model")
            d = dcfg.get("index_dir") or (index_dir_for(self.dir, model) if model else None)
            if not d or not DenseIndex.exists(d):
                print(f"[retrieval] {self.name}: dense index missing at {d}; BM25 only (build with retrieval/dense.py)"); return
            t0 = time.time()
            dense = DenseIndex(d)
            if dense.N != self.idx.N or not dense.matches_passages(os.path.join(self.dir, "passages.jsonl")):
                print(f"[retrieval] {self.name}: dense index {d} does not match the BM25 index ({dense.N} vs {self.idx.N} passages); BM25 only"); return
            model = model or dense.model
            if model != dense.model:
                print(f"[retrieval] {self.name}: config model {model} but index built with {dense.model}; using the index's model")
                model = dense.model
            if model not in _EMBEDDERS:   # one query encoder per model, shared by the Wikipedia index and every pack (2026-09-10)
                _EMBEDDERS[model] = Embedder(model)
            self.embedder = _EMBEDDERS[model]
            self.dense = dense
            self.fusion = str(dcfg.get("fusion", "rrf")).lower()
            if self.fusion not in ("rrf", "minmax"):
                print(f"[retrieval] {self.name}: unknown fusion {self.fusion}; using rrf"); self.fusion = "rrf"
            self.dense_weight = float(dcfg.get("weight", 1.0)); self.dense_top_n = int(dcfg.get("top_n", 50))
            print(f"[retrieval] {self.name}: dense {model} ({dense.N} x {dense.dim}, {dense.device}) fusion={self.fusion} weight={self.dense_weight} in {time.time() - t0:.1f}s")
        except Exception as e:
            print(f"[retrieval] {self.name}: dense retrieval unavailable ({type(e).__name__}: {e}); BM25 only")
            self.dense = None; self.embedder = None; self.fusion = "bm25"
    def _passage(self, i):
        self.fh.seek(int(self.offsets[i])); return json.loads(self.fh.readline())
    def _boost(self, s, qn, title):
        tn = " ".join(toks(title))
        if qn and tn == qn:
            return s * 1.5          # exact title match: the article about the thing asked
        if qn and qn in tn:
            return s * 1.15
        return s
    def _bm25_scores_for(self, query, ids):
        """BM25 scores of specific passages (dense-only candidates outside the BM25 top list), same formula as BM25Index.search."""
        import math
        import numpy as np
        from .text import STOPWORDS
        idx = self.idx
        q = toks(query); q = [t for t in q if t not in STOPWORDS] or q
        ids = np.asarray(sorted(set(int(i) for i in ids)), dtype=np.int64)
        scores = {int(i): 0.0 for i in ids}
        if not q or len(ids) == 0:
            return scores
        k1, b = 1.5, 0.75
        norm = k1 * (1 - b + b * idx.dl[ids] / idx.avgdl)
        for t in set(q):
            tid = idx.vocab.get(t)
            if tid is None:
                continue
            s, e = int(idx.ptr[tid]), int(idx.ptr[tid + 1])
            if e <= s:
                continue
            docs = np.asarray(idx.doc[s:e]); pos = np.searchsorted(docs, ids)
            pos = np.minimum(pos, len(docs) - 1)
            hit = docs[pos] == ids
            if not hit.any():
                continue
            tf = np.asarray(idx.tf[s:e])[pos[hit]]
            idf = math.log(1 + (idx.N - (e - s) + 0.5) / ((e - s) + 0.5))
            contrib = idf * tf * (k1 + 1) / (tf + norm[hit])
            for i, c in zip(ids[hit], contrib):
                scores[int(i)] += float(c)
        return scores
    def _dense_hits(self, query, n):
        try:
            v = self.embedder.encode([query], kind="query")[0]
            return self.dense.search(v, n)
        except Exception as e:
            print(f"[retrieval] {self.name}: dense search failed ({type(e).__name__}: {e}); BM25 only for this query")
            return []
    def search(self, query, k=None, fusion=None):
        """fusion: None (the configured method), "bm25" (lexical only), "dense" (dense only), "rrf" or "minmax"."""
        if not self.ok:
            return []
        kk = k or self.k
        from .text import STOPWORDS
        qn = " ".join(t for t in toks(query) if t not in STOPWORDS)
        use = fusion or self.fusion
        if self.dense is None or use == "bm25":
            use = "bm25"
        top_n = self.dense_top_n if use != "bm25" else max(kk * 5, 20)
        bm = self.idx.search(query, top_n) if use != "dense" else []
        dn = self._dense_hits(query, top_n) if use != "bm25" else []
        if use != "bm25" and not dn:
            use = "bm25"
            if not bm:
                bm = self.idx.search(query, max(kk * 5, 20))
        bm_rank = {i: r for r, (i, _) in enumerate(bm)}; dn_rank = {i: r for r, (i, _) in enumerate(dn)}
        bm_score = {i: s for i, s in bm}; dn_score = {i: s for i, s in dn}
        cand = list(dict.fromkeys([i for i, _ in bm] + [i for i, _ in dn]))
        if not cand:
            return []
        missing = [i for i in cand if i not in bm_score]
        if missing:
            bm_score.update(self._bm25_scores_for(query, missing))
        titles = {i: self._passage(i) for i in cand}
        boosted = {i: self._boost(bm_score.get(i, 0.0), qn, titles[i]["title"]) for i in cand}
        if use == "bm25":
            fused = {i: boosted[i] for i in cand}
        elif use == "dense":
            fused = {i: dn_score[i] for i in cand}
        elif use == "minmax":
            def mm(d):
                if not d:
                    return {}
                lo, hi = min(d.values()), max(d.values())
                return {i: (v - lo) / (hi - lo) if hi > lo else 1.0 for i, v in d.items()}
            bmn = mm({i: boosted[i] for i in bm_rank}); dnn = mm(dn_score)
            fused = {i: bmn.get(i, 0.0) + self.dense_weight * dnn.get(i, 0.0) for i in cand}
        else:   # rrf
            K = self.RRF_K
            fused = {i: (1.0 / (K + bm_rank[i] + 1) if i in bm_rank else 0.0) + self.dense_weight * (1.0 / (K + dn_rank[i] + 1) if i in dn_rank else 0.0) for i in cand}
        order = sorted(cand, key=lambda i: (-fused[i], bm_rank.get(i, 10**9), dn_rank.get(i, 10**9)))
        out = []
        for r, i in enumerate(order[:kk]):
            p = titles[i]
            meta = {"title": p["title"], "fusion": use, "fused_rank": r + 1, "fused_score": round(float(fused[i]), 6),
                    "bm25_rank": (bm_rank[i] + 1) if i in bm_rank else None, "dense_rank": (dn_rank[i] + 1) if i in dn_rank else None,
                    "dense_score": round(float(dn_score[i]), 4) if i in dn_score else None, "passage_id": int(i)}
            meta.update({k: v for k, v in (p.get("meta") or {}).items() if k not in meta})   # the stored chunk fields (dish, topic, licence, dated ...)
            out.append(Passage(text=p["text"], title=p["title"], source=self.name, score=float(boosted[i]), meta=meta))
        return out

class FolderSource:
    type = "folder"
    def __init__(self, cfg):
        self.name = cfg["name"]; self.k = int(cfg.get("k", 4)); self.weight = float(cfg.get("weight", 1.0))
        self.path = cfg["path"]; self.dir = cfg.get("index_dir", f"data/index/{self.name}")
        self.ok = os.path.isdir(self.path)
        if not self.ok:
            print(f"[retrieval] source {self.name} disabled: folder {self.path} not found"); return
        files = self._files()
        newest = max((os.path.getmtime(f) for f in files), default=0)
        marker = os.path.join(self.dir, "meta.json")
        if not BM25Index.exists(self.dir) or os.path.getmtime(marker) < newest:
            self._build(files)
        self.idx = BM25Index(self.dir)
        self.passages = [json.loads(l) for l in open(os.path.join(self.dir, "passages.jsonl"), encoding="utf-8")]
    def _files(self):
        out = []
        for root, _, fs in os.walk(self.path):
            out += [os.path.join(root, f) for f in fs if f.endswith((".txt", ".md", ".jsonl"))]
        return sorted(out)
    def _build(self, files):
        os.makedirs(self.dir, exist_ok=True)
        passages = []
        for f in files:
            rel = os.path.relpath(f, self.path)
            if f.endswith(".jsonl"):
                for l in open(f, encoding="utf-8"):
                    try:
                        d = json.loads(l)
                    except Exception:
                        continue
                    for c in chunk_words(str(d.get("text", "")), target=200):
                        passages.append({"title": d.get("title") or rel, "text": c, "file": rel})
            else:
                for c in chunk_words(open(f, encoding="utf-8", errors="replace").read(), target=200):
                    passages.append({"title": rel, "text": c, "file": rel})
        with open(os.path.join(self.dir, "passages.jsonl"), "w", encoding="utf-8") as w:
            for p in passages:
                w.write(json.dumps(p, ensure_ascii=False) + "\n")
        build_bm25(self.dir, (toks(p["title"] + " " + p["text"]) for p in passages))
        print(f"[retrieval] built folder index {self.name}: {len(files)} files, {len(passages)} passages")
    def search(self, query, k=None):
        if not self.ok:
            return []
        return [Passage(text=self.passages[i]["text"], title=self.passages[i]["title"], source=self.name, score=s,
                        meta={"file": self.passages[i]["file"]}) for i, s in self.idx.search(query, k or self.k)]

SOURCE_TYPES = {c.type: c for c in (KBSource, WikiDumpSource, FolderSource)}   # general web search dropped from the design (2026-09-08); live Wikipedia is retrieval/wiki_live.py, wired in serve.py

class Retriever:
    def __init__(self, config_path=DEFAULT_CONFIG, only=None):
        cfg = yaml.safe_load(open(config_path))
        self.top_k = int(cfg.get("top_k", 4))
        self.sources = []
        for s in cfg.get("sources", []):
            if only and s["name"] not in only:
                continue
            cls = SOURCE_TYPES.get(s.get("type"))
            if cls is None:
                print(f"[retrieval] unknown source type {s.get('type')} for {s.get('name')}; skipped"); continue
            t0 = time.time()
            self.sources.append(cls(s))
            print(f"[retrieval] loaded {s['name']} ({s['type']}) in {time.time() - t0:.1f}s")
    def source(self, name):
        return next((s for s in self.sources if s.name == name), None)
    def search(self, query, k=None):
        merged = []
        for src in self.sources:
            hits = src.search(query)
            if not hits:
                continue
            # rank across sources by the raw BM25 score times the source weight; per-source normalisation
            # made every source's best hit look equally good (a weak literature match outranked the
            # right Wikipedia article for a plain recipe question, 2026-09-07)
            # A source's own order is kept (hybrid wiki hits are fused-rank ordered but carry raw BM25 scores,
            # 2026-09-09): the sort key is the suffix max of the raw score along the source's order, which is
            # the raw score itself for BM25-only sources; score_raw stays the hit's own raw BM25 score.
            run = 0.0; keys = []
            for h in reversed(hits):
                run = max(run, float(h["score"])); keys.append(run)
            for h, key in zip(hits, reversed(keys)):
                h["score_raw"] = h["score"]; h["score"] = src.weight * key
                merged.append(h)
        merged.sort(key=lambda h: -h["score"])   # stable: ties keep the source order
        return merged[: k or self.top_k]

def format_passages(hits):
    out = []
    for h in hits:
        if h["source"] == "literature_kb":
            out.append(h["text"])
        else:
            out.append(f"[{h['source']}: {h['title']}]\n{h['text']}")
    return "\n\n".join(out)
