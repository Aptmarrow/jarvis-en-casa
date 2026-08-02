from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.core.types import ToolMetadata

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register_tool(self, metadata: ToolMetadata) -> None:
        self._tools[metadata.name] = metadata
        logger.debug(f"Registered tool: {metadata.name}")

    def unregister_tool(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")

    def get_tool(self, name: str) -> ToolMetadata | None:
        return self._tools.get(name)

    def list_tools(self, plugin_name: str | None = None) -> list[ToolMetadata]:
        if plugin_name:
            return [t for t in self._tools.values() if t.plugin_name == plugin_name]
        return list(self._tools.values())

    def search_tools(self, query: str) -> list[ToolMetadata]:
        query = query.lower()
        results = []
        for t in self._tools.values():
            if query in t.name.lower() or query in t.description.lower():
                results.append(t)
        return results


class PluginRegistry:
    """Registry for all loaded plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, Any] = {}

    def register_plugin(self, plugin: Any) -> None:
        name = getattr(plugin, "name", plugin.__class__.__name__)
        self._plugins[name] = plugin
        logger.info(f"Registered plugin: {name}")

    def unregister_plugin(self, name: str) -> None:
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unregistered plugin: {name}")

    def get_plugin(self, name: str) -> Any | None:
        return self._plugins.get(name)

    def list_plugins(self) -> list[Any]:
        return list(self._plugins.values())

    async def discover_and_load(
        self, plugins_dir: Path, api: JarvisAPI, tool_registry: ToolRegistry
    ) -> None:
        """Auto-discover and load plugins from subdirectories.

        Scans ``plugins_dir`` for subdirectories (system/, network/, media/, …),
        imports every ``.py`` module inside them, finds ``Plugin`` subclasses,
        instantiates them, calls ``setup(api)``, and registers their tools.
        """
        from jarvis.plugins.base import Plugin

        if not plugins_dir.exists() or not plugins_dir.is_dir():
            logger.warning(f"Plugins directory {plugins_dir} does not exist.")
            return

        for subdir in sorted(plugins_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("_"):
                continue

            for module_path in sorted(subdir.glob("*.py")):
                if module_path.name.startswith("_"):
                    continue

                module_name = f"jarvis.plugins.{subdir.name}.{module_path.stem}"
                try:
                    module = importlib.import_module(module_name)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            inspect.isclass(attr)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                            and attr.__module__ == module.__name__
                        ):
                            plugin_instance = attr()
                            await plugin_instance.setup(api)

                            self.register_plugin(plugin_instance)

                            for tool_meta in plugin_instance.get_tools():
                                tool_registry.register_tool(tool_meta)

                            logger.info(
                                f"Loaded plugin: {plugin_instance.name} "
                                f"({len(plugin_instance.get_tools())} tools)"
                            )
                except Exception as e:
                    logger.error(
                        f"Failed to load plugin module {module_name}: {e}",
                        exc_info=True,
                    )

