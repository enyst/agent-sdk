"""Behavioral regressions for state ownership in SDK PR #4813.

These are ordinary assertions, including the five regressions that must fail
until the implementation is fixed. All inference uses TestLLM.
"""

import asyncio
import json
from collections.abc import Callable
from contextlib import AsyncExitStack, closing
from pathlib import Path
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest
from acp.schema import AgentMessageChunk, TextContentBlock
from pydantic import SecretStr

from openhands.agent_server.conversation_service import ConversationService
from openhands.sdk import LLM, Agent
from openhands.sdk.agent import ACPAgent
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.request import StartConversationRequest
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.llm import LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.secret import StaticSecret
from openhands.sdk.security import (
    AlwaysConfirm,
    LLMSecurityAnalyzer,
    NeverConfirm,
    SecurityRisk,
    ToolShieldLLMSecurityAnalyzer,
)
from openhands.sdk.testing import TestLLM
from openhands.sdk.utils.async_executor import AsyncExecutor
from openhands.sdk.utils.cipher import Cipher
from openhands.tools.terminal import TerminalAction


def _guardrail(key: str) -> ToolShieldLLMSecurityAnalyzer:
    return ToolShieldLLMSecurityAnalyzer(
        llm=TestLLM(
            model="openai/gpt-4o",
            usage_id="ownership-guardrail",
            api_key=SecretStr(key),
        )
    )


def _action(command: str) -> ActionEvent:
    return ActionEvent(
        thought=[],
        action=TerminalAction(command=command),
        tool_name="terminal",
        tool_call_id="ownership-call",
        tool_call=MessageToolCall(
            id="ownership-call",
            name="terminal",
            arguments=json.dumps({"command": command}),
            origin="completion",
        ),
        llm_response_id="ownership-response",
    )


def _run_reply(conversation: LocalConversation, reply: str) -> None:
    # Serialized LLM config does not retain TestLLM's private response queue.
    conversation.switch_llm(
        TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text=reply)])],
            model="openai/gpt-4o",
            usage_id=conversation.agent.llm.usage_id,
        )
    )
    conversation.send_message("Continue the conversation.")
    conversation.run()
    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED
    assert any(
        isinstance(event, MessageEvent)
        and event.source == "agent"
        and any(
            isinstance(content, TextContent) and content.text == reply
            for content in event.llm_message.content
        )
        for event in conversation.state.events
    )


async def test_acp_stream_masks_secrets_added_after_start(tmp_path: Path) -> None:
    agent = ACPAgent(acp_command=["stub-acp-server"], acp_file_secrets=[])
    with closing(
        LocalConversation(agent=agent, workspace=tmp_path, visualizer=None)
    ) as conv:
        # Run the real bridge setup, replacing only the subprocess handshake.
        executor = MagicMock(spec=AsyncExecutor)
        executor.run_async.return_value = ("session", "stub", "1", None, None, False)
        agent._executor = executor
        agent._start_acp_server(conv._state)
        client = agent._client
        assert client is not None
        chunks: list[str] = []
        client.on_token = chunks.append

        conv.update_secrets({"NEW_TOKEN": "new-token-added-after-start"})
        await client.session_update(
            "session",
            AgentMessageChunk(
                session_update="agent_message_chunk",
                content=TextContentBlock(
                    type="text", text="token=new-token-added-after-start"
                ),
            ),
        )

        assert chunks == ["token=<secret-hidden>"]


async def test_server_fork_preserves_request_secrets(
    ownership_service: ConversationService,
    ownership_request: StartConversationRequest,
) -> None:
    request = ownership_request.model_copy(
        update={"secrets": {"TOKEN": StaticSecret(value=SecretStr("fork-token"))}}
    )
    source_info, _ = await ownership_service.start_conversation(request)
    fork_info = await ownership_service.fork_conversation(source_info.id)
    assert fork_info is not None
    fork_service = await ownership_service.get_event_service(fork_info.id)
    assert fork_service is not None
    fork = fork_service.get_conversation()
    assert fork.state.secret_registry.get_secret_value("TOKEN") == "fork-token"

    source_service = await ownership_service.get_event_service(source_info.id)
    assert source_service is not None
    await source_service.update_secrets({"TOKEN": "parent-only-update"})
    assert fork.state.secret_registry.get_secret_value("TOKEN") == "fork-token"
    await ownership_service._evict_idle_conversations(ttl_seconds=0)
    restored_service = await ownership_service.get_event_service(fork_info.id)
    assert restored_service is not None
    restored = restored_service.get_conversation()
    assert restored.state.secret_registry.get_secret_value("TOKEN") == "fork-token"


