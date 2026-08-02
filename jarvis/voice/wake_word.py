from __future__ import annotations

import asyncio
import logging
import struct
from typing import Callable, Coroutine

logger = logging.getLogger(__name__)

try:
    import pvporcupine
    from pvrecorder import PvRecorder
    HAS_PORCUPINE = True
except ImportError:
    HAS_PORCUPINE = False
    logger.warning("pvporcupine or pvrecorder not found. Wake word detection will be disabled.")


class WakeWordEngine:
    """Wake Word Engine using Picovoice Porcupine."""

    def __init__(self, access_key: str | None = None, keyword: str = "jarvis") -> None:
        self.access_key = access_key
        self.keyword = keyword
        self._is_listening = False
        self._porcupine = None
        self._recorder = None
        self._listen_task: asyncio.Task | None = None

    async def start_listening(self, callback: Callable[[], Coroutine]) -> None:
        """Start listening for the wake word."""
        if not HAS_PORCUPINE:
            logger.error("Cannot start wake word engine: dependencies not installed.")
            return

        if not self.access_key:
            logger.error("Picovoice access key required for wake word detection.")
            return

        if self._is_listening:
            return

        try:
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=[self.keyword] if self.keyword in pvporcupine.KEYWORDS else [] # This needs to handle custom keywords or built-ins
            )
            # Use default built-in if it's a known keyword, or just try to pass it directly if custom logic was added
            
            self._recorder = PvRecorder(device_index=-1, frame_length=self._porcupine.frame_length)
            self._recorder.start()
            self._is_listening = True

            loop = asyncio.get_running_loop()
            self._listen_task = loop.create_task(self._listen_loop(callback))
            logger.info(f"Started listening for wake word: '{self.keyword}'")
            
        except Exception as e:
            logger.error(f"Failed to initialize wake word engine: {e}")
            self.stop_listening()

    async def _listen_loop(self, callback: Callable[[], Coroutine]) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self._is_listening and self._recorder:
                # read() is blocking, run in executor
                pcm = await loop.run_in_executor(None, self._recorder.read)
                if self._porcupine:
                    result = self._porcupine.process(pcm)
                    if result >= 0:
                        logger.info("Wake word detected!")
                        # Call the callback asynchronously
                        asyncio.create_task(callback())
        except Exception as e:
            logger.error(f"Error in wake word loop: {e}")
        finally:
            self.stop_listening()

    def stop_listening(self) -> None:
        """Stop listening for the wake word."""
        self._is_listening = False
        
        if self._recorder:
            try:
                self._recorder.stop()
                self._recorder.delete()
            except Exception:
                pass
            self._recorder = None
            
        if self._porcupine:
            try:
                self._porcupine.delete()
            except Exception:
                pass
            self._porcupine = None
            
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        
        logger.info("Wake word listening stopped.")
