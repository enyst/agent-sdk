"""
Persistence locally using Conversation state (no S3).

Run:
  uv run python -m examples.persistence_local
"""
from __future__ import annotations

import shutil
import tempfile

# Use the DummyAgent from echo_offline to avoid network calls
from examples.echo_offline import DummyAgent
from openhands.core import Conversation, Message, TextContent


# Note: ConversationPersistence is not exposed publicly; using the public API only.
# If a persistence API becomes public later, this example can be revised accordingly.

def main() -> None:
    tmpdir = tempfile.mkdtemp(prefix="oh-example-")
    try:
        convo = Conversation(agent=DummyAgent())
        convo.send_message(Message(role="user", content=[TextContent(text="Save me locally")]))
        convo.run()

        # Minimal demo: show that state exists in memory; file-based persistence is internal
        print("Conversation finished with", len(convo.state.history.messages), "messages.")
        print("Temporary dir prepared:", tmpdir)
        # Developers can extend this to their own persistence layer.
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    main()
