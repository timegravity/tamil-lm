"""The ONE mutable file during autoresearch. Baseline reference recipe.

Recipe (baseline commit):
  LoRA r128 on attention (q,k,v,o) + DeltaNet (in_proj_qkv, in_proj_z, out_proj),
  r256 on MLP (gate,up,down). Embeddings and lm_head frozen. 8-bit AdamW,
  lr 2e-4 cosine to 10% floor, warmup 3%. seq 4096, micro-batch 4, grad accum
  to 65536 tokens/step. Grad checkpointing on. torch.compile on. MTP off. bf16.

Power-cut-safe checkpointing:
  saves model/LoRA + optimizer + scheduler + RNG states + step + tokens seen +
  dataloader position (per-bucket shard index and offset). Atomic:
  tmp_step_N -> fsync -> rename. Verified after rename. Resume continues from
  the exact next token.

Usage:
  python train.py --run exp001 --minutes 15 [--resume] [--data data/shards/auto100m]
"""
import argparse, glob, json, math, os, random, shutil, time, sys

import numpy as np
import torch

SEQ = 4096
MICRO_BSZ = 1                # 4 OOMs at 248K vocab (8GB logits per micro-batch); accum keeps 64K tok/step
STEP_TOKENS = 65536          # tokens per optimizer step (grad accum)
LR = 2e-4
WARMUP_FRAC = 0.03
COSINE_FLOOR = 0.1
CKPT_EVERY_S = int(os.environ.get("CKPT_EVERY_S", 20 * 60))   # time-based, power-cut cost <= 20 min; env override for tests
KEEP_LAST = 3
KEEP_EVERY = 5000

# Kept autoresearch changes become defaults here (one mutable file).
# exp001 (2026-08-25): tokenizer extension kept provisionally.
KEPT = {
    "lora_r": 256, "lora_mlp_r": 512,    # exp005 kept under the literature-first rule (b)
    "data": "data/shards/auto100m_ext_lit15rep05xqa50",   # exp021 composed data mix (confirmed)
    "tokenizer": "ckpt/tokenizer_ext",
    "init_embeddings": "ckpt/exp1_stageA/step_3053/embeddings.pt",
}

def log(run, obj):
    os.makedirs("logs", exist_ok=True)
    with open(f"logs/{run}.jsonl", "a") as f:
        f.write(json.dumps(obj) + "\n")

class ShardReader:
    """Sequential reader over uint32 shards of one bucket, with exact position."""
    def __init__(self, dirpath, bucket, val=False):
        prefix = f"val_{bucket}" if val else bucket
        self.files = sorted(glob.glob(f"{dirpath}/{prefix}_[0-9]*.bin"))
        assert self.files, f"no shards for {prefix} in {dirpath}"
        self.shard_i = 0
        self.offset = 0            # token offset within shard
        self._arr = None
        self._loaded = -1

    def _load(self):
        if self._loaded != self.shard_i:
            self._arr = np.memmap(self.files[self.shard_i], dtype=np.uint32, mode="r")
            self._loaded = self.shard_i

    def next_block(self, n):
        """Return n+ tokens (crossing shards, wrapping at end of data)."""
        out = []
        while n > 0:
            self._load()
            avail = len(self._arr) - self.offset
            if avail <= 0:
                self.shard_i = (self.shard_i + 1) % len(self.files)
                self.offset = 0
                continue
            take = min(n, avail)
            out.append(np.asarray(self._arr[self.offset:self.offset + take]))
            self.offset += take
            n -= take
        return np.concatenate(out)

    def state(self):
        return {"shard_i": self.shard_i, "offset": self.offset}

    def load_state(self, s):
        self.shard_i, self.offset = s["shard_i"], s["offset"]

def extend_embeddings(model, tokenizer_dir):
    """Tokenizer extension (experiment 1): resize embeddings, initialise each
    new row as the mean of its old-tokenizer subword rows, and return a grad
    mask that keeps only the new rows trainable (lm_head is tied, so the same
    rows serve output)."""
    info = json.load(open(f"{tokenizer_dir}/init_map.json"))
    base, new_size = info["base_vocab_size"], info["new_vocab_size"]
    model.resize_token_embeddings(new_size, mean_resizing=False)
    emb = model.get_input_embeddings().weight
    with torch.no_grad():
        for i, tok_str in enumerate(info["new_tokens"]):
            old_ids = info["init_map"][tok_str]
            emb[base + i] = emb[old_ids].mean(0)
    mask = torch.zeros(new_size, 1, dtype=emb.dtype, device=emb.device)
    mask[base:] = 1.0
    emb.requires_grad_(True)
    global _EMB_MASK_HANDLE
    _EMB_MASK_HANDLE = emb.register_hook(lambda g: g * mask.to(g.device))
    print(f"tokenizer extension: {new_size - base} new rows trainable, {base} frozen")
    return emb

_EMB_MASK_HANDLE = None

def build_model(tokenizer_dir=None, stage_a=False, init_embeddings=None,
                lora_r=128, lora_mlp_r=256, full_mlp=False, unfreeze_embeddings=False,
                init_adapter=None):
    from transformers import AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model
    model = AutoModelForCausalLM.from_pretrained(
        "Qwen/Qwen3.5-2B-Base", dtype=torch.bfloat16)
    model.gradient_checkpointing_enable()
    model.config.use_cache = False
    new_rows_param = None
    if tokenizer_dir:
        new_rows_param = extend_embeddings(model, tokenizer_dir)
        if init_embeddings:
            # load Stage A-trained embedding matrix (all rows; frozen rows are
            # bit-identical to the original since their grads were masked)
            sd = torch.load(init_embeddings, weights_only=True)
            with torch.no_grad():
                new_rows_param.copy_(sd["embed_tokens"].to(new_rows_param.dtype))
            print(f"loaded Stage A embeddings from {init_embeddings}")
    if stage_a:
        # Stage A: ONLY the new embedding rows train, no LoRA
        for n, p in model.named_parameters():
            p.requires_grad_(p is new_rows_param)
        model.enable_input_require_grads()
        return model.cuda(), new_rows_param
    targets = ["q_proj", "k_proj", "v_proj", "o_proj", "in_proj_qkv", "in_proj_z", "out_proj"]
    if not full_mlp:
        targets += ["gate_proj", "up_proj", "down_proj"]
    lcfg = LoraConfig(
        r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.0, bias="none",
        target_modules=targets,
        rank_pattern={".*mlp\\.(gate|up|down)_proj": lora_mlp_r},
        alpha_pattern={".*mlp\\.(gate|up|down)_proj": 2 * lora_mlp_r},
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lcfg)
    if init_adapter:
        # continuation run (Phase 4 interventions): start from a trained adapter
        from safetensors.torch import load_file
        from peft.utils import set_peft_model_state_dict
        sd_a = load_file(f"{init_adapter}/adapter_model.safetensors")
        res = set_peft_model_state_dict(model, sd_a)
        missing = [k for k in getattr(res, "unexpected_keys", [])]
        print(f"loaded adapter weights from {init_adapter} (unexpected: {len(missing)})")
    if full_mlp:   # experiment: full fine-tune of MLP weights (no LoRA on them)
        for n, p in model.named_parameters():
            if ".mlp." in n and "lora" not in n:
                p.requires_grad_(True)
    if unfreeze_embeddings:   # experiment: train ALL embedding rows (tied lm_head)
        if _EMB_MASK_HANDLE is not None:
            _EMB_MASK_HANDLE.remove()   # drop the new-rows-only gradient mask
        model.get_input_embeddings().weight.requires_grad_(True)
        print("unfreeze-embeddings: all rows trainable (mask removed)")
    if new_rows_param is not None:
        new_rows_param.requires_grad_(True)   # peft froze it; re-enable (masked to new rows)
    model.print_trainable_parameters()
    return model.cuda(), new_rows_param

def fused_ce_loss(model, input_ids, labels):
    """Liger fused linear cross-entropy over the tied lm_head: hidden states -> loss
    without materialising the [tokens x vocab] logits. Ignores label -100."""
    from liger_kernel.transformers import LigerFusedLinearCrossEntropyLoss
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    out = base.model(input_ids=input_ids)
    h = (out.last_hidden_state if hasattr(out, "last_hidden_state") else out[0])[:, :-1, :]
    h = h.reshape(-1, h.shape[-1])
    y = labels[:, 1:].reshape(-1)
    return LigerFusedLinearCrossEntropyLoss(ignore_index=-100)(base.lm_head.weight, h, y)

