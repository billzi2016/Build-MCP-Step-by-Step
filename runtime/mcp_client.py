from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class MCPClientError(RuntimeError):
    pass


class StdioMCPClient:
    def __init__(self, server_path: Path | None = None) -> None:
        self.server_path = server_path or ROOT / "server" / "mcp_server.py"
        self._request_id = 0
        # 这里用最简单的 stdio 传输把 server 拉起来，
        # 目的是把“能力层”和“runtime”保留成两个真实边界，而不是全塞进一个脚本。
        self.proc = subprocess.Popen(
            [sys.executable, str(self.server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(ROOT),
        )
        self.request("initialize", {})

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        if self.proc.stdout:
            self.proc.stdout.close()
        self.proc.terminate()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        payload = {
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        if not self.proc.stdin or not self.proc.stdout:
            raise MCPClientError("MCP process is not available.")

        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

        response_line = self.proc.stdout.readline()
        if not response_line:
            stderr = ""
            if self.proc.stderr:
                stderr = self.proc.stderr.read()
            raise MCPClientError(f"No response from MCP server. stderr={stderr}")

        response = json.loads(response_line)
        if "error" in response:
            raise MCPClientError(response["error"]["message"])
        return response["result"]

    def list_tools(self) -> list[dict[str, Any]]:
        return self.request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def list_resources(self) -> list[dict[str, Any]]:
        return self.request("resources/list")["resources"]

    def read_resource(self, uri: str) -> dict[str, Any]:
        return self.request("resources/read", {"uri": uri})

    def list_prompts(self) -> list[dict[str, Any]]:
        return self.request("prompts/list")["prompts"]

    def get_prompt(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("prompts/get", {"name": name, "arguments": arguments})
