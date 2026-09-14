"""Per-bucket judgement for mix/data experiments (their val proportions differ,
so the char-weighted total bpc is not comparable to the reference).

Usage: python judge_mix.py exp013 [exp014 ...]
Prints per-bucket bpc deltas vs the reference run (exp001) and the fast-probe
delta, and a suggested verdict: kept-candidate if the literature bucket and the
mean over buckets both improve by > 0.002 with probe not fallen beyond noise.
"""
import json, sys

REF = "exp005"
REF_PROBE = 0.329
NOISE = 0.025

def final_bpc(run):
    rows = [json.loads(l) for l in open(f"logs/{run}.jsonl")]
    fin = [r for r in rows if r.get("event") == "final"][-1]
    return {k: v for k, v in fin["val_bpc"].items() if not k.endswith("_bpb") and k != "total"}

ref = final_bpc(REF)
for run in sys.argv[1:]:
    cur = final_bpc(run)
    try:
        probe = json.load(open(f"logs/probe_{run}.json"))["probe_acc"]
    except FileNotFoundError:
        probe = None
    deltas = {b: round(cur[b] - ref[b], 4) for b in ref if b in cur}
    mean_d = sum(deltas.values()) / len(deltas)
    d_probe = (probe - REF_PROBE) if probe is not None else None
    ok_bpc = deltas.get("literature", 0) < -0.002 and mean_d < -0.002
    ok_probe = d_probe is None or d_probe >= -NOISE
    if d_probe is not None and d_probe > NOISE:
        verdict = "probe-candidate (rule b: full probe needed)"
    elif ok_bpc and ok_probe:
        verdict = "kept-candidate (full probe needed)"
    else:
        verdict = "reverted"
    print(f"{run}: per-bucket delta vs {REF}: {deltas}; mean {mean_d:+.4f}; "
          f"fast-probe {probe} ({'n/a' if d_probe is None else f'{d_probe*100:+.1f} pt'}) -> {verdict}")
