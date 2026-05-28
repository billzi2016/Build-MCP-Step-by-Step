from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Callable

# 允许 server 作为独立脚本被 runtime 子进程拉起。
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.capabilities import (
    call_tool,
    get_prompt,
    list_prompts,
    list_resources,
    list_tools,
    read_resource,
)


Handler = Callable[[dict[str, Any]], Any]


def handle_initialize(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol": "minimal-mcp-0.1",
        "capabilities": {
            "tools": True,
            "resources": True,
            "prompts": True,
        },
    }


def handle_tools_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"tools": list_tools()}


def handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params["name"]
    arguments = params.get("arguments", {})
    return {"name": name, "content": call_tool(name, arguments)}


def handle_resources_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"resources": list_resources()}


def handle_resources_read(params: dict[str, Any]) -> dict[str, Any]:
    return read_resource(params["uri"])


def handle_prompts_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"prompts": list_prompts()}


def handle_prompts_get(params: dict[str, Any]) -> dict[str, Any]:
    return get_prompt(params["name"], params.get("arguments"))


HANDLERS: dict[str, Handler] = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "resources/list": handle_resources_list,
    "resources/read": handle_resources_read,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
}


def _write_message(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve() -> None:
    # 这是一个最小化的 stdio JSON-RPC 循环。
    # 它不是完整 MCP SDK，但保留了最关键的边界：
    # 能力发现、resource 读取、prompt 获取和 tool 调用都通过 server 这层发生。
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        request = json.loads(line)
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method not in HANDLERS:
                raise KeyError(f"Unknown method: {method}")
            result = HANDLERS[method](params)
            _write_message({"id": request_id, "result": result})
        except Exception as exc:  # noqa: BLE001
            _write_message(
                {
                    "id": request_id,
                    "error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                }
            )


if __name__ == "__main__":
    serve()
