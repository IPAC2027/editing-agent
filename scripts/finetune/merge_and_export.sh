#!/bin/bash
# Merge the LoRA adapter into Qwen3-14B, convert to GGUF, quantise, and
# register it with Ollama as "jacow-refs".
#   scripts/finetune/merge_and_export.sh runs/refs-v1/adapter /path/to/llama.cpp
set -euo pipefail
ADAPTER="$1"; LLAMA_CPP="$2"; BASE="${BASE:-Qwen/Qwen3-14B}"; NAME="${NAME:-jacow-refs}"
OUT="$(dirname "$ADAPTER")/merged"
python - "$BASE" "$ADAPTER" "$OUT" <<'PY'
import sys, torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base, adapter, out = sys.argv[1:4]
model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16, device_map="cpu")
model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
model.save_pretrained(out, safe_serialization=True)
AutoTokenizer.from_pretrained(base).save_pretrained(out)
print("merged model in", out)
PY
python "$LLAMA_CPP/convert_hf_to_gguf.py" "$OUT" --outtype f16 --outfile "$OUT/$NAME-f16.gguf"
"$LLAMA_CPP/build/bin/llama-quantize" "$OUT/$NAME-f16.gguf" "$OUT/$NAME-q4_k_m.gguf" Q4_K_M
cat > "$OUT/Modelfile" <<MF
FROM ./$NAME-q4_k_m.gguf
PARAMETER temperature 0
PARAMETER num_ctx 2048
MF
(cd "$OUT" && ollama create "$NAME" -f Modelfile)
echo "Served as '$NAME'. Set REFERENCE_MODEL=$NAME in editing-agent/.env"
