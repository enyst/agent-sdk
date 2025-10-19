"""Create and use an LLM profile with :class:`LLMRegistry`.

Run with::

    uv run python examples/01_standalone_sdk/25_llm_profiles.py

Profiles are stored under ``~/.openhands/llm-profiles/<name>.json`` by default.
Set ``LLM_PROFILE_NAME`` to pick a profile and ``LLM_API_KEY`` to supply
credentials when the profile omits secrets.
"""

import os

from pydantic import SecretStr

from openhands.sdk import Agent, Conversation
from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_registry import LLMRegistry
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.execute_bash import BashTool


DEFAULT_PROFILE_NAME = "gpt-5-mini"
PROFILE_NAME = os.getenv("LLM_PROFILE_NAME", DEFAULT_PROFILE_NAME)


def ensure_profile_exists(registry: LLMRegistry, name: str) -> None:
    """Create a starter profile in the default directory when missing."""

    if name in registry.list_profiles():
        return

    profile_defaults = LLM(
        model="litellm_proxy/openai/gpt-5-mini",
        base_url="https://llm-proxy.eval.all-hands.dev",
        temperature=0.2,
        max_output_tokens=4096,
        service_id="agent",
        metadata={
            "profile_description": "Sample GPT-5 Mini profile created by example 25.",
        },
    )
    path = registry.save_profile(name, profile_defaults)
    print(f"Created profile '{name}' at {path}")


def load_profile(registry: LLMRegistry, name: str) -> LLM:
    llm = registry.load_profile(name)
    if llm.api_key is None:
        api_key = os.getenv("LLM_API_KEY")
        if api_key is None:
            raise RuntimeError(
                "Set LLM_API_KEY to authenticate, or save the profile with "
                "include_secrets=True."
            )
        llm = llm.model_copy(update={"api_key": SecretStr(api_key)})
    return llm


def main() -> None:
    registry = LLMRegistry()
    ensure_profile_exists(registry, PROFILE_NAME)

    llm = load_profile(registry, PROFILE_NAME)

    register_tool("BashTool", BashTool)
    tools = [Tool(name="BashTool")]
    agent = Agent(llm=llm, tools=tools)

    conversation = Conversation(agent=agent, workspace=os.getcwd())
    conversation.send_message("Print 'Profile created successfully.'")
    conversation.run()


if __name__ == "__main__":  # pragma: no cover
    main()
