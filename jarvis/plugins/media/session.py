"""Media Session Facade Plugin for J.A.R.V.I.S.

Provides unified playback controls (play, pause, unpause, toggle, next, previous)
over Linux MPRIS D-Bus players (Chrome/YouTube, Firefox, Spotify, VLC, MPV, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

logger = logging.getLogger(__name__)


async def _list_mpris_players() -> list[str]:
    """Find all active MPRIS media players registered on session D-Bus."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
            "--object-path", "/org/freedesktop/DBus",
            "--method", "org.freedesktop.DBus.ListNames",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            names = re.findall(r"'([^']+)'", stdout.decode("utf-8", errors="ignore"))
            players = [n for n in names if "org.mpris.MediaPlayer2" in n]
            return players
    except Exception as e:
        logger.warning(f"Failed to list MPRIS players: {e}")
    return []


async def _call_kde_shortcut(shortcut_name: str) -> bool:
    """Invoke KDE Plasma Wayland global media shortcut (playpausemedia, nextmedia, etc.)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "gdbus", "call", "--session", "--dest", "org.kde.kglobalaccel",
            "--object-path", "/component/mediacontrol",
            "--method", "org.kde.kglobalaccel.Component.invokeShortcut",
            shortcut_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception as e:
        logger.debug(f"KDE shortcut {shortcut_name} failed: {e}")
        return False


async def _call_mpris_method(method: str) -> list[dict[str, Any]]:
    """Send MPRIS Player method call (Play, Pause, PlayPause, Next, Previous) via gdbus."""
    players = await _list_mpris_players()
    results = []
    for player in players:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gdbus", "call", "--session", "--dest", player,
                "--object-path", "/org/mpris/MediaPlayer2",
                "--method", f"org.mpris.MediaPlayer2.Player.{method}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            success = (proc.returncode == 0)
            results.append({"player": player, "success": success})
        except Exception as e:
            results.append({"player": player, "error": str(e)})
    return results


class MediaSessionPlugin(Plugin):
    """Unified Media Session Facade Plugin with Linux MPRIS support."""

    name = "media.session"
    description = "Unified media playback controls across YouTube, Chrome, Spotify, VLC, and Linux MPRIS players."
    version = "0.2.0"

    @tool(
        description="Resume or play media playback across Chrome/YouTube, Spotify, VLC, and active Linux MPRIS players",
        permissions=["media.play"],
        parameters=[
            ToolParameter(
                name="media_uri",
                type="string",
                description="Optional URL or URI to play",
                required=False,
            ),
        ],
    )
    async def play(self, media_uri: str | None = None) -> dict[str, Any]:
        """Resume or start media playback on active players."""
        if media_uri:
            return await self.api.call_tool("media.browser.play_youtube", {"query": media_uri})

        kde_ok = await _call_kde_shortcut("playpausemedia")
        mpris_results = await _call_mpris_method("Play")
        if not any(r.get("success") for r in mpris_results):
            mpris_results = await _call_mpris_method("PlayPause")

        await self.api.call_tool("media.spotify.play", {})

        return {
            "status": "playing",
            "message": "Comando de reproducción enviado a los reproductores activos (KDE/YouTube/Chrome/Spotify/VLC)",
            "kde_shortcut": kde_ok,
            "players": mpris_results,
        }

    @tool(
        description="Pause media playback across Chrome/YouTube, Spotify, VLC, and active Linux MPRIS players",
        permissions=["media.play"],
    )
    async def pause(self) -> dict[str, Any]:
        """Pause media playback on all active Linux players."""
        kde_ok = await _call_kde_shortcut("playpausemedia")
        mpris_results = await _call_mpris_method("Pause")
        if not any(r.get("success") for r in mpris_results):
            mpris_results = await _call_mpris_method("PlayPause")

        await self.api.call_tool("media.spotify.pause", {})
        await self.api.call_tool("media.vlc.control", {"action": "pause"})

        return {
            "status": "paused",
            "message": "Comando de pausa enviado a los reproductores activos (KDE/YouTube/Chrome/Spotify/VLC)",
            "kde_shortcut": kde_ok,
            "players": mpris_results,
        }

    @tool(
        description="Toggle play/pause on active media playback (YouTube, Spotify, VLC, etc.)",
        permissions=["media.play"],
    )
    async def toggle_play_pause(self) -> dict[str, Any]:
        """Toggle play/pause state across active media players."""
        kde_ok = await _call_kde_shortcut("playpausemedia")
        mpris_results = await _call_mpris_method("PlayPause")
        return {
            "status": "toggled",
            "message": "Alternada la reproducción/pausa en reproductores activos",
            "kde_shortcut": kde_ok,
            "players": mpris_results,
        }

    @tool(
        description="Skip to next track/media item",
        permissions=["media.play"],
    )
    async def next_track(self) -> dict[str, Any]:
        """Skip to next track on active player."""
        mpris_results = await _call_mpris_method("Next")
        await self.api.call_tool("media.spotify.next_track", {})
        return {"status": "next_track_sent", "players": mpris_results}

    @tool(
        description="Get current active media session info",
        permissions=["media.play"],
    )
    async def get_active_session(self) -> dict[str, Any]:
        """Get metadata of currently playing track/media."""
        players = await _list_mpris_players()
        return {
            "status": "active" if players else "idle",
            "active_players": players,
        }

