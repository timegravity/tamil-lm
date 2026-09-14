"""Start-token harness change (bos-v1, ruling 2026-09-13): which finished results can carry to the new harness version unchanged.

The ruling re-runs every raw phase (raw dev, raw test, probe) of the finished models. Chat-mode test rows, each model's batched-vs-
single check and the batch verification (eval/results/batch_check.json) are carried only when the model inputs are proven identical:
for every item of every task, the token ids the old harness fed the model (e35cc70118: generation and bpc with the tokenizer's own
special tokens for raw prompts, log-likelihood prompts without special tokens, templated prompts without special tokens) equal the
ids bos-v1 feeds it (eval/suite.py raw_ids and prompt_ids). The comparison runs the suite's own prompt construction (score_items)
with the model calls replaced by recorders, so no GPU is used; batched rows use the same per-item ids with left padding, so equal
per-item ids mean equal batch tensors. Anything not identical re-runs.

  .venv/bin/python eval/harness_carry.py            # analyse -> eval/results/harness_carry_bos_v1.json
  .venv/bin/python eval/harness_carry.py --apply    # stamp carried rows with the new version (old version kept in harness_carried_from)
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
os.environ.setdefault("SUITE_GEN_BATCH", "32")
import suite
import baselines_round4 as B

OLD = "e35cc70118"
OUT = os.path.join(HERE, "results", "harness_carry_bos_v1.json")

class Recorder:
    def __init__(self): self.items = 0; self.changed = 0; self.example = None
    def cmp(self, old, new, what):
        self.items += 1
        if list(old) != list(new):
            self.changed += 1
            if self.example is None: self.example = f"{what}: old starts {list(old)[:4]}, new starts {list(new)[:4]}"

def analyse_task(tok, task, split, cap):
    _, kind = suite.REGISTRY[task]
    items = {it["id"]: it for it in suite.load_items(task)}
    ids = json.load(open(os.path.join(suite.SPLITS, f"{task}.json")))[split]
    if cap: ids = ids[:cap]
    sel = [items[i] for i in ids if i in items]
    rec = Recorder()
    def cont_loglik(model, tok_, p, cont):
        w = suite.chat_wrap(tok_, p); c = tok_(cont, add_special_tokens=False).input_ids
        rec.cmp(tok_(w, add_special_tokens=False).input_ids + c, suite.prompt_ids(tok_, w, p) + c, "log-likelihood prompt"); return 0.0
    def greedy_one(tok_, p):
        w = suite.chat_wrap(tok_, p)
        rec.cmp(tok_(w, add_special_tokens=(w == p)).input_ids, suite.prompt_ids(tok_, w, p), "generation prompt")
    def greedy_batch(model, tok_, prompts, max_new):
        for p in prompts: greedy_one(tok_, p)
        return [""] * len(prompts)
    def greedy(model, tok_, p, max_new):
        greedy_one(tok_, p); return ""
    def bpc(model, tok_, text):
        rec.cmp(tok_(text).input_ids[:4096], suite.raw_ids(tok_, text)[:4096], "bpc text"); return 1.0
    saved = (suite.cont_loglik, suite.greedy_batch, suite.greedy, suite.bpc)
    suite.cont_loglik, suite.greedy_batch, suite.greedy, suite.bpc = cont_loglik, greedy_batch, greedy, bpc
    try: suite.score_items(kind, sel, None, tok, task=task)
    finally: suite.cont_loglik, suite.greedy_batch, suite.greedy, suite.bpc = saved
    return {"n": rec.items, "changed": rec.changed, "example": rec.example}

def load_tok(name_or_path, env):
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        from transformers import AutoTokenizer
        import transformers as tf
        trc = os.environ.get("SUITE_TRUST_REMOTE", "0") == "1"
        try: tok = AutoTokenizer.from_pretrained(name_or_path, trust_remote_code=trc)
        except Exception: tok = tf.AutoProcessor.from_pretrained(name_or_path, trust_remote_code=trc).tokenizer
        if tok.pad_token_id is None: tok.pad_token = tok.eos_token
        return tok
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

def with_env(env, fn):
    old = {k: os.environ.get(k) for k in env}; os.environ.update(env)
    try: return fn()
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

def carried_flags(name, stage_split, rows):
    """The degenerate-output check on a carried chat file: translation captures (gen_raw) and bpc rows, as the suite would have flagged them."""
    import extract_score as XS
    flags = {}; sc = {(r["benchmark"], r["metric"]): r["score"] for r in rows}
    for t in B.TRANSLATION_TASKS:
        texts, _ = XS.local_texts(f"cmp_{name}_chat", t)
        if texts is None or (t, "chrf++") not in sc: continue
        prompts = [p for _, p in XS.prompts_for(t)]
        why = suite.degenerate_task(prompts, texts, chrf=sc[(t, "chrf++")])
        if why: flags[t] = why
    for t, lim in suite.DEGEN_BPC.items():
        if (t, "bpc") in sc and sc[(t, "bpc")] > lim: flags[t] = f"bpc {sc[(t, 'bpc')]:.2f} above {lim}"
    return flags

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--ours-chat-dir", default="ckpt/final/tamil-lm-2b-instruct-sft4c"); a = ap.parse_args()
    new = B.expected_harness(); state = json.load(open(os.path.join(HERE, "results", "comparison_bare_state.json")))
    finished = [m for m in B.MODELS if m[0] not in B.SKIP and all((state.get(m[0]) or {}).get("phases", {}).get(p) in (True, "skipped") for p in ("raw_dev", "raw_test", "chat_test"))]
    report = {"old": OLD, "new": new, "generated": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "models": {}}
    if not a.apply:
        for name, mid, adapter, *_ in finished:
            env = dict(B.MODEL_ENV.get(name, {})); env.pop("SUITE_DEVICE_MAP", None)
            raw_tok = load_tok(mid, env)
            chat_tok = load_tok(a.ours_chat_dir, env) if adapter == "OURS" else raw_tok
            m = {"bos_token_id": raw_tok.bos_token_id, "adds_bos_by_default": bool(raw_tok("x").input_ids[:1] == [raw_tok.bos_token_id]) if raw_tok.bos_token_id is not None else False}
            raw_env = {"SUITE_CHAT": "0", "SUITE_SYSTEM_PROMPT": ""}
            chat_env = {"SUITE_CHAT": "1", "SUITE_SYSTEM_PROMPT": B.CHAT_HINTS.get(name, "")}
            m["check"] = {t: with_env(raw_env, lambda t=t: analyse_task(raw_tok, t, "dev", B.CHECK_CAP)) for t in B.CHECK_TASKS}
            m["raw_test"] = {t: with_env(raw_env, lambda t=t: analyse_task(raw_tok, t, "test", None)) for t in B.TEST_TASKS}
            m["chat_test"] = {t: with_env(chat_env, lambda t=t: analyse_task(chat_tok, t, "test", None)) for t in B.TEST_TASKS} if state[name]["phases"].get("chat_test") is True else "skipped"
            for k in ("check", "raw_test", "chat_test"):
                if isinstance(m[k], dict): m[k + "_identical"] = all(v["changed"] == 0 for v in m[k].values())
            report["models"][name] = m
            print(name, {k: m.get(k + "_identical") for k in ("check", "raw_test", "chat_test")}, "bos", m["bos_token_id"], "default adds", m["adds_bos_by_default"], flush=True)
        json.dump(report, open(OUT, "w"), indent=1)
        return
    rep = json.load(open(OUT))
    if rep["new"] != new: raise SystemExit(f"analysis was for {rep['new']}, the harness is now {new}: re-run the analysis")
    stamp = {"harness_carried_from": f"{OLD}:batched-eager", "carry_check": f"token-identical model inputs on every item under bos-v1 (eval/harness_carry.py, {rep['generated']})"}
    for name, m in rep["models"].items():
        r = state[name]
        if m.get("chat_test_identical"):
            for fn in (f"cmp_{name}_chat_test.json", f"cmp_{name}_trans_chat_test.json"):
                p = os.path.join(HERE, "results", fn)
                if os.path.exists(p):
                    rows = json.load(open(p))
                    stage_split = fn[:-len(".json")]
                    flags = carried_flags(name, stage_split, rows)
                    for row in rows:
                        if row.get("harness", "").startswith(OLD):
                            row.update(stamp); row["harness"] = new.split(":")[0] + ":" + row["harness"].split(":", 1)[1]
                        f = flags.get(row["benchmark"])
                        if f:
                            row["degenerate"] = f
                            rv = suite.reviewed(stage_split.rsplit("_", 1)[0], "test", row["benchmark"])
                            if rv: row["degenerate_reviewed"] = rv
                            print("  degenerate flag on carried row", stage_split, row["benchmark"], f, "reviewed" if rv else "UNREVIEWED")
                    json.dump(rows, open(p, "w"), indent=1, ensure_ascii=False); print("carried", fn)
        if m.get("check_identical") and (r.get("mode_check") or {}).get("harness", "").startswith(OLD):
            r["mode_check"].update(stamp); r["mode_check"]["harness"] = new; print("carried check", name)
    json.dump(state, open(os.path.join(HERE, "results", "comparison_bare_state.json"), "w"), indent=1)
    bc = os.path.join(HERE, "results", "batch_check.json"); bcj = json.load(open(bc))
    refs = [rep["models"].get(n, {}) for n in ("tamil-lm-2b-instruct-r4", "Gemma-3-1B-it")]
    if all(x.get("check_identical") for x in refs) and bcj.get("expected_harness", "").startswith(OLD):
        bcj.update(stamp); bcj["expected_harness"] = new; json.dump(bcj, open(bc, "w"), indent=1); print("carried batch_check.json")
    else:
        print("batch_check.json NOT carried: the verification models' check inputs changed")

if __name__ == "__main__":
    main()
