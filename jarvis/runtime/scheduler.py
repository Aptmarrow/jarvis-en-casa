"""Cron-like task scheduler for J.A.R.V.I.S."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from jarvis.core.api import JarvisAPI
from jarvis.core.types import ScheduledTask

logger = logging.getLogger(__name__)


class Scheduler:
    """Cron-like task scheduler that executes tools on a recurring basis."""

    def __init__(
        self, api: JarvisAPI, config: Any, project_root: Path | None = None
    ) -> None:
        self.api = api
        self.config = config
        self._project_root = project_root or Path.cwd()
        self.tasks: dict[str, ScheduledTask] = {}
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._load_tasks()

    def _load_tasks(self) -> None:
        """Load scheduled tasks from the config file."""
        config_file = "config/schedules.yaml"
        try:
            config_file = self.config.scheduler.config_file
        except Exception:
            pass

        path = self._project_root / config_file
        if not path.exists():
            logger.warning(f"Schedules config file {path} not found.")
            return

        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for task_data in data.get("tasks", []):
                task = ScheduledTask(
                    name=task_data["name"],
                    cron=task_data["cron"],
                    tool_name=task_data["tool"],
                    args=task_data.get("args", {}),
                    enabled=task_data.get("enabled", True),
                    on_change=task_data.get("on_change"),
                )
                self.add_task(task)
            logger.info(f"Loaded {len(self.tasks)} scheduled tasks.")
        except Exception as e:
            logger.error(f"Failed to load schedules from {path}: {e}")

    async def start(self) -> None:
        """Begin the scheduling loop."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started.")

    async def stop(self) -> None:
        """Cancel all scheduled tasks and stop the loop."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped.")

    async def _run_loop(self) -> None:
        """Main loop — checks every 10 seconds if any task is due."""
        while self._running:
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)

            for task in self.tasks.values():
                if not task.enabled:
                    continue

                # Skip if already ran in this minute
                if task.last_run and task.last_run >= current_minute:
                    continue

                if self._matches_cron(task.cron, current_minute):
                    task.last_run = current_minute
                    asyncio.create_task(self._execute_task(task))

            # Update next_run for all tasks
            for task in self.tasks.values():
                task.next_run = self._compute_next_run(task.cron, now)

            await asyncio.sleep(10)

    async def _execute_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task, logging errors gracefully."""
        try:
            result = await self.api.call_tool(
                task.tool_name, task.args, source="scheduler"
            )
            if not result.success:
                logger.debug(
                    f"Scheduled task '{task.name}' tool '{task.tool_name}' "
                    f"returned error: {result.error}"
                )
        except Exception as e:
            logger.error(f"Error executing scheduled task '{task.name}': {e}")

    def _matches_cron(self, cron: str, dt: datetime) -> bool:
        """Check if a datetime matches a cron expression."""
        parts = cron.split()
        if len(parts) != 5:
            return False

        m, h, dom, mon, dow = parts
        # Python weekday: 0=Monday..6=Sunday. Cron: 0=Sunday.
        cron_dow = (dt.weekday() + 1) % 7

        return (
            self._match_field(m, dt.minute)
            and self._match_field(h, dt.hour)
            and self._match_field(dom, dt.day)
            and self._match_field(mon, dt.month)
            and self._match_field(dow, cron_dow)
        )

    def _match_field(self, field: str, value: int) -> bool:
        """Match a single cron field against a value."""
        if field == "*":
            return True

        for part in field.split(","):
            if part == "*":
                return True
            if part.startswith("*/"):
                try:
                    step = int(part[2:])
                    if step > 0 and value % step == 0:
                        return True
                except ValueError:
                    pass
            elif part.isdigit():
                if int(part) == value:
                    return True
        return False

    def _compute_next_run(self, cron: str, dt: datetime) -> datetime | None:
        """Calculate the next time a cron expression matches."""
        test_dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Search up to 48 hours ahead
        for _ in range(60 * 48):
            if self._matches_cron(cron, test_dt):
                return test_dt
            test_dt += timedelta(minutes=1)
        return None

    def list_tasks(self) -> list[ScheduledTask]:
        """Return all scheduled tasks."""
        return list(self.tasks.values())

    def add_task(self, task: ScheduledTask) -> None:
        """Add or update a scheduled task."""
        self.tasks[task.name] = task

    def remove_task(self, name: str) -> None:
        """Remove a scheduled task by name."""
        self.tasks.pop(name, None)

    def enable_task(self, name: str) -> None:
        """Enable a scheduled task."""
        if name in self.tasks:
            self.tasks[name].enabled = True

    def disable_task(self, name: str) -> None:
        """Disable a scheduled task."""
        if name in self.tasks:
            self.tasks[name].enabled = False
