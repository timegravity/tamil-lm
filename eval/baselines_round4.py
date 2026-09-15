"""Comparison of open models against ours (rulings 2026-09-10, 2026-09-11, 2026-09-12). Every model runs through THIS harness
locally. Two prompt modes on the LOCKED TEST SPLITS (full, no cap):
  (a) raw: identical raw prompts for every model (eval/prompts/*.txt), greedy, bf16, no chat template;
  (b) chat: each model wrapped in its own chat template with the system prompt its model card recommends (CHAT_HINTS),
      thinking disabled where the template supports it; ours with its own chat template (the merged instruct directory).
The dev split (cap 300) is also run in raw mode for reference (results folder only). The literature probe (eval/run_probe.py)
runs on the raw weights; both of its scorers are reported (letter log-likelihood and the option-text gate). Tokens per Tamil
word: each tokenizer over the first 300 FLORES Tamil dev sentences. Parameter counts from the safetensors headers.
Storage rule: one baseline on disk at a time; download, run every phase, write results, purge; free-space floor 80 GB.
Nothing is copied from papers or model cards; a model that cannot be run is listed with the reason.

  .venv/bin/python eval/baselines_round4.py --ours-adapter ckpt/sft4c/step_1589 --ours-chat-dir ckpt/final/tamil-lm-2b-instruct-sft4c
      [--only name,name] [--phases raw_dev,raw_test,chat_test,probe] [--render-only]
Writes eval/results/comparison_bare.json, comparison_bare.md (table a), comparison_chat.md (table b), comparison_dev.md.
"""
import sys as _s, os as _o; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__))); from table_guard import need, MissingResult
import argparse, glob, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
PY = os.path.join(ROOT, ".venv", "bin", "python")

TASKS = ["flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en", "milu_ta", "indicqa_ta", "belebele_ta",
         "indicxnli_ta", "indicsentiment_ta", "mmlu_en", "gsm8k_en", "tamil_heldout", "tanglish_heldout"]
CAP = 300
PHASES = ["raw_dev", "raw_test", "chat_test", "probe", "trans_raw", "trans_chat"]
# trans_raw / trans_chat (ruling 2026-09-13, extracted score): the four translation tasks re-run with full generations captured, only
# for models whose test passes ran before eval/run_dev_capped.py captured generations; done when a complete capture exists.
TRANSLATION_TASKS = ["flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en"]
# Test tables (a) and (b) carry only the tasks behind the summary (ruling 2026-09-12): XL-Sum, Belebele, INCLUDE, COPA, sentiment
# and NLI stay in the dev table only.
TEST_TASKS = ["flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en", "milu_ta", "indicqa_ta", "tamil_heldout", "tanglish_heldout", "mmlu_en", "gsm8k_en"]
# Batched greedy generation (ruling 2026-09-12; eval/results/batch_check.md must say PASS): 32 for small models, 16 for 7B and the offloaded ones.
def batch_for(size_b):
    return 16 if size_b >= 5 else 32
# GPU scheduling: bf16 weights (2.1 GB per billion) plus generation headroom; the sum of running footprints stays under GPU_CAP_GB.
# 2026-09-13: four concurrent batched workers (eager attention, long IndicQA contexts) oversubscribed the 48 GB card; WSL's dxg layer
# failed the allocations (dxgkio_make_resident -12) instead of raising a CUDA OOM and every worker stalled at 100% CPU until the
# adapter wedged. Footprints now include the eager-attention peak, the cap is 40 GB (30 GB at first; raised with the VRAM ceiling), at most two workers run at once, and every
# worker runs under eval/run_dev_capped.py with a per-process VRAM ceiling (SUITE_GPU_FRACTION) so an overrun raises a clean OOM.
GPU_TOTAL_GB = 48
GPU_CAP_GB = 40
def footprint_gb(size_b):
    # weights plus the eager-attention peak: a 6,000-token IndicQA context (high-fertility tokenizers) materialises about 2.3 GB of
    # attention weights per layer in bf16 plus its fp32 softmax, about 8 GB transient even at batch 1 (Llama-3.2-1B OOM at a 12.5 GB
    # ceiling, 2026-09-13); 16 GB of headroom covers it for small models, 18 GB for 7B-class ones.
    return round(size_b * 2.1 + (18 if size_b >= 5 else 16), 1)
# Batched generation runs with eager attention for every model: the sdpa path with left padding degraded Gemma-3-1B by 1 to 2.6 chrF++
# (eval/results/batch_check.md, 2026-09-12); eager reproduces the single-item numbers within noise on both check models.
ATTN = "eager"
ALONE = {"gpt-oss-20b", "Sarvam-30B"}          # run with nothing else on the GPU (CPU offload, 42 GiB GPU budget)
MAX_SMALL, MAX_7B = 2, 1                        # concurrent small (<5B) and 7B-class models; the cap binds first

# name, model id or path, adapter, licence (as on the Hub card), note, category, approximate stored parameters in billions (run order)
MODELS = [
    ("tamil-lm-2b-instruct-r4", "ckpt/final/tamil-lm-2b-base", "OURS", "apache-2.0 (Qwen3.5 base)", "this project, round 4c", "ours", 2.0),
    ("Qwen3.5-2B", "Qwen/Qwen3.5-2B", None, "apache-2.0", "our base's own post-trained instruct model", "base family", 2.0),
    ("Qwen3.5-4B", "Qwen/Qwen3.5-4B", None, "apache-2.0", "next size up in the same family", "base family", 4.0),
    ("Gemma-3-1B-it", "google/gemma-3-1b-it", None, "gemma", "gated, terms accepted 2026-09-10", "big-lab small models", 1.0),
    ("Llama-3.2-1B-Instruct", "meta-llama/Llama-3.2-1B-Instruct", None, "llama3.2", "gated, access granted 2026-09-11", "big-lab small models", 1.2),
    ("Llama-3.2-3B-Instruct", "meta-llama/Llama-3.2-3B-Instruct", None, "llama3.2", "gated, access granted 2026-09-11", "big-lab small models", 3.2),
    # Ministral-3-3B-Instruct removed from the comparison (Vignesh, 2026-09-14)
    ("Gemma-3-4B-it", "google/gemma-3-4b-it", None, "gemma", "gated, terms accepted 2026-09-10; removed and restored the same day (Vignesh, 2026-09-13)", "big-lab small models", 4.3),
    # Gemma-4-E2B-it removed from the comparison (Vignesh, 2026-09-13)
    # Gemma-4-E4B-it removed from the comparison (Vignesh, 2026-09-13)
    # gpt-oss-20b (local) removed from the comparison (Vignesh, 2026-09-13); gpt-oss-20b and gpt-oss-120b run hosted instead (eval/hosted_compare.py)
    ("Sarvam-1", "sarvamai/sarvam-1", None, "not stated on the card", "Indic model, 2B; its tokenizer ships a Llama 2 style [INST] chat template, which table b uses (corrected 2026-09-13)", "Indian labs", 2.5),
    ("Param-1-2.9B-Instruct", "bharatgenai/Param-1-2.9B-Instruct", None, "apache-2.0", "BharatGen sovereign model, 22 Indian languages (2026-02)", "Indian labs", 2.9),
    ("BharatGPT-3B-Indic", "CoRover/BharatGPT-3B-Indic", None, "other", "gated with manual approval, granted 2026-09-11", "Indian labs", 3.2),
    ("Param2-17B-A2.4B-Thinking", "bharatgenai/Param2-17B-A2.4B-Thinking", None, "not stated on the card", "BharatGen Param 2, 17B MoE with 2.4B active; the only Param 2 checkpoint on the Hub is the Thinking variant", "Indian labs", 17.0),
    ("Qwen3-1.7B-tamil-Instruct", "sabaridsnfuji/Qwen3-1.7B-tamil-16bit-Instruct", None, "apache-2.0", "Tamil-adapted Qwen3, 1.7B (2026-08)", "community Tamil fine-tunes", 1.7),
    ("Tamil-Llama-7B-instruct-v0.2", "abhinand/tamil-llama-7b-instruct-v0.2", None, "llama2", "Tamil-adapted Llama 2, 7B", "community Tamil fine-tunes", 6.9),
    ("tamil-qwen25-7b-instruct", "Tamil-ai/tamil-qwen25-7b-instruct", None, "apache-2.0", "Tamil-adapted Qwen2.5, 7.6B (2026-03)", "community Tamil fine-tunes", 7.6),
    ("Sarvam-30B", "sarvamai/sarvam-30b", None, "apache-2.0", "32B MoE (6 of 128 experts active); ruling 2026-09-10; bf16 with CPU offload, run last", "Indian labs", 32.0),
]
CATEGORIES = ["ours", "base family", "big-lab small models", "Indian labs", "community Tamil fine-tunes"]
# order (Vignesh, 2026-09-14): finished models first, then Qwen3.5-2B, Sarvam-1, Gemma-3-4B, Qwen3.5-4B, tamil-qwen25-7b, the Llama-family
# models (Llama-3.2-3B, BharatGPT-3B on Llama 3.2, Tamil-Llama-7B on Llama 2), and Sarvam-30B at the very end; Ministral-3, Gemma-4, local gpt-oss-20b removed
_PRIORITY = ["tamil-lm-2b-instruct-r4", "Gemma-3-1B-it", "Llama-3.2-1B-Instruct", "Qwen3-1.7B-tamil-Instruct", "Qwen3.5-2B", "Sarvam-1",
             "Gemma-3-4B-it", "Qwen3.5-4B", "tamil-qwen25-7b-instruct",
             "Llama-3.2-3B-Instruct", "BharatGPT-3B-Indic", "Tamil-Llama-7B-instruct-v0.2", "Sarvam-30B"]
