from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class VolumePlugin(Plugin):
    name = "system.volume"
    description = "Control system volume and mute status."
    version = "0.1.0"

    @tool(
        description="Get current volume level and mute status",
        permissions=["system.volume"]
    )
    async def get_volume(self) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "get-sink-volume", "@DEFAULT_SINK@",
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        volume = 0
        if "%" in output:
            parts = output.split("%")
            vol_str = parts[0].split()[-1]
            try:
                volume = int(vol_str)
            except ValueError:
                pass
                
        proc_mute = await asyncio.create_subprocess_exec(
            "pactl", "get-sink-mute", "@DEFAULT_SINK@",
            stdout=asyncio.subprocess.PIPE
        )
        stdout_mute, _ = await proc_mute.communicate()
        muted = "yes" in stdout_mute.decode().strip().lower()
        
        return {"volume": volume, "muted": muted}

    @tool(
        description="Set system volume level",
        permissions=["system.volume"],
        parameters=[
            ToolParameter(name="level", type="integer", description="Volume 0-100"),
        ]
    )
    async def set_volume(self, level: int) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"
        )
        await proc.wait()
        return {"volume": level}

    @tool(
        description="Toggle system mute status",
        permissions=["system.volume"]
    )
    async def toggle_mute(self) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"
        )
        await proc.wait()
        
        proc_mute = await asyncio.create_subprocess_exec(
            "pactl", "get-sink-mute", "@DEFAULT_SINK@",
            stdout=asyncio.subprocess.PIPE
        )
        stdout_mute, _ = await proc_mute.communicate()
        muted = "yes" in stdout_mute.decode().strip().lower()
        return {"muted": muted}
