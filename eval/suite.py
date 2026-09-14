import re
"""Tamil benchmark suite: registry, frozen prompts, scoring, runner.

Registry maps task name -> loader (module.function returning normalised
items), kind, metric. Prompt templates live in eval/prompts/<kind>.txt and are
committed (frozen). Splits live in eval/splits/<task>.json (made by
make_splits.py). Results are written as eval/results/<stage>_<split>.json rows:
{benchmark, split, n, metric, score, script, commit, timestamp}.

Kinds and scoring:
  mcq          loglik over answer letters                   -> acc
  nli          loglik over 3 Tamil label words              -> acc
  copa         loglik over the two alternatives (mean lp)   -> acc
  paraphrase   loglik over yes/no                           -> acc
  sentiment    loglik over pos/neg                          -> acc
  qa           greedy, first line                           -> token F1
  translation  greedy, first line                           -> chrF++ (sacrebleu chrF word_order=2), BLEU
  summarisation greedy, first paragraph                     -> ROUGE-L (rouge_score, character-tokenised)
  gsm8k        greedy CoT 256 tokens, last number           -> acc
  tanglish_ppl bits per character over the text            -> bpc (lower is better)
"""
import importlib, json, math, os, re, subprocess, time, unicodedata
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "prompts")
SPLITS = os.path.join(HERE, "splits")
RESULTS = os.path.join(HERE, "results")

# name: (loader "module:function", kind)
REGISTRY = {
    "milu_ta":          ("bench_loaders_knowledge:load_milu", "mcq"),
    "indicmmlu_pro_ta": ("bench_loaders_knowledge:load_indicmmlu_pro", "mcq"),
    "global_mmlu_ta":   ("bench_loaders_knowledge:load_global_mmlu", "mcq"),
    "belebele_ta":      ("bench_loaders_knowledge:load_belebele", "mcq"),
    "include_ta":       ("bench_loaders_knowledge:load_include", "mcq"),
    "mmlu_en":          ("bench_loaders_knowledge:load_mmlu", "mcq"),
    "gsm8k_en":         ("bench_loaders_knowledge:load_gsm8k", "gsm8k"),
    "indicxnli_ta":     ("bench_loaders_understanding:load_indicxnli_all", "nli"),
    "indiccopa_ta":     ("bench_loaders_understanding:load_indiccopa_all", "copa"),
    "indicxparaphrase_ta": ("bench_loaders_understanding:load_indicxparaphrase", "paraphrase"),
    "indicsentiment_ta": ("bench_loaders_understanding:load_indicsentiment_all", "sentiment"),
    "indicqa_ta":       ("bench_loaders_understanding:load_indicqa_all", "qa"),
    "flores_en_ta":     ("bench_loaders_understanding:load_flores_en_ta", "translation"),
    "flores_ta_en":     ("bench_loaders_understanding:load_flores_ta_en", "translation"),
    "in22gen_en_ta":    ("bench_loaders_understanding:load_in22gen_en_ta", "translation"),
    "in22gen_ta_en":    ("bench_loaders_understanding:load_in22gen_ta_en", "translation"),
    "xlsum_ta":         ("bench_loaders_understanding:load_xlsum", "summarisation"),
    "tanglish_heldout": ("bench_loaders_understanding:load_tanglish_heldout", "tanglish_ppl"),
    "tamil_heldout":    ("bench_loaders_understanding:load_tamil_heldout", "tanglish_ppl"),   # bpc over FLORES Tamil (2026-09-10)
}
# retention subsample sizes (fixed seed in make_splits)
SUBSAMPLE = {"mmlu_en": 500, "gsm8k_en": 200}
# dev cap per task for the loop (fast); test uses the full test split
DEV_CAP = 300

def nfc(s): return unicodedata.normalize("NFC", s)

def load_items(task):
    mod, fn = REGISTRY[task][0].split(":")
    return getattr(importlib.import_module(mod), fn)()

def prompt_template(kind):
    return open(os.path.join(PROMPTS, f"{kind}.txt"), encoding="utf-8").read()

def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, cwd=os.path.dirname(HERE)).stdout.strip()
    except Exception:
        return "unknown"

