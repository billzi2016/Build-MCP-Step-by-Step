from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from runtime.mcp_client import StdioMCPClient
from runtime.ollama_client import OllamaClient, OllamaError


@dataclass
class RuntimeState:
    goal: str
    step: int = 0
    jd_text: str = ""
    candidate_text: str = ""
    requirements: list[str] = field(default_factory=list)
    fit_matrix: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


class AgentRuntime:
    def __init__(
        self,
        *,
        mcp_client: StdioMCPClient,
        ollama_client: OllamaClient | None = None,
        max_steps: int = 8,
    ) -> None:
        self.mcp = mcp_client
        self.ollama = ollama_client
        self.max_steps = max_steps

    def run_hr_case(self) -> dict[str, Any]:
        state = RuntimeState(
            goal="Generate a structured candidate-to-JD fit analysis grounded in explicit evidence."
        )

        while state.step < self.max_steps:
            state.step += 1
            action = self._decide_next_action(state)
            self._apply_action(state, action)
            if action["action"] == "final_answer":
                return {
                    "trace": state.trace,
                    "result": action["result"],
                }

        raise RuntimeError("Agent runtime hit max steps before producing a final answer.")

    def _decide_next_action(self, state: RuntimeState) -> dict[str, Any]:
        fallback = self._fallback_action(state)
        if not self.ollama:
            return fallback

        # 模型在这里扮演“规划器”，只负责给出下一步意图；
        # 真正执行动作、读资源、改状态的仍然是 runtime。
        resources = [item["uri"] for item in self.mcp.list_resources()]
        tools = [item["name"] for item in self.mcp.list_tools()]
        planner_messages = [
            {
                "role": "system",
                "content": (
                    "You are the planning loop of an agent runtime. "
                    "Return strict JSON only. "
                    "Allowed actions: read_resource, call_tool, final_answer. "
                    "Do not invent tools or resources."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": state.goal,
                        "step": state.step,
                        "known_state": {
                            "has_jd": bool(state.jd_text),
                            "has_candidate": bool(state.candidate_text),
                            "has_requirements": bool(state.requirements),
                            "has_fit_matrix": bool(state.fit_matrix),
                        },
                        "available_resources": resources,
                        "available_tools": tools,
                        "fallback_plan_if_unsure": fallback,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            content = self.ollama.chat(planner_messages, format_json=True, temperature=0.0)
            parsed = json.loads(content)
            if self._is_valid_action(parsed):
                return parsed
        except (OllamaError, json.JSONDecodeError, RuntimeError):
            return fallback
        return fallback

    def _is_valid_action(self, action: Any) -> bool:
        if not isinstance(action, dict):
            return False
        kind = action.get("action")
        if kind == "read_resource":
            return isinstance(action.get("uri"), str) and bool(action["uri"])
        if kind == "call_tool":
            return isinstance(action.get("name"), str) and bool(action["name"])
        if kind == "final_answer":
            return True
        return False

    def _fallback_action(self, state: RuntimeState) -> dict[str, Any]:
        # 如果本地模型不可用，或者规划输出坏掉，runtime 仍然按确定性顺序把最小闭环跑通，
        # 这样 demo 至少能验证 server、resource、tool 和状态推进这条链。
        if not state.jd_text:
            return {"action": "read_resource", "uri": "project://case/jd_sample"}
        if not state.candidate_text:
            return {"action": "read_resource", "uri": "project://case/candidate_profile"}
        if not state.requirements:
            return {
                "action": "call_tool",
                "name": "extract_key_requirements",
                "arguments": {"text": state.jd_text, "focus": "hiring_requirements"},
            }
        if not state.fit_matrix:
            return {
                "action": "call_tool",
                "name": "score_candidate_fit",
                "arguments": {
                    "requirements": state.requirements,
                    "candidate_profile": state.candidate_text,
                },
            }
        return {"action": "final_answer"}

    def _apply_action(self, state: RuntimeState, action: dict[str, Any]) -> None:
        kind = action["action"]
        if kind == "read_resource":
            resource = self.mcp.read_resource(action["uri"])
            if action["uri"] == "project://case/jd_sample":
                state.jd_text = resource["text"]
            elif action["uri"] == "project://case/candidate_profile":
                state.candidate_text = resource["text"]
            state.trace.append(
                {
                    "step": state.step,
                    "action": kind,
                    "target": action["uri"],
                    "note": "Loaded resource into runtime state.",
                }
            )
            return

        if kind == "call_tool":
            result = self.mcp.call_tool(action["name"], action.get("arguments", {}))
            content = result["content"]
            if action["name"] == "extract_key_requirements":
                state.requirements = content["requirements"]
            elif action["name"] == "score_candidate_fit":
                state.fit_matrix = content
            state.trace.append(
                {
                    "step": state.step,
                    "action": kind,
                    "target": action["name"],
                    "note": "Executed tool and updated runtime state.",
                    "content": content,
                }
            )
            return

        if kind == "final_answer":
            result = self._synthesize_final_answer(state)
            state.trace.append(
                {
                    "step": state.step,
                    "action": kind,
                    "target": "map_candidate_to_jd",
                    "note": "Produced final structured hiring artifact.",
                }
            )
            action["result"] = result
            return

        raise RuntimeError(f"Unsupported action: {kind}")

    def _synthesize_final_answer(self, state: RuntimeState) -> dict[str, Any]:
        prompt = self.mcp.get_prompt(
            "map_candidate_to_jd",
            {
                "job_requirements": "\n".join(f"- {item}" for item in state.requirements),
                "candidate_profile": state.candidate_text,
                "fit_matrix": json.dumps(state.fit_matrix, ensure_ascii=False, indent=2),
            },
        )
        fallback = self._fallback_final_answer(state)
        if not self.ollama:
            return fallback

        try:
            # 到这一步才让模型生成最终招聘产物。
            # 前面的 resource 读取和 tool 调用，本质上都在为这里准备更干净的证据输入。
            content = self.ollama.chat(
                [
                    {"role": "system", "content": prompt["system"]},
                    {"role": "user", "content": prompt["user"]},
                ],
                format_json=True,
                temperature=0.0,
            )
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except (OllamaError, json.JSONDecodeError):
            return fallback
        return fallback

    def _fallback_final_answer(self, state: RuntimeState) -> dict[str, Any]:
        fit = state.fit_matrix or {"overall_fit": "Moderate", "dimensions": [], "risks": []}
        return {
            "overall_fit": fit["overall_fit"],
            "dimensions": fit["dimensions"],
            "risks": fit["risks"],
            "interview_followups": [
                "Describe a concrete multi-step agent runtime you designed and how state was maintained.",
                "Explain how you would expose tools, resources, and prompts through an MCP-compatible capability layer.",
            ],
        }
