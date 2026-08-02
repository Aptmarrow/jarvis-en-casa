from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.ai.context_manager import CompiledContext


JARVIS_SYSTEM_PROMPT = """You are J.A.R.V.I.S., an advanced AI assistant.
Your operating environment is a Fedora Linux system.
Always communicate clearly and concisely in Spanish.
Follow system guidelines closely and assist the user proactively.
You are capable of using tools and reading system state to provide accurate information and execute commands."""


def build_full_prompt(context: CompiledContext) -> str:
    """Renders prompt with injected context (Knowledge nodes, State, Recent history)."""
    parts = [JARVIS_SYSTEM_PROMPT, "\n=== SYSTEM CONTEXT ==="]
    
    if context.state_snapshot:
        parts.append(f"\nCurrent State Snapshot:\n{json.dumps(context.state_snapshot, indent=2, default=str)}")
        
    if context.knowledge_nodes:
        parts.append(f"\nRelevant Knowledge Nodes:\n{json.dumps(context.knowledge_nodes, indent=2, default=str)}")
        
    if context.recent_messages:
        parts.append("\nRecent History:")
        for msg in context.recent_messages:
            # Assuming msg is a dict with 'role' and 'content'
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")
            
    parts.append("\n=====================\n")
    
    return "\n".join(parts)
