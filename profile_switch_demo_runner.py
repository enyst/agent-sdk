"""Run a GPT-5 conversation focused on LLM profile switching tasks.

This script uses the OpenHands SDK to launch a conversation powered by
OpenAI's GPT-5 model. It repeatedly prompts the agent to build a CLI/TUI
that demonstrates LLM profile creation and switching. If the conversation
fails, it automatically restarts with a fresh conversation ID, keeping
track of each attempt in ``tracking.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

from pydantic import SecretStr

from openhands.sdk.context.condenser import LLMSummarizingCondenser


REPO_ROOT = Path(__file__).resolve().parent
SDK_ROOT = REPO_ROOT / "openhands-sdk"
TOOLS_ROOT = REPO_ROOT / "openhands-tools"
for path in (SDK_ROOT, TOOLS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from openhands.sdk import Conversation
from openhands.sdk.llm import LLM
from openhands.tools.preset.default import get_default_agent


REAL_PROMPT = (
    "Read ~/.openhands/microagents, especially the file about bd, run its quickstart to refresh task tracking. "
    "Then read the repository README to re-familiarize yourself with agent-sdk. You are on a branch that has "
    "implemented LLM Profiles and LLM Profile Switch. Create a CLI with a TUI that lets the user run a conversation, "
    "enter prompts, define profiles via /model, and switch between saved profiles via /profile so the conversation "
    "continues with the new settings. Place the CLI/TUI in a dedicated examples/ subdirectory for this demo, and make "
    "sure it genuinely works. Add unit tests for everything you build, run them, and fix any issues. Keep working until "
    "all tasks are complete, then: review your changes critically, compare against main to know your diff, file follow-up"
    "tasks as needed, fix them, re-test, and close them in bd."
    "Whenever you run bd list, consider outstanding profile/switch tasks. Use docs/llm_profiles.md, "
    "docs/llm_runtime_switch_investigation.md, and docs/llm_runtime_switch_plan.md to understand the goals."
    "Note: At some point, the implementation did not allow the registry to load profiles saved with the same usage_id."
    "If this is still the case, investigate and design a solution so the registry can load any profile and assign the appropriate usage_id"
    "only when switching (e.g., 'agent' for the main LLM, 'condenser' for the condenser). Consider whether profiles should omit usage_id"
    "and whether the LLM model needs to accept usage_id=None. If loading already works, skip to reviewing and polishing the feature. "
    "Always start by reviewing the documentation (the .md files mentioned above) and ensure it matches the implementation, updating docs as needed."
    '\n\nCommit your changes often, use real newlines in commit messages, do not write literal "\n".'
    "Understand that the project is an uv workspace, with four packages: openhands-sdk, openhands-tools, openhands-workspace, and openhands-agent-server."
    "Use tmux (`tmux new-session`, `tmux send-keys` , etc. as you see fit, these are only examples) for long-running commands, especially test runs, so output stays available to you."
    "Before running tests, rely on the uv environment: e.g. run `uv run pytest` (or specific module under test) so the workspace's packages resolve without import errors."
    "IMPORTANT: We need to get LLM Switch to work for real. The CLI/TUI is just an e2e test for it."
    "IMPORTANT: Please investigate carefully and make sure you understand the codebase before making any changes."
    "IMPORTANT: Think deeply and design the solution before implementing it. You can use the .md files mentioned above to help you and modify them as needed."
    "\nKeep conversation persistence working as it was previously designed, with only our absolutely necessary changes."
    "\nWe rely on pydantic and serialization based on it and the DiscriminatedUnionMixin. Do not mess the code with special cases, do not create parallel hierarchies or implementations, try to use what exists."
    "If you run an LLM, set the LLM_BASE_URL=https://llm-proxy.eval.all-hands.dev env variable."
    "I recommend using LLM_API_KEY from your env as the API key."
    "LLM_MODEL=openai/gpt-5-mini is a good model to test with."
)

TEST_PROMPT = (
    "Test run: confirm the automation wiring is functional without modifying files. "
    "Summarize the repository name and stop."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the OpenHands profile switching demo conversation.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run with a lightweight test prompt instead of the full workflow.",
    )
    return parser.parse_args()


def select_prompt(use_test: bool) -> str:
    return TEST_PROMPT if use_test else REAL_PROMPT


TRACKING_FILE = Path("logs/ralph/tracking.md")
REMINDER_TEMPLATE = (
    "Reminder: continue working on the requested task. Here are the instructions "
    "verbatim so you do not forget.\n\n"
    "\n\nPrompt:\n{prompt}\n"
)
BD_REMINDER_TEMPLATE = (
    "Reminder: continue working on the requested task. Here are the instructions "
    "verbatim so you do not forget.\n\n"
    "\n\nBD reminder:\n{bd_message}\n"
    "\n\nPrompt:\n{prompt}\n"
)

MAX_ATTEMPTS = 100


def _build_llm() -> LLM:
    api_key = os.getenv("OPENAI_API_KEY_AH")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY_AH must be set in the environment to run the demo"
        )

    return LLM(
        model="openai/gpt-5",
        api_key=SecretStr(api_key),
        reasoning_effort="high",
        log_completions=False,
        drop_params=True,
        usage_id="agent",
    )


def _create_conversation() -> Conversation:
    llm = _build_llm()
    base_agent = get_default_agent(llm=llm, cli_mode=True)
    condenser = LLMSummarizingCondenser(
        llm=llm.model_copy(update={"usage_id": "condenser"}),
        max_size=600,
        keep_first=8,
    )
    agent = base_agent.model_copy(update={"condenser": condenser})
    conversation = Conversation(
        agent=agent,
        workspace=os.getcwd(),
        visualize=True,
    )
    return conversation


def _append_tracking_entry(conversation_id: str, attempt_number: int) -> None:
    TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TRACKING_FILE.exists():
        TRACKING_FILE.touch()
    with TRACKING_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"Attempt {attempt_number}: {conversation_id}\n")


def _send_and_run(conversation: Conversation, message: str) -> None:
    conversation.send_message(message)
    conversation.run()


def main() -> None:
    args = parse_args()
    prompt_text = select_prompt(args.test)
    bd_message = "Run 'bd list' to see outstanding tasks. We ONLY care about LLM profiles / LLM switch tasks. Add new tasks as needed."
    reminder_message = REMINDER_TEMPLATE.format(prompt=prompt_text, bd_message="")
    reminder_message_with_bd = BD_REMINDER_TEMPLATE.format(
        prompt=prompt_text, bd_message=bd_message
    )

    target_attempts = 1 if args.test else MAX_ATTEMPTS

    TRACKING_FILE.touch(exist_ok=True)

    conversation_ids: list[str] = []
    user_message_runs = 0
    attempts = 0

    while attempts < target_attempts:
        conversation: Conversation | None = None
        conversation_id = "unknown"
        try:
            conversation = _create_conversation()
            attempts += 1
            conversation_id = str(conversation.id)
            conversation_ids.append(conversation_id)
            _append_tracking_entry(conversation_id, attempts)

            _send_and_run(conversation, prompt_text)
            user_message_runs += 1

            _send_and_run(conversation, reminder_message)
            user_message_runs += 1

            _send_and_run(conversation, reminder_message_with_bd)
            user_message_runs += 1

            print(
                f"[Attempt {attempts}/{target_attempts}] Conversation {conversation_id} completed successfully."
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            print(
                f"[Attempt {attempts}/{target_attempts}] Conversation {conversation_id} failed with exception {exc.__class__.__name__}.",
                file=sys.stderr,
            )
            error_log_dir = Path("logs/ralph")
            error_log_dir.mkdir(parents=True, exist_ok=True)
            error_path = error_log_dir / f"{conversation_id}_error.log"
            with error_path.open("w", encoding="utf-8") as error_file:
                traceback.print_exception(exc, file=error_file)
        finally:
            if conversation is not None:
                try:
                    conversation.close()
                except Exception:  # pragma: no cover - best effort cleanup
                    traceback.print_exc()

    print(f"Total conversation attempts: {attempts}")
    print(f"Conversation IDs: {conversation_ids}")
    print(f"User messages executed: {user_message_runs}")


if __name__ == "__main__":
    main()
