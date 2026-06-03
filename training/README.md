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

- `seeds.py` — hand-authored single-step seeds (one intent → one tool).
- `trajectories.py` — **multi-step goals** flattened to single-decision rows
  (the same tool in many screen contexts). This is where the real semantic
  diversity lives; single-step seeds alone made the 1b memorize and collapse.
- `augment.py` — multiplies surface variety (app/verb swaps), folds in the
  trajectory rows, and injects hard-negative `present_tools`.
- `schema.py` — two-layer validator (schema + functional); every row checked.
- `to_mlx.py` — converts to MLX **native** tool-call rows: `{messages:[system,
  user, assistant(tool_calls)], tools:[…schemas]}`. mlx-lm renders these
  through the base model's own chat template.

Generated data lives under `training/data/` (gitignored — reproducible).

### Two hard-won invariants (do not break these)

1. **train-format == serve-format.** Train on the model's NATIVE tool-call
   format (`{"name":…,"parameters":…}` for Llama), NOT a custom dialect. The
   first attempt used a `{"tool":…,"args":…}` dialect and scored 0.10 — a 1b's
   pretrained prior overpowers a small LoRA, so it degenerated at inference.
2. **train-prompt == eval/serve-prompt.** `to_mlx._system_message` /
   `_user_message` must match `yuki/eval/run.py` (and the live agent) verbatim
   (`"Task: …"` + `"Screen state:"`). A 1b keys hard on this wrapper; a mismatch
   silently tanks the score even when tool selection is right.

## Train (uses the training venv)

```bash
training/.venv/bin/python -m training.train_lora \
    --model mlx-community/Llama-3.2-1B-Instruct-4bit
```

Adapter weights land in `training/adapters/` (one checkpoint per 100 iters —
eval several, pick the best; don't assume more iters = better). Defaults
(`train_lora.py:DEFAULTS`): batch_size=1, top-8 LoRA layers, **max_seq 3072,
`--grad-checkpoint` on**. Native rows are long (~2200-2950 tok); seq 1024 would
truncate the assistant target away → `nan` loss / 0 trained tokens. grad-
checkpoint keeps peak mem ~4.5GB so a 16GB Mac doesn't swap.

## Fuse → Ollama (serve the result)

```bash
# fuse the chosen checkpoint into the base. --dequantize is REQUIRED: Ollama's
# importer rejects MLX's U32-packed 4-bit weights ("unknown data type: U32").
cp training/adapters/0000300_adapters.safetensors training/adapters/adapters.safetensors
training/.venv/bin/python -m mlx_lm fuse \
    --model mlx-community/Llama-3.2-1B-Instruct-4bit \
    --adapter-path training/adapters --save-path training/fused --dequantize

cd training && ollama create yuki-1b -f Modelfile
```

> The Modelfile embeds the base model's native tool template (so Ollama serves
> the same format we trained on) and a SYSTEM line. `ollama show yuki-1b` must
> list `Capabilities: tools`.

## Evaluate (the acceptance gate)

```bash
uv run python -m yuki.eval.run --model yuki-1b --mode flash
```

**Measured results (graph_score, Tool RAG on):**

| model | score | note |
|-------|-------|------|
| llama3.2:1b (stock) | 0.10 | baseline |
| **yuki-1b** (this fine-tune) | **0.30** | 3× stock; capped by 1b JSON-syntax errors |
| qwen2.5:3b (stock) | 0.40 | next ladder rung |
| qwen2.5:7b (stock) | 0.90 | reliable |

yuki-1b's residual failures are malformed JSON (`{"name":"launch"…}`, dropped
braces, `App_tool`), not wrong tool choice — the 1b's structured-output wall.

## The ladder

**llama3.2:1b → 3b → 7b, stop when eval clears the bar.** The 1b proved the
pipeline works (0.10 → 0.30) but hit its capacity wall on JSON syntax. Climb to
3b (better structured-output reliability) on the SAME data + pipeline.
