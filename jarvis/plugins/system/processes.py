from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class ProcessesPlugin(Plugin):
    name = "system.processes"
    description = "Manage system processes."
    version = "0.1.0"

    @tool(
        description="List running processes",
        permissions=["system.processes.list"],
        parameters=[
            ToolParameter(name="sort_by", type="string", description="Sort by 'cpu' or 'memory'", default="cpu"),
            ToolParameter(name="limit", type="integer", description="Max number of processes to return", default=10),
        ]
    )
    async def list_processes(self, sort_by: str = "cpu", limit: int = 10) -> dict:
        sort_flag = "-pcpu" if sort_by == "cpu" else "-pmem"
        proc = await asyncio.create_subprocess_exec(
            "ps", "aux", "--sort", sort_flag,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split('\n')
        
        processes = []
        for line in lines[1:]:
            if not line:
                continue
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "user": parts[0],
                    "pid": int(parts[1]),
                    "cpu": float(parts[2]),
                    "memory": float(parts[3]),
                    "name": parts[10]
                })
        
        return {"processes": processes[:limit]}

    @tool(
        description="Kill a process by PID",
        permissions=["system.processes.kill"],
        parameters=[
            ToolParameter(name="pid", type="integer", description="Process ID to kill"),
            ToolParameter(name="signal", type="string", description="Signal to send (e.g. TERM, KILL)", default="TERM"),
        ]
    )
    async def kill_process(self, pid: int, signal: str = "TERM") -> dict:
        proc = await asyncio.create_subprocess_exec(
            "kill", f"-{signal}", str(pid)
        )
        await proc.wait()
        return {"killed": proc.returncode == 0, "pid": pid}

    @tool(
        description="Find a process by name",
        permissions=["system.processes.list"],
        parameters=[
            ToolParameter(name="name", type="string", description="Process name to search for"),
        ]
    )
    async def find_process(self, name: str) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-a", name,
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split('\n')
        
        matches = []
        for line in lines:
            if line:
                parts = line.split(None, 1)
                matches.append({
                    "pid": int(parts[0]),
                    "name": parts[1] if len(parts) > 1 else ""
                })
                
        return {"matches": matches}

    @tool(
        description="Restart the J.A.R.V.I.S. system daemon 100% cleanly",
        permissions=["system.processes.restart"],
        parameters=[]
    )
    async def restart_jarvis(self) -> dict:
        import os
        import sys
        logger.info("⚡ Restarting J.A.R.V.I.S. process...")
        asyncio.get_event_loop().call_later(0.5, lambda: os.execv(sys.executable, [sys.executable, "-m", "jarvis"]))
        return {"status": "restarting", "message": "J.A.R.V.I.S. se está reiniciando..."}
