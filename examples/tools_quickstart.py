"""
Tools Quickstart: call built-in tools directly without an agent/LLM.

Run:
  uv run python -m examples.tools_quickstart
"""
from __future__ import annotations

import os

from openhands.tools import (
    BashExecutor,
    ExecuteBashAction,
    FileEditorExecutor,
    StrReplaceEditorAction,
    execute_bash_tool,
    str_replace_editor_tool,
)


def main() -> None:
    # Bash executor
    bash = BashExecutor(working_dir=os.getcwd())
    bash_tool = execute_bash_tool.set_executor(bash)
    obs = bash_tool.call(ExecuteBashAction(command="echo hello && python -V", security_risk="LOW"))
    print("[execute_bash] observation:\n", obs.agent_observation)

    # Str replace editor
    editor = FileEditorExecutor()
    editor_tool = str_replace_editor_tool.set_executor(editor)

    # Replace a small string in README.md if present; otherwise create a temp file
    target = "README.md" if os.path.exists("README.md") else "TEMP_QUICKSTART.txt"
    if not os.path.exists(target):
        open(target, "w", encoding="utf-8").write("OpenHands Quickstart\n")

    action = StrReplaceEditorAction(command="str_replace", path=os.path.abspath(target), old_str="OpenHands", new_str="OpenHands SDK", security_risk="LOW")
    obs2 = editor_tool.call(action)
    print("[str_replace_editor] observation:\n", obs2.agent_observation)


if __name__ == "__main__":
    main()
