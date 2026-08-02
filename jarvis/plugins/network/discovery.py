from __future__ import annotations

import asyncio
from typing import Any
from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class NetworkDiscoveryPlugin(Plugin):
    name = "network.discovery"
    description = "Network discovery and ARP scanning"

    @tool(
        description="Scans the network for active devices",
        parameters=[
            ToolParameter(name="subnet", type="string", description="Subnet to scan", required=False, default="192.168.0.0/24")
        ]
    )
    async def scan_network(self, subnet: str = "192.168.0.0/24") -> dict[str, Any]:
        devices = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "neighbor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                for line in lines:
                    if not line: continue
                    parts = line.split()
                    if len(parts) >= 5 and 'lladdr' in parts:
                        ip = parts[0]
                        mac_idx = parts.index('lladdr') + 1
                        mac = parts[mac_idx]
                        status = parts[-1]
                        devices.append({
                            "ip": ip,
                            "mac": mac,
                            "hostname": "unknown",
                            "status": status
                        })
        except FileNotFoundError:
            pass
            
        return {"devices": devices}

    @tool(
        description="Pings a host to check reachability and latency",
        parameters=[
            ToolParameter(name="host", type="string", description="Host to ping", required=True)
        ]
    )
    async def ping_host(self, host: str) -> dict[str, Any]:
        reachable = False
        latency_ms = 0.0
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "2", "-W", "1", host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            reachable = (proc.returncode == 0)
            if reachable:
                output = stdout.decode()
                for line in output.split("\n"):
                    if "min/avg/max" in line or "mdev" in line:
                        try:
                            parts = line.split("=")[1].strip().split("/")
                            latency_ms = float(parts[1])
                        except (IndexError, ValueError):
                            pass
        except FileNotFoundError:
            pass
            
        return {"host": host, "reachable": reachable, "latency_ms": latency_ms}
