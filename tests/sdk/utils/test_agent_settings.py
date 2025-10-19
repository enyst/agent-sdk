"""Tests for agent settings helpers."""

from __future__ import annotations

import json

from openhands.sdk.llm import LLM
from openhands.sdk.llm.profile_manager import ProfileManager
from openhands.sdk.utils.agent_settings import load_agent_settings, save_agent_settings


def test_agent_settings_inline_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    settings_path = tmp_path / "agent_settings.json"

    llm = LLM(model="gpt-4o-mini", service_id="agent")
    settings = {"agent": {"llm": llm.model_dump(exclude_none=True)}}

    save_agent_settings(settings, settings_path)

    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored["agent"]["llm"]["model"] == "gpt-4o-mini"

    loaded = load_agent_settings(settings_path)
    assert loaded["agent"]["llm"]["model"] == "gpt-4o-mini"


def test_agent_settings_profile_reference_mode(tmp_path, monkeypatch):
    home_dir = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("OPENHANDS_INLINE_CONVERSATIONS", "false")

    manager = ProfileManager()
    profile_name = "settings-profile"
    manager.save_profile(
        profile_name, LLM(model="litellm_proxy/openai/gpt-5-mini", service_id="agent")
    )

    llm = manager.load_profile(profile_name)
    settings_path = tmp_path / "agent_settings.json"
    settings = {"agent": {"llm": llm.model_dump(exclude_none=True)}}

    save_agent_settings(settings, settings_path)

    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored["agent"]["llm"] == {"profile_id": profile_name}

    loaded = load_agent_settings(settings_path)
    assert loaded["agent"]["llm"]["profile_id"] == profile_name
    assert loaded["agent"]["llm"]["model"] == "litellm_proxy/openai/gpt-5-mini"
