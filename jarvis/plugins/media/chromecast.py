from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

logger = logging.getLogger(__name__)


class ChromecastPlugin(Plugin):
    name = "media.chromecast"
    description = "Cast YouTube videos, audio and media to Chromecast or Smart TV (Comedor, etc.)"
    version = "0.2.0"

    @tool("List available Chromecast and Smart TV devices on the local network")
    async def list_chromecasts(self) -> dict[str, Any]:
        """Scans local Wi-Fi network for Chromecast devices using catt/pychromecast."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "catt", "scan",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            devices = []
            if proc.returncode == 0:
                for line in stdout.decode("utf-8", errors="ignore").splitlines():
                    match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+-\s+(.+?)\s+-", line)
                    if match:
                        devices.append({"ip": match.group(1), "name": match.group(2).strip()})

            if not devices:
                # Fallback scan with default known device
                devices = [{"ip": "192.168.100.9", "name": "Comedor"}]

            return {"chromecasts": devices, "status": "success"}
        except FileNotFoundError:
            return {"chromecasts": [{"ip": "192.168.100.9", "name": "Comedor"}], "warning": "catt CLI not found"}
        except Exception as e:
            return {"error": f"Failed to list chromecasts: {e}"}

    @tool("Cast media URL or YouTube link to a Chromecast device (defaults to 'Comedor')", parameters=[
        ToolParameter(name="url", type="string", description="URL of the media or YouTube video to cast"),
        ToolParameter(name="device_name", type="string", description="Name of the Chromecast device (default: 'Comedor')", required=False),
    ])
    async def cast_url(self, url: str, device_name: str | None = None) -> dict[str, Any]:
        """Casts video/audio URL directly to a Chromecast device using catt."""
        target_device = device_name or "Comedor"
        try:
            proc = await asyncio.create_subprocess_exec(
                "catt", "-d", target_device, "cast", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success", "device": target_device, "url": url}
            else:
                # Retry with default catt without explicit device name if device not found
                proc2 = await asyncio.create_subprocess_exec(
                    "catt", "cast", url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc2.communicate()
                if proc2.returncode == 0:
                    return {"status": "success", "device": "default", "url": url}
                return {"error": f"Failed to cast: {stderr.decode().strip()}"}
        except Exception as e:
            return {"error": f"Error casting URL: {e}"}

    @tool("Search YouTube and cast top matching video directly to Chromecast TV (Comedor)", parameters=[
        ToolParameter(name="query", type="string", description="Song or video name to search and cast to Chromecast TV"),
        ToolParameter(name="device_name", type="string", description="Chromecast device name (default: 'Comedor')", required=False),
    ])
    async def cast_youtube(self, query: str, device_name: str | None = None) -> dict[str, Any]:
        """Finds YouTube video for query and casts it directly to Chromecast."""
        target_device = device_name or "Comedor"

        def _get_youtube_url(search_term: str) -> str:
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
                        return f"https://www.youtube.com/watch?v={video_ids[0]}"
            except Exception:
                pass
            return search_url

        loop = asyncio.get_running_loop()
        yt_url = await loop.run_in_executor(None, _get_youtube_url, query)

        return await self.cast_url(url=yt_url, device_name=target_device)

    @tool("Control playback state of Chromecast device (play, pause, stop, volume)", parameters=[
        ToolParameter(name="action", type="string", description="Action: 'play', 'pause', 'stop', 'volup', 'voldown'"),
        ToolParameter(name="device_name", type="string", description="Name of Chromecast device (default: 'Comedor')", required=False),
    ])
    async def chromecast_control(self, action: str, device_name: str | None = None) -> dict[str, Any]:
        """Control playback state on Chromecast."""
        target_device = device_name or "Comedor"
        action_clean = action.lower().strip()
        try:
            proc = await asyncio.create_subprocess_exec(
                "catt", "-d", target_device, action_clean,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return {"status": "success", "action": action_clean, "device": target_device}
        except Exception as e:
            return {"error": f"Failed to control Chromecast: {e}"}

