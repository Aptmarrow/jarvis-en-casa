from __future__ import annotations

import asyncio
import webbrowser
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class BrowserPlugin(Plugin):
    name = "media.browser"
    description = "Open URLs and manage browser tabs"

    @tool("Open URL in default web browser", parameters=[
        ToolParameter(name="url", type="string", description="URL to open")
    ])
    async def open_url(self, url: str) -> dict[str, Any]:
        try:
            # Using xdg-open for linux
            proc = await asyncio.create_subprocess_exec(
                "xdg-open", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success"}
            
            # fallback to webbrowser
            def open_sync():
                return webbrowser.open(url)
            
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, open_sync)
            if success:
                return {"status": "success"}
            return {"error": "Failed to open URL"}
        except FileNotFoundError:
            # fallback to webbrowser
            loop = asyncio.get_running_loop()
            success = await loop.run_in_executor(None, open_sync)
            if success:
                return {"status": "success"}
            return {"error": "Failed to open URL and xdg-open not found"}

    @tool("Search YouTube and directly play/autoplay the top matching song or video", parameters=[
        ToolParameter(name="query", type="string", description="Song, artist, or video name to play on YouTube")
    ])
    async def play_youtube(self, query: str) -> dict[str, Any]:
        """Finds top video ID for query on YouTube and opens it directly with autoplay."""
        import urllib.parse
        import urllib.request
        import re

        def _fetch_first_video_url(search_term: str) -> str:
            encoded = urllib.parse.quote(search_term)
            search_url = f"https://www.youtube.com/results?search_query={encoded}"
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                    video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", html)
                    if video_ids:
                        return f"https://www.youtube.com/watch?v={video_ids[0]}&autoplay=1"
            except Exception as e:
                pass
            # Fallback to search results page with autoplay hint
            return search_url

        loop = asyncio.get_running_loop()
        autoplay_url = await loop.run_in_executor(None, _fetch_first_video_url, query)

        return await self.open_url(autoplay_url)
