from __future__ import annotations

import ast
import logging
import operator
from pathlib import Path
from typing import Any

import yaml

from jarvis.core.event_bus import EventBus
from jarvis.core.state import StateManager
from jarvis.core.types import Event, EventType, PermissionCheck, PermissionLevel

logger = logging.getLogger(__name__)


def _evaluate_condition(condition: str, state: dict[str, Any]) -> bool:
    """Evaluate a simple condition string like 'state.night_mode == true'."""
    try:
        if not condition:
            return True

        # Simple tokenization for basic conditions
        parts = condition.split()
        if len(parts) == 3:
            left, op, right = parts

            if left.startswith("state."):
                key = left[6:]  # Remove 'state.' prefix
                # Support both 'user_confidence' and 'user.confidence' notation
                left_val = state.get(key)
                if left_val is None:
                    # Try with dots replaced by underscores and vice versa
                    left_val = state.get(key.replace("_", "."))
                if left_val is None:
                    left_val = state.get(key.replace(".", "_"))
            else:
                left_val = left

            if right.lower() == "true":
                right_val: Any = True
            elif right.lower() == "false":
                right_val = False
            else:
                try:
                    right_val = float(right)
                except ValueError:
                    right_val = right

            # Null-safe comparisons
            if left_val is None:
                return False

            if op == "==":
                return left_val == right_val
            elif op == "!=":
                return left_val != right_val
            elif op == "<":
                return left_val < right_val
            elif op == ">":
                return left_val > right_val
            elif op == "<=":
                return left_val <= right_val
            elif op == ">=":
                return left_val >= right_val
    except Exception as e:
        logger.warning(f"Failed to evaluate condition '{condition}': {e}")
    return False



class PermissionManager:
    """Manages permissions and contextual rules."""

    def __init__(self, state_manager: StateManager, event_bus: EventBus, config_path: str | Path | None = None) -> None:
        self._state_manager = state_manager
        self._event_bus = event_bus
        self._permissions: dict[str, PermissionLevel] = {}
        self._rules: list[dict[str, Any]] = []
        
        if config_path:
            self.load(config_path)

    def load(self, config_path: str | Path) -> None:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            perms = data.get("permissions", {})
            for k, v in perms.items():
                self._permissions[k] = PermissionLevel(v)
                
            self._rules = data.get("rules", [])
        except Exception as e:
            logger.warning(f"Could not load permissions from {config_path}: {e}")

    async def check(self, required_permissions: list[str], context: dict[str, Any] | None = None) -> PermissionCheck:
        if not required_permissions:
            return PermissionCheck(granted=True, level=PermissionLevel.AUTO)
            
        state = await self._state_manager.snapshot()
        
        # Base permissions
        evaluated_perms = {}
        for p in required_permissions:
            evaluated_perms[p] = self._permissions.get(p, PermissionLevel.CONFIRM_ALWAYS)
            
        # Apply rules
        for rule in self._rules:
            condition = rule.get("when")
            if condition and _evaluate_condition(condition, state):
                overrides = rule.get("override", {})
                for p in required_permissions:
                    if p in overrides:
                        evaluated_perms[p] = PermissionLevel(overrides[p])
                    if "*" in overrides:
                        evaluated_perms[p] = PermissionLevel(overrides["*"])
                        
        levels = list(evaluated_perms.values())
        
        if PermissionLevel.DENY in levels:
            return PermissionCheck(
                granted=False, 
                level=PermissionLevel.DENY, 
                permissions_checked=required_permissions, 
                denial_reason="Permission denied by rules."
            )
            
        if PermissionLevel.CONFIRM_ALWAYS in levels:
            return PermissionCheck(
                granted=False,
                level=PermissionLevel.CONFIRM_ALWAYS,
                permissions_checked=required_permissions,
                requires_confirmation=True
            )
            
        if PermissionLevel.CONFIRM in levels:
            return PermissionCheck(
                granted=False,
                level=PermissionLevel.CONFIRM,
                permissions_checked=required_permissions,
                requires_confirmation=True
            )
            
        return PermissionCheck(
            granted=True,
            level=PermissionLevel.AUTO,
            permissions_checked=required_permissions
        )

    async def request_confirmation(self, tool_name: str, permissions: list[str]) -> bool:
        """Publish a permission request and wait for a response."""
        req_event = Event(
            type=EventType.PERMISSION_REQUEST,
            data={"tool_name": tool_name, "permissions": permissions},
            source="permission_manager"
        )
        
        await self._event_bus.publish(req_event)
        
        try:
            # In a real scenario, we'd match the response to the request_id.
            # Simplified for now.
            resp_event = await self._event_bus.wait_for(EventType.PERMISSION_RESPONSE, timeout=30.0)
            return resp_event.data.get("granted", False)
        except TimeoutError:
            logger.warning(f"Permission request for {tool_name} timed out.")
            return False
