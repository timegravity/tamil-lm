"""Long CPT run (Phase 4). Derived from the winning train.py recipe: reuses its
model builder, shard reader, optimizer, and power-cut-safe checkpoint protocol.

Additions over train.py:
  - always resumes from the latest checkpoint if one exists (run_cpt.sh loops it)
  - checkpoints every 500 steps AND every 20 minutes (whichever first), kept:
    last 3 plus every 5000th (train.KEEP_LAST / KEEP_EVERY)
  - val bpc per bucket every 1000 steps -> logs/<run>.jsonl and STATUS.md
  - loss-spike rule: if the 200-step moving average jumps > 30% above the
    previous 200-step window, halve the LR, restore the last good checkpoint,
    and note it in STATUS.md (LR halving persists via lr_scale in meta.json)
  - resume sanity: log resumed step/tokens and first 20 losses; if the first
    loss is > 2x the pre-cut moving average, stop and write STATUS.md
  - PAUSE / PAUSE-SCHEDULE / STOP files honoured every step
  - writes DONE-CPT when the token target is reached (supervisor exits)

Usage (via run_cpt.sh): python train_long.py --run cpt --resume
"""
import argparse, json, math, os, random, shutil, sys, time
import numpy as np
import torch
import train as T

TOTAL_TOKENS = 3_000_000_000
PROBE_MILESTONES = (500_000_000, 1_000_000_000)   # Vignesh 2026-08-26: full probe, report, notify, no pause
CKPT_EVERY_STEPS = 500
EVAL_EVERY_STEPS = 1000
SPIKE_WINDOW = 200
SPIKE_FACTOR = 1.30

def status_note(msg):
    with open("STATUS.md", "a") as f:
        f.write(f"\n- {time.strftime('%F %T')}: {msg}\n")

