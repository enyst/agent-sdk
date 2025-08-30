import os

from pydantic import SecretStr

from openhands.core import (
    LLM,
    ActionBase,
    CodeActAgent,
    Conversation,
    ConversationEventType,
    LLMConfig,
    Message,
    ObservationBase,
    TextContent,
    Tool,
    get_logger,
)
from openhands.tools import (
    BashExecutor,
    FileEditorExecutor,
    execute_bash_tool,
    str_replace_editor_tool,
)


logger = get_logger(__name__)

"""
Run this example with a valid API key. It tries, in order:
  1) LITELLM_API_KEY (for litellm proxy)
  2) GEMINI_API_KEY  (for gemini models)
  3) OPENAI_API_KEY  (for openai models)

Usage:
  uv run python -m examples.hello_world
"""

# Configure LLM (fallbacks)
api_key = (
    os.getenv("LITELLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("OPENAI_API_KEY")
)
assert api_key is not None, "No API key found. Set LITELLM_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY."

# Default to litellm proxy if LITELLM_API_KEY is set; else pick provider by env
if os.getenv("LITELLM_API_KEY"):
    model = "litellm_proxy/anthropic/claude-sonnet-4-20250514"
    base_url = "https://llm-proxy.eval.all-hands.dev"
elif os.getenv("GEMINI_API_KEY"):
    model = "gemini-2.5-pro"
    base_url = None
else:
    model = "gpt-4o-mini"
    base_url = None

llm = LLM(
    config=LLMConfig(
        model=model,
        base_url=base_url,
        api_key=SecretStr(api_key),
    )
)

# Tools
cwd = os.getcwd()
bash = BashExecutor(working_dir=cwd)
file_editor = FileEditorExecutor()
tools: list[Tool] = [
    execute_bash_tool.set_executor(executor=bash),
    str_replace_editor_tool.set_executor(executor=file_editor),
]

# Agent
agent = CodeActAgent(llm=llm, tools=tools)

llm_messages = []  # collect raw LLM messages
def conversation_callback(event: ConversationEventType):
    # print all the actions
    if isinstance(event, ActionBase):
        logger.info(f"Found a conversation action: {event}")
    elif isinstance(event, ObservationBase):
        logger.info(f"Found a conversation observation: {event}")
    elif isinstance(event, Message):
        logger.info(f"Found a conversation message: {str(event)[:200]}...")
        llm_messages.append(event.model_dump())

conversation = Conversation(agent=agent, callbacks=[conversation_callback])

conversation.send_message(
    message=Message(
        role="user",
        content=[TextContent(text="Hello! Can you create a new Python file named hello.py that prints 'Hello, World!'?")],
    )
)
conversation.run()

print("="*100)
print("Conversation finished. Got the following LLM messages:")
for i, message in enumerate(llm_messages):
    print(f"Message {i}: {str(message)[:200]}")
