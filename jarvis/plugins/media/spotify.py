from __future__ import annotations

import asyncio
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class SpotifyPlugin(Plugin):
    name = "media.spotify"
    description = "Control Spotify playback"

    @tool("Play Spotify", parameters=[
        ToolParameter(name="uri", type="string", description="Optional URI to play", required=False)
    ])
    async def play(self, uri: str | None = None) -> dict[str, Any]:
        try:
            args = ["--player=spotify", "play"]
            if uri:
                # playerctl might not natively support opening URIs easily without d-bus, 
                # but we will try to pass it if specified, or maybe it's ignored by standard playerctl play.
                # Just executing standard play
                pass
                
            proc = await asyncio.create_subprocess_exec(
                "playerctl", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": "Failed to play Spotify"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}

    @tool("Pause Spotify")
    async def pause(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--player=spotify", "pause",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": "Failed to pause Spotify"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}

    @tool("Next track on Spotify")
    async def next_track(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--player=spotify", "next",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": "Failed to skip to next track"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}

    @tool("Previous track on Spotify")
    async def previous_track(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--player=spotify", "previous",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            return {"error": "Failed to skip to previous track"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}

    @tool("Get Spotify metadata")
    async def get_metadata(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "playerctl", "--player=spotify", "metadata",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success", "metadata": stdout.decode("utf-8").strip()}
            return {"error": "Failed to get metadata"}
        except FileNotFoundError:
            return {"error": "playerctl command not found"}
