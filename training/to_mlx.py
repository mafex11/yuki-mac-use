"""Convert Yuki tool-call records into MLX-LM chat-format training data.

MLX-LM's LoRA trainer (`mlx_lm.lora`) reads JSONL where each line is
{"messages": [{"role","content"}, ...]} and applies the model's chat template.

We teach the tool-calling format EXPLICITLY (robust across base models whose
chat templates have inconsistent native tool support):

  system   — lists the available tools for THIS row (present_tools: correct +
             hard-negative distractors) with one-line descriptions, and states
             the output contract (emit ONE JSON tool call).
  user     — the task, plus a Screen State block when the row is reactive.
  assistant— the exact target JSON: {"tool": <name>, "args": {...}}.

This mirrors inference: at run time the agent shows the Tool-RAG-selected tools
and reads back a single tool call. Training on present_tools (not all 16) keeps
train/inference distributions aligned and exercises discrimination.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _descriptions() -> dict[str, str]:
    """One-line description per tool, from the real registry."""
    from yuki.agent.tools import BUILTIN_TOOLS

    out: dict[str, str] = {}
    for t in BUILTIN_TOOLS:
        desc = (t.description or "").strip().splitlines()[0] if t.description else ""
        out[t.name] = desc[:120]
    return out


def _system_message(present_tools: list[str]) -> str:
    descs = _descriptions()
    lines = ["You are Yuki, a macOS control agent. Choose exactly ONE tool to "
             "begin the user's task and respond with a single JSON object:",
             '{"tool": "<tool_name>", "args": {"thought": "...", ...}}',
             "",
             "Available tools:"]
    for name in present_tools:
        lines.append(f"- {name}: {descs.get(name, '')}")
    lines.append("")
    lines.append("Always include a `thought`. Use done_tool to answer questions "
                 "or report completion. Output ONLY the JSON object.")
    return "\n".join(lines)


def _user_message(rec: dict[str, Any]) -> str:
    parts = [f"Task: {rec['task']}"]
    if rec.get("screen", "").strip():
        parts.append("Screen State:\n" + rec["screen"])
    return "\n\n".join(parts)


def _assistant_message(rec: dict[str, Any]) -> str:
    # Compact, stable JSON — the exact target the model learns to emit.
    return json.dumps({"tool": rec["tool"], "args": rec["args"]},
                      ensure_ascii=False)


def record_to_messages(rec: dict[str, Any]) -> dict[str, Any]:
    present = rec.get("present_tools") or [rec["tool"], "done_tool"]
    return {"messages": [
        {"role": "system", "content": _system_message(present)},
        {"role": "user", "content": _user_message(rec)},
        {"role": "assistant", "content": _assistant_message(rec)},
    ]}


def convert_file(src: Path, dst: Path) -> int:
    n = 0
    with dst.open("w", encoding="utf-8") as out:
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.write(json.dumps(record_to_messages(json.loads(line)),
                                 ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="training/data")
    ap.add_argument("--out-dir", default="training/data/mlx")
    args = ap.parse_args()

    in_dir, out_dir = Path(args.in_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # MLX-LM expects train.jsonl + valid.jsonl (note: "valid", not "val").
    mapping = {"train": "train", "val": "valid", "test": "test"}
    for src_name, dst_name in mapping.items():
        src = in_dir / f"{src_name}.jsonl"
        if not src.exists():
            continue
        n = convert_file(src, out_dir / f"{dst_name}.jsonl")
        print(f"{src_name} -> {dst_name}.jsonl: {n} rows")


if __name__ == "__main__":
    main()
