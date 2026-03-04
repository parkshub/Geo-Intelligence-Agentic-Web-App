# Plan Checklist v2 (LangChain -> Graph Orchestration)

This checklist defines the technical migration plan and validation criteria for the orchestration upgrade.

## Phase 1 - Define Graph Model

- Define graph state contract (messages, latest input, intent, plan, tool results, tool errors, output)
- Define intent flag schema for map/list/demographics/industry/compare
- Implement session context structure (last locations/categories/radius/tool snapshots)

## Phase 2 - Intent Routing

- Implement LLM-first intent router with strict structured output
- Add deterministic fallback parser for router failures
- Ensure follow-up context extraction works ("these areas", "also show")
- Ensure compare intent is inferred from both explicit and implicit patterns

## Phase 3 - Plan Builder

- Implement dynamic tool plan generation from intent + context
- Add contract enforcement pass:
  - map metrics flow uses summarize/compare tools
  - raw lists use search tool only when appropriate
  - combined requests include all required tool calls
- Add dedupe pass for duplicate tool calls
- Add category canonicalization stage (cache + constrained LLM mapping)

## Phase 4 - Tool Execution

- Implement bounded parallel execution for independent tool calls
- Add per-call timeout and total execution timeout
- Capture and aggregate tool errors without crashing the turn
- Preserve actionable provider error details for narration

## Phase 5 - Narration and Output Safety

- Narrate from compact, sanitized tool outputs
- Prevent raw map internals/tags/coordinates leakage in text
- Add deterministic fallback responses for common provider failures:
  - unresolvable ZIP/location
  - no demographics data available
  - generic provider failure

## Phase 6 - Frontend State Contract

- Ensure tool output bucketing aligns with backend contracts
- Replace map state from current turn's map payloads
- Replace demographics state from current turn's demographics payloads
- Keep map/demographics updates independent per turn

## Phase 7 - Validation Matrix

- Map only -> expected: summarize_area or compare_areas
- Demographics only -> expected: get_demographics or compare_demographics
- Map + demographics -> expected: both map and demographics tool calls
- Compare map + demographics -> expected: compare_areas + compare_demographics
- Industry request -> expected: analyze_industries
- Invalid ZIP/location -> expected: clear fallback message, no conversational loop

## Phase 8 - Risks and Mitigations

- Risk: planner over/under-calls tools -> mitigation: contract enforcement + validation prompts
- Risk: provider instability -> mitigation: bounded execution + error-detail fallbacks
- Risk: category drift -> mitigation: canonical key resolver + strict payload sanitization
- Risk: UI mismatch -> mitigation: fixed tool-output schema expectations + replace policy

## Phase 9 - Rollback Strategy

- Keep non-graph plan builder path available behind feature flag during rollout
- Keep previous narrator fallback available for emergency fallback mode
- Validate canary queries before full cutover

## Done Criteria

- Mixed-intent requests consistently execute all required tools
- Multi-location compare behavior is deterministic
- Provider failures produce actionable user-facing messages
- No raw map internals leak into narrative output
- Frontend renders latest-turn map/demographics state predictably
