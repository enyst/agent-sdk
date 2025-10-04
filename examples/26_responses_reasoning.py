"""
Example: Responses API path via LiteLLM in a Real Agent Conversation

- Runs a real Agent/Conversation to verify /responses path works
- Demonstrates rendering of Responses reasoning within normal conversation events
"""

from __future__ import annotations

import os

from pydantic import SecretStr

from openhands.sdk import (
    Conversation,
    Event,
    LLMConvertibleEvent,
    get_logger,
)
from openhands.sdk.llm import LLM
from openhands.tools.preset.default import get_default_agent


logger = get_logger(__name__)


def run_agent_conversation(llm: LLM) -> None:
    print("\n=== Agent Conversation using /responses path ===")
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,  # disable browser tools for env simplicity
    )

    llm_messages = []  # collect raw LLM-convertible messages for inspection

    def conversation_callback(event: Event):
        if isinstance(event, LLMConvertibleEvent):
            llm_messages.append(event.to_llm_message())

    conversation = Conversation(
        agent=agent,
        callbacks=[conversation_callback],
        workspace=os.getcwd(),
    )

    # Keep the tasks short for demo purposes
    conversation.send_message("Read the repo and write one fact into FACTS.txt.")
    conversation.run()

    conversation.send_message("Now delete FACTS.txt.")
    conversation.run()

    print("=" * 100)
    print("Conversation finished. Got the following LLM messages:")
    for i, message in enumerate(llm_messages):
        ms = str(message)
        print(f"Message {i}: {ms[:200]}{'...' if len(ms) > 200 else ''}")


def main():
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    assert api_key, "Set LITELLM_API_KEY or OPENAI_API_KEY in your environment."

    model = os.getenv("OPENAI_RESPONSES_MODEL", "openai/gpt-5-mini")
    base_url = os.getenv("LITELLM_BASE_URL", "https://llm-proxy.eval.all-hands.dev")

    llm = LLM(
        model=model,
        api_key=SecretStr(api_key),
        base_url=base_url,
        # Responses-path options
        enable_encrypted_reasoning=True,  # request encrypted reasoning passthrough
        reasoning_effort="high",
        # Logging / behavior tweaks
        log_completions=False,
        drop_params=True,
        service_id="agent",
    )

    # Run Agent + Conversation using /responses routing
    run_agent_conversation(llm)


if __name__ == "__main__":
    main()
