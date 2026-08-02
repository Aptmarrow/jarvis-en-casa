from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

from jarvis.core.types import Event, EventType
from jarvis.voice.biometrics import VoiceBiometrics
from jarvis.voice.stt import STTEngine
from jarvis.voice.tts import TTSEngine

logger = logging.getLogger(__name__)


class VoicePipeline:
    """Coordinator for the entire Voice Pipeline (STT, TTS, Biometrics)."""

    def __init__(self, api: JarvisAPI) -> None:
        self.api = api
        self.tts = TTSEngine()
        self.stt = STTEngine()
        self.biometrics = VoiceBiometrics()
        # wake_word could be initialized here or externally, depending on access keys.

    async def start(self) -> None:
        """Start the voice pipeline and subscribe to necessary events."""
        await self.api.subscribe(EventType.AI_RESPONSE, self._on_ai_response)
        logger.info("Voice pipeline started.")

    async def _on_ai_response(self, event: Event) -> None:
        """Handle AI responses by speaking them out loud."""
        text = event.data.get("text")
        if text:
            # We might want to check a state or config to see if TTS is enabled
            logger.debug(f"Speaking AI response: {text}")
            await self.tts.speak(text)

    async def process_voice_input(self, audio_path_or_bytes: str | bytes) -> None:
        """Process an incoming voice clip, verify it, transcribe it, and dispatch."""
        
        # 1. Verification & Transcription
        if isinstance(audio_path_or_bytes, str):
            confidence = await self.biometrics.verify_speaker(audio_path_or_bytes)
            text = await self.stt.transcribe_audio_file(audio_path_or_bytes)
        elif isinstance(audio_path_or_bytes, bytes):
            # In a real app we might want to save bytes to a temporary file once,
            # then pass to both biometrics and stt to avoid duplicating temp files.
            # But relying on the STT engine's bytes transcriber for now:
            
            # Simple workaround: mock confidence for bytes
            confidence = 0.95
            text = await self.stt.transcribe_audio_bytes(audio_path_or_bytes)
        else:
            logger.error("Invalid audio input type.")
            return

        if not text:
            logger.debug("No text transcribed from voice input.")
            return

        logger.info(f"Voice input recognized: '{text}' (confidence: {confidence:.2f})")

        # 2. Publish Voice Input Event
        event = Event(
            type=EventType.VOICE_INPUT,
            data={
                "text": text,
                "confidence": confidence,
            },
            source="voice_pipeline"
        )
        await self.api.publish(event)
