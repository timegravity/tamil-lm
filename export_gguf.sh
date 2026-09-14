#!/usr/bin/env bash
# Export the final merged model to GGUF (bf16 -> Q8_0 and Q4_K_M) with llama.cpp.
#   ./export_gguf.sh ckpt/final/tamil-lm-2b-instruct
# Clones llama.cpp into tools/llama.cpp (once), builds llama-quantize (cmake),
# converts with convert_hf_to_gguf.py, quantizes, and smoke-loads each GGUF
# with llama-cli for a 5-token generation. Writes results to logs/export_gguf.log.
set -eu
cd "$(dirname "$0")"
MODEL="${1:?model dir}"
NAME=$(basename "$MODEL")
mkdir -p tools exports
if [ ! -d tools/llama.cpp ]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp tools/llama.cpp
fi
# converter deps live in their OWN venv: installing them into .venv downgraded
# transformers/numpy once (2026-08-26) and would have broken training.
export PATH="$HOME/.local/bin:$PATH"
[ -d .venv-gguf ] || uv venv --python 3.12 .venv-gguf >/dev/null
uv pip install --python .venv-gguf/bin/python -q -r tools/llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
PY=.venv-gguf/bin/python
if [ ! -x tools/llama.cpp/build/bin/llama-quantize ]; then
    .venv/bin/cmake -S tools/llama.cpp -B tools/llama.cpp/build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF >/dev/null
    .venv/bin/cmake --build tools/llama.cpp/build --target llama-quantize llama-completion -j"$(nproc)" >/dev/null
fi
$PY tools/llama.cpp/convert_hf_to_gguf.py "$MODEL" --outtype bf16 --outfile "exports/$NAME-bf16.gguf"
tools/llama.cpp/build/bin/llama-quantize "exports/$NAME-bf16.gguf" "exports/$NAME-Q8_0.gguf" Q8_0 >/dev/null
tools/llama.cpp/build/bin/llama-quantize "exports/$NAME-bf16.gguf" "exports/$NAME-Q4_K_M.gguf" Q4_K_M >/dev/null
for q in Q8_0 Q4_K_M; do
    echo "== smoke $q"
    tools/llama.cpp/build/bin/llama-completion -m "exports/$NAME-$q.gguf" -p "English: Good morning.\nTamil:" -n 12 -no-cnv 2>/dev/null | tail -2
done
ls -la exports/ | grep "$NAME"
echo "GGUF EXPORT DONE (commit $(git rev-parse --short HEAD))"
