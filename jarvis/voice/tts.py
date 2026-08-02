from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from typing import ClassVar

logger = logging.getLogger(__name__)

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    logger.warning("edge-tts python library not found. Falling back to CLI or mocking if missing.")


class TTSEngine:
    """Text-to-Speech Engine using edge-tts and system audio players."""

    PLAYERS: ClassVar[list[str]] = ["pw-play", "paplay", "mpv", "ffplay"]
    default_voice: str = "es-AR-TomasNeural"

    async def speak(self, text: str, voice: str = "es-AR-TomasNeural") -> bool:
        """Synthesize and play speech asynchronously."""
        if not text.strip():
            return False

        tmp_file = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")
        try:
            # 1. Synthesize
            success = await self._synthesize(text, voice, tmp_file)
            if not success:
                logger.error("Failed to synthesize speech.")
                return False

            # 2. Play
            played = await self._play_audio(tmp_file)
            return played
        finally:
            # 3. Cleanup
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception as e:
                    logger.debug(f"Failed to remove temp file {tmp_file}: {e}")

    async def _synthesize(self, text: str, voice: str, output_path: str) -> bool:
        if HAS_EDGE_TTS:
            try:
                communicate = edge_tts.Communicate(text, voice)
                await communicate.save(output_path)
                return True
            except Exception as e:
                logger.error(f"edge-tts Python API failed: {e}")
                # Fallthrough to CLI

        # Fallback to CLI
        try:
            process = await asyncio.create_subprocess_exec(
                "edge-tts", f"--voice={voice}", f"--text={text}", f"--write-media={output_path}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            if process.returncode == 0:
                return True
            else:
                logger.error(f"edge-tts CLI failed: {stderr.decode().strip()}")
                return False
        except FileNotFoundError:
            logger.error("edge-tts CLI not installed. Cannot synthesize speech.")
            return False
        except Exception as e:
            logger.error(f"Unexpected error synthesizing speech: {e}")
            return False

    async def _play_audio(self, file_path: str) -> bool:
        for player in self.PLAYERS:
            try:
                process = await asyncio.create_subprocess_exec(
                    player, file_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await process.communicate()
                if process.returncode == 0:
                    return True
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug(f"Error playing with {player}: {e}")

        logger.error(f"Failed to play audio. No working audio player found among: {self.PLAYERS}")
        return False
