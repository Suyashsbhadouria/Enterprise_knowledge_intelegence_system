from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorCapability(str, Enum):
    READ = "read"
    WRITE = "write"
    SEARCH = "search"


class ConnectorHealth(BaseModel):
    name: str
    ready: bool
    mode: str
    detail: str | None = None


class ConnectorPort(ABC):
    """Runtime connector contract. Phase 1+ implements HTTP/SDK; MCP used in Cursor agent workflows."""

    name: str
    capabilities: tuple[ConnectorCapability, ...] = (ConnectorCapability.READ,)

    @abstractmethod
    async def health(self) -> ConnectorHealth:
        raise NotImplementedError

    @abstractmethod
    async def ping(self) -> dict[str, Any]:
        raise NotImplementedError
