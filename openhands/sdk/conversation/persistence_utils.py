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
    return _transform(data, inline=inline_mode, deserialize=False, llm_registry=None)


def resolve_llm_profiles(
    data: Mapping[str, Any],
    *,
    inline: bool | None = None,
    llm_registry: LLMRegistry | None = None,
) -> dict[str, Any]:
    """Expand stored profile references back into inline LLM dictionaries."""

    inline_mode = should_inline_conversations() if inline is None else inline
    registry = llm_registry or LLMRegistry()
    return _transform(data, inline=inline_mode, deserialize=True, llm_registry=registry)


def _transform(
    data: Mapping[str, Any] | list[Any],
    *,
    inline: bool,
    deserialize: bool,
    llm_registry: LLMRegistry | None,
) -> Any:
    if isinstance(data, Mapping):
        expanded = {
            key: _transform(
                value,
                inline=inline,
                deserialize=deserialize,
                llm_registry=llm_registry,
            )
            for key, value in data.items()
        }

        if deserialize:
            if _is_profile_reference(expanded):
                if inline:
                    profile_id = expanded["profile_id"]
                    raise ValueError(
                        "Encountered profile reference for LLM while "
                        "OPENHANDS_INLINE_CONVERSATIONS is enabled. "
                        "Inline the profile or set "
                        "OPENHANDS_INLINE_CONVERSATIONS=false."
                    )
                assert llm_registry is not None
                profile_id = expanded["profile_id"]
                llm = llm_registry.load_profile(profile_id)
                llm_dict = llm.model_dump(exclude_none=True)
                llm_dict["profile_id"] = profile_id
                return _transform(
                    llm_dict,
                    inline=inline,
                    deserialize=True,
                    llm_registry=llm_registry,
                )
        else:
            if not inline and _is_llm_dict(expanded):
                profile_id = expanded.get("profile_id")
                if profile_id:
                    return {"profile_id": profile_id}
        return expanded

    if isinstance(data, list):
        return [
            _transform(
                item,
                inline=inline,
                deserialize=deserialize,
                llm_registry=llm_registry,
            )
            for item in data
        ]

    return data


def _is_llm_dict(value: Mapping[str, Any]) -> bool:
    return "model" in value and "service_id" in value


def _is_profile_reference(value: Mapping[str, Any]) -> bool:
    return "profile_id" in value and "model" not in value
