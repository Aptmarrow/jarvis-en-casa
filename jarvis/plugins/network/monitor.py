from __future__ import annotations

from typing import Any
from jarvis.plugins.base import Plugin, tool

class NetworkMonitorPlugin(Plugin):
    name = "network.monitor"
    description = "Monitors device presence on local network"

    @tool(
        description="Returns list of known monitored devices"
    )
    async def get_monitored_devices(self) -> dict[str, Any]:
        return {"devices": []}
