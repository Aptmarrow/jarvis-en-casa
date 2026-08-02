from __future__ import annotations

from typing import Any

from jarvis.core.types import ToolMetadata

# Fields that Gemini's Schema protobuf does NOT support
_UNSUPPORTED_SCHEMA_FIELDS = frozenset({
    "default", "title", "examples", "readOnly", "writeOnly",
    "deprecated", "exclusiveMinimum", "exclusiveMaximum",
    "additionalProperties", "$schema", "$id", "$ref",
    "definitions", "allOf", "anyOf", "oneOf", "not",
    "patternProperties", "minProperties", "maxProperties",
    "contentEncoding", "contentMediaType", "if", "then", "else",
})


def _clean_schema(schema: Any) -> Any:
    """Recursively remove fields not supported by the Gemini Schema protobuf."""
    if isinstance(schema, dict):
        cleaned = {}
        for key, value in schema.items():
            if key in _UNSUPPORTED_SCHEMA_FIELDS:
                continue
            cleaned[key] = _clean_schema(value)
        return cleaned
    if isinstance(schema, list):
        return [_clean_schema(item) for item in schema]
    return schema


def _to_gemini_name(full_name: str) -> str:
    """Convert 'system.volume.set_volume' → 'system_volume__set_volume' (unique, Gemini-safe)."""
    # Gemini function names must be alphanumeric + underscores only
    return full_name.replace(".", "_")


def tool_metadata_to_gemini_declaration(tool_meta: ToolMetadata) -> tuple[dict[str, Any], str]:
    """
    Converts ToolMetadata into standard Google Gemini Function Declaration schema.
    Returns (declaration_dict, gemini_safe_name).
    """
    raw_schema = tool_meta.to_json_schema()
    clean = _clean_schema(raw_schema)
    gemini_name = _to_gemini_name(tool_meta.name)
    decl = {
        "name": gemini_name,
        "description": f"[{tool_meta.name}] {tool_meta.description}",
        "parameters": clean,
    }
    return decl, gemini_name


def build_gemini_tools(
    tools: list[ToolMetadata],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Converts a list of ToolMetadata into Gemini function declarations.

    Returns:
        (gemini_tools_list, name_map)
        - gemini_tools_list: list for genai.GenerativeModel(tools=...)
        - name_map: {gemini_safe_name: full_tool_name} for resolving function calls
    """
    if not tools:
        return [], {}

    declarations: list[dict[str, Any]] = []
    name_map: dict[str, str] = {}

    for t in tools:
        decl, gemini_name = tool_metadata_to_gemini_declaration(t)
        declarations.append(decl)
        name_map[gemini_name] = t.name

    return [{"function_declarations": declarations}], name_map

