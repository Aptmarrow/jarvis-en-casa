from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class BrightnessPlugin(Plugin):
    name = "system.brightness"
    description = "Control screen brightness."
    version = "0.1.0"

    @tool(
        description="Get current screen brightness",
        permissions=["system.brightness"]
    )
    async def get_brightness(self) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "brightnessctl", "info",
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode().strip()
        
        brightness = 0
        max_b = 0
        
        m = re.search(r"\((\d+)%\)", output)
        if m:
            brightness = int(m.group(1))
            
        m_max = re.search(r"Max brightness: (\d+)", output)
        if m_max:
            max_b = int(m_max.group(1))
            
        return {"brightness": brightness, "max": max_b}

    @tool(
        description="Set screen brightness",
        permissions=["system.brightness"],
        parameters=[
            ToolParameter(name="level", type="integer", description="Brightness level 0-100"),
        ]
    )
    async def set_brightness(self, level: int) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "brightnessctl", "set", f"{level}%"
        )
        await proc.wait()
        return {"brightness": level}