RUN_ORDER = sorted(MODELS, key=lambda m: (_PRIORITY.index(m[0]) if m[0] in _PRIORITY else -1, m[6]))   # unlisted models (skipped ones) first
SKIP = {"Param2-17B-A2.4B-Thinking": "its repository modelling code is written for transformers 4.x and does not build under the pinned transformers 5.15.1: it imports removed helpers (is_torch_fx_available, then ROPE_INIT_FUNCTIONS['default'], legacy attention-mask utilities); evidence logs/cmp_Param2-17B-A2.4B-Thinking.log and logs/param2_load_check.log (2026-09-13)",
        "Param-1-2.9B-Instruct": "its repository modelling code uses the legacy key-value cache API and rope_scaling keys that the pinned transformers 5.15.1 no longer provides (KeyError 'type', then DynamicCache not subscriptable); generation would need use_cache=False at about 7 hours per mode (evidence: logs/serving_vs_bare_param1.log)"}
# per-model environment for the harness subprocesses (only where the plain bf16 GPU load cannot work)
MODEL_ENV = {"Sarvam-30B": {"SUITE_DEVICE_MAP": "auto", "SUITE_TRUST_REMOTE": "1", "SUITE_GPU_MEM": "42GiB", "SUITE_CPU_MEM": "30GiB"},
             "Param2-17B-A2.4B-Thinking": {"SUITE_TRUST_REMOTE": "1"},
             "Param-1-2.9B-Instruct": {"SUITE_TRUST_REMOTE": "1"},
             # Ministral-3 (removed 2026-09-14) needed SUITE_MODEL_CLASS=AutoModelForImageTextToText, SUITE_FIX_MISTRAL_REGEX=1, SUITE_DEQUANTIZE_FP8=1
             "gpt-oss-20b": {"SUITE_DEVICE_MAP": "auto", "SUITE_GPU_MEM": "42GiB", "SUITE_CPU_MEM": "30GiB"}}
# table (b): the system prompt each model card recommends; absent = the card recommends none (the template alone is used)
CHAT_HINTS = {
    "tamil-lm-2b-instruct-r4": "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்.",
    "Tamil-Llama-7B-instruct-v0.2": "You are a helpful assistant.",   # the card's chat format uses this system line
    "tamil-qwen25-7b-instruct": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.",   # Qwen2.5 default system prompt kept by the fine-tune's template
}

def free_gb():
    import shutil; return round(shutil.disk_usage("/home/user").free / 1e9, 1)

def params_of(model_dir):
    try:
        from safetensors import safe_open
        from huggingface_hub import snapshot_download
        d = model_dir if os.path.isdir(model_dir) else snapshot_download(model_dir, allow_patterns=["*.safetensors", "*.json"])
        n = 0
        for f in glob.glob(os.path.join(d, "*.safetensors")):
            with safe_open(f, "pt") as sf:
                for k in sf.keys():
                    shape = sf.get_slice(k).get_shape(); m = 1
                    for s_ in shape: m *= s_
                    n += m
        return n
    except Exception:
        return None

def tokens_per_word(model_id, n=300):
    from transformers import AutoTokenizer
    import bench_loaders_understanding as B
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    items = B.load_tamil_heldout(); by = {it["id"]: it["text"] for it in items}
    ids = json.load(open(os.path.join(HERE, "splits", "tamil_heldout.json")))["dev"][:n]
    texts = [by[i] for i in ids if i in by]
    toks = sum(len(tok(t, add_special_tokens=False).input_ids) for t in texts); words = sum(len(t.split()) for t in texts)
    return round(toks / max(1, words), 2)

def has_chat_template(mid):
    """Chat-template mode runs only for chat-tuned models (ruling 2026-09-12): a base model without a template runs raw only.
    Returns True or False only when the tokenizer loaded; None when it could not be loaded after three attempts (a transient
    error during concurrent downloads marked Gemma-3-1B as template-less on 2026-09-12), and the caller then runs the chat phase
    rather than skipping it."""
    from transformers import AutoTokenizer, AutoProcessor
    for attempt in range(3):
        try:
            try:
                tok = AutoTokenizer.from_pretrained(mid, trust_remote_code=True)
            except Exception:
                tok = AutoProcessor.from_pretrained(mid, trust_remote_code=True).tokenizer
            return bool(getattr(tok, "chat_template", None))
        except Exception:
            time.sleep(10 * (attempt + 1))
    return None

