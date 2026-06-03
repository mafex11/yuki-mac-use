"""Local fine-tuning pipeline for Yuki's tool-calling agent.

Phase B of Plan Q. Produces a LoRA-fine-tuned small model (llama3.2:1b → 3b →
7b ladder) that reliably emits Yuki's native tool calls, trained entirely
on-device. Not part of the shipped `yuki` package — dev/ML tooling only.
"""
