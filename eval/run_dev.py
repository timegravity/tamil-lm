"""Run the DEV suite (used for all tuning decisions). No restrictions.

Usage: python eval/run_dev.py --stage <label> --model M [--adapter A] [--tokenizer T]
       [--embeddings E] [--tasks a,b] [--cap 300] [--wrong-dir eval/results/wrong_<label>]
Writes eval/results/<label>_dev.json
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite

ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--adapter"); ap.add_argument("--tokenizer"); ap.add_argument("--embeddings")
ap.add_argument("--tasks", default=None)
ap.add_argument("--cap", type=int, default=suite.DEV_CAP)
ap.add_argument("--wrong-dir", default=None)
ap.add_argument("--split", default="dev", choices=["dev", "test"], help="test = the locked test splits, full, no cap (baselines only; our stages use eval/run_test.py)")
a = ap.parse_args()
split = a.split; cap = a.cap if split == "dev" else None
suite.run(a.stage, split, a.model, a.adapter, a.tokenizer, a.embeddings,
          tasks=a.tasks.split(",") if a.tasks else None, cap=cap,
          out=os.path.join(suite.RESULTS, f"{a.stage}_{split}.json"),
          wrong_dir=a.wrong_dir or os.path.join(suite.RESULTS, f"wrong_{a.stage}" + ("" if split == "dev" else "_test")))
