from __future__ import annotations

import asyncio
from typing import Any
from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class WifiPlugin(Plugin):
    name = "network.wifi"
    description = "WiFi status and connection management"

    @tool(
        description="Gets the current WiFi status",
    )
    async def get_status(self) -> dict[str, Any]:
        status = {"connected": False, "ssid": None, "signal": None, "ip": None}
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "GENERAL,WIFI-PROPERTIES", "dev", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode()
                if "connected" in output.lower():
                    status["connected"] = True
                
                # Fetch more details using nmcli dev wifi
                proc2 = await asyncio.create_subprocess_exec(
                    "nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL", "dev", "wifi",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout2, _ = await proc2.communicate()
                if proc2.returncode == 0:
                    for line in stdout2.decode().strip().split('\n'):
                        if line.startswith('*'):
                            parts = line.split(':')
                            if len(parts) >= 3:
                                status["ssid"] = parts[1]
                                status["signal"] = parts[2]
                                break
        except FileNotFoundError:
            pass
        return status

    @tool(
        description="Lists available WiFi networks",
    )
    async def list_networks(self) -> list[dict[str, Any]]:
        networks = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                for line in lines:
                    if not line: continue
                    parts = line.split(':')
                    if len(parts) >= 3:
                        networks.append({
                            "ssid": parts[0],
                            "signal": parts[1],
                            "security": parts[2]
                        })
        except FileNotFoundError:
            pass
        return networks

    @tool(
        description="Connects to a WiFi network",
        parameters=[
            ToolParameter(name="ssid", type="string", description="SSID to connect to", required=True),
            ToolParameter(name="password", type="string", description="Password for the network", required=False)
        ]
    )
    async def connect_wifi(self, ssid: str, password: str | None = None) -> dict[str, Any]:
        success = False
        try:
            args = ["nmcli", "dev", "wifi", "connect", ssid]
            if password:
                args.extend(["password", password])
                
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            success = (proc.returncode == 0)
        except FileNotFoundError:
            pass
        return {"success": success}
