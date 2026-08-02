"""Secure WebSocket Transport for Moto g04 Dedicated Companion App with Protocol v1."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from jarvis.core.types import Event, EventPriority, EventType

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI
    from jarvis.runtime.scheduler import Scheduler

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


class JarvisWebSocketServer:
    """Secure WebSocket Server & Companion App Host with Protocol v1."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        allowed_ips: list[str] | None = None,
        auth_token: str | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.allowed_ips = allowed_ips or [
            "192.168.100.3",
            "127.0.0.1",
            "fe80::4024:92ff:fe53:6995",
            "2803:9800:9849:7454:4024:92ff:fe53:6995",
            "2803:9800:9849:7454:78fa:f1fb:3b83:75ba",
        ]
        self.auth_token = (
            auth_token or "jarvis_moto_g04_owner_secret_token_8765"
        )
        self._project_root = project_root or Path.cwd()
        self.api: JarvisAPI | None = None
        self.scheduler: Scheduler | None = None
        self.orchestrator: Any = None
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._active_sockets: set[web.WebSocketResponse] = set()
        self._sequence_counter: int = 0

    async def start(
        self,
        api: JarvisAPI,
        scheduler: Scheduler | None = None,
        orchestrator: Any = None,
    ) -> None:
        """Start the secure HTTP/WebSocket server."""
        self.api = api
        self.scheduler = scheduler
        self.orchestrator = orchestrator

        # Subscribe to events to push to WebSocket clients
        await self.api.subscribe("*", self._broadcast_event)

        # Register Moto g04 in DeviceRegistry & KnowledgeGraph on startup
        if self.api.device_registry:
            await self.api.device_registry.register_or_update(
                mac="40:24:92:53:69:95",
                ip="192.168.100.3",
                hostname="Moto-g04-Rodrigo",
                alias="Moto g04 de Rodrigo",
                vendor="Motorola",
            )
        if self.api.knowledge_graph:
            await self.api.knowledge_graph.add_entity(
                name="Moto g04 de Rodrigo",
                entity_type="smartphone",
                aliases=["mi celular", "el moto g04", "mi moto g04"],
                metadata={
                    "ip": "192.168.100.3",
                    "role": "owner_device",
                    "priority": "realtime",
                },
            )

        self._app = web.Application()

        # Routes
        self._app.router.add_get("/", self._index_handler)
        self._app.router.add_get("/index.html", self._index_handler)
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/api/status", self._status_handler)
        self._app.router.add_get("/api/telemetry", self._telemetry_handler)

        # Serve static companion PWA files
        companion_dir = self._project_root / "web" / "companion"
        if companion_dir.exists():
            self._app.router.add_static("/", companion_dir)
            logger.info(f"Serving Moto g04 Companion App from {companion_dir}")

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        logger.info(
            f"🔒 Secure WebSocket Protocol v1 Server active on ws://{self.host}:{self.port}/ws "
            f"(Whitelisted IP: 192.168.100.3)"
        )

    async def stop(self) -> None:
        """Stop the HTTP/WebSocket server."""
        for ws in list(self._active_sockets):
            await ws.close(code=1001, message=b"Server shutting down")
        self._active_sockets.clear()

        if self._runner:
            await self._runner.cleanup()
        logger.info("WebSocket Server stopped.")

    def _is_ip_allowed(self, remote_ip: str) -> bool:
        """IP check (secondary guardrail alongside token & key auth)."""
        if remote_ip in ("127.0.0.1", "::1", "localhost"):
            return True
        for allowed in self.allowed_ips:
            if remote_ip == allowed or allowed in remote_ip:
                return True
        return False

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle incoming Protocol v1 WebSocket connection."""
        remote_ip = request.remote or "unknown"

        # Token Auth
        auth_header = request.headers.get("Authorization", "")
        token = request.query.get("token") or (
            auth_header[7:] if auth_header.startswith("Bearer ") else auth_header
        )

        if token != self.auth_token:
            logger.warning(
                f"⛔ SECURITY ALERT: Unauthorized connection attempt from IP {remote_ip}"
            )
            return web.Response(
                status=401, text="401 Unauthorized: Invalid Device Token"
            )

        ws = web.WebSocketResponse(heartbeat=30.0)
        await ws.prepare(request)
        self._active_sockets.add(ws)

        logger.info(
            f"⚡ REALTIME WebSocket Protocol v1 Connected: Moto g04 ({remote_ip})"
        )

        # Welcome message in Protocol v1 format
        await self._send_v1_msg(
            ws,
            msg_type="welcome",
            payload={
                "device": "Moto g04 de Rodrigo",
                "status": "connected",
                "priority": "REALTIME",
                "security": "token_key_auth",
            },
        )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._process_proto_v1_msg(data, ws, remote_ip)
                    except json.JSONDecodeError:
                        await self._send_v1_msg(
                            ws,
                            msg_type="error",
                            payload={"message": "Invalid JSON format"},
                        )

                elif msg.type == WSMsgType.BINARY:
                    # Complete WebM audio recording from Moto g04 (REALTIME priority)
                    logger.info(
                        f"🎤 Received audio recording ({len(msg.data)} bytes) from Moto g04"
                    )
                    transcription = ""
                    if hasattr(self.api, "voice_pipeline") and self.api.voice_pipeline:
                        try:
                            transcription = await self.api.voice_pipeline.stt.transcribe_audio_bytes(
                                msg.data, mime_type="audio/webm"
                            )
                        except Exception as stt_err:
                            logger.error(f"Voice transcription error: {stt_err}", exc_info=True)

                    if transcription:
                        logger.info(f"🗣️ Transcribed Voice Command: '{transcription}'")
                        try:
                            if self.orchestrator:
                                response_text = await self.orchestrator.process_user_request(
                                    transcription, session_id="moto_g04"
                                )
                            else:
                                response_text = f"🤖 Transcripción: {transcription}"
                        except Exception as exc:
                            logger.error(f"Error processing voice command '{transcription}': {exc}", exc_info=True)
                            response_text = f"⚠️ Error procesando comando de voz: {exc}"

                        await self._send_v1_msg(
                            ws,
                            msg_type="ai_response",
                            payload={
                                "request_text": f"🎙️ {transcription}",
                                "response_text": response_text,
                            },
                        )
                    else:
                        await self._send_v1_msg(
                            ws,
                            msg_type="ai_response",
                            payload={
                                "request_text": "🎙️ (Audio no reconocido)",
                                "response_text": "⚠️ No pude entender el audio. Por favor intentá hablar más claro o más cerca del micrófono.",
                            },
                        )

                elif msg.type == WSMsgType.ERROR:
                    logger.error(
                        f"WebSocket connection error with Moto g04: {ws.exception()}"
                    )
        finally:
            self._active_sockets.discard(ws)
            logger.info(f"WebSocket Disconnected: Moto g04 ({remote_ip})")

        return ws

    async def _send_v1_msg(
        self,
        ws: web.WebSocketResponse,
        msg_type: str,
        payload: dict[str, Any],
        msg_id: str | None = None,
    ) -> None:
        """Format and send a message using Protocol v1 schema."""
        self._sequence_counter += 1
        msg = {
            "v": PROTOCOL_VERSION,
            "type": msg_type,
            "id": msg_id or f"msg_{self._sequence_counter}",
            "seq": self._sequence_counter,
            "ts": asyncio.get_event_loop().time(),
            "payload": payload,
        }
        await ws.send_json(msg)

    async def _process_proto_v1_msg(
        self, data: dict[str, Any], ws: web.WebSocketResponse, remote_ip: str
    ) -> None:
        """Process structured Protocol v1 messages from Moto g04."""
        version = data.get("v", 1)
        msg_type = data.get("type", "chat")
        payload = data.get("payload", {})
        msg_id = data.get("id")

        if msg_type == "heartbeat":
            await self._send_v1_msg(
                ws, msg_type="heartbeat_ack", payload={"pong": True}, msg_id=msg_id
            )

        elif msg_type == "chat":
            text = payload.get("text", "").strip() if isinstance(payload, dict) else str(payload).strip()
            if not text:
                return

            # Publish Event with REALTIME Priority
            event = Event(
                type=EventType.TEXT_INPUT,
                data={"text": text, "source": "moto_g04"},
                source="moto_g04",
                priority=EventPriority.REALTIME,
            )
            assert self.api is not None
            await self.api.publish(event)

            try:
                if self.orchestrator:
                    response_text = await self.orchestrator.process_user_request(
                        text, session_id="moto_g04"
                    )
                else:
                    response_text = f"🤖 Recibido: {text} (Orchestrator en preparación)"
            except Exception as exc:
                logger.error(f"Error in chat processing for '{text}': {exc}", exc_info=True)
                response_text = f"⚠️ Error interno: {exc}"

        elif msg_type == "voice_audio":
            b64_str = payload.get("audio_b64", "") if isinstance(payload, dict) else ""
            if not b64_str:
                logger.warning("Received empty voice_audio payload from Moto g04")
                return

            try:
                # Strip Data URL prefix if present ("data:audio/webm;base64,...")
                if "," in b64_str:
                    b64_str = b64_str.split(",", 1)[-1]

                # Fix padding if length is not a multiple of 4
                missing_padding = len(b64_str) % 4
                if missing_padding:
                    b64_str += "=" * (4 - missing_padding)

                audio_bytes = base64.b64decode(b64_str)
                try:
                    with open("/tmp/last_received_moto.bin", "wb") as f_save:
                        f_save.write(audio_bytes)
                except Exception:
                    pass
                logger.info(
                    f"🎤 [PROTOCOL V1] Received voice recording ({len(audio_bytes)} bytes) from Moto g04 (saved to /tmp/last_received_moto.bin)"
                )
            except Exception as b64_err:
                logger.error(f"Error decoding base64 voice audio: {b64_err}")
                return

            mime_type = payload.get("mime_type", "audio/webm") if isinstance(payload, dict) else "audio/webm"
            transcription = ""
            if hasattr(self.api, "voice_pipeline") and self.api.voice_pipeline:
                try:
                    transcription = await self.api.voice_pipeline.stt.transcribe_audio_bytes(
                        audio_bytes, mime_type=mime_type
                    )
                except Exception as stt_err:
                    logger.error(f"Voice STT error: {stt_err}", exc_info=True)

            if transcription:
                logger.info(f"🗣️ Transcribed Voice Command: '{transcription}'")
                try:
                    if self.orchestrator:
                        response_text = await self.orchestrator.process_user_request(
                            transcription, session_id="moto_g04"
                        )
                    else:
                        response_text = f"🤖 Transcripción: {transcription}"
                except Exception as exc:
                    logger.error(f"Error processing voice command '{transcription}': {exc}", exc_info=True)
                    response_text = f"⚠️ Error procesando comando de voz: {exc}"

                await self._send_v1_msg(
                    ws,
                    msg_type="ai_response",
                    payload={
                        "request_text": f"🎙️ {transcription}",
                        "response_text": response_text,
                    },
                    msg_id=msg_id,
                )
            else:
                logger.warning("Voice transcription returned empty result.")
                await self._send_v1_msg(
                    ws,
                    msg_type="ai_response",
                    payload={
                        "request_text": "🎙️ (Audio no reconocido)",
                        "response_text": "⚠️ No pude entender el audio. Por favor hablale más cerca al micrófono del cel.",
                    },
                    msg_id=msg_id,
                )

        elif msg_type == "device_telemetry":
            # Update StateManager with Moto g04 telemetry
            assert self.api is not None
            if isinstance(payload, dict):
                batt = payload.get("battery_level")
                charging = payload.get("charging")
                if batt is not None:
                    await self.api.set_state("user.device.battery", batt, source="moto_g04")
                if charging is not None:
                    await self.api.set_state("user.device.charging", charging, source="moto_g04")
                await self.api.set_state("user.device.last_seen", asyncio.get_event_loop().time(), source="moto_g04")
                logger.info(f"📱 Moto g04 Telemetry: Battery {batt}%, Charging: {charging}")

        elif msg_type == "permission_response":
            req_id = payload.get("request_id")
            granted = payload.get("granted", False)
            assert self.api is not None
            await self.api.publish(
                Event(
                    type=EventType.PERMISSION_RESPONSE,
                    data={"request_id": req_id, "granted": granted},
                    source="moto_g04",
                    priority=EventPriority.REALTIME,
                )
            )

    async def _broadcast_event(self, event: Event) -> None:
        """Push events to connected Moto g04 WebSocket client using Protocol v1."""
        if not self._active_sockets:
            return

        payload = {
            "event_type": str(event.type),
            "source": event.source,
            "priority": event.priority.name,
            "data": event.data,
        }

        for ws in list(self._active_sockets):
            if not ws.closed:
                try:
                    await self._send_v1_msg(ws, msg_type="event", payload=payload)
                except Exception as e:
                    logger.debug(f"Error broadcasting event to WS: {e}")

    async def _index_handler(self, request: web.Request) -> web.FileResponse | web.Response:
        """Serve Moto g04 Web Companion HTML."""
        index_path = self._project_root / "web" / "companion" / "index.html"
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text="Companion App index.html not found", status=404)

    async def _status_handler(self, request: web.Request) -> web.Response:
        """Public status endpoint."""
        assert self.api is not None
        tools_count = len(self.api.list_tools())
        plugins_count = len(self.api.plugin_registry.list_plugins())

        return web.json_response(
            {
                "protocol": PROTOCOL_VERSION,
                "status": "online",
                "system": "J.A.R.V.I.S.",
                "authorized_device": "Moto g04 de Rodrigo",
                "priority_level": "REALTIME",
                "plugins_count": plugins_count,
                "tools_count": tools_count,
            }
        )

    async def _telemetry_handler(self, request: web.Request) -> web.Response:
        """Get live system & device telemetry for the Moto g04 dashboard."""
        assert self.api is not None
        state = await self.api.snapshot_state()

        return web.json_response(
            {
                "protocol": PROTOCOL_VERSION,
                "pc_state": {
                    "cpu_temp": state.get("system.cpu_temp", 0),
                    "night_mode": state.get("system.night_mode", False),
                    "headphones": state.get("audio.headphones", False),
                    "volume": state.get("audio.volume", 70),
                },
                "moto_g04_state": {
                    "battery": state.get("user.device.battery", "N/A"),
                    "charging": state.get("user.device.charging", False),
                    "last_seen": state.get("user.device.last_seen"),
                },
            }
        )
