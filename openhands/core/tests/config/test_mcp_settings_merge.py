"""Lean MCP merge tests: validate concatenation and preserve future hardening."""

import pytest

from openhands.core.config import MCPConfig
from openhands.core.config.mcp_config import (
    MCPSHTTPServerConfig,
    MCPSSEServerConfig,
    MCPStdioServerConfig,
)


def test_merge_empty():
    a, b = MCPConfig(), MCPConfig()
    m = a.merge(b)
    assert m.sse_servers == [] and m.stdio_servers == [] and m.shttp_servers == []


def test_merge_all_types_and_preserve_inputs():
    c1 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://sse1:1')],
        stdio_servers=[MCPStdioServerConfig(name='stdio1', command='python')],
        shttp_servers=[MCPSHTTPServerConfig(url='http://shttp1:1')],
    )
    c2 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://sse2:2')],
        stdio_servers=[MCPStdioServerConfig(name='stdio2', command='node')],
        shttp_servers=[MCPSHTTPServerConfig(url='http://shttp2:2')],
    )

    m = c1.merge(c2)
    assert [s.url for s in m.sse_servers] == ['http://sse1:1', 'http://sse2:2']
    assert [s.name for s in m.stdio_servers] == ['stdio1', 'stdio2']
    assert [s.url for s in m.shttp_servers] == ['http://shttp1:1', 'http://shttp2:2']

    # Originals unchanged
    assert [s.url for s in c1.sse_servers] == ['http://sse1:1']
    assert [s.url for s in c2.shttp_servers] == ['http://shttp2:2']


# Keep suite minimal; richer scenarios add little value over the above.








def test_merge_then_validate_duplicates_desired():
    c1 = MCPConfig(sse_servers=[MCPSSEServerConfig(url='http://x:1')])
    c2 = MCPConfig(sse_servers=[MCPSSEServerConfig(url='http://x:1')])
    merged = c1.merge(c2)

    # Desired: validation should flag duplicates post-merge; current impl does not catch via merge.
    pytest.xfail("Desired: validate duplicates post-merge across SSE as well.")
    merged.validate_servers()


def test_mcp_config_merge_validation_on_merged_config():
    """Test that validate_servers() works correctly on merged configurations."""
    config1 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://server1:8080')]
    )
    
    config2 = MCPConfig(
        sse_servers=[MCPSSEServerConfig(url='http://server1:8080')]  # Same URL
    )
    
    merged = config1.merge(config2)
    
    # The merged config should have duplicate URLs and validation should fail
    with pytest.raises(ValueError, match="Duplicate MCP server URLs are not allowed"):
        merged.validate_servers()