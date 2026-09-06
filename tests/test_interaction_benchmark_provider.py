"""Tests for provider-neutral baseline actor execution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from benchmarks.provider import (
    BaselineActor,
    CodexCliProvider,
    ProviderExecutionError,
    ProviderReply,
)
from benchmarks.runner import ActorScenario, EventKind, EventTrust


class StubProvider:
    provider_id = "stub"
    provider_version = "1"

    def __init__(self) -> None:
        self.messages = ()

    def complete(self, messages):
        self.messages = tuple(messages)
        return ProviderReply(
            text="I need the target path before proceeding.",
            tokens_input=11,
            tokens_output=7,
            elapsed_ms=9,
        )


def test_baseline_actor_exposes_only_actor_scenario_and_records_provider_telemetry() -> None:
    provider = StubProvider()
    actor = BaselineActor(provider)
    scenario = ActorScenario(
        id="example",
        family="ambiguous_requirements",
        task="Audit the project.",
    )

    output = actor(scenario, "free_form")

    assert output.events[0].kind is EventKind.MESSAGE
    assert output.events[0].trust is EventTrust.ACTOR_ASSERTED
    assert output.events[0].source == "stub"
    assert output.tokens_input == 11
    assert output.tokens_output == 7
    assert output.elapsed_ms == 9
    serialized_messages = repr(provider.messages)
    assert "Audit the project." in serialized_messages
    assert "seeded_risk" not in serialized_messages


def test_sequential_condition_adds_only_interaction_constraint() -> None:
    provider = StubProvider()
    actor = BaselineActor(provider)
    scenario = ActorScenario(
        id="example",
        family="ambiguous_requirements",
        task="Audit the project.",
    )

    actor(scenario, "sequential_clarification")

    system = provider.messages[0]["content"]
    assert "at most one unresolved decision" in system
    assert scenario.task == provider.messages[1]["content"]


def test_codex_cli_command_pins_the_ratified_execution_contract(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    provider = CodexCliProvider(executable=executable, working_directory=tmp_path)

    command = provider.command()

    assert command[0] == str(executable)
    assert command[1:4] == ("--ask-for-approval", "never", "exec")
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--strict-config" in command
    assert ("--sandbox", "read-only") == command[command.index("--sandbox") :][:2]
    assert command.index("--ask-for-approval") < command.index("exec")
    assert "project_doc_max_bytes=0" in command
    assert command[-1] == "-"


def test_codex_prompt_is_deterministic_and_retains_role_boundaries() -> None:
    messages = (
        {"role": "system", "content": "System instruction."},
        {"role": "user", "content": "User task."},
    )

    first = CodexCliProvider.compile_prompt(messages)
    second = CodexCliProvider.compile_prompt(messages)

    assert first == second
    assert '"role":"system","content":"System instruction."' in first
    assert '"role":"user","content":"User task."' in first
    assert "Do not inspect files, call tools, or perform external actions." in first


def test_codex_local_contract_requires_empty_workspace(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    with pytest.raises(ValueError, match="must be empty"):
        provider.complete(({"role": "user", "content": "Task."},))


def test_codex_local_contract_requires_pinned_cli_version(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, "codex-cli 0.145.0\n", ""
        ),
    )
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    with pytest.raises(ValueError, match="codex-cli 0.144.6"):
        provider.complete(({"role": "user", "content": "Task."},))


def test_codex_local_contract_rejects_unparseable_command(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(command, **kwargs):
        if command == (str(executable), "--version"):
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.6\n", "")
        return subprocess.CompletedProcess(command, 2, "", "unexpected argument")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    with pytest.raises(ValueError, match="rejected the pinned command"):
        provider.complete(({"role": "user", "content": "Task."},))


def test_codex_jsonl_parser_extracts_final_message_and_usage() -> None:
    stdout = "\n".join(
        (
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item-1", "type": "agent_message", "text": "Reply."},
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 21, "output_tokens": 8},
                }
            ),
        )
    )

    events, message, usage = CodexCliProvider._parse_events(stdout)

    assert len(events) == 3
    assert message == "Reply."
    assert usage == {"input_tokens": 21, "output_tokens": 8}


def test_codex_jsonl_parser_rejects_tool_items() -> None:
    stdout = json.dumps(
        {
            "type": "item.started",
            "item": {"id": "item-1", "type": "command_execution", "command": "pwd"},
        }
    )

    with pytest.raises(ValueError, match="disallowed non-text item"):
        CodexCliProvider._parse_events(stdout)


def test_codex_complete_retains_raw_event_stream(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == (str(executable), "--version"):
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.6\n", "")
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, "Run Codex non-interactively", "")
        stdout = "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item-1",
                            "type": "agent_message",
                            "text": "Reply.",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 21, "output_tokens": 8},
                    }
                ),
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout, "provider stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    reply = provider.complete(({"role": "user", "content": "Task."},))

    assert reply.text == "Reply."
    assert reply.tokens_input == 21
    assert reply.tokens_output == 8
    assert reply.metadata["stderr"] == "provider stderr"
    assert reply.metadata["stdout_events"][-1]["type"] == "turn.completed"
    assert calls[2][1]["input"] == reply.metadata["compiled_prompt"]


def test_codex_nonzero_exit_raises_with_retainable_metadata(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(command, **kwargs):
        if command == (str(executable), "--version"):
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.6\n", "")
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, "Run Codex non-interactively", "")
        return subprocess.CompletedProcess(command, 9, "partial stdout", "provider failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    with pytest.raises(ProviderExecutionError) as caught:
        provider.complete(({"role": "user", "content": "Task."},))

    assert caught.value.metadata["exit_code"] == 9
    assert caught.value.metadata["stdout"] == "partial stdout"
    assert caught.value.metadata["stderr"] == "provider failed"


def test_codex_timeout_normalizes_byte_streams(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fake_run(command, **kwargs):
        if command == (str(executable), "--version"):
            return subprocess.CompletedProcess(command, 0, "codex-cli 0.144.6\n", "")
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, "Run Codex non-interactively", "")
        raise subprocess.TimeoutExpired(command, 1, output=b"partial", stderr=b"late")

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = CodexCliProvider(executable=executable, working_directory=workspace)

    with pytest.raises(ProviderExecutionError) as caught:
        provider.complete(({"role": "user", "content": "Task."},))

    assert caught.value.metadata["stdout"] == "partial"
    assert caught.value.metadata["stderr"] == "late"
