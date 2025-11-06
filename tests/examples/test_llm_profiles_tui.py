import types
from pathlib import Path
from typing import Any

import pytest

# Import the CLI module
from examples.llm_profiles_tui import cli as tui


class DummyLLM:
    def __init__(self, model: str, usage_id: str = "agent") -> None:
        self.model = model
        self.usage_id = usage_id
        self.profile_id: str | None = None

    def model_dump(self, exclude_none: bool = False):
        return {"model": self.model, "usage_id": self.usage_id}


class DummyConversation:
    def __init__(self) -> None:
        self._llm = DummyLLM(model="gpt-4o-mini")
        self.agent = types.SimpleNamespace(llm=self._llm)
        self.switched_to: str | None = None
        self.messages: list[str] = []

    def switch_llm(self, profile_id: str) -> None:
        # Emulate a switch by replacing agent.llm
        self.switched_to = profile_id
        self._llm = DummyLLM(model=f"model:{profile_id}")
        self.agent = types.SimpleNamespace(llm=self._llm)

    def send_message(self, text: str) -> None:
        self.messages.append(text)

    def run(self) -> None:
        # No-op for tests
        return None

    def close(self) -> None:  # pragma: no cover - used by app cleanup
        return None


class DummyRegistry:
    def __init__(self, tmpdir: Path) -> None:
        self.tmpdir = Path(tmpdir)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, dict[str, Any]] = {}

    def get_profile_path(self, profile_id: str) -> Path:
        return self.tmpdir / f"{profile_id}.json"

    def save_profile(self, profile_id: str, llm, include_secrets: bool = False):
        self._profiles[profile_id] = {"model": llm.model, "usage_id": llm.usage_id}
        path = self.get_profile_path(profile_id)
        path.write_text("{}")
        return path

    def list_profiles(self) -> list[str]:
        return sorted(p.stem for p in self.tmpdir.glob("*.json"))

    def load_profile(self, profile_id: str):
        data = self._profiles[profile_id]
        llm = DummyLLM(model=data["model"], usage_id=data["usage_id"])
        llm.profile_id = profile_id
        return llm


@pytest.fixture
def dummy_ctx(tmp_path):
    conv = DummyConversation()
    reg = DummyRegistry(tmp_path)
    return tui.AppContext(conversation=conv, registry=reg)


def test_parse_keyvals_coerces_types(monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "secret")
    data = tui.parse_keyvals(
        [
            "model=openai/gpt-4o-mini",
            "temperature=0.3",
            "top_p=0.9",
            "log_completions=false",
            "api_key=ENV[MY_API_KEY]",
        ]
    )
    assert data["model"] == "openai/gpt-4o-mini"
    assert isinstance(data["temperature"], float) and data["temperature"] == 0.3
    assert isinstance(data["top_p"], float) and data["top_p"] == 0.9
    assert data["log_completions"] is False
    assert hasattr(data["api_key"], "get_secret_value")


def test_cmd_model_and_list_and_show(dummy_ctx):
    out = tui.cmd_model(
        dummy_ctx, ["fast", "model=openai/gpt-4o-mini", "temperature=0.2"]
    )
    assert "Saved profile 'fast'" in out

    out = tui.cmd_list(dummy_ctx, [])
    assert "fast" in out

    out = tui.cmd_show(dummy_ctx, ["fast"])
    assert "gpt-4o-mini" in out


def test_cmd_profile_switches_conversation(dummy_ctx):
    tui.cmd_model(dummy_ctx, ["alt", "model=openai/gpt-5-mini"])
    out = tui.cmd_profile(dummy_ctx, ["alt"])
    assert "Switched to profile 'alt'" in out
    assert dummy_ctx.conversation.switched_to == "alt"
    assert dummy_ctx.conversation.agent.llm.model == "model:alt"


def test_cmd_delete_removes_profile(dummy_ctx):
    tui.cmd_model(dummy_ctx, ["gone", "model=openai/gpt-4o-mini"])
    assert "gone" in dummy_ctx.registry.list_profiles()
    out = tui.cmd_delete(dummy_ctx, ["gone"])
    assert "Deleted profile 'gone'" in out
    assert "gone" not in dummy_ctx.registry.list_profiles()


def test_cmd_save_saves_current_llm(dummy_ctx):
    out = tui.cmd_save(dummy_ctx, ["current"])
    assert "Saved current LLM" in out
    assert "current" in dummy_ctx.registry.list_profiles()


def test_run_loop_handles_commands_and_chat(monkeypatch, dummy_ctx):
    # Prepare a sequence of inputs: /help, chat, unknown, /exit
    inputs = iter(["/help", "hello there", "/what", "/exit"])
    outputs: list[str] = []

    def fake_input(prompt: str) -> str:
        return next(inputs)

    def fake_print(*args, **kwargs):
        outputs.append(" ".join(str(a) for a in args))

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("builtins.print", fake_print)

    tui.run_loop(dummy_ctx)

    # Check that chat message was sent and run was called without errors
    assert dummy_ctx.conversation.messages == ["hello there"]
    # Ensure help text appeared and unknown command was reported
    assert any("Commands:" in line for line in outputs)
    assert any("Unknown command" in line for line in outputs)
