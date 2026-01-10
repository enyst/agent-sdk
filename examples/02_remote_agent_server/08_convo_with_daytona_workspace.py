import os
import time

from dotenv import load_dotenv
from pydantic import SecretStr

from openhands.sdk import LLM, Conversation, RemoteConversation, get_logger
from openhands.tools.preset.default import get_default_agent
from openhands.workspace.daytona import DaytonaWorkspace


load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


logger = get_logger(__name__)

api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)


daytona_api_key = os.getenv("DAYTONA_API_KEY")
assert daytona_api_key is not None, "DAYTONA_API_KEY environment variable is not set."


with DaytonaWorkspace(
    daytona_api_key=daytona_api_key,
    daytona_target=os.getenv("DAYTONA_TARGET"),
    daytona_api_url=os.getenv("DAYTONA_API_URL"),
    server_image=os.getenv(
        "AGENT_SERVER_IMAGE", "ghcr.io/openhands/agent-server:latest-python"
    ),
    server_port=int(os.getenv("AGENT_SERVER_PORT", "3000")),
    session_api_key=os.getenv("SESSION_API_KEY"),
    public=False,
) as workspace:
    agent = get_default_agent(
        llm=llm,
        cli_mode=True,
    )

    received_events: list = []
    last_event_time = {"ts": time.time()}

    def event_callback(event) -> None:
        logger.info(f"🔔 Callback received event: {type(event).__name__}\n{event}")
        received_events.append(event)
        last_event_time["ts"] = time.time()

    result = workspace.execute_command("echo 'Hello from Daytona sandbox!' && pwd")
    logger.info(
        f"Command '{result.command}' completed with exit code {result.exit_code}"
    )
    logger.info(f"Output: {result.stdout}")

    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        callbacks=[event_callback],
    )
    assert isinstance(conversation, RemoteConversation)

    try:
        logger.info(f"\n📋 Conversation ID: {conversation.state.id}")

        conversation.send_message(
            "Read the current repo and write 3 facts about the project into FACTS.txt."
        )
        conversation.run()

        while time.time() - last_event_time["ts"] < 2.0:
            time.sleep(0.1)

        conversation.send_message("Great! Now delete that file.")
        conversation.run()

        cost = conversation.conversation_stats.get_combined_metrics().accumulated_cost
        print(f"EXAMPLE_COST: {cost}")
    finally:
        conversation.close()
