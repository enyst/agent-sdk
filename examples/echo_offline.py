"""
Echo-Offline example: minimal Conversation + Agent with no network or LLM calls.

Run:
  uv run python -m examples.echo_offline
"""
from __future__ import annotations

from openhands.core import (
    LLM,
    AgentBase,
    Conversation,
    ConversationCallbackType,
    LLMConfig,
    Message,
    TextContent,
    get_logger,
)
from openhands.core.conversation import ConversationState


logger = get_logger(__name__)


class DummyAgent(AgentBase):
    """A minimal agent that never calls the LLM and finishes in one step."""

    def __init__(self) -> None:
        # Provide an unused LLM instance to satisfy the AgentBase signature
        super().__init__(llm=LLM(LLMConfig(model="gpt-4o-mini")), tools=[])

    def init_state(
        self,
        state: ConversationState,
        initial_user_message: Message | None = None,
        on_event: ConversationCallbackType | None = None,
    ) -> None:
        if initial_user_message is None:
            raise ValueError("initial_user_message required")
        # Add system and user messages
        sys = Message(role="system", content=[TextContent(text="You are a dummy agent.")])
        state.history.messages.append(sys)
        if on_event:
            on_event(sys)
        state.history.messages.append(initial_user_message)
        if on_event:
            on_event(initial_user_message)

    def step(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType | None = None,
    ) -> None:
        # Produce a single assistant message and finish
        reply = Message(role="assistant", content=[TextContent(text="Echo: done")])
        state.history.messages.append(reply)
        if on_event:
            on_event(reply)
        state.agent_finished = True


def main() -> None:
    convo = Conversation(agent=DummyAgent(), callbacks=[lambda e: logger.info(str(e)[:200])])
    convo.send_message(Message(role="user", content=[TextContent(text="Hello")]))
    convo.run()


if __name__ == "__main__":
    main()