# ------------------------------------------------------------------ model ops
_CHAT_WARNED = set()
def chat_wrap(tok, prompt):
    """Table (b) mode (ruling 2026-09-12): SUITE_CHAT=1 wraps the task prompt in the model's own chat template, with the
    card-recommended system prompt from SUITE_SYSTEM_PROMPT when one is set, thinking disabled where the template supports
    it. A model without a chat template (a base model) keeps the raw prompt, and the run records that."""
    if os.environ.get("SUITE_CHAT", "0") != "1" or not getattr(tok, "chat_template", None):
        return prompt
    sysp = os.environ.get("SUITE_SYSTEM_PROMPT", "").strip()
    msgs = ([{"role": "system", "content": sysp}] if sysp else []) + [{"role": "user", "content": prompt}]
    kw = {"enable_thinking": False} if "enable_thinking" in str(tok.chat_template) else {}
    if "date_string" in str(tok.chat_template): kw["date_string"] = CHAT_DATE
    try:
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **kw)
    except Exception:
        try:   # templates that reject a system role (Gemma): fold the system prompt into the user turn
            msgs = [{"role": "user", "content": (sysp + "\n\n" if sysp else "") + prompt}]
            return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, **kw)
        except Exception as e:
            if "wrap" not in _CHAT_WARNED:
                _CHAT_WARNED.add("wrap"); print(f"[suite] chat template failed ({type(e).__name__}); raw prompt used")
            return prompt

_THINK = re.compile(r"<think>.*?</think>\s*", re.S)
def strip_think(text):
    return _THINK.sub("", text).lstrip()

# Start token (harness rule bos-v1, ruling 2026-09-13). Raw prompts and bpc texts begin with the tokenizer's own defined start token
# (bos_token_id) whenever it defines one, and carry no other special tokens. Before bos-v1 the harness relied on the tokenizer to add
# it: generation and bpc used add_special_tokens=True (Gemma 4's tokenizer adds none, and its raw outputs degenerated), and the
# log-likelihood tasks used add_special_tokens=False (no model had a start token on MILU, MMLU, Belebele and the other choice tasks in
# raw mode). Chat-templated prompts are unchanged: the template writes its own tokens and is tokenized without special tokens.
PROMPT_RULE = "bos-v1"
# Harness v3 (audit ruling 2026-09-13), on top of bos-v1: per-tokenizer generation caps with a stop once the scored line is complete,
# numeric GSM8K comparison, bpc over every character of the text, letter continuations without the leading space after a chat
# template, a fixed date in date-aware chat templates, eager attention on every load path, batches ordered by token length, a
# within-line loop rule in the degenerate check. eval/HARNESS_NOTES.md has the evidence for each.
HARNESS_RULES = "v3"
CHAT_DATE = "13 Sep 2026"   # Llama 3.2 style templates otherwise write today's date into every prompt; the date of the first chat runs

def start_ids(tok):
    b = getattr(tok, "bos_token_id", None)
    return [b] if b is not None else []

def raw_ids(tok, text):
    """Token ids of a raw prompt or a bpc text under bos-v1."""
    ids = tok(text, add_special_tokens=False).input_ids
    s = start_ids(tok)
    return s + ids if s and (not ids or ids[0] != s[0]) else ids

def prompt_ids(tok, wrapped, prompt):
    """A prompt after chat_wrap: raw (no chat template applied) under bos-v1, templated text without added special tokens."""
    return raw_ids(tok, wrapped) if wrapped == prompt else tok(wrapped, add_special_tokens=False).input_ids

@torch.no_grad()
def cont_loglik(model, tok, prompt, cont):
    """Mean log-prob per token of continuation `cont` after `prompt`."""
    w = chat_wrap(tok, prompt)
    p_ids = prompt_ids(tok, w, prompt)
    if w != prompt and w[-1:].isspace():   # after a chat template the answer starts a fresh turn: "A", not " A" (audit 2026-09-13: " A" put
        cont = cont.lstrip(" ")            # the letter prior on one option, e.g. Qwen3.5-2B chat MMLU 0.25 against raw 0.49)
    c_ids = tok(cont, add_special_tokens=False).input_ids
    ids = torch.tensor([p_ids + c_ids], device="cuda")
    logits = model(input_ids=ids).logits[0]
    lp = torch.log_softmax(logits[len(p_ids)-1:-1].float(), -1)
    tgt = ids[0, len(p_ids):]
    return lp.gather(1, tgt.unsqueeze(1)).mean().item()

def gen_batch_size():
    """SUITE_GEN_BATCH: 0 (default) = one item at a time; N = left-padded greedy batches of N (ruling 2026-09-12; verified against
    single-item numbers in eval/results/batch_check.md before use)."""
    try: return int(os.environ.get("SUITE_GEN_BATCH", "0"))
    except ValueError: return 0

