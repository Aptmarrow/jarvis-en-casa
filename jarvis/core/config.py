from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

class CoreConfig(BaseModel):
    data_dir: str = "data"
    plugins_dir: str | None = None

class TransportCliConfig(BaseModel):
    enabled: bool = True
    prompt: str = "jarvis"
    history_file: str = "data/cli_history"

class TransportWebsocketConfig(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8765
    tls: bool = False
    cert_file: str | None = None
    key_file: str | None = None

class TransportWebConsoleConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080

class TransportConfig(BaseModel):
    cli: TransportCliConfig = Field(default_factory=TransportCliConfig)
    websocket: TransportWebsocketConfig = Field(default_factory=TransportWebsocketConfig)
    web_console: TransportWebConsoleConfig = Field(default_factory=TransportWebConsoleConfig)

class RateLimitConfig(BaseModel):
    requests_per_minute: int = 15
    tokens_per_minute: int = 1000000

class AIConfig(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    temperature: float = 0.7
    max_tokens: int = 4096
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

class VoiceConfidenceThresholds(BaseModel):
    high: float = 0.85
    medium: float = 0.60
    low: float = 0.40

class VoiceConfig(BaseModel):
    enabled: bool = False
    wake_word: str = "jarvis"
    stt_model: str = "small"
    tts_voice: str = "es-AR-TomasNeural"
    confidence_thresholds: VoiceConfidenceThresholds = Field(default_factory=VoiceConfidenceThresholds)

class SchedulerConfig(BaseModel):
    enabled: bool = True
    config_file: str = "config/schedules.yaml"

class RuntimeConfig(BaseModel):
    pid_file: str = "/tmp/jarvis.pid"
    log_level: str = "INFO"
    log_file: str | None = None
    watchdog_interval: int = 30

class JarvisConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = "Jarvis"
    version: str = "0.1.0"
    language: str = "es"

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    core: CoreConfig = Field(default_factory=CoreConfig)
    transport: TransportConfig = Field(default_factory=TransportConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    _project_root: Path | None = None

    @classmethod
    def load(cls, config_path: str | Path) -> JarvisConfig:
        path = Path(config_path)
        project_root = path.parent.parent if path.parent.name == "config" else path.parent
        
        load_dotenv(project_root / ".env")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load config file {path}: {e}. Using defaults.")
            data = {}

        if "jarvis" in data:
            for k, v in data["jarvis"].items():
                data[k] = v
            del data["jarvis"]

        config = cls(**data)
        config._project_root = project_root
        return config

    def get(self, section: str, key: str) -> Any:
        try:
            section_obj = getattr(self, section)
            return getattr(section_obj, key)
        except AttributeError:
            raise KeyError(f"Key {section}.{key} not found in config")
