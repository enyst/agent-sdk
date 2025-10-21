"""Helpers for serializing and deserializing persisted conversation data."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from openhands.sdk.llm.llm_registry import LLMRegistry


_INLINE_ENV_VAR = "OPENHANDS_INLINE_CONVERSATIONS"
_FALSE_VALUES = {"0", "false", "no"}


def should_inline_conversations() -> bool:
    """Return True when conversations should be persisted with inline LLM payloads."""

    value = os.getenv(_INLINE_ENV_VAR, "true").strip().lower()
    return value not in _FALSE_VALUES


def compact_llm_profiles(
    data: Mapping[str, Any], *, inline: bool | None = None
) -> dict[str, Any]:
    """Return a mapping ready to be persisted to disk.

    When ``inline`` is False and an LLM dict contains ``profile_id``, the body is
    replaced with ``{"profile_id": <id>}``. Otherwise the structure is left intact.
    """

    inline_mode = should_inline_conversations() if inline is None else inline
    return _compact(data, inline=inline_mode)


def resolve_llm_profiles(
    data: Mapping[str, Any],
    *,
    inline: bool | None = None,
    llm_registry: LLMRegistry | None = None,
) -> dict[str, Any]:
    """Expand stored profile references back into inline LLM dictionaries."""

    inline_mode = should_inline_conversations() if inline is None else inline
    registry = llm_registry or LLMRegistry()
    return _resolve(data, inline=inline_mode, llm_registry=registry)


def _compact(value: Mapping[str, Any] | list[Any] | Any, *, inline: bool) -> Any:
    if isinstance(value, Mapping):
        compacted = {key: _compact(item, inline=inline) for key, item in value.items()}
        if not inline and _is_llm_dict(compacted):
            profile_id = compacted.get("profile_id")
            if profile_id:
                return {"profile_id": profile_id}
        return compacted

    if isinstance(value, list):
        return [_compact(item, inline=inline) for item in value]

    return value


def _resolve(
    value: Mapping[str, Any] | list[Any] | Any,
    *,
    inline: bool,
    llm_registry: LLMRegistry,
) -> Any:
    if isinstance(value, Mapping):
        expanded = {
            key: _resolve(item, inline=inline, llm_registry=llm_registry)
            for key, item in value.items()
        }

        if _is_profile_reference(expanded):
            if inline:
                profile_id = expanded["profile_id"]
                raise ValueError(
                    "Encountered profile reference for LLM while "
                    "OPENHANDS_INLINE_CONVERSATIONS is enabled. "
                    "Inline the profile or set "
                    "OPENHANDS_INLINE_CONVERSATIONS=false."
                )
            profile_id = expanded["profile_id"]
            llm = llm_registry.load_profile(profile_id)
            llm_dict = llm.model_dump(exclude_none=True)
            llm_dict["profile_id"] = profile_id
            return _resolve(llm_dict, inline=inline, llm_registry=llm_registry)

        return expanded

    if isinstance(value, list):
        return [
            _resolve(item, inline=inline, llm_registry=llm_registry) for item in value
        ]

    return value


def _is_llm_dict(value: Mapping[str, Any]) -> bool:
    return "model" in value and ("usage_id" in value or "service_id" in value)


def _is_profile_reference(value: Mapping[str, Any]) -> bool:
    return "profile_id" in value and "model" not in value
