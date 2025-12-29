"""Shared helpers for SDK persistence configuration.

This module intentionally avoids environment-driven behavior for conversation
serialization. Persistence should be deterministic and controlled by the caller
via explicit serialization context.
"""

from __future__ import annotations


INLINE_CONTEXT_KEY = "inline_llm_persistence"
