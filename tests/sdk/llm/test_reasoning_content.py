"""Tests for reasoning content support in LLM and Message classes."""

from unittest.mock import patch

from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage


def create_mock_response(content: str = "Test response", response_id: str = "test-id"):
    """Helper function to create properly structured mock responses."""
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(
                    content=content,
                    role="assistant",
                ),
            )
        ],
        created=1234567890,
        model="claude-sonnet-4-20250514",
        object="chat.completion",
        usage=Usage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


def test_message_with_reasoning_content():
    """Test Message with reasoning content fields."""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="The answer is 42.")],
        reasoning_content="Let me think about this step by step...",
        thinking_blocks=[
            {
                "type": "thinking",
                "thinking": "The user is asking about the meaning of life.",
                "signature": "abc123",
            }
        ],
    )

    assert message.reasoning_content == "Let me think about this step by step..."
    assert message.thinking_blocks is not None
    assert len(message.thinking_blocks) == 1
    assert message.thinking_blocks[0]["type"] == "thinking"


def test_message_without_reasoning_content():
    """Test Message without reasoning content (default behavior)."""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(role="assistant", content=[TextContent(text="The answer is 42.")])

    assert message.reasoning_content is None
    assert message.thinking_blocks is None


def test_message_from_litellm_message_with_reasoning():
    """Test Message.from_litellm_message with reasoning content."""
    from openhands.sdk.llm.message import Message

    # Create a mock LiteLLM message with reasoning content
    litellm_message = LiteLLMMessage(role="assistant", content="The answer is 42.")
    # Add reasoning content as attributes
    litellm_message.reasoning_content = "Let me think about this..."
    litellm_message.thinking_blocks = [
        {
            "type": "thinking",
            "thinking": "The user is asking about math.",
            "signature": "def456",
        }
    ]

    message = Message.from_litellm_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    from openhands.sdk.llm.message import TextContent

    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."
    assert message.reasoning_content == "Let me think about this..."
    assert message.thinking_blocks is not None
    assert len(message.thinking_blocks) == 1
    assert message.thinking_blocks[0]["type"] == "thinking"


def test_message_from_litellm_message_without_reasoning():
    """Test Message.from_litellm_message without reasoning content."""
    from openhands.sdk.llm.message import Message

    litellm_message = LiteLLMMessage(role="assistant", content="The answer is 42.")

    message = Message.from_litellm_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    from openhands.sdk.llm.message import TextContent

    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."
    assert message.reasoning_content is None
    assert message.thinking_blocks is None


def test_llm_expose_reasoning_default():
    """Test LLM expose_reasoning default value."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514")
    assert llm.expose_reasoning is True


def test_llm_expose_reasoning_disabled():
    """Test LLM with expose_reasoning disabled."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=False)
    assert llm.expose_reasoning is False


def test_llm_extract_reasoning_content_enabled():
    """Test LLM._extract_reasoning_content when expose_reasoning is True."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=True)

    # Create a mock response with reasoning content
    mock_response = create_mock_response()
    # Add reasoning content to the message
    mock_response.choices[0].message.reasoning_content = "I need to think about this..."  # type: ignore
    mock_response.choices[0].message.thinking_blocks = [  # type: ignore
        {"type": "thinking", "thinking": "Step 1..."}
    ]

    # Call the extraction method
    llm._extract_reasoning_content(mock_response)

    # Verify reasoning content exists on the message
    assert hasattr(mock_response.choices[0].message, "reasoning_content")  # type: ignore
    assert hasattr(mock_response.choices[0].message, "thinking_blocks")  # type: ignore


def test_llm_extract_reasoning_content_no_choices():
    """Test LLM._extract_reasoning_content with no choices."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=True)

    mock_response = create_mock_response()
    mock_response.choices = []  # type: ignore

    # Should not raise an error
    llm._extract_reasoning_content(mock_response)


def test_llm_extract_reasoning_content_no_message():
    """Test LLM._extract_reasoning_content with no message."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=True)

    mock_response = create_mock_response()
    # Remove the message from the choice
    delattr(mock_response.choices[0], "message")  # type: ignore

    # Should not raise an error
    llm._extract_reasoning_content(mock_response)


def test_llm_extract_reasoning_content_no_reasoning():
    """Test LLM._extract_reasoning_content with no reasoning content."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=True)

    mock_response = create_mock_response()
    # The message won't have reasoning_content or thinking_blocks attributes by default

    # Should not raise an error
    llm._extract_reasoning_content(mock_response)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_with_reasoning_enabled(mock_completion):
    """Test LLM.completion with reasoning content extraction enabled."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=True)

    # Mock the response with reasoning content
    mock_response = create_mock_response()
    mock_completion.return_value = mock_response

    messages = [{"role": "user", "content": "Hello"}]

    with patch.object(llm, "_extract_reasoning_content") as mock_extract:
        result = llm.completion(messages)

        # Verify reasoning extraction was called
        mock_extract.assert_called_once_with(mock_response)
        assert result == mock_response


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_with_reasoning_disabled(mock_completion):
    """Test LLM.completion with reasoning content extraction disabled."""
    from openhands.sdk.llm.llm import LLM

    llm = LLM(model="claude-sonnet-4-20250514", expose_reasoning=False)

    mock_response = create_mock_response()
    mock_completion.return_value = mock_response

    messages = [{"role": "user", "content": "Hello"}]

    with patch.object(llm, "_extract_reasoning_content") as mock_extract:
        result = llm.completion(messages)

        # Verify reasoning extraction was NOT called
        mock_extract.assert_not_called()
        assert result == mock_response


def test_message_serialization_with_reasoning():
    """Test Message serialization includes reasoning content."""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Answer")],
        reasoning_content="Thinking process...",
        thinking_blocks=[{"type": "thinking", "thinking": "Step 1"}],
    )

    serialized = message.model_dump()

    assert serialized["reasoning_content"] == "Thinking process..."
    assert serialized["thinking_blocks"] == [{"type": "thinking", "thinking": "Step 1"}]


def test_message_serialization_without_reasoning():
    """Test Message serialization without reasoning content."""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(role="assistant", content=[TextContent(text="Answer")])

    serialized = message.model_dump()

    assert serialized["reasoning_content"] is None
    assert serialized["thinking_blocks"] is None
