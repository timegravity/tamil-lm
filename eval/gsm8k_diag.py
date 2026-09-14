"""Phase-4 ruling item 0: dump raw GSM8K generations from a checkpoint under the eval prompt
and classify them (correct_unparsed / partial_arithmetic / incoherent / correct_strict).
Usage: python eval/gsm8k_diag.py --adapter ckpt/cpt3/step_22431 [--n 20]
"""
import argparse, json, os, re, sys
import torch
sys.path.insert(0, os.path.dirname(__file__))
import suite
from transformers import AutoModelForCausalLM, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen/Qwen3.5-2B-Base"); ap.add_argument("--adapter", required=True)
ap.add_argument("--tokenizer", default="ckpt/tokenizer_ext"); ap.add_argument("--n", type=int, default=20)
ap.add_argument("--out", default="logs/gsm8k_diag.json")
ap.add_argument("--chat", action="store_true", help="wrap the eval prompt in the chat template with the SFT system prompt (instruct stage)")
a = ap.parse_args()
tok = AutoTokenizer.from_pretrained(a.tokenizer)
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16)
if os.path.exists(f"{a.adapter}/embeddings.pt"):
    sd = torch.load(f"{a.adapter}/embeddings.pt", weights_only=True)["embed_tokens"]
    model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
    with torch.no_grad(): model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
model = model.cuda().eval()
from peft import PeftModel
model = PeftModel.from_pretrained(model, a.adapter)
ids = set(json.load(open("eval/splits/gsm8k_en.json"))["dev"][: a.n])
import bench_loaders_knowledge as K
items = [i for i in K.load_gsm8k() if i["id"] in ids][: a.n]
T = suite.prompt_template("gsm8k")
TA = re.compile(r"[஀-௿]")
rows = []
for it in items:
    p = T.format(question=it["question"])
    if a.chat:
        SYS = "நீங்கள் தமிழ் மொழியில் உதவும் ஒரு உதவியாளர். துல்லியமாகவும் மரியாதையாகவும் பதிலளிக்கவும்."
        p = tok.apply_chat_template([{"role": "system", "content": SYS}, {"role": "user", "content": p}], tokenize=False, add_generation_prompt=True)
    with torch.no_grad():
        out = model.generate(tok(p, return_tensors="pt").input_ids.cuda(), max_new_tokens=256, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    g = tok.decode(out[0][len(tok(p).input_ids):], skip_special_tokens=True)
    nums = re.findall(r"-?\d[\d,]*\.?\d*", g)
    strict = bool(nums) and nums[-1].replace(",", "").rstrip(".") == it["answer_numeric"].replace(",", "")
    gold = it["answer_numeric"].replace(",", "")
    anywhere = any(n.replace(",", "").rstrip(".") == gold for n in nums)
    ta_ratio = len(TA.findall(g)) / max(1, len(g))
    ops = len(re.findall(r"\d\s*[-+*/x=]\s*\d", g))
    if strict: cls = "correct_strict"
    elif anywhere: cls = "correct_but_unparsed"
    elif ops >= 2 and nums: cls = "partial_arithmetic"
    else: cls = "incoherent"
    rows.append({"id": it["id"], "class": cls, "ta_ratio": round(ta_ratio, 2), "n_numbers": len(nums),
                 "gold": gold, "generation": g})
import collections
counts = dict(collections.Counter(r["class"] for r in rows))
json.dump({"adapter": a.adapter, "counts": counts, "rows": rows}, open(a.out, "w"), ensure_ascii=False, indent=1)
print("counts:", counts, "mean ta_ratio:", round(sum(r["ta_ratio"] for r in rows) / len(rows), 2))
for r in rows[:6]: print("--", r["class"], "gold", r["gold"], "| gen:", r["generation"][:150].replace("\n", " "))
