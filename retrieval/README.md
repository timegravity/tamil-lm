# retrieval/

Pluggable retrieval for serve.py. `Retriever(config.yaml)` loads the sources listed in `config.yaml` and returns
merged passages `{"text", "title", "source", "score", "score_raw", "meta"}`; serve.py thresholds on `score_raw`
(the raw BM25 score of the top hit, `PASSAGE_MIN_RAW`).

| file | what |
|---|---|
| `__init__.py` | `Retriever`, `KBSource` (literature KB, BM25), `WikiDumpSource` (Wikipedia BM25, optional dense fusion), `FolderSource` |
| `bm25.py` | compact CSR BM25 index (numpy only) |
| `dense.py` | dense index over the Wikipedia passages: `Embedder`, `DenseIndex`, `build` (see below) |
| `build_wiki_index.py` | Wikipedia dump to `articles.jsonl` + `passages.jsonl` + BM25 index (`--family-safe` for the `_fs` index) |
| `text.py` | tokeniser, wikitext stripping, chunking, query stopwords |
| `translit.py`, `roman.py` | romanised (Tanglish) to Tamil-script query expansion, used by serve.py before search |
| `kb.py`, `litmatch.py`, `facts.py` | literature KB loading and matching, fact sheets (structured and fuzzy matching; not touched by dense retrieval) |
| `wiki_live.py` | live Wikipedia lookup tool (not a source) |

## Dense retrieval for the Wikipedia source (ruling 2026-09-09)

Server-side only. The Android APK ships the BM25 index and code only (`publish.sh` tools list); `dense.py` and the
`*_dense_*` index dirs are never published, so on the phone `WikiDumpSource` silently stays BM25-only.

Build one index per embedder from the same `passages.jsonl` the BM25 index was built from (passage ids must line up):

    .venv/bin/python retrieval/dense.py --index-dir data/index/tawiki_20260801_fs --model BAAI/bge-m3
    .venv/bin/python retrieval/dense.py --index-dir data/index/tawiki_20260801_fs --model intfloat/multilingual-e5-base

Output: `data/index/<index>_dense_<tag>/emb.npy` (float16, N x dim, memmap-able) and `meta.json` (model, dim, count,
build date, encode time, size of the passages file it was built from). Title and passage text are encoded together;
multilingual-e5 gets its `query: ` / `passage: ` prefixes, bge-m3 none (dense output only, CLS pooling).

Config, on the `wiki_dump` source in `config.yaml`:

    dense:
      model: BAAI/bge-m3            # query encoder; must match the index
      index_dir: data/index/tawiki_20260801_fs_dense_bgem3   # default: <index_dir>_dense_<tag>
      fusion: rrf                   # rrf (reciprocal rank fusion, k=60) or minmax (min-max normalised weighted sum)
      weight: 1.0                   # weight of the dense side in the fusion
      top_n: 50                     # candidates taken from each of BM25 and dense before fusion

Behaviour:

- BM25-only is the default whenever the `dense` block is absent, the index dir is missing, the index does not match
  the BM25 index (passage count or passages file size), the embedder cannot load, or `DENSE_RETRIEVAL=0` is set.
- The Passage contract is unchanged: `score` (and so `score_raw` after `Retriever.search`) is still the title-boosted
  BM25 score of that passage, computed on demand for dense-only candidates, so serve.py's threshold keeps its meaning.
  `meta` adds `fusion` (rrf, minmax or bm25), `fused_rank`, `fused_score`, `bm25_rank`, `dense_rank`, `dense_score`
  (cosine) and `passage_id`.
- `WikiDumpSource.search(query, k, fusion=...)` accepts `bm25`, `dense`, `rrf`, `minmax` for evaluation; serve.py
  never passes it.
- The query encoder stays resident (about 1.1 GB for bge-m3, 0.6 GB for e5-base, float16) and the embedding matrix
  lives on the GPU (0.5 GB for bge-m3, 0.4 GB for e5-base); search is one matmul plus top-k. Without CUDA both fall
  back to CPU (chunked numpy cosine, slower query encoding).
- Literature stays on the structured and fuzzy matching in `litmatch.py` / `kb.py`; `KBSource` is untouched.

Evaluation: `eval/retrieval_eval.py` (query set `eval/retrieval_queries_200.jsonl`, review sheet
`eval/retrieval_queries_200_review.csv`, report `eval/results/retrieval_dense_eval.md`). Re-run against the marked
labels with `python eval/retrieval_eval.py eval --label correct_title`.
