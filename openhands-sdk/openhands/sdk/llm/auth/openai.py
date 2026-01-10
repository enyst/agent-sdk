"""OpenAI subscription-based authentication via OAuth.

This module implements OAuth PKCE flow for authenticating with OpenAI's ChatGPT
service, allowing users with ChatGPT Plus/Pro subscriptions to use Codex models
without consuming API credits.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import time
import webbrowser
from typing import TYPE_CHECKING, Any

import httpx

from openhands.sdk.llm.auth.credentials import CredentialStore, OAuthCredentials
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM

logger = get_logger(__name__)

# OAuth configuration for OpenAI Codex
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ISSUER = "https://auth.openai.com"
CODEX_API_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_OAUTH_PORT = 1455
OAUTH_TIMEOUT_SECONDS = 300  # 5 minutes

# Models available via ChatGPT subscription (not API)
OPENAI_CODEX_MODELS = frozenset(
    {
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5.2",
        "gpt-5.2-codex",
    }
)


class PKCECodes:
    """PKCE (Proof Key for Code Exchange) codes for OAuth."""

    def __init__(self, verifier: str, challenge: str):
        self.verifier = verifier
        self.challenge = challenge

    @classmethod
    def generate(cls) -> PKCECodes:
        """Generate PKCE verifier and challenge."""
        # Generate a random verifier (43-128 characters)
        verifier = secrets.token_urlsafe(32)

        # Create SHA-256 hash of verifier
        digest = hashlib.sha256(verifier.encode()).digest()

        # Base64url encode the hash
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        return cls(verifier=verifier, challenge=challenge)


def _generate_state() -> str:
    """Generate a random state parameter for OAuth."""
    return secrets.token_urlsafe(32)


def _build_authorize_url(redirect_uri: str, pkce: PKCECodes, state: str) -> str:
    """Build the OAuth authorization URL."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email offline_access",
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "openhands",
    }
    return f"{ISSUER}/oauth/authorize?{urlencode(params)}"


async def _exchange_code_for_tokens(
    code: str, redirect_uri: str, pkce: PKCECodes
) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": CLIENT_ID,
                "code_verifier": pkce.verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise RuntimeError(f"Token exchange failed: {response.status_code}")
        return response.json()


async def _refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh the access token using a refresh token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if not response.is_success:
            raise RuntimeError(f"Token refresh failed: {response.status_code}")
        return response.json()


# HTML templates for OAuth callback
_HTML_SUCCESS = """<!DOCTYPE html>
<html>
<head>
  <title>OpenHands - Authorization Successful</title>
  <style>
    body {
      font-family: system-ui, -apple-system, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
      margin: 0;
      background: #1a1a2e;
      color: #eee;
    }
    .container { text-align: center; padding: 2rem; }
    h1 { color: #4ade80; margin-bottom: 1rem; }
    p { color: #aaa; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Successful</h1>
    <p>You can close this window and return to OpenHands.</p>
  </div>
  <script>setTimeout(() => window.close(), 2000);</script>
</body>
</html>"""

_HTML_ERROR = """<!DOCTYPE html>
<html>
<head>
  <title>OpenHands - Authorization Failed</title>
  <style>
    body {
      font-family: system-ui, -apple-system, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
      margin: 0;
      background: #1a1a2e;
      color: #eee;
    }
    .container { text-align: center; padding: 2rem; }
    h1 { color: #f87171; margin-bottom: 1rem; }
    p { color: #aaa; }
    .error {
      color: #fca5a5;
      font-family: monospace;
      margin-top: 1rem;
      padding: 1rem;
      background: rgba(248,113,113,0.1);
      border-radius: 0.5rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Authorization Failed</h1>
    <p>An error occurred during authorization.</p>
    <div class="error">{error}</div>
  </div>
</body>
</html>"""


