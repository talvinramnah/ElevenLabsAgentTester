# Agent Simulator

Local Streamlit dev tool for running ElevenLabs `simulate-conversation` against
your conversational AI agents using a fixed set of OSCE personas, then viewing
the results.

This is internal tooling. It is not deployed and does not depend on the
`backend/` or `frontend/` apps.

## Setup

```bash
cd tools/agent_simulator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then put your ElevenLabs API key in `.env`:

```
ELEVENLABS_API_KEY=sk_...
```

## Run

```bash
streamlit run app.py
```

Streamlit opens at `http://localhost:8501`.

## What it does

1. **Agent list** (`app.py`): live `GET /v1/convai/agents` to your workspace, click any agent.
2. **Agent detail** (`pages/1_agent_detail.py`): pick one or more of the 6 OSCE personas, click Run. Personas execute in parallel via a thread pool (max 6 workers). Progress is shown live.
3. **Three result views**:
   - **Per-prompt**: criteria + result + rationale for one selected persona.
   - **Coverage matrix**: criteria x personas grid, cells colored by result.
   - **Failures**: drill-in on `fail` results, with rationale and transcript slice.
4. **Transcripts**: each persona's full transcript is available in an expander.

## Personas

The 6 personas live in [prompts.py](prompts.py):

1. Repeated open questions
2. Closed questions only
3. Protected variables / gated information
4. General guardrails (role-break attempts)
5. Non-verbal / non-question inputs
6. Non-chronological history taking

## Output

Each run also dumps raw JSON per persona to `tmp/sims/<agent_id>/<timestamp>/<persona_id>.json`
for offline inspection. The Streamlit UI itself is ephemeral and does not yet
surface past runs.

## Notes

- Each `simulate-conversation` call is synchronous and takes ~30-90s. Six in parallel runs in roughly that same window.
- ElevenLabs simulated conversations are **not** persisted in the conversation history dashboard. If you want them archived, the JSON dumps in `tmp/sims/` are your record.
- The simulated user uses the API default LLM (`gemini-2.5-flash` at the time of writing). If you want a different LLM, set `prompt.llm` in `elevenlabs_client.py`.
