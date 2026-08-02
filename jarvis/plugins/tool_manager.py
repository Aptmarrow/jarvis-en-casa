from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from jarvis.core.types import Event, EventType, ToolRequest, ToolResult

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self, api: JarvisAPI) -> None:
        self.api = api

    async def execute(self, request: ToolRequest) -> ToolResult:
        start_time = time.perf_counter()
        tool = self.api.get_tool(request.tool_name)
        
        if not tool:
            return ToolResult(
                request_id=request.request_id,
                tool_name=request.tool_name,
                success=False,
                error="Tool not found",
            )
            
        try:
            perm_check = await self.api.check_permissions(tool.permissions)
            
            if perm_check.requires_confirmation:
                event = Event(
                    type=EventType.PERMISSION_REQUEST, 
                    data={"tool_name": tool.name, "permissions": tool.permissions, "request_id": request.request_id}
                )
                await self.api.publish(event)
                
                try:
                    # Assume api provides a way to wait for a specific event
                    # This is a conceptual implementation of waiting for confirmation
                    if hasattr(self.api, "wait_for_event"):
                        response_event = await asyncio.wait_for(
                            self.api.wait_for_event(
                                EventType.PERMISSION_RESPONSE, 
                                lambda e: e.data.get("request_id") == request.request_id
                            ),
                            timeout=60.0
                        )
                        if not response_event.data.get("granted"):
                            return ToolResult(request_id=request.request_id, tool_name=tool.name, success=False, error="Permission denied")
                    else:
                        # Fallback if wait_for_event isn't implemented
                        return ToolResult(request_id=request.request_id, tool_name=tool.name, success=False, error="Permission denied (no confirmation mechanism)")
                except asyncio.TimeoutError:
                    return ToolResult(request_id=request.request_id, tool_name=tool.name, success=False, error="Permission denied (timeout)")
                    
            elif not perm_check.granted:
                return ToolResult(request_id=request.request_id, tool_name=tool.name, success=False, error="Permission denied")

            if tool.handler is None:
                raise ValueError("Tool handler missing")
                
            if asyncio.iscoroutinefunction(tool.handler):
                data = await tool.handler(**request.arguments)
            else:
                data = tool.handler(**request.arguments)
            
            execution_time = (time.perf_counter() - start_time) * 1000.0
            
            result = ToolResult(
                request_id=request.request_id,
                tool_name=tool.name,
                success=True,
                data=data,
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000.0
            result = ToolResult(
                request_id=request.request_id,
                tool_name=request.tool_name,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )
            
        await self.api.publish(Event(type=EventType.TOOL_RESULT, data={"result": result}))
        return result
