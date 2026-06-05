"""Tests for SOUL.md loading and system prompt snapshot integration.

These tests use golden-file snapshots of the full rendered system prompt.
When the prompt template or SOUL integration changes, the snapshots will
fail and show exactly what changed — run with --snapshot-update to accept.

Loader unit tests verify _load_soul_md edge cases without snapshots.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

from openhands.sdk.agent import Agent
from openhands.sdk.agent.base import _load_soul_md
from openhands.sdk.llm import LLM


SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _make_agent(
    system_prompt_kwargs: dict[str, object] | None = None,
) -> Agent:
    llm = LLM(model="gpt-4o", usage_id="test")
    kwargs: dict[str, object] = {"llm": llm, "tools": []}
    if system_prompt_kwargs is not None:
        kwargs["system_prompt_kwargs"] = system_prompt_kwargs
    return Agent(**kwargs)  # type: ignore[arg-type]


def _read_snapshot(name: str) -> str:
    return (SNAPSHOTS_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Snapshot tests: full system prompt comparison
# ---------------------------------------------------------------------------


def test_system_prompt_default_soul_snapshot(tmp_path: Path) -> None:
    """Full prompt with the built-in default soul matches the snapshot."""
    # Point SOUL.md to a missing file so we always get the default
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(tmp_path / "missing")):
        agent = _make_agent()
        actual = agent.static_system_message
    expected = _read_snapshot("system_prompt_default_soul.txt")
    assert actual == expected, (
        "System prompt with default soul has drifted from snapshot. "
        "If this is intentional, regenerate snapshots:\n"
        '  uv run python -c "from openhands.sdk.agent import Agent; '
        "from openhands.sdk.llm import LLM; "
        "a = Agent(llm=LLM(model='gpt-4o', usage_id='test'), tools=[]); "
        "open('tests/sdk/agent/snapshots/system_prompt_default_soul.txt','w')"
        '.write(a.static_system_message)"'
    )


def test_system_prompt_custom_soul_snapshot(tmp_path: Path) -> None:
    """Full prompt with a custom soul_content matches the snapshot."""
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(tmp_path / "missing")):
        agent = _make_agent(
            system_prompt_kwargs={
                "soul_content": "You are a tiny cat agent with toe beans."
            },
        )
        actual = agent.static_system_message
    expected = _read_snapshot("system_prompt_custom_soul.txt")
    assert actual == expected, (
        "System prompt with custom soul has drifted from snapshot. "
        "If this is intentional, regenerate snapshots:\n"
        '  uv run python -c "from openhands.sdk.agent import Agent; '
        "from openhands.sdk.llm import LLM; "
        "a = Agent(llm=LLM(model='gpt-4o', usage_id='test'), tools=[], "
        "system_prompt_kwargs={'soul_content': "
        "'You are a tiny cat agent with toe beans.'}); "
        "open('tests/sdk/agent/snapshots/system_prompt_custom_soul.txt','w')"
        '.write(a.static_system_message)"'
    )


# ---------------------------------------------------------------------------
# _load_soul_md loader unit tests
# ---------------------------------------------------------------------------


def test_load_soul_md_returns_default_when_missing(tmp_path: Path) -> None:
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(tmp_path / "SOUL.md")):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_default_when_empty(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_default_when_whitespace_only(
    tmp_path: Path,
) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("   \n\n  \n")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert "OpenHands agent" in _load_soul_md()


def test_load_soul_md_returns_content(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("You are a helpful cat agent.")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert _load_soul_md() == "You are a helpful cat agent."


def test_load_soul_md_strips_whitespace(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("\n  You are direct.  \n\n")
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        assert _load_soul_md() == "You are direct."


def test_load_soul_md_preserves_internal_structure(tmp_path: Path) -> None:
    content = textwrap.dedent("""\
        # Identity
        You are smolpaws.

        # Style
        Be direct. Be concise.
    """)
    soul = tmp_path / "SOUL.md"
    soul.write_text(content)
    with patch("openhands.sdk.agent.base._SOUL_PATH", str(soul)):
        result = _load_soul_md()
        assert "# Identity" in result
        assert "# Style" in result
        assert "smolpaws" in result
