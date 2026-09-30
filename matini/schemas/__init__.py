"""Schema modules, resolved on first use (same lazy pattern as sindhu)."""

import importlib

__all__ = ["assessment", "bases", "conversations", "llms"]


def __getattr__(name: str):
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
