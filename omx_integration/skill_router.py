"""
Skill router for OMX keyword detection and skill activation.

Implements the AGENTS.md keyword_detection contract:
- Case-insensitive keyword matching
- Explicit $name invocations override non-explicit matches
- Most specific match wins for non-explicit keywords
- Runtime-only keywords gated by environment check
"""

import re
from typing import Optional, Callable


# Skill definitions matching the AGENTS.md keyword_detection table
SKILL_DEFINITIONS = {
    "deep-interview": {
        "keywords": [
            "interview", "deep interview", "gather requirements",
            "interview me", "don't assume", "ouroboros",
        ],
        "description": "Socratic deep interview workflow — clarifies intent and boundaries.",
        "runtime_only": False,
    },
    "ralplan": {
        "keywords": ["ralplan", "consensus plan"],
        "description": "Consensus planning with RALPLAN-DR structured deliberation.",
        "runtime_only": False,
    },
    "ralph": {
        "keywords": ["ralph", "don't stop", "must complete", "keep going"],
        "description": "Persistent completion and verification loop.",
        "runtime_only": True,
    },
    "autopilot": {
        "keywords": ["autopilot", "build me", "I want a"],
        "description": "Full autonomous pipeline: requirements -> design -> implementation -> QA.",
        "runtime_only": True,
    },
    "ultrawork": {
        "keywords": ["ultrawork", "ulw", "parallel"],
        "description": "Parallel agent execution for throughput.",
        "runtime_only": True,
    },
    "team": {
        "keywords": ["team", "swarm", "coordinated team", "coordinated swarm"],
        "description": "Tmux/worktree-based team orchestration with durable state.",
        "runtime_only": True,
    },
    "ecomode": {
        "keywords": ["ecomode", "eco", "budget"],
        "description": "Cost-aware parallel workflow.",
        "runtime_only": True,
    },
    "plan": {
        "keywords": ["plan this", "plan the", "let's plan"],
        "description": "Start planning workflow.",
        "runtime_only": False,
    },
    "analyze": {
        "keywords": ["analyze", "investigate"],
        "description": "Root-cause analysis and debugging.",
        "runtime_only": False,
    },
    "cancel": {
        "keywords": ["cancel", "stop", "abort"],
        "description": "Cancel active modes.",
        "runtime_only": False,
    },
    "tdd": {
        "keywords": ["tdd", "test first"],
        "description": "Test-first development workflow.",
        "runtime_only": False,
    },
    "build-fix": {
        "keywords": ["fix build", "type errors"],
        "description": "Fix build errors with minimal diff.",
        "runtime_only": False,
    },
    "code-review": {
        "keywords": ["review code", "code review", "code-review"],
        "description": "Code review workflow.",
        "runtime_only": False,
    },
    "security-review": {
        "keywords": ["security review"],
        "description": "Security audit workflow.",
        "runtime_only": False,
    },
    "web-clone": {
        "keywords": ["web-clone", "clone site", "clone website", "copy webpage"],
        "description": "Website cloning pipeline.",
        "runtime_only": False,
    },
}


class SkillRouter:
    """
    Routes user messages to the appropriate OMX skill based on keyword detection.

    Usage:
        router = SkillRouter()
        match = router.route("let's plan the authentication module")
        if match:
            print(f"Skill: {match['skill']}, Task: {match['task']}")
    """

    def __init__(self, omx_runtime: bool = False):
        """
        Args:
            omx_runtime: Whether running inside OMX CLI/runtime.
                Runtime-only skills are gated by this flag.
        """
        self.omx_runtime = omx_runtime
        self._handlers: dict[str, Callable] = {}

    def register_handler(self, skill_name: str, handler: Callable):
        """Register a handler function for a skill."""
        self._handlers[skill_name] = handler

    def route(self, message: str) -> Optional[dict]:
        """
        Route a user message to the matching skill.

        Returns dict with 'skill', 'description', 'task', 'handler' or None.
        """
        # Check for explicit $name invocations first (left-to-right)
        explicit_match = re.search(r'\$(\w[\w-]*)', message)
        if explicit_match:
            skill_name = explicit_match.group(1)
            if skill_name in SKILL_DEFINITIONS:
                defn = SKILL_DEFINITIONS[skill_name]
                if defn["runtime_only"] and not self.omx_runtime:
                    return {
                        "skill": skill_name,
                        "description": defn["description"],
                        "task": message,
                        "handler": None,
                        "blocked": True,
                        "reason": f"${skill_name} requires OMX CLI/runtime.",
                    }
                # Extract task: everything after the $name invocation
                task_part = message[explicit_match.end():].strip()
                task_part = task_part.strip('"').strip("'")
                return {
                    "skill": skill_name,
                    "description": defn["description"],
                    "task": task_part or message,
                    "handler": self._handlers.get(skill_name),
                    "blocked": False,
                }

        # Non-explicit keyword matching: most specific (longest) match wins
        best_match = None
        best_length = 0
        msg_lower = message.lower()

        for skill_name, defn in SKILL_DEFINITIONS.items():
            for keyword in defn["keywords"]:
                if keyword.lower() in msg_lower and len(keyword) > best_length:
                    best_match = skill_name
                    best_length = len(keyword)

        if best_match:
            defn = SKILL_DEFINITIONS[best_match]
            if defn["runtime_only"] and not self.omx_runtime:
                return {
                    "skill": best_match,
                    "description": defn["description"],
                    "task": message,
                    "handler": None,
                    "blocked": True,
                    "reason": f"{best_match} requires OMX CLI/runtime.",
                }
            return {
                "skill": best_match,
                "description": defn["description"],
                "task": message,
                "handler": self._handlers.get(best_match),
                "blocked": False,
            }

        return None

    def list_skills(self) -> list:
        """Return all registered skill definitions."""
        result = []
        for name, defn in SKILL_DEFINITIONS.items():
            result.append({
                "name": name,
                "keywords": defn["keywords"],
                "description": defn["description"],
                "runtime_only": defn["runtime_only"],
                "has_handler": name in self._handlers,
            })
        return result
