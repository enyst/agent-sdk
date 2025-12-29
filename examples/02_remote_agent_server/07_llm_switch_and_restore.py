"""Demonstrate agent-server LLM switching + persistence across restart.

This script:
1) Starts a local Python agent-server with a dedicated conversations directory.
2) Creates a conversation (without running it).
3) Switches the conversation's active LLM via `POST /api/conversations/{id}/llm`.
4) Restarts the agent-server and verifies the switched LLM persists on restore.

The switch uses an inline LLM payload, which is the recommended path for remote
clients whose "profiles" are local-only (e.g. the VS Code extension).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(
        f"Timed out waiting for agent-server health at {base_url}/health"
    )


def _start_agent_server(
    *, conversations_path: Path
) -> tuple[subprocess.Popen[str], str]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "OH_ENABLE_VSCODE": "0",
        "OH_ENABLE_VNC": "0",
        "OH_PRELOAD_TOOLS": "0",
        "SESSION_API_KEY": "",
        "OH_CONVERSATIONS_PATH": str(conversations_path),
    }

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "openhands.agent_server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_health(base_url)
    except Exception:
        try:
            output = (proc.stdout.read() if proc.stdout else "") or ""
        except Exception:
            output = ""
        proc.terminate()
        raise RuntimeError(f"agent-server failed to start.\n\n{output}") from None

    return proc, base_url


def _stop_agent_server(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> None:
    root = Path(".agent_server_llm_switch_demo").resolve()
    conversations_path = root / "conversations"
    workspace_path = root / "workspace"
    conversations_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)

    proc_1, base_1 = _start_agent_server(conversations_path=conversations_path)
    conversation_id: str
    try:
        print("agent-server #1:", base_1)

        create = httpx.post(
            f"{base_1}/api/conversations",
            json={
                "agent": {
                    "llm": {
                        "usage_id": "agent",
                        "model": "test-provider/original",
                        "api_key": "test-key",
                    },
                    "tools": [],
                },
                "workspace": {"working_dir": str(workspace_path)},
            },
            timeout=10.0,
        )
        create.raise_for_status()
        conversation_id = create.json()["id"]
        print("conversation id:", conversation_id)

        update = httpx.post(
            f"{base_1}/api/conversations/{conversation_id}/llm",
            json={
                "llm": {
                    "usage_id": "ignored-by-server",
                    "model": "test-provider/alternate",
                    "api_key": "test-key-2",
                }
            },
            timeout=10.0,
        )
        update.raise_for_status()

        info = httpx.get(
            f"{base_1}/api/conversations/{conversation_id}",
            timeout=10.0,
        )
        info.raise_for_status()
        current_model = info.json()["agent"]["llm"]["model"]
        print("server #1 model:", current_model)
        if current_model != "test-provider/alternate":
            raise RuntimeError("LLM switch did not apply on server #1")
    finally:
        _stop_agent_server(proc_1)

    proc_2, base_2 = _start_agent_server(conversations_path=conversations_path)
    try:
        print("agent-server #2:", base_2)
        restored = httpx.get(
            f"{base_2}/api/conversations/{conversation_id}",
            timeout=10.0,
        )
        restored.raise_for_status()
        restored_model = restored.json()["agent"]["llm"]["model"]
        print("server #2 restored model:", restored_model)
        if restored_model != "test-provider/alternate":
            raise RuntimeError("LLM switch did not persist across restart")
    finally:
        _stop_agent_server(proc_2)

    print("✓ LLM switch persisted across agent-server restart")

    base_state = (
        conversations_path / conversation_id.replace("-", "") / "base_state.json"
    )
    if base_state.exists():
        payload = json.loads(base_state.read_text(encoding="utf-8"))
        print("base_state.json agent.llm:", payload.get("agent", {}).get("llm"))


if __name__ == "__main__":
    main()
