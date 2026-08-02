from __future__ import annotations

import asyncio
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class VLCPlugin(Plugin):
    name = "media.vlc"
    description = "Control VLC media player"

    @tool("Play media file or URL in VLC", parameters=[
        ToolParameter(name="file_or_url", type="string", description="File path or URL to play")
    ])
    async def play_media(self, file_or_url: str) -> dict[str, Any]:
        try:
            # We don't await the end since VLC might run indefinitely
            proc = await asyncio.create_subprocess_exec(
                "vlc", "--one-instance", file_or_url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            return {"status": "success", "message": f"Started playing {file_or_url}"}
        except FileNotFoundError:
            return {"error": "vlc command not found"}

    @tool("Control VLC playback", parameters=[
        ToolParameter(name="action", type="string", description="Action to perform (play, pause, stop, next, previous)")
    ])
    async def control(self, action: str) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--player=vlc", action,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": f"Failed to perform {action} on VLC"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}
