from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


RESOURCE_PATHS = {
    "project://prd/main": ROOT / "PRD.md",
    "project://case/jd_sample": EXAMPLES_DIR / "jd_sample.md",
    "project://case/candidate_profile": EXAMPLES_DIR / "candidate_profile.md",
}


RESOURCE_DESCRIPTIONS = {
    "project://prd/main": "Current project PRD for overall scope, structure, and delivery goals.",
    "project://case/jd_sample": "Sample job description used by the HR-facing case study.",
    "project://case/candidate_profile": "Sample candidate profile used by the HR-facing case study.",
}


PROMPT_TEMPLATES = {
    "map_candidate_to_jd": {
        "description": "Generate a structured candidate-to-JD fit analysis grounded in explicit evidence.",
        "arguments": ["job_requirements", "candidate_profile", "fit_matrix"],
        "system": (
            "You are producing a hiring artifact, not a generic summary. "
            "Every judgment must be grounded in provided evidence. "
            "Return concise JSON with keys overall_fit, dimensions, risks, interview_followups."
        ),
        "user_template": (
            "Job requirements:\n{job_requirements}\n\n"
            "Candidate profile:\n{candidate_profile}\n\n"
            "Fit matrix:\n{fit_matrix}\n\n"
            "Produce a structured hiring assessment."
        ),
    },
    "analyze_project_brief": {
        "description": "Turn a project brief into a structured analysis of goals, constraints, and implementation direction.",
        "arguments": ["project_brief"],
        "system": (
            "You are analyzing a project brief for execution planning. "
            "Stay concrete and identify goal, constraints, risks, and next actions."
        ),
        "user_template": "Project brief:\n{project_brief}",
    },
}


STOPWORDS = {
    "and",
    "with",
    "for",
    "that",
    "this",
    "from",
    "have",
    "will",
    "into",
    "your",
    "about",
    "their",
    "they",
    "them",
    "using",
    "build",
    "built",
    "ability",
    "experience",
    "strong",
    "should",
    "must",
}


KEYWORD_RULES = {
    "llm_systems": ["llm", "large language", "prompt", "system prompt", "tool use", "tool calling"],
    "agent_runtime": ["agent", "runtime", "loop", "state", "multi-step", "planning"],
    "mcp": ["mcp", "model context protocol", "resource", "tool", "prompt template"],
    "python_engineering": ["python", "api", "backend", "cli", "automation"],
}


def list_resources() -> list[dict[str, Any]]:
    # 这里故意把资源暴露成稳定 URI，而不是直接把本地路径泄漏给 runtime。
    # 这样后面无论是换存储位置还是扩展更多资源，消费侧看到的仍然是能力对象。
    return [
        {
            "uri": uri,
            "name": path.name,
            "description": RESOURCE_DESCRIPTIONS[uri],
            "mimeType": "text/markdown",
        }
        for uri, path in RESOURCE_PATHS.items()
    ]


def read_resource(uri: str) -> dict[str, Any]:
    if uri not in RESOURCE_PATHS:
        raise KeyError(f"Unknown resource: {uri}")
    path = RESOURCE_PATHS[uri]
    return {
        "uri": uri,
        "mimeType": "text/markdown",
        "text": _read_text(path),
    }


def list_prompts() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": meta["description"],
            "arguments": meta["arguments"],
        }
        for name, meta in PROMPT_TEMPLATES.items()
    ]


def get_prompt(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in PROMPT_TEMPLATES:
        raise KeyError(f"Unknown prompt: {name}")
    meta = PROMPT_TEMPLATES[name]
    arguments = arguments or {}
    missing = [arg for arg in meta["arguments"] if arg not in arguments]
    if missing:
        raise ValueError(f"Missing prompt arguments: {', '.join(missing)}")
    return {
        "name": name,
        "description": meta["description"],
        "system": meta["system"],
        "user": meta["user_template"].format(**arguments),
    }


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "extract_key_requirements",
            "description": (
                "Extract structured hiring or project requirements from a longer document. "
                "Use this when the runtime needs dimensions or requirements instead of raw prose."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "focus": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "score_candidate_fit",
            "description": (
                "Map candidate evidence to a set of requirements and produce a structured fit matrix."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "requirements": {"type": "array"},
                    "candidate_profile": {"type": "string"},
                },
                "required": ["requirements", "candidate_profile"],
            },
        },
        {
            "name": "summarize_section",
            "description": "Compress a longer text section into a concise summary for downstream reasoning.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "max_sentences": {"type": "integer"},
                },
                "required": ["text"],
            },
        },
    ]