async def test_server_fork_preserves_guardrail_credentials(
    ownership_service: ConversationService,
    ownership_request: StartConversationRequest,
) -> None:
    request = ownership_request.model_copy(
        update={"security_analyzer": _guardrail("fork-guardrail-key")}
    )
    source_info, _ = await ownership_service.start_conversation(request)
    fork_info = await ownership_service.fork_conversation(source_info.id)
    assert fork_info is not None
    fork_service = await ownership_service.get_event_service(fork_info.id)
    assert fork_service is not None
    analyzer = fork_service.get_conversation().state.security_analyzer

    assert isinstance(analyzer, ToolShieldLLMSecurityAnalyzer)
    assert analyzer.llm.api_key == SecretStr("fork-guardrail-key")


async def test_encrypted_start_decrypts_guardrail_credentials(
    ownership_service: ConversationService,
    ownership_request: StartConversationRequest,
    ownership_cipher: Cipher,
) -> None:
    encrypted = ownership_cipher.encrypt(SecretStr("encrypted-guardrail-key"))
    assert encrypted is not None
    request = ownership_request.model_copy(
        update={
            "security_analyzer": _guardrail(encrypted),
            "secrets_encrypted": True,
        }
    )
    info, _ = await ownership_service.start_conversation(request)
    event_service = await ownership_service.get_event_service(info.id)
    assert event_service is not None
    analyzer = event_service.get_conversation().state.security_analyzer

    assert isinstance(analyzer, ToolShieldLLMSecurityAnalyzer)
    assert analyzer.llm.api_key == SecretStr("encrypted-guardrail-key"), (
        "The guardrail credential must be decrypted before the first run"
    )


def test_local_fork_keeps_guardrail_history_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[list[Message]] = []
    scripted_guardrail = TestLLM.from_messages(
        [Message(role="assistant", content=[TextContent(text="RISK: LOW")])] * 2
    )

    def judge(self: LLM, messages: list[Message], **kwargs: Any) -> LLMResponse:
        prompts.append(messages)
        return scripted_guardrail.completion(messages, **kwargs)

    # A fork may reconstruct an ordinary LLM from the serialized configuration.
    monkeypatch.setattr(LLM, "completion", judge)
    analyzer = ToolShieldLLMSecurityAnalyzer(
        llm=LLM(model="openai/gpt-4o", usage_id="guardrail-history")
    )
    agent = Agent(
        llm=TestLLM(model="openai/gpt-4o", usage_id="ownership-actor"), tools=[]
    )
    with closing(
        LocalConversation(agent=agent, workspace=tmp_path, visualizer=None)
    ) as source:
        source.set_security_analyzer(analyzer)
        with closing(source.fork()) as fork:
            fork_analyzer = fork.state.security_analyzer
            assert isinstance(fork_analyzer, ToolShieldLLMSecurityAnalyzer)
            assert (
                fork_analyzer.security_risk(_action("echo FORK_ONLY_ACTION"))
                == SecurityRisk.LOW
            )
            assert (
                analyzer.security_risk(_action("echo SOURCE_ONLY_ACTION"))
                == SecurityRisk.LOW
            )

    assert len(prompts) == 2
    source_prompt = "\n".join(
        content.text
        for message in prompts[-1]
        for content in message.content
        if isinstance(content, TextContent)
    )
    assert "SOURCE_ONLY_ACTION" in source_prompt
    assert "FORK_ONLY_ACTION" not in source_prompt


@pytest.mark.parametrize("restore_mode", ["eviction", "restart"])
async def test_mutations_survive_restore_and_conversation_continues(
    ownership_service_factory: Callable[[], ConversationService],
    ownership_request: StartConversationRequest,
    ownership_cipher: Cipher,
    restore_mode: Literal["eviction", "restart"],
) -> None:
    request = ownership_request.model_copy(
        update={"secrets": {"TOKEN": StaticSecret(value=SecretStr("initial-token"))}}
    )
    async with AsyncExitStack() as stack:
        service = await stack.enter_async_context(ownership_service_factory())
        info, _ = await service.start_conversation(request)
        original_service = await service.get_event_service(info.id)
        assert original_service is not None
        original = original_service.get_conversation()
        await asyncio.to_thread(_run_reply, original, "before restore")
        original_events = {event.id for event in original.state.events}

        await original_service.set_confirmation_policy(AlwaysConfirm())
        await original_service.set_security_analyzer(LLMSecurityAnalyzer())
        await original_service.update_secrets(
            {"TOKEN": "rotated-token", "ADDED": "added-token"}
        )
        # Check durability before close or any later mutation can save the registry.
        state_path = service.conversations_dir / info.id.hex / "base_state.json"
        serialized = state_path.read_text()
        saved = ConversationState.model_validate_json(
            serialized, context={"cipher": ownership_cipher}
        )
        assert saved.secret_registry.get_secret_value("TOKEN") == "rotated-token"
        assert "rotated-token" not in serialized
        assert "added-token" not in serialized

        if restore_mode == "restart":
            await stack.aclose()
            service = await stack.enter_async_context(ownership_service_factory())
        else:
            await service._evict_idle_conversations(ttl_seconds=0)
        assert not original_service.is_open()

        restored_service = await service.get_event_service(info.id)
        assert restored_service is not None
        restored = restored_service.get_conversation()
        assert isinstance(restored.state.confirmation_policy, AlwaysConfirm)
        assert isinstance(restored.state.security_analyzer, LLMSecurityAnalyzer)
        assert (
            restored.state.secret_registry.get_secret_value("TOKEN") == "rotated-token"
        )
        assert restored.state.secret_registry.get_secret_value("ADDED") == "added-token"
        assert original_events <= {event.id for event in restored.state.events}
        await asyncio.to_thread(_run_reply, restored, "after restore")


