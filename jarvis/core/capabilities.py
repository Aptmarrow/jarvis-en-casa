"""Capability Manager for J.A.R.V.I.S.

Decouples intent from specific plugin implementations.
Plugins register capabilities (e.g. 'media.playback', 'network.scan', 'printer.use').
Jarvis queries the CapabilityManager to find all plugins or tools satisfying a capability.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.types import ToolMetadata

logger = logging.getLogger(__name__)


class CapabilityManager:
    """Registry and lookup for system capabilities."""

    def __init__(self) -> None:
        # capability_name -> list of plugin names or tool names
        self._capabilities: dict[str, list[str]] = {
            "media.playback": [
                "media.spotify.play",
                "media.vlc.play_media",
                "media.chromecast.cast_url",
            ],
            "media.control": [
                "media.spotify.pause",
                "media.spotify.next_track",
                "media.vlc.control",
            ],
            "network.connectivity": [
                "network.wifi.get_status",
                "network.bluetooth.get_status",
            ],
            "network.discovery": [
                "network.discovery.scan_network",
            ],
            "system.print": [
                "system.printer.print_file",
            ],
            "system.service": [
                "system.services.get_status",
                "system.services.restart_service",
            ],
            "system.volume": [
                "system.volume.set_volume",
                "system.volume.toggle_mute",
            ],
        }

    def register_capability(self, capability: str, provider_name: str) -> None:
        """Register a tool or plugin name as a provider for a capability."""
        if capability not in self._capabilities:
            self._capabilities[capability] = []
        if provider_name not in self._capabilities[capability]:
            self._capabilities[capability].append(provider_name)
            logger.debug(f"Registered capability '{capability}' -> {provider_name}")

    def find_providers(self, capability: str) -> list[str]:
        """Find all registered providers (tools or plugins) for a capability."""
        return self._capabilities.get(capability, [])

    def list_capabilities(self) -> dict[str, list[str]]:
        """Return a copy of all registered capabilities and their providers."""
        return {k: list(v) for k, v in self._capabilities.items()}