def run_phase(name, mid, adapter, phase, a, size_b=2.0, batch=None):
    """Run one phase for one model; returns (ok, reason, seconds). Generation is batched (SUITE_GEN_BATCH) in every phase; a CUDA
    out-of-memory failure is retried once at half the batch and recorded in the state."""
    env = dict(os.environ, **MODEL_ENV.get(name, {}))
    bs = batch if batch is not None else batch_for(size_b)
    env["SUITE_GEN_BATCH"] = str(bs); env["SUITE_ATTN"] = ATTN
    if name not in ALONE: env["SUITE_GPU_FRACTION"] = f"{min(0.95, footprint_gb(size_b) / GPU_TOTAL_GB):.3f}"; env.setdefault("SUITE_GEN_TOKENS", "8000")
    log = os.path.join(ROOT, "logs", f"cmp_{name}_{phase}.log")
    if phase == "probe":
        out = os.path.join(HERE, "results", f"probe_cmp_{name}.json")
        cmd = [PY, os.path.join(HERE, "run_probe.py"), "--model", mid, "--out", out] + (["--adapter", adapter] if adapter else [])
    else:
        split = "dev" if phase == "raw_dev" else "test"
        stage = f"cmp_{name}" + ("_v2" if phase == "raw_dev" else "") + ("_chat" if phase == "chat_test" else "") + ("_trans" if phase == "trans_raw" else "") + ("_trans_chat" if phase == "trans_chat" else "")   # dev under the new harness: _v2 (the legacy single-item dev table stays until every model has a v2 row)
        model_arg, ad = mid, adapter
        if phase in ("chat_test", "trans_chat"):
            env["SUITE_CHAT"] = "1"; env["SUITE_SYSTEM_PROMPT"] = CHAT_HINTS.get(name, "")
            if name == "tamil-lm-2b-instruct-r4":
                model_arg, ad = a.ours_chat_dir, None   # the merged directory carries our chat template
        out = os.path.join(HERE, "results", f"{stage}_{split}.json")
        tasks = TASKS if split == "dev" else (TRANSLATION_TASKS if phase.startswith("trans_") else TEST_TASKS)
        cmd = [PY, os.path.join(HERE, "run_dev_capped.py"), "--stage", stage, "--model", model_arg, "--tasks", ",".join(tasks), "--cap", str(CAP), "--split", split] + (["--adapter", ad] if ad else [])
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
    open(log, "w").write(r.stdout + "\n" + r.stderr)
    if r.returncode != 0 and "out of memory" in (r.stderr or "").lower() and bs > 4 and phase != "probe":
        env["SUITE_GEN_BATCH"] = str(bs // 2)
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
        open(log, "a").write(f"\n[retry at batch {bs // 2} after CUDA out of memory]\n" + r.stdout + "\n" + r.stderr)
    if r.returncode != 0 or not os.path.exists(out):
        tail = [l for l in (r.stderr or r.stdout).strip().splitlines() if l.strip()][-1:] or ["no output"]
        return False, f"{phase}: {tail[0][:160]}", round(time.time() - t0)
    return True, "", round(time.time() - t0)

_EXPECTED = None
_EXPECTED_LOCK = __import__("threading").Lock()
def expected_harness():
    """The harness version every table row must carry: suite.harness_version() in batched eager mode. Computed once under a lock:
    the earlier version mutated os.environ per call, and two workers calling it at the same time could read each other's half-restored
    environment, see a different version key, and re-run a finished phase (Llama-3.2-1B raw test re-ran on 2026-09-13)."""
    global _EXPECTED
    with _EXPECTED_LOCK:
        if _EXPECTED is None:
            import suite
            old = {k: os.environ.get(k) for k in ("SUITE_GEN_BATCH", "SUITE_ATTN")}; os.environ["SUITE_GEN_BATCH"] = "32"; os.environ["SUITE_ATTN"] = ATTN
            try: _EXPECTED = suite.harness_version()
            finally:
                for k, v in old.items():
                    if v is None: os.environ.pop(k, None)
                    else: os.environ[k] = v
        return _EXPECTED

def phase_done(name, phase):
    """A phase is done when its result file exists and (for suite files) every row carries the current harness version; a file
    from an older harness is archived under results/prev_harness/ and the phase re-runs (ruling 2026-09-12: no mixed versions)."""
    if phase.startswith("trans_"):   # checked before any result file: a model captured during its main test pass has no re-run file (BharatGPT re-ran for nothing, 2026-09-13)
        import extract_score as XS
        stage = f"cmp_{name}" + ("_chat" if phase == "trans_chat" else "")
        return all(XS.local_texts(stage, t)[0] is not None for t in TRANSLATION_TASKS)
    f = phase_file(name, phase)
    if not os.path.exists(f): return False
    rows = json.load(open(f)); hv = version_key(expected_harness())
    if phase == "probe":   # probe files carry the harness version since bos-v1 (2026-09-13); older files re-run
        return version_key(rows.get("harness", "unversioned")) == hv
    return bool(rows) and all(version_key(r.get("harness", "unversioned")) == hv for r in rows)   # single-item and batched rows share the key

# Check v2 (ruling 2026-09-13): 100 dev items per generation task, single-item half for the generation tasks only (log-likelihood
# tasks are not batched; they are compared batched-only against the single-item Gemma-3-1B full-split reference in
# eval/results/batch_check.md). Noise thresholds widened by sqrt(3) for the smaller sample. Models checked under v1 (300 items,
# thresholds 2.0 / 0.02 / 0.03 / 0.05) keep their result; the spec is recorded per model in the state and in the table footnote.
CHECK_SPEC = "check-v2: 100 items per generation task, single-item half on generation tasks only, thresholds chrF++ 3.5, F1 0.035, contains 0.05, accuracy 0.05"
CHECK_CAP = 100
CHECK_TASKS = ["flores_en_ta", "flores_ta_en", "in22gen_en_ta", "in22gen_ta_en", "indicqa_ta", "gsm8k_en"]
CHECK_TOL = {"chrf++": 3.5, "bleu": 3.5, "f1": 0.035, "contains": 0.05, "acc": 0.05}

def mode_check(name, mid, adapter, size_b, log):
    """Batched harness safeguard (ruling 2026-09-12): right after a model's download and before its full pass, the 300-item dev
    check runs single-item and batched (both eager). Within noise on every task: the full pass runs batched; otherwise single-item.
    Returns ("batched" | "single", record). Files: eval/results/check_cmp_<name>_{single,batched}_dev.json."""
    env = dict(os.environ, **MODEL_ENV.get(name, {})); env["SUITE_ATTN"] = ATTN
    if name not in ALONE: env["SUITE_GPU_FRACTION"] = f"{min(0.95, footprint_gb(size_b) / GPU_TOTAL_GB):.3f}"; env.setdefault("SUITE_GEN_TOKENS", "8000")
    outs = {}
    for mode, bs in (("single", "0"), ("batched", str(batch_for(size_b)))):
        stage = f"check_cmp_{name}_{mode}"; out = os.path.join(HERE, "results", f"{stage}_dev.json"); outs[mode] = out
        if os.path.exists(out): continue
        env["SUITE_GEN_BATCH"] = bs
        cmd = [PY, os.path.join(HERE, "run_dev_capped.py"), "--stage", stage, "--model", mid, "--tasks", ",".join(CHECK_TASKS), "--cap", str(CHECK_CAP), "--split", "dev"] + (["--adapter", adapter] if adapter else [])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env)
        open(os.path.join(ROOT, "logs", f"{stage}.log"), "w").write(r.stdout + "\n" + r.stderr)
        if r.returncode != 0 or not os.path.exists(out):
            tail = [l for l in (r.stderr or r.stdout).strip().splitlines() if l.strip()][-1:] or ["no output"]
            return "single", {"gate": "not run", "reason": f"{mode} check failed: {tail[0][:160]}", "mode": "single"}
    S = {(r["benchmark"], r["metric"]): r["score"] for r in json.load(open(outs["single"]))}
    B = {(r["benchmark"], r["metric"]): r["score"] for r in json.load(open(outs["batched"]))}
    diffs = []; failed = []
    for k, b in B.items():
        if k not in S: continue
        d = b - S[k]; tol = CHECK_TOL.get(k[1], 0.05); within = abs(d) <= tol
        diffs.append({"task": k[0], "metric": k[1], "single": S[k], "batched": b, "diff": round(d, 4), "tol": tol, "within": within})
        if not within: failed.append(f"{k[0]} {k[1]} {d:+.3f}")
    mode = "single" if failed else "batched"
    rec = {"gate": "PASS" if not failed else "FAIL", "failed": failed, "diffs": diffs, "mode": mode, "n_items": CHECK_CAP, "spec": CHECK_SPEC}
    log(f"[check] {name}: batched-vs-single {rec['gate']}" + (f" ({'; '.join(failed)})" if failed else "") + f" -> full pass {mode}")
    return mode, rec

