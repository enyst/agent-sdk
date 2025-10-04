from collections.abc import Sequence

from pydantic import Field
from rich.text import Text

from openhands.sdk.event.base import N_CHAR_PREVIEW, LLMConvertibleEvent
from openhands.sdk.event.types import EventID, SourceType, ToolCallID
from openhands.sdk.llm import (
    Message,
    MessageToolCall,
    ReasoningItemModel,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.security import risk
from openhands.sdk.tool.schema import Action


class ActionEvent(LLMConvertibleEvent):
    source: SourceType = "agent"
    thought: Sequence[TextContent] = Field(
        ..., description="The thought process of the agent before taking this action"
    )
    reasoning_content: str | None = Field(
        default=None,
        description="Intermediate reasoning/thinking content from reasoning models",
    )
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = Field(
        default_factory=list,
        description="Anthropic thinking blocks from the LLM response",
    )
    responses_reasoning_item: ReasoningItemModel | None = Field(
        default=None, description="OpenAI Responses reasoning item from model output"
    )
    action: Action = Field(..., description="Single action (tool call) returned by LLM")
    tool_name: str = Field(..., description="The name of the tool being called")
    tool_call_id: ToolCallID = Field(
        ..., description="The unique id returned by LLM API for this tool call"
    )
    tool_call: MessageToolCall = Field(
        ...,
        description=(
            "The tool call received from the LLM response. We keep a copy of it "
            "so it is easier to construct it into LLM message"
            "This could be different from `action`: e.g., `tool_call` may contain "
            "`security_risk` field predicted by LLM when LLM risk analyzer is enabled"
            ", while `action` does not."
        ),
    )
    llm_response_id: EventID = Field(
        ...,
        description=(
            "Groups related actions from same LLM response. This helps in tracking "
            "and managing results of parallel function calling from the same LLM "
            "response."
        ),
    )

    security_risk: risk.SecurityRisk = Field(
        default=risk.SecurityRisk.UNKNOWN,
        description="The LLM's assessment of the safety risk of this action.",
    )

    @property
    def visualize(self) -> Text:
        """Return Rich Text representation of this action event."""
        content = Text()

        if self.security_risk != risk.SecurityRisk.UNKNOWN:
            content.append(self.security_risk.visualize)

        # Display reasoning content first if available
        if self.reasoning_content:
            content.append("Reasoning:\n", style="bold")
            content.append(self.reasoning_content)
            content.append("\n\n")

        # Display complete thought content
        thought_text = " ".join([t.text for t in self.thought])
        if thought_text:
            content.append("Thought:\n", style="bold")
            content.append(thought_text)
            content.append("\n\n")

        # Responses API reasoning (plaintext only; never render encrypted_content)
        reasoning_item = self.responses_reasoning_item
        if reasoning_item is not None:
            content.append("Reasoning:\n", style="bold")
            if reasoning_item.summary:
                for s in reasoning_item.summary:
                    content.append(f"- {s}\n")
            if reasoning_item.content:
                for b in reasoning_item.content:
                    content.append(f"{b}\n")

        # Display action information using action's visualize method
        content.append(self.action.visualize)

        return content

    def to_llm_message(self) -> Message:
        """Individual message - may be incomplete for multi-action batches"""
        return Message(
            role="assistant",
            content=self.thought,
            tool_calls=[self.tool_call],
            reasoning_content=self.reasoning_content,
            thinking_blocks=self.thinking_blocks,
            responses_reasoning_item=self.responses_reasoning_item,
        )

    def __str__(self) -> str:
        """Plain text string representation for ActionEvent."""
        base_str = f"{self.__class__.__name__} ({self.source})"
        thought_text = " ".join([t.text for t in self.thought])
        thought_preview = (
            thought_text[:N_CHAR_PREVIEW] + "..."
            if len(thought_text) > N_CHAR_PREVIEW
            else thought_text
        )
        action_name = self.action.__class__.__name__
        return f"{base_str}\n  Thought: {thought_preview}\n  Action: {action_name}"


class NonExecutableActionEvent(LLMConvertibleEvent):
    """Assistant function_call(s) persisted without a validated Action.

    Emitted when LLM returned tool call(s) but validation failed (or tool missing),
    so we still persist the function_call(s) for the next turn to match tool outputs.
    """

    source: SourceType = "agent"
    thought: Sequence[TextContent] = Field(
        default_factory=list,
        description="The assistant's thought content returned alongside tool calls",
    )
    reasoning_content: str | None = Field(
        default=None,
        description="Intermediate reasoning content from reasoning models",
    )
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = Field(
        default_factory=list,
        description="Anthropic thinking blocks from the LLM response",
    )
    responses_reasoning_item: ReasoningItemModel | None = Field(
        default=None, description="OpenAI Responses reasoning item from model output"
    )
    tool_calls: list[MessageToolCall] = Field(
        default_factory=list, description="Raw tool calls returned by the LLM"
    )

    def to_llm_message(self) -> Message:
        return Message(
            role="assistant",
            content=self.thought,
            tool_calls=self.tool_calls,
            reasoning_content=self.reasoning_content,
            thinking_blocks=self.thinking_blocks,
            responses_reasoning_item=self.responses_reasoning_item,
        )

    @property
    def visualize(self) -> Text:
        content = Text()
        if self.reasoning_content:
            content.append("Reasoning:\n", style="bold")
            content.append(self.reasoning_content)
            content.append("\n\n")
        thought_text = " ".join([t.text for t in self.thought])
        if thought_text:
            content.append("Thought:\n", style="bold")
            content.append(thought_text)
            content.append("\n\n")
        # Responses API reasoning (plaintext only; never render encrypted_content)
        reasoning_item = self.responses_reasoning_item
        if reasoning_item is not None:
            content.append("Reasoning:\n", style="bold")
            if reasoning_item.summary:
                for s in reasoning_item.summary:
                    content.append(f"- {s}\n")
            if reasoning_item.content:
                for b in reasoning_item.content:
                    content.append(f"{b}\n")

        content.append("Function calls:\n", style="bold")
        for tc in self.tool_calls:
            content.append(f"- {tc.name} ({tc.id})\n")
        return content

    def __str__(self) -> str:
        base_str = f"{self.__class__.__name__} ({self.source})"
        thought_text = " ".join([t.text for t in self.thought])
        thought_preview = (
            thought_text[:N_CHAR_PREVIEW] + "..."
            if len(thought_text) > N_CHAR_PREVIEW
            else thought_text
        )
        calls = ", ".join([f"{tc.name}:{tc.id}" for tc in self.tool_calls]) or "[]"
        return f"{base_str}\n  Thought: {thought_preview}\n  Calls: {calls}"
