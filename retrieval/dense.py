"""Dense retrieval over the Wikipedia passages (server-side only; the Android APK stays BM25-only).

Build (one index per embedder, from the same passages.jsonl the BM25 index was built from):
  python retrieval/dense.py --index-dir data/index/tawiki_20260801_fs --model BAAI/bge-m3
  python retrieval/dense.py --index-dir data/index/tawiki_20260801_fs --model intfloat/multilingual-e5-base

Output dir: <index_dir>_dense_<model_tag>/ with emb.npy (float16, N x D, memmap-able), meta.json
(model, dim, count, build date, passages file size so a rebuilt BM25 index is detected).
Search: cosine via a torch matmul on the GPU when available (the whole matrix is 0.4 to 0.6 GB in
float16), chunked numpy otherwise. The query encoder stays resident (about 1.1 GB for bge-m3, 0.6 GB
for multilingual-e5-base in float16); the passage encoder is released after a build.
"""
import argparse, datetime, gc, json, os, sys, time
import numpy as np

MODELS = {
    # pool: cls (bge-m3 dense head) or mean (e5); prefixes per the model cards
    "BAAI/bge-m3": {"tag": "bgem3", "pool": "cls", "q_prefix": "", "p_prefix": "", "max_len": 512},
    "intfloat/multilingual-e5-base": {"tag": "e5base", "pool": "mean", "q_prefix": "query: ", "p_prefix": "passage: ", "max_len": 512},
    "intfloat/multilingual-e5-large": {"tag": "e5large", "pool": "mean", "q_prefix": "query: ", "p_prefix": "passage: ", "max_len": 512},
    "intfloat/multilingual-e5-small": {"tag": "e5small", "pool": "mean", "q_prefix": "query: ", "p_prefix": "passage: ", "max_len": 512},
}

def model_spec(name):
    if name in MODELS:
        return dict(MODELS[name])
    low = name.lower()
    if "e5" in low:
        return {"tag": low.split("/")[-1].replace("-", ""), "pool": "mean", "q_prefix": "query: ", "p_prefix": "passage: ", "max_len": 512}
    return {"tag": low.split("/")[-1].replace("-", ""), "pool": "cls", "q_prefix": "", "p_prefix": "", "max_len": 512}

def index_dir_for(base_index_dir, model):
    return base_index_dir.rstrip("/") + "_dense_" + model_spec(model)["tag"]

class Embedder:
    """Sentence embedder on top of transformers AutoModel: float16 on CUDA, float32 on CPU, L2-normalised output."""
    def __init__(self, model, device=None, max_len=None):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.model_name = model; self.spec = model_spec(model)
        self.max_len = int(max_len or self.spec["max_len"])
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
        self.tok = AutoTokenizer.from_pretrained(model)
        kw = {"dtype": self.dtype}
        try:
            self.net = AutoModel.from_pretrained(model, add_pooling_layer=False, **kw)
        except TypeError:
            self.net = AutoModel.from_pretrained(model, **kw)
        self.net.to(self.device).eval()
        self.dim = int(self.net.config.hidden_size)

    def _pool(self, out, mask):
        import torch
        h = out.last_hidden_state.float()   # pool in float32 (a 512-token mean in float16 loses precision)
        if self.spec["pool"] == "cls":
            v = h[:, 0]
        else:
            m = mask.unsqueeze(-1).to(h.dtype)
            v = (h * m).sum(1) / m.sum(1).clamp(min=1e-6)
        return torch.nn.functional.normalize(v, dim=-1)

    def encode(self, texts, kind="query", batch_size=32, max_len=None):
        """texts: list of str. kind: query | passage (selects the model's prefix). Returns float32 array (n, dim)."""
        import torch
        prefix = self.spec["q_prefix"] if kind == "query" else self.spec["p_prefix"]
        ml = int(max_len or self.max_len)
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        with torch.inference_mode():
            for i in range(0, len(texts), batch_size):
                batch = [prefix + t for t in texts[i:i + batch_size]]
                enc = self.tok(batch, padding=True, truncation=True, max_length=ml, return_tensors="pt").to(self.device)
                out[i:i + len(batch)] = self._pool(self.net(**enc), enc["attention_mask"]).cpu().numpy()
        return out

    def close(self):
        import torch
        self.net = None; self.tok = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

class DenseIndex:
    """float16 embedding matrix with cosine top-k. GPU-resident torch tensor when CUDA is available, numpy memmap otherwise."""
    FILES = ("emb.npy", "meta.json")

    def __init__(self, d, device=None):
        self.dir = d
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.model = self.meta["model"]; self.dim = int(self.meta["dim"]); self.N = int(self.meta["count"])
        self.emb = np.load(os.path.join(d, "emb.npy"), mmap_mode="r")
        assert self.emb.shape == (self.N, self.dim), f"emb shape {self.emb.shape} != meta ({self.N}, {self.dim})"
        self.device = "cpu"; self._t = None
        try:
            import torch
            dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
            if dev.startswith("cuda"):
                self._t = torch.from_numpy(np.array(self.emb, dtype=np.float16)).to(dev)   # float16, N x D (a copy: memmaps are read-only)
                self.device = dev
        except Exception as e:
            print(f"[dense] GPU matrix unavailable ({e}); numpy fallback")
            self._t = None; self.device = "cpu"

    @staticmethod
    def exists(d):
        return all(os.path.exists(os.path.join(d, f)) for f in DenseIndex.FILES)

    def matches_passages(self, passages_fn):
        """True when the index was built from a passages file of the same size (a rebuilt BM25 index would shift passage ids)."""
        pb = self.meta.get("passages_bytes")
        return pb is None or (os.path.exists(passages_fn) and os.path.getsize(passages_fn) == pb)

    def search(self, qvec, k=50):
        """qvec: float32 (dim,) normalised. Returns list of (passage_id, cosine) sorted descending."""
        k = min(int(k), self.N)
        if k <= 0:
            return []
        if self._t is not None:
            import torch
            q = torch.from_numpy(np.asarray(qvec, dtype=np.float32)).to(self.device, dtype=self._t.dtype)
            s = torch.mv(self._t, q).float()
            v, i = torch.topk(s, k)
            return list(zip(i.cpu().tolist(), v.cpu().tolist()))
        q = np.asarray(qvec, dtype=np.float32)
        best_i = np.zeros(0, dtype=np.int64); best_s = np.zeros(0, dtype=np.float32)
        step = 32768
        for s0 in range(0, self.N, step):
            chunk = np.asarray(self.emb[s0:s0 + step], dtype=np.float32) @ q
            kk = min(k, len(chunk))
            top = np.argpartition(-chunk, kk - 1)[:kk]
            best_i = np.concatenate([best_i, top + s0]); best_s = np.concatenate([best_s, chunk[top]])
            if len(best_i) > k:
                keep = np.argpartition(-best_s, k - 1)[:k]
                best_i, best_s = best_i[keep], best_s[keep]
        order = np.argsort(-best_s)
        return [(int(best_i[j]), float(best_s[j])) for j in order]