def write_extracts(name, log=print):
    """Extracted-score files (eval/extract_score.py) for a model's raw and chat captures, when complete and not yet written. CPU only."""
    import extract_score as XS
    for st in (f"cmp_{name}", f"cmp_{name}_chat"):
        out = os.path.join(HERE, "results", f"extract_{st}_test.json")
        try:
            stale = os.path.exists(out) and any(version_key(v) != version_key(expected_harness()) for r in json.load(open(out)) for v in str(r.get("source_harness", "unrecorded")).split(","))
            if (stale or not os.path.exists(out)) and all(XS.local_texts(st, t)[0] is not None for t in TRANSLATION_TASKS):
                r = subprocess.run([PY, os.path.join(HERE, "extract_score.py"), "--stage", st], capture_output=True, text=True, cwd=ROOT, timeout=900)
                log(f"[extract] {st}: " + ("written" if os.path.exists(out) else f"failed: {(r.stderr or r.stdout)[-160:]}"))
        except Exception as e:
            log(f"[extract] {st}: {type(e).__name__}: {str(e)[:120]}")

def phase_file(name, phase):
    """The result file a phase must have written; a phase counts as done only when this file exists (resume after a restart)."""
    if phase.startswith("trans_"):
        return os.path.join(HERE, "results", f"cmp_{name}_{'trans_chat' if phase == 'trans_chat' else 'trans'}_test.json")
    return os.path.join(HERE, "results", {"raw_dev": f"cmp_{name}_v2_dev.json", "raw_test": f"cmp_{name}_test.json",
                                          "chat_test": f"cmp_{name}_chat_test.json", "probe": f"probe_cmp_{name}.json"}[phase])

def empty_outputs(name):
    """True when the raw test translation outputs are (nearly all) empty: the harness could not drive the model."""
    d = os.path.join(HERE, "results", f"wrong_cmp_{name}_test", "flores_en_ta.jsonl")
    if not os.path.exists(d):
        return False
    rows = [json.loads(l) for l in open(d, encoding="utf-8") if l.strip()]
    return bool(rows) and sum(1 for r in rows if not (r.get("pred") or "").strip()) >= 0.9 * len(rows)

def main():
    """Parallel driver (ruling 2026-09-12): models run concurrently while the sum of their bf16 footprints plus headroom stays under
    GPU_CAP_GB; small models up to MAX_SMALL at a time, 7B-class up to MAX_7B, gpt-oss-20b and Sarvam-30B alone. Each worker keeps
    the download-run-purge rule for its own model (one model on disk per slot) with the 80 GB free-space check before each download.
    Resume: a phase is skipped only when its result file exists. Every phase runs batched, so every result file carries the same
    harness version; the tables refuse to mix versions. Batched mode requires eval/results/batch_check.json to say PASS."""
    import threading
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours-adapter", required=True); ap.add_argument("--ours-chat-dir", default="ckpt/final/tamil-lm-2b-instruct-sft4c")
    ap.add_argument("--only", default=None); ap.add_argument("--phases", default=",".join(PHASES)); ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--gpu-cap", type=float, default=GPU_CAP_GB)
    a = ap.parse_args()
    phases = [p for p in a.phases.split(",") if p in PHASES]
    expected_harness()   # computed once, before any worker thread starts
    state_p = os.path.join(HERE, "results", "comparison_bare_state.json")
    res = json.load(open(state_p)) if os.path.exists(state_p) else {}
    lock = threading.RLock()
    def save():
        with lock: json.dump(res, open(state_p, "w"), indent=1)
    def log(msg):
        with lock: print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    import baseline_storage as BS
    if not a.render_only:
        bc = os.path.join(HERE, "results", "batch_check.json")
        bcj = json.load(open(bc)) if os.path.exists(bc) else {}
        if bcj.get("gate") != "PASS" or bcj.get("expected_harness") != expected_harness():
            raise SystemExit(f"refusing to run batched: eval/results/batch_check.json is missing, not PASS, or verified a different harness version ({bcj.get('expected_harness')} vs {expected_harness()}) (ruling 2026-09-12)")
        only = set(a.only.split(",")) if a.only else None
        with lock:
            res.setdefault("_storage", {}).setdefault("free_gb_start", free_gb()); res["_storage"]["parallel"] = {"gpu_cap_gb": a.gpu_cap, "max_small": MAX_SMALL, "max_7b": MAX_7B}
            res["_storage"]["free_gb_end"] = "run in progress"   # explicit until the run ends (tables render as models land)
        save(); log(f"[storage] free at start: {res['_storage']['free_gb_start']} GB; GPU cap {a.gpu_cap} GB")
        pending = [m for m in RUN_ORDER if not only or m[0] in only]
        running = {}   # name -> (thread, footprint, size_b)

        def worker(name, mid, adapter, cat, size):
            with lock:
                r = res.get(name) or {}
                r.setdefault("phases", {}); res[name] = r
                if not isinstance(r.get("seconds"), dict): r["seconds"] = {"legacy_single_item_run": r.get("seconds")}   # pre-2026-09-12 state stored one number
            if name in SKIP:
                with lock: r["reason"] = SKIP[name]; r["skipped"] = True
                save(); return
            todo = [p for p in phases if not phase_done(name, p)]   # a recorded "skipped" chat phase is re-validated below, never trusted blindly
            if not todo:
                write_extracts(name, log); log(f"[cmp] {name}: all phases done (result files present)"); return
            ours = adapter == "OURS"; ad = a.ours_adapter if ours else adapter
            try:
                with fetch_lock:   # the free-space check and the download start are serialised across slots
                    BS.fetch(mid, log=log)
            except RuntimeError as e:
                with lock: res["_storage"]["stopped"] = str(e)
                save(); log(f"[storage] STOP: {e}"); return
            except Exception as e:
                with lock: r["reason"] = f"download failed: {type(e).__name__}: {str(e)[:120]}"
                save(); log(f"[cmp] {name}: {r['reason']}"); BS.purge(mid, log=log); return
            hv = expected_harness()
            if ours:
                mode, rec = "batched", {"gate": "PASS", "mode": "batched", "note": "verified in eval/results/batch_check.md (ours and Gemma-3-1B, 300 dev items)"}
            elif (r.get("mode_check") or {}).get("harness") == hv:
                mode, rec = r["mode_check"]["mode"], r["mode_check"]
            else:
                mode, rec = mode_check(name, mid, ad, size, log); rec["harness"] = hv
            with lock: r["mode_check"] = rec; r["gen_mode"] = mode
            save()
            if r["phases"].get("chat_test") == "skipped" and "trans_chat" in todo:
                todo.remove("trans_chat")
            if "chat_test" in todo and not ours and has_chat_template(mid) is False:   # only a confirmed absence skips the chat phase
                with lock: r["phases"]["chat_test"] = "skipped"; r["chat_note"] = "base model without a chat template: raw mode only (ruling 2026-09-12)"
                todo.remove("chat_test"); save(); log(f"[cmp] {name}: chat_test skipped (no chat template, confirmed)")
                if "trans_chat" in todo: todo.remove("trans_chat")
            elif "chat_test" in todo and r["phases"].get("chat_test") == "skipped":
                with lock: r["phases"]["chat_test"] = False; r.pop("chat_note", None)
                save(); log(f"[cmp] {name}: earlier chat_test skip was not confirmed; running it")
            for phase in todo:
                if phase_done(name, phase):   # audit 2026-09-13: the list was built once, so translation re-runs repeated what the test phases had just captured
                    log(f"[cmp] {name}: {phase} already satisfied (checked again before running)"); continue
                bs = batch_for(size) if mode == "batched" else 0
                log(f"[cmp] {name}: {phase} running ({'batch ' + str(bs) if bs else 'single-item'})")
                ok, why, sec = run_phase(name, mid, ad, phase, a, size_b=size, batch=bs)
                with lock:
                    r["phases"][phase] = ok; r["seconds"][phase] = sec; r["batch"] = bs
                    if not ok: r["reason"] = why
                    if phase == "raw_test" and ok and empty_outputs(name):
                        r["raw_note"] = "raw-prompt outputs mostly empty or degenerate (an instruct-only model without its template); its numbers stand in table (a) as measured, table (b) is the fair view"
                save(); log(f"[cmp] {name}: {phase} {'ok' if ok else 'FAILED ' + why} ({sec}s)")
                if not ok and "DEGENERATE" in why:
                    log(f"[DEGENERATE] {name} {phase}: the harness refused the output; rows are marked and will not render as scores (eval/degenerate_reviewed.json clears a reviewed flag)")
            if not r.get("params") or r.get("tok_per_word") is None:
                try:
                    pc, tw = params_of(mid), tokens_per_word(mid)
                    with lock: r["params"] = pc; r["tok_per_word"] = tw
                except Exception as e:
                    with lock: r["params_error"] = str(e)[:100]
            with lock:
                if all(r["phases"].get(p) in (True, "skipped") for p in phases): r.pop("reason", None)
            write_extracts(name, log)
            save(); BS.purge(mid, log=log)

        fetch_lock = threading.Lock()
        def fits(name, size):
            used = sum(f for _, f, _ in running.values()); fp = footprint_gb(size)
            if name in ALONE: return not running
            if any(n in ALONE for n in running): return False
            if used + fp > a.gpu_cap: return False
            live = [(f, sz) for n, (_, f, sz) in running.items() if n not in SKIP]   # skipped models hold no slot (they took both small slots at start, 2026-09-13)
            n_small = sum(1 for _, sz in live if sz < 5); n_big = sum(1 for _, sz in live if sz >= 5)
            return (n_small < MAX_SMALL) if size < 5 else (n_big < MAX_7B)
        control = os.path.join(HERE, "results", "comparison_control.json")   # {"remove": [model names]}: drops pending models without a restart
        while pending or running:
            try:
                drop = set(json.load(open(control)).get("remove", [])) if os.path.exists(control) else set()
                for m in [m for m in pending if m[0] in drop]:
                    pending.remove(m); log(f"[sched] removed {m[0]} from the pending list (eval/results/comparison_control.json)")
            except (OSError, ValueError) as e:
                log(f"[sched] control file unreadable: {e}")
            for m in list(pending):
                name, mid, adapter, lic, note, cat, size = m
                if name in SKIP or fits(name, size):
                    t = threading.Thread(target=worker, args=(name, mid, adapter, cat, size), daemon=True); t.start()
                    running[name] = (t, 0 if name in SKIP else footprint_gb(size), size); pending.remove(m)
                    if name not in SKIP: log(f"[sched] start {name} ({footprint_gb(size)} GB); running {[n for n in running]}; GPU budget used {sum(f for _, f, _ in running.values())} of {a.gpu_cap} GB")
                    if name in ALONE: break
            for n in [n for n, (t, _, _) in running.items() if not t.is_alive()]:
                running.pop(n); log(f"[sched] done {n}")
            if res.get("_storage", {}).get("stopped"): break
            time.sleep(15)
        with lock: res["_storage"]["free_gb_end"] = free_gb()
        save(); log(f"[storage] free at end: {res['_storage']['free_gb_end']} GB")
    render(res, a)

