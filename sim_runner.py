"""Parallel runner for executing simulated-conversation calls across multiple personas."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from elevenlabs_client import simulate_conversation
from prompts import Persona

TMP_DIR = Path(__file__).parent / "tmp" / "sims"


@dataclass
class RunResult:
    persona_id: str
    persona_label: str
    transcript: list[dict[str, Any]] = field(default_factory=list)
    criteria: list[dict[str, Any]] = field(default_factory=list)
    call_successful: str = "unknown"
    transcript_summary: str = ""
    elapsed_seconds: float = 0.0
    error: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


def _dump_json(agent_id: str, run_ts: str, persona_id: str, payload: dict[str, Any]) -> Path:
    out_dir = TMP_DIR / agent_id / run_ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{persona_id}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


def new_run_timestamp() -> str:
    """Return a `YYYYMMDD_HHMMSS` string suitable as a run id for filesystem dumps."""
    return time.strftime("%Y%m%d_%H%M%S")


def run_persona(
    agent_id: str,
    persona: Persona,
    run_ts: str,
) -> RunResult:
    started = time.time()
    result = RunResult(persona_id=persona.id, persona_label=persona.label)
    try:
        data = simulate_conversation(agent_id, persona)
        result.raw_response = data
        result.transcript = data.get("simulated_conversation") or []
        analysis = data.get("analysis") or {}
        result.criteria = analysis.get("evaluation_criteria_results_list") or []
        result.call_successful = analysis.get("call_successful") or "unknown"
        result.transcript_summary = analysis.get("transcript_summary") or ""
        _dump_json(agent_id, run_ts, persona.id, data)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        result.elapsed_seconds = time.time() - started
    return result


def run_personas(
    agent_id: str,
    personas: list[Persona],
    on_progress: Callable[[RunResult], None] | None = None,
    max_workers: int = 6,
) -> list[RunResult]:
    """Run a set of personas in parallel against a single agent.

    Returns results in the same order as the input `personas`. `on_progress` is
    called once per persona as soon as that persona finishes (in completion
    order, not input order) so the UI can show live progress.
    """
    if not personas:
        return []
    run_ts = new_run_timestamp()
    by_id: dict[str, RunResult] = {}
    workers = min(max_workers, len(personas))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_persona, agent_id, p, run_ts): p for p in personas}
        for fut in as_completed(futures):
            res = fut.result()
            by_id[res.persona_id] = res
            if on_progress is not None:
                try:
                    on_progress(res)
                except Exception:
                    pass
    return [by_id[p.id] for p in personas]
