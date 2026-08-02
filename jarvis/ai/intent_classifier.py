"""Intent Classifier & Fast Path Matcher for J.A.R.V.I.S."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto


class IntentCategory(Enum):
    DIRECT_COMMAND = auto()
    QUERY_KNOWLEDGE = auto()
    LLM_ORCHESTRATION = auto()


@dataclass
class IntentClassificationResult:
    category: IntentCategory
    confidence: float
    direct_tool_name: str | None = None
    direct_args: dict | None = None
    domains: list[str] = field(default_factory=list)


class IntentClassifier:
    """Fast-Path Matcher & Intent Classifier."""

    def __init__(self) -> None:
        self.volume_level_pattern = re.compile(
            r"(?i)(?:sub[ií]|baja|pon[eé]|setea|subir|bajar).*volumen.*?(?:a|en)?\s*(\d+)"
        )
        self.volume_up_pattern = re.compile(r"(?i)(?:sub[ií]|subir|aumentar)\s+(?:el\s+)?volumen")
        self.volume_down_pattern = re.compile(r"(?i)(?:baja|bajar|disminuir)\s+(?:el\s+)?volumen")
        self.mute_pattern = re.compile(r"(?i)(silencia|mutear|unmute|mute)")
        self.brightness_pattern = re.compile(r"(?i)brillo.*?(?:a|en)?\s*(\d+)")
        self.battery_pattern = re.compile(r"(?i)bater[ií]a")
        self.list_files_pattern = re.compile(r"(?i)listar?\s+archivos(?:\s+en\s+(.+))?")
        self.knowledge_pattern = re.compile(
            r"(?i)(?:cu[aá]l es|qu[eé] es|qui[eé]n es|d[oó]nde est[aá]|ip de|impresora|titan|epson)"
        )

    async def classify(self, text: str) -> IntentClassificationResult:
        """Classify user request into Direct Command, Knowledge Query, or LLM Orchestration."""
        text_clean = text.strip()

        # Volume with specific number
        match = self.volume_level_pattern.search(text_clean)
        if match:
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=1.0,
                direct_tool_name="system.volume.set_volume",
                direct_args={"level": int(match.group(1))},
                domains=["volume", "media"],
            )

        # Volume up (no number)
        if self.volume_up_pattern.search(text_clean):
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=0.95,
                direct_tool_name="system.volume.set_volume",
                direct_args={"level": 70},
                domains=["volume", "media"],
            )

        # Volume down (no number)
        if self.volume_down_pattern.search(text_clean):
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=0.95,
                direct_tool_name="system.volume.set_volume",
                direct_args={"level": 30},
                domains=["volume", "media"],
            )

        # Mute
        if self.mute_pattern.search(text_clean):
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=1.0,
                direct_tool_name="system.volume.toggle_mute",
                direct_args={},
                domains=["volume", "media"],
            )

        # Brightness
        match = self.brightness_pattern.search(text_clean)
        if match:
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=1.0,
                direct_tool_name="system.brightness.set_brightness",
                direct_args={"level": int(match.group(1))},
                domains=["system", "display"],
            )

        # List files
        match = self.list_files_pattern.search(text_clean)
        if match:
            path = match.group(1).strip() if match.group(1) else "."
            return IntentClassificationResult(
                category=IntentCategory.DIRECT_COMMAND,
                confidence=0.9,
                direct_tool_name="system.files.list_files",
                direct_args={"path": path},
                domains=["files", "system"],
            )

        # Knowledge queries
        if self.knowledge_pattern.search(text_clean) and not any(
            w in text_clean.lower() for w in ["imprimí", "imprimir", "proceso", "cpu", "matar", "kill"]
        ):
            return IntentClassificationResult(
                category=IntentCategory.QUERY_KNOWLEDGE,
                confidence=0.9,
                domains=["knowledge"],
            )

        # Default fallback to LLM
        return IntentClassificationResult(
            category=IntentCategory.LLM_ORCHESTRATION,
            confidence=1.0,
            domains=[],
        )
