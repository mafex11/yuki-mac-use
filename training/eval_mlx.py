"""Evaluate a fine-tuned MLX model (base + LoRA adapter) on Yuki eval cases.

Runs in the training venv (no `yuki` import — reads cases from a JSON exported
by the main env, since the training venv lacks Yuki's full deps). Grades
tool-selection accuracy on the hand-written eval cases the model never trained
on — the honest generalization test (loss can lie on small augmented sets).

Usage:
    # 1. export cases from the MAIN env (has yuki):
    uv run python -m training.export_eval > /tmp/eval_export.json
    # 2. run the eval in the TRAINING venv:
    training/.venv/bin/python -m training.eval_mlx \
        --model mlx-community/Llama-3.2-1B-Instruct-4bit \
        --adapter training/adapters --cases /tmp/eval_export.json
"""
from __future__ import annotations

import argparse
import json


def _system_message(present: list[str], descs: dict[str, str]) -> str:
    lines = ["You are Yuki, a macOS control agent. Choose exactly ONE tool to "
             "begin the user's task and respond with a single JSON object:",
             '{"tool": "<tool_name>", "args": {"thought": "...", ...}}', "",
             "Available tools:"]
    for n in present:
        lines.append(f"- {n}: {descs.get(n, '')}")
    lines += ["", "Always include a `thought`. Use done_tool to answer questions "
              "or report completion. Output ONLY the JSON object."]
    return "\n".join(lines)


def _present_for(exp: str) -> list[str]:
    base = [exp, "done_tool", "app_tool", "shell_tool", "type_tool", "click_tool"]
    seen, out = set(), []
    for t in base:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) == 5:
            break
    return out


def main() -> None:
    from mlx_lm import generate, load

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="mlx-community/Llama-3.2-1B-Instruct-4bit")
    ap.add_argument("--adapter", default="training/adapters")
    ap.add_argument("--cases", default="/tmp/eval_export.json")
    args = ap.parse_args()

    data = json.load(open(args.cases))
    descs = data["descriptions"]
    model, tok = load(args.model, adapter_path=args.adapter)

    correct = 0
    for c in data["cases"]:
        exp = c["expected_tool"]
        user = f"Task: {c['task']}"
        if c.get("screen"):
            user += "\n\nScreen State:\n" + c["screen"]
        msgs = [{"role": "system", "content": _system_message(_present_for(exp), descs)},
                {"role": "user", "content": user}]
        prompt = tok.apply_chat_template(msgs, add_generation_prompt=True)
        out = generate(model, tok, prompt=prompt, max_tokens=120, verbose=False)
        got = "(unparseable)"
        try:
            got = json.loads(out[out.index("{"):out.rindex("}") + 1]).get("tool", "?")
        except Exception:
            pass
        ok = got == exp
        correct += ok
        print(f"{'OK' if ok else 'XX'}  {c['task'][:40]:40} exp={exp:13} got={got}")
    n = len(data["cases"])
    print(f"\nTOOL-SELECTION ACCURACY: {correct}/{n} = {correct / n:.2f}")


if __name__ == "__main__":
    main()
