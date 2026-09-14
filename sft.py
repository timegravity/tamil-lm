"""Phase 5 SFT: fresh LoRA on the merged CPT model, Qwen chat template,
loss only on assistant tokens, 2 epochs, lr 5e-5. Resumable (same
checkpoint protocol as train.py). Produces ckpt/sft/step_N adapters; merge
with merge_final.py.

Data: data/sft/train.jsonl rows {"messages": [{"role","content"}, ...], "src": str}
(built by build_sft_data.py). Held-out: data/sft/dev.jsonl (2%).

Usage: python sft.py --base ckpt/final/tamil-lm-2b-base --run sft [--resume]
"""
import argparse, json, math, os, random, sys, time
import torch
import train as T

EPOCHS = 2
LR = 5e-5
MAX_LEN = 4096
MICRO = 2
ACCUM = 16

def encode(tok, messages, max_len):
    """Tokenise a chat; labels = -100 everywhere except assistant content."""
    ids, labels = [], []
    text_all = tok.apply_chat_template(messages, tokenize=False)
    # build incrementally so we know which spans are assistant turns
    prefix = ""
    first_user = next(i for i, m in enumerate(messages) if m["role"] == "user")
    for i, m in enumerate(messages):
        if i < first_user:
            continue   # the Qwen3.5 template refuses a system-only prefix; system text lands in the first user segment (masked)
        upto = tok.apply_chat_template(messages[:i+1], tokenize=False)
        seg = upto[len(prefix):]
        seg_ids = tok(seg, add_special_tokens=False).input_ids
        if m["role"] == "assistant":
            labels += seg_ids
        else:
            labels += [-100] * len(seg_ids)
        ids += seg_ids
        prefix = upto
    return ids[:max_len], labels[:max_len]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="merged CPT model dir (bf16)")
    ap.add_argument("--run", default="sft")
    ap.add_argument("--data", default="data/sft/train.jsonl")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--init-adapter", default=None, help="start from an existing SFT adapter dir (round-2 continuation on new data)")
    ap.add_argument("--epochs", type=float, default=EPOCHS)
    ap.add_argument("--lr", type=float, default=LR)
    args = ap.parse_args()

    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    tok = AutoTokenizer.from_pretrained(args.base)
    assert "<|im_end|>" in tok.get_vocab(), "chat template tokens missing; copy from data/sft/template"
    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16)
    model.gradient_checkpointing_enable(); model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=64, lora_alpha=128, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "in_proj_qkv", "in_proj_z",
                        "out_proj", "gate_proj", "up_proj", "down_proj"]))
    if args.init_adapter:
        from safetensors.torch import load_file
        from peft.utils import set_peft_model_state_dict
        set_peft_model_state_dict(model, load_file(f"{args.init_adapter}/adapter_model.safetensors"))
        print(f"initialised LoRA from {args.init_adapter}")
    model.print_trainable_parameters(); model = model.cuda()

    rows = [json.loads(l) for l in open(args.data)]
    random.Random(5).shuffle(rows)
    n_steps = int(len(rows) * args.epochs / (MICRO * ACCUM))
    from bitsandbytes.optim import AdamW8bit
    params = [p for p in model.parameters() if p.requires_grad]
    opt = AdamW8bit(params, lr=args.lr, betas=(0.9, 0.95), weight_decay=0.05)
    warm = max(10, int(0.03 * n_steps))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: s / warm if s < warm else
        0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1, (s - warm) / max(1, n_steps - warm)))))

    step, pos = 0, 0
    ck = T.latest_ckpt(args.run) if args.resume else None
    if ck:
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict
        set_peft_model_state_dict(model, load_file(f"{ck}/adapter_model.safetensors"))
        opt.load_state_dict(torch.load(f"{ck}/optimizer.pt", weights_only=False))
        sched.load_state_dict(torch.load(f"{ck}/scheduler.pt", weights_only=False))
        T.load_rng(torch.load(f"{ck}/rng.pt", weights_only=False))
        m = json.load(open(f"{ck}/meta.json")); step, pos = m["step"], m["data_pos"]
        print(f"resumed {ck}: step {step} pos {pos}")

    class Pos:   # dataloader position as a "reader" for save_ckpt
        def __init__(self): self.p = pos
        def state(self): return {"data_pos": self.p}
    P = Pos()
    def save():
        T.save_ckpt(args.run, step, step * MICRO * ACCUM, model, opt, sched, {"sft": P}, {"data_pos": P.p})

    t0, t_ck = time.time(), time.time()
    model.train()
    while step < n_steps:
        if any(os.path.exists(f) for f in ("STOP", "PAUSE")):
            save(); print("paused"); sys.exit(0)
        opt.zero_grad(set_to_none=True); tot = 0.0
        for _ in range(ACCUM):
            batch = [rows[(P.p + i) % len(rows)] for i in range(MICRO)]; P.p += MICRO
            enc = [encode(tok, r["messages"], MAX_LEN) for r in batch]
            L = max(len(e[0]) for e in enc)
            x = torch.full((MICRO, L), tok.pad_token_id or 0, dtype=torch.long)
            y = torch.full((MICRO, L), -100, dtype=torch.long)
            for i, (ids, lab) in enumerate(enc):
                x[i, :len(ids)] = torch.tensor(ids); y[i, :len(lab)] = torch.tensor(lab)
            loss = model(input_ids=x.cuda(), labels=y.cuda()).loss / ACCUM
            loss.backward(); tot += loss.item()
        torch.nn.utils.clip_grad_norm_(params, 1.0); opt.step(); sched.step(); step += 1
        if step % 10 == 0:
            print(f"step {step}/{n_steps} loss {tot:.4f} lr {sched.get_last_lr()[0]:.2e} {time.time()-t0:.0f}s", flush=True)
            T.log(args.run, {"event": "train", "step": step, "loss": tot, "lr": sched.get_last_lr()[0], "time": time.time()})
        if time.time() - t_ck > T.CKPT_EVERY_S:
            save(); t_ck = time.time()
    save(); print("SFT done")

if __name__ == "__main__":
    main()
