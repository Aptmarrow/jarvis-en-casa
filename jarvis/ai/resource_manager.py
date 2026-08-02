from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AIResourceManager:
    """Manages AI rate limits and resource usage."""
    
    def __init__(self, config: Any = None) -> None:
        if config is None:
            self.rpm_limit = 15
            self.tpm_limit = 1000000
        elif hasattr(config, "requests_per_minute"):
            self.rpm_limit = getattr(config, "requests_per_minute", 15)
            self.tpm_limit = getattr(config, "tokens_per_minute", 1000000)
        elif isinstance(config, dict):
            rate_limit_config = config.get("rate_limit", config)
            self.rpm_limit = rate_limit_config.get("requests_per_minute", 15)
            self.tpm_limit = rate_limit_config.get("tokens_per_minute", 1000000)
        else:
            self.rpm_limit = 15
            self.tpm_limit = 1000000
        
        self._request_timestamps: list[float] = []
        self._token_usage: list[tuple[float, int]] = []
        self._lock = asyncio.Lock()
        
    async def acquire_slot(self) -> bool:
        """
        Checks rate limit, waits if necessary or returns False if exceeded.
        """
        async with self._lock:
            now = time.time()
            one_minute_ago = now - 60.0
            
            # Clean up old data
            self._request_timestamps = [ts for ts in self._request_timestamps if ts > one_minute_ago]
            self._token_usage = [(ts, tokens) for ts, tokens in self._token_usage if ts > one_minute_ago]
            
            if len(self._request_timestamps) >= self.rpm_limit:
                wait_time = 60.0 - (now - self._request_timestamps[0])
                if wait_time > 0 and wait_time < 30.0:  # Only wait if it's reasonable
                    logger.warning(f"Rate limit approaching. Waiting {wait_time:.2f}s.")
                else:
                    return False

            current_tokens = sum(tokens for _, tokens in self._token_usage)
            if current_tokens >= self.tpm_limit:
                return False

        if 'wait_time' in locals() and wait_time > 0 and wait_time < 30.0:
            await asyncio.sleep(wait_time)
            
        async with self._lock:
            self._request_timestamps.append(time.time())
            return True
            
    def report_usage(self, tokens_used: int) -> None:
        """Updates usage counters."""
        now = time.time()
        self._token_usage.append((now, tokens_used))