def gen_mode():
    """"batched" or "single": the version key names the code path, not the batch size (the size is stored per row as gen_batch)."""
    m = "batched" if gen_batch_size() > 0 else "single"
    return m + (f"-{os.environ['SUITE_ATTN']}" if os.environ.get("SUITE_ATTN") else "")   # the attention implementation is part of the version

def harness_version():
    """Content hash of the harness (suite, prompts, loaders) plus the generation mode; stored in every result row so tables can
    refuse to mix versions (ruling 2026-09-12)."""
    import hashlib, glob as _g
    h = hashlib.sha1()
    for f in sorted([os.path.join(HERE, "suite.py"), os.path.join(HERE, "run_probe.py"), os.path.join(HERE, "literature_probe.jsonl")] + _g.glob(os.path.join(HERE, "prompts", "*.txt")) + _g.glob(os.path.join(HERE, "bench_loaders_*.py")) + _g.glob(os.path.join(SPLITS, "*.json"))):
        h.update(open(f, "rb").read())
    return f"{h.hexdigest()[:10]}:{gen_mode()}"   # the hash covers PROMPT_RULE (bos-v1) and the degenerate-output check, both in this file

GEN_TOKENS_BUDGET = 8000   # prompt tokens per batch (fixed in the harness since v3; the driver used 8,000 and the notes said 12,000)
GEN_CAPS = {}              # task -> generation cap used in this run (recorded in each row)