SHORT = {"flores_en_ta:chrf++": "FLORES en-ta chrF++", "flores_ta_en:chrf++": "FLORES ta-en chrF++", "in22gen_en_ta:chrf++": "IN22 en-ta chrF++", "in22gen_ta_en:chrf++": "IN22 ta-en chrF++",
         "milu_ta:acc": "MILU accuracy", "indicqa_ta:f1": "IndicQA F1", "indicqa_ta:contains": "IndicQA contains-answer rate", "belebele_ta:acc": "Belebele accuracy", "indicxnli_ta:acc": "IndicXNLI accuracy",
         "indicsentiment_ta:acc": "IndicSentiment accuracy", "mmlu_en:acc": "MMLU accuracy", "gsm8k_en:acc": "GSM8K accuracy", "tamil_heldout:bpc": "Tamil bpc (lower is better)", "tanglish_heldout:bpc": "Tanglish bpc (lower is better)",
         "probe_letter": "literature probe, letter log-likelihood accuracy (identify source and meaning)", "probe_option_identify": "literature probe, option-text accuracy, identify source", "probe_option_meaning": "literature probe, option-text accuracy, meaning"}
METRICS_TEST = ["flores_en_ta:chrf++", "flores_ta_en:chrf++", "in22gen_en_ta:chrf++", "in22gen_ta_en:chrf++", "milu_ta:acc", "indicqa_ta:f1", "indicqa_ta:contains", "tamil_heldout:bpc", "tanglish_heldout:bpc", "mmlu_en:acc", "gsm8k_en:acc"]
METRICS_MAIN = ["flores_en_ta:chrf++", "flores_ta_en:chrf++", "in22gen_en_ta:chrf++", "in22gen_ta_en:chrf++", "milu_ta:acc", "indicqa_ta:f1", "indicqa_ta:contains", "belebele_ta:acc", "indicxnli_ta:acc", "indicsentiment_ta:acc", "mmlu_en:acc", "gsm8k_en:acc", "tamil_heldout:bpc", "tanglish_heldout:bpc"]

DEGENERATE_CELLS = []; REVIEWED_NOTES = []   # degenerate-output check (ruling 2026-09-13): unreviewed flags show as "degenerate", reviewed ones are footnoted
VERSIONS = {}   # (table key) -> set of harness versions seen; a table refuses to render when it would mix versions (ruling 2026-09-12)
def load_scores(stage, split, table_key=None):
    p = os.path.join(HERE, "results", f"{stage}_{split}.json")
    if not os.path.exists(p): return {}
    rows = json.load(open(p))
    if table_key:
        VERSIONS.setdefault(table_key, set()).update(r.get("harness", "unversioned (pre-2026-09-12 harness)") for r in rows)
    out = {}
    for r in rows:
        k = f"{r['benchmark']}:{r['metric']}"
        if r.get("degenerate") and not r.get("degenerate_reviewed"):
            import suite as _S
            rv = _S.reviewed(r.get("stage", stage), r.get("split", "test"), r["benchmark"])
            if rv: r["degenerate_reviewed"] = rv
        if r.get("degenerate") and not r.get("degenerate_reviewed"):
            DEGENERATE_CELLS.append(f"{stage} {k}: {r['degenerate']}"); out[k] = "degenerate"   # shown as a flag, never as a score
            continue
        if r.get("degenerate_reviewed"): REVIEWED_NOTES.append(f"{r.get('stage', stage)} {r['benchmark']}: {r['degenerate']}; reviewed: {r['degenerate_reviewed']}")
        out[k] = r["score"]
    return out

