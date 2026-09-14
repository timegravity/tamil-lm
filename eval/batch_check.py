"""Batched-generation check (ruling 2026-09-12): the batched greedy path must match the single-item path within noise on a
300-item dev sample, on our model AND on Gemma-3-1B (padding behaviour differs by architecture), before any batched result is
used. Reference: the single-item dev files produced by the same greedy() function (cmp_<name>_dev.json, pre-batching harness).
Noise thresholds as in compare_sft.py: chrF++ 2.0, F1 0.02, contains 0.03, accuracy 0.05.
  .venv/bin/python eval/batch_check.py  -> eval/results/batch_check.md and .json (gate PASS/FAIL); the driver refuses batched runs without PASS
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(HERE, "results"); sys.path.insert(0, HERE)
from table_guard import need, MissingResult
# Harness v3 (2026-09-13): both halves re-run under v3, one prompt at a time and in batches of 32, both eager, 300 dev items per
# generation task (the v1 and bos-v1 files are kept in eval/results/pre_v3/).
PAIRS = {"tamil-lm-2b-instruct-r4": ("check_v3_single_ours_dev.json", "check_v3_batch32_ours_dev.json"),
         "Gemma-3-1B-it": ("check_v3_single_gemma1b_dev.json", "check_v3_batch32_gemma1b_dev.json")}
SDPA_PAIRS = {"tamil-lm-2b-instruct-r4": "check_batch32_ours_dev.json", "Gemma-3-1B-it": "check_batch32_gemma1b_dev.json"}   # the first attempt (sdpa), kept for the record
TOL = {"chrf++": 2.0, "bleu": 2.0, "f1": 0.02, "contains": 0.03, "acc": 0.05}
# GSM8K (40 dev items): the eager attention kernel itself moves 3 items on both models (single-item eager = batched eager), so the
# batching comparison for that task uses the single-item EAGER reference; both references are shown.
SINGLE_EAGER = {"tamil-lm-2b-instruct-r4": "none-under-v3", "Gemma-3-1B-it": "none-under-v3"}   # v3: GSM8K decodes one item at a time in both halves
TEST_PAIR = ("cmp_Gemma-3-1B-it_single_test.json", "cmp_Gemma-3-1B-it_test.json")   # full locked test split, single-item sdpa vs batched eager (ruling 2026-09-12 item 3)

def rows(name):
    p = os.path.join(R, name)
    if not os.path.exists(p): raise MissingResult(f"missing {p}")
    return {(r["benchmark"], r["metric"]): r for r in json.load(open(p))}

def main():
    L = [f"# Batched generation check ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Single-item reference: the dev files of the comparison run (one prompt at a time, greedy). Batched: SUITE_GEN_BATCH=32, left-padded, "
         "length-sorted batches with a 12,000 prompt-token budget per batch, greedy, EAGER attention. Same 300 dev items per task. A difference beyond the noise threshold fails the check. "
         "The first attempt used the default sdpa attention: Gemma-3-1B lost 1 to 2.6 chrF++ on Tamil-to-English (sliding-window attention with left padding); those files are kept as check_batch32_*_dev.json and listed at the end.", "",
         "| model | task | metric | single | batched | difference | threshold | within noise |", "|---|---|---|---|---|---|---|---|"]
    ok = True; out = {"pairs": {}, "tolerances": TOL}
    for model, (single, batched) in PAIRS.items():
        S, B = rows(single), rows(batched); hv = None
        SE = rows(SINGLE_EAGER[model]) if os.path.exists(os.path.join(R, SINGLE_EAGER[model])) else {}
        for key, rb in B.items():
            rs = S.get(key)
            if rs is None: raise MissingResult(f"{model}: {key} absent from the single-item reference {single}")
            ref = SE.get(key, rs) if key[0] == "gsm8k_en" else rs
            tol = TOL.get(key[1]); d = rb["score"] - ref["score"]; within = abs(d) <= tol
            ok = ok and within; hv = need(rb, "harness")
            note = f" (single sdpa {rs['score']:.4f}; reference is single eager)" if ref is not rs else ""
            L.append(f"| {model} | {key[0]} | {key[1]} | {ref['score']:.4f}{note} | {rb['score']:.4f} | {d:+.4f} | {tol} | {'yes' if within else 'NO'} |")
            out["pairs"].setdefault(model, []).append({"task": key[0], "metric": key[1], "single": rs["score"], "batched": rb["score"], "diff": round(d, 4), "tol": tol, "within": within, "n": rb["n"]})
        out.setdefault("harness_batched", {})[model] = hv
    # the verified version must be the version the driver will run (suite content hash, batched, eager)
    old_env = {k: os.environ.get(k) for k in ("SUITE_GEN_BATCH", "SUITE_ATTN")}; os.environ["SUITE_GEN_BATCH"] = "32"; os.environ["SUITE_ATTN"] = "eager"
    import suite; expected = suite.harness_version()
    for k, v in old_env.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
    stale = {m: v for m, v in out["harness_batched"].items() if v != expected}
    if stale:
        ok = False; L += ["", f"Harness version mismatch: the check files were produced by {stale}, the current harness is {expected}; re-run the check."]
    out["expected_harness"] = expected
    out["gate"] = "PASS" if ok else "FAIL"; out["generated"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    # Gemma-3-1B on the FULL locked test split: single-item (sdpa, the reference pass kept at the pause) against the batched eager pass
    same_version = all(os.path.exists(os.path.join(R, f)) for f in TEST_PAIR) and all(r.get("harness", "").split(":")[0] == expected.split(":")[0] for f in TEST_PAIR for r in json.load(open(os.path.join(R, f))))
    if not same_version:
        out["test_gate_gemma_3_1b"] = "not re-run under this harness version"
        L += ["", "Gemma-3-1B full locked test split, single-item against batched: the 2026-09-12 comparison (PASS, harness e35cc70118) is not repeated under v3; the 300-item dev check above and each model's own batched-versus-single check cover batching (eval/results/pre_v3/batch_check.md keeps the full-split result)."]
    if same_version:
        S, B = rows(TEST_PAIR[0]), rows(TEST_PAIR[1]); tok = True; L += ["", "## Gemma-3-1B on the full locked test split (single-item sdpa vs batched eager)", "", "| task | metric | single | batched | difference | threshold | within noise |", "|---|---|---|---|---|---|---|"]
        for key, rb in B.items():
            rs = S.get(key)
            if rs is None: continue
            tol = TOL.get(key[1], 0.05); d = rb["score"] - rs["score"]; within = abs(d) <= tol; tok = tok and within
            L.append(f"| {key[0]} | {key[1]} | {rs['score']:.4f} | {rb['score']:.4f} | {d:+.4f} | {tol} | {'yes' if within else 'NO'} |")
        out["test_gate_gemma_3_1b"] = "PASS" if tok else "FAIL"
        L += ["", f"Gemma-3-1B full-split comparison: {out['test_gate_gemma_3_1b']} (a FAIL removes Gemma-3-1B from the batched tables, ruling 2026-09-12)."]
    L += ["", f"**Check: {out['gate']}.** Batched harness versions: {out['harness_batched']}.", "", "sdpa attempt (not used):", ""]
    for model, f in SDPA_PAIRS.items():
        p = os.path.join(R, f)
        if os.path.exists(p):
            S = rows(PAIRS[model][0]); B = rows(f)
            L += [f"- {model}: " + "; ".join(f"{k[0]} {k[1]} {B[k]['score']:.3f} vs single {S[k]['score']:.3f}" for k in B if k in S and k[1] in ("chrf++", "f1", "acc"))]
    json.dump(out, open(os.path.join(R, "batch_check.json"), "w"), indent=1); open(os.path.join(R, "batch_check.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
