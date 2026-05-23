import os
from typing import Any

from ekcip_connectors.ports import ConnectorCapability, ConnectorHealth, ConnectorPort


class StubConnector(ConnectorPort):
    """Phase 0: reports readiness from env presence; real HTTP clients arrive in Phase 1+."""

    def __init__(
        self,
        name: str,
        env_keys: tuple[str, ...],
        *,
        capabilities: tuple[ConnectorCapability, ...] = (ConnectorCapability.READ,),
    ) -> None:
        self.name = name
        self._env_keys = env_keys
        self.capabilities = capabilities

    def _configured(self) -> bool:
        return all(os.getenv(key) for key in self._env_keys)

    async def health(self) -> ConnectorHealth:
        configured = self._configured()
        return ConnectorHealth(
            name=self.name,
            ready=configured,
            mode="runtime_stub",
            detail=None if configured else f"Missing env: {', '.join(self._env_keys)}",
        )

    async def ping(self) -> dict[str, Any]:
        health = await self.health()
        return {"name": self.name, "ready": health.ready, "mode": health.mode}
