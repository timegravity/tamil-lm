#!/usr/bin/env bash
# Phase 4 pre-flight: run before launching run_cpt.sh. Exits non-zero on any failure.
#   ./preflight_cpt.sh [shard_profile_dir]   (default: data/shards/main3b_ext)
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
DATA="${1:-data/shards/main3b_ext}"
ok=1
chk() { if eval "$2"; then echo "PASS  $1"; else echo "FAIL  $1"; ok=0; fi; }
chk "venv pins (transformers 5.15.1, numpy 2.4.4, torch 2.11.0+cu128)" "$PY -c 'import transformers,numpy,torch; assert transformers.__version__==\"5.15.1\" and numpy.__version__==\"2.4.4\" and torch.__version__.startswith(\"2.11.0+cu128\")'"
chk "train.py compiles"            "$PY -m py_compile train.py"
chk "train_long.py compiles"       "$PY -m py_compile train_long.py"
chk "shard profile has meta.json"  "[ -f $DATA/meta.json ]"
chk "shard profile has train+val shards" "ls $DATA/tamil_web_0000.bin $DATA/val_tamil_web_*.bin >/dev/null 2>&1"
chk "KEPT tokenizer dir exists"    "[ -d ckpt/tokenizer_ext ]"
chk "KEPT Stage A embeddings exist" "[ -f ckpt/exp1_stageA/step_3053/embeddings.pt ]"
chk "no DONE-CPT sentinel"         "[ ! -f DONE-CPT ]"
chk "no STOP file"                 "[ ! -f STOP ]"
chk "tmux available"               "command -v tmux >/dev/null"
chk "run_cpt.sh executable"        "[ -x run_cpt.sh ]"
chk "notify.sh executable"         "[ -x notify.sh ]"
chk "GPU memory in use <= 8GB (nothing else running)" "[ \$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc '0-9') -le 8192 ]"
chk "no autoresearch/train running" "! pgrep -f '[t]rain.py --run' >/dev/null && ! pgrep -f '[a]utoresearch.sh' >/dev/null"
chk "disk free > 50GB"             "[ \$(df -BG --output=avail . | tail -1 | tr -dc '0-9') -gt 50 ]"
$PY - "$DATA" <<'EOF'
import json, sys
m = json.load(open(f"{sys.argv[1]}/meta.json"))
tot = sum(v["train_tokens"] for v in m["buckets"].values())
print(f"INFO  profile {sys.argv[1]}: {tot/1e9:.2f}B train tokens; shares " +
      ", ".join(f"{b} {v['train_tokens']/tot:.3f}" for b, v in m["buckets"].items()))
import train
print("INFO  KEPT recipe:", train.KEPT)
EOF
[ $ok -eq 1 ] && echo "PREFLIGHT OK" || { echo "PREFLIGHT FAILED"; exit 1; }
