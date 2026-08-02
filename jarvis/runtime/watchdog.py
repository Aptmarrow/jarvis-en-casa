"""Health monitoring watchdog for J.A.R.V.I.S."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from jarvis.core.api import JarvisAPI
from jarvis.core.types import Event, EventType

logger = logging.getLogger(__name__)


class Watchdog:
    """Periodically checks system health and reports degradation."""

    def __init__(self, api: JarvisAPI, interval: int = 30) -> None:
        self.api = api
        self.interval = interval
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._start_time = datetime.now()
        self._last_check = datetime.now()
        self._status = "healthy"
        self._event_count = 0
        self._error_count = 0

    async def start(self) -> None:
        """Begin periodic health checks."""
        if self._running:
            return
        self._running = True
        self._start_time = datetime.now()

        # Subscribe to all events to count them and track errors
        await self.api.subscribe("*", self._on_event)

        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info(f"Watchdog started (interval={self.interval}s).")

    async def stop(self) -> None:
        """Stop the watchdog."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped.")

    async def _on_event(self, event: Event) -> None:
        """Track event counts and error events."""
        self._event_count += 1
        if event.type in (EventType.PLUGIN_ERROR,) or "error" in str(event.type):
            self._error_count += 1

    async def _run_loop(self) -> None:
        """Main loop — runs health checks at the configured interval."""
        while self._running:
            await asyncio.sleep(self.interval)
            await self._check_health()

    async def _check_health(self) -> None:
        """Run health checks and publish notifications if degraded."""
        self._last_check = datetime.now()
        degraded_reasons: list[str] = []

        # 1. Event bus responsive
        try:
            test_event = Event(
                type=EventType.NOTIFICATION,
                source="watchdog",
                data={"type": "health_ping"},
            )
            await self.api.publish(test_event)
        except Exception as e:
            degraded_reasons.append(f"Event bus error: {e}")

        # 2. State manager accessible
        try:
            await self.api.snapshot_state()
        except Exception as e:
            degraded_reasons.append(f"State manager error: {e}")

        # 3. Error events in last interval
        if self._error_count > 0:
            degraded_reasons.append(
                f"Detected {self._error_count} error events in the last interval"
            )

        # Reset error count for next interval
        self._error_count = 0

        if degraded_reasons:
            self._status = "degraded"
            logger.warning(
                f"Watchdog: health degraded — {', '.join(degraded_reasons)}"
            )
            await self.api.publish(
                Event(
                    type=EventType.NOTIFICATION,
                    source="watchdog",
                    data={
                        "level": "warning",
                        "message": "System health degraded",
                        "reasons": degraded_reasons,
                    },
                )
            )
        else:
            self._status = "healthy"

    async def get_health(self) -> dict[str, Any]:
        """Return the current health status."""
        return {
            "uptime_seconds": (datetime.now() - self._start_time).total_seconds(),
            "event_count": self._event_count,
            "plugin_count": len(self.api.plugin_registry.list_plugins()),
            "last_check": self._last_check.isoformat(),
            "status": self._status,
        }
