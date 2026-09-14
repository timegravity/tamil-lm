"""Diagnostic for the MCQ probe types: is the letter-loglik scorer measuring the model
or a constant letter prior? Reports, per type: accuracy of (a) the production scorer
(raw letter loglik), (b) calibrated letter loglik (minus the letter loglik after a
neutral prompt), (c) option-text scoring (mean per-token loglik of the option text),
plus the predicted-letter distribution for (a). Same model flags as run_probe.py.
Usage: python eval/probe_diag.py --model Qwen/Qwen3.5-2B-Base [--adapter D --tokenizer T --embeddings E] --tag name
"""
import argparse, ast, collections, json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

LETTERS = ("A", "B", "C", "D")

@torch.no_grad()
def letter_lps(model, tok, prompt):
    ids = tok(prompt, return_tensors="pt").input_ids.cuda()
    lp = torch.log_softmax(model(input_ids=ids).logits[0, -1].float(), -1)
    out = []
    for L in LETTERS:
        cand = tok(" " + L, add_special_tokens=False).input_ids or tok(L, add_special_tokens=False).input_ids
        out.append(lp[cand[0]].item())
    return out

@torch.no_grad()
def option_lp(model, tok, prompt, option):
    p = tok(prompt, add_special_tokens=False).input_ids
    o = tok(" " + option, add_special_tokens=False).input_ids
    ids = torch.tensor([p + o]).cuda()
    lp = torch.log_softmax(model(input_ids=ids).logits[0].float(), -1)
    tot = sum(lp[len(p) - 1 + i, o[i]].item() for i in range(len(o)))
    return tot / len(o)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--adapter"); ap.add_argument("--tokenizer"); ap.add_argument("--embeddings")
    ap.add_argument("--probe", default="eval/literature_probe.jsonl"); ap.add_argument("--tag", required=True)
    ap.add_argument("--types", default="identify_source,meaning_mcq")
    a = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(a.tokenizer or a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16)
    if a.embeddings:
        sd = torch.load(a.embeddings, weights_only=True)["embed_tokens"]
        model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
        with torch.no_grad(): model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
    model = model.cuda().eval()
    if a.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    items = [json.loads(l) for l in open(a.probe) if json.loads(l)["type"] in a.types.split(",")]
    neutral = letter_lps(model, tok, "விடை:")
    res = {}
    for t in a.types.split(","):
        its = [i for i in items if i["type"] == t]
        acc = collections.Counter(); dist = collections.Counter()
        for it in its:
            lps = letter_lps(model, tok, it["prompt"])
            raw = LETTERS[max(range(4), key=lambda i: lps[i])]
            cal = LETTERS[max(range(4), key=lambda i: lps[i] - neutral[i])]
            opts = it.get("options"); opts = ast.literal_eval(opts) if isinstance(opts, str) else opts
            txt = None
            if opts and len(opts) == 4:
                sc = [option_lp(model, tok, it["prompt"], o) for o in opts]
                txt = LETTERS[max(range(4), key=lambda i: sc[i])]
            dist[raw] += 1
            acc["raw"] += raw == it["answer"]; acc["calibrated"] += cal == it["answer"]; acc["option_text"] += (txt == it["answer"]) if txt else 0
        n = len(its)
        res[t] = {"n": n, "raw": acc["raw"] / n, "calibrated": acc["calibrated"] / n, "option_text": acc["option_text"] / n,
                  "raw_letter_dist": dict(dist), "gold_dist": dict(collections.Counter(i["answer"] for i in its))}
        print(a.tag, t, json.dumps(res[t], ensure_ascii=False))
    json.dump(res, open(f"logs/probe_diag_{a.tag}.json", "w"), indent=1, ensure_ascii=False)

if __name__ == "__main__":
    main()