def _split_lines(text: str) -> list[str]:
    return [line.strip("- ").strip() for line in text.splitlines() if line.strip()]


def _keyword_bag(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9\-\+]*", text.lower()))
    return {token for token in tokens if token not in STOPWORDS and len(token) > 2}


def extract_key_requirements(text: str, focus: str = "requirements") -> dict[str, Any]:
    # 这个工具保持确定性输出。模型已经在 runtime 里承担推理角色，
    # 工具层更适合提供可检查、可复现的中间结构，而不是再引入一层模糊生成。
    lines = _split_lines(text)
    candidate_lines = []
    for line in lines:
        lowered = line.lower()
        if any(marker in lowered for marker in ["must", "should", "experience", "build", "agent", "mcp", "llm"]):
            candidate_lines.append(line)
    if not candidate_lines:
        candidate_lines = lines[:6]

    requirements: list[str] = []
    seen = set()
    for line in candidate_lines:
        normalized = re.sub(r"\s+", " ", line)
        if normalized not in seen:
            requirements.append(normalized)
            seen.add(normalized)
        if len(requirements) >= 6:
            break

    ambiguities = [
        req for req in requirements if len(_keyword_bag(req)) < 4 or "etc" in req.lower() or "plus" in req.lower()
    ]
    return {
        "focus": focus,
        "requirements": requirements,
        "signals": candidate_lines[:6],
        "ambiguities": ambiguities,
    }


def _score_requirement(requirement: str, profile: str) -> dict[str, Any]:
    req_lower = requirement.lower()
    profile_lower = profile.lower()
    hits = []

    for family, keywords in KEYWORD_RULES.items():
        if any(keyword in req_lower for keyword in keywords):
            family_hits = [keyword for keyword in keywords if keyword in profile_lower]
            if family_hits:
                hits.extend(family_hits)

    req_tokens = _keyword_bag(requirement)
    profile_tokens = _keyword_bag(profile)
    overlap = sorted(req_tokens & profile_tokens)
    hits.extend(overlap[:6])

    unique_hits = []
    seen = set()
    for hit in hits:
        if hit not in seen:
            unique_hits.append(hit)
            seen.add(hit)

    score = min(5, max(1, len(unique_hits)))
    if not unique_hits:
        score = 1

    return {
        "requirement": requirement,
        "score": score,
        "evidence": unique_hits[:5],
        "gap": None if score >= 3 else "Candidate evidence is weak or indirect for this requirement.",
    }


def score_candidate_fit(requirements: list[str], candidate_profile: str) -> dict[str, Any]:
    # 这里不追求“神奇的招聘评分”，而是生成一个可解释的中间 fit matrix，
    # 让 runtime 和最终综合输出都有明确证据可依。
    dimension_scores = [_score_requirement(req, candidate_profile) for req in requirements]
    avg_score = sum(item["score"] for item in dimension_scores) / max(1, len(dimension_scores))
    if avg_score >= 4:
        overall = "Strong"
    elif avg_score >= 2.5:
        overall = "Moderate"
    else:
        overall = "Weak"

    risks = [item["requirement"] for item in dimension_scores if item["gap"]]
    return {
        "overall_fit": overall,
        "dimensions": dimension_scores,
        "risks": risks,
    }


def summarize_section(text: str, max_sentences: int = 3) -> dict[str, Any]:
    sentences = [chunk.strip() for chunk in re.split(r"(?<=[.!?])\s+", text.strip()) if chunk.strip()]
    if not sentences:
        sentences = _split_lines(text)
    summary = " ".join(sentences[:max(1, max_sentences)])
    return {"summary": summary}


TOOL_HANDLERS = {
    "extract_key_requirements": extract_key_requirements,
    "score_candidate_fit": score_candidate_fit,
    "summarize_section": summarize_section,
}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_HANDLERS:
        raise KeyError(f"Unknown tool: {name}")
    return TOOL_HANDLERS[name](**arguments)
