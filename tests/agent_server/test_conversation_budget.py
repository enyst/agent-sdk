import json

import pytest
from pydantic import ValidationError

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.models import StartConversationRequest, StoredConversation
from openhands.sdk import LLM, Agent
from openhands.sdk.workspace import LocalWorkspace


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_creation_rejects_invalid_budget(budget, tmp_path):
    with pytest.raises(ValidationError, match="max_budget_per_run"):
        StartConversationRequest(
            agent=Agent(llm=LLM(model="gpt-4o"), tools=[]),
            workspace=LocalWorkspace(working_dir=str(tmp_path)),
            max_budget_per_run=budget,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [None, 1.25])
async def test_budget_survives_creation_fork_and_restart(tmp_path, budget):
    conversations_dir = tmp_path / "conversations"
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    request = StartConversationRequest(
        agent=Agent(llm=LLM(model="gpt-4o"), tools=[]),
        workspace=LocalWorkspace(working_dir=str(workspace_dir)),
        max_budget_per_run=budget,
    )
    async with ConversationService(conversations_dir=conversations_dir) as service:
        info, _ = await service.start_conversation(request)
        assert info.max_budget_per_run == budget
        original = await service.get_event_service(info.id)
        assert original is not None
        assert original.get_conversation().max_budget_per_run == budget

        fork = await service.fork_conversation(info.id)
        assert fork is not None
        assert fork.max_budget_per_run == budget
        fork_service = await service.get_event_service(fork.id)
        assert fork_service is not None
        assert fork_service.get_conversation().max_budget_per_run == budget

    for conversation_id in (info.id, fork.id):
        meta_path = conversations_dir / conversation_id.hex / "meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["max_budget_per_run"] == budget
        if budget is None:
            # Old metadata has no budget field.
            del meta["max_budget_per_run"]
            meta_path.write_text(json.dumps(meta))
            assert StoredConversation.model_validate(meta).max_budget_per_run is None

    async with ConversationService(conversations_dir=conversations_dir) as restarted:
        for conversation_id in (info.id, fork.id):
            reloaded = await restarted.get_conversation(conversation_id)
            assert reloaded is not None
            assert reloaded.max_budget_per_run == budget
            event_service = await restarted.get_event_service(conversation_id)
            assert event_service is not None
            assert event_service.get_conversation().max_budget_per_run == budget
