"""Tests for SOUL.md loading and system prompt integration."""

import textwrap
from pathlib import Path
from unittest.mock import patch

from openhands.sdk.agent.base import _load_soul_md


def test_load_soul_md_returns_default_when_missing(tmp_path: Path) -> None:
    missing = str(tmp_path / "SOUL.md")
    with patch("openhands.sdk.agent.base._SOUL_PATH", missing):
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


def test_soul_content_replaces_default_in_prompt() -> None:
    """When soul_content is provided, it appears in the SOUL block."""
    from openhands.sdk.agent import Agent
    from openhands.sdk.llm import LLM

    llm = LLM(model="gpt-4o", usage_id="test-llm")
    agent = Agent(
        llm=llm,
        tools=[],
        system_prompt_kwargs={"soul_content": "You are a tiny cat agent."},
    )
    message = agent.static_system_message
    assert "<SOUL>" in message
    assert "You are a tiny cat agent." in message
    assert "</SOUL>" in message


def test_default_soul_in_prompt() -> None:
    """Without a SOUL.md file, the default identity appears."""
    from openhands.sdk.agent import Agent
    from openhands.sdk.llm import LLM

    llm = LLM(model="gpt-4o", usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    message = agent.static_system_message
    assert "<SOUL>" in message
    assert "OpenHands agent" in message
