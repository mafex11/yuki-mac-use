"""Internal smoke-test helper. Will be removed once real code lands."""


def echo(value: str) -> str:
    """Return *value* unchanged. Used to prove the toolchain works."""
    if not isinstance(value, str):
        raise TypeError(f"echo expects str, got {type(value).__name__}")
    return value
