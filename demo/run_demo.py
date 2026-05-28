from __future__ import annotations

import json
from pathlib import Path
import sys

# 允许直接用 `python demo/run_demo.py` 运行，而不需要先安装成包。
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.agent_runtime import AgentRuntime
from runtime.mcp_client import StdioMCPClient
from runtime.ollama_client import OllamaClient


def main() -> None:
    mcp = StdioMCPClient()
    try:
        runtime = AgentRuntime(
            mcp_client=mcp,
            ollama_client=OllamaClient(),
        )
        result = runtime.run_hr_case()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
