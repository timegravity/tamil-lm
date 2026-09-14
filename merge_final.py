"""Merge a LoRA adapter (+ extended embeddings) into bf16 weights and save a
standalone model directory with the extended tokenizer.

Usage:
  python merge_final.py --adapter ckpt/cpt/step_N --out ckpt/final/tamil-lm-2b-base
  python merge_final.py --base ckpt/final/tamil-lm-2b-base --adapter ckpt/sft/step_N \
      --out ckpt/final/tamil-lm-2b-instruct --chat-template data/sft/template

For the CPT merge the base is Qwen/Qwen3.5-2B-Base resized to the extended vocab
with the checkpoint's embeddings.pt. For the SFT merge the base is the merged
CPT model. --chat-template copies tokenizer_config.json and chat_template.jinja
from Qwen/Qwen3.5-2B (template only) into the output.
"""
import argparse, json, os, shutil
import torch

def add_mtp_tensors(out_dir, base_repo="Qwen/Qwen3.5-2B-Base"):
    """llama.cpp's qwen35 converter requires the MTP head tensors. The text-only
    model never loads them, so copy the base checkpoint's 15 mtp.* tensors
    (unchanged, unused at inference) into an extra shard and write an index."""
    import glob
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from safetensors.torch import save_file
    idx = json.load(open(hf_hub_download(base_repo, "model.safetensors.index.json")))["weight_map"]
    mtp_keys = [k for k in idx if k.startswith("mtp.")]
    if not mtp_keys:
        return
    files = sorted(set(idx[k] for k in mtp_keys))
    tensors = {}
    for f in files:
        with safe_open(hf_hub_download(base_repo, f), framework="pt") as sf:
            for k in mtp_keys:
                if idx[k] == f:
                    tensors[k] = sf.get_tensor(k)
    save_file(tensors, os.path.join(out_dir, "model-mtp.safetensors"), metadata={"format": "pt"})
    weight_map = {}
    for f in sorted(glob.glob(os.path.join(out_dir, "model*.safetensors"))):
        with safe_open(f, framework="pt") as sf:
            for k in sf.keys():
                weight_map[k] = os.path.basename(f)
    json.dump({"metadata": {}, "weight_map": weight_map},
              open(os.path.join(out_dir, "model.safetensors.index.json"), "w"), indent=1)
    print(f"added {len(tensors)} MTP tensors from {base_repo}; index has {len(weight_map)} tensors")

