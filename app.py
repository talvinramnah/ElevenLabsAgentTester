"""Streamlit entry point: lists ElevenLabs agents and routes into the detail page on click."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from elevenlabs_client import AgentSummary, list_agents

st.set_page_config(page_title="Agent Simulator", page_icon=None, layout="wide")

st.title("Agent Simulator")
st.caption(
    "Run OSCE persona simulations against ElevenLabs ConvAI agents. "
    "Pick an agent below to drill in and run the personas."
)


@st.cache_data(ttl=60, show_spinner="Fetching agents from ElevenLabs...")
def _cached_list_agents(include_archived: bool) -> list[dict]:
    agents = list_agents(include_archived=include_archived)
    return [
        {
            "agent_id": a.agent_id,
            "name": a.name,
            "tags": a.tags,
            "created_at_unix_secs": a.created_at_unix_secs,
            "last_call_time_unix_secs": a.last_call_time_unix_secs,
            "archived": a.archived,
        }
        for a in agents
    ]


def _format_unix(ts: int | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


with st.sidebar:
    st.header("Filters")
    include_archived = st.toggle("Include archived agents", value=False)
    if st.button("Refresh agent list"):
        _cached_list_agents.clear()
        st.rerun()

try:
    raw_agents = _cached_list_agents(include_archived)
except Exception as exc:
    st.error(f"Failed to fetch agents: {exc}")
    st.stop()

if not raw_agents:
    st.warning("No agents found in this workspace.")
    st.stop()

search = st.text_input("Search by name or agent_id", "").strip().lower()
filtered = (
    [
        a
        for a in raw_agents
        if search in (a["name"] or "").lower() or search in a["agent_id"].lower()
    ]
    if search
    else raw_agents
)

st.write(f"**{len(filtered)}** agents")

table_rows = []
for a in filtered:
    table_rows.append(
        {
            "Name": a["name"],
            "Agent ID": a["agent_id"],
            "Tags": ", ".join(a["tags"]) if a["tags"] else "",
            "Created": _format_unix(a["created_at_unix_secs"]),
            "Last call": _format_unix(a["last_call_time_unix_secs"]),
            "Archived": "yes" if a["archived"] else "",
        }
    )
df = pd.DataFrame(table_rows)
st.dataframe(df, hide_index=True, use_container_width=True)

st.markdown("---")
st.subheader("Open an agent")

cols = st.columns(2)
for i, a in enumerate(filtered):
    col = cols[i % 2]
    with col.container(border=True):
        st.markdown(f"**{a['name']}**")
        st.caption(a["agent_id"])
        if a["tags"]:
            st.caption("Tags: " + ", ".join(a["tags"]))
        if st.button("Open", key=f"open_{a['agent_id']}"):
            st.session_state["agent_id"] = a["agent_id"]
            st.session_state["agent_name"] = a["name"]
            st.switch_page("pages/1_agent_detail.py")
