# Architecture

This architecture describes the implemented system boundaries and runtime flow.

## High-Level Flow

`frontend` -> `agent (LangChain tool-calling)` -> `mcp_server (FastAPI)` -> `Geoapify/Census/Overpass`

## Components

## 1) Frontend (`frontend`)

Responsibilities:

- Provide chat interface
- Send full message history to `/chat`
- Render tool-driven outputs:
  - map/profile cards
  - demographics cards
  - comparison views
- Show tool call console for transparency

Inputs/Outputs:

- Input: user natural language query
- Output: assistant text + structured tool calls/result payloads

## 2) Agent Backend (`backend/agent`)

Agent mode: LangChain-based tool calling.

Responsibilities:

- Infer intent from message + recent context
- Select and call tools exposed by MCP
- Resolve categories to canonical Geoapify keys
- Compose final narrative response from tool outputs

Key design principle:

- LLM decides actions; deterministic Python computes numeric metrics.

## 3) MCP Server (`backend/mcp_server`)

Responsibilities:

- Wrap public API calls behind stable internal contracts
- Normalize provider payloads into internal schemas
- Enforce request validation and clear error semantics

Core endpoints:

- geocoding
- place search
- area summarization/comparison
- demographics
- industry analysis

## 4) External Providers

- Geoapify: geocode + places search
- Census: ZIP demographics
- Overpass: best-effort fallback/augmentation path

## Data/Decision Boundaries

- Frontend: presentation + state transitions
- Agent: orchestration and tool strategy
- MCP: provider execution and normalization
- Providers: raw source data

## Sequence Example (Cafe Profile)

1. User asks: "Profile 90007. How competitive is Starbucks nearby?"
2. Agent infers profile intent + category context.
3. Agent calls `summarize_area` through MCP.
4. MCP resolves location, fetches places, computes metrics, returns normalized profile.
5. Agent narrates business summary from structured output.
6. Frontend renders profile/map card.

## Rationale for This Architecture

- Fast to implement and validate
- Clear separation of concerns
- Supports incremental expansion (single-area -> comparison -> demographics)
- Easy to evolve to graph orchestration later without rewriting MCP/frontend contracts
