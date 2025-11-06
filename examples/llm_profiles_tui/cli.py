from __future__ import annotations

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import argparse
import json
import os
import shlex
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr

from openhands.sdk import Conversation
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.llm import LLM
from openhands.sdk.llm.llm_registry import LLMRegistry
from openhands.tools.preset.default import get_default_agent


@dataclass
class AppContext:
    conversation: Any
    registry: Any


def parse_keyvals(args: list[str]) -> dict[str, Any]:
    """Parse key=value pairs into a dict with basic type coercion.

    Supports numbers (int/float), booleans, and strings. Special-case api_key
    to wrap in SecretStr when provided as a literal value. If the value looks
    like ENV[NAME], read from environment.
    """
    data: dict[str, Any] = {}
    for token in args:
        if "=" not in token:
            raise ValueError(f"Expected key=value, got: {token}")
        key, value = token.split("=", 1)
        key = key.strip()
        value = value.strip()
        # ENV var indirection: api_key=ENV[OPENAI_API_KEY]
        if value.startswith("ENV[") and value.endswith("]"):
            env_name = value[4:-1]
            value = os.getenv(env_name) or ""
        # booleans
        if value in {"true", "True"}:
            coerced: Any = True
        elif value in {"false", "False"}:
            coerced = False
        else:
            # numbers
            try:
                if "." in value:
                    coerced = float(value)
                else:
                    coerced = int(value)
            except ValueError:
                coerced = value
        if key in {
            "api_key",
            "aws_access_key_id",
            "aws_secret_access_key",
        } and coerced not in (None, ""):
            coerced = SecretStr(str(coerced))
        data[key] = coerced
    return data


def cmd_model(ctx: AppContext, tokens: list[str]) -> str:
    """Define and save a profile: /model <profile_id> model=... [k=v]..."""
    if not tokens:
        return "Usage: /model <profile_id> model=<name> [key=value ...]"
    profile_id = tokens[0]
    keyvals = parse_keyvals(tokens[1:]) if len(tokens) > 1 else {}
    if "model" not in keyvals:
        return "Error: model=<name> is required"
    # Default usage_id of the saved payload; runtime slot assignment happens on switch
    if "usage_id" not in keyvals:
        keyvals["usage_id"] = "agent"
    llm = LLM(**keyvals)
    ctx.registry.save_profile(profile_id, llm, include_secrets=False)
    return f"Saved profile '{profile_id}' for model '{llm.model}'."


def cmd_profile(ctx: AppContext, tokens: list[str]) -> str:
    """Switch active LLM to a stored profile: /profile <profile_id>"""
    if not tokens:
        return "Usage: /profile <profile_id>"
    profile_id = tokens[0]
    ctx.conversation.switch_llm(profile_id)
    active = ctx.conversation.agent.llm
    return f"Switched to profile '{profile_id}' (model={active.model})."


def cmd_list(ctx: AppContext, _tokens: list[str]) -> str:
    profiles = ctx.registry.list_profiles()
    if not profiles:
        return "No profiles found. Use /model to create one."
    return "Available profiles:\n" + "\n".join(f"- {p}" for p in profiles)


def cmd_show(ctx: AppContext, tokens: list[str]) -> str:
    if not tokens:
        return "Usage: /show <profile_id>"
    profile_id = tokens[0]
    llm = ctx.registry.load_profile(profile_id)
    payload = llm.model_dump(exclude_none=True)
    # Redact secrets if any somehow made it
    for key in ("api_key", "aws_access_key_id", "aws_secret_access_key"):
        if key in payload:
            payload[key] = "****"
    return json.dumps(payload, indent=2)


def cmd_save(ctx: AppContext, tokens: list[str]) -> str:
    if not tokens:
        return "Usage: /save <profile_id>"
    profile_id = tokens[0]
    llm = ctx.conversation.agent.llm
    ctx.registry.save_profile(profile_id, llm, include_secrets=False)
    return f"Saved current LLM configuration to profile '{profile_id}'."


def cmd_delete(ctx: AppContext, tokens: list[str]) -> str:
    if not tokens:
        return "Usage: /delete <profile_id>"
    profile_id = tokens[0]
    try:
        path = ctx.registry.get_profile_path(profile_id)
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"
    if not path.exists():
        return f"Profile not found: {profile_id}"
    try:
        path.unlink()
        return f"Deleted profile '{profile_id}'."
    except Exception as exc:  # noqa: BLE001
        return f"Error deleting '{profile_id}': {exc}"


