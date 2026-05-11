"""Agent detail page: pick personas, run them in parallel, view results."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit pages run with cwd set to the project root, so we add the parent
# directory of this file to sys.path to make sibling modules importable.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# Bridge Streamlit Cloud secrets into env so existing os.environ-based clients
# work even if a user lands on this page directly without going through app.py.
if "ELEVENLABS_API_KEY" not in os.environ:
    try:
        if "ELEVENLABS_API_KEY" in st.secrets:
            os.environ["ELEVENLABS_API_KEY"] = st.secrets["ELEVENLABS_API_KEY"]
    except Exception:
        pass

from prompts import PERSONAS, PERSONAS_BY_ID, Persona  # noqa: E402
from sim_runner import RunResult, new_run_timestamp, run_persona  # noqa: E402

st.set_page_config(page_title="Agent Simulator | Detail", layout="wide")

agent_id = st.session_state.get("agent_id")
agent_name = st.session_state.get("agent_name", "(unknown)")

if not agent_id:
    st.warning("No agent selected. Go back to the agent list.")
    if st.button("Back to agent list"):
        st.switch_page("app.py")
    st.stop()

st.title(f"{agent_name}")
st.caption(f"`{agent_id}`")

if st.button("← Back to agent list"):
    st.switch_page("app.py")

st.markdown("---")

st.subheader("1. Pick personas")

selected_ids: list[str] = st.session_state.setdefault(
    "selected_persona_ids", [p.id for p in PERSONAS]
)

cols = st.columns([1, 1, 4])
with cols[0]:
    if st.button("Select all"):
        st.session_state["selected_persona_ids"] = [p.id for p in PERSONAS]
        st.rerun()
with cols[1]:
    if st.button("Clear"):
        st.session_state["selected_persona_ids"] = []
        st.rerun()

selected_ids = st.multiselect(
    "Personas to run",
    options=[p.id for p in PERSONAS],
    default=st.session_state["selected_persona_ids"],
    format_func=lambda pid: f"{PERSONAS_BY_ID[pid].label}",
    key="persona_multiselect",
)
st.session_state["selected_persona_ids"] = selected_ids

with st.expander("Show persona descriptions"):
    for p in PERSONAS:
        marker = "[selected]" if p.id in selected_ids else "         "
        st.markdown(f"`{marker}` **{p.label}** — {p.description}")

st.subheader("2. Run")

run_clicked = st.button(
    f"Run {len(selected_ids)} persona(s) in parallel",
    disabled=not selected_ids,
    type="primary",
)

if run_clicked:
    selected_personas: list[Persona] = [PERSONAS_BY_ID[pid] for pid in selected_ids]
    run_ts = new_run_timestamp()
    status = st.status(
        f"Running {len(selected_personas)} personas in parallel...", expanded=True
    )
    progress_lines: dict[str, str] = {
        p.id: f"- **{p.label}** — pending" for p in selected_personas
    }
    placeholder = status.empty()
    placeholder.markdown("\n".join(progress_lines.values()))

    results: list[RunResult] = []
    workers = min(12, len(selected_personas))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_persona, agent_id, p, run_ts): p for p in selected_personas
        }
        for fut in as_completed(futures):
            res: RunResult = fut.result()
            results.append(res)
            if res.error:
                progress_lines[res.persona_id] = (
                    f"- **{res.persona_label}** — FAILED ({res.error}) "
                    f"in {res.elapsed_seconds:.1f}s"
                )
            else:
                fail_count = sum(1 for c in res.criteria if c.get("result") == "failure")
                summary = (
                    f"call_successful=`{res.call_successful}` "
                    f"| {len(res.criteria)} criteria | {fail_count} fail"
                )
                progress_lines[res.persona_id] = (
                    f"- **{res.persona_label}** — done in "
                    f"{res.elapsed_seconds:.1f}s ({summary})"
                )
            placeholder.markdown("\n".join(progress_lines.values()))

    results.sort(key=lambda r: [p.id for p in selected_personas].index(r.persona_id))

    fail_total = sum(
        1
        for r in results
        for c in r.criteria
        if c.get("result") == "failure"
    )
    error_total = sum(1 for r in results if r.error)
    if error_total:
        status.update(
            label=f"Done with {error_total} HTTP error(s)", state="error"
        )
    elif fail_total:
        status.update(
            label=f"Done — {fail_total} criteria failed across {len(results)} personas",
            state="complete",
        )
    else:
        status.update(label=f"Done — all {len(results)} personas passed", state="complete")

    st.session_state["last_results"] = results
    st.session_state["last_run_agent_id"] = agent_id
    st.session_state["last_run_ts"] = run_ts

results = st.session_state.get("last_results")
last_agent = st.session_state.get("last_run_agent_id")
if not results or last_agent != agent_id:
    st.info("Pick personas above and click Run to see results.")
    st.stop()

st.markdown("---")
st.subheader("3. Results")

run_ts_label = st.session_state.get("last_run_ts", "")
st.caption(
    f"Run id: `{run_ts_label}` | "
    f"raw JSON dumps in `tools/agent_simulator/tmp/sims/{agent_id}/{run_ts_label}/`"
)


_LONG_DF_COLUMNS = ["persona_id", "persona_label", "criteria_id", "result", "rationale"]


def _to_long_df(results: list[RunResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        if r.error:
            rows.append(
                {
                    "persona_id": r.persona_id,
                    "persona_label": r.persona_label,
                    "criteria_id": "<error>",
                    "result": "error",
                    "rationale": r.error,
                }
            )
            continue
        for c in r.criteria:
            rows.append(
                {
                    "persona_id": r.persona_id,
                    "persona_label": r.persona_label,
                    "criteria_id": c.get("criteria_id", ""),
                    "result": c.get("result", ""),
                    "rationale": c.get("rationale", ""),
                }
            )
    if not rows:
        return pd.DataFrame(columns=_LONG_DF_COLUMNS)
    return pd.DataFrame(rows)


long_df = _to_long_df(results)


def _color_result(val: str) -> str:
    if val == "success":
        return "background-color: rgba(0, 180, 70, 0.18)"
    if val == "failure":
        return "background-color: rgba(220, 50, 50, 0.55); color: white; font-weight: 700"
    if val == "error":
        return "background-color: rgba(220, 50, 50, 0.75); color: white; font-weight: 700"
    if val == "unknown":
        return "background-color: rgba(180, 180, 180, 0.15)"
    return ""


def _style_row(row: "pd.Series") -> list[str]:
    """Row-level styling so the whole criterion row goes red on fail, not just the result cell."""
    result = str(row.get("result", ""))
    if result in ("failure", "error"):
        base = (
            "background-color: rgba(220, 50, 50, 0.45); "
            "color: white; font-weight: 700"
        )
    elif result == "success":
        base = "background-color: rgba(0, 180, 70, 0.10)"
    elif result == "unknown":
        base = "background-color: rgba(180, 180, 180, 0.08)"
    else:
        base = ""
    return [base] * len(row)


tabs = st.tabs(
    ["Per-prompt", "Coverage matrix", "Failure drill-in", "Transcripts", "Run summary"]
)

with tabs[0]:
    st.markdown("**Per-prompt criteria results**")
    if long_df.empty:
        st.info("No results to show.")
    else:
        col_a, col_b = st.columns([3, 2])
        with col_a:
            persona_label = st.selectbox(
                "Persona",
                options=[r.persona_label for r in results],
                index=0,
                key="perprompt_persona",
            )
        with col_b:
            fails_only = st.toggle(
                "Show fails only",
                value=False,
                key="perprompt_fails_only",
                help="Filter to criteria where result is `fail` or `error`.",
            )

        sub = long_df[long_df["persona_label"] == persona_label][
            ["criteria_id", "result", "rationale"]
        ].reset_index(drop=True)

        total_count = len(sub)
        fail_count = int((sub["result"].isin(["failure", "error"])).sum())
        if fails_only:
            sub = sub[sub["result"].isin(["failure", "error"])].reset_index(drop=True)

        if fail_count:
            st.markdown(
                f":red[**{fail_count}** failed criteria] out of {total_count} for **{persona_label}**"
            )
        else:
            st.markdown(f"No failures for **{persona_label}** ({total_count} criteria)")

        if sub.empty:
            st.info("Nothing to show with the current filter.")
        else:
            styled = sub.style.apply(_style_row, axis=1)
            st.dataframe(styled, use_container_width=True, hide_index=True)

with tabs[1]:
    st.markdown("**Coverage matrix** — rows: criteria, columns: personas, cells: result")
    if long_df.empty:
        st.info("No results to show.")
    else:
        matrix_fails_only = st.toggle(
            "Show only criteria with at least one fail",
            value=False,
            key="matrix_fails_only",
        )
        matrix = long_df.pivot_table(
            index="criteria_id",
            columns="persona_label",
            values="result",
            aggfunc="first",
        ).fillna("")
        ordered_cols = [r.persona_label for r in results if r.persona_label in matrix.columns]
        matrix = matrix[ordered_cols]
        if matrix_fails_only:
            fail_mask = matrix.isin(["failure", "error"]).any(axis=1)
            matrix = matrix[fail_mask]
        if matrix.empty:
            st.info("No criteria match the current filter.")
        else:
            styled_matrix = matrix.style.map(_color_result)
            st.dataframe(styled_matrix, use_container_width=True)

        col_summary = st.columns(len(results))
        for col, r in zip(col_summary, results):
            with col:
                if r.error:
                    st.metric(r.persona_label, "error")
                else:
                    success = sum(1 for c in r.criteria if c.get("result") == "success")
                    fail = sum(1 for c in r.criteria if c.get("result") == "failure")
                    unknown = sum(1 for c in r.criteria if c.get("result") == "unknown")
                    st.metric(
                        r.persona_label,
                        f"{success}/{len(r.criteria)} pass",
                        delta=f"{fail} fail / {unknown} unknown",
                        delta_color="inverse" if fail else "off",
                    )

with tabs[2]:
    if long_df.empty:
        st.info(
            "No criteria results to show. Does the selected agent have any "
            "evaluation criteria configured in the ElevenLabs dashboard?"
        )
        fails = pd.DataFrame(columns=_LONG_DF_COLUMNS)
    else:
        fails = long_df[long_df["result"].isin(["failure", "error"])].reset_index(drop=True)
        if fails.empty:
            st.success("Zero `fail` results across all selected personas.")
            unknowns = long_df[long_df["result"] == "unknown"].reset_index(drop=True)
            if not unknowns.empty:
                st.markdown(
                    "Showing `unknown` results instead — criteria the personas did not exercise."
                )
                st.dataframe(unknowns, use_container_width=True, hide_index=True)
    if not fails.empty:
        st.markdown(f"**{len(fails)}** failures across selected personas.")
        for _, row in fails.iterrows():
            with st.expander(
                f"{row['persona_label']} — {row['criteria_id']} ({row['result']})",
                expanded=False,
            ):
                st.markdown(f"**Rationale:**\n\n{row['rationale']}")
                matching = next(
                    (r for r in results if r.persona_id == row["persona_id"]), None
                )
                if matching is None:
                    continue
                if matching.transcript:
                    st.markdown("**Transcript context:**")
                    transcript_lines = []
                    for i, t in enumerate(matching.transcript, 1):
                        role = (t.get("role") or "?").upper()
                        msg = t.get("message") or t.get("text") or ""
                        transcript_lines.append(f"[{i:02d}] {role}: {msg}")
                    st.code("\n".join(transcript_lines), language="text")

with tabs[3]:
    st.markdown("**Full transcripts per persona**")
    for r in results:
        with st.expander(
            f"{r.persona_label} ({len(r.transcript)} turns)", expanded=False
        ):
            if r.error:
                st.error(r.error)
                continue
            if r.transcript_summary:
                st.markdown(f"**Summary:** {r.transcript_summary}")
            transcript_lines = []
            user_turns = 0
            for i, t in enumerate(r.transcript, 1):
                role = (t.get("role") or "?").upper()
                msg = t.get("message") or t.get("text") or ""
                if role == "USER":
                    user_turns += 1
                transcript_lines.append(f"[{i:02d}] {role}: {msg}")
            st.caption(
                f"Total: {len(r.transcript)} turns | "
                f"User (simulated student) turns: {user_turns} | "
                f"call_successful: {r.call_successful}"
            )
            st.code("\n".join(transcript_lines), language="text")

with tabs[4]:
    st.markdown("**Run summary**")
    summary_rows = []
    for r in results:
        success = sum(1 for c in r.criteria if c.get("result") == "success")
        fail = sum(1 for c in r.criteria if c.get("result") == "failure")
        unknown = sum(1 for c in r.criteria if c.get("result") == "unknown")
        user_turns = sum(1 for t in r.transcript if (t.get("role") or "") == "user")
        summary_rows.append(
            {
                "Persona": r.persona_label,
                "call_successful": r.call_successful,
                "Criteria total": len(r.criteria),
                "Success": success,
                "Fail": fail,
                "Unknown": unknown,
                "User turns": user_turns,
                "Total turns": len(r.transcript),
                "Elapsed (s)": round(r.elapsed_seconds, 1),
                "Error": r.error or "",
            }
        )
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
