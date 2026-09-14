"""run_dev.py under a per-process VRAM ceiling (comparison driver, 2026-09-13), with the full generations captured.
Concurrent workers that oversubscribe the card make WSL's GPU layer fail allocations silently (dxgkio_make_resident -12) and
stall; with a ceiling, an overrun raises a CUDA out-of-memory error that the driver retries at half the batch.
Capture (ruling 2026-09-13, extracted-score harness change): every generation the suite scores is also written in full, after
the suite's own think-block stripping and before its first-line cut, to eval/results/gen_raw/<stage>_<split>/<task>.jsonl as
{prompt_sha1, text}. The extracted score (eval/extract_score.py) is computed from these files. Nothing here changes a score, and
this file lives outside the hashed harness files.
  SUITE_GPU_FRACTION=0.25 .venv/bin/python eval/run_dev_capped.py <run_dev.py arguments>
"""
import hashlib, json, os, runpy, sys, threading
import torch
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
frac = os.environ.get("SUITE_GPU_FRACTION")
if frac:
    torch.cuda.set_per_process_memory_fraction(float(frac), 0)
import suite

def _arg(name, default=None):
    a = sys.argv[1:]
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default

stage, split = _arg("--stage"), _arg("--split", "dev")
CAP_DIR = os.path.join(HERE, "results", "gen_raw", f"{stage}_{split}")
_lock = threading.Lock(); _task = {"name": None}
_orig_score, _orig_batch, _orig_greedy = suite.score_items, suite.greedy_batch, suite.greedy

def _write(prompts, outs):
    if not _task["name"]: return
    os.makedirs(CAP_DIR, exist_ok=True)
    with _lock, open(os.path.join(CAP_DIR, _task["name"] + ".jsonl"), "a", encoding="utf-8") as f:
        for p, t in zip(prompts, outs):
            f.write(json.dumps({"prompt_sha1": hashlib.sha1(p.encode()).hexdigest(), "text": t}, ensure_ascii=False) + "\n")

def score_items(kind, items, model, tok, log_wrong=None, task=""):
    _task["name"] = task
    p = os.path.join(CAP_DIR, task + ".jsonl")
    if os.path.exists(p): os.remove(p)   # a re-run of a task replaces its capture
    try: return _orig_score(kind, items, model, tok, log_wrong=log_wrong, task=task)
    finally: _task["name"] = None

_inside_batch = threading.local()
def greedy_batch(model, tok, prompts, max_new, **kw):
    _inside_batch.on = True
    try: outs = _orig_batch(model, tok, prompts, max_new, **kw)
    finally: _inside_batch.on = False
    _write(prompts, outs); return outs

def greedy(model, tok, prompt, max_new, **kw):
    out = _orig_greedy(model, tok, prompt, max_new, **kw)
    if not getattr(_inside_batch, "on", False): _write([prompt], [out])   # single-item mode calls greedy from greedy_batch: written once (audit 2026-09-13)
    return out

suite.score_items, suite.greedy_batch, suite.greedy = score_items, greedy_batch, greedy
sys.argv = [os.path.join(HERE, "run_dev.py")] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
