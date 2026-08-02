from __future__ import annotations

import asyncio
import logging
from typing import Any

from jarvis.core.event_bus import EventBus
from jarvis.core.types import Event, EventType, StateChange, StateWatcher

logger = logging.getLogger(__name__)


class StateManager:
    """Global state manager."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._lock = asyncio.Lock()
        self._watchers: dict[str, list[StateWatcher]] = {}
        
        self._state: dict[str, Any] = {
            "user.present": True,
            "user.confidence": 1.0,
            "system.night_mode": False,
            "system.cpu_temp": 0.0,
            "system.battery": 100,
            "audio.headphones": False,
            "audio.volume": 50,
            "network.active": True,
            "network.devices_count": 0,
            "bluetooth.connected": False,
        }

    async def get(self, key: str) -> Any:
        async with self._lock:
            return self._state.get(key)

    async def set(self, key: str, value: Any, source: str = "") -> None:
        async with self._lock:
            old_value = self._state.get(key)
            if old_value == value:
                return
            self._state[key] = value

        change = StateChange(key=key, old_value=old_value, new_value=value, source=source)
        logger.debug(f"State changed: {key} {old_value} -> {value}")
        
        async with self._lock:
            watchers = list(self._watchers.get(key, []))

        for watcher in watchers:
            asyncio.create_task(self._safe_invoke_watcher(watcher, change))
            
        await self._event_bus.publish(Event(type=EventType.STATE_CHANGED, data={"change": change}, source=source))

    async def _safe_invoke_watcher(self, watcher: StateWatcher, change: StateChange) -> None:
        try:
            await watcher(change)
        except Exception as e:
            logger.error(f"Error in state watcher {watcher} for {change.key}: {e}", exc_info=True)

    async def watch(self, key: str, callback: StateWatcher) -> None:
        async with self._lock:
            if key not in self._watchers:
                self._watchers[key] = []
            if callback not in self._watchers[key]:
                self._watchers[key].append(callback)

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return self._state.copy()

    async def bulk_update(self, updates: dict[str, Any], source: str = "") -> None:
        for key, value in updates.items():
            await self.set(key, value, source)