def version_key(hv):
    """Table-mixing key: content hash and attention implementation; the generation mode (batched or single-item) is allowed to
    differ per model under the safeguard ruling of 2026-09-12 and is footnoted instead."""
    if ":" not in hv: return hv
    h, m = hv.split(":", 1); return h + ":" + (m.split("-", 1)[1] if "-" in m else "default-attention")

def check_versions(table_key):
    v = {version_key(x) for x in VERSIONS.get(table_key, set())}
    if len(v) > 1:
        raise MissingResult(f"table {table_key} would mix harness versions {sorted(v)}; every row of a table must come from one harness version (ruling 2026-09-12)")
    return next(iter(v)) if v else "no rows"

def table(rows, mode, split, title_note):
    metrics = (METRICS_MAIN if split == "dev" else METRICS_TEST) + (["probe_letter", "probe_option_identify", "probe_option_meaning"] if mode == "raw" else [])
    head = "| model | params | licence | tokens per Tamil word | " + " | ".join(SHORT[m] for m in metrics) + " |"
    sep = "|" + "---|" * (4 + len(metrics)); L = [title_note, ""]
    for cat in CATEGORIES:
        L += [f"**{cat}**", "", head, sep]
        for row in [r for r in rows if r["category"] == cat]:
            p = row.get("params"); ps = f"{p/1e9:.2f}B" if p else f"~{row['size_b']}B"
            sc = row["scores"][f"{mode}_{split}"]
            if row.get("not_run") or not sc:
                why = row.get("not_run") or (row.get("chat_note") if mode == "chat" and row.get("chat_note") else "not run")
                L.append(f"| {row['model']} | {ps} | {row['licence']} | | " + " | ".join([""] * len(metrics)) + f" | NOT RUN: {why}")
                continue
            cells = []
            for m in metrics:
                v = sc.get(m) if not m.startswith("probe") else row.get(m)
                if v is None:
                    raise MissingResult(f"{row['model']}: {m} missing in {mode}_{split} (ruling 2026-09-12: a missing result key fails the table)")
                cells.append(v if isinstance(v, str) else (f"{v:.1f}" if "chrf" in m else f"{v:.3f}"))
            tpw = row.get("tok_per_word")
            if tpw is None:
                raise MissingResult(f"{row['model']}: tokens per Tamil word missing")
            L.append(f"| {row['model']} | {ps} | {row['licence']} | {tpw} | " + " | ".join(cells) + " |")
        L.append("")
    return L

def public_note(text):
    """Card-facing wording (2026-09-14): the substance of a note without internal process references (who reviewed and when, ruling
    dates, log file paths)."""
    import re as _re
    t = _re.sub(r"\s*\((?:reviewed and )?(?:accepted|confirmed|approved)[^()]*\)", "", text)
    t = _re.sub(r"[;,]?\s*\(?evidence:? logs/[^)]*\)?", "", t)
    t = _re.sub(r"\s*\((?:ruling|rulings) [^()]*\)", "", t)
    return t.strip()

STATE_FOR_TABLES = {}
def TR_closed():
    import table_rank as _TR
    return _TR.closed_set()
def load_n(stage, split):
    p = os.path.join(HERE, "results", f"{stage}_{split}.json")
    return {f"{r['benchmark']}:{r['metric']}": r.get("n") for r in json.load(open(p))} if os.path.exists(p) else {}


def table_t(rows, mode, split, title_note):
    """Tables (a) and (b), transposed (2026-09-14): metrics as rows with their direction and tie margin, models as columns with their
    parameter count, a model-group row, best scores bold within the tie margin (eval/table_rank.py)."""
    import table_rank as TR
    metrics = METRICS_TEST + (["probe_letter", "probe_option_identify", "probe_option_meaning"] if mode == "raw" else [])
    shown = [r for r in rows if not r.get("not_run") and r["scores"].get(f"{mode}_{split}")]
    cols = []
    for cat in CATEGORIES:
        for r in [x for x in shown if x["category"] == cat]:
            p = r.get("params"); ps = f"{p/1e9:.2f}B" if p else f"~{r['size_b']}B"
            cols.append((r["model"], f"{r['model']} ({ps})", cat))
    stage_of = lambda n: f"cmp_{n}" if mode == "raw" else f"cmp_{n}_chat"
    table_rows = [(None, "licence", {r["model"]: r["licence"] for r in shown}, None)]
    tpw = {}
    for r in shown:
        if r.get("tok_per_word") is None: raise MissingResult(f"{r['model']}: tokens per Tamil word missing")
        tpw[r["model"]] = r["tok_per_word"]
    table_rows.append(("tok_per_word", "tokens per Tamil word", tpw, None))
    for m in metrics:
        vals, ns = {}, []
        for r in shown:
            v = r["scores"][f"{mode}_{split}"].get(m) if not m.startswith("probe") else r.get(m)
            if v is None: raise MissingResult(f"{r['model']}: {m} missing in {mode}_{split} (ruling 2026-09-12: a missing result key fails the table)")
            vals[r["model"]] = v
            if not m.startswith("probe"):
                n = load_n(stage_of(r["model"]), split).get(m)
                if n: ns.append(n)
        n = min(ns) if ns else (380 if m == "probe_letter" else 190)   # probe: identify source and meaning, 190 items each
        table_rows.append((m, SHORT[m], vals, n))
    body, decisions = TR.transposed(cols, table_rows)
    TR.write_decisions(f"{mode}_{split}", decisions)
    return [title_note, "", TR.CAPTION, ""] + body + [""]

