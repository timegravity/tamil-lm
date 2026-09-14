#!/bin/bash
# Qwen/Qwen3.5-<size> (the instruct release; size 2B by default, ./run_qwen35_gguf.sh 4B for the 4B) to Q4_K_M GGUF with the pinned llama.cpp, for sideloading into the app (decision 3.2:
# Qwen 3.5 GGUFs are converted with the pinned llama.cpp). Text weights only; the vision tower is not part of the text GGUF.
set -e
cd "$(dirname "$0")"
S=${1:-2B}
LOG=logs/qwen35_gguf.log
echo "[$(date -u +%FT%TZ)] download" >> $LOG
D=$(.venv/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen3.5-$S', allow_patterns=['*.json','*.safetensors','*.jinja','*.txt','*.model','tokenizer*']))")
echo "[$(date -u +%FT%TZ)] convert $D" >> $LOG
.venv-gguf/bin/python tools/llama.cpp/convert_hf_to_gguf.py "$D" --outtype bf16 --outfile exports/Qwen3.5-$S-bf16.gguf >> $LOG 2>&1
tools/llama.cpp/build/bin/llama-quantize exports/Qwen3.5-$S-bf16.gguf exports/Qwen3.5-$S-Q4_K_M.gguf Q4_K_M >> $LOG 2>&1
[ "$S" = 2B ] || rm -f exports/Qwen3.5-$S-bf16.gguf   # the bf16 intermediate is only kept for the 2B
ls -la exports/Qwen3.5-$S-Q4_K_M.gguf >> $LOG
sha256sum exports/Qwen3.5-$S-Q4_K_M.gguf >> $LOG
echo "[$(date -u +%FT%TZ)] smoke" >> $LOG
tools/llama.cpp/build/bin/llama-completion -m exports/Qwen3.5-$S-Q4_K_M.gguf -p "<|im_start|>user
Say hello in Tamil.<|im_end|>
<|im_start|>assistant
" -n 60 -no-cnv --temp 0 2>/dev/null | tail -5 >> $LOG
echo "[$(date -u +%FT%TZ)] done" >> $LOG
