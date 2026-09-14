"""Run the TEST suite. Allowed exactly once per stage in {base, cpt_final, sft_final}.

A lock file eval/results/test_<stage>.lock is written before running and the
script refuses to run if it exists. Deleting a lock is a human decision; the
lock records who and when. Full test splits, no cap.

Usage: python eval/run_test.py --stage base --model M [--adapter A] [--tokenizer T] [--embeddings E]
"""
import argparse, os, sys, time, getpass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite

ALLOWED = ("base", "cpt_final", "sft_final", "sft4_final")   # sft4_final added 2026-09-10 (round 4; one run, locked)
ap = argparse.ArgumentParser()
ap.add_argument("--stage", required=True, choices=ALLOWED)
ap.add_argument("--model", required=True)
ap.add_argument("--adapter"); ap.add_argument("--tokenizer"); ap.add_argument("--embeddings")
ap.add_argument("--tasks", default=None, help="only for resuming a crashed run; still one stage")
a = ap.parse_args()

os.makedirs(suite.RESULTS, exist_ok=True)
lock = os.path.join(suite.RESULTS, f"test_{a.stage}.lock")
if os.path.exists(lock) and not a.tasks:
    sys.exit(f"REFUSED: test suite already run for stage '{a.stage}' ({open(lock).read().strip()}). "
             f"Test is run exactly once per stage.")
with open(lock, "a") as f:
    f.write(f"{a.stage} started {time.strftime('%FT%T')} by {getpass.getuser()} "
            f"model={a.model} adapter={a.adapter} commit={suite.git_commit()}\n")
suite.run(a.stage, "test", a.model, a.adapter, a.tokenizer, a.embeddings,
          tasks=a.tasks.split(",") if a.tasks else None, cap=None,
          out=os.path.join(suite.RESULTS, f"{a.stage}_test.json"))