def render(res, a):
    import suite
    rows = []
    active = [m for m in MODELS if m[0] not in SKIP]
    v2_complete = all(os.path.exists(os.path.join(HERE, "results", f"cmp_{m[0]}_v2_dev.json")) for m in active)
    dev_stage = (lambda n: f"cmp_{n}_v2") if v2_complete else (lambda n: f"cmp_{n}")
    bc = os.path.join(HERE, "results", "batch_check.json"); bcj = json.load(open(bc)) if os.path.exists(bc) else {}
    for name, mid, adapter, lic, note, cat, size in MODELS:
        r = res.get(name) or {}
        ph = r.get("phases") or {}
        row = {"model": name, "id": mid, "licence": lic, "note": note, "category": cat, "size_b": size, "params": r.get("params"), "tok_per_word": r.get("tok_per_word"),
               "scores": {"raw_dev": load_scores(dev_stage(name), "dev", "dev"), "raw_test": load_scores(f"cmp_{name}", "test", "a"), "chat_test": load_scores(f"cmp_{name}_chat", "test", "b")},
               "not_run": (SKIP.get(name) or r.get("reason")) if (name in SKIP or r.get("skipped")) else None, "phases": ph, "chat_note": r.get("chat_note"), "raw_note": r.get("raw_note")}
        # closed comparison (comparison_final.json, 2026-09-15): a model not run has no scores in any table, dev rows included
        final_not_run = TR_closed().get("not_run", {})
        if name in final_not_run and name not in SKIP:
            row["not_run"] = final_not_run[name]; row["scores"] = {"raw_dev": {}, "raw_test": {}, "chat_test": {}}
        # a model without its complete result set never shows partial numbers
        _need = (f"cmp_{name}_test.json", f"probe_cmp_{name}.json") + (() if (r.get("phases") or {}).get("chat_test") == "skipped" else (f"cmp_{name}_chat_test.json",))
        if not all(os.path.exists(os.path.join(HERE, "results", f)) for f in _need) and name not in SKIP and not r.get("skipped"):
            row["scores"] = {"raw_dev": {}, "raw_test": {}, "chat_test": {}}
        if name == "Gemma-3-1B-it" and bcj.get("test_gate_gemma_3_1b") == "FAIL":
            row["not_run"] = "batched harness failed the single-item comparison on its full test split (eval/results/batch_check.md)"; row["scores"]["raw_test"] = {}; row["scores"]["chat_test"] = {}
        pp = os.path.join(HERE, "results", f"probe_cmp_{name}.json")
        if os.path.exists(pp):
            p = json.load(open(pp)); row["probe_letter"] = p.get("letter_acc_choice_types"); ot = p.get("per_type_acc_option_text") or {}   # audit 2026-09-13: probe_acc is the mean of four types, two of them generation
            row["probe_option_identify"] = ot.get("identify_source"); row["probe_option_meaning"] = ot.get("meaning_mcq")
        rows.append(row)
    json.dump(rows, open(os.path.join(HERE, "results", "comparison_bare.json"), "w"), indent=1, ensure_ascii=False)
    va, vb, vd = check_versions("a"), check_versions("b"), check_versions("dev")   # raises on a mixed table
    st = dict(res.get("_storage") or {}); st.setdefault("free_gb_end", "run in progress")
    common = (f"Every number was produced locally by eval/suite.py and eval/run_probe.py on the LOCKED TEST SPLITS (full, no cap) with greedy decoding and bf16 weights; "
              "no number is copied from a paper or a model card. The metric and its direction are named in the first column of every row; each column is one model with its parameter count. Tokens per Tamil word: each model's tokenizer over the first 300 FLORES Tamil dev sentences. "
              f"Storage rule: one baseline on disk per parallel slot, purged after its results; free space at start {need(st, 'free_gb_start', what='storage record')} GB, " + (f"at end {st['free_gb_end']} GB. " if isinstance(st.get('free_gb_end'), (int, float)) else "at end: run in progress. ") +
              "Generation is greedy in left-padded batches with EAGER attention for every model, except GSM8K, which decodes one item at a time in every mode (batching shifted its long chain-of-thought answers): padded SDPA attention shifted scores on some architectures (Gemma-3-1B lost up to 2.6 chrF++ on Tamil-to-English), eager reproduces single-item decoding within noise on our model and on Gemma-3-1B (eval/results/batch_check.md, eval/HARNESS_NOTES.md). Every row of a table comes from one harness version, named in the table title.")
    global STATE_FOR_TABLES; STATE_FOR_TABLES = res
    ta = table_t(rows, "raw", "test", f"# Table (a): identical raw prompts, test split ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}, commit {suite.git_commit()}, harness version {va})\n\n" + common +
               " Table (a): the SAME raw prompt for every model (eval/prompts/*.txt), no chat template for any model including ours, so chat-tuned models that expect their template (Qwen3.5 thinking modes, Gemma) are penalised on generation tasks; that is the design of this table, not a defect of those models.")
    tb = table_t(rows, "chat", "test", f"# Table (b): each model with its own chat template and card-recommended system prompt, test split (harness version {vb})\n\n" + common +
               " Table (b): every model wrapped in its OWN chat template with the system prompt its model card recommends (none for most; listed below), thinking disabled where the template supports it; ours with its own chat template. A model without a chat template would keep the raw prompt here; every model in the table has one (Sarvam-1's tokenizer ships a Llama 2 style [INST] template). The literature probe runs on raw weights only and is shown in table (a).")
    import preamble_share as PS
    pre = []
    for n, *_ in MODELS:
        stage = f"cmp_{n}_chat"
        if os.path.exists(os.path.join(HERE, "results", f"{stage}_test.json")):
            a_, t_ = PS.local_share(stage)
            note = " (ours: an instruction-following result of the answer format taught in SFT, not a measure of translation quality)" if n == "tamil-lm-2b-instruct-r4" else ""
            pre.append(f"{n} {100*a_/t_:.1f}% ({a_} of {t_}){note}")
    tb += ["Translations scored by their first line, the harness rule for every model. Share of each model's translations whose first line is a preamble rather than a translation (the first non-empty line ends with a colon after markdown emphasis is removed; eval/preamble_share.py), which score near zero under that rule: " + "; ".join(pre) + ". The extracted-body score for every model is in table (e) (comparison_translation_rules.md), and every comparison claim uses it.", ""]
    tb += ["Bits per character in table (b) is the same measurement as in table (a), except for our model: with no start token, the first text token is scored after the end-of-sequence token, and our chat mode loads the instruct tokenizer, whose end-of-sequence token is <|im_end|> rather than the base tokenizer's <|endoftext|>. Quote our bpc from table (a).", ""]
    tb += ["System prompts used in table (b): " + "; ".join(f"{k}: \"{v}\"" for k, v in CHAT_HINTS.items() if k not in set(TR_closed().get("not_run", {})) | set(SKIP)) + "; every other model: none (template only).", ""]
    ours = next((r for r in rows if r["category"] == "ours"), None)
    if ours is not None:
        t = load_scores("sft4_final", "test")
        if t:
            rows = [dict(ours, model="tamil-lm-2b-instruct-r4 (locked TEST split)", scores={"raw_dev": t, "raw_test": t, "chat_test": {}}, probe_letter="no test split", probe_option_identify="no test split", probe_option_meaning="no test split")] + rows
    td = table(rows, "raw", "dev", ("# Dev split, up to 300 items per task (fewer where the dev split is smaller: IN22 204, IndicQA 255, Belebele 180, IndicSentiment 156, MMLU 100, GSM8K 40), identical raw prompts" + (" (harness version " + vd + ")" if v2_complete else " (legacy single-item harness, pre-versioning; re-run under the batched eager harness follows once every model has a v2 dev row)") + "; the test-split tables (raw and chat-template modes) carry our model now and each baseline as it lands. Our own model's row also shows its locked test numbers alongside, marked as test."))
    _not_run = set(TR_closed().get("not_run", {})) | set(SKIP)
    modes = {n: (res.get(n) or {}).get("gen_mode") for n, *_ in MODELS if (res.get(n) or {}).get("gen_mode") and n not in _not_run}
    checks = {n: (res.get(n) or {}).get("mode_check") or {} for n in modes}
    V1 = "check-v1: 300 items per generation task, thresholds chrF++ 2.0, F1 0.02, contains 0.03, accuracy 0.05"
    by_spec = {}
    for n in checks:
        by_spec.setdefault(checks[n].get("spec") or (checks[n].get("note") and "verified in eval/results/batch_check.md (300 dev items)") or V1, []).append(n)
    notes = ["", "Generation mode per model (batched harness safeguard: each model's dev check, batched against single-item, both eager, decides its mode; check used per model: " + " | ".join(f"{sp}: {', '.join(ns)}" for sp, ns in sorted(by_spec.items())) + "): "
             + "batched: " + (", ".join(n for n, m in modes.items() if m == "batched") or "none") + "; single-item: "
             + (", ".join(f"{n} (failed the check on {'; '.join(checks[n].get('failed', []))})" if checks[n].get("failed") else f"{n} ({checks[n].get('reason', 'check not run')})" for n, m in modes.items() if m == "single") or "none") + ".",
             "", "Models not run and why:"] + [f"- {r['model']}: {public_note(r['not_run'])}" for r in rows if r.get("not_run")]
    notes += [f"- {r['model']} (raw mode note): {r['raw_note']}" for r in rows if r.get("raw_note")]
    notes += ["", "Start token (harness rule bos-v1): raw prompts and bits-per-character texts begin with each tokenizer's own defined start token and carry no other special tokens; chat-templated prompts are tokenized as the template writes them. Before bos-v1, generation relied on the tokenizer to add the token (Gemma 4's tokenizer adds none, which made its raw outputs degenerate) and the log-likelihood tasks had none for any model."]
    ba = os.path.join(HERE, "results", "bos_before_after.json")
    if os.path.exists(ba):
        bj = json.load(open(ba)); moved = bj.get("material") or []
        notes += ["Effect of the start token on raw-mode MILU, MMLU and Belebele, per re-run model (eval/results/bos_before_after.md): " + ("; ".join(moved) + "." if moved else f"no model moved by {bj.get('threshold_points')} accuracy points or more." )]
    notes += ["", "Degenerate-output check: a generation task is refused when at least half of its generations repeat the prompt's last line or loop on one line, when a translation task scores chrF++ below 2 with non-empty generations, or when bpc exceeds 4.8 (Tamil) or 6.0 (Tanglish); refused cells read \"degenerate\" and never show a score."]
    notes += [f"- degenerate, not scored: {x}" for x in dict.fromkeys(DEGENERATE_CELLS)] + [f"- flagged and reviewed, shown as measured: {public_note(x)}" for x in dict.fromkeys(REVIEWED_NOTES)]
    for lg in glob.glob(os.path.join(ROOT, "logs", "cmp_gpt-oss-20b_raw_test.log")):
        for line in open(lg, encoding="utf-8", errors="ignore"):
            if "[suite] precision:" in line:
                notes += ["", "Precision footnote, gpt-oss-20b: " + line.split("[suite] precision:")[1].strip() + " (MXFP4 experts are kept only when the kernels package and a supported GPU are present; otherwise transformers dequantises them to bf16 at load, which changes numerics slightly)."]; break
    open(os.path.join(HERE, "results", "comparison_bare.md"), "w", encoding="utf-8").write("\n".join(ta + notes) + "\n")
    open(os.path.join(HERE, "results", "comparison_chat.md"), "w", encoding="utf-8").write("\n".join(tb + notes) + "\n")
    render_translation_rules(rows)
    open(os.path.join(HERE, "results", "comparison_dev.md"), "w", encoding="utf-8").write("\n".join(td + (notes if v2_complete else ["", "This dev table is the legacy single-item harness from before harness versions and before the start-token rule; the generation-mode and start-token notes of tables (a) and (b) do not apply to it."])) + "\n")
    print("\n".join(ta[:6]))


