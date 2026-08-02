from __future__ import annotations

import asyncio
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class ServicesPlugin(Plugin):
    name = "system.services"
    description = "Systemd service control"

    @tool("Get status of a systemd service", parameters=[
        ToolParameter(name="service_name", type="string", description="Name of the systemd service")
    ])
    async def get_status(self, service_name: str) -> dict[str, Any]:
        try:
            active_proc = await asyncio.create_subprocess_exec(
                "systemctl", "is-active", service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            active_stdout, _ = await active_proc.communicate()
            is_active = (active_proc.returncode == 0)
            
            status_proc = await asyncio.create_subprocess_exec(
                "systemctl", "status", service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            status_stdout, _ = await status_proc.communicate()
            
            return {
                "active": is_active,
                "status": active_stdout.decode("utf-8").strip(),
                "details": status_stdout.decode("utf-8").strip()
            }
        except FileNotFoundError:
            return {"error": "systemctl command not found"}

    @tool("Restart a systemd service", permissions=["system.services"], parameters=[
        ToolParameter(name="service_name", type="string", description="Name of the systemd service to restart")
    ])
    async def restart_service(self, service_name: str) -> dict[str, Any]:
        try:
            # Note: restarting services might require polkit / sudo depending on user privileges
            proc = await asyncio.create_subprocess_exec(
                "systemctl", "restart", service_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": f"Failed to restart service {service_name}"}
        except FileNotFoundError:
            return {"error": "systemctl command not found"}
