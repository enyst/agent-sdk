"""Utilities for reading and writing agent_settings.json."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from openhands.sdk.conversation.persistence_utils import (
    expand_profiles_in_payload,
    prepare_payload_for_persistence,
)
from openhands.sdk.llm.profile_manager import ProfileManager


DEFAULT_AGENT_SETTINGS_PATH = Path.home() / ".openhands" / "agent_settings.json"


def load_agent_settings(
    path: Path | str | None = None,
    *,
    inline: bool | None = None,
    profile_manager: ProfileManager | None = None,
) -> dict[str, Any]:
    """Load agent settings from ``path`` applying profile expansion."""

    settings_path = Path(path) if path is not None else DEFAULT_AGENT_SETTINGS_PATH
    with settings_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return expand_profiles_in_payload(
        payload,
        inline=inline,
        profile_manager=profile_manager,
    )


def save_agent_settings(
    settings: Mapping[str, Any],
    path: Path | str | None = None,
    *,
    inline: bool | None = None,
) -> Path:
    """Persist ``settings`` to disk, returning the destination path."""

    settings_path = Path(path) if path is not None else DEFAULT_AGENT_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = prepare_payload_for_persistence(settings, inline=inline)
    with settings_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return settings_path
