# Yuki local fine-tuning (Phase B)

Fine-tune a small model **entirely on-device** (Apple Silicon / MLX) so Yuki
reliably emits its native tool calls without a cloud API. This is the path to
closing the ~40% reliability gap the untuned local 7B leaves (see
`docs/superpowers/specs/2026-06-02-Q-...`).

## Why this exists

The untuned local models *select* tools well with Tool RAG (qwen2.5:7b → 0.90)
but **terminate/emit inconsistently** (~60% end-to-end). Fine-tuning on Yuki's
exact tool-call format fixes that consistency — TinyAgent took a 1.1B from 12%
to 80% this way. We train smallest-first and stop when one's good enough:

**Ladder: llama3.2:1b → 3b → 7b (stop when eval clears the bar).**

On a 16GB M-series: 1b trains comfortably (~1-3h), 3b is tight (batch=1, ~4-8h),
7b will swap (slow + SSD wear, but *correct* and *finishes* — not impossible).

## Environment

Isolated venv (kept out of the shipped `yuki` deps):

```bash
cd training
uv venv .venv --python 3.12
UV_HTTP_TIMEOUT=300 uv pip install --python .venv/bin/python mlx-lm
.venv/bin/python -c "import mlx.core as mx; print('metal:', mx.metal.is_available())"  # → True
```

## Data pipeline (no API, no cost — fully local)

```bash
# from repo root (main env has the yuki package for validation)
uv run python -m training.augment  --out training/data --per-seed 12
uv run python -m training.to_mlx   --in-dir training/data --out-dir training/data/mlx
```

- `seeds.py` — hand-authored, semantically-correct seed examples.
- `augment.py` — multiplies surface variety (app/verb swaps) + injects
  hard-negative `present_tools` (correct tool + observed wrong picks).
- `schema.py` — two-layer validator (schema + functional); every row checked.
- `to_mlx.py` — converts to MLX chat format (system lists tools, user=task,
  assistant=target JSON tool call). Writes `train.jsonl` + `valid.jsonl`.

Generated data lives under `training/data/` (gitignored — reproducible from
seeds).

## Train (uses the training venv)

```bash
training/.venv/bin/python -m training.train_lora \
    --model mlx-community/Llama-3.2-1B-Instruct-4bit
```

Adapter weights land in `training/adapters/`. Hyperparameters
(`train_lora.py:DEFAULTS`) are RAM-conservative: batch_size=1, top-8 LoRA
layers, max_seq 1024, ~600 iters. Bump `--iters` when the dataset grows.

## Fuse → GGUF → Ollama (serve the result)

```bash
# fuse adapter into the base, export fused MLX weights
training/.venv/bin/python -m mlx_lm fuse \
    --model mlx-community/Llama-3.2-1B-Instruct-4bit \
    --adapter-path training/adapters \
    --save-path training/fused

# convert fused weights to GGUF for Ollama (llama.cpp convert), then:
#   ollama create yuki-1b -f training/Modelfile
# (Modelfile: FROM ./fused-gguf + a SYSTEM line; see below)
```

> GGUF conversion specifics depend on your llama.cpp version; the fused MLX
> weights in `training/fused` are the portable artifact. Register the result
> with Ollama as `yuki-1b`.

## Evaluate (the acceptance gate)

The same eval harness that measured the baseline:

```bash
uv run python -m yuki.eval.run --model yuki-1b --mode flash
```

**Ship gate:** `graph_score` ≥ the off-the-shelf baseline for that size
(1b=0.10, 3b=0.40, 7b=0.90). If yuki-1b clears ~0.6+, it's a usable local
default; add it to the recommended list in
`yuki/backend/routers/provider.py`. If not, climb the ladder.

## Proof-of-concept first

Start with `--per-seed 12` (~200 rows) and train 1b. If the score moves
meaningfully vs the 0.10 baseline, scale `--per-seed` up (more data) and/or
climb to 3b. If it doesn't move at all, diagnose before spending more.
