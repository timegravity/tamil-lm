"""Per-item predictions for the gate scorer (shuffled option-text identify_source), for auditing.
Usage: python eval/probe_items.py --adapter D --out logs/items_<tag>.json  (same loading as run_probe)
"""
import argparse, hashlib, json, os, sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
sys.path.insert(0, os.path.dirname(__file__))
from run_probe import shuffle_mcq, option_text_pred, PROBE_SHUFFLE_SEED

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen/Qwen3.5-2B-Base"); ap.add_argument("--adapter", required=True)
ap.add_argument("--tokenizer", default="ckpt/tokenizer_ext"); ap.add_argument("--out", required=True)
ap.add_argument("--types", default="identify_source")
a = ap.parse_args()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
tok = AutoTokenizer.from_pretrained(a.tokenizer)
model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16)
sd = torch.load(f"{a.adapter}/embeddings.pt", weights_only=True)["embed_tokens"]
model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
with torch.no_grad(): model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
model = model.cuda().eval()
from peft import PeftModel
model = PeftModel.from_pretrained(model, a.adapter)
items = [json.loads(l) for l in open("eval/literature_probe.jsonl")]
items = [i for i in items if i["type"] in a.types.split(",")]
preds = {}
for it in items:
    sp, sopts, sans = shuffle_mcq(it)
    p = option_text_pred(model, tok, sp, sopts)
    preds[it["id"]] = {"pred": p, "gold": sans, "ok": p == sans}
res = {"adapter": os.path.realpath(a.adapter), "adapter_sha256_16": sha(f"{a.adapter}/adapter_model.safetensors"),
       "embeddings_sha256_16": sha(f"{a.adapter}/embeddings.pt"), "shuffle_seed": PROBE_SHUFFLE_SEED,
       "n": len(preds), "acc": sum(v["ok"] for v in preds.values()) / len(preds), "items": preds}
json.dump(res, open(a.out, "w"), indent=1)
print(a.out, res["adapter"], res["adapter_sha256_16"], "acc", round(res["acc"], 4))
