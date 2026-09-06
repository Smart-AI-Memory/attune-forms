"""Non-Claude host install surface (attune-ai host-surface-parity D10).

``plugin/skills/forms/SKILL.md`` is the SOURCE; ``.agents/skills/forms/
SKILL.md`` is its projection for agents that read the ``.agents/``
convention (Antigravity, Codex inside a checkout). The README's Codex
and generic-MCP install lines must name the real console script, the
real extra, and the plugin's own ``.mcp.json`` verbatim — a renamed
script or a hand-edited JSON block would instruct users into a 404.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_PYPROJECT = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_agents_skill_mirrors_plugin_skill_byte_for_byte() -> None:
    source = (_ROOT / "plugin" / "skills" / "forms" / "SKILL.md").read_bytes()
    mirror = (_ROOT / ".agents" / "skills" / "forms" / "SKILL.md").read_bytes()
    assert (
        source == mirror
    ), "re-copy plugin/skills/forms/SKILL.md over .agents/skills/forms/SKILL.md"


def test_readme_codex_install_names_real_script_and_extra() -> None:
    assert re.search(r"^attune-forms-mcp\s*=", _PYPROJECT, re.M), "console script renamed"
    assert re.search(r"^mcp\s*=\s*\[", _PYPROJECT, re.M), "[mcp] extra renamed"
    line = "codex mcp add attune-forms -- uvx --from 'attune-forms[mcp]' attune-forms-mcp"
    assert line in _README
    assert "plugin/skills/forms/SKILL.md -o ~/.codex/skills/forms/SKILL.md" in _README


def test_readme_generic_mcp_json_is_the_plugin_mcp_json_verbatim() -> None:
    server = json.loads((_ROOT / "plugin" / ".mcp.json").read_text(encoding="utf-8"))
    server = server["mcpServers"]["attune-forms"]
    blocks = re.findall(r"```json\n(\{\"mcpServers\".*?)\n```", _README, re.S)
    assert blocks, "README lost its generic MCP-client JSON block"
    assert any(
        json.loads(b)["mcpServers"]["attune-forms"] == server for b in blocks
    ), "README's MCP JSON drifted from plugin/.mcp.json"
