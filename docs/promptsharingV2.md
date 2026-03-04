# Approach and Prompts Sharing (v2)

This document captures the prompt that guided the planning/migration work when the system moved from a simple LangChain tool-calling flow to a graph-based orchestration flow.

## Why We Needed a New Plan

The first version was good for straightforward queries (map businesses, simple industry summaries), but it became inconsistent as we added:

- demographics + map in one request
- multi-location comparisons
- follow-up context ("these areas", "also show ...")
- stronger reliability and fallback expectations

At that point, a plain agent-executor style loop was too brittle. The system needed explicit orchestration.

## Technical Shortcomings We Observed in the LangChain-First Flow

- **Inconsistent multi-tool planning**
  - Combined intents (map + demographics + compare) were sometimes partially executed.
  - Some requests triggered only one tool even when two or more were required.

- **Static pairing behavior and brittle intent gating**
  - Deterministic keyword branches could suppress valid calls in mixed-intent prompts.
  - Example pattern: demographics requests suppressing list/map branches unexpectedly.

- **Weak control over execution order and parallelism**
  - Harder to guarantee "run these together" vs "run these conditionally".
  - No explicit graph state transitions to control plan -> execute -> narrate behavior.

- **Error handling produced confusing conversational loops**
  - Tool failures often collapsed into generic fallback text instead of actionable cause.
  - User saw repeated "specify again" responses after already providing location/context.

- **Provider/output handling fragility**
  - Streaming/provider output edge cases caused runtime instability (`IndexError`, timeout/deadline patterns).
  - Needed deterministic non-stream fallback and stronger output coercion/sanitization.

- **Map/data contract drift**
  - Frontend expected certain tool payload shapes, but planner occasionally produced overlapping or mismatched flows.
  - Needed clearer tool contracts and post-planning enforcement.

## Prompt Used to Plan the Migration

```text
We need a reliability-focused upgrade plan from a simple LangChain tool-calling flow to a graph-orchestrated agent flow.

Context:
- App now supports map profiling, industry analysis, demographics, and multi-area comparison.
- Mixed requests (map + demographics, compare + map, follow-up context) are inconsistent.
- We need predictable multi-tool behavior, better failure handling, and clearer state transitions.

Please create a technical migration plan with these goals:
1) Move orchestration to LangGraph state machine:
   - intent_router -> plan_builder -> tool_executor -> narrator
   - explicit graph state model with intent, plan, tool_results, intermediate_steps
2) Keep tool contracts clear and enforce separation of concerns:
   - summarize/compare for map metrics
   - search_places for raw lists only
   - demographics tools only when requested
3) Support bounded parallel execution for independent tool calls.
4) Add robust error handling:
   - preserve provider error details
   - no generic "please provide tool output" loops
   - actionable fallback text
5) Maintain session context memory (locations/categories/radius) without causing tool drift.
6) Add category resolution pipeline:
   - canonical Geoapify key mapping via cache + constrained LLM mapping
7) Add verification plan:
   - map-only, demographics-only, combined, compare, and failure scenarios.

Output required:
- Migration checklist by phase
- Risks and mitigations
- Validation matrix with expected tool calls
- Minimal rollback strategy
```

## Scope Expansion Narrative (for interview/documentation)

- Initial scope: business mapping + industry views.
- Added value layer: accurate demographics integration and comparison.
- As feature complexity increased, orchestration quality became the bottleneck.
- Migrated planning/execution to graph-based flow to improve determinism, composability, and reliability.
