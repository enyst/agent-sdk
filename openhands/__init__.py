################################################################################
# IMPORTANT: this file is NOT part of the repo. It was created by an AI agent to help itself, but you can delete it if you want.
################################################################################

# Ensure monorepo package resolution works when running from the repo root.
# We prefer local package sources (e.g., openhands-sdk/openhands) over the
# umbrella directories under ./openhands to surface full packages with
# __init__.py during imports like `from openhands.sdk import Agent`.
from __future__ import annotations

import sys
from pathlib import Path


_pkg_dir = Path(__file__).resolve().parent
_root = _pkg_dir.parent
_candidates = [
    _root / "openhands-sdk" / "openhands",
    _root / "openhands-tools" / "openhands",
    _root / "openhands-workspace" / "openhands",
    _root / "openhands-agent-server" / "openhands",
]

# Prepend valid candidates to sys.path and openhands.__path__ so subpackages
# (e.g., openhands.sdk) resolve to their implemented packages with __init__.py
for p in reversed([c for c in _candidates if c.exists()]):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
    # Ensure import resolution for subpackages goes through the concrete
    # package dirs (those that contain __init__.py)
    if sp not in __path__:
        __path__.insert(0, sp)