def _ceil16(x): return int(-(-x // 16) * 16)

def gen_cap(tok, base, refs):
    """Generation cap for this tokenizer (audit 2026-09-13: fixed caps of 160, 48 and 64 tokens cut high-fertility tokenizers mid-answer,
    Llama-3.2 needs more than 160 tokens for 725 of 1,012 FLORES Tamil references): the larger of the task's base cap and 1.25 times the
    99th-percentile reference length in this tokenizer's tokens, rounded up to 16. Generation stops once the scored line is complete
    (stop rule below), so a larger cap costs time only for answers that actually need it."""
    lens = sorted(len(tok(r, add_special_tokens=False).input_ids) for r in refs if r)
    if not lens: return base
    p99 = lens[min(len(lens) - 1, int(0.99 * len(lens)))]
    return max(base, _ceil16(1.25 * p99))

def _nl_ids(tok):
    ids = getattr(tok, "_suite_nl_ids", None)
    if ids is None:
        ids = set()
        for i in range(len(tok)):
            try:
                if "\n" in tok.decode([i]): ids.add(i)
            except Exception: pass
        tok._suite_nl_ids = ids
    return ids

def scored_line_complete(text, mode):
    """Stop rule. "line": a completed line that is neither empty nor a preamble (ends with a colon after markdown emphasis is removed)
    exists, so both the first-line score and the extracted score (extract-v1) are already decided. "para": a blank line follows text."""
    text = strip_think(text)
    if "<think>" in text: return False
    if mode == "para": return bool(text.strip()) and "\n\n" in text.lstrip()
    from preamble_share import strip_emphasis
    return any(strip_emphasis(l) and not strip_emphasis(l).endswith(":") for l in text.split("\n")[:-1])

class _LineStop:
    """Per-row stopping criterion for generate(): checked only on steps where a row emitted a token containing a newline."""
    def __init__(self, tok, start, mode):
        self.tok, self.start, self.mode, self.nl = tok, start, mode, _nl_ids(tok); self.done = None
    def __call__(self, input_ids, scores, **kw):
        if self.done is None: self.done = torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)
        last = input_ids[:, -1].tolist()
        for r, t in enumerate(last):
            if not self.done[r] and t in self.nl and scored_line_complete(self.tok.decode(input_ids[r, self.start:], skip_special_tokens=True), self.mode):
                self.done[r] = True
        return self.done.clone()

def _stops(tok, start, stop):
    if not stop: return None
    from transformers import StoppingCriteriaList
    return StoppingCriteriaList([_LineStop(tok, start, stop)])

@torch.no_grad()
def greedy_batch(model, tok, prompts, max_new, stop=None):
    """Greedy decoding for a list of prompts in left-padded batches. Each row's continuation is decoded from the shared padded
    length, so per-item outputs are independent of batch composition up to padding numerics."""
    bs = gen_batch_size()
    if bs <= 0:
        return [greedy(model, tok, p, max_new, stop=stop) for p in prompts]
    wrapped = [chat_wrap(tok, p) for p in prompts]
    add_special = [w == p for w, p in zip(wrapped, prompts)]
    outs = [None] * len(prompts)
    old_side = tok.padding_side; tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    budget = GEN_TOKENS_BUDGET   # prompt tokens per batch: bounds the KV cache (long IndicQA contexts)
    pids = {i: prompt_ids(tok, wrapped[i], prompts[i]) for i in range(len(prompts))}
    lens = {i: len(pids[i]) for i in pids}
    order = sorted(range(len(prompts)), key=lambda i: (lens[i], i))   # batches ordered by token length (v3; characters before), so the budget holds
    try:
        k = 0
        while k < len(order):
            longest = lens[order[min(k + bs, len(order)) - 1]]   # length-sorted, so the last item of a candidate batch is its longest
            n = max(1, min(bs, budget // max(1, longest)))
            idx = order[k:k + n]; k += n
            width = max(lens[i] for i in idx)   # left padding, built from the same ids the single-item path uses
            ids = torch.tensor([[tok.pad_token_id] * (width - lens[i]) + pids[i] for i in idx]).cuda()
            mask = torch.tensor([[0] * (width - lens[i]) + [1] * lens[i] for i in idx]).cuda()
            out = model.generate(input_ids=ids, attention_mask=mask, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id, stopping_criteria=_stops(tok, ids.shape[1], stop))
            for j, i in enumerate(idx):
                text = tok.decode(out[j, ids.shape[1]:], skip_special_tokens=True)
                outs[i] = strip_think(text) if not add_special[i] else text
    finally:
        tok.padding_side = old_side
    return outs

@torch.no_grad()
def greedy(model, tok, prompt, max_new, stop=None):
    wrapped = chat_wrap(tok, prompt)
    ids = torch.tensor([prompt_ids(tok, wrapped, prompt)]).cuda()
    out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                         pad_token_id=tok.eos_token_id, stopping_criteria=_stops(tok, ids.shape[1], stop))
    text = tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)
    return strip_think(text) if wrapped != prompt else text

@torch.no_grad()
def bpc(model, tok, text):
    """Bits per character over every character of the text (v3). Context token: the tokenizer's start token, or its end-of-sequence
    token when it defines no start token (the lm-eval convention); before v3 a tokenizer without a start token left its first text token
    unscored and uncounted (our model counted 98.0 percent of Tamil characters, 96.4 percent of Tanglish)."""
    t_ids = tok(text, add_special_tokens=False).input_ids
    ctx = start_ids(tok) or ([tok.eos_token_id] if tok.eos_token_id is not None else [])
    if not ctx or not t_ids: return None
    kept = t_ids[:4096 - len(ctx)]
    ids = torch.tensor([ctx + kept]).cuda()
    loss = model(input_ids=ids, labels=ids).loss.item()
    nats = loss * (ids.shape[1] - 1)
    chars = len(text) if len(kept) == len(t_ids) else len(tok.decode(kept))
    return nats / max(1, chars) / math.log(2)

# ------------------------------------------------------------------ metrics
def token_f1(pred, gold):
    p, g = pred.split(), gold.split()
    if not p or not g:
        return float(p == g)
    common = {}
    for w in p:
        common[w] = common.get(w, 0) + 1
    overlap = sum(min(common.get(w, 0), g.count(w)) for w in set(g))
    if overlap == 0:
        return 0.0
    pr, rc = overlap / len(p), overlap / len(g)
    return 2 * pr * rc / (pr + rc)

def squash(s):
    return re.sub(r"[^஀-௿A-Za-z0-9]+", "", nfc(s))

# ------------------------------------------------------------------ degenerate-output check (ruling 2026-09-13)
# Three broken runs were caught by eye (Gemma 4 raw prompts without a start token, among them); the harness now refuses them. A
# generation task is DEGENERATE when at least DEGEN_SHARE of its generations are non-empty and repeat the prompt's last line (the
# first line equals it) or loop on one line (one line at least DEGEN_REPEATS times and at least 80% of the lines), or when a
# translation task scores chrF++ below DEGEN_CHRF with at least half of its generations non-empty. Log-likelihood tasks are
# DEGENERATE when bpc exceeds DEGEN_BPC for the text set. run() writes the rows with a "degenerate" field and then exits with an
# error; renderers refuse such rows.
# Calibrated on every generation captured before the check existed (2026-09-13): only Gemma-4-E4B's no-start-token runs trip the
# repetition rule (83 to 99 percent of generations; the highest share among the other models is Qwen3.5-2B base in raw mode, 40
# percent). A flag is not always an artefact: Qwen3-1.7B-tamil in chat mode answers Tamil-to-English requests in Tamil (1,000 of 1,012
# generations in Tamil script), chrF++ 1.97. Such a flag is cleared only by a reviewed entry in eval/degenerate_reviewed.json, with the
# reason, which the table footnotes; an unreviewed flag stops the run and the render. bpc limits sit above the highest real value
# (Tamil 4.45, Qwen3.5-2B; Tanglish 4.41, Qwen3-1.7B-tamil) and below the no-start-token Gemma 4 values (Tamil 5.03, Tanglish 7.09).
DEGEN_SHARE = 0.5; DEGEN_REPEATS = 5; DEGEN_CHRF = 2.0; DEGEN_BPC = {"tamil_heldout": 4.8, "tanglish_heldout": 6.0}
DEGENERATE = {}   # task -> reason, filled by score_items for the current run
REVIEWED_FILE = os.path.join(HERE, "degenerate_reviewed.json")

def reviewed(stage, split, task):
    """The review note clearing a degenerate flag for this stage, split and task, or None."""
    try: rv = json.load(open(REVIEWED_FILE, encoding="utf-8"))
    except (OSError, ValueError): return None
    return (rv.get(f"{stage}_{split}") or {}).get(task)

def _lines(t):
    return [l.strip() for l in (t or "").split("\n") if l.strip()]

def degenerate_generation(prompt, text):
    L = _lines(text)
    if not L: return None
    last = (_lines(prompt) or [""])[-1]
    if last and L[0] == last: return "repeats the prompt's last line"
    top = max(set(L), key=L.count); c = L.count(top)
    if c >= DEGEN_REPEATS and c >= 0.8 * len(L): return "loops on one line"
    if len(L) >= 2 * DEGEN_REPEATS and len(set(L)) <= 2: return "cycles between two lines"
    w = L[0].split()
    if len(w) >= 3 * DEGEN_REPEATS:
        grams = [tuple(w[i:i + 3]) for i in range(len(w) - 2)]
        g = max(set(grams), key=grams.count)
        if grams.count(g) >= DEGEN_REPEATS and grams.count(g) * 3 >= 0.6 * len(w): return "loops within its first line"
    return None

def degenerate_task(prompts, gens, chrf=None):
    n = max(1, len(gens)); nonempty = sum(1 for g in gens if _lines(g))
    bad = [degenerate_generation(p, g) for p, g in zip(prompts, gens)]
    k = sum(1 for b in bad if b)
    if k >= DEGEN_SHARE * n:
        why = max(set(b for b in bad if b), key=lambda x: bad.count(x))
        return f"{k} of {n} generations degenerate (mostly: {why})"
    if chrf is not None and chrf < DEGEN_CHRF and nonempty >= 0.5 * n:
        ta = sum(1 for g in gens if re.search("[\u0b80-\u0bff]", g or ""))
        return f"chrF++ {chrf:.2f} with {nonempty} of {n} generations non-empty ({ta} contain Tamil script)"
    return None

def _flag(task, reason):
    if reason:
        DEGENERATE[task] = reason
        print(f"[suite] DEGENERATE {task}: {reason}", flush=True)

# ------------------------------------------------------------------ scoring
def score_items(kind, items, model, tok, log_wrong=None, task=""):
    """Returns (metrics dict, list of per-item records)."""
    tmpl = kind
    if kind == "mcq" and task.endswith("_en"):
        tmpl = "mcq_en"   # English retention tasks use an English prompt
    T = prompt_template(tmpl) if kind != "tanglish_ppl" else None
    recs = []
    if kind == "mcq":
        L = "ABCDEFGHIJ"   # IndicMMLU-Pro has up to 10 options
        for it in items:
            ch = it["choices"][:10]
            opts = "\n".join(f"{L[i]}. {c}" for i, c in enumerate(ch))
            p = T.format(question=it["question"], options=opts)
            lps = [cont_loglik(model, tok, p, " " + L[i]) for i in range(len(ch))]
            pred = int(max(range(len(ch)), key=lambda i: lps[i]))
            recs.append({"id": it["id"], "ok": pred == it["answer_idx"], "pred": pred})
        return {"acc": sum(r["ok"] for r in recs) / len(recs)}, recs
    if kind in ("nli", "paraphrase", "sentiment", "copa"):
        labels = {"nli": [" ஆம்", " ஒருவேளை", " இல்லை"],
                  "paraphrase": [" ஆம்", " இல்லை"],
                  "sentiment": [" நேர்மறை", " எதிர்மறை"]}
        for it in items:
            if kind == "copa":
                q = "காரணம்" if it.get("question") == "cause" else "விளைவு"
                p = T.format(premise=it["premise"], question=q)
                lps = [cont_loglik(model, tok, p, " " + it["choice1"]),
                       cont_loglik(model, tok, p, " " + it["choice2"])]
            else:
                p = T.format(**{k: v for k, v in it.items() if isinstance(v, str)})
                lps = [cont_loglik(model, tok, p, lab) for lab in labels[kind]]
            pred = int(max(range(len(lps)), key=lambda i: lps[i]))
            recs.append({"id": it["id"], "ok": pred == it["label_idx"], "pred": pred})
        return {"acc": sum(r["ok"] for r in recs) / len(recs)}, recs
    if kind == "qa":
        f1s = []; cont = []
        qps = [T.format(context=it["context"][:3000], question=it["question"]) for it in items]
        cap = GEN_CAPS[task] = gen_cap(tok, 48, [max(it["answers"], key=len) for it in items if it["answers"]]) if tok is not None else 48
        gens = greedy_batch(model, tok, qps, cap, stop="line"); _flag(task, degenerate_task(qps, gens))
        for it, g0 in zip(items, gens):
            g = g0.split("\n")[0].strip()
            f1 = max(token_f1(squash_words(g), squash_words(a)) for a in it["answers"]) if it["answers"] else 0.0
            # contains-answer: a gold span appears inside the prediction (whitespace-squashed); insensitive to answer length (ruling 2026-09-11)
            c = 1.0 if it["answers"] and any(squash_words(a) and squash_words(a) in squash_words(g) for a in it["answers"]) else 0.0
            f1s.append(f1); cont.append(c)
            recs.append({"id": it["id"], "ok": f1 >= 0.5, "pred": g, "f1": f1, "contains": c})
        return {"f1": sum(f1s) / len(f1s), "contains": sum(cont) / len(cont)}, recs
    if kind == "translation":
        import sacrebleu
        hyps, refs = [], []
        ps = []
        for it in items:
            src_lang, tgt_lang = ("English", "Tamil") if it["direction"] == "en-ta" else ("Tamil", "English")
            ps.append(T.format(src_lang=src_lang, tgt_lang=tgt_lang, src=it["src"]))
        cap = GEN_CAPS[task] = gen_cap(tok, 160, [it["tgt"] for it in items]) if tok is not None else 160
        tgens = greedy_batch(model, tok, ps, cap, stop="line")
        for it, g0 in zip(items, tgens):
            g = g0.split("\n")[0].strip()
            hyps.append(g); refs.append(it["tgt"])
            recs.append({"id": it["id"], "pred": g, "ref": it["tgt"]})
        chrfpp = sacrebleu.CHRF(word_order=2).corpus_score(hyps, [refs]).score
        _flag(task, degenerate_task(ps, tgens, chrf=chrfpp))
        tok_kind = "none" if items[0]["direction"] == "en-ta" else "13a"
        bleu = sacrebleu.BLEU(tokenize=tok_kind).corpus_score(hyps, [refs]).score
        for r in recs:
            r["ok"] = sacrebleu.CHRF(word_order=2).sentence_score(r["pred"], [r["ref"]]).score >= 30
        return {"chrf++": chrfpp, "bleu": bleu}, recs
    if kind == "summarisation":
        from rouge_score import rouge_scorer
        sc = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False, tokenizer=CharTok())
        rl = []
        sps = [T.format(text=it["text"][:3500]) for it in items]
        cap = GEN_CAPS[task] = gen_cap(tok, 120, [it["summary"] for it in items]) if tok is not None else 120
        gens = greedy_batch(model, tok, sps, cap, stop="para"); _flag(task, degenerate_task(sps, gens))
        for it, g0 in zip(items, gens):
            g = g0.split("\n\n")[0].strip()
            s = sc.score(it["summary"], g)["rougeL"].fmeasure
            rl.append(s)
            recs.append({"id": it["id"], "ok": s >= 0.25, "pred": g, "rougeL": s})
        return {"rougeL": sum(rl) / len(rl)}, recs
    if kind == "gsm8k":
        # GSM8K decodes one item at a time even in batched mode: its 256-token chain-of-thought generations diverge under batched
        # numerics (3 to 4 of 40 dev items flipped on both check models, eval/results/batch_check.md, 2026-09-12); the split is small
        # (160 test items) so single-item decoding costs little.
        gps = [T.format(question=it["question"]) for it in items]
        GEN_CAPS[task] = 512
        gens = [greedy(model, tok, p, 512) for p in gps]; _flag(task, degenerate_task(gps, gens))
        for it, g in zip(items, gens):
            nums = re.findall(r"-?\d[\d,]*\.?\d*", g)
            pred = nums[-1].replace(",", "").rstrip(".") if nums else ""
            gold = it["answer_numeric"].replace(",", "")
            try: ok = pred != "" and abs(float(pred) - float(gold)) < 1e-6   # numeric (v3): "42.00" equals "42"; 46 such answers were marked wrong
            except ValueError: ok = pred == gold
            recs.append({"id": it["id"], "ok": ok, "pred": pred})
        return {"acc": sum(r["ok"] for r in recs) / len(recs)}, recs
    if kind == "tanglish_ppl":
        vals = []
        for it in items:
            b = bpc(model, tok, it["text"])
            if b is not None:
                vals.append(b); recs.append({"id": it["id"], "bpc": b})
        m = sum(vals) / len(vals)
        if task in DEGEN_BPC and m > DEGEN_BPC[task]: _flag(task, f"bpc {m:.2f} above {DEGEN_BPC[task]}")
        return {"bpc": m}, recs
    raise ValueError(kind)

