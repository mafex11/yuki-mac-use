# Yuki

A macOS-native personal AI assistant that learns who you are.

**Status:** Pre-alpha. See `docs/superpowers/specs/2026-05-22-yuki-macos-design.md` for the full design and `docs/superpowers/plans/` for implementation plans.

## Requirements

- macOS 12+
- Python 3.12 (managed via `uv python install 3.12`)
- [uv](https://docs.astral.sh/uv/) 0.5+ (`brew install uv`)

## Development

```bash
# install or sync deps
uv sync --all-extras

# run all checks the way CI does
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -v

# auto-format
uv run ruff format .

# add a runtime dep
uv add some-package

# add a dev dep
uv add --dev some-package
```

## Layout

```
yuki/                  # main package; subsystems land here in later plans
tests/                 # pytest tests, mirrors yuki/ structure
.github/workflows/     # CI
pyproject.toml         # deps + tool config (ruff, mypy, pytest)
```

## License

MIT — see `LICENSE`.
