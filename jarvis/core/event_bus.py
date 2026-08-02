from __future__ import annotations

import asyncio
import fnmatch
import logging
from typing import Any

from jarvis.core.types import Event, EventHandler, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """Async pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        """Register a handler for an event type (supports wildcards)."""
        key = str(event_type)
        async with self._lock:
            if key not in self._subscribers:
                self._subscribers[key] = []
            if handler not in self._subscribers[key]:
                self._subscribers[key].append(handler)
        logger.debug(f"Subscribed handler to {key}")

    async def unsubscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        """Unregister a handler."""
        key = str(event_type)
        async with self._lock:
            if key in self._subscribers and handler in self._subscribers[key]:
                self._subscribers[key].remove(handler)
                if not self._subscribers[key]:
                    del self._subscribers[key]
        logger.debug(f"Unsubscribed handler from {key}")

    def _get_matching_handlers(self, event_type_str: str) -> list[EventHandler]:
        handlers: list[EventHandler] = []
        for pattern, subscriber_list in self._subscribers.items():
            if fnmatch.fnmatch(event_type_str, pattern):
                handlers.extend(subscriber_list)
        # Deduplicate while preserving order
        unique_handlers = []
        for h in handlers:
            if h not in unique_handlers:
                unique_handlers.append(h)
        return unique_handlers

    async def publish(self, event: Event) -> None:
        """Dispatch event to all matching handlers concurrently based on EventPriority."""
        logger.debug(f"Publishing {event}")
        async with self._lock:
            handlers = self._get_matching_handlers(str(event.type))

        if not handlers:
            return

        # High priority events are scheduled immediately or awaited
        for handler in handlers:
            task = asyncio.create_task(self._safe_invoke(handler, event))
            if getattr(event, "priority", None) and getattr(event.priority, "value", 2) == 1:
                # Yield control to allow HIGH priority event tasks to run immediately
                await asyncio.sleep(0)

    async def _safe_invoke(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error in handler {handler} for {event}: {e}", exc_info=True)

    async def wait_for(self, event_type: EventType | str, timeout: float | None = None) -> Event:
        """Wait for a specific event type."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        key = str(event_type)

        async def _waiter(event: Event) -> None:
            if not future.done():
                future.set_result(event)

        await self.subscribe(key, _waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            await self.unsubscribe(key, _waiter)
