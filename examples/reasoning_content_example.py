#!/usr/bin/env python3
"""
Example demonstrating reasoning content support in OpenHands Agent SDK.

This example shows how to:
1. Enable/disable reasoning content extraction
2. Access reasoning content from different providers
3. Handle reasoning content in agent workflows

Reasoning models supported:
- OpenAI o1-preview, o1-mini (reasoning_content field)
- Anthropic Claude with thinking (thinking_blocks field)
- DeepSeek R1 (reasoning_content field)
"""

import os

from pydantic import SecretStr

from openhands.sdk.llm import LLM
from openhands.sdk.llm.message import Message


def example_with_reasoning_enabled():
    """Example showing reasoning content extraction enabled (default)."""
    print("=== Example 1: Reasoning Content Enabled ===")

    # Create LLM with reasoning content enabled (default behavior)
    llm = LLM(
        model="o1-preview",  # OpenAI reasoning model
        api_key=SecretStr(os.getenv("OPENAI_API_KEY", "your-api-key")),
        expose_reasoning=True,  # Default: True
    )

    messages = [
        {"role": "user", "content": "Solve this step by step: What is 15 * 23?"}
    ]

    # Make completion call
    response = llm.completion(messages)

    # Convert to OpenHands Message to access reasoning content
    if response.choices:
        message = Message.from_litellm_message(response.choices[0].message)  # type: ignore

        from openhands.sdk.llm.message import TextContent

        content_text = (
            message.content[0].text
            if message.content and isinstance(message.content[0], TextContent)
            else "No content"
        )
        print(f"Assistant response: {content_text}")

        # Access reasoning content if available
        if message.reasoning_content:
            print(f"Reasoning process: {message.reasoning_content[:200]}...")
        else:
            print("No reasoning content available")

        # For Anthropic models, check thinking_blocks
        if message.thinking_blocks:
            print(f"Thinking blocks: {len(message.thinking_blocks)} blocks")
            for i, block in enumerate(message.thinking_blocks[:2]):  # Show first 2
                print(f"  Block {i + 1}: {block.get('thinking', 'N/A')[:100]}...")


def example_with_reasoning_disabled():
    """Example showing reasoning content extraction disabled."""
    print("\n=== Example 2: Reasoning Content Disabled ===")

    # Create LLM with reasoning content disabled
    llm = LLM(
        model="o1-preview",
        api_key=SecretStr(os.getenv("OPENAI_API_KEY", "your-api-key")),
        expose_reasoning=False,  # Disable reasoning content
    )

    messages = [{"role": "user", "content": "What is the capital of France?"}]

    response = llm.completion(messages)

    if response.choices:
        message = Message.from_litellm_message(response.choices[0].message)  # type: ignore

        from openhands.sdk.llm.message import TextContent

        content_text = (
            message.content[0].text
            if message.content and isinstance(message.content[0], TextContent)
            else "No content"
        )
        print(f"Assistant response: {content_text}")
        print(f"Reasoning content: {message.reasoning_content}")  # Should be None
        print(f"Thinking blocks: {message.thinking_blocks}")  # Should be None


def example_with_anthropic_thinking():
    """Example showing Anthropic Claude thinking blocks."""
    print("\n=== Example 3: Anthropic Claude Thinking ===")

    llm = LLM(
        model="claude-3-5-sonnet-20241022",
        api_key=SecretStr(os.getenv("ANTHROPIC_API_KEY", "your-api-key")),
        expose_reasoning=True,
    )

    messages = [
        {
            "role": "user",
            "content": (
                "Think through this problem: How would you design a simple cache?"
            ),
        }
    ]

    response = llm.completion(messages)

    if response.choices:
        message = Message.from_litellm_message(response.choices[0].message)  # type: ignore

        from openhands.sdk.llm.message import TextContent

        content_text = (
            message.content[0].text[:200]
            if message.content and isinstance(message.content[0], TextContent)
            else "No content"
        )
        print(f"Assistant response: {content_text}...")

        # Anthropic uses thinking_blocks instead of reasoning_content
        if message.thinking_blocks:
            print(f"Found {len(message.thinking_blocks)} thinking blocks")
            for i, block in enumerate(message.thinking_blocks):
                thinking_text = block.get("thinking", "")
                print(f"  Thinking block {i + 1}: {thinking_text[:150]}...")
        else:
            print("No thinking blocks available")


def example_message_serialization():
    """Example showing how reasoning content is preserved in serialization."""
    print("\n=== Example 4: Message Serialization ===")

    # Create a message with reasoning content
    from openhands.sdk.llm.message import TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="The answer is 345.")],
        reasoning_content="Let me calculate 15 * 23 step by step...",
        thinking_blocks=[
            {"type": "thinking", "thinking": "First, I'll break this down..."}
        ],
    )

    # Serialize to dict
    message_dict = message.model_dump()
    print("Serialized message includes:")
    print(f"  - content: {message_dict.get('content')}")
    print(f"  - reasoning_content: {message_dict.get('reasoning_content')}")
    print(f"  - thinking_blocks: {message_dict.get('thinking_blocks')}")

    # Deserialize back
    restored_message = Message.model_validate(message_dict)
    print(f"Restored reasoning content: {restored_message.reasoning_content}")


def main():
    """Run all examples."""
    print("OpenHands Agent SDK - Reasoning Content Examples")
    print("=" * 50)

    # Note: These examples require actual API keys to run
    # For demonstration purposes, they show the structure

    try:
        example_with_reasoning_enabled()
        example_with_reasoning_disabled()
        example_with_anthropic_thinking()
        example_message_serialization()

    except Exception as e:
        print(f"Note: Examples require valid API keys. Error: {e}")
        print("The code structure above shows how to use reasoning content.")


if __name__ == "__main__":
    main()
