"""Convert Yuki tool-call records into MLX-LM chat-format training data.

CRITICAL: train-format MUST equal serve-format. We previously trained a custom
dialect ({"tool":..., "args":...} JSON in the content) which fought the base
model's strong pretrained prior ({"name":..., "parameters":...}); a 1B + small
LoRA couldn't overwrite it, so inference degenerated into looping/truncated
output. The fix is to train on the model's OWN NATIVE tool-call format.

mlx-lm's ChatDataset reads each row's optional `tools` field and renders via
`tokenizer.apply_chat_template(messages, tools=tools)`. So if we provide:

  messages: [system, user, assistant(with tool_calls)]
  tools:    [<real function schema>, ...]   (the present_tools for this row)

...the HF tokenizer emits the base model's native tool template verbatim
(Llama 3.2 → {"name":..,"parameters":..}; Qwen 2.5 → <tool_call>{...}</tool_call>).
Ollama then SERVES that same template, so train == serve by construction and
we serve through the normal native tools= API — no custom dialect needed.

Row shape we emit (one JSON object per line):
  {"messages":[{role,content}, {role,content},
               {role:"assistant","content":"",
                "tool_calls":[{"type":"function",
                               "function":{"name":..,"arguments":{...}}}]}],
   "tools":[{"type":"function","function":<json_schema>}, ...]}
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _tool_schemas() -> dict[str, dict[str, Any]]:
    """Native function schema per tool, from the real registry. This is the
    EXACT schema Ollama receives at inference (ChatOllama._convert_tools), so
    training on it keeps the rendered tool list identical to serving."""
    from yuki.agent.tools import BUILTIN_TOOLS

    return {t.name: {"type": "function", "function": t.json_schema}
            for t in BUILTIN_TOOLS}


def _tools_for(present_tools: list[str]) -> list[dict[str, Any]]:
    schemas = _tool_schemas()
    return [schemas[name] for name in present_tools if name in schemas]


def _system_message() -> str:
    """System prompt. MUST match the eval/serve system text so train==serve
    (the eval harness in yuki/eval/run.py uses this exact wording). The tool
    list is supplied via `tools=` and rendered by the template."""
    return ("You are a macOS control agent. Choose the single best tool to "
            "begin the user's task. Always emit a tool call.")


def _user_message(rec: dict[str, Any]) -> str:
    """User message. MUST match the eval format ("Task: ..." + "Screen state:")
    so the model sees the same surface form at train and eval time — a 1b keys
    hard on this wrapper, and a mismatch silently tanks the score."""
    parts = [f"Task: {rec['task']}"]
    if rec.get("screen", "").strip():
        parts.append("Screen state:\n" + rec["screen"])
    return "\n\n".join(parts)


def record_to_messages(rec: dict[str, Any]) -> dict[str, Any]:
    present = rec.get("present_tools") or [rec["tool"], "done_tool"]
    return {
        "messages": [
            {"role": "system", "content": _system_message()},
            {"role": "user", "content": _user_message(rec)},
            {"role": "assistant", "content": "",
             "tool_calls": [{
                 "type": "function",
                 "function": {"name": rec["tool"], "arguments": rec["args"]},
             }]},
        ],
        "tools": _tools_for(present),
    }


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
