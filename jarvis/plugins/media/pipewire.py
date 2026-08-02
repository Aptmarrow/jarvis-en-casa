from __future__ import annotations

import asyncio
import json
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class PipeWirePlugin(Plugin):
    name = "media.pipewire"
    description = "Control PipeWire audio sinks, sources and routing"

    @tool("Get list of audio output devices (sinks)")
    async def get_sinks(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "-f", "json", "list", "sinks",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return {"error": "Failed to list sinks"}
            
            data = json.loads(stdout)
            sinks = []
            for item in data:
                sinks.append({
                    "id": str(item.get("index")),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "volume": item.get("volume"),
                    "muted": item.get("mute"),
                    "default": False
                })
            return {"sinks": sinks}
        except FileNotFoundError:
            return {"error": "pactl command not found"}

    @tool("Set default audio sink", parameters=[
        ToolParameter(name="sink_name_or_id", type="string", description="Name or ID of the sink to set as default")
    ])
    async def set_default_sink(self, sink_name_or_id: str) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "set-default-sink", sink_name_or_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success", "sink": sink_name_or_id}
            return {"error": "Failed to set default sink"}
        except FileNotFoundError:
            return {"error": "pactl command not found"}

    @tool("Get list of audio input devices (sources)")
    async def get_sources(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pactl", "-f", "json", "list", "sources",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return {"error": "Failed to list sources"}
            
            data = json.loads(stdout)
            sources = []
            for item in data:
                sources.append({
                    "id": str(item.get("index")),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "volume": item.get("volume"),
                    "muted": item.get("mute")
                })
            return {"sources": sources}
        except FileNotFoundError:
            return {"error": "pactl command not found"}
