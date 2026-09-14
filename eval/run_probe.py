"""Score a model on eval/literature_probe.jsonl.

Usage: python eval/run_probe.py --model Qwen/Qwen3.5-2B-Base [--out logs/probe_base.json]
       python eval/run_probe.py --model ckpt/cpt/step_5000 --adapter path/to/lora

MCQ items: loglik scoring of the letter continuation (A/B/C/D) after the prompt.
quote_kural: greedy generation, exact match on squashed text + chrF.
which_kural: greedy generation, first integer extracted, exact match.

The aggregate "probe_acc" is the mean of per-type accuracies (chrF reported
separately, not part of probe_acc). This is the project's primary gate metric.
"""
import argparse, json, re, unicodedata, os, sys, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite import raw_ids, PROMPT_RULE   # start-token rule bos-v1 (ruling 2026-09-13): the probe's raw prompts begin with the tokenizer's start token

def squash(s):
    return re.sub(r"[^஀-௿A-Za-z0-9]+", "", unicodedata.normalize("NFC", s))

def chrf(ref, hyp, n=6, beta=2.0):
    """Simple chrF on characters (whitespace stripped), mean over n-gram orders."""
    ref = re.sub(r"\s+", "", ref); hyp = re.sub(r"\s+", "", hyp)
    if not hyp or not ref:
        return 0.0
    scores = []
    for k in range(1, n + 1):
        rg = {}
        for i in range(len(ref) - k + 1):
            g = ref[i:i+k]; rg[g] = rg.get(g, 0) + 1
        hg = {}
        for i in range(len(hyp) - k + 1):
            g = hyp[i:i+k]; hg[g] = hg.get(g, 0) + 1
        if not rg or not hg:
            continue
        overlap = sum(min(rg.get(g, 0), c) for g, c in hg.items())
        p = overlap / max(1, sum(hg.values()))
        r = overlap / max(1, sum(rg.values()))
        if p + r > 0:
            scores.append((1 + beta**2) * p * r / (beta**2 * p + r))
        else:
            scores.append(0.0)
    return 100.0 * sum(scores) / len(scores) if scores else 0.0

PROBE_SHUFFLE_SEED = 20260828   # ruling 2026-08-28: MCQ options shuffled per item with this committed seed, both scorers

def shuffle_mcq(it):
    """Return (prompt, options, answer) with the option order shuffled deterministically per item.
    The prompt's option block (lines 'A. ...' .. 'D. ...') is rewritten in the new order."""
    import ast, random, re
    opts = it.get("options")
    opts = ast.literal_eval(opts) if isinstance(opts, str) else opts
    if not opts or len(opts) != 4:
        return it["prompt"], opts, it["answer"]
    letters = ["A", "B", "C", "D"]
    gold = opts[letters.index(it["answer"])]
    rng = random.Random(f"{PROBE_SHUFFLE_SEED}:{it['id']}")
    new = list(opts); rng.shuffle(new)
    lines = it["prompt"].split("\n")
    idx = [i for i, l in enumerate(lines) if re.match(r"^[ABCD]\. ", l)]
    if len(idx) != 4:
        return it["prompt"], opts, it["answer"]
    for i, L, o in zip(idx, letters, new):
        lines[i] = f"{L}. {o}"
    return "\n".join(lines), new, letters[new.index(gold)]

@torch.no_grad()
def letter_loglik(model, tok, prompt, letters=("A", "B", "C", "D")):
    ids = torch.tensor([raw_ids(tok, prompt)]).cuda()
    out = model(input_ids=ids)
    logits = out.logits[0, -1]
    best, best_lp = None, -1e30
    for L in letters:
        cand = tok(" " + L, add_special_tokens=False).input_ids or tok(L, add_special_tokens=False).input_ids
        lp = torch.log_softmax(logits, -1)[cand[0]].item()
        if lp > best_lp:
            best, best_lp = L, lp
    return best

@torch.no_grad()
def option_text_pred(model, tok, prompt, options, letters=("A", "B", "C", "D")):
    """Letter-format-free MCQ scoring: mean per-token log-likelihood of each option text after the prompt
    (diagnostic 2026-08-28 showed the letter scorer reads a letter prior on CPT checkpoints)."""
    import ast
    opts = ast.literal_eval(options) if isinstance(options, str) else options
    if not opts or len(opts) != len(letters):
        return None
    p = raw_ids(tok, prompt)
    best, best_s = None, -1e30
    for L, o in zip(letters, opts):
        oids = tok(" " + o, add_special_tokens=False).input_ids
        lp = torch.log_softmax(model(input_ids=torch.tensor([p + oids]).cuda()).logits[0].float(), -1)
        s = sum(lp[len(p) - 1 + i, oids[i]].item() for i in range(len(oids))) / len(oids)
        if s > best_s:
            best, best_s = L, s
    return best

