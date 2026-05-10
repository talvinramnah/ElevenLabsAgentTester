"""Thin wrapper around the ElevenLabs ConvAI HTTP API.

We deliberately use plain `requests` (no SDK) to keep deps minimal and to mirror
the shape used in the original `backend/scripts/run_osce_simulation.py` proof.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from prompts import Persona

API_BASE = "https://api.elevenlabs.io"
SIMULATE_TIMEOUT_SECONDS = 600
LIST_TIMEOUT_SECONDS = 30

_ENV_LOADED = False


def _ensure_env_loaded() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    _ENV_LOADED = True


def _api_key() -> str:
    _ensure_env_loaded()
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key


def _headers() -> dict[str, str]:
    return {"xi-api-key": _api_key(), "Content-Type": "application/json"}


@dataclass(frozen=True)
class AgentSummary:
    agent_id: str
    name: str
    tags: list[str]
    created_at_unix_secs: int
    last_call_time_unix_secs: int | None
    archived: bool


def list_agents(page_size: int = 100, include_archived: bool = False) -> list[AgentSummary]:
    """Fetch all agents in the workspace, following pagination cursors."""
    agents: list[AgentSummary] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": page_size, "archived": include_archived}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            f"{API_BASE}/v1/convai/agents",
            headers=_headers(),
            params=params,
            timeout=LIST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        for raw in data.get("agents", []):
            agents.append(
                AgentSummary(
                    agent_id=raw["agent_id"],
                    name=raw.get("name", "(unnamed)"),
                    tags=list(raw.get("tags", []) or []),
                    created_at_unix_secs=int(raw.get("created_at_unix_secs", 0)),
                    last_call_time_unix_secs=raw.get("last_call_time_unix_secs"),
                    archived=bool(raw.get("archived", False)),
                )
            )
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return agents


def get_agent(agent_id: str) -> dict[str, Any]:
    """Return the full agent settings document."""
    resp = requests.get(
        f"{API_BASE}/v1/convai/agents/{agent_id}",
        headers=_headers(),
        timeout=LIST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def update_agent_criteria(
    agent_id: str,
    criteria_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    """Read-modify-write: PATCH the agent's `platform_settings.evaluation.criteria`.

    We GET the current agent, modify only the criteria array, and PATCH back
    the entire `platform_settings` to avoid any chance of nested fields being
    dropped by partial-update semantics.
    """
    current = get_agent(agent_id)
    platform_settings = dict(current.get("platform_settings") or {})
    evaluation = dict(platform_settings.get("evaluation") or {})
    evaluation["criteria"] = criteria_payload
    platform_settings["evaluation"] = evaluation

    body = {"platform_settings": platform_settings}
    resp = requests.patch(
        f"{API_BASE}/v1/convai/agents/{agent_id}",
        headers=_headers(),
        json=body,
        timeout=LIST_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"PATCH agent failed: HTTP {resp.status_code}: {resp.text[:1000]}"
        )
    return resp.json()


def simulate_conversation(agent_id: str, persona: Persona) -> dict[str, Any]:
    """POST a single simulate-conversation request and return the raw JSON response."""
    body = {
        "simulation_specification": {
            "simulated_user_config": {
                "first_message": persona.first_message,
                "language": "en",
                "prompt": {
                    "prompt": persona.prompt,
                },
            },
        },
    }
    resp = requests.post(
        f"{API_BASE}/v1/convai/agents/{agent_id}/simulate-conversation",
        headers=_headers(),
        json=body,
        timeout=SIMULATE_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"simulate-conversation failed: HTTP {resp.status_code}: {resp.text[:500]}"
        )
    return resp.json()
