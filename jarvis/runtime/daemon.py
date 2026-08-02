from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from rich.console import Console

from jarvis.runtime.lifecycle import Lifecycle

logger = logging.getLogger(__name__)

BANNER = r"""
       _     _    _____  __      __ _____  _____ 
      | |   / \  |  __ \ \ \    / /|_   _|/ ____|
      | |  /  \  | |__) | \ \  / /   | | | (___  
  _   | | / /\ \ |  _  /   \ \/ /    | |  \___ \ 
 | |__| |/ ____ \| | \ \    \  /    _| |_ ____) |
  \____//_/    \_\_|  \_\    \/    |_____|_____/ 
"""

class JarvisDaemon:
    """Main daemon process for J.A.R.V.I.S."""

    def __init__(self) -> None:
        self.lifecycle = Lifecycle()
        self.shutdown_event = asyncio.Event()

    def _signal_handler(self) -> None:
        logger.info("Received shutdown signal. Stopping daemon...")
        self.shutdown_event.set()

    def _get_pid_file(self) -> str:
        # Default pid file location
        pid_file = "/tmp/jarvis.pid"
        try:
            if hasattr(self.lifecycle, "config") and self.lifecycle.config:
                config = self.lifecycle.config
                if isinstance(config, dict):
                    pid_file = config.get("runtime", {}).get("pid_file", pid_file)
                elif hasattr(config, "get"):
                    pid_file = config.get("runtime", {}).get("pid_file", pid_file)
        except Exception as e:
            logger.debug(f"Could not read pid_file from config, using default: {e}")
        return pid_file

    async def run(self) -> None:
        """Main entry point for the daemon."""
        Console().print(f"[bold cyan]{BANNER}[/bold cyan]")
        logger.info("Starting J.A.R.V.I.S. daemon...")
        
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        pid_file: str | None = None

        try:
            # Create Lifecycle instance and call startup
            await self.lifecycle.startup()
            
            pid_file = self._get_pid_file()
            
            # Write PID file
            try:
                Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
                Path(pid_file).write_text(str(os.getpid()))
            except Exception as e:
                logger.warning(f"Could not write PID file to {pid_file}: {e}")

            logger.info("Daemon is now running. Waiting for events...")
            
            # Enter main loop (wait for shutdown signal)
            await self.shutdown_event.wait()
        
        except Exception as e:
            logger.exception(f"Fatal error in daemon: {e}")
        finally:
            logger.info("Initiating shutdown sequence...")
            await self.lifecycle.shutdown()
            
            if pid_file:
                try:
                    Path(pid_file).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not remove PID file {pid_file}: {e}")
