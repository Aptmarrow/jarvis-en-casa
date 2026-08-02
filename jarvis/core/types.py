"""Core type definitions for Jarvis.

Every typed dataclass, enum, and type alias used across the system lives here.
This module has **zero** internal dependencies to avoid circular imports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Callable, Coroutine


# ─── Events ────────────────────────────────────────────────────────────────────


class EventType(StrEnum):
    """All event types flowing through the event bus."""

    # Lifecycle
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_READY = "system.ready"

    # Input
    TEXT_INPUT = "input.text"
    VOICE_INPUT = "input.voice"
    WAKE_WORD_DETECTED = "input.wake_word"

    # Tool execution
    TOOL_REQUEST = "tool.request"
    TOOL_RESULT = "tool.result"

    # AI
    AI_REQUEST = "ai.request"
    AI_RESPONSE = "ai.response"

    # State
    STATE_CHANGED = "state.changed"

    # Permissions
    PERMISSION_REQUEST = "permission.request"
    PERMISSION_RESPONSE = "permission.response"

    # Scheduler
    SCHEDULED_TASK = "scheduler.task"
    SCHEDULED_TASK_RESULT = "scheduler.task_result"

    # Notifications
    NOTIFICATION = "notification"

    # Plugin lifecycle
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_ERROR = "plugin.error"


class EventPriority(IntEnum):
    """Priority levels for event processing in EventBus."""

    REALTIME = 0    # Audio streaming, wake word, PTT, cancellations
    HIGH = 1        # Direct user actions, interactive command responses
    NORMAL = 2      # System notifications, tool results, state changes
    LOW = 3         # Background network scans, device checks
    BACKGROUND = 4  # Watchdog maintenance, backups, sync


class VoiceIdentityState(StrEnum):
    """Voice identity confidence levels."""

    OWNER = "owner"
    TRUSTED = "trusted"
    UNKNOWN = "unknown"
    REJECTED = "rejected"


@dataclass
class Event:
    """Base event that flows through the event bus.

    Every piece of communication between modules is an Event.
    Modules never call each other directly — they publish and subscribe to events.
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        return f"Event({self.type}, priority={self.priority.name}, source={self.source}, id={self.event_id})"

    def __repr__(self) -> str:
        return (
            f"Event(type={self.type!r}, priority={self.priority.name!r}, source={self.source!r}, "
            f"event_id={self.event_id!r}, data_keys={list(self.data.keys())})"
        )


# ─── Permissions ───────────────────────────────────────────────────────────────


class PermissionLevel(StrEnum):
    """How a specific permission is enforced."""

    AUTO = "auto"                       # Execute without asking
    CONFIRM = "confirm"                 # Ask for confirmation (skippable by context)
    CONFIRM_ALWAYS = "confirm_always"   # Always require explicit confirmation
    DENY = "deny"                       # Never allow


@dataclass
class PermissionCheck:
    """Result of evaluating permissions for a tool execution."""

    granted: bool
    level: PermissionLevel
    permissions_checked: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    denial_reason: str | None = None


# ─── Tools ─────────────────────────────────────────────────────────────────────


@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""

    name: str
    type: str              # "string", "integer", "float", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


@dataclass
class ToolMetadata:
    """Complete metadata about a registered tool.

    Generated automatically from the ``@tool`` decorator.
    Used by the AI orchestrator to generate function declarations,
    and by the CLI to display help.
    """

    name: str                    # Fully qualified: "system.volume.get_volume"
    description: str
    plugin_name: str             # "system.volume"
    parameters: list[ToolParameter] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    handler: Callable | None = None   # The actual async callable

    @property
    def short_name(self) -> str:
        """Last segment of the qualified name: 'get_volume'."""
        return self.name.rsplit(".", 1)[-1]

    def to_json_schema(self) -> dict[str, Any]:
        """Convert parameters to JSON Schema (for AI function calling)."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum is not None:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema


@dataclass
class ToolRequest:
    """Request to execute a registered tool."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    source: str = "cli"          # "cli" | "voice" | "websocket" | "ai" | "scheduler"
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolResult:
    """Result returned after executing a tool."""

    request_id: str
    tool_name: str
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


# ─── State ─────────────────────────────────────────────────────────────────────


@dataclass
class StateChange:
    """Emitted when a value in the global state changes."""

    key: str
    old_value: Any
    new_value: Any
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ─── Scheduler ─────────────────────────────────────────────────────────────────


@dataclass
class ScheduledTask:
    """Definition of a recurring scheduled task."""

    name: str
    cron: str                              # "*/15 * * * *"
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    on_change: str | None = None           # "notify" | None
    last_run: datetime | None = None
    next_run: datetime | None = None
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


# ─── Type Aliases ──────────────────────────────────────────────────────────────

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]
"""Async callable that processes an Event."""

StateWatcher = Callable[[StateChange], Coroutine[Any, Any, None]]
"""Async callable that reacts to a StateChange."""

ToolHandler = Callable[..., Coroutine[Any, Any, Any]]
"""Async callable that implements a tool."""
