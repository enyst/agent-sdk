import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from openhands.core.config import LLMConfig


def test_llm_config_defaults():
    """Test LLMConfig with default values."""
    config = LLMConfig()
    assert config.model == "claude-sonnet-4-20250514"
    assert config.api_key is None
    assert config.base_url is None
    assert config.api_version is None
    assert config.num_retries == 5
    assert config.retry_multiplier == 8
    assert config.retry_min_wait == 8
    assert config.retry_max_wait == 64
    assert config.timeout is None
    assert config.max_message_chars == 30_000
    assert config.temperature == 0.0
    assert config.top_p == 1.0
    assert config.top_k is None
    assert config.custom_llm_provider is None
    assert config.max_input_tokens is None
    assert config.max_output_tokens is None
    assert config.input_cost_per_token is None
    assert config.output_cost_per_token is None
    assert config.ollama_base_url is None
    assert config.drop_params is True
    assert config.modify_params is True
    assert config.disable_vision is None
    assert config.disable_stop_word is False
    assert config.caching_prompt is True
    assert config.log_completions is False
    assert config.custom_tokenizer is None
    assert config.native_tool_calling is None
    assert config.reasoning_effort == "high"  # Default for non-Gemini models
    assert config.seed is None
    assert config.safety_settings is None


def test_llm_config_minimal_customization_roundtrip():
    config = LLMConfig(
        model="gpt-4",
        api_key=SecretStr("k"),
        timeout=30,
        drop_params=False,
        modify_params=False,
        disable_stop_word=True,
        log_completions=True,
        native_tool_calling=True,
        seed=42,
    )

    assert config.model == "gpt-4"
    assert config.api_key and config.api_key.get_secret_value() == "k"
    assert config.timeout == 30
    assert config.drop_params is False
    assert config.modify_params is False
    assert config.disable_stop_word is True
    assert config.log_completions is True
    assert config.native_tool_calling is True
    assert config.seed == 42


def test_llm_config_secret_str():
    """Test that api_key is properly handled as SecretStr."""
    config = LLMConfig(api_key=SecretStr("secret-key"))
    assert config.api_key is not None and config.api_key.get_secret_value() == "secret-key"
    # Ensure the secret is not exposed in string representation
    assert "secret-key" not in str(config)


def test_llm_config_aws_credentials():
    """Test AWS credentials handling."""
    config = LLMConfig(
        aws_access_key_id=SecretStr("test-access-key"),
        aws_secret_access_key=SecretStr("test-secret-key"),
        aws_region_name="us-east-1",
    )
    assert config.aws_access_key_id is not None and config.aws_access_key_id.get_secret_value() == "test-access-key"
    assert config.aws_secret_access_key is not None and config.aws_secret_access_key.get_secret_value() == "test-secret-key"
    assert config.aws_region_name == "us-east-1"


def test_llm_config_openrouter_defaults():
    """Test OpenRouter default values."""
    config = LLMConfig()
    assert config.openrouter_site_url == "https://docs.all-hands.dev/"
    assert config.openrouter_app_name == "OpenHands"


def test_llm_config_post_init_openrouter_env_vars():
    """Test that OpenRouter environment variables are set in post_init."""
    with patch.dict(os.environ, {}, clear=True):
        LLMConfig(
            openrouter_site_url="https://custom.site.com",
            openrouter_app_name="CustomApp",
        )
        assert os.environ.get("OR_SITE_URL") == "https://custom.site.com"
        assert os.environ.get("OR_APP_NAME") == "CustomApp"


def test_llm_config_post_init_reasoning_effort_default():
    """Test that reasoning_effort is set to 'high' by default for non-Gemini models."""
    config = LLMConfig(model="gpt-4")
    assert config.reasoning_effort == "high"
    
    # Test that Gemini models don't get default reasoning_effort
    config = LLMConfig(model="gemini-2.5-pro-experimental")
    assert config.reasoning_effort is None


def test_llm_config_post_init_azure_api_version():
    """Test that Azure models get default API version."""
    config = LLMConfig(model="azure/gpt-4")
    assert config.api_version == "2024-12-01-preview"
    
    # Test that non-Azure models don't get default API version
    config = LLMConfig(model="gpt-4")
    assert config.api_version is None
    
    # Test that explicit API version is preserved
    config = LLMConfig(model="azure/gpt-4", api_version="custom-version")
    assert config.api_version == "custom-version"


def test_llm_config_post_init_aws_env_vars():
    """Test that AWS credentials are set as environment variables."""
    with patch.dict(os.environ, {}, clear=True):
        LLMConfig(
            aws_access_key_id=SecretStr("test-access-key"),
            aws_secret_access_key=SecretStr("test-secret-key"),
            aws_region_name="us-west-2",
        )
        assert os.environ.get("AWS_ACCESS_KEY_ID") == "test-access-key"
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "test-secret-key"
        assert os.environ.get("AWS_REGION_NAME") == "us-west-2"


def test_llm_config_log_completions_folder_default():
    """Test that log_completions_folder has a default value."""
    config = LLMConfig()
    assert config.log_completions_folder is not None
    assert "completions" in config.log_completions_folder


def test_llm_config_extra_fields_forbidden():
    """Test that extra fields are forbidden."""
    with pytest.raises(ValidationError) as exc_info:
        LLMConfig(invalid_field="should_not_work")  # type: ignore
    assert "Extra inputs are not permitted" in str(exc_info.value)


# Drop tests that merely assert Pydantic accepts negative numbers; not product behavior.


def test_llm_config_model_passthrough():
    # Spot-check a couple of variants only; we do not need to exhaustively enumerate
    for m in ["gpt-4", "azure/gpt-4", "gemini-2.5-pro-experimental"]:
        assert LLMConfig(model=m).model == m


def test_llm_config_boolean_fields_small():
    cfg = LLMConfig(drop_params=True, modify_params=False, disable_stop_word=False, caching_prompt=True)
    assert (cfg.drop_params, cfg.modify_params, cfg.disable_stop_word, cfg.caching_prompt) == (True, False, False, True)