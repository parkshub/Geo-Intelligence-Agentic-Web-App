# Agent Service (`backend/agent`)

LangGraph-based orchestration service for chat requests.

## Documentation Philosophy

This service is documented for two audiences:

- a collaborating developer adding features in parallel
- a new developer taking over the project

The intent is to explain *behavior and decision flow* (why the system does what it does), not only file names. Since this layer performs most orchestration, documentation focuses on execution stages, state transitions, and extension points.

## Responsibilities

- Parse user intent from conversation context
- Build a dynamic tool plan (`summarize_area`, `compare_areas`, `search_places`, `get_demographics`, `compare_demographics`, `analyze_industries`)
- Resolve free-text categories to canonical Geoapify keys
- Execute tool calls via MCP client
- Produce final user-facing narrative text

## Core Components (Heavy Lifting)

- **Graph orchestration** (`app/services/agent.py`)
  - Entry point: `intent_router` -> `plan_builder` -> `tool_executor` -> `narrator`
  - State model carries messages, intent flags, plan, tool results, and tool errors.

- **Intent routing**
  - LLM-first intent parsing with keyword fallback.
  - Extracts locations/categories/radius from latest + recent context.

- **Plan building + contract enforcement**
  - Dynamic tool plan from intent.
  - Contract rules reduce overlap and ensure map/list/demographic flows stay coherent.
  - Category resolution happens before execution and maps free-text categories to canonical Geoapify keys.

- **Tool execution**
  - Parallel execution with bounded timeouts.
  - MCP errors are captured and normalized into meaningful fallback responses.

- **Narration**
  - Generates user-facing output from tool results.
  - Uses guarded fallback messaging when providers fail or locations cannot be resolved.

## Run

```bash
cd backend/agent
pip install -r requirements.txt
uvicorn app.main:app --port 8002
```

## Required Configuration

Set in `backend/agent/.env`:

- `AGENT_MCP__BASE_URL` (usually `http://localhost:8101`)
- LLM provider/model settings (`AGENT_LLM_*`)
- API key for chosen provider

API key setup walkthrough (Gemini, Geoapify, Census) is documented in the root README: `../../README.md` under **API Key Setup**.

## Category Mapping

- Runtime category catalog: `app/data/geoapify_categories_cache.json`
- Resolver pipeline:
  1. exact key check
  2. in-memory resolution cache
  3. constrained LLM mapping for unresolved phrases

## How To Add New Functionality

Use this sequence to keep changes safe and predictable:

1. **Define tool contract first**
   - Decide: what input payload and output shape should the new capability use?
   - If external data is needed, add/update endpoint in `backend/mcp_server` first.

2. **Add MCP client method**
   - Add the corresponding call in `app/services/mcp_client.py`.
   - Ensure HTTP errors surface actionable detail.

3. **Expose tool to agent**
   - Add schema + tool definition in `app/services/tools.py`.
   - Keep descriptions explicit to help planner pick the correct tool.

4. **Wire planner behavior**
   - Update intent/planning logic in `app/services/agent.py`:
     - intent flags (if needed)
     - execution plan generation
     - contract enforcement rules (if needed)
     - category resolution compatibility (if categories apply)

5. **Update narration + frontend expectation**
   - Ensure narrator compaction/sanitization supports new output.
   - Ensure frontend can consume `tool_calls` payload shape if UI rendering is required.

6. **Validate with real prompts**
   - Run at least:
     - success flow
     - partial/missing data flow
     - provider failure flow
   - Confirm fallback text is specific and actionable.

## Contributor Guardrails

- Prefer adding behavior through graph nodes/contracts rather than hardcoding one-off prompt hacks.
- Keep tool outputs structured; avoid relying on narrator free-form text for UI behavior.
- Fail clearly on provider issues; avoid conversational loops that ask for already supplied data.

## Error Handling

- MCP HTTP errors are normalized and bubbled up with detail text
- If tool calls fail and no tool outputs are available, agent returns actionable fallback messaging (instead of generic loops)

## API

- `POST /chat` - main chat endpoint
- `GET /health` - service health check
