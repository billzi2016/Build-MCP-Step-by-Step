from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "gpt-oss:120b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        format_json: bool = False,
        temperature: float = 0.1,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format_json:
            payload["format"] = "json"

        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise OllamaError(f"Failed to reach Ollama at {self.base_url}: {exc}") from exc

        try:
            return data["message"]["content"]
        except KeyError as exc:
            raise OllamaError(f"Unexpected Ollama response: {data}") from exc
