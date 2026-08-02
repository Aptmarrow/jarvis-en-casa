from __future__ import annotations

import asyncio
from typing import Any
from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class BluetoothPlugin(Plugin):
    name = "network.bluetooth"
    description = "Bluetooth device management"

    @tool(
        description="Gets Bluetooth status"
    )
    async def get_status(self) -> dict[str, Any]:
        status = {"powered": False, "discoverable": False}
        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                out = stdout.decode()
                status["powered"] = "Powered: yes" in out
                status["discoverable"] = "Discoverable: yes" in out
        except FileNotFoundError:
            pass
        return status

    @tool(
        description="Lists Bluetooth devices"
    )
    async def list_devices(self) -> list[dict[str, Any]]:
        devices = []
        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                for line in lines:
                    if line.startswith("Device "):
                        parts = line.split(" ", 2)
                        if len(parts) >= 3:
                            devices.append({"mac": parts[1], "name": parts[2]})
        except FileNotFoundError:
            pass
        return devices

    @tool(
        description="Connects to a Bluetooth device",
        parameters=[
            ToolParameter(name="mac", type="string", description="MAC address", required=True)
        ]
    )
    async def connect_device(self, mac: str) -> dict[str, Any]:
        connected = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "connect", mac,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            connected = (proc.returncode == 0)
        except FileNotFoundError:
            pass
        return {"connected": connected}

    @tool(
        description="Disconnects from a Bluetooth device",
        parameters=[
            ToolParameter(name="mac", type="string", description="MAC address", required=True)
        ]
    )
    async def disconnect_device(self, mac: str) -> dict[str, Any]:
        disconnected = False
        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "disconnect", mac,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            disconnected = (proc.returncode == 0)
        except FileNotFoundError:
            pass
        return {"disconnected": disconnected}
