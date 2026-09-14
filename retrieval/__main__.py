"""CLI: python -m retrieval "query" [--config retrieval/config.yaml] [--k 4] [--only name,name]"""
import argparse, sys
from . import Retriever, DEFAULT_CONFIG, format_passages
from .facts import match_fact_sheet

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query"); ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--k", type=int, default=None); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    sheet = match_fact_sheet(a.query)
    if sheet:
        print("=== FACT SHEET MATCHED ===")
        print(sheet[:1200]); print()
    r = Retriever(a.config, only=a.only.split(",") if a.only else None)
    hits = r.search(a.query, k=a.k)
    print(f"=== {len(hits)} passages ===")
    for h in hits:
        print(f"--- {h['source']} | {h['title']} | score {h['score']:.3f} (raw {h.get('score_raw', 0):.2f})")
        print(h["text"][:500])
    return 0

if __name__ == "__main__":
    sys.exit(main())