async def test_removed_analyzer_and_relaxed_policy_survive_restart(
    ownership_service_factory: Callable[[], ConversationService],
    ownership_request: StartConversationRequest,
) -> None:
    request = ownership_request.model_copy(
        update={
            "confirmation_policy": AlwaysConfirm(),
            "security_analyzer": LLMSecurityAnalyzer(),
        }
    )
    async with ownership_service_factory() as service:
        info, _ = await service.start_conversation(request)
        event_service = await service.get_event_service(info.id)
        assert event_service is not None
        await event_service.set_confirmation_policy(NeverConfirm())
        await event_service.set_security_analyzer(None)

    async with ownership_service_factory() as restarted:
        restored_service = await restarted.get_event_service(info.id)
        assert restored_service is not None
        restored = restored_service.get_conversation()
        assert isinstance(restored.state.confirmation_policy, NeverConfirm)
        assert restored.state.security_analyzer is None
        await asyncio.to_thread(_run_reply, restored, "after removing analyzer")


async def test_legacy_metadata_cannot_override_restored_state(
    ownership_service_factory: Callable[[], ConversationService],
    ownership_request: StartConversationRequest,
    ownership_cipher: Cipher,
) -> None:
    async with ownership_service_factory() as service:
        info, _ = await service.start_conversation(ownership_request)
        event_service = await service.get_event_service(info.id)
        assert event_service is not None
        await event_service.set_confirmation_policy(AlwaysConfirm())
        await event_service.set_security_analyzer(LLMSecurityAnalyzer())
        await event_service.update_secrets({"TOKEN": "canonical-token"})
        meta_path = service.conversations_dir / info.id.hex / "meta.json"

    meta = json.loads(meta_path.read_text())
    meta.update(
        confirmation_policy={"kind": "NeverConfirm"},
        security_analyzer=None,
        secrets={
            "TOKEN": StaticSecret(value=SecretStr("stale-metadata-token")).model_dump(
                mode="json", context={"cipher": ownership_cipher}
            )
        },
        secrets_encrypted=False,
    )
    meta_path.write_text(json.dumps(meta))

    async with ownership_service_factory() as restarted:
        restored_service = await restarted.get_event_service(info.id)
        assert restored_service is not None
        restored = restored_service.get_conversation()
        assert isinstance(restored.state.confirmation_policy, AlwaysConfirm)
        assert isinstance(restored.state.security_analyzer, LLMSecurityAnalyzer)
        assert (
            restored.state.secret_registry.get_secret_value("TOKEN")
            == "canonical-token"
        )
        await asyncio.to_thread(_run_reply, restored, "after legacy metadata")


async def test_encrypted_request_secrets_survive_restart(
    ownership_service_factory: Callable[[], ConversationService],
    ownership_request: StartConversationRequest,
    ownership_cipher: Cipher,
) -> None:
    encrypted = ownership_cipher.encrypt(SecretStr("encrypted-request-token"))
    assert encrypted is not None
    request = ownership_request.model_copy(
        update={
            "secrets": {"TOKEN": StaticSecret(value=SecretStr(encrypted))},
            "secrets_encrypted": True,
        }
    )
    async with ownership_service_factory() as service:
        info, _ = await service.start_conversation(request)

    async with ownership_service_factory() as restarted:
        restored_service = await restarted.get_event_service(info.id)
        assert restored_service is not None
        restored = restored_service.get_conversation()
        assert (
            restored.state.secret_registry.get_secret_value("TOKEN")
            == "encrypted-request-token"
        )
