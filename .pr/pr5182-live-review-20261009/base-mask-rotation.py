"""Check whether the underlying replacement-source flaw predates PR 5182."""

import asyncio
import json
from pathlib import Path
import tempfile

from openhands.sdk import Agent, Conversation
from openhands.sdk.event import MessageEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.testing import TestLLM


OLD_FAKE = "rotation-qa-old-credential"
NEW_FAKE = "rotation-qa-new-credential"


async def main():
    directory = tempfile.mkdtemp(prefix="pr5182-base-rotation-")
    llm = TestLLM.from_messages([
        Message(role="assistant", content=[TextContent(text=f"rejected token {NEW_FAKE}")])
    ])
    conversation = Conversation(
        agent=Agent(llm=llm, tools=[]), workspace=directory,
        persistence_dir=directory, visualizer=None, secrets={"TEST_TOKEN": OLD_FAKE},
    )
    try:
        conversation.state.secret_registry.get_secret_value("TEST_TOKEN")
        conversation.update_secrets({"TEST_TOKEN": NEW_FAKE})
        conversation.send_message("hello")
        await asyncio.wait_for(conversation.arun(), timeout=5)
        messages = [e for e in conversation.state.events
                    if isinstance(e, MessageEvent) and e.source == "agent"]
        persisted = list(Path(directory).rglob("events/*.json"))
        print(json.dumps({
            "new_secret_in_event": any(NEW_FAKE in e.model_dump_json() for e in messages),
            "new_secret_persisted": any(NEW_FAKE in p.read_text() for p in persisted),
            "persistence_dir": directory,
        }, indent=2))
    finally:
        await asyncio.to_thread(conversation.close)


asyncio.run(main())
