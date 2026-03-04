# Plan Checklist (Agentic IDE Output)

This checklist reflects the implementation plan produced from the project planning prompt.

## Phase 0 - Foundations

- Confirm project scope: cafe/coffee-focused geo-intelligence first
- Confirm provider choice: Geoapify (primary), Census (demographics), Overpass (fallback)
- Define environment variables per service
- Create base repo structure (`frontend`, `backend/agent`, `backend/mcp_server`)

## Phase 1 - MCP Server (Provider Wrapper)

- Create FastAPI app + router layout
- Add provider clients:
  - Geoapify client (geocode + places)
  - Census client (ZIP demographics)
  - Overpass client (optional fallback path)
- Define request/response schemas
- Implement endpoints:
  - `POST /places/geocode`
  - `POST /places/search`
  - `POST /places/profile`
  - `POST /places/compare`
  - `POST /places/demographics`
  - `POST /places/demographics/compare`
  - `POST /places/industries`
- Add deterministic metrics functions (saturation + demand proxy)
- Add input validation and actionable 4xx responses

## Phase 2 - Agent Service (LangChain First)

- Create `/chat` endpoint
- Implement MCP client abstraction in agent service
- Define tool schemas for MCP operations
- Implement intent parsing (location/category/radius/brand/compare)
- Implement tool planning logic
- Add category resolution pipeline using Geoapify category cache
- Generate final narrative from tool outputs
- Add fallback responses when tools fail (no generic loops)

## Phase 3 - Frontend

- Build chat UI with message history
- Integrate `/chat` API call
- Render assistant output
- Add tool-call console for transparency/debug
- Render map/profile cards from tool outputs
- Render demographics cards/charts
- Handle replace-on-new-data behavior for map/demographics states

## Phase 4 - End-to-End Scenarios

- Single profile prompt (ZIP + cafes)
- Brand-focused competitive prompt (Starbucks nearby)
- Area comparison prompt (ZIP A vs ZIP B)
- Demographics + map combined request
- Industry popularity prompt
- Invalid/unresolvable ZIP fallback behavior

## Phase 5 - Documentation

- Root README (architecture + setup + keys)
- Service READMEs (agent/mcp/frontend)
- Prompt-sharing doc (approach + key prompts used)
- Architecture doc
- Deployment planning doc

## Acceptance Criteria

- User can ask cafe competition questions by ZIP/location
- Agent uses tools instead of fabricating data
- MCP schemas are stable and provider-agnostic to the frontend
- UI renders structured outputs clearly
- Errors are actionable for users and traceable in logs
