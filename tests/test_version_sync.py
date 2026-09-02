"""The release version and public overview stay synchronized.

pyproject.toml is the source of truth; the plugin manifest and the
marketplace manifest must match it exactly, and the README must present
the current version in its public ``What's new`` heading.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, flags=re.MULTILINE)
    assert match, "pyproject.toml has no version line"
    return match.group(1)


def test_plugin_manifest_matches_pyproject() -> None:
    plugin = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == _pyproject_version()


def test_marketplace_manifest_matches_pyproject() -> None:
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    version = _pyproject_version()
    assert market["metadata"]["version"] == version
    assert all(p["version"] == version for p in market["plugins"])


def test_readme_whats_new_matches_pyproject() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"## What's new in {_pyproject_version()}" in readme
