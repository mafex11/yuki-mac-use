"""Thin wrapper to LoRA-fine-tune a local model on Yuki's tool-call data via MLX.

Runs on Apple Silicon (Metal) with the isolated training/.venv. Defaults are
tuned for a 1-3B model on 16GB unified memory: small batch + short sequences so
the working set stays in RAM (avoid swap — see plan notes on the model ladder).

Pipeline:  augment.py -> to_mlx.py -> THIS -> fuse -> GGUF -> `ollama create`.

Usage (from repo root, with the training venv):
    # 1. (one-time) generate + convert data
    uv run python -m training.augment   --out training/data --per-seed 12
    uv run python -m training.to_mlx    --in-dir training/data --out-dir training/data/mlx
    # 2. train (uses training/.venv which has mlx-lm)
    training/.venv/bin/python -m training.train_lora --model mlx-community/Llama-3.2-1B-Instruct-4bit

This wrapper just assembles the `mlx_lm.lora` command with vetted args; you can
also call `mlx_lm.lora` directly. It does NOT auto-fuse/convert — those are
explicit follow-up steps (see training/README.md) so you can eval the adapter
first.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Hyperparameters (TinyAgent-informed, RAM-conservative for 16GB M-series).
DEFAULTS = {
    "iters": 600,          # ~3 epochs over a small set; bump with bigger data
    "batch_size": 1,       # keep working set in RAM (16GB ceiling)
    "num_layers": 8,       # LoRA on the top N layers (cheaper, usually enough)
    "learning_rate": 1e-4,
    "max_seq_length": 1024,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mlx-community/Llama-3.2-1B-Instruct-4bit",
                    help="HF/MLX base model (ungated mlx-community converts recommended)")
    ap.add_argument("--data", default="training/data/mlx",
                    help="dir with train.jsonl + valid.jsonl (MLX chat format)")
    ap.add_argument("--adapter-path", default="training/adapters",
                    help="where LoRA adapter weights are written")
    ap.add_argument("--iters", type=int, default=DEFAULTS["iters"])
    ap.add_argument("--batch-size", type=int, default=DEFAULTS["batch_size"])
    ap.add_argument("--num-layers", type=int, default=DEFAULTS["num_layers"])
    ap.add_argument("--learning-rate", type=float, default=DEFAULTS["learning_rate"])
    ap.add_argument("--max-seq-length", type=int, default=DEFAULTS["max_seq_length"])
    args = ap.parse_args()

    data = Path(args.data)
    if not (data / "train.jsonl").exists():
        sys.exit(f"error: {data}/train.jsonl not found — run to_mlx.py first.")
    Path(args.adapter_path).mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "mlx_lm", "lora",
        "--model", args.model,
        "--train",
        "--data", str(data),
        "--adapter-path", args.adapter_path,
        "--iters", str(args.iters),
        "--batch-size", str(args.batch_size),
        "--num-layers", str(args.num_layers),
        "--learning-rate", str(args.learning_rate),
        "--max-seq-length", str(args.max_seq_length),
        "--mask-prompt",  # only train on the assistant target, not the prompt
    ]
    print("running:", " ".join(cmd))
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