def render_translation_rules(rows):
    """Table (e) (ruling 2026-09-13): translation chrF++ under the two scoring rules, side by side, from the same generations:
    first line (the suite's rule) and extracted body (eval/extract_score.py, extract-v1). One table per mode; hosted models join the
    chat table. Only rows whose four translation captures exist are shown; a row is never mixed from different rule versions."""
    res = os.path.join(HERE, "results"); tasks = [("flores_en_ta", "FLORES en-ta"), ("flores_ta_en", "FLORES ta-en"), ("in22gen_en_ta", "IN22 en-ta"), ("in22gen_ta_en", "IN22 ta-en")]
    def load(fname):
        p = os.path.join(res, fname)
        if not os.path.exists(p): return None
        d = {(r["benchmark"], r["metric"]): r for r in json.load(open(p))}
        vers = {r["harness"] for r in d.values()}
        if vers != {"extract-v1"}: raise MissingResult(f"{fname}: extract rule versions {vers}; a table row must come from one rule version")
        return d
    import table_rank as TR
    L = [f"# Table (e): translation chrF++ under two scoring rules, locked test split ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
         "Both scores come from the same generations. First line: the harness rule used in tables (a), (b) and (d), text.split(newline)[0]. "
         "Extracted (rule extract-v1, eval/extract_score.py): markdown emphasis removed, leading empty lines and lines ending with a colon skipped, then the first remaining line. "
         "A model without its four translation captures yet is not listed; the captures for models that ran before capture existed come from a re-run of the translation tasks only.", "",
         TR.CAPTION, ""]
    srcs = {}
    for mode, suffix, title in (("raw", "", "identical raw prompts (as table a)"), ("chat", "_chat", "own chat template (as table b)")):
        cols, data = [], {}
        for r in rows:
            if r["model"].endswith("(locked TEST split)") or r.get("not_run") or not r["scores"].get(f"{mode}_test"): continue
            d = load(f"extract_cmp_{r['model']}{suffix}_test.json")
            if d is None: continue
            src_v = {x.get("source_harness", "unrecorded") for x in d.values()}
            srcs.setdefault(mode, set()).update(version_key(v) for x in src_v for v in x.split(","))
            sc = r["scores"].get(f"{mode}_test") or {}
            p_ = r.get("params"); ps = f"{p_/1e9:.2f}B" if p_ else f"~{r['size_b']}B"
            cols.append((r["model"], f"{r['model']} ({ps})", r["category"]))
            for t, _ in tasks:
                bad = sc.get(f"{t}:chrf++") == "degenerate"   # the suite refused these generations: no score from them in any table
                data[(r["model"], f"{t}:chrf++_firstline")] = "degenerate" if bad else need(d, (t, "chrf++_firstline"), "score")
                data[(r["model"], f"{t}:chrf++_extracted")] = "degenerate" if bad else need(d, (t, "chrf++_extracted"), "score")
        if mode == "chat":
            for label, slug in (("Gemini 3.5 Flash-Lite", "google_gemini-3.5-flash-lite"), ("GPT-5.4 nano", "openai_gpt-5.4-nano"), ("gpt-oss-20b (any provider)", "openai_gpt-oss-20b"), ("gpt-oss-120b (any provider)", "openai_gpt-oss-120b")):
                d = load(f"extract_hosted_{slug}_test.json")
                if d is None: continue
                cols.append((slug, label, "hosted"))
                for t, _ in tasks:
                    data[(slug, f"{t}:chrf++_firstline")] = need(d, (t, "chrf++_firstline"), "score"); data[(slug, f"{t}:chrf++_extracted")] = need(d, (t, "chrf++_extracted"), "score")
        L += [f"**{title}**", ""]
        if not cols:
            L += ["(no captures yet)", ""]; continue
        trows = []
        for t, tl in tasks:
            for rule, rl in (("firstline", "first line"), ("extracted", "extracted")):
                k = f"{t}:chrf++_{rule}"
                trows.append((k, f"{tl} chrF++, {rl}", {c[0]: data[(c[0], k)] for c in cols}, None))
        body, decisions = TR.transposed(cols, trows)
        TR.write_decisions(f"translation_rules_{mode}", decisions)
        L += body + [""]
    for mode, vs in srcs.items():
        vs.discard(version_key("unrecorded"))
        if len(vs) > 1: raise MissingResult(f"table (e), {mode} mode: local rows come from generation harness versions {sorted(vs)}; one table, one version")
        L.append(f"Generation harness of the local rows, {mode} mode: {', '.join(sorted(vs)) or 'not recorded (extract files written before 2026-09-13 21:00 UTC)'}; hosted rows: hosted-openrouter-v1.")
    open(os.path.join(res, "comparison_translation_rules.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

if __name__ == "__main__":
    main()
