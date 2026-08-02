from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from jarvis.core.types import ToolMetadata, ToolParameter

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class Plugin:
    name: str = ""
    description: str = ""
    version: str = "0.1.0"

    def __init__(self) -> None:
        self._api: JarvisAPI | None = None
        self._tools: list[ToolMetadata] = []
        
        # Scan for tools
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name)
            if hasattr(attr, "_tool_metadata"):
                # Copy the metadata so we don't modify the class-level object
                orig_metadata: ToolMetadata = attr._tool_metadata
                
                # Reconstruct full name if necessary
                tool_name = orig_metadata.name
                if not tool_name.startswith(f"{self.name}."):
                    tool_name = f"{self.name}.{tool_name}"
                    
                metadata = ToolMetadata(
                    name=tool_name,
                    description=orig_metadata.description,
                    plugin_name=self.name,
                    parameters=orig_metadata.parameters,
                    permissions=orig_metadata.permissions,
                    handler=getattr(self, attr_name) # Bind to instance method
                )
                
                self._tools.append(metadata)

    async def setup(self, api: JarvisAPI) -> None:
        self._api = api

    async def teardown(self) -> None:
        pass

    @property
    def api(self) -> JarvisAPI:
        if self._api is None:
            raise RuntimeError(f"Plugin {self.name} has no API (setup not called)")
        return self._api

    def get_tools(self) -> list[ToolMetadata]:
        return self._tools


def tool(description: str, permissions: list[str] | None = None, parameters: list[ToolParameter] | None = None) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._tool_metadata = ToolMetadata(
            name=func.__name__,
            description=description,
            plugin_name="",
            parameters=parameters or [],
            permissions=permissions or [],
        )
        return func
    return decorator
