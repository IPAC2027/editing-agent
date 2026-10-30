"""QLoRA fine-tuning of Qwen3-14B on JACoW reference formatting.

    python scripts/finetune/train_qwen3_lora.py --data data/refs --out runs/refs-v1
    python scripts/finetune/train_qwen3_lora.py --data data/refs --check   # no GPU needed

Input: train.jsonl / eval.jsonl written by ``main.py finetune-data``.  Each row
holds chat messages [system, user, assistant]; they are trained as
prompt -> completion, so the loss is on the formatted reference only.

Defaults suit one 24 GB GPU (4-bit base model, LoRA rank 16 on attention and
MLP projections, sequences of 1024 tokens).  ``--check`` prints the first
example exactly as the model will see it — run it before spending GPU hours:
the system prompt must end with "/no_think" and no <think> text may appear in
the completion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _rows(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        msgs = json.loads(line)["messages"]
        yield {"prompt": msgs[:2], "completion": msgs[2:]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("runs/jacow-refs"))
    ap.add_argument("--base", default="Qwen/Qwen3-14B")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--check", action="store_true", help="print one templated example and stop")
    args = ap.parse_args()

    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    train = list(_rows(args.data / "train.jsonl"))
    evaluation = list(_rows(args.data / "eval.jsonl"))
    if args.check:
        first = train[0]
        print(tokenizer.apply_chat_template(first["prompt"] + first["completion"], tokenize=False,
                                            enable_thinking=False))
        print(f"\n{len(train)} training / {len(evaluation)} evaluation examples")
        return

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    model = AutoModelForCausalLM.from_pretrained(
        args.base, torch_dtype=torch.bfloat16, device_map="auto",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True))
    lora = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                      task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    config = SFTConfig(
        output_dir=str(args.out), num_train_epochs=args.epochs, learning_rate=args.lr,
        per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.accum,
        lr_scheduler_type="cosine", warmup_ratio=0.03, bf16=True,
        gradient_checkpointing=True, max_length=args.max_len,
        completion_only_loss=True, logging_steps=20, eval_strategy="steps",
        eval_steps=200, save_steps=200, save_total_limit=3, report_to="none",
        chat_template_kwargs={"enable_thinking": False})
    trainer = SFTTrainer(model=model, args=config, peft_config=lora,
                         train_dataset=Dataset.from_list(train),
                         eval_dataset=Dataset.from_list(evaluation) if evaluation else None,
                         processing_class=tokenizer)
    trainer.train()
    trainer.save_model(str(args.out / "adapter"))
    tokenizer.save_pretrained(str(args.out / "adapter"))
    print(f"LoRA adapter saved to {args.out / 'adapter'}")


if __name__ == "__main__":
    main()
