from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import uuid

logger = logging.getLogger(__name__)

try:
    import whisper
    HAS_WHISPER_LIB = True
except ImportError:
    HAS_WHISPER_LIB = False
    logger.warning("openai-whisper python library not found. Falling back to CLI.")


class STTEngine:
    """Speech-to-Text Engine using Whisper and Gemini Multimodal fallback."""

    def __init__(self) -> None:
        self._model = None

    def _get_whisper(self):
        try:
            import whisper
            return whisper
        except ImportError:
            return None

    async def _load_model(self, model_size: str = "tiny"):
        whisper_lib = self._get_whisper()
        if not whisper_lib:
            return
        if self._model is None:
            try:
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(None, whisper_lib.load_model, model_size)
                logger.info(f"✓ Whisper model '{model_size}' loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load Whisper model '{model_size}': {e}")
                self._model = None

    async def transcribe_audio_file(self, audio_path: str, model_size: str = "base") -> str:
        """Transcribe an audio file to text."""
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return ""

        whisper_lib = self._get_whisper()
        if whisper_lib:
            await self._load_model(model_size)
            if self._model:
                try:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, lambda: self._model.transcribe(audio_path, language="es", fp16=False)
                    )
                    text = result.get("text", "").strip() if isinstance(result, dict) else ""
                    if text:
                        return text
                except Exception as e:
                    logger.error(f"Whisper transcription failed: {e}")

        return ""

    async def transcribe_audio_bytes(self, audio_bytes: bytes, mime_type: str = "audio/webm", model_size: str = "base") -> str:
        """Transcribe audio bytes using local Whisper or Gemini STT pool."""
        loop = asyncio.get_running_loop()

        # Step 1: Convert audio bytes to 16kHz mono WAV using ffmpeg auto-detection
        def _convert_to_wav(raw_bytes: bytes) -> tuple[bytes, str]:
            in_tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
            out_tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            try:
                in_tmp.write(raw_bytes)
                in_tmp.close()
                out_tmp.close()

                proc = subprocess.run(
                    ["ffmpeg", "-y", "-i", in_tmp.name, "-ar", "16000", "-ac", "1", "-f", "wav", out_tmp.name],
                    capture_output=True
                )
                if proc.returncode == 0 and os.path.exists(out_tmp.name):
                    with open(out_tmp.name, "rb") as f:
                        wav_out = f.read()
                    if len(wav_out) > 44:
                        logger.info(f"🎙️ Auto-converted {len(raw_bytes)} bytes ({mime_type}) -> {len(wav_out)} bytes 16kHz WAV")
                        return wav_out, "audio/wav"
                logger.warning(f"ffmpeg conversion warning: {proc.stderr.decode('utf-8', errors='ignore')[:200]}")
            except Exception as convert_err:
                logger.error(f"ffmpeg exception: {convert_err}")
            finally:
                for p in [in_tmp.name, out_tmp.name]:
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            return raw_bytes, mime_type

        proc_bytes, final_mime = await loop.run_in_executor(None, _convert_to_wav, audio_bytes)

        # Step 2: Try local Whisper model first (offline, fast < 0.5s)
        tmp_file = os.path.join(tempfile.gettempdir(), f"stt_{uuid.uuid4().hex}.wav")
        try:
            with open(tmp_file, "wb") as f:
                f.write(proc_bytes)
            local_text = await self.transcribe_audio_file(tmp_file, model_size=model_size)
            if local_text and len(local_text) > 1:
                logger.info(f"🎙️ Local Whisper STT: '{local_text}'")
                return local_text
        except Exception as local_err:
            logger.debug(f"Local Whisper STT failed: {local_err}")
        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass

        # Step 3: Try Gemini STT model pool with inline_data format
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            stt_models = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash"]
            prompt = "Transcribí de forma exacta y precisa ÚNICAMENTE las palabras habladas en español en este audio. Si hay silencio o no hay voz clara, no respondas nada."

            for m_name in stt_models:
                try:
                    def _do_gemini_stt(model_name: str) -> str:
                        model = genai.GenerativeModel(model_name)
                        res = model.generate_content([
                            prompt,
                            {"inline_data": {"mime_type": final_mime, "data": proc_bytes}}
                        ])
                        if res and hasattr(res, "text") and res.text:
                            return res.text.strip()
                        return ""

                    text = await loop.run_in_executor(None, _do_gemini_stt, m_name)
                    clean_text = text.strip('"\'` .')
                    if clean_text and not clean_text.lower().startswith("como no") and not clean_text.lower().startswith("no adjuntaste") and not clean_text.lower().startswith("no se adjuntó"):
                        logger.info(f"🎙️ Gemini STT ({m_name}): '{clean_text}'")
                        return clean_text
                except Exception as e:
                    logger.debug(f"STT model {m_name} failed: {e}")

        return ""