def squash_words(s):
    return " ".join(re.findall(r"[஀-௿A-Za-z0-9]+", nfc(s).lower()))

class CharTok:
    """rouge_score tokenizer: characters (Tamil has no reliable stemmer)."""
    def tokenize(self, text):
        return [c for c in re.sub(r"\s+", "", nfc(text))]

# ------------------------------------------------------------------ runner
def _precision_note(model):
    """Print how quantised weights were loaded (gpt-oss MXFP4 experts stay MXFP4 only when the kernels package and a supported
    GPU are present; otherwise transformers dequantises them to bf16). The comparison driver copies the line into the footnote."""
    try:
        qc = getattr(model.config, "quantization_config", None)
        if qc is None:
            return
        method = qc.get("quant_method") if isinstance(qc, dict) else getattr(qc, "quant_method", None)
        deq = qc.get("dequantize") if isinstance(qc, dict) else getattr(qc, "dequantize", None)
        kinds = {}
        for n, p in model.named_parameters():
            if "expert" in n:
                kinds[str(p.dtype)] = kinds.get(str(p.dtype), 0) + 1
        print(f"[suite] precision: quant_method={method} dequantize={deq} expert parameter dtypes={kinds or 'no expert params'}", flush=True)
    except Exception as e:
        print(f"[suite] precision note failed: {e}")

