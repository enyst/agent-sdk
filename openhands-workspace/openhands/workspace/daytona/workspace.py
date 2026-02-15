"""Daytona Cloud workspace implementation.

This workspace provisions a Daytona sandbox from the published OpenHands agent-server
image, starts the agent-server inside the sandbox, and exposes it via Daytona's preview
link mechanism.

Authentication:
- Daytona preview URLs for private sandboxes require `x-daytona-preview-token`.
- OpenHands agent-server can optionally require `X-Session-API-Key` when
  SESSION_API_KEY is set in the sandbox environment.

"""

from __future__ import annotations

import time
from typing import Any

import httpx
import tenacity


try:
    from daytona import CreateSandboxFromImageParams, Daytona, DaytonaConfig, Sandbox
    from daytona.common.process import SessionExecuteRequest
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "DaytonaWorkspace requires the optional Daytona dependency. "
        "Install it with: uv pip install 'openhands-workspace[daytona]'"
    ) from e
from pydantic import Field, PrivateAttr

from openhands.sdk.logger import get_logger
from openhands.sdk.workspace.remote.base import RemoteWorkspace


logger = get_logger(__name__)


class DaytonaWorkspace(RemoteWorkspace):
    """Remote workspace backed by Daytona Cloud."""

    working_dir: str = Field(
        default="/workspace/project",
        description="Working directory inside the sandbox",
    )
    host: str = Field(
        default="undefined",
        description="Agent server URL. Set automatically after sandbox starts.",
    )

    daytona_api_key: str = Field(description="Daytona API key")
    daytona_target: str | None = Field(
        default=None,
        description="Optional Daytona target/region (e.g. us, eu)",
    )
    daytona_api_url: str | None = Field(
        default=None,
        description="Optional Daytona API URL override (e.g. https://app.daytona.io/api)",
    )

    server_image: str = Field(
        default="ghcr.io/openhands/agent-server:latest-python",
        description="Published OpenHands agent-server image",
    )
    server_port: int = Field(
        default=3000,
        description="Port to run the agent-server on inside the sandbox",
    )
    session_api_key: str | None = Field(
        default=None,
        description="Optional OpenHands agent-server session API key",
    )

    public: bool = Field(
        default=False,
        description="If True, Daytona preview URLs are publicly accessible",
    )
    auto_stop_interval: int = Field(
        default=30,
        description="Auto-stop interval in minutes",
    )
    auto_delete_interval: int = Field(
        default=60,
        description="Auto-delete interval in minutes",
    )

    init_timeout: float = Field(
        default=600.0,
        description="Sandbox creation timeout in seconds",
    )
    api_timeout: float = Field(
        default=60.0,
        description="HTTP read timeout for agent-server calls",
    )

    keep_alive: bool = Field(
        default=False,
        description="If True, keep sandbox alive on cleanup instead of deleting",
    )

    _sandbox: Sandbox | None = PrivateAttr(default=None)

    def __enter__(self) -> DaytonaWorkspace:
        return self

    _daytona_preview_token: str | None = PrivateAttr(default=None)

    @property
    def client(self) -> httpx.Client:
        client = self._client
        if client is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.api_timeout,
                write=10.0,
                pool=10.0,
            )
            client = httpx.Client(
                base_url=self.host,
                timeout=timeout,
                headers=self._headers,
            )
            self._client = client
        return client

    @property
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._daytona_preview_token:
            headers["x-daytona-preview-token"] = self._daytona_preview_token
        if self.api_key:
            headers["X-Session-API-Key"] = self.api_key
        return headers

    def model_post_init(self, context: Any) -> None:
        try:
            self._start_sandbox()
            super().model_post_init(context)
        except Exception:
            self._cleanup_sandbox()
            raise

    def _start_sandbox(self) -> None:
        daytona_config = DaytonaConfig(
            api_key=self.daytona_api_key,
            target=self.daytona_target,
            api_url=self.daytona_api_url,
        )
        daytona = Daytona(config=daytona_config)

        name = f"oh-agent-server-{int(time.time())}"
        params = CreateSandboxFromImageParams(
            name=name,
            image=self.server_image,
            public=self.public,
            auto_stop_interval=self.auto_stop_interval,
            auto_delete_interval=self.auto_delete_interval,
            env_vars={
                "OH_ENABLE_VNC": "false",
                "LOG_JSON": "true",
                **(
                    {"SESSION_API_KEY": self.session_api_key}
                    if self.session_api_key
                    else {}
                ),
            },
        )

        logger.info("Creating Daytona sandbox...")
        sandbox = daytona.create(params, timeout=self.init_timeout)
        self._sandbox = sandbox

        logger.info("Starting agent-server inside sandbox...")
        sandbox.process.create_session("agent-server")
        sandbox.process.execute_session_command(
            "agent-server",
            SessionExecuteRequest(
                command=(
                    f"openhands-agent-server --host 0.0.0.0 --port {self.server_port}"
                ),
                additional_properties={"runAsync": True},
            ),
        )

        preview = sandbox.get_preview_link(self.server_port)
        self._daytona_preview_token = getattr(preview, "token", None)

        self.host = preview.url.rstrip("/")
        self.api_key = self.session_api_key

        self.reset_client()
        self._wait_for_health()

    @tenacity.retry(
        stop=tenacity.stop_after_delay(120),
        wait=tenacity.wait_fixed(1),
        retry=tenacity.retry_if_exception_type(RuntimeError),
        reraise=True,
    )
    def _wait_for_health(self) -> None:
        try:
            resp = self.client.get("/health")
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(str(e)) from e

        if resp.status_code != 200:
            raise RuntimeError(f"Not ready: {resp.status_code}")

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._cleanup_sandbox()

    def _cleanup_sandbox(self) -> None:
        if self.keep_alive:
            return
        if self._sandbox is None:
            return

        try:
            daytona_config = DaytonaConfig(
                api_key=self.daytona_api_key,
                target=self.daytona_target,
                api_url=self.daytona_api_url,
            )
            daytona = Daytona(config=daytona_config)
            daytona.delete(self._sandbox)
        except Exception:
            logger.warning("Failed to delete Daytona sandbox", exc_info=True)
