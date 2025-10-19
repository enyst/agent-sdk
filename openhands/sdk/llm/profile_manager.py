from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_registry import LLMRegistry


logger = logging.getLogger(__name__)

_SECRET_FIELDS: tuple[str, ...] = (
    "api_key",
    "aws_access_key_id",
    "aws_secret_access_key",
)


class ProfileManager:
    """Manage LLM profile files on disk.

    Profiles are stored as JSON files using the existing LLM schema. By default
    they live under ``~/.openhands/llm-profiles/<name>.json``.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            self.base_dir = Path.home() / ".openhands" / "llm-profiles"
        else:
            self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[str]:
        return sorted([path.stem for path in self.base_dir.glob("*.json")])

    def get_profile_path(self, name: str) -> Path:
        return self.base_dir / f"{name}.json"

    def load_profile(self, name: str) -> LLM:
        path = self.get_profile_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {name} -> {path}")
        return self._load_profile_from_path(path, name)

    def save_profile(self, name: str, llm: LLM, include_secrets: bool = False) -> Path:
        path = self.get_profile_path(name)
        data = llm.model_dump(exclude_none=True)
        data["profile_id"] = name
        if not include_secrets:
            for secret_field in _SECRET_FIELDS:
                data.pop(secret_field, None)
        else:
            for secret_field in _SECRET_FIELDS:
                value = data.get(secret_field)
                if isinstance(value, SecretStr):
                    data[secret_field] = value.get_secret_value()
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        logger.info("Saved profile %s -> %s", name, path)
        return path

    def register_all(self, registry: LLMRegistry) -> None:
        for name in self.list_profiles():
            try:
                llm = self.load_profile(name)
            except Exception as exc:  # noqa: BLE001 - log and continue
                logger.warning("Failed to load profile %s: %s", name, exc)
                continue
            try:
                registry.add(llm)
            except Exception as exc:  # noqa: BLE001 - registry enforces its own invariants
                logger.info("Skipping profile %s: registry.add failed: %s", name, exc)

    def validate_profile(self, data: Mapping[str, Any]) -> tuple[bool, list[str]]:
        try:
            LLM.model_validate(dict(data))
        except ValidationError as exc:
            messages: list[str] = []
            for error in exc.errors():
                loc = ".".join(str(piece) for piece in error.get("loc", ()))
                if loc:
                    messages.append(f"{loc}: {error.get('msg')}")
                else:
                    messages.append(error.get("msg", "Unknown validation error"))
            return False, messages
        return True, []

    def _load_profile_from_path(self, path: Path, name: str) -> LLM:
        llm = LLM.load_from_json(str(path))
        if llm.profile_id != name:
            llm = llm.model_copy(update={"profile_id": name})
        return llm
