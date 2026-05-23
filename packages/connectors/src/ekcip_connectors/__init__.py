"""Connector plane: external system adapters and MCP routing metadata."""

from ekcip_connectors.mcp_registry import McpConnectorRegistry, get_mcp_registry
from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort

__all__ = [
    "ConnectorCapability",
    "ConnectorHealth",
    "ConnectorPort",
    "McpConnectorRegistry",
    "get_mcp_registry",
]