def status_rewrite(run, step, tokens, tps, loss, eta_h, ckpt, bpc=None):
    """Rewrite the header block of STATUS.md (single source of truth)."""
    s = open("STATUS.md").read()
    lines = s.split("\n")
    def setline(prefix, text):
        for i, l in enumerate(lines):
            if l.startswith(prefix):
                lines[i] = text; return
    setline("- Phase:", "- Phase: cpt")
    setline("- Current run:", f"- Current run: {run}, step {step}, {tokens/1e6:.0f}M tokens, {tps:.0f} tok/s, last loss (200-step MA) {loss:.3f}, ETA {eta_h:.1f} h")
    setline("- Last checkpoint:", f"- Last checkpoint: {ckpt} ({time.strftime('%F %T')})")
    if bpc:
        setline("- Best result so far:", f"- Best result so far: cpt step {step} val_bpc total {bpc['total']} (per bucket: " +
                ", ".join(f"{k} {v}" for k, v in bpc.items() if not k.endswith('_bpb') and k != 'total') + ")")
    open("STATUS.md", "w").write("\n".join(lines))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="cpt")
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--data", default=os.environ.get("CPT_DATA", "data/shards/main3b_ext_v2"))   # run 2 (2026-08-26): rebuilt literature, 16x/8x caps
    ap.add_argument("--lr", type=float, default=float(os.environ.get("CPT_LR", T.LR)))
    ap.add_argument("--total-tokens", type=int, default=int(os.environ.get("CPT_TOTAL_TOKENS", TOTAL_TOKENS)))   # env override for run 3 (cpt3)
    ap.add_argument("--no-compile", action="store_true")
    args = ap.parse_args()

    if os.path.exists("DONE-CPT"):
        print("DONE-CPT exists; nothing to do"); return
    import subprocess
    q = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    try:
        other = int(q.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        other = 0
    if other > 8192:
        status_note(f"NOT LAUNCHING {args.run}: other GPU processes use {other} MiB"); sys.exit(3)

    meta = json.load(open(f"{args.data}/meta.json"))
    weights = {b: meta["buckets"][b]["train_tokens"] for b in meta["buckets"]}
    buckets = list(weights); tw = sum(weights.values())
    probs = [weights[b] / tw for b in buckets]
    readers = {b: T.ShardReader(args.data, b) for b in buckets}

    model, new_rows = T.build_model(T.KEPT.get("tokenizer"), False,
                                    os.environ.get("CPT_INIT_EMBEDDINGS", T.KEPT.get("init_embeddings")),
                                    lora_r=T.KEPT.get("lora_r", 128), lora_mlp_r=T.KEPT.get("lora_mlp_r", 256),
                                    init_adapter=os.environ.get("CPT_INIT_ADAPTER"))
    from bitsandbytes.optim import AdamW8bit
    params = [p for p in model.parameters() if p.requires_grad]
    groups = [{"params": [p for p in params if p is not new_rows], "weight_decay": 0.1}]
    if new_rows is not None:
        groups.append({"params": [new_rows], "weight_decay": 0.0})
    opt = AdamW8bit([g for g in groups if g["params"]], lr=args.lr, betas=(0.9, 0.95))
    total_steps = args.total_tokens // T.STEP_TOKENS
    warmup = int(total_steps * T.WARMUP_FRAC)
    lr_scale = 1.0
    def lr_lambda(s):
        base = s / max(1, warmup) if s < warmup else \
            T.COSINE_FLOOR + (1 - T.COSINE_FLOOR) * 0.5 * (1 + math.cos(math.pi * min(1.0, (s - warmup) / max(1, total_steps - warmup))))
        return base * lr_scale
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)

    step, tokens = 0, 0
    ma_hist = []          # per-step losses (for moving averages)
    pre_cut_ma = None
    milestones_done = set()
    ck = T.latest_ckpt(args.run)
    if ck:
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict
        set_peft_model_state_dict(model, load_file(f"{ck}/adapter_model.safetensors"))
        if os.path.exists(f"{ck}/embeddings.pt"):
            emb = model.get_input_embeddings().weight
            with torch.no_grad():
                emb.copy_(torch.load(f"{ck}/embeddings.pt", weights_only=True)["embed_tokens"].to(emb.dtype))
        opt.load_state_dict(torch.load(f"{ck}/optimizer.pt", weights_only=False))
        sched.load_state_dict(torch.load(f"{ck}/scheduler.pt", weights_only=False))
        T.load_rng(torch.load(f"{ck}/rng.pt", weights_only=False))
        m = json.load(open(f"{ck}/meta.json"))
        step, tokens = m["step"], m["tokens_seen"]
        lr_scale = m.get("lr_scale", 1.0)
        pre_cut_ma = m.get("ma_loss")
        milestones_done = set(m.get("milestones_done", []))
        for b, s in m["readers"].items():
            readers[b].load_state(s)
        print(f"resumed {ck}: step {step}, {tokens/1e6:.1f}M tokens, lr_scale {lr_scale}, pre-cut MA {pre_cut_ma}")
        T.log(args.run, {"event": "resume", "step": step, "tokens": tokens, "ckpt": ck, "time": time.time()})
    if not args.no_compile:
        model = torch.compile(model)

    accum = T.STEP_TOKENS // (T.SEQ * T.MICRO_BSZ)
    t0 = time.time(); t_ck = t0; tokens0 = tokens
    last_good = ck
    first_losses = []
    while tokens < args.total_tokens:
        if any(os.path.exists(f) for f in ("STOP", "PAUSE", "PAUSE-SCHEDULE")):
            ma = float(np.mean(ma_hist[-SPIKE_WINDOW:])) if ma_hist else None
            T.save_ckpt(args.run, step, tokens, model, opt, sched, readers, {"lr_scale": lr_scale, "ma_loss": ma})
            status_note(f"paused at step {step}"); sys.exit(0)
        opt.zero_grad(set_to_none=True)
        step_loss = 0.0
        for _ in range(accum):
            b = random.choices(buckets, probs)[0]
            x = torch.from_numpy(readers[b].next_block(T.SEQ * T.MICRO_BSZ).astype(np.int64)).view(T.MICRO_BSZ, T.SEQ).cuda()
            loss = model(input_ids=x, labels=x).loss / accum
            loss.backward(); step_loss += loss.item()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step(); sched.step()
        step += 1; tokens += T.STEP_TOKENS
        ma_hist.append(step_loss)
        if len(first_losses) < 20:
            first_losses.append(step_loss)
            if len(first_losses) == 20 and pre_cut_ma:
                T.log(args.run, {"event": "resume_sanity", "first_losses": first_losses, "pre_cut_ma": pre_cut_ma})
                if first_losses[0] > 2 * pre_cut_ma:
                    status_note(f"STOPPED: first loss after resume {first_losses[0]:.3f} > 2x pre-cut MA {pre_cut_ma:.3f}; checkpoint {ck} may be corrupt. Human decision needed.")
                    open("STOP", "w").close(); sys.exit(0)
        # loss spike rule on 200-step windows
        if len(ma_hist) >= 2 * SPIKE_WINDOW and step % SPIKE_WINDOW == 0:
            prev = float(np.mean(ma_hist[-2*SPIKE_WINDOW:-SPIKE_WINDOW])); cur = float(np.mean(ma_hist[-SPIKE_WINDOW:]))
            if cur > SPIKE_FACTOR * prev and last_good:
                lr_scale *= 0.5
                status_note(f"LOSS SPIKE at step {step}: MA {cur:.3f} vs {prev:.3f}; halving LR (scale {lr_scale}) and restoring {last_good}")
                os.system(f'./notify.sh "tamil-lm: loss spike step {step}, LR halved, restoring {last_good}"')
                # write lr_scale into the last good checkpoint's meta and exit; supervisor resumes it
                mp = f"{last_good}/meta.json"; mm = json.load(open(mp)); mm["lr_scale"] = lr_scale
                json.dump(mm, open(mp, "w"))
                for d in os.listdir(f"ckpt/{args.run}"):
                    p = f"ckpt/{args.run}/{d}"
                    if d.startswith("step_") and p != last_good and int(d.split("_")[1]) > int(last_good.split("_")[-1]):
                        shutil.rmtree(p, ignore_errors=True)
                sys.exit(1)
        if step % 10 == 0:
            dt = time.time() - t0; tps = (tokens - tokens0) / dt
            ma = float(np.mean(ma_hist[-SPIKE_WINDOW:]))
            eta_h = (args.total_tokens - tokens) / max(1, tps) / 3600
            print(f"step {step} loss {step_loss:.4f} ma {ma:.4f} lr {sched.get_last_lr()[0]:.2e} {tokens/1e6:.0f}M tok {tps:.0f} tok/s ETA {eta_h:.1f}h", flush=True)
            T.log(args.run, {"event": "train", "step": step, "loss": step_loss, "ma": ma, "tokens": tokens,
                             "lr": sched.get_last_lr()[0], "tok_per_s": tps, "time": time.time()})
        due = [mtok for mtok in PROBE_MILESTONES if tokens >= mtok and mtok not in milestones_done]
        do_ck = step % CKPT_EVERY_STEPS == 0 or time.time() - t_ck > T.CKPT_EVERY_S or bool(due)
        if do_ck:
            ma = float(np.mean(ma_hist[-SPIKE_WINDOW:]))
            path = T.save_ckpt(args.run, step, tokens, model, opt, sched, readers,
                               {"lr_scale": lr_scale, "ma_loss": ma, "milestones_done": sorted(milestones_done | set(due))})
            if path:
                last_good = path; t_ck = time.time()
                for mtok in due:
                    milestones_done.add(mtok)
                    tag = f"{mtok//1_000_000}M"
                    emb = f"{path}/embeddings.pt"
                    cmd = (f"nohup bash -c '.venv/bin/python eval/run_probe.py --model Qwen/Qwen3.5-2B-Base "
                           f"--adapter {path} --tokenizer {T.KEPT.get('tokenizer')} --embeddings {emb} "
                           f"--out logs/probe_cpt_{tag}.json > logs/probe_cpt_{tag}.log 2>&1; "
                           f"R=$(.venv/bin/python -c \"import json; d=json.load(open(\\\"logs/probe_cpt_{tag}.json\\\")); "
                           f"print(d[\\\"probe_acc\\\"], d[\\\"per_type_acc\\\"], \\\"chrF\\\", d[\\\"quote_chrf\\\"])\"); "
                           f"printf \"\\n- MILESTONE PROBE {tag} tokens (ckpt {path}): %s\\n\" \"$R\" >> STATUS.md; "
                           f"./notify.sh \"tamil-lm cpt {tag}: probe $R\"; "
                           f"[ {mtok} -ge 1000000000 ] && .venv/bin/python milestone_decide.py --tag {tag}' > /dev/null 2>&1 &")
                    os.system(cmd)
                    status_note(f"milestone {tag} tokens reached at step {step}; full probe launched in the background on {path}")
                dt = time.time() - t0; tps = (tokens - tokens0) / max(1, dt)
                status_rewrite(args.run, step, tokens, tps, ma, (args.total_tokens - tokens) / max(1, tps) / 3600, path)
                os.system(f'./notify.sh "tamil-lm cpt: checkpoint step {step}, {tokens/1e6:.0f}M tokens"')
        if step % EVAL_EVERY_STEPS == 0:
            bpc = T.eval_bpc(model, args.data, meta)
            T.log(args.run, {"event": "eval", "step": step, "tokens": tokens, "val_bpc": bpc, "time": time.time()})
            print("eval", bpc, flush=True)
            dt = time.time() - t0; tps = (tokens - tokens0) / max(1, dt)
            status_rewrite(args.run, step, tokens, tps, float(np.mean(ma_hist[-SPIKE_WINDOW:])),
                           (args.total_tokens - tokens) / max(1, tps) / 3600, last_good, bpc)
    ma = float(np.mean(ma_hist[-SPIKE_WINDOW:])) if ma_hist else None
    T.save_ckpt(args.run, step, tokens, model, opt, sched, readers, {"lr_scale": lr_scale, "ma_loss": ma})
    bpc = T.eval_bpc(model, args.data, meta)
    T.log(args.run, {"event": "final", "step": step, "tokens": tokens, "val_bpc": bpc, "time": time.time()})
    open("DONE-CPT", "w").write(f"{args.run} step {step} tokens {tokens} {time.strftime('%F %T')}\n")
    status_note(f"CPT COMPLETE: {tokens/1e9:.2f}B tokens, val_bpc {bpc}")
    os.system('./notify.sh "tamil-lm: CPT complete"')

if __name__ == "__main__":
    main()
