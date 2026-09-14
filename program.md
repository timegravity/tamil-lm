# Autoresearch program: Tamil CPT recipe search

Karpathy-style loop. One mutable file, one primary gate, fixed budget per run.

## Rules
- The ONLY mutable file during the loop is train.py. prepare.py and the eval
  harness are frozen after Phase 1.
- One change per experiment. Never two.
- Budget: 15 minutes of training on the 100M-token autoresearch subset per run.
- Metrics per run: total val_bpc (bits per CHARACTER, comparable across
  tokenizers), per-bucket val_bpc, tok/s, AND literature probe accuracy
  (eval/run_probe.py, MCQ subset for speed; full probe on keeps).
  bpb is logged for reference only; bpc is the gate metric (Vignesh 2026-08-25).
- GATE (literature-first): keep a change if
  (a) probe_acc does not fall AND total val_bpc improves by > 0.002, OR
  (b) probe_acc rises by more than 1 point (0.01).
  Otherwise: git revert the change.
- Log every run as one row in experiments.tsv:
  id, commit, change, val_bpb, probe_acc, tok/s, kept
- Stop after 60 experiments or 15 consecutive non-keeps, whichever first.
- Update STATUS.md every 30 minutes. Call notify.sh on every kept improvement.
- Before every GPU launch: nvidia-smi; if another process uses > 8GB, do not
  launch, write reason to STATUS.md.

## Reference recipe (the baseline commit)
LoRA r128 on attention + DeltaNet projections, r256 on MLP; embeddings and
lm_head frozen; 8-bit AdamW; lr 2e-4 cosine, warmup 3%; seq 4096; batch 4 with
grad accum to 64K tokens/step; grad checkpointing on; torch.compile on;
MTP head off; bf16.

## Experiment queue (priority order, one variable each)
1. TOKENIZER EXTENSION (moved to first by Vignesh, fertility 6.49):
   tokenizer_extend.py trains a 24K-piece Tamil SentencePiece unigram on the
   Tamil web bucket, adds only pieces absent from the Qwen vocab, writes an
   init map. train.py --tokenizer ckpt/tokenizer_ext initialises each new
   embedding row as the mean of its old-tokenizer subword embeddings and
   unfreezes exactly the new rows (plus the tied lm_head rows) for full
   training; everything else stays LoRA.
   Protocol: Stage A warmup of 200M tokens with ONLY the new rows trainable,
   then the standard 15-minute budget run with the full recipe. Compare to
   baseline on bpc + probe. Report new fertility and effective Tamil context
   in words at seq 4096. Requires re-tokenised shards (data/shards/auto100m_ext).
2. LR sweep: 1e-4, 3e-4, 5e-4
3. LoRA rank and target sweep, including full fine-tune of MLP only
4. Unfreeze embeddings + lm_head (measure VRAM and tok/s cost; vocab is 248K
   and tied, this is expensive at 2B)
5. Literature upweight 1x / 3x / 5x (mix-level; literature is now 30% of mix,
   the sweep adjusts repetition inside the bucket)
6. Replay fraction 5% / 10% / 15%
7. Sequence length 2048 vs 4096 vs 8192
8. Optimizer: 8-bit AdamW vs Muon on hidden matrices (if available) vs Lion
9. Packing strategy and loss masking at doc boundaries
10. MTP head loss on vs off (default off)
11. Warmup and cosine floor sweep
12. Q&A rendering fraction inside the literature bucket (if time permits)
13. Conv path throughput: fla Triton short-conv vs transformers torch fallback
    (only if profiling shows the conv fallback is a bottleneck)

## Notes
- bpc is computed as loss_nats_per_token / (chars per token) / ln 2 per bucket
  using the character counts stored at shard build time (meta.json), so it is
  comparable under tokenizer changes. total = char-weighted mean over buckets.
- Literature augmentation floor: >= 20 distinct renderings per tier-1 unit and
  >= 8 per tier-2 unit before repetition; repetition cap 8x per unit in run 1.
  If the 30% literature share cannot be met, the share is reduced and logged.
- The 100M subset has the same mix as the main run (40/30/10/10/10).
- Probe MCQ subset during the loop: meaning_mcq + identify_source (loglik
  scoring only, ~380 items, fast). quote/which_kural need generation and run
  only on kept candidates.

## Benchmark-driven improvement loop (addendum 2026-08-25; after first CPT run, before SFT; again after SFT)
1. eval/run_dev.py on the latest checkpoint, then eval/analyze.py --stage <stage> [--judge]:
   per-benchmark delta vs base and, for every benchmark below +2 points, 30 wrong
   items categorised (not_understanding, wrong_tamil, right_idea_wrong_format,
   script_mixing, refused, truncated, tokenisation_artefact) with counts.
2. Propose at most 3 interventions, each mapped to a category with its count.
   Allowed: add a data bucket (e.g. Tamil MCQ-format synthetic data), adjust a
   mix ratio, change the SFT prompt format, Tanglish normalisation.
   NOT allowed: benchmark items or near-paraphrases as training data.
3. Each intervention is one experiment (one variable), judged on the dev suite
   plus the literature probe. Keep or revert.
4. At most 2 rounds per stage, then freeze and run eval/run_test.py once.
5. eval/render_table.py --write puts base / cpt_final / sft_final (dev and test)
   into README.md with commit hashes; add a paragraph on remaining weaknesses.

- Mix-ratio experiments rebuild shards with prepare.py --mix; compare per-bucket bpc, not the char-weighted total (val proportions differ).