def write_upstream_layout(src_dir, out_dir, base_repo="Qwen/Qwen3.5-2B"):   # the full VL repo: vision tower + ConditionalGeneration config live here, not in -Base
    """Re-express the merged text-only model in the upstream layout that vLLM
    expects: Qwen3_5ForConditionalGeneration config, text weights under
    model.language_model.*, plus the base model's vision tower and MTP tensors
    copied unchanged (they are never trained; text-only project)."""
    import glob
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from safetensors.torch import save_file
    os.makedirs(out_dir, exist_ok=True)
    # 1. text weights renamed
    tensors = {}
    for f in sorted(glob.glob(os.path.join(src_dir, "model*.safetensors"))):
        with safe_open(f, framework="pt") as sf:
            for k in sf.keys():
                if k.startswith("mtp."):
                    continue
                if k.startswith("model.language_model.") or not k.startswith("model."):
                    nk = k                      # already in upstream naming (transformers 5)
                else:
                    nk = "model.language_model." + k[len("model."):]
                tensors[nk] = sf.get_tensor(k)
    save_file(tensors, os.path.join(out_dir, "model-text.safetensors"), metadata={"format": "pt"})
    # 2. vision + mtp tensors from the base checkpoint
    idx = json.load(open(hf_hub_download(base_repo, "model.safetensors.index.json")))["weight_map"]
    keep = [k for k in idx if k.startswith("model.visual.") or k.startswith("mtp.")]
    extra = {}
    for f in sorted(set(idx[k] for k in keep)):
        with safe_open(hf_hub_download(base_repo, f), framework="pt") as sf:
            for k in keep:
                if idx[k] == f:
                    extra[k] = sf.get_tensor(k)
    save_file(extra, os.path.join(out_dir, "model-vision-mtp.safetensors"), metadata={"format": "pt"})
    wm = {k: "model-text.safetensors" for k in tensors}
    wm.update({k: "model-vision-mtp.safetensors" for k in extra})
    json.dump({"metadata": {}, "weight_map": wm}, open(os.path.join(out_dir, "model.safetensors.index.json"), "w"), indent=1)
    # 3. config: base (ConditionalGeneration) with the text vocab updated
    cfg = json.load(open(hf_hub_download(base_repo, "config.json")))
    tcfg = json.load(open(os.path.join(src_dir, "config.json")))
    cfg["text_config"]["vocab_size"] = tcfg["vocab_size"]
    json.dump(cfg, open(os.path.join(out_dir, "config.json"), "w"), indent=2)
    # 4. tokenizer (extended) + preprocessor configs from the base
    for f in glob.glob(os.path.join(src_dir, "tokenizer*")) + glob.glob(os.path.join(src_dir, "*.jinja")) + \
             glob.glob(os.path.join(src_dir, "vocab.json")) + glob.glob(os.path.join(src_dir, "merges.txt")) + \
             glob.glob(os.path.join(src_dir, "special_tokens_map.json")) + glob.glob(os.path.join(src_dir, "generation_config.json")):
        shutil.copy(f, out_dir)
    for f in ("preprocessor_config.json", "video_preprocessor_config.json"):
        try:
            shutil.copy(hf_hub_download(base_repo, f), out_dir)
        except Exception:
            pass
    print(f"upstream layout written: {out_dir} ({len(tensors)} text + {len(extra)} vision/mtp tensors)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3.5-2B-Base")
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tokenizer", default="ckpt/tokenizer_ext")
    ap.add_argument("--chat-template", default=None)
    ap.add_argument("--upstream-layout", action="store_true",
                    help="also write <out>-vl in the upstream Qwen3_5ForConditionalGeneration layout (vLLM)")
    a = ap.parse_args()

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    tok = AutoTokenizer.from_pretrained(a.tokenizer if a.base.startswith("Qwen/") else a.base)
    model = AutoModelForCausalLM.from_pretrained(a.base, dtype=torch.bfloat16)
    emb_path = os.path.join(a.adapter, "embeddings.pt")
    if os.path.exists(emb_path):
        sd = torch.load(emb_path, weights_only=True)["embed_tokens"]
        if model.get_input_embeddings().weight.shape[0] != sd.shape[0]:
            model.resize_token_embeddings(sd.shape[0], mean_resizing=False)
        with torch.no_grad():
            model.get_input_embeddings().weight.copy_(sd.to(torch.bfloat16))
        print(f"embeddings loaded: {tuple(sd.shape)}")
    model = PeftModel.from_pretrained(model, a.adapter)
    model = model.merge_and_unload()
    os.makedirs(a.out, exist_ok=True)
    model.save_pretrained(a.out, safe_serialization=True)
    tok.save_pretrained(a.out)
    add_mtp_tensors(a.out)
    if a.chat_template:
        for f in ("tokenizer_config.json", "chat_template.jinja"):
            src = os.path.join(a.chat_template, f)
            if os.path.exists(src):
                if f == "tokenizer_config.json":
                    # keep our (extended) tokenizer files; only import the chat_template field
                    cfg = json.load(open(os.path.join(a.out, f)))
                    cfg["chat_template"] = json.load(open(src)).get("chat_template", cfg.get("chat_template"))
                    json.dump(cfg, open(os.path.join(a.out, f), "w"), indent=2, ensure_ascii=False)
                else:
                    shutil.copy(src, os.path.join(a.out, f))
        print("chat template applied from", a.chat_template)
    if a.chat_template:   # instruct export: chat turns end at <|im_end|>; make it an EOS for loaders that ignore the template
        for d in (a.out,):
            gp = os.path.join(d, "generation_config.json"); g = json.load(open(gp)) if os.path.exists(gp) else {}
            im_end = tok.convert_tokens_to_ids("<|im_end|>")
            g.update({"eos_token_id": [im_end, tok.eos_token_id], "pad_token_id": tok.eos_token_id}); json.dump(g, open(gp, "w"), indent=2)
            tp = os.path.join(d, "tokenizer_config.json"); tc = json.load(open(tp)); tc["eos_token"] = "<|im_end|>"; json.dump(tc, open(tp, "w"), indent=2, ensure_ascii=False)
    if a.upstream_layout:
        write_upstream_layout(a.out, a.out + "-vl")
    meta = {"base": a.base, "adapter": a.adapter, "tokenizer": a.tokenizer,
            "vocab_size": model.get_input_embeddings().weight.shape[0]}
    json.dump(meta, open(os.path.join(a.out, "merge_meta.json"), "w"), indent=2)
    print("saved", a.out, meta)

if __name__ == "__main__":
    main()
