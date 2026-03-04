## Development Approach

Our implementation approach is intentionally staged:

1. Build a working vertical slice first (chat -> tool call -> output).
2. Focus the domain narrowly on cafes/coffee competition using ZIP/location queries.
3. Use Geoapify as the primary public API via an MCP wrapper.
4. Use LangChain tool-calling for fast iteration.
5. Keep scoring logic deterministic in Python (not LLM arithmetic).
6. Add demographics and comparisons after the single-location workflow was stable.

This staged approach reduced complexity early and made debugging easier before orchestration became more advanced.

## Implementation Vision

- Frontend: chat interface with tool call transparency
- Agent backend: LangChain, function/tool-calling, structured outputs
- MCP server: wraps provider calls and normalizes schemas
- Provider: Geoapify places/geocode (free-tier accessible)
- First use case: "How competitive is Starbucks/cafes near ZIP X?"
- Output style: competition metrics + demand proxy (explicitly labeled as proxy)

## Scaffold the architecture

```text
Build a full-stack geo-intelligence app with three layers:
1) Next.js frontend chat UI
2) Python agent backend using LangChain tool calling
3) Python MCP server using FastAPI

The domain is location-based business competition, starting with cafes/coffee.
Use Geoapify geocoding + places APIs through the MCP server.

Requirements:
- User can ask for ZIP-based profiling (example: 90007)
- Agent calls tools, not direct provider APIs
- Keep API keys in env vars
- Return structured data for map rendering + readable text summary
- Include a tool-call debug panel in frontend
```

## Generate MCP wrapper contracts

```text
Create MCP endpoints with stable schemas for:
- geocode_location(query)
- search_places(location/lat/lon, radius_m, categories, brand/name filters)
- summarize_area(location, radius, categories, brand) with deterministic metrics
- compare_areas(area_a, area_b, radius, categories, focus_brand)
- demographics endpoints (single and compare)

Use FastAPI + pydantic models.
Normalize provider payloads to internal response models.
Handle errors clearly (400 for invalid input/unresolvable location).
```

## Build LangChain tools

```text
Implement an agent service using LangChain tool-calling (not LangGraph yet).

Agent behavior:
- Parse user intent for location/category/brand/radius
- Select one or more tools
- Call MCP endpoints through an MCP client
- Return concise business answer

Keep deterministic logic in code:
- competitor counts
- density/saturation/demand-proxy calculations
Do not ask the LLM to do arithmetic.
```

## Cafe-focused functionality

```text
Prioritize cafe/coffee competition in the first version.

For prompts like:
"Profile 90007. How competitive is Starbucks nearby?"
Return:
- brand count
- competitor count
- saturation score
- demand proxy score
- top competitors list (closest unique places)

Label demand as a proxy estimate, not real measured foot traffic.
```

## Frontend structure

```text
Create a Next.js page with:
- chat pane (messages + input + loading + errors)
- tool-call console for debugging transparency
- profile cards for map-oriented tool outputs
- demographics card rendering

Data should come from structured tool outputs returned by the backend.
```

## Add comparison flow after single-profile flow

```text
Add compare support:
- "Compare 90007 vs 90210 for high-end coffee campaigns."
Agent should call compare_areas and return both profiles.
Frontend should show two map/profile cards and comparison rationale.
```

## Reliability and fallback behavior

```text
Improve failure handling:
- If provider cannot resolve location/ZIP, return actionable fallback text
- Avoid generic loops like "please provide tool output"
- Surface provider detail (e.g., no results found for ZIP)
```

## Why This Prompt Sequence Worked

- It matched project constraints (public API + MCP + agent + frontend).
- It delivered demonstrable value quickly (first cafe profile flow).
- It deferred orchestration complexity until the basic chain was stable.
- It created a clean path to evolve from LangChain-only into LangGraph later.
