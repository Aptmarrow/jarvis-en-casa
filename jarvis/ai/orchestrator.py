"""AI Orchestrator module for J.A.R.V.I.S."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from jarvis.ai.context_manager import ContextManager
from jarvis.ai.function_calls import build_gemini_tools
from jarvis.ai.intent_classifier import IntentCategory, IntentClassifier
from jarvis.ai.prompts import JARVIS_SYSTEM_PROMPT, build_full_prompt
from jarvis.ai.resource_manager import AIResourceManager
from jarvis.core.api import JarvisAPI
from jarvis.memory.engine import MemoryEngine
from jarvis.memory.knowledge import KnowledgeGraph

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class AIOrchestrator:
    """Gemini Flash Orchestrator with Fast-Path and Memory Integration."""

    def __init__(
        self,
        api: JarvisAPI,
        intent_classifier: IntentClassifier,
        context_manager: ContextManager,
        resource_manager: AIResourceManager,
        memory_engine: MemoryEngine | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> None:
        self.api = api
        self.intent_classifier = intent_classifier
        self.context_manager = context_manager
        self.resource_manager = resource_manager
        self.memory_engine = memory_engine
        self.knowledge_graph = knowledge_graph

        ai_cfg = self.api.get_config("ai")
        self.api_key = os.environ.get("GEMINI_API_KEY") or getattr(
            ai_cfg, "api_key", None
        )
        self.model_name = getattr(ai_cfg, "model", "gemini-3.5-flash")
        self.model: Any = None

        if self.api_key and GENAI_AVAILABLE:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini AI model configured ({self.model_name})")
            except Exception as e:
                logger.error(f"Failed to configure Gemini: {e}")

    async def process_user_request(
        self, text: str, session_id: str = "default"
    ) -> str:
        """Process a user request through the orchestrator pipeline."""
        classification = await self.intent_classifier.classify(text)
        cat = classification.category

        # ─── Fast Path 1: Direct Command ──────────────────────────────────
        if cat == IntentCategory.DIRECT_COMMAND and classification.direct_tool_name:
            tool_name = classification.direct_tool_name
            args = classification.direct_args or {}

            result = await self.api.call_tool(tool_name, args, source="ai_fastpath")

            if result.success:
                res_str = (
                    f"Comando ejecutado: `{tool_name}`. Resultado: {result.data}"
                )
            else:
                res_str = f"Error al ejecutar `{tool_name}`: {result.error}"

            await self._save_memory(text, res_str, session_id)
            return res_str

        # ─── Fast Path 2: Knowledge Graph Query ───────────────────────────
        elif cat == IntentCategory.QUERY_KNOWLEDGE and self.knowledge_graph:
            # Extract query candidate
            query_term = text.lower()
            for prefix in [
                "¿cuál es la ip de ",
                "¿quién es ",
                "¿qué es ",
                "cuál es la ip de ",
                "quién es ",
                "qué es ",
            ]:
                if query_term.startswith(prefix):
                    query_term = query_term[len(prefix) :].strip(" ?")
                    break

            entity = await self.knowledge_graph.resolve(query_term)
            if not entity:
                entity = await self.knowledge_graph.resolve(text)

            if entity:
                entity_name = entity.get("name", "Entidad")
                entity_type = entity.get("type", "desconocido")
                metadata = entity.get("metadata", {})
                res_str = f"🏷️ **{entity_name}** ({entity_type})"
                if metadata:
                    details = ", ".join(f"{k}: {v}" for k, v in metadata.items())
                    res_str += f"\n  Datos: {details}"
                await self._save_memory(text, res_str, session_id)
                return res_str
            # If entity is not found in KnowledgeGraph, fall through to LLM Orchestration Path below

        # ─── Fast Path 3: Greetings & Casual Chat ──────────────────────
        clean_lower = text.strip().lower()
        if clean_lower in {"hola", "hola jarvis", "buenas", "buen dia", "buenas noches", "buenas tardes", "que tal", "hola bot"}:
            res_str = "¡Hola Rodrigo! Jarvis a tu disposición con nivel REALTIME. ¿Qué orden querés ejecutar?"
            await self._save_memory(text, res_str, session_id)
            return res_str

        # ─── LLM Orchestration Path ───────────────────────────────────────
        else:
            context = await self.context_manager.build_context(
                text, classification
            )
            relevant_tools = context.relevant_tools

            if not self.model or not self.api_key or not GENAI_AVAILABLE:
                # LLM not available fallback
                if relevant_tools:
                    tool_names = ", ".join(t.short_name for t in relevant_tools)
                    res_str = (
                        f"🤖 Entendí la consulta. (Sin API Key de Gemini configurada). "
                        f"Herramientas seleccionadas por el Context Manager: [{tool_names}]"
                    )
                else:
                    res_str = "🤖 ¡Hola! Entendí tu mensaje. (API key de Gemini no configurada en .env)."

                await self._save_memory(text, res_str, session_id)
                return res_str

            # Check rate limit
            can_proceed = await self.resource_manager.acquire_slot()
            if not can_proceed:
                return "⚠️ Sistema ocupado (Límite de peticiones alcanzado). Por favor aguardá un momento."

            gemini_tools, tool_map = build_gemini_tools(relevant_tools)
            last_tool_result = None
            system_prompt = build_full_prompt(context)

            # Pool of free tier models to rotate automatically if one is exhausted
            model_pool = [
                self.model_name,
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.5-flash",
            ]
            # Remove duplicates while preserving order
            model_pool = list(dict.fromkeys(model_pool))

            last_exception = None
            for current_model_name in model_pool:
                try:
                    logger.info(f"🤖 Attempting reasoning with model: {current_model_name}")
                    model = genai.GenerativeModel(
                        current_model_name,
                        tools=gemini_tools if gemini_tools else None,
                        system_instruction=system_prompt,
                    )

                    chat = model.start_chat()
                    # Directly send message; if 429 occurs, fall back immediately to next model in pool
                    response_obj = await asyncio.to_thread(chat.send_message, text)
                    self.model_name = current_model_name  # Update active working model
                    logger.info(f"✅ Active model set to: {current_model_name}")
                    break  # Success! Exit model loop
                except Exception as model_err:
                    err_str = str(model_err)
                    is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "ResourceExhausted" in err_str
                    if is_rate_limit:
                        logger.warning(
                            f"⚡ Model {current_model_name} exhausted quota. Instant fallback to next model..."
                        )
                        last_exception = model_err
                        continue
                    else:
                        raise model_err
            else:
                # All models in pool failed
                if last_exception:
                    raise last_exception

            try:

                # Iterative Function Calling loop
                function_calls = self._extract_function_calls(response_obj)
                while function_calls:
                    fc = function_calls[0]
                    gemini_name = fc.name
                    args_dict = dict(fc.args) if fc.args else {}

                    full_name = tool_map.get(gemini_name, gemini_name)
                    tool_result = await self.api.call_tool(
                        full_name, args_dict, source="ai"
                    )
                    last_tool_result = (full_name, tool_result)

                    result_data = (
                        {"result": tool_result.data}
                        if tool_result.success
                        else {"error": tool_result.error}
                    )

                    try:
                        fn_response_part = genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=gemini_name, response=result_data
                            )
                        )
                        response_obj = await self._send_with_retry(
                            chat, fn_response_part
                        )
                    except Exception as fc_err:
                        logger.warning(f"Error sending function result back to Gemini: {fc_err}")
                        break
                    function_calls = self._extract_function_calls(response_obj)

                # Robust text extraction
                final_text = self._safe_extract_text(response_obj)

                # If AI returned no text but a tool was executed, build a useful response
                if not final_text and last_tool_result:
                    tool_name, result = last_tool_result
                    if result.success:
                        final_text = f"✅ Comando ejecutado: `{tool_name}`. Resultado: {result.data}"
                    else:
                        final_text = f"⚠️ Error ejecutando `{tool_name}`: {result.error}"
                elif not final_text:
                    final_text = "Solicitud completada."

                if hasattr(response_obj, "usage_metadata") and response_obj.usage_metadata:
                    tokens = getattr(
                        response_obj.usage_metadata, "total_token_count", 0
                    )
                    self.resource_manager.report_usage(tokens)

                await self._save_memory(text, final_text, session_id)
                return final_text

            except Exception as e:
                error_str = str(e)
                logger.error(f"Error calling Gemini LLM: {e}", exc_info=True)

                # User-friendly rate limit message
                if "429" in error_str or "quota" in error_str.lower() or "ResourceExhausted" in error_str:
                    res_str = (
                        "⚠️ Límite de uso de la API de Gemini alcanzado (20 req/día en free tier). "
                        "Esperá unos segundos e intentá de nuevo, o activá facturación en Google AI Studio "
                        "para tener límites más altos."
                    )
                elif last_tool_result and last_tool_result[1].success:
                    tool_name, result = last_tool_result
                    res_str = f"✅ Comando ejecutado: `{tool_name}`. Resultado: {result.data}"
                else:
                    res_str = f"Ocurrió un error en el razonamiento de la IA: {e}"
                await self._save_memory(text, res_str, session_id)
                return res_str

    async def _send_with_retry(self, chat: Any, message: Any, max_retries: int = 3) -> Any:
        """Send a message to Gemini with automatic retry on 429 rate limit errors."""
        for attempt in range(max_retries + 1):
            try:
                return await asyncio.to_thread(chat.send_message, message)
            except Exception as e:
                error_str = str(e)
                is_rate_limit = "429" in error_str or "ResourceExhausted" in error_str
                if is_rate_limit and attempt < max_retries:
                    wait_time = 5 * (2 ** attempt)  # 5s, 10s, 20s
                    logger.warning(
                        f"Rate limit hit (429), retrying in {wait_time}s "
                        f"(intento {attempt + 1}/{max_retries})..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    async def _save_memory(
        self, user_text: str, response_text: str, session_id: str
    ) -> None:
        """Helper to save interaction to conversational memory."""
        if self.memory_engine:
            try:
                await self.memory_engine.add_message("user", user_text, session_id=session_id)
                await self.memory_engine.add_message("assistant", response_text, session_id=session_id)
            except Exception as e:
                logger.warning(f"Could not save conversation to memory: {e}")

    def _extract_function_calls(self, response_obj: Any) -> list[Any]:
        """Safely extract function call objects from Gemini API response."""
        try:
            if hasattr(response_obj, "function_calls") and response_obj.function_calls:
                return list(response_obj.function_calls)
        except Exception:
            pass
        try:
            if hasattr(response_obj, "candidates") and response_obj.candidates:
                calls = []
                for candidate in response_obj.candidates:
                    if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                                calls.append(part.function_call)
                if calls:
                    return calls
        except Exception:
            pass
        return []

    def _safe_extract_text(self, response_obj: Any) -> str:
        """Safely extract text from a Gemini response, handling all edge cases."""
        # Try the simple .text property first
        try:
            txt = response_obj.text
            if txt:
                return txt.strip()
        except Exception:
            pass

        # Fall back to manually reading text parts from candidates
        try:
            if hasattr(response_obj, "candidates") and response_obj.candidates:
                parts_text = []
                for candidate in response_obj.candidates:
                    if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                parts_text.append(part.text)
                if parts_text:
                    return "\n".join(parts_text).strip()
        except Exception:
            pass

        return ""