class OpenAISubscriptionAuth:
    """Handle OAuth authentication for OpenAI ChatGPT subscription access."""

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        oauth_port: int = DEFAULT_OAUTH_PORT,
    ):
        """Initialize the OpenAI subscription auth handler.

        Args:
            credential_store: Optional custom credential store.
            oauth_port: Port for the local OAuth callback server.
        """
        self._credential_store = credential_store or CredentialStore()
        self._oauth_port = oauth_port

    @property
    def vendor(self) -> str:
        """Get the vendor name."""
        return "openai"

    def get_credentials(self) -> OAuthCredentials | None:
        """Get stored credentials if they exist."""
        return self._credential_store.get(self.vendor)

    def has_valid_credentials(self) -> bool:
        """Check if valid (non-expired) credentials exist."""
        creds = self.get_credentials()
        return creds is not None and not creds.is_expired()

    async def refresh_if_needed(self) -> OAuthCredentials | None:
        """Refresh credentials if they are expired.

        Returns:
            Updated credentials, or None if no credentials exist.
        """
        creds = self.get_credentials()
        if creds is None:
            return None

        if not creds.is_expired():
            return creds

        logger.info("Refreshing OpenAI access token")
        try:
            tokens = await _refresh_access_token(creds.refresh_token)
            updated = self._credential_store.update_tokens(
                vendor=self.vendor,
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token"),
                expires_in=tokens.get("expires_in", 3600),
            )
            return updated
        except Exception as e:
            logger.warning(f"Failed to refresh token: {e}")
            # Token refresh failed, credentials are invalid
            self._credential_store.delete(self.vendor)
            return None

    async def login(self, open_browser: bool = True) -> OAuthCredentials:
        """Perform OAuth login flow.

        This starts a local HTTP server to handle the OAuth callback,
        opens the browser for user authentication, and waits for the
        callback with the authorization code.

        Args:
            open_browser: Whether to automatically open the browser.

        Returns:
            The obtained OAuth credentials.

        Raises:
            RuntimeError: If the OAuth flow fails or times out.
        """
        pkce = PKCECodes.generate()
        state = _generate_state()
        redirect_uri = f"http://localhost:{self._oauth_port}/auth/callback"
        auth_url = _build_authorize_url(redirect_uri, pkce, state)

        # Create a future to receive the callback result
        callback_future: asyncio.Future[dict[str, Any]] = asyncio.Future()

        # Start the callback server
        server = await self._start_callback_server(pkce, state, callback_future)

        try:
            # Open browser for authentication
            if open_browser:
                logger.info("Opening browser for OpenAI authentication...")
                webbrowser.open(auth_url)
            else:
                logger.info(
                    f"Please open the following URL in your browser:\n{auth_url}"
                )

            # Wait for callback with timeout
            try:
                tokens = await asyncio.wait_for(
                    callback_future, timeout=OAUTH_TIMEOUT_SECONDS
                )
            except TimeoutError:
                raise RuntimeError(
                    "OAuth callback timeout - authorization took too long"
                )

            # Save credentials
            expires_at = int(time.time() * 1000) + (
                tokens.get("expires_in", 3600) * 1000
            )
            credentials = OAuthCredentials(
                vendor=self.vendor,
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                expires_at=expires_at,
            )
            self._credential_store.save(credentials)
            logger.info("OpenAI OAuth login successful")
            return credentials

        finally:
            server.close()
            await server.wait_closed()

    async def _start_callback_server(
        self,
        pkce: PKCECodes,
        expected_state: str,
        callback_future: asyncio.Future[dict[str, Any]],
    ) -> asyncio.Server:
        """Start the local HTTP server for OAuth callback."""
        redirect_uri = f"http://localhost:{self._oauth_port}/auth/callback"

        async def handle_request(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                # Read the HTTP request
                request_line = await reader.readline()
                request_str = request_line.decode()

                # Parse the request path
                parts = request_str.split()
                if len(parts) < 2:
                    return

                path = parts[1]

                # Read headers (we don't need them, but must consume them)
                while True:
                    line = await reader.readline()
                    if line == b"\r\n" or line == b"\n" or line == b"":
                        break

                # Handle the callback
                if path.startswith("/auth/callback"):
                    await self._handle_callback(
                        path,
                        pkce,
                        expected_state,
                        redirect_uri,
                        callback_future,
                        writer,
                    )
                else:
                    # 404 for other paths
                    response = "HTTP/1.1 404 Not Found\r\n\r\nNot Found"
                    writer.write(response.encode())

                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(
            handle_request, "localhost", self._oauth_port
        )
        logger.debug(f"OAuth callback server started on port {self._oauth_port}")
        return server

    async def _handle_callback(
        self,
        path: str,
        pkce: PKCECodes,
        expected_state: str,
        redirect_uri: str,
        callback_future: asyncio.Future[dict[str, Any]],
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle the OAuth callback request."""
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(path)
        params = parse_qs(parsed.query)

        # Check for errors
        if "error" in params:
            error_msg = params.get("error_description", params["error"])[0]
            self._send_html_response(writer, _HTML_ERROR.format(error=error_msg))
            if not callback_future.done():
                callback_future.set_exception(RuntimeError(error_msg))
            return

        # Get authorization code
        code_list = params.get("code")
        if not code_list:
            error_msg = "Missing authorization code"
            self._send_html_response(writer, _HTML_ERROR.format(error=error_msg), 400)
            if not callback_future.done():
                callback_future.set_exception(RuntimeError(error_msg))
            return

        # Verify state
        state_list = params.get("state")
        if not state_list or state_list[0] != expected_state:
            error_msg = "Invalid state - potential CSRF attack"
            self._send_html_response(writer, _HTML_ERROR.format(error=error_msg), 400)
            if not callback_future.done():
                callback_future.set_exception(RuntimeError(error_msg))
            return

        # Exchange code for tokens
        try:
            tokens = await _exchange_code_for_tokens(code_list[0], redirect_uri, pkce)
            self._send_html_response(writer, _HTML_SUCCESS)
            if not callback_future.done():
                callback_future.set_result(tokens)
        except Exception as e:
            error_msg = str(e)
            self._send_html_response(writer, _HTML_ERROR.format(error=error_msg), 500)
            if not callback_future.done():
                callback_future.set_exception(e)

    def _send_html_response(
        self, writer: asyncio.StreamWriter, html: str, status: int = 200
    ) -> None:
        """Send an HTML response."""
        status_text = {200: "OK", 400: "Bad Request", 500: "Internal Server Error"}
        response = (
            f"HTTP/1.1 {status} {status_text.get(status, 'Error')}\r\n"
            f"Content-Type: text/html\r\n"
            f"Content-Length: {len(html)}\r\n"
            f"\r\n"
            f"{html}"
        )
        writer.write(response.encode())

    def logout(self) -> bool:
        """Remove stored credentials.

        Returns:
            True if credentials were removed, False if none existed.
        """
        return self._credential_store.delete(self.vendor)

    def create_llm(
        self,
        model: str = "gpt-5.2-codex",
        credentials: OAuthCredentials | None = None,
        **llm_kwargs: Any,
    ) -> LLM:
        """Create an LLM instance configured for Codex subscription access.

        Args:
            model: The model to use (must be in OPENAI_CODEX_MODELS).
            credentials: OAuth credentials to use. If None, uses stored credentials.
            **llm_kwargs: Additional arguments to pass to LLM constructor.

        Returns:
            An LLM instance configured for Codex access.

        Raises:
            ValueError: If the model is not supported or no credentials available.
        """
        from openhands.sdk.llm.llm import LLM

        if model not in OPENAI_CODEX_MODELS:
            raise ValueError(
                f"Model '{model}' is not supported for subscription access. "
                f"Supported models: {', '.join(sorted(OPENAI_CODEX_MODELS))}"
            )

        creds = credentials or self.get_credentials()
        if creds is None:
            raise ValueError(
                "No credentials available. Call login() first or provide credentials."
            )

        # Create LLM with Codex configuration
        uname = os.uname()
        user_agent = f"openhands-sdk ({uname.sysname}; {uname.machine})"
        return LLM(
            model=f"openai/{model}",
            base_url=CODEX_API_ENDPOINT.rsplit("/", 1)[0],  # Remove /responses
            api_key=creds.access_token,
            extra_headers={
                "originator": "openhands",
                "User-Agent": user_agent,
            },
            # Codex-specific settings
            temperature=None,  # Use model default
            **llm_kwargs,
        )


async def subscription_login_async(
    vendor: str = "openai",
    model: str = "gpt-5.2-codex",
    force_login: bool = False,
    open_browser: bool = True,
    **llm_kwargs: Any,
) -> LLM:
    """Authenticate with a subscription and return an LLM instance.

    This is the main entry point for subscription-based LLM access.
    It handles credential caching, token refresh, and login flow.

    Args:
        vendor: The vendor/provider (currently only "openai" is supported).
        model: The model to use.
        force_login: If True, always perform a fresh login.
        open_browser: Whether to automatically open the browser for login.
        **llm_kwargs: Additional arguments to pass to LLM constructor.

    Returns:
        An LLM instance configured for subscription access.

    Raises:
        ValueError: If the vendor is not supported.
        RuntimeError: If authentication fails.

    Example:
        >>> import asyncio
        >>> from openhands.sdk.llm.auth import subscription_login_async
        >>> llm = asyncio.run(subscription_login_async(model="gpt-5.2-codex"))
    """
    if vendor != "openai":
        raise ValueError(
            f"Vendor '{vendor}' is not supported. Only 'openai' is supported."
        )

    auth = OpenAISubscriptionAuth()

    # Check for existing valid credentials
    if not force_login:
        creds = await auth.refresh_if_needed()
        if creds is not None:
            logger.info("Using existing OpenAI credentials")
            return auth.create_llm(model=model, credentials=creds, **llm_kwargs)

    # Perform login
    creds = await auth.login(open_browser=open_browser)
    return auth.create_llm(model=model, credentials=creds, **llm_kwargs)


def subscription_login(
    vendor: str = "openai",
    model: str = "gpt-5.2-codex",
    force_login: bool = False,
    open_browser: bool = True,
    **llm_kwargs: Any,
) -> LLM:
    """Synchronous wrapper for subscription_login_async.

    See subscription_login_async for full documentation.
    """
    return asyncio.run(
        subscription_login_async(
            vendor=vendor,
            model=model,
            force_login=force_login,
            open_browser=open_browser,
            **llm_kwargs,
        )
    )
