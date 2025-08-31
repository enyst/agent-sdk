import pytest
from pydantic import ValidationError

from openhands.core.config import MCPConfig
from openhands.core.config.mcp_config import (
    MCPSHTTPServerConfig,
    MCPSSEServerConfig,
    MCPStdioServerConfig,
)


# ---- SSE/SHTTP URL validation (parametrized) ----
@pytest.mark.parametrize(
    "url",
    [
        "http://server1:8080",
        "https://server1:8080",
        "ws://server1:8080",
        "wss://server1:8080",
    ],
)
@pytest.mark.parametrize("cls", [MCPSSEServerConfig, MCPSHTTPServerConfig])
def test_mcp_server_url_valid(cls, url):
    cfg = cls(url=url)
    assert cfg.url == url


@pytest.mark.parametrize("bad", ["", "not_a_url", "ftp://server", "file://server", "tcp://server"]) 
@pytest.mark.parametrize("cls", [MCPSSEServerConfig, MCPSHTTPServerConfig])
def test_mcp_server_url_invalid(cls, bad):
    with pytest.raises(ValidationError):
        cls(url=bad)


def test_stdio_name_and_command_validation():
    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="", command="python")
    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="bad name with spaces", command="python")

    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="srv", command="")
    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="srv", command="python -m server")


def test_stdio_args_parsing_and_invalid_quotes():
    assert MCPStdioServerConfig(name="s", command="python", args="arg1 arg2").args == [  # type: ignore[arg-type]
        "arg1",
        "arg2",
    ]
    assert MCPStdioServerConfig(name="s", command="python", args="--config 'x y'").args == [  # type: ignore[arg-type]
        "--config",
        "x y",
    ]
    assert MCPStdioServerConfig(name="s", command="python", args="").args == []  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="s", command="python", args='--config "unmatched')  # type: ignore[arg-type]


def test_stdio_env_parsing_and_invalid():
    assert MCPStdioServerConfig(name="s", command="python", env="DEBUG=true,PORT=8080").env == {  # type: ignore[arg-type]
        "DEBUG": "true",
        "PORT": "8080",
    }
    assert MCPStdioServerConfig(name="s", command="python", env="").env == {}  # type: ignore[arg-type]
    assert MCPStdioServerConfig(name="s", command="python", env="DEBUG=true").env == {  # type: ignore[arg-type]
        "DEBUG": "true"
    }

    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="s", command="python", env="INVALID")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="s", command="python", env="=value")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MCPStdioServerConfig(name="s", command="python", env="9BAD=value")  # type: ignore[arg-type]


def test_stdio_equality_semantics():
    a = MCPStdioServerConfig(
        name="srv",
        command="python",
        args=["--v", "--port=8080"],
        env={"PORT": "8080", "DEBUG": "true"},
    )
    b = MCPStdioServerConfig(
        name="srv",
        command="python",
        args=["--v", "--port=8080"],
        env={"DEBUG": "true", "PORT": "8080"},
    )
    c = MCPStdioServerConfig(
        name="srv",
        command="python",
        args=["--port=8080", "--v"],
        env={"DEBUG": "true", "PORT": "8080"},
    )

    assert a == b
    assert a != c
    assert a != "not-a-config"


def test_mcp_shttp_server_config_basic():
    """Test basic MCPSHTTPServerConfig."""
    config = MCPSHTTPServerConfig(url='http://server1:8080')
    assert config.url == 'http://server1:8080'
    assert config.api_key is None


def test_mcp_shttp_server_config_with_api_key():
    """Test MCPSHTTPServerConfig with API key."""
    config = MCPSHTTPServerConfig(url='http://server1:8080', api_key='test-api-key')
    assert config.url == 'http://server1:8080'
    assert config.api_key == 'test-api-key'


def test_mcp_shttp_server_config_invalid_url():
    """Test MCPSHTTPServerConfig with invalid URL format."""
    with pytest.raises(ValidationError) as exc_info:
        MCPSHTTPServerConfig(url='not_a_url')
    assert 'URL must include a scheme' in str(exc_info.value)


def test_mcp_config_empty():
    """Test empty MCPConfig."""
    config = MCPConfig()
    assert config.sse_servers == []
    assert config.stdio_servers == []
    assert config.shttp_servers == []


def test_mcp_config_with_all_server_types_minimal():
    sse_server = MCPSSEServerConfig(url='http://sse-server:8080')
    stdio_server = MCPStdioServerConfig(name='stdio-server', command='python')
    shttp_server = MCPSHTTPServerConfig(url='http://shttp-server:8080')

    cfg = MCPConfig(
        sse_servers=[sse_server],
        stdio_servers=[stdio_server],
        shttp_servers=[shttp_server],
    )

    assert [s.url for s in cfg.sse_servers] == ['http://sse-server:8080']
    assert [s.name for s in cfg.stdio_servers] == ['stdio-server']
    assert [s.url for s in cfg.shttp_servers] == ['http://shttp-server:8080']


