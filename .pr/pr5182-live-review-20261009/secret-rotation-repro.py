import asyncio
import json
from pathlib import Path
import tempfile

from openhands.sdk import Agent, Conversation
from openhands.sdk.event import SecurityAnalysisEvent
from openhands.sdk.llm import Message, MessageToolCall
from openhands.sdk.secret import LookupSecret
from openhands.sdk.security import (
    ConfirmRisky,
    SecurityAnalysis,
    SecurityAnalyzerBase,
    SecurityRisk,
)
from openhands.sdk.testing import TestLLM


OLD_FAKE = "rotation-qa-old-credential"
NEW_FAKE = "rotation-qa-new-credential"


class RotationDetailAnalyzer(SecurityAnalyzerBase):
    def security_risk(self, action):
        return SecurityRisk.HIGH

    def analyze_action(self, action):
        return SecurityAnalysis(
            risk=SecurityRisk.HIGH,
            details={"rationale": f"rejected token {NEW_FAKE}"},
        )


async def main():
    lookup_seen = asyncio.Event()

    async def serve_secret(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        await asyncio.to_thread(conversation.update_secrets, {"TEST_TOKEN": NEW_FAKE})
        lookup_seen.set()
        body = OLD_FAKE.encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
            + b"\r\nConnection: close\r\n\r\n" + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(serve_secret, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    llm = TestLLM.from_messages([
        Message(role="assistant", content=[], tool_calls=[
            MessageToolCall(
                id=f"think-{i}", origin="completion", name="think",
                arguments='{"thought":"test"}',
            )
            for i in range(2)
        ])
    ])
    directory = tempfile.mkdtemp(prefix="pr5182-static-rotation-")
    conversation = Conversation(
        agent=Agent(llm=llm, tools=[]), workspace=directory,
        persistence_dir=directory, visualizer=None,
        secrets={"TEST_TOKEN": LookupSecret(url=f"http://127.0.0.1:{port}/secret")},
    )
    conversation.set_security_analyzer(RotationDetailAnalyzer())
    conversation.set_confirmation_policy(ConfirmRisky())
    try:
        conversation.send_message("hello")
        await asyncio.wait_for(conversation.arun(), timeout=5)
        audits = [e for e in conversation.state.events if isinstance(e, SecurityAnalysisEvent)]
        persisted = list(Path(directory).rglob("events/*.json"))
        print(json.dumps({
            "lookup_seen": lookup_seen.is_set(),
            "audits": [e.model_dump(mode="json") for e in audits],
            "new_secret_in_event": any(NEW_FAKE in e.model_dump_json() for e in audits),
            "new_secret_persisted": any(NEW_FAKE in p.read_text() for p in persisted),
            "current_source": conversation.state.secret_registry.secret_sources["TEST_TOKEN"].__class__.__name__,
            "persistence_dir": directory,
        }, indent=2))
    finally:
        await asyncio.to_thread(conversation.close)
        server.close()
        await server.wait_closed()


asyncio.run(main())
