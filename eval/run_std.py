"""Standard benchmark suite for tamil-lm. Custom loaders (lm-eval lacks these
tasks for Tamil): FLORES-200 eng<->tam chrF, IndicXNLI ta, IndicSentiment ta,
MILU Tamil. Each task subsampled to --n items (fixed seed) for runtime; the
subsample is deterministic so deltas across checkpoints are comparable.

Usage: python eval/run_std.py --model Qwen/Qwen3.5-2B-Base --out logs/std_base.json
"""
import argparse, json, os, random, re, sys, time, unicodedata
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.dirname(__file__))
from run_probe import chrf   # reuse chrF implementation

@torch.no_grad()
def option_loglik(model, tok, prompt, options):
    """Return index of option with highest mean logprob continuation."""
    best, best_lp = 0, -1e30
    for i, opt in enumerate(options):
        full = prompt + opt
        ids = tok(full, return_tensors="pt").input_ids.cuda()
        plen = len(tok(prompt).input_ids)
        out = model(input_ids=ids)
        lp = torch.log_softmax(out.logits[0, plen-1:-1], -1)
        tgt = ids[0, plen:]
        score = lp.gather(1, tgt.unsqueeze(1)).mean().item()
        if score > best_lp:
            best, best_lp = i, score
    return best

@torch.no_grad()
def greedy(model, tok, prompt, max_new=128):
    ids = tok(prompt, return_tensors="pt").input_ids.cuda()
    out = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                         pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)

def eval_flores(model, tok, n):
    from datasets import load_dataset
    res = {}
    # gsarti/flores_101 parquet mirror (ungated); devtest sentences are identical
    # to FLORES-200 devtest for eng/tam
    en_ds = load_dataset("parquet", data_files=
        "hf://datasets/gsarti/flores_101@refs%2Fconvert%2Fparquet/eng/devtest/0000.parquet",
        split="train")
    ta_ds = load_dataset("parquet", data_files=
        "hf://datasets/gsarti/flores_101@refs%2Fconvert%2Fparquet/tam/devtest/0000.parquet",
        split="train")
    ta_by_id = {r["id"]: r["sentence"] for r in ta_ds}
    rows = [{"sentence_eng_Latn": r["sentence"], "sentence_tam_Taml": ta_by_id[r["id"]]}
            for r in en_ds if r["id"] in ta_by_id][:n]
    for direction in ["en-ta", "ta-en"]:
        scores = []
        for r in rows:
            en = r.get("sentence_eng_Latn")
            ta = r.get("sentence_tam_Taml")
            if direction == "en-ta":
                p = f"English: {en}\nTamil:"
                ref = ta
            else:
                p = f"Tamil: {ta}\nEnglish:"
                ref = en
            gen = greedy(model, tok, p).split("\n")[0].strip()
            scores.append(chrf(ref, gen))
        res[f"flores_chrf_{direction}"] = round(sum(scores) / len(scores), 2)
    return res

def eval_indicxnli(model, tok, n):
    from datasets import load_dataset
    ds = load_dataset("parquet", data_files=
        "hf://datasets/Divyanshu/indicxnli@refs%2Fconvert%2Fparquet/ta/validation/0000.parquet",
        split="train")
    rows = list(ds)
    random.Random(7).shuffle(rows)
    rows = rows[:n]
    labels = ["ஆம்", "ஒருவேளை", "இல்லை"]   # entail / neutral / contradict
    correct = 0
    for r in rows:
        p = (f"முன்னுரை: {r['premise']}\nகருதுகோள்: {r['hypothesis']}\n"
             f"முன்னுரையிலிருந்து கருதுகோள் பின்பற்றுகிறதா? பதில்:")
        pred = option_loglik(model, tok, p, [" " + l for l in labels])
        correct += pred == r["label"]
    return {"indicxnli_ta_acc": round(correct / len(rows), 4), "indicxnli_n": len(rows)}

def eval_indicsentiment(model, tok, n):
    from datasets import load_dataset
    ds = load_dataset("parquet", data_files=
        "hf://datasets/ai4bharat/IndicSentiment@refs%2Fconvert%2Fparquet/translation-ta/validation/0000.parquet",
        split="train")
    rows = [r for r in ds if r.get("LABEL")][:n]
    correct = 0
    for r in rows:
        sent = r.get("INDIC REVIEW") or r.get("REVIEW")
        p = f"விமர்சனம்: {sent}\nஇந்த விமர்சனம் நேர்மறையா எதிர்மறையா? பதில்:"
        pred = option_loglik(model, tok, p, [" நேர்மறை", " எதிர்மறை"])
        gold = 0 if str(r["LABEL"]).lower().startswith("pos") else 1
        correct += pred == gold
    return {"indicsentiment_ta_acc": round(correct / max(1, len(rows)), 4),
            "indicsentiment_n": len(rows)}

def eval_milu(model, tok, n):
    from datasets import load_dataset
    try:
        ds = load_dataset("ai4bharat/MILU", "Tamil", split="test")
    except Exception as e:
        return {"milu_ta_error": str(e)[:200]}
    rows = list(ds)
    random.Random(7).shuffle(rows)
    rows = rows[:n]
    correct = 0
    for r in rows:
        opts = [r["option1"], r["option2"], r["option3"], r["option4"]]
        p = f"{r['question']}\n" + "\n".join(
            f"{c}. {o}" for c, o in zip("ABCD", opts)) + "\nவிடை:"
        pred = option_loglik(model, tok, p, [" A", " B", " C", " D"])
        gold = {"option1": 0, "option2": 1, "option3": 2, "option4": 3}.get(
            str(r["target"]), None)
        if gold is None:
            gold = opts.index(r["target"]) if r["target"] in opts else -1
        correct += pred == gold
    return {"milu_ta_acc": round(correct / max(1, len(rows)), 4), "milu_n": len(rows)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--tasks", default="flores,indicxnli,indicsentiment,milu")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).cuda().eval()
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)

    results = {"model": args.model, "adapter": args.adapter, "n_per_task": args.n}
    for t in args.tasks.split(","):
        t0 = time.time()
        try:
            fn = {"flores": eval_flores, "indicxnli": eval_indicxnli,
                  "indicsentiment": eval_indicsentiment, "milu": eval_milu}[t]
            results.update(fn(model, tok, args.n))
        except Exception as e:
            results[f"{t}_error"] = f"{type(e).__name__}: {e}"[:300]
        results[f"{t}_time_s"] = round(time.time() - t0)
        print(t, "done:", {k: v for k, v in results.items() if k.startswith(t)}, flush=True)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    if args.out:
        json.dump(results, open(args.out, "w"), indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