def test_mcp_config_validate_servers():
    """Test MCPConfig server validation."""
    # Valid configuration should not raise
    config = MCPConfig(
        sse_servers=[
            MCPSSEServerConfig(url='http://server1:8080'),
            MCPSSEServerConfig(url='http://server2:8080'),
        ]
    )
    config.validate_servers()  # Should not raise
    
    # Duplicate URLs in sse_servers should raise
    config = MCPConfig(
        sse_servers=[
            MCPSSEServerConfig(url='http://server1:8080'),
            MCPSSEServerConfig(url='http://server1:8080'),
        ]
    )
    with pytest.raises(ValueError) as exc_info:
        config.validate_servers()
    assert 'Duplicate MCP server URLs are not allowed' in str(exc_info.value)


@pytest.mark.xfail(reason="Desired: detect shttp duplicate URLs. Current implementation only checks sse.")
def test_mcp_validate_servers_duplicates_shttp_desired():
    cfg = MCPConfig(
        shttp_servers=[
            MCPSHTTPServerConfig(url='http://server1:8080'),
            MCPSHTTPServerConfig(url='http://server1:8080'),
        ]
    )
    cfg.validate_servers()


@pytest.mark.xfail(reason="Desired: detect cross-type duplicate URLs. Current implementation does not.")
def test_mcp_validate_servers_cross_type_duplicates_desired():
    cfg = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://server1:8080')],
        shttp_servers=[MCPSHTTPServerConfig(url='http://server1:8080')],
    )
    cfg.validate_servers()


def test_mcp_config_from_toml_section_basic():
    """Test MCPConfig.from_toml_section with basic data."""
    data = {
        'sse_servers': ['http://server1:8080'],
    }
    result = MCPConfig.from_toml_section(data)
    assert 'mcp' in result
    assert len(result['mcp'].sse_servers) == 1
    assert result['mcp'].sse_servers[0].url == 'http://server1:8080'


def test_mcp_config_from_toml_section_with_stdio():
    """Test MCPConfig.from_toml_section with stdio servers."""
    data = {
        'sse_servers': ['http://server1:8080'],
        'stdio_servers': [
            {
                'name': 'test-server',
                'command': 'python',
                'args': ['-m', 'server'],
                'env': {'DEBUG': 'true'},
            }
        ],
    }
    result = MCPConfig.from_toml_section(data)
    assert 'mcp' in result
    assert len(result['mcp'].sse_servers) == 1
    assert len(result['mcp'].stdio_servers) == 1
    assert result['mcp'].stdio_servers[0].name == 'test-server'
    assert result['mcp'].stdio_servers[0].command == 'python'
    assert result['mcp'].stdio_servers[0].args == ['-m', 'server']
    assert result['mcp'].stdio_servers[0].env == {'DEBUG': 'true'}


def test_mcp_config_from_toml_section_with_shttp():
    """Test MCPConfig.from_toml_section with SHTTP servers."""
    data = {
        'shttp_servers': [
            {'url': 'http://server1:8080', 'api_key': 'test-key'}
        ],
    }
    result = MCPConfig.from_toml_section(data)
    assert 'mcp' in result
    assert len(result['mcp'].shttp_servers) == 1
    assert result['mcp'].shttp_servers[0].url == 'http://server1:8080'
    assert result['mcp'].shttp_servers[0].api_key == 'test-key'


def test_mcp_config_from_toml_section_invalid():
    """Test MCPConfig.from_toml_section with invalid data."""
    data = {
        'sse_servers': ['not_a_url'],
    }
    with pytest.raises(ValueError) as exc_info:
        MCPConfig.from_toml_section(data)
    assert 'URL must include a scheme' in str(exc_info.value)


def test_mcp_config_merge():
    """Test MCPConfig merge functionality."""
    config1 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://server1:8080')],
        stdio_servers=[MCPStdioServerConfig(name='server1', command='python')],
        shttp_servers=[MCPSHTTPServerConfig(url='http://shttp1:8080')],
    )
    
    config2 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://server2:8080')],
        stdio_servers=[MCPStdioServerConfig(name='server2', command='node')],
        shttp_servers=[MCPSHTTPServerConfig(url='http://shttp2:8080')],
    )
    
    merged = config1.merge(config2)
    
    assert len(merged.sse_servers) == 2
    assert len(merged.stdio_servers) == 2
    assert len(merged.shttp_servers) == 2
    assert merged.sse_servers[0].url == 'http://server1:8080'
    assert merged.sse_servers[1].url == 'http://server2:8080'
    assert merged.stdio_servers[0].name == 'server1'
    assert merged.stdio_servers[1].name == 'server2'
    assert merged.shttp_servers[0].url == 'http://shttp1:8080'
    assert merged.shttp_servers[1].url == 'http://shttp2:8080'


def test_mcp_config_extra_fields_forbidden():
    """Test that extra fields are forbidden in MCPConfig."""
    with pytest.raises(ValidationError) as exc_info:
        MCPConfig(extra_field='value')  # type: ignore
    assert 'Extra inputs are not permitted' in str(exc_info.value)


def test_mcp_config_complex_urls():
    """Test MCPConfig with complex URLs."""
    config = MCPConfig(
        sse_servers=[
            MCPSSEServerConfig(url='https://user:pass@server1:8080/path?query=1'),
            MCPSSEServerConfig(url='wss://server2:8443/ws'),
            MCPSSEServerConfig(url='http://subdomain.example.com:9090'),
        ]
    )
    config.validate_servers()  # Should not raise any exception
    assert len(config.sse_servers) == 3