import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    EventType,
    Message,
    TextContent,
    Tool,
    get_logger,
)
from openhands.sdk.conversation import ConversationVisualizer


logger = get_logger(__name__)


def main() -> None:
    # Configure LLM from env, defaulting to a reasoning-capable model
    api_key = os.getenv("LITELLM_API_KEY")
    assert api_key is not None, "LITELLM_API_KEY environment variable is not set."

    model = os.getenv(
        "REASONING_MODEL",
        # DeepSeek Reasoner returns `reasoning_content` via Chat Completions
        "litellm_proxy/deepseek/deepseek-reasoner",
    )
    base_url = os.getenv("LITELLM_BASE_URL", "https://llm-proxy.eval.all-hands.dev")

    llm = LLM(
        model=model,
        base_url=base_url,
        api_key=SecretStr(api_key),
    )

    # No external tools required to view reasoning. Built-ins are auto-added.
    tools: list[Tool] = []

    # Agent and visualizer to display tokens and content nicely
    agent = Agent(llm=llm, tools=tools)
    visualizer = ConversationVisualizer()

    # Track whether we saw reasoning_content in any event
    saw_reasoning: bool = False

    def on_event(event: EventType) -> None:
        nonlocal saw_reasoning
        # Pretty conversation panels (also shows reasoning tokens if available)
        visualizer.on_event(event)

        # Print reasoning_content explicitly if present on the event
        rc = getattr(event, "reasoning_content", None)
        if rc:
            saw_reasoning = True
            print("\n==== reasoning_content (from event) ====")
            print(rc)
            print("=======================================\n")

        # For MessageEvent, the reasoning lives on llm_message
        if hasattr(event, "llm_message"):
            llm_msg = getattr(event, "llm_message")
            msg_rc = getattr(llm_msg, "reasoning_content", None)
            if msg_rc:
                saw_reasoning = True
                print("\n==== reasoning_content (from llm_message) ====")
                print(msg_rc)
                print("============================================\n")

    conversation = Conversation(agent=agent, callbacks=[on_event])

    # Prompt that encourages internal reasoning without requiring tools
    task = os.getenv(
        "REASONING_TASK",
        (
            "Solve this carefully and show your internal reasoning as available: "
            "78*964 + 17. Respond with the final integer answer."
        ),
    )

    conversation.send_message(
        message=Message(role="user", content=[TextContent(text=task)])
    )
    conversation.run()

    if not saw_reasoning:
        print(
            (
                "No reasoning_content surfaced. Try a different model or proxy that "
                "exposes reasoning, e.g. set REASONING_MODEL to one of:\n"
                "  - litellm_proxy/deepseek/deepseek-reasoner (Chat Completions)\n"
                "  - litellm_proxy/openai/o3-2025-04-16 (Responses API;\n"
                "    may not surface reasoning via Chat Completions)\n"
                "Also ensure your LiteLLM proxy supports returning reasoning_content."
            )
        )


if __name__ == "__main__":
    main()
