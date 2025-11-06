# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
# Tests for LocalConversation.close robustness

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM


class NoInitAgent(AgentBase):
    def init_state(self, state, on_event):  # type: ignore[override]
        # Intentionally skip initialization so tools_map would raise
        return None

    def step(self, conversation, on_event):  # type: ignore[override]
        return None


def test_close_handles_uninitialized_agent(tmp_path):
    agent = NoInitAgent(llm=LLM(model="gpt-4o-mini", usage_id="test"), tools=[])
    conv = LocalConversation(agent=agent, workspace=str(tmp_path), visualize=False)

    # LocalConversation.__init__ will call our overridden init_state which does nothing
    # Close should not raise even though tools_map would normally error
    conv.close()  # Should not raise
