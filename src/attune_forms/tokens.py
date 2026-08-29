"""Provider-neutral semantic design tokens.

The JSON artifact is the cross-repository source consumed by
``attune-forms`` and projected into host applications. Python loads it
through package resources so wheels and editable installs behave the
same way.
"""

from __future__ import annotations

import json
from importlib.resources import files
from types import MappingProxyType
from typing import Any


def _load_tokens() -> dict[str, Any]:
    source = files("attune_forms").joinpath("semantic_tokens.json")
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("version") != 1:
        raise ValueError("unsupported semantic token version")
    return data


SEMANTIC_TOKENS = MappingProxyType(_load_tokens())


def token(path: str) -> str:
    """Return one scalar token from a dot-separated path.

    Raises:
        KeyError: If the path is absent or resolves to a mapping.
    """
    value: Any = SEMANTIC_TOKENS
    for part in path.split("."):
        value = value[part]
    if isinstance(value, dict):
        raise KeyError(f"token path resolves to a mapping: {path}")
    return str(value)