def rng_state():
    return {"py": random.getstate(), "np": np.random.get_state(),
            "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}

def load_rng(s):
    random.setstate(s["py"]); np.random.set_state(s["np"])
    torch.set_rng_state(s["torch"]); torch.cuda.set_rng_state_all(s["cuda"])

def save_ckpt(run, step, tokens_seen, model, opt, sched, readers, extra=None):
    base = f"ckpt/{run}"
    os.makedirs(base, exist_ok=True)
    tmp = f"{base}/tmp_step_{step}"
    final = f"{base}/step_{step}"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    if hasattr(model, "peft_config"):
        model.save_pretrained(tmp)                   # LoRA adapter only
        emb = model.get_input_embeddings().weight
        if emb.requires_grad:                        # tokenizer ext: new rows train too
            torch.save({"embed_tokens": emb.detach().cpu()}, f"{tmp}/embeddings.pt")
    else:
        torch.save({"embed_tokens": model.get_input_embeddings().weight.detach().cpu()},
                   f"{tmp}/embeddings.pt")           # Stage A: embeddings only
    torch.save(opt.state_dict(), f"{tmp}/optimizer.pt")
    torch.save(sched.state_dict(), f"{tmp}/scheduler.pt")
    torch.save(rng_state(), f"{tmp}/rng.pt")
    meta = {"step": step, "tokens_seen": tokens_seen,
            "readers": {b: r.state() for b, r in readers.items()},
            "time": time.time(), **(extra or {})}
    with open(f"{tmp}/meta.json", "w") as f:
        json.dump(meta, f)
        f.flush(); os.fsync(f.fileno())
    fd = os.open(tmp, os.O_RDONLY)
    os.fsync(fd); os.close(fd)
    if os.path.exists(final):
        shutil.rmtree(final)
    os.rename(tmp, final)
    # verify
    try:
        m2 = json.load(open(f"{final}/meta.json"))
        assert m2["step"] == step
    except Exception as e:
        print(f"CHECKPOINT VERIFY FAILED at step {step}: {e}; marking bad")
        os.rename(final, final + ".bad")
        return None
    # retention: last KEEP_LAST plus every KEEP_EVERY
    steps = sorted(int(d.split("_")[1]) for d in os.listdir(base)
                   if d.startswith("step_") and not d.endswith(".bad"))
    for s in steps[:-KEEP_LAST]:
        if s % KEEP_EVERY != 0:
            shutil.rmtree(f"{base}/step_{s}", ignore_errors=True)
    return final

def latest_ckpt(run):
    base = f"ckpt/{run}"
    if not os.path.isdir(base):
        return None
    for d in os.listdir(base):                       # clean stale tmp dirs
        if d.startswith("tmp_"):
            shutil.rmtree(f"{base}/{d}", ignore_errors=True)
    steps = sorted(int(d.split("_")[1]) for d in os.listdir(base)
                   if d.startswith("step_") and not d.endswith(".bad"))
    return f"{base}/step_{steps[-1]}" if steps else None

@torch.no_grad()
def eval_bpc(model, data_dir, meta, max_tokens_per_bucket=500_000):
    model.eval()
    out = {}
    for bucket, info in meta["buckets"].items():
        if info["val_tokens"] == 0:
            continue
        r = ShardReader(data_dir, bucket, val=True)
        want = min(info["val_tokens"], max_tokens_per_bucket)
        nll = 0.0; ntok = 0
        while ntok < want:
            block = r.next_block(SEQ * MICRO_BSZ)
            x = torch.from_numpy(block.astype(np.int64)).view(MICRO_BSZ, SEQ).cuda()
            loss = model(input_ids=x, labels=x).loss
            nll += loss.item() * (SEQ - 1) * MICRO_BSZ
            ntok += SEQ * MICRO_BSZ
        # bpc: nats per token converted to bits per CHARACTER using the char
        # count recorded at shard time. Comparable across tokenizers (Vignesh
        # 2026-08-25). bpb kept for reference.
        chars_per_token = info["val_chars"] / info["val_tokens"]
        bytes_per_token = info["val_bytes"] / info["val_tokens"]
        nats = nll / ntok
        out[bucket] = round(nats / chars_per_token / math.log(2), 4)
        out[bucket + "_bpb"] = round(nats / bytes_per_token / math.log(2), 4)
    model.train()
    buckets = [b for b in out if not b.endswith("_bpb")]
    w = {b: meta["buckets"][b]["val_chars"] for b in buckets}
    out["total"] = round(sum(out[b] * w[b] for b in buckets) / sum(w.values()), 4)
    return out

def main():
    global SEQ, WARMUP_FRAC, COSINE_FLOOR
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--minutes", type=float, default=15.0)
    ap.add_argument("--data", default=KEPT["data"])
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--tokenizer", default=KEPT["tokenizer"],
                    help="ckpt/tokenizer_ext: enable tokenizer extension (experiment 1)")
    ap.add_argument("--stage-a", action="store_true",
                    help="tokenizer ext Stage A: only new embedding rows train, no LoRA")
    ap.add_argument("--init-embeddings", default=KEPT["init_embeddings"],
                    help="embeddings.pt from a Stage A checkpoint (tokenizer extension)")
    ap.add_argument("--lora-r", type=int, default=KEPT["lora_r"])
    ap.add_argument("--lora-mlp-r", type=int, default=KEPT["lora_mlp_r"])
    ap.add_argument("--full-mlp", action="store_true", help="full FT of MLP instead of LoRA")
    ap.add_argument("--unfreeze-embeddings", action="store_true")
    ap.add_argument("--seq", type=int, default=SEQ)
    ap.add_argument("--optimizer", default="adamw8bit", choices=["adamw8bit", "lion", "adamw"])
    ap.add_argument("--warmup", type=float, default=WARMUP_FRAC)
    ap.add_argument("--floor", type=float, default=COSINE_FLOOR)
    ap.add_argument("--fused-ce", action="store_true", default=KEPT.get("fused_ce", False),
                    help="Liger fused linear cross-entropy (no 270K-vocab logits materialised); adopt only if bench shows identical loss")
    ap.add_argument("--fla-conv", action="store_true",
                    help="use fla's Triton causal short-conv instead of the transformers torch fallback")
    ap.add_argument("--mask-boundaries", action="store_true",
                    help="loss masking: do not predict the first token after an EOS")
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="stop after this many tokens this session (Stage A uses 200M)")
    args = ap.parse_args()

    # GPU guard: another process using > 8GB means do not launch
    import subprocess
    # WSL2 cannot report per-process GPU memory, so use total memory in use at
    # launch time: nothing of ours is running yet, so any usage is another job.
    q = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    try:
        other = int(q.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        other = 0
    if other > 8192:
        msg = f"NOT LAUNCHING {args.run}: other GPU processes use {other} MiB (> 8GB)"
        print(msg)
        with open("STATUS.md", "a") as f:
            f.write(f"\n- {time.strftime('%F %T')}: {msg}\n")
        sys.exit(3)

    meta = json.load(open(f"{args.data}/meta.json"))
    weights = {b: meta["buckets"][b]["train_tokens"] for b in meta["buckets"]}
    total_w = sum(weights.values())
    buckets = list(weights)
    probs = [weights[b] / total_w for b in buckets]
    readers = {b: ShardReader(args.data, b) for b in buckets}

    SEQ, WARMUP_FRAC, COSINE_FLOOR = args.seq, args.warmup, args.floor
    if args.fla_conv:
        # experiment exp019: swap the conv path. transformers' qwen3_5 binds
        # causal_conv1d_fn to a torch fallback when causal-conv1d is absent;
        # fla ships a Triton kernel with the same (x, weight, bias, activation) contract.
        import transformers.models.qwen3_5.modeling_qwen3_5 as M
        from fla.modules.conv.causal_conv1d import causal_conv1d as fla_causal_conv1d
        def _fla_conv(x, weight, bias=None, seq_idx=None, activation=None, **kw):
            out, _ = fla_causal_conv1d(x.transpose(1, 2).contiguous(), weight, bias,
                                       activation=activation)
            return out.transpose(1, 2)
        M.causal_conv1d_fn = _fla_conv
        print("conv path: fla Triton causal_conv1d")
    model, new_rows = build_model(args.tokenizer, args.stage_a, args.init_embeddings,
                                  args.lora_r, args.lora_mlp_r, args.full_mlp, args.unfreeze_embeddings)
    params = [p for p in model.parameters() if p.requires_grad]
    groups = [{"params": [p for p in params if p is not new_rows], "weight_decay": 0.1}]
    if new_rows is not None:
        # no weight decay on the embedding matrix: frozen rows must stay bit-identical
        groups.append({"params": [new_rows], "weight_decay": 0.0})
    groups = [g for g in groups if g["params"]]
    if args.optimizer == "adamw8bit":
        from bitsandbytes.optim import AdamW8bit
        opt = AdamW8bit(groups, lr=args.lr, betas=(0.9, 0.95))
    elif args.optimizer == "lion":
        from bitsandbytes.optim import Lion8bit
        opt = Lion8bit(groups, lr=args.lr, betas=(0.9, 0.99))
    else:
        opt = torch.optim.AdamW(groups, lr=args.lr, betas=(0.9, 0.95))

    # scheduler horizon: estimate steps from budget at ~8K tok/s minimum
    est_total_steps = max(50, int(args.minutes * 60 * 12000 / STEP_TOKENS))
    warmup = max(5, int(est_total_steps * WARMUP_FRAC))
    def lr_lambda(s):
        if s < warmup:
            return s / warmup
        t = (s - warmup) / max(1, est_total_steps - warmup)
        t = min(t, 1.0)
        return COSINE_FLOOR + (1 - COSINE_FLOOR) * 0.5 * (1 + math.cos(math.pi * t))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

    step, tokens_seen = 0, 0
    resumed_from = None
    if args.resume:
        ck = latest_ckpt(args.run)
        if ck:
            if os.path.exists(f"{ck}/adapter_model.safetensors"):
                from peft import set_peft_model_state_dict
                from safetensors.torch import load_file
                set_peft_model_state_dict(model, load_file(f"{ck}/adapter_model.safetensors"))
            if os.path.exists(f"{ck}/embeddings.pt"):
                emb = model.get_input_embeddings().weight
                with torch.no_grad():
                    emb.copy_(torch.load(f"{ck}/embeddings.pt", weights_only=True)["embed_tokens"].to(emb.dtype))
            opt.load_state_dict(torch.load(f"{ck}/optimizer.pt", weights_only=False))
            sched.load_state_dict(torch.load(f"{ck}/scheduler.pt", weights_only=False))
            load_rng(torch.load(f"{ck}/rng.pt", weights_only=False))
            m = json.load(open(f"{ck}/meta.json"))
            step, tokens_seen = m["step"], m["tokens_seen"]
            for b, s in m["readers"].items():
                readers[b].load_state(s)
            resumed_from = ck
            print(f"resumed from {ck}: step {step}, {tokens_seen/1e6:.1f}M tokens")

    if not args.no_compile:
        model = torch.compile(model)

    accum = STEP_TOKENS // (SEQ * MICRO_BSZ)
    from transformers import AutoTokenizer
    eos_id = AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B-Base").eos_token_id
    t_start = time.time()
    t_last_ckpt = t_start
    budget_s = args.minutes * 60
    log(args.run, {"event": "start", "run": args.run, "resumed": resumed_from,
                   "lr": args.lr, "step": step, "time": time.time()})
    losses = []
    tokens_at_start = tokens_seen
    while time.time() - t_start < budget_s:
        if args.max_tokens and tokens_seen - tokens_at_start >= args.max_tokens:
            print(f"token budget {args.max_tokens} reached"); break
        if os.path.exists("STOP") or os.path.exists("PAUSE") or os.path.exists("PAUSE-SCHEDULE"):
            print("PAUSE/STOP detected; checkpointing and exiting 0")
            save_ckpt(args.run, step, tokens_seen, model, opt, sched, readers)
            with open("STATUS.md", "a") as f:
                f.write(f"\n- paused at step {step} ({time.strftime('%F %T')})\n")
            sys.exit(0)
        opt.zero_grad(set_to_none=True)
        step_loss = 0.0
        for _ in range(accum):
            b = random.choices(buckets, probs)[0]
            block = readers[b].next_block(SEQ * MICRO_BSZ)
            x = torch.from_numpy(block.astype(np.int64)).view(MICRO_BSZ, SEQ).cuda()
            y = x
            if args.mask_boundaries:
                y = x.clone()
                after_eos = torch.zeros_like(x, dtype=torch.bool)
                after_eos[:, 1:] = x[:, :-1] == eos_id
                y[after_eos] = -100
            if args.fused_ce:
                loss = fused_ce_loss(model, x, y) / accum
            else:
                loss = model(input_ids=x, labels=y).loss / accum
            loss.backward()
            step_loss += loss.item()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step(); sched.step()
        step += 1
        tokens_seen += STEP_TOKENS
        losses.append(step_loss)
        if step % 5 == 0:
            dt = time.time() - t_start
            print(f"step {step} loss {step_loss:.4f} lr {sched.get_last_lr()[0]:.2e} "
                  f"{tokens_seen/1e6:.1f}M tok {dt:.0f}s", flush=True)
            log(args.run, {"event": "train", "step": step, "loss": step_loss,
                           "tokens": tokens_seen, "lr": sched.get_last_lr()[0],
                           "time": time.time()})
        if time.time() - t_last_ckpt > CKPT_EVERY_S:
            save_ckpt(args.run, step, tokens_seen, model, opt, sched, readers)
            t_last_ckpt = time.time()

    save_ckpt(args.run, step, tokens_seen, model, opt, sched, readers)
    dt = time.time() - t_start
    tokens_this_session = tokens_seen - (0 if resumed_from is None
                                         else json.load(open(f"{resumed_from}/meta.json"))["tokens_seen"])
    bpb = eval_bpc(model, args.data, meta)
    result = {"event": "final", "run": args.run, "step": step,
              "tokens": tokens_seen, "tok_per_s": round(tokens_this_session / dt),
              "val_bpc": bpb, "time": time.time()}
    print(json.dumps(result, indent=2))
    log(args.run, result)

if __name__ == "__main__":
    main()