def load_tokenizer(name, trc):
    """Tokenizer, with the per-model fixes the driver sets: SUITE_FIX_MISTRAL_REGEX=1 for Mistral 3 tokenizers, whose shipped pre-tokenizer
    regex is wrong unless fix_mistral_regex=True (transformers warns that tokenization is otherwise incorrect)."""
    import transformers as _tf
    kw = {"fix_mistral_regex": True} if os.environ.get("SUITE_FIX_MISTRAL_REGEX") == "1" else {}
    try:
        return _tf.AutoTokenizer.from_pretrained(name, trust_remote_code=trc, **kw)
    except Exception:
        return _tf.AutoProcessor.from_pretrained(name, trust_remote_code=trc, **kw).tokenizer

def load_kwargs():
    """SUITE_DEQUANTIZE_FP8=1: a checkpoint released in FP8 (Ministral 3) is dequantised to bf16 at load, so every model runs in bf16."""
    if os.environ.get("SUITE_DEQUANTIZE_FP8") == "1":
        from transformers import FineGrainedFP8Config
        return {"quantization_config": FineGrainedFP8Config(dequantize=True)}
    return {}

def load_model(model_name, adapter=None, tokenizer=None, embeddings=None):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    trc = os.environ.get("SUITE_TRUST_REMOTE", "0") == "1"   # only for models whose architecture is not in transformers (Sarvam-30B MoE)
    import transformers as _tf
    # SUITE_MODEL_CLASS: the loader class the model card documents when it is not the plain causal-LM one (Gemma 4: AutoModelForMultimodalLM,
    # text-only use through its tokenizer; ruling 2026-09-12). The tokenizer comes from AutoProcessor when AutoTokenizer cannot load it.
    cls_name = os.environ.get("SUITE_MODEL_CLASS", "AutoModelForCausalLM"); Loader = getattr(_tf, cls_name)
    tok, extra = load_tokenizer(tokenizer or model_name, trc), load_kwargs()
    if os.environ.get("SUITE_DEVICE_MAP") == "auto":
        # a model larger than the GPU (Sarvam-30B, 64 GB in bf16): bf16 weights kept, layers that do not fit are offloaded to CPU
        # RAM; numerics unchanged, only slower (2026-09-10)
        attn = os.environ.get("SUITE_ATTN")   # v3: the offload path honours the attention setting too (it recorded "-eager" without applying it)
        model = Loader.from_pretrained(model_name, dtype=torch.bfloat16, device_map="auto", max_memory={0: os.environ.get("SUITE_GPU_MEM", "42GiB"), "cpu": os.environ.get("SUITE_CPU_MEM", "30GiB")}, trust_remote_code=trc, **({"attn_implementation": attn} if attn else {}), **extra)
        model = model.eval(); _precision_note(model)
        if adapter:
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter)
        return model, tok
    attn = os.environ.get("SUITE_ATTN")   # e.g. "eager" for architectures whose sdpa path misbehaves with left padding (batch check diagnostics)
    model = Loader.from_pretrained(model_name, dtype=torch.bfloat16, trust_remote_code=trc, **({"attn_implementation": attn} if attn else {}), **extra)
    _precision_note(model)
    if embeddings:
        sd = torch.load(embeddings, weights_only=True)["embed_tokens"]
        model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
        with torch.no_grad():
            model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
    model = model.cuda().eval()
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    return model, tok

