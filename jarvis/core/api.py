from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.capabilities import CapabilityManager
    from jarvis.memory.device_registry import DeviceRegistry
    from jarvis.memory.engine import MemoryEngine
    from jarvis.memory.knowledge import KnowledgeGraph

from jarvis.core.config import JarvisConfig
from jarvis.core.event_bus import EventBus
from jarvis.core.permissions import PermissionManager
from jarvis.core.registry import PluginRegistry, ToolRegistry
from jarvis.core.state import StateManager
from jarvis.core.types import (
    Event,
    EventHandler,
    EventType,
    PermissionCheck,
    StateWatcher,
    ToolMetadata,
    ToolResult,
)

logger = logging.getLogger(__name__)


class JarvisAPI:
    """Core API facade provided to plugins and internal components."""

    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        permission_manager: PermissionManager,
        tool_registry: ToolRegistry,
        plugin_registry: PluginRegistry,
        config: JarvisConfig,
        memory_engine: MemoryEngine | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
        capability_manager: CapabilityManager | None = None,
        device_registry: DeviceRegistry | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._state_manager = state_manager
        self._permission_manager = permission_manager
        self._tool_registry = tool_registry
        self._plugin_registry = plugin_registry
        self._config = config
        self._memory_engine = memory_engine
        self._knowledge_graph = knowledge_graph
        self._capability_manager = capability_manager
        self._device_registry = device_registry

    async def publish(self, event: Event) -> None:
        """Publish an event to the event bus."""
        await self._event_bus.publish(event)

    async def subscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        """Subscribe to an event type."""
        await self._event_bus.subscribe(event_type, handler)

    async def call_tool(self, name: str, args: dict[str, Any], source: str = "internal") -> ToolResult:
        """Execute a tool by name, checking permissions first."""
        tool = self._tool_registry.get_tool(name)
        if not tool:
            return ToolResult(
                request_id="",
                tool_name=name,
                success=False,
                error=f"Tool '{name}' not found."
            )

        check = await self._permission_manager.check(tool.permissions)
        
        if not check.granted:
            if check.requires_confirmation:
                granted = await self._permission_manager.request_confirmation(name, tool.permissions)
                if not granted:
                    return ToolResult(
                        request_id="",
                        tool_name=name,
                        success=False,
                        error="Permission denied by user."
                    )
            else:
                return ToolResult(
                    request_id="",
                    tool_name=name,
                    success=False,
                    error=check.denial_reason or "Permission denied."
                )

        if not tool.handler:
            return ToolResult(
                request_id="",
                tool_name=name,
                success=False,
                error="Tool has no handler."
            )

        import time
        start_time = time.time()
        try:
            result_data = await tool.handler(**args)
            execution_time = (time.time() - start_time) * 1000
            return ToolResult(
                request_id="",
                tool_name=name,
                success=True,
                data=result_data,
                execution_time_ms=execution_time
            )
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return ToolResult(
                request_id="",
                tool_name=name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )

    async def get_state(self, key: str) -> Any:
        """Get a value from the global state."""
        return await self._state_manager.get(key)

    async def set_state(self, key: str, value: Any, source: str = "") -> None:
        """Set a value in the global state."""
        await self._state_manager.set(key, value, source)

    async def watch_state(self, key: str, callback: StateWatcher) -> None:
        """Watch a state key for changes."""
        await self._state_manager.watch(key, callback)

    async def check_permissions(self, permissions: list[str]) -> PermissionCheck:
        """Check if a set of permissions is granted."""
        return await self._permission_manager.check(permissions)

    def get_config(self, section: str) -> Any:
        """Get a configuration section."""
        try:
            return getattr(self._config, section)
        except AttributeError:
            raise KeyError(f"Configuration section '{section}' not found.")

    def list_tools(self) -> list[ToolMetadata]:
        """List all registered tools."""
        return self._tool_registry.list_tools()

    def get_tool(self, name: str) -> ToolMetadata | None:
        """Get metadata for a specific tool."""
        return self._tool_registry.get_tool(name)

    # ─── Internal access for system components ─────────────────────────────

    @property
    def event_bus(self) -> EventBus:
        """Direct access to event bus (for internal components)."""
        return self._event_bus

    @property
    def state_manager(self) -> StateManager:
        """Direct access to state manager (for internal components)."""
        return self._state_manager

    @property
    def permission_manager(self) -> PermissionManager:
        """Direct access to permission manager (for internal components)."""
        return self._permission_manager

    @property
    def plugin_registry(self) -> PluginRegistry:
        """Direct access to plugin registry (for internal components)."""
        return self._plugin_registry

    @property
    def tool_registry(self) -> ToolRegistry:
        """Direct access to tool registry (for internal components)."""
        return self._tool_registry

    @property
    def memory_engine(self) -> MemoryEngine | None:
        """Direct access to memory engine."""
        return self._memory_engine

    @property
    def knowledge_graph(self) -> KnowledgeGraph | None:
        """Direct access to knowledge graph."""
        return self._knowledge_graph

    async def get_memory(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search conversational memory."""
        if not self._memory_engine:
            return []
        return await self._memory_engine.search_memory(query, limit=limit)

    async def get_knowledge(self, query: str) -> dict[str, Any] | None:
        """Query knowledge graph by entity name or alias."""
        if not self._knowledge_graph:
            return None
        return await self._knowledge_graph.resolve(query)

    @property
    def capability_manager(self) -> CapabilityManager | None:
        """Direct access to capability manager."""
        return self._capability_manager

    @property
    def device_registry(self) -> DeviceRegistry | None:
        """Direct access to device registry."""
        return self._device_registry

    def find_providers(self, capability: str) -> list[str]:
        """Find all registered tools or plugins for a capability."""
        if not self._capability_manager:
            return []
        return self._capability_manager.find_providers(capability)

    async def snapshot_state(self) -> dict[str, Any]:
        """Get a full snapshot of the global system state."""
        return await self._state_manager.snapshot()

    def get_permissions_config(self) -> dict[str, str]:
        """Get the current permissions configuration as a dict."""
        return {k: str(v) for k, v in self._permission_manager._permissions.items()}

    async def wait_for_event(
        self, event_type: EventType | str, timeout: float | None = None
    ) -> Event:
        """Wait for a specific event type on the bus."""
        return await self._event_bus.wait_for(event_type, timeout)
