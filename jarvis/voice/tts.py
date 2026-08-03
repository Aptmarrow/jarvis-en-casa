from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)

try:
    from kokoro_onnx import Kokoro
    import soundfile as sf
    HAS_KOKORO = True
except ImportError:
    HAS_KOKORO = False
    logger.warning("kokoro-onnx not found. Falling back to edge-tts as primary engine.")

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    logger.warning("edge-tts python library not found.")


class TTSEngine:
    """Text-to-Speech Engine: Kokoro (local, expressive) with fallback to edge-tts."""

    PLAYERS: ClassVar[list[str]] = ["pw-play", "paplay", "mpv", "ffplay"]
    default_voice: str = "es-ES-AlvaroNeural"  # fallback edge-tts
    kokoro_voice: str = "em_alex"  # Kokoro Spanish male voice (Alex)

    def __init__(self, model_dir: str | Path = "data/models/kokoro") -> None:
        self._kokoro: Kokoro | None = None
        self._model_dir = Path(model_dir)

    def _get_kokoro(self) -> Kokoro | None:
        if not HAS_KOKORO:
            return None
        if self._kokoro is None:
            onnx_path = self._model_dir / "kokoro-v1.0.onnx"
            voices_path = self._model_dir / "voices-v1.0.bin"
            if not onnx_path.exists() or not voices_path.exists():
                logger.warning(f"Kokoro model files not found in {self._model_dir}. Falling back to edge-tts.")
                return None
            try:
                self._kokoro = Kokoro(str(onnx_path), str(voices_path))
                logger.info("✓ Kokoro ONNX local neural voice loaded successfully.")
            except Exception as e:
                logger.error(f"Error loading Kokoro ONNX model: {e}")
                return None
        return self._kokoro

    async def speak(self, text: str, voice: str | None = None) -> bool:
        """Synthesize and play speech asynchronously, with sentence splitting."""
        if not text.strip():
            return False

        tmp_file = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.wav")
        try:
            success = await self._synthesize(text, tmp_file)
            if not success:
                logger.error("Failed to synthesize speech.")
                return False
            return await self._play_audio(tmp_file)
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception as e:
                    logger.debug(f"Failed to remove temp file {tmp_file}: {e}")

    async def _synthesize(self, text: str, output_path: str) -> bool:
        clean = text.replace("*", "").replace("#", "").replace("`", "").replace("~", "").strip()

        kokoro = self._get_kokoro()
        if kokoro:
            try:
                loop = asyncio.get_running_loop()

                def _gen() -> bool:
                    import numpy as np
                    sentences = re.split(r'(?<=[.!?])\s+', clean) or [clean]
                    audio_chunks = []
                    sample_rate = 24000
                    for s in sentences:
                        if not s.strip():
                            continue
                        samples, sample_rate = kokoro.create(
                            s, voice=self.kokoro_voice, speed=1.05, lang="es"
                        )
                        audio_chunks.append(samples)
                    if not audio_chunks:
                        return False
                    full_audio = np.concatenate(audio_chunks)
                    sf.write(output_path, full_audio, sample_rate)
                    return True

                ok = await loop.run_in_executor(None, _gen)
                if ok:
                    return True
            except Exception as e:
                logger.error(f"Kokoro TTS failed, falling back to edge-tts: {e}")

        # Fallback to edge-tts if Kokoro is unavailable or fails
        if HAS_EDGE_TTS:
            try:
                mp3_path = output_path.replace(".wav", ".mp3")
                communicate = edge_tts.Communicate(clean, self.default_voice, pitch="-3Hz", rate="+2%")
                await communicate.save(mp3_path)
                if os.path.exists(mp3_path):
                    os.replace(mp3_path, output_path)
                    return True
            except Exception as e:
                logger.error(f"edge-tts fallback failed: {e}")

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
        logger.error(f"No working audio player found among: {self.PLAYERS}")
        return False