def run(stage, split, model_name, adapter=None, tokenizer=None, embeddings=None,
        tasks=None, cap=None, out=None, wrong_dir=None):
    """Score all registered tasks that have a split file. Writes results JSON."""
    model, tok = load_model(model_name, adapter, tokenizer, embeddings)
    commit = git_commit(); hv = harness_version(); gm = gen_mode()
    rows = []
    for task, (_, kind) in REGISTRY.items():
        if tasks and task not in tasks:
            continue
        sp = os.path.join(SPLITS, f"{task}.json")
        if not os.path.exists(sp):
            print(f"skip {task}: no split file"); continue
        try:
            items = {it["id"]: it for it in load_items(task)}
        except Exception as e:
            print(f"skip {task}: loader error {type(e).__name__}: {str(e)[:120]}"); continue
        ids = json.load(open(sp))[split]
        if cap:
            ids = ids[:cap]
        sel = [items[i] for i in ids if i in items]
        if not sel:
            print(f"skip {task}: no items"); continue
        t0 = time.time()
        metrics, recs = score_items(kind, sel, model, tok, task=task)
        for metric, score in metrics.items():
            rows.append({"benchmark": task, "split": split, "n": len(sel), "metric": metric,
                         "score": round(score, 4), "script": "eval/suite.py",
                         "commit": commit, "harness": hv, "gen_mode": gm, "gen_batch": gen_batch_size(), "timestamp": time.strftime("%FT%T"),
                         "stage": stage, "model": model_name, "adapter": adapter, "prompt_mode": "chat" if os.environ.get("SUITE_CHAT", "0") == "1" else "raw",
                         "rules": HARNESS_RULES, **({"gen_cap": GEN_CAPS[task]} if task in GEN_CAPS else {}), **({"degenerate": DEGENERATE[task]} if task in DEGENERATE else {}),
                         **({"degenerate_reviewed": reviewed(stage, split, task)} if task in DEGENERATE and reviewed(stage, split, task) else {})})
        print(f"{task:22s} {split} n={len(sel):4d} {metrics} ({time.time()-t0:.0f}s)", flush=True)
        if wrong_dir:
            os.makedirs(wrong_dir, exist_ok=True)
            with open(os.path.join(wrong_dir, f"{task}.jsonl"), "w") as f:
                for r in recs:
                    if not r.get("ok", True):
                        f.write(json.dumps({**r, "item": items[r["id"]]}, ensure_ascii=False) + "\n")
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        # merge with an existing results file (partial reruns replace only their rows)
        if os.path.exists(out):
            old = json.load(open(out))
            new_keys = {(r["benchmark"], r["split"], r["metric"]) for r in rows}
            rows = [r for r in old if (r["benchmark"], r["split"], r["metric"]) not in new_keys] + rows
        json.dump(rows, open(out, "w"), indent=1, ensure_ascii=False)
        print(f"wrote {out}")
    bad = {r["benchmark"]: r["degenerate"] for r in rows if r.get("degenerate") and not r.get("degenerate_reviewed")}
    if bad:
        raise SystemExit("DEGENERATE OUTPUT (rows written with a degenerate field; no table renders them until the output is fixed or a reviewed entry is added to eval/degenerate_reviewed.json): " + "; ".join(f"{k}: {v}" for k, v in sorted(bad.items())))
    return rows
