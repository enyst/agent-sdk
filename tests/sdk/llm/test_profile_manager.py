import json

from pydantic import SecretStr

from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.llm_registry import LLMRegistry
from openhands.sdk.llm.profile_manager import ProfileManager


def test_list_profiles_returns_sorted_names(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")

    assert manager.list_profiles() == ["a", "b"]


def test_save_profile_excludes_secret_fields(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)
    llm = LLM(
        model="gpt-4o-mini",
        service_id="service",
        api_key=SecretStr("secret"),
        aws_access_key_id=SecretStr("id"),
        aws_secret_access_key=SecretStr("value"),
    )

    path = manager.save_profile("sample", llm)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["profile_id"] == "sample"
    assert data["service_id"] == "service"
    assert "api_key" not in data
    assert "aws_access_key_id" not in data
    assert "aws_secret_access_key" not in data


def test_save_profile_can_include_secret_fields(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)
    llm = LLM(
        model="gpt-4o-mini",
        service_id="service",
        api_key=SecretStr("secret"),
        aws_access_key_id=SecretStr("id"),
        aws_secret_access_key=SecretStr("value"),
    )

    path = manager.save_profile("sample", llm, include_secrets=True)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["api_key"] == "secret"
    assert data["aws_access_key_id"] == "id"
    assert data["aws_secret_access_key"] == "value"


def test_load_profile_assigns_profile_id_when_missing(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)
    profile_path = tmp_path / "foo.json"
    profile_path.write_text(
        json.dumps({"model": "gpt-4o-mini", "service_id": "svc"}),
        encoding="utf-8",
    )

    llm = manager.load_profile("foo")

    assert llm.profile_id == "foo"
    assert llm.service_id == "svc"


def test_register_all_skips_invalid_and_duplicate_profiles(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)
    registry = LLMRegistry()

    llm = LLM(model="gpt-4o-mini", service_id="shared")
    manager.save_profile("alpha", llm)

    duplicate_data = llm.model_dump(exclude_none=True)
    duplicate_data["profile_id"] = "beta"
    (tmp_path / "beta.json").write_text(
        json.dumps(duplicate_data),
        encoding="utf-8",
    )

    (tmp_path / "gamma.json").write_text("{", encoding="utf-8")

    manager.register_all(registry)

    assert registry.list_services() == ["shared"]


def test_validate_profile_reports_errors(tmp_path):
    manager = ProfileManager(base_dir=tmp_path)

    ok, errors = manager.validate_profile({"model": "gpt-4o-mini", "service_id": "svc"})
    assert ok
    assert errors == []

    ok, errors = manager.validate_profile({"service_id": "svc"})
    assert not ok
    assert any("model" in message for message in errors)
