from __future__ import annotations

import asyncio
from typing import Any

from jarvis.plugins.base import Plugin, tool
from jarvis.core.types import ToolParameter

class PrinterPlugin(Plugin):
    name = "system.printer"
    description = "CUPS printer management and document printing"

    @tool("List CUPS printers")
    async def list_printers(self) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "lpstat", "-p", "-d",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return {"error": "Failed to list printers"}
            
            lines = stdout.decode("utf-8").strip().split('\n')
            printers = []
            default = None
            
            for line in lines:
                if line.startswith("system default destination:"):
                    default = line.split(":")[-1].strip()
                elif line.startswith("printer"):
                    parts = line.split(" ")
                    if len(parts) >= 2:
                        name = parts[1]
                        status = " ".join(parts[2:]) if len(parts) > 2 else ""
                        printers.append({
                            "name": name,
                            "status": status
                        })
            
            for p in printers:
                p["default"] = (p["name"] == default)
                
            return {"printers": printers}
        except FileNotFoundError:
            return {"error": "lpstat command not found. Is CUPS installed?"}

    @tool("Print a file", parameters=[
        ToolParameter(name="file_path", type="string", description="Path to the file to print"),
        ToolParameter(name="printer_name", type="string", description="Optional specific printer to use", required=False)
    ])
    async def print_file(self, file_path: str, printer_name: str | None = None) -> dict[str, Any]:
        try:
            args = []
            if printer_name:
                args.extend(["-d", printer_name])
            args.append(file_path)
            
            proc = await asyncio.create_subprocess_exec(
                "lp", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return {"status": "success", "message": stdout.decode("utf-8").strip()}
            return {"error": "Failed to print file"}
        except FileNotFoundError:
            return {"error": "lp command not found. Is CUPS installed?"}