def iter_passages(passages_fn):
    with open(passages_fn, "rb") as fh:
        for line in fh:
            p = json.loads(line)
            yield p.get("title", ""), p.get("text", "")

def build(base_index_dir, model, out_dir=None, batch_size=64, max_len=None, device=None, limit=None):
    """Encode title + passage text for every passage in <base_index_dir>/passages.jsonl (in file order, so passage
    ids line up with the BM25 index) into <out_dir>/emb.npy float16. Length-sorted batches cut padding; the passage
    encoder is released afterwards."""
    import torch
    passages_fn = os.path.join(base_index_dir, "passages.jsonl")
    out_dir = out_dir or index_dir_for(base_index_dir, model)
    t0 = time.time()
    texts = [(t + "\n" + x) if t else x for t, x in iter_passages(passages_fn)]
    if limit:
        texts = texts[:int(limit)]
    N = len(texts)
    print(f"[dense] {N} passages read in {time.time() - t0:.0f}s; loading {model}", flush=True)
    emb = Embedder(model, device=device, max_len=max_len)
    ml = emb.max_len
    tmp = out_dir + ".building"; os.makedirs(tmp, exist_ok=True)
    arr = np.lib.format.open_memmap(os.path.join(tmp, "emb.npy"), mode="w+", dtype=np.float16, shape=(N, emb.dim))
    order = np.argsort([-len(t) for t in texts], kind="stable")   # longest first: OOM (if any) shows up in the first batch
    t1 = time.time(); done = 0; ntok = 0
    with torch.inference_mode():
        for i in range(0, N, batch_size):
            ids = order[i:i + batch_size]
            batch = [emb.spec["p_prefix"] + texts[j] for j in ids]
            enc = emb.tok(batch, padding=True, truncation=True, max_length=ml, return_tensors="pt").to(emb.device)
            ntok += int(enc["attention_mask"].sum())
            v = emb._pool(emb.net(**enc), enc["attention_mask"]).to(torch.float16).cpu().numpy()
            arr[ids] = v
            done += len(ids)
            if (i // batch_size) % 200 == 0:
                el = time.time() - t1
                print(f"[dense] {done}/{N} ({done / max(el, 1e-6):.0f}/s, {el:.0f}s, eta {(N - done) / max(done / max(el, 1e-6), 1e-6):.0f}s, "
                      f"gpu {torch.cuda.max_memory_allocated() / 2**30:.1f} GB)" if torch.cuda.is_available() else f"[dense] {done}/{N}", flush=True)
    arr.flush(); del arr
    secs = time.time() - t1
    meta = {"model": model, "tag": emb.spec["tag"], "pool": emb.spec["pool"], "q_prefix": emb.spec["q_prefix"], "p_prefix": emb.spec["p_prefix"],
            "dim": emb.dim, "count": N, "max_len": ml, "batch_size": batch_size, "dtype": "float16",
            "build_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "encode_seconds": round(secs), "tokens": ntok, "truncated_to": ml,
            "source_index": os.path.abspath(base_index_dir), "passages_file": passages_fn, "passages_bytes": os.path.getsize(passages_fn),
            "device": emb.device, "gpu_peak_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else None}
    json.dump(meta, open(os.path.join(tmp, "meta.json"), "w"), indent=1)
    emb.close(); del emb
    gc.collect(); torch.cuda.empty_cache() if torch.cuda.is_available() else None
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(tmp):
        os.replace(os.path.join(tmp, f), os.path.join(out_dir, f))
    os.rmdir(tmp)
    size = sum(os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir))
    print(f"[dense] built {out_dir}: {N} x {meta['dim']} float16, {size / 2**20:.0f} MB, encode {secs:.0f}s ({N / max(secs, 1e-6):.0f} passages/s)", flush=True)
    return out_dir, meta

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-dir", default="data/index/tawiki_20260801_fs", help="BM25 index dir holding passages.jsonl")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--out", default=None, help="output dir (default <index-dir>_dense_<tag>)")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--max-len", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="encode only the first N passages (smoke test)")
    a = ap.parse_args()
    out = a.out or index_dir_for(a.index_dir, a.model)
    if DenseIndex.exists(out) and not a.limit:
        print(f"[dense] {out} exists; delete it to rebuild"); sys.exit(0)
    build(a.index_dir, a.model, out_dir=out, batch_size=a.batch_size, max_len=a.max_len, limit=a.limit)
    print("DENSE INDEX DONE")