@torch.no_grad()
def greedy(model, tok, prompt, max_new):
    ids = torch.tensor([raw_ids(tok, prompt)]).cuda()
    out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--tokenizer", default=None, help="extended tokenizer dir (tokenizer ext)")
    ap.add_argument("--embeddings", default=None, help="embeddings.pt (resized matrix) for tokenizer ext")
    ap.add_argument("--probe", default="eval/literature_probe.jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0, help="debug: only first N items")
    ap.add_argument("--types", default=None,
                    help="comma list of item types to score (loop uses meaning_mcq,identify_source for speed)")
    ap.add_argument("--manual-out", default=None,
                    help="write generations for manual_rubric items here (jsonl) for review")
    ap.add_argument("--manual-current", default=None,
                    help="current-affairs set (eval/current_affairs.jsonl) to add to --manual-out generations")
    args = ap.parse_args()
    HARNESS_AT_START = __import__("suite").harness_version()   # v3: the version of the code that runs, not of the files at the end

    trc = os.environ.get("SUITE_TRUST_REMOTE", "0") == "1"
    ATTN = {"attn_implementation": os.environ["SUITE_ATTN"]} if os.environ.get("SUITE_ATTN") else {}   # v3: the probe honours the attention setting
    import transformers as _tf
    Loader = getattr(_tf, os.environ.get("SUITE_MODEL_CLASS", "AutoModelForCausalLM"))
    from suite import load_tokenizer, load_kwargs
    tok = load_tokenizer(args.tokenizer or args.model, trc); ATTN = {**ATTN, **load_kwargs()}
    if os.environ.get("SUITE_DEVICE_MAP") == "auto":   # larger than the GPU: bf16 with CPU offload (see eval/suite.py)
        model = Loader.from_pretrained(args.model, dtype=torch.bfloat16, device_map="auto", max_memory={0: os.environ.get("SUITE_GPU_MEM", "42GiB"), "cpu": os.environ.get("SUITE_CPU_MEM", "30GiB")}, trust_remote_code=trc, **ATTN)
    else:
        model = Loader.from_pretrained(args.model, dtype=torch.bfloat16, trust_remote_code=trc, **ATTN)
    if args.embeddings:
        sd = torch.load(args.embeddings, weights_only=True)["embed_tokens"]
        model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
        with torch.no_grad():
            model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
    model = model.eval() if os.environ.get("SUITE_DEVICE_MAP") == "auto" else model.cuda().eval()
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)

    items = [json.loads(l) for l in open(args.probe)]
    from suite import gen_cap
    QUOTE_CAP = gen_cap(tok, 64, [it["answer"] for it in items if it.get("score") == "exact_and_chrf"])   # v3: 64 tokens could not hold a kural in Llama tokens (178 of 178)
    if args.types:
        keep = set(args.types.split(","))
        items = [it for it in items if it["type"] in keep]
    if args.limit:
        items = items[:args.limit]

    per_type = {}
    option_text = {}
    chrf_scores = []
    manual = []
    t0 = time.time()
    for i, it in enumerate(items):
        t = it["type"]
        ok = False
        if it["score"] == "manual_rubric":
            if args.manual_out:
                gen = greedy(model, tok, it["prompt"], 200)
                manual.append({"id": it["id"], "prompt": it["prompt"], "generation": gen,
                               "reference": it["reference"], "rubric_score": None})
            continue
        if it["score"] == "mcq_loglik":
            sp, sopts, sans = shuffle_mcq(it)
            pred = letter_loglik(model, tok, sp)
            if sopts:   # GATING scorer (ruling 2026-08-28): option-text likelihood on the shuffled options
                option_text.setdefault(t, []).append(option_text_pred(model, tok, sp, sopts) == sans)
            ok = pred == sans
        elif it["score"] == "exact_and_chrf":
            gen = greedy(model, tok, it["prompt"], QUOTE_CAP)
            gen_cut = gen.split("\n\n")[0]
            ok = squash(gen_cut) == it["answer_squashed"]
            chrf_scores.append(chrf(it["answer"], gen_cut))
        elif it["score"] == "exact_number":
            gen = greedy(model, tok, it["prompt"], 8)
            m = re.search(r"\d+", gen)
            ok = bool(m) and m.group(0) == it["answer"]
        per_type.setdefault(t, []).append(ok)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(items)} ({time.time()-t0:.0f}s)", flush=True)

    if args.manual_out and args.manual_current:
        for it in (json.loads(l) for l in open(args.manual_current)):
            gen = greedy(model, tok, it["question"], 160)
            manual.append({"id": it["id"], "prompt": it["question"], "generation": gen,
                           "reference": f"expected: {it['expected_behaviour']}; check {it['source_url']}",
                           "category": it["category"], "lang": it["lang"], "rubric_score": None})
    if args.manual_out and manual:
        with open(args.manual_out, "w") as f:
            for m in manual:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        print(f"wrote {len(manual)} manual-review generations -> {args.manual_out}")
    acc = {t: sum(v) / len(v) for t, v in per_type.items()}
    result = {
        "model": args.model, "adapter": args.adapter,
        "n_items": len(items),
        "per_type_acc": {t: round(a, 4) for t, a in acc.items()},
        "probe_acc": round(sum(acc.values()) / len(acc), 4),
        "quote_chrf": round(sum(chrf_scores) / len(chrf_scores), 2) if chrf_scores else None,
        "per_type_n": {t: len(v) for t, v in per_type.items()},
        "per_type_acc_option_text": {t: round(sum(v) / len(v), 4) for t, v in option_text.items()},
        "gate_identify_source_option_text": round(sum(option_text["identify_source"]) / len(option_text["identify_source"]), 4) if option_text.get("identify_source") else None,
        "shuffle_seed": PROBE_SHUFFLE_SEED,
        "harness": HARNESS_AT_START, "prompt_rule": PROMPT_RULE, "quote_cap": QUOTE_CAP,
        "letter_acc_choice_types": round(sum(acc[t] for t in ("identify_source", "meaning_mcq") if t in acc) / max(1, sum(1 for t in ("identify_source", "meaning_mcq") if t in acc)), 4),
        "time_s": round(time.time() - t0),
    }
    print(json.dumps(result, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(result, open(args.out, "w"), indent=2)

if __name__ == "__main__":
    main()
