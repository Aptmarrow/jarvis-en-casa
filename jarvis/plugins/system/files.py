from __future__ import annotations

import asyncio
import logging
import os
import stat
from typing import TYPE_CHECKING

from jarvis.core.types import ToolParameter
from jarvis.plugins.base import Plugin, tool

if TYPE_CHECKING:
    from jarvis.core.api import JarvisAPI

logger = logging.getLogger(__name__)

class FilesPlugin(Plugin):
    name = "system.files"
    description = "File system operations."
    version = "0.1.0"

    @tool(
        description="List directory contents",
        permissions=["filesystem.read"],
        parameters=[
            ToolParameter(name="path", type="string", description="Directory path", default="."),
            ToolParameter(name="show_hidden", type="boolean", description="Show hidden files", default=False),
        ]
    )
    async def list_files(self, path: str = ".", show_hidden: bool = False) -> dict:
        try:
            entries = os.listdir(path)
            files = []
            for entry in entries:
                if not show_hidden and entry.startswith("."):
                    continue
                full_path = os.path.join(path, entry)
                try:
                    st = os.stat(full_path)
                    files.append({
                        "name": entry,
                        "size": st.st_size,
                        "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
                        "modified": st.st_mtime
                    })
                except OSError:
                    pass
            return {"path": path, "files": files}
        except OSError as e:
            return {"error": str(e)}

    @tool(
        description="Get file information",
        permissions=["filesystem.read"],
        parameters=[
            ToolParameter(name="path", type="string", description="File path"),
        ]
    )
    async def file_info(self, path: str) -> dict:
        try:
            st = os.stat(path)
            import pwd
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except KeyError:
                owner = str(st.st_uid)
                
            return {
                "name": os.path.basename(path),
                "size": st.st_size,
                "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
                "permissions": oct(stat.S_IMODE(st.st_mode)),
                "owner": owner,
                "modified": st.st_mtime
            }
        except OSError as e:
            return {"error": str(e)}

    @tool(
        description="Search for files",
        permissions=["filesystem.read"],
        parameters=[
            ToolParameter(name="query", type="string", description="File name pattern to search for"),
            ToolParameter(name="path", type="string", description="Base directory to search in", default="."),
            ToolParameter(name="max_results", type="integer", description="Maximum number of results", default=20),
        ]
    )
    async def search_files(self, query: str, path: str = ".", max_results: int = 20) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "find", path, "-iname", f"*{query}*",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split('\n')
        
        matches = [line for line in lines if line]
        return {"matches": matches[:max_results]}

    @tool(
        description="Open a file or URL with the default application",
        permissions=["filesystem.execute"],
        parameters=[
            ToolParameter(name="path", type="string", description="File path or URL to open"),
        ]
    )
    async def open_file(self, path: str) -> dict:
        proc = await asyncio.create_subprocess_exec(
            "xdg-open", path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        # xdg-open forks and returns quickly, so we can wait
        await proc.wait()
        return {"opened": path}
