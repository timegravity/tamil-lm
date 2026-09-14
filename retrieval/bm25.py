"""Compact BM25 index: CSR postings in numpy, built from an iterator of token lists.

Files under an index dir: vocab.json (term -> id), post_ptr.npy (int64, V+1),
post_doc.npy (int32), post_tf.npy (float32), doc_len.npy (int32), meta.json.
Query cost is O(sum of posting lengths of query terms) with a dense score array.
"""
import json, math, os
import numpy as np
from .text import toks, STOPWORDS

class BM25Index:
    def __init__(self, d):
        self.dir = d
        self.vocab = json.load(open(os.path.join(d, "vocab.json")))
        self.ptr = np.load(os.path.join(d, "post_ptr.npy"))
        self.doc = np.load(os.path.join(d, "post_doc.npy"), mmap_mode="r")
        self.tf = np.load(os.path.join(d, "post_tf.npy"), mmap_mode="r")
        self.dl = np.load(os.path.join(d, "doc_len.npy"))
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.N = int(self.meta["N"]); self.avgdl = float(self.meta["avgdl"])

    @staticmethod
    def exists(d):
        return all(os.path.exists(os.path.join(d, f)) for f in ("vocab.json", "post_ptr.npy", "post_doc.npy", "post_tf.npy", "doc_len.npy", "meta.json"))

    def search(self, query, k=5, k1=1.5, b=0.75):
        q = toks(query)
        q = [t for t in q if t not in STOPWORDS] or q
        if not q or self.N == 0:
            return []
        scores = np.zeros(self.N, dtype=np.float32)
        norm = k1 * (1 - b + b * self.dl / self.avgdl)
        for t in set(q):
            tid = self.vocab.get(t)
            if tid is None:
                continue
            s, e = int(self.ptr[tid]), int(self.ptr[tid + 1])
            if e <= s:
                continue
            docs = np.asarray(self.doc[s:e]); tf = np.asarray(self.tf[s:e])
            n = e - s
            idf = math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            scores[docs] += idf * tf * (k1 + 1) / (tf + norm[docs])
        if k >= self.N:
            top = np.argsort(-scores)
        else:
            top = np.argpartition(-scores, k)[:k]
            top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]

def build(index_dir, token_lists, batch=20000):
    """token_lists: iterable of token lists (one per document). Two-stage, memory-sane:
    collect (term, doc, tf) triples in int32 chunks, sort by term, write CSR."""
    os.makedirs(index_dir, exist_ok=True)
    vocab = {}
    term_chunks, doc_chunks, tf_chunks, doc_len = [], [], [], []
    ct, cd, cf = [], [], []
    n = 0
    for tl in token_lists:
        doc_len.append(len(tl))
        counts = {}
        for t in tl:
            counts[t] = counts.get(t, 0) + 1
        for t, c in counts.items():
            tid = vocab.get(t)
            if tid is None:
                tid = len(vocab); vocab[t] = tid
            ct.append(tid); cd.append(n); cf.append(c)
        n += 1
        if len(ct) >= batch * 100:
            term_chunks.append(np.array(ct, dtype=np.int32)); doc_chunks.append(np.array(cd, dtype=np.int32)); tf_chunks.append(np.array(cf, dtype=np.float32))
            ct, cd, cf = [], [], []
    if ct:
        term_chunks.append(np.array(ct, dtype=np.int32)); doc_chunks.append(np.array(cd, dtype=np.int32)); tf_chunks.append(np.array(cf, dtype=np.float32))
    if n == 0:
        term = np.zeros(0, np.int32); doc = np.zeros(0, np.int32); tf = np.zeros(0, np.float32)
    else:
        term = np.concatenate(term_chunks); doc = np.concatenate(doc_chunks); tf = np.concatenate(tf_chunks)
    del term_chunks, doc_chunks, tf_chunks
    order = np.argsort(term, kind="stable")
    term = term[order]; doc = doc[order]; tf = tf[order]; del order
    V = len(vocab)
    ptr = np.zeros(V + 1, dtype=np.int64)
    if V:
        ptr[1:] = np.bincount(term, minlength=V)
    ptr = np.cumsum(ptr)
    tmp = index_dir + ".building"
    os.makedirs(tmp, exist_ok=True)
    np.save(os.path.join(tmp, "post_ptr.npy"), ptr)
    np.save(os.path.join(tmp, "post_doc.npy"), doc)
    np.save(os.path.join(tmp, "post_tf.npy"), tf)
    np.save(os.path.join(tmp, "doc_len.npy"), np.array(doc_len, dtype=np.int32))
    json.dump(vocab, open(os.path.join(tmp, "vocab.json"), "w"), ensure_ascii=False)
    json.dump({"N": n, "avgdl": (sum(doc_len) / n) if n else 0.0, "V": V, "postings": int(len(term))},
              open(os.path.join(tmp, "meta.json"), "w"))
    for f in os.listdir(tmp):
        os.replace(os.path.join(tmp, f), os.path.join(index_dir, f))
    os.rmdir(tmp)
    return n, V, int(len(term))