def cmd_edit(ctx: AppContext, tokens: list[str]) -> str:
    if not tokens:
        return "Usage: /edit <profile_id> key=value ..."
    profile_id = tokens[0]
    if len(tokens) == 1:
        return "Error: provide at least one key=value to edit"
    try:
        base = ctx.registry.load_profile(profile_id)
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"

    try:
        updates = parse_keyvals(tokens[1:])
        payload = getattr(base, "model_dump", lambda **_: {})(exclude_none=True)
        if not isinstance(payload, dict):
            payload = {}
        payload.update(updates)
        updated = LLM(**payload)
        ctx.registry.save_profile(profile_id, updated, include_secrets=False)
        return f"Updated profile '{profile_id}'."
    except Exception as exc:  # noqa: BLE001
        return f"Error: {exc}"


COMMANDS = {
    "/model": cmd_model,
    "/profile": cmd_profile,
    "/list": cmd_list,
    "/show": cmd_show,
    "/save": cmd_save,
    "/delete": cmd_delete,
    "/edit": cmd_edit,
    "/help": None,  # handled specially
}


HELP_TEXT = """
Commands:
  /model <profile_id> model=<name> [key=value ...]   Create & save a profile
  /profile <profile_id>                              Switch active LLM profile
  /list                                              List saved profiles
  /show <profile_id>                                 Show profile details
  /save <profile_id>                                 Save current LLM as profile
  /delete <profile_id>                               Delete saved profile
  /edit <profile_id> key=value ...                   Update fields in a profile
  /help                                              Show this help
  /exit | /quit                                      Exit the app

Examples:
  /model fast-gpt model=openai/gpt-4o-mini temperature=0.2
  /model heavy-sonnet model=anthropic/claude-sonnet-4-20250514 reasoning_effort=high
  /profile fast-gpt
""".strip()


def run_loop(ctx: AppContext) -> None:
    print("OpenHands LLM Profiles Demo (TUI)")
    print("Type /help for commands. Enter text to chat with the agent.")
    while True:
        try:
            raw = input("> ")
        except EOFError:
            print()
            break
        line = raw.strip()
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            break
        if line.startswith("/"):
            parts = shlex.split(line)
            cmd = parts[0]
            handler = COMMANDS.get(cmd)
            if cmd == "/help":
                print(HELP_TEXT)
                continue
            if handler is None:
                print(f"Unknown command: {cmd}. Type /help for help.")
                continue
            try:
                output = handler(ctx, parts[1:])
            except Exception as exc:  # noqa: BLE001
                output = f"Error: {exc}"
            print(output)
            continue
        # Regular chat message
        ctx.conversation.send_message(line)
        try:
            ctx.conversation.run()
        except Exception as exc:  # noqa: BLE001
            print(f"Error during run: {exc}")


def build_conversation(
    initial_profile: str | None, workspace: str | None
) -> AppContext:
    registry = LLMRegistry()
    if initial_profile:
        # Use profile for agent LLM
        llm = registry.load_profile(initial_profile)
    else:
        # Minimal default LLM; user can switch later via /profile
        llm = LLM(model="gpt-4o-mini", usage_id="agent")
    agent: AgentBase = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(agent=agent, workspace=workspace or os.getcwd())
    return AppContext(conversation=conversation, registry=registry)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM Profiles TUI Demo")
    parser.add_argument("--profile", help="Initial profile id to load", default=None)
    parser.add_argument("--workspace", help="Workspace directory", default=None)
    parser.add_argument(
        "--inline",
        action="store_true",
        help=(
            "Persist inline LLM payloads (disables runtime switching). "
            "By default, profile references are used "
            "(OPENHANDS_INLINE_CONVERSATIONS=false)."
        ),
        default=False,
    )
    args = parser.parse_args(argv)

    # Default to profile references so /profile works out of the box
    os.environ["OPENHANDS_INLINE_CONVERSATIONS"] = "true" if args.inline else "false"

    ctx = build_conversation(args.profile, args.workspace)
    try:
        run_loop(ctx)
        return 0
    finally:
        try:
            ctx.conversation.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
