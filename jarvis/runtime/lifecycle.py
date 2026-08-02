"""Startup/Shutdown orchestration for J.A.R.V.I.S."""

from __future__ import annotations

import logging
from pathlib import Path

from jarvis.ai.context_manager import ContextManager
from jarvis.ai.intent_classifier import IntentClassifier
from jarvis.ai.orchestrator import AIOrchestrator
from jarvis.ai.resource_manager import AIResourceManager
from jarvis.core.api import JarvisAPI
from jarvis.core.config import JarvisConfig
from jarvis.core.event_bus import EventBus
from jarvis.core.permissions import PermissionManager
from jarvis.core.registry import PluginRegistry, ToolRegistry
from jarvis.core.state import StateManager
from jarvis.core.types import Event, EventType
from jarvis.memory.engine import MemoryEngine
from jarvis.memory.knowledge import KnowledgeGraph
from jarvis.runtime.scheduler import Scheduler
from jarvis.runtime.watchdog import Watchdog

logger = logging.getLogger(__name__)


class Lifecycle:
    """Ordered startup and shutdown of all Jarvis subsystems."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self.config: JarvisConfig | None = None
        self.event_bus: EventBus | None = None
        self.state_manager: StateManager | None = None
        self.permission_manager: PermissionManager | None = None
        self.tool_registry: ToolRegistry | None = None
        self.plugin_registry: PluginRegistry | None = None
        self.memory_engine: MemoryEngine | None = None
        self.knowledge_graph: KnowledgeGraph | None = None
        self.intent_classifier: IntentClassifier | None = None
        self.context_manager: ContextManager | None = None
        self.resource_manager: AIResourceManager | None = None
        self.orchestrator: AIOrchestrator | None = None
        self._api: JarvisAPI | None = None
        self.scheduler: Scheduler | None = None
        self.watchdog: Watchdog | None = None
        self._cli = None

    @property
    def api(self) -> JarvisAPI:
        """Access the JarvisAPI instance (raises if startup() not called)."""
        if self._api is None:
            raise RuntimeError("API not initialized. Call startup() first.")
        return self._api

    async def startup(self) -> None:
        """Ordered initialization of the entire system."""
        logger.info("Initializing Jarvis...")

        # 1. Load config
        config_path = self._project_root / "config" / "jarvis.yaml"
        if config_path.exists():
            self.config = JarvisConfig.load(config_path)
        else:
            logger.warning(f"Config not found at {config_path}, using defaults.")
            self.config = JarvisConfig()

        # Configure logging from config
        log_level = self.config.runtime.log_level
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )

        # 2. Create EventBus
        self.event_bus = EventBus()

        # 3. Create StateManager
        self.state_manager = StateManager(self.event_bus)

        # 4. Create PermissionManager
        permissions_path = self._project_root / "config" / "permissions.yaml"
        self.permission_manager = PermissionManager(
            self.state_manager,
            self.event_bus,
            permissions_path if permissions_path.exists() else None,
        )

        # 5. Create Registries
        self.tool_registry = ToolRegistry()
        self.plugin_registry = PluginRegistry()

        # 6. Initialize Memory, Knowledge Graph, Device Registry & Capability Manager
        db_path = self._project_root / self.config.core.data_dir / "jarvis.db"
        self.memory_engine = MemoryEngine(db_path)
        await self.memory_engine.initialize()

        seed_path = self._project_root / "config" / "knowledge_seed.yaml"
        self.knowledge_graph = KnowledgeGraph(db_path)
        await self.knowledge_graph.initialize(
            seed_path if seed_path.exists() else None
        )

        from jarvis.core.capabilities import CapabilityManager
        from jarvis.memory.device_registry import DeviceRegistry

        self.capability_manager = CapabilityManager()
        self.device_registry = DeviceRegistry(db_path)
        await self.device_registry.initialize()

        # 7. Create Core API
        self._api = JarvisAPI(
            self.event_bus,
            self.state_manager,
            self.permission_manager,
            self.tool_registry,
            self.plugin_registry,
            self.config,
            memory_engine=self.memory_engine,
            knowledge_graph=self.knowledge_graph,
            capability_manager=self.capability_manager,
            device_registry=self.device_registry,
        )

        # 8. Discover and load plugins
        if self.config.core.plugins_dir:
            plugins_dir = self._project_root / self.config.core.plugins_dir
        else:
            plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
        await self.plugin_registry.discover_and_load(
            plugins_dir, self._api, self.tool_registry
        )

        # 9. Initialize Intelligence Layer (AI Orchestrator)
        self.intent_classifier = IntentClassifier()
        self.context_manager = ContextManager(
            self._api, self.memory_engine, self.knowledge_graph
        )
        self.resource_manager = AIResourceManager(self.config.ai.rate_limit)
        self.orchestrator = AIOrchestrator(
            self._api,
            self.intent_classifier,
            self.context_manager,
            self.resource_manager,
            self.memory_engine,
            self.knowledge_graph,
        )

        # 10. Start Scheduler if enabled
        if self.config.scheduler.enabled:
            self.scheduler = Scheduler(self._api, self.config, self._project_root)
            await self.scheduler.start()

        # 11. Start Watchdog
        self.watchdog = Watchdog(self._api, self.config.runtime.watchdog_interval)
        await self.watchdog.start()

        # 12. Initialize Voice Pipeline & Transports
        from jarvis.voice.pipeline import VoicePipeline
        from jarvis.transport.websocket import JarvisWebSocketServer

        self.voice_pipeline = VoicePipeline(self._api)
        await self.voice_pipeline.start()
        self._api.voice_pipeline = self.voice_pipeline

        ws_cfg = self.config.transport.websocket
        self.ws_server = JarvisWebSocketServer(
            host=ws_cfg.host,
            port=ws_cfg.port,
            allowed_ips=[
                "192.168.100.3",
                "127.0.0.1",
                "fe80::4024:92ff:fe53:6995",
                "2803:9800:9849:7454:4024:92ff:fe53:6995",
                "2803:9800:9849:7454:78fa:f1fb:3b83:75ba",
            ],
            auth_token="jarvis_moto_g04_owner_secret_token_8765",
            project_root=self._project_root,
        )
        await self.ws_server.start(
            self._api, scheduler=self.scheduler, orchestrator=self.orchestrator
        )

        if self.config.transport.cli.enabled:
            from jarvis.transport.cli import JarvisCLI

            self._cli = JarvisCLI()
            await self._cli.start(
                self._api, scheduler=self.scheduler, orchestrator=self.orchestrator
            )

        # 13. Publish SYSTEM_READY event
        await self.event_bus.publish(
            Event(type=EventType.SYSTEM_READY, source="lifecycle")
        )

        # 14. Log startup summary
        plugins_count = len(self.plugin_registry.list_plugins())
        tools_count = len(self.tool_registry.list_tools())
        logger.info(
            f"✓ Startup complete — {plugins_count} plugins, {tools_count} tools, AI Orchestrator & Moto g04 WS ready."
        )

    async def shutdown(self) -> None:
        """Ordered teardown of the entire system."""
        logger.info("Shutting down Jarvis...")

        # 1. Publish SYSTEM_SHUTDOWN event
        if self.event_bus:
            await self.event_bus.publish(
                Event(type=EventType.SYSTEM_SHUTDOWN, source="lifecycle")
            )

        # 2. Stop WebSocket server
        if hasattr(self, "ws_server") and self.ws_server:
            await self.ws_server.stop()

        # 2. Stop Scheduler
        if self.scheduler:
            await self.scheduler.stop()

        # 3. Stop Watchdog
        if self.watchdog:
            await self.watchdog.stop()

        # 4. Close database connections
        if self.memory_engine:
            await self.memory_engine.close()
        if self.knowledge_graph:
            await self.knowledge_graph.close()

        # 5. Unload plugins (call teardown on each)
        if self.plugin_registry:
            for plugin in self.plugin_registry.list_plugins():
                try:
                    await plugin.teardown()
                except Exception as e:
                    name = getattr(plugin, "name", "?")
                    logger.error(f"Error tearing down plugin {name}: {e}")

        logger.info("⚡ Shutdown complete.")
