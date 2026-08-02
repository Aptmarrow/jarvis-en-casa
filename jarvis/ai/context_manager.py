from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis.ai.intent_classifier import IntentClassificationResult
from jarvis.ai.prompts import build_full_prompt
from jarvis.core.api import JarvisAPI
from jarvis.core.types import ToolMetadata


@dataclass
class CompiledContext:
    relevant_tools: list[ToolMetadata]
    recent_messages: list[dict[str, Any]]
    knowledge_nodes: list[dict[str, Any]]
    state_snapshot: dict[str, Any]
    system_prompt: str


class ContextManager:
    """Dynamic Context Filtering for Jarvis AI operations."""

    def __init__(self, api: JarvisAPI, memory_engine: Any = None, knowledge_graph: Any = None) -> None:
        self.api = api
        self.memory_engine = memory_engine
        self.knowledge_graph = knowledge_graph

    async def build_context(self, user_input: str, classification: IntentClassificationResult) -> CompiledContext:
        """Builds a compiled context from current state, memory, and knowledge graph."""
        # 1. Filter relevant tools
        all_tools = self.api.list_tools()
        relevant_tools = []
        
        if classification.domains:
            for tool in all_tools:
                tool_text = (tool.plugin_name + " " + tool.name).lower()
                if any(domain.lower() in tool_text for domain in classification.domains):
                    relevant_tools.append(tool)
        else:
            # Default: potentially provide some common tools or none. 
            # Providing all tools if no specific domain is matched.
            relevant_tools = all_tools

        # 2. Get recent messages
        recent_messages = []
        if self.memory_engine:
            try:
                # Expecting memory engine to provide a method to get recent context
                if hasattr(self.memory_engine, "get_recent"):
                    recent = await self.memory_engine.get_recent(limit=10)
                    if isinstance(recent, list):
                        recent_messages = recent
            except Exception:
                pass  # Handle gracefully if no data or method fails

        # 3. Get knowledge nodes
        knowledge_nodes = []
        if self.knowledge_graph:
            try:
                # Expecting knowledge graph to provide search or query
                if hasattr(self.knowledge_graph, "search"):
                    nodes = await self.knowledge_graph.search(user_input)
                    if isinstance(nodes, list):
                        knowledge_nodes = nodes
            except Exception:
                pass  # Handle gracefully

        # 4. State snapshot
        state_snapshot = {}
        try:
            full_state = await self.api.snapshot_state()
            if classification.domains:
                # Filter state based on relevant domains
                for k, v in full_state.items():
                    if any(domain.lower() in k.lower() for domain in classification.domains):
                        state_snapshot[k] = v
            
            if not state_snapshot:
                state_snapshot = full_state
        except Exception:
            pass

        # 5. Compile Context
        context_without_prompt = CompiledContext(
            relevant_tools=relevant_tools,
            recent_messages=recent_messages,
            knowledge_nodes=knowledge_nodes,
            state_snapshot=state_snapshot,
            system_prompt=""
        )

        # Inject final compiled prompt
        context_without_prompt.system_prompt = build_full_prompt(context_without_prompt)

        return context_without_prompt
