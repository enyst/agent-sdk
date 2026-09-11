"""Shared fixtures for cross package tests."""

import json
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.persistence import reset_stores
from openhands.sdk import Agent
from openhands.sdk.conversation.request import StartConversationRequest
from openhands.sdk.testing import TestLLM
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def ownership_cipher() -> Cipher:
    return Cipher("conversation-state-ownership-test-key")


@pytest.fixture
def ownership_request(tmp_path: Path) -> StartConversationRequest:
    return StartConversationRequest(
        agent=Agent(
            llm=TestLLM(model="openai/gpt-4o", usage_id="ownership-actor"),
            tools=[],
        ),
        workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
        autotitle=False,
    )


@pytest.fixture
def ownership_service_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ownership_cipher: Cipher
) -> Iterator[Callable[[], ConversationService]]:
    monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / "settings"))
    reset_stores()

    def create_service() -> ConversationService:
        return ConversationService(
            conversations_dir=tmp_path / "conversations",
            cipher=ownership_cipher,
            lease_ttl_seconds=0,
        )

    try:
        yield create_service
    finally:
        reset_stores()


@pytest.fixture
async def ownership_service(
    ownership_service_factory: Callable[[], ConversationService],
) -> AsyncIterator[ConversationService]:
    async with ownership_service_factory() as service:
        yield service


@pytest.fixture
def llm_fixtures_dir():
    """Get the LLM fixtures directory path."""
    return Path(__file__).parent.parent / "fixtures" / "llm_data"


@pytest.fixture
def fncall_raw_logs(llm_fixtures_dir):
    """Load function calling raw logs from real data."""
    logs = []
    log_dir = llm_fixtures_dir / "llm-logs"
    if log_dir.exists():
        for log_file in log_dir.glob("*.json"):
            with open(log_file) as f:
                logs.append(json.load(f))
    return logs


@pytest.fixture
def nonfncall_raw_logs(llm_fixtures_dir):
    """Load non-function calling raw logs from real data."""
    logs = []
    log_dir = llm_fixtures_dir / "nonfncall-llm-logs"
    if log_dir.exists():
        for log_file in log_dir.glob("*.json"):
            with open(log_file) as f:
                logs.append(json.load(f))
    return logs
