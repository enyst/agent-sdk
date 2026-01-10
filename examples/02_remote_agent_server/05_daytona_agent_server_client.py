"""Example: run OpenHands agent-server in a Daytona Cloud sandbox and connect to it.

Prerequisites:
  - Set DAYTONA_API_KEY in your environment.
  - The GHCR image must be public (or your org must have a registry configured).

This script:
  1) Creates a Daytona sandbox from the published agent-server image
  2) Starts the agent-server inside the sandbox (port 8000)
  3) Gets a Daytona preview link for port 8000
  4) Calls /health on the agent-server via the preview URL

Notes:
  - If the sandbox is private, Daytona returns a preview token. For programmatic
    access, we send it as `x-daytona-preview-token`.
  - We also support the agent-server session API key via X-Session-API-Key if
    you set SESSION_API_KEY. By default, the agent-server is unsecured.

"""

from __future__ import annotations

import os
import time

import httpx
from daytona import CreateSandboxFromImageParams, Daytona, DaytonaConfig
from daytona.common.process import SessionExecuteRequest
from dotenv import load_dotenv


load_dotenv(dotenv_path=os.getenv("DOTENV_PATH", ".env"))


AGENT_SERVER_IMAGE = os.getenv(
    "AGENT_SERVER_IMAGE",
    "ghcr.io/openhands/agent-server:latest-python",
)
# Daytona preview links are commonly used for ports 3000-3999.
# Agent-server itself defaults to 8000, but we can run it on 3000 for convenience.
AGENT_SERVER_PORT = int(os.getenv("AGENT_SERVER_PORT", "3000"))

DAYTONA_API_KEY = os.getenv("DAYTONA_API_KEY")
assert DAYTONA_API_KEY is not None, "DAYTONA_API_KEY environment variable is not set."
DAYTONA_TARGET = os.getenv("DAYTONA_TARGET")
DAYTONA_API_URL = os.getenv("DAYTONA_API_URL")

SESSION_API_KEY = os.getenv("SESSION_API_KEY")


def _start_agent_server(sandbox, port: int) -> None:
    session_id = "agent-server"
    sandbox.process.create_session(session_id)
    # The published image doesn't expose the Python package as `openhands.agent_server`.
    # It ships a CLI entrypoint `openhands-agent-server`.
    cmd = f"openhands-agent-server --host 0.0.0.0 --port {port}"
    sandbox.process.execute_session_command(
        session_id,
        SessionExecuteRequest(command=cmd, additional_properties={"runAsync": True}),
    )


def _wait_for_health(url: str, headers: dict[str, str]) -> float:
    deadline = time.time() + 120
    start = time.monotonic()
    last_err: str | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=5.0, headers=headers) as client:
                resp = client.get(f"{url.rstrip('/')}/health")
            if resp.status_code == 200:
                return time.monotonic() - start
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(1)

    raise RuntimeError(f"Agent-server did not become healthy: {last_err}")


def main() -> None:
    t0 = time.monotonic()

    daytona_config = DaytonaConfig(
        api_key=DAYTONA_API_KEY,
        target=DAYTONA_TARGET,
        api_url=DAYTONA_API_URL,
    )
    daytona = Daytona(config=daytona_config)

    params = CreateSandboxFromImageParams(
        name=f"oh-agent-server-{int(time.time())}",
        image=AGENT_SERVER_IMAGE,
        public=False,
        auto_stop_interval=30,
        auto_delete_interval=60,
        env_vars={
            "OH_ENABLE_VNC": "false",
            "LOG_JSON": "true",
            **({"SESSION_API_KEY": SESSION_API_KEY} if SESSION_API_KEY else {}),
        },
    )

    sandbox = daytona.create(params, timeout=600)
    t1 = time.monotonic()

    _start_agent_server(sandbox, AGENT_SERVER_PORT)
    t2 = time.monotonic()

    preview = sandbox.get_preview_link(AGENT_SERVER_PORT)
    t3 = time.monotonic()

    daytona_headers: dict[str, str] = {}
    if getattr(preview, "token", None):
        daytona_headers["x-daytona-preview-token"] = preview.token

    headers = {
        **daytona_headers,
        **({"X-Session-API-Key": SESSION_API_KEY} if SESSION_API_KEY else {}),
    }

    print(f"Agent-server preview URL: {preview.url}")

    sandbox.process.execute_session_command(
        "agent-server",
        SessionExecuteRequest(
            command=(
                'python -c "import urllib.request; '
                'urllib.request.urlopen("http://127.0.0.1:'
                f"{AGENT_SERVER_PORT}"
                '" + "/health", timeout=1).read(); '
                "print('OK')\""
            ),
        ),
        timeout=120,
    )
    t4 = time.monotonic()

    external_ready_s = _wait_for_health(preview.url, headers)
    t5 = time.monotonic()

    print("Agent-server is healthy")
    print(
        "Timings (seconds): "
        f"provision={t1 - t0:.2f}, "
        f"start_cmd={t2 - t1:.2f}, "
        f"preview_link={t3 - t2:.2f}, "
        f"local_ready={t4 - t3:.2f}, "
        f"preview_ready={external_ready_s:.2f}, "
        f"end_to_end={t5 - t0:.2f}"
    )


if __name__ == "__main__":
    main()
