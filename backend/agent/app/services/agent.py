from __future__ import annotations

import asyncio
import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field, ValidationError

from app.llm.provider import build_chat_model
from app.models import ChatMessage
from app.services.mcp_client import MCPClient
from app.services.tools import build_tools
from app.utils.logging import get_logger

SYSTEM_PROMPT = """You are the Geo-Intel Campaign Planner.
Use only provided tool outputs for factual claims.
Never claim you cannot map or graph; the UI renders map/graph when tool data exists.
If demographics are requested, ensure demographics tool data is present.
If map + demographics are requested together, include both in the response.
Never output XML/HTML-like tags (for example: <map>, <area_a_label>, <area_b_center>).
Never output raw map coordinates, centroid values, or lat/lon pairs in chat text.
Map rendering is handled by structured tool data in the UI, not by chat text.
Return plain-language markdown only. Never output JSON objects, tool payloads, or code blocks.
"""

INTENT_ROUTER_PROMPT = """You are an intent router for a geo-intel assistant.
Return STRICT JSON only, no markdown, no prose.

Infer intent from user request and recent context. Decide whether the user wants:
- map/area profiling
- demographics
- industry analysis
- list/count lookup

Schema:
{
  "wants_map": boolean,
  "wants_demographics": boolean,
  "wants_list": boolean,
  "wants_industry": boolean,
  "is_compare": boolean,
  "locations": [string],
  "categories": [string],
  "radius_m": integer|null,
  "brand": string|null,
  "confidence": number
}

Rules:
- For queries like "Compare 90007 vs 90210 for high-end coffee campaigns", set wants_map=true and is_compare=true.
- For demographics requests, set wants_demographics=true.
- For "how many <brand> shops", set wants_list=true and brand.
- Keep locations as explicit strings from the query/context.
- Use categories like "cafe", "restaurant" when clear.
"""

TOOL_PLAN_PROMPT = """You are a tool planner for a geo-intel assistant.
Return STRICT JSON only. Do not include markdown or prose.

Choose the minimal set of tools needed to answer the user's latest request.
Allowed tools:
- summarize_area
- compare_areas
- search_places
- get_demographics
- compare_demographics
- analyze_industries

Output schema:
{
  "calls": [
    {"tool": "<tool_name>", "payload": {...}}
  ]
}

Rules:
- Be flexible: if a user asks for multiple things (for example demographics + counts), include all needed tools.
- Do not invent tools outside the allowed list.
- Keep payloads concise and grounded in the user request/context.
"""

CATEGORY_SELECTOR_PROMPT = """You map user category phrases to valid Geoapify category keys.
Return STRICT JSON only with this schema:
{
  "mappings": {
    "<input phrase>": "<geoapify.category.key>"
  }
}

Rules:
- Output one best key for each input phrase.
- Only use keys from the allowed list.
- Do not invent keys.
"""


class IntentRouterOutput(BaseModel):
    wants_map: bool = False
    wants_demographics: bool = False
    wants_list: bool = False
    wants_industry: bool = False
    is_compare: bool = False
    locations: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    radius_m: int | None = None
    brand: str | None = None
    confidence: float = 0.0


@dataclass
class SessionContext:
    last_locations: list[str] = field(default_factory=list)
    last_categories: list[str] = field(default_factory=list)
    last_radius_m: int | None = None
    last_tool_results: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentFlags:
    wants_map: bool
    wants_demographics: bool
    wants_list: bool
    wants_industry: bool
    is_compare: bool
    locations: list[str]
    categories: list[str]
    radius_m: int
    brand: str | None = None


@dataclass
class PlannedCall:
    tool: str
    payload: dict[str, Any]


class GraphState(TypedDict, total=False):
    messages: list[ChatMessage]
    latest_user_input: str
    session_key: str
    session_ctx: SessionContext
    intent: IntentFlags
    plan: list[PlannedCall]
    tool_results: list[dict[str, Any]]
    tool_errors: list[str]
    intermediate_steps: list[dict[str, Any]]
    output: str


class AgentService:
    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._client = MCPClient()
        self._tools = build_tools(self._client)
        self._llm = build_chat_model(None)
        self._session_store: dict[str, SessionContext] = {}
        self._category_resolution_cache: dict[str, str] = {}
        self._geoapify_categories = self._load_geoapify_categories()
        self._graph = self._build_graph()
        self._logger.info("agent.initialized", tool_count=len(self._tools))

    def _load_geoapify_categories(self) -> list[str]:
        try:
            cache_path = Path(__file__).resolve().parents[1] / "data" / "geoapify_categories_cache.json"
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            categories = payload.get("categories")
            if isinstance(categories, list):
                return [c for c in categories if isinstance(c, str)]
        except Exception as exc:
            self._logger.warning("agent.category_cache.load_failed", error=str(exc))
        return []

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("intent_router", self._node_intent_router)
        graph.add_node("plan_builder", self._node_plan_builder)
        graph.add_node("tool_executor", self._node_tool_executor)
        graph.add_node("narrator", self._node_narrator)

        graph.set_entry_point("intent_router")
        graph.add_edge("intent_router", "plan_builder")
        graph.add_conditional_edges(
            "plan_builder",
            self._route_after_plan,
            {
                "tool_executor": "tool_executor",
                "narrator": "narrator",
            },
        )
        graph.add_edge("tool_executor", "narrator")
        graph.add_edge("narrator", END)
        return graph.compile()

    async def run(self, messages: list[ChatMessage], trace_id: str | None = None) -> dict[str, Any]:
        latest = messages[-1].content if messages else ""
        self._logger.info(
            "agent.run.start",
            message_count=len(messages),
            last_message_preview=latest[:160],
        )
        session_key = trace_id or "default_session"
        session_ctx = self._session_store.get(session_key, SessionContext())
        initial: GraphState = {
            "messages": messages,
            "latest_user_input": latest,
            "session_key": session_key,
            "session_ctx": session_ctx,
            "intermediate_steps": [],
            "tool_results": [],
            "tool_errors": [],
        }
        try:
            result = await self._graph.ainvoke(initial)
        except Exception:
            self._logger.exception(
                "agent.run.error",
                message_count=len(messages),
                last_message_preview=latest[:160],
            )
            raise

        steps = result.get("intermediate_steps", [])
        for step in steps:
            self._logger.info(
                "agent.tool_call",
                tool=step.get("tool"),
                input=step.get("input", {}),
                observation_summary=_summarize_observation(step.get("observation")),
            )

        output = _coerce_output_text(result.get("output", ""))
        self._logger.info(
            "agent.run.end",
            output_length=len(output),
            tool_step_count=len(steps),
            output_preview=output[:200],
        )
        return {
            "output": output,
            "intermediate_steps": steps,
        }

    async def _node_intent_router(self, state: GraphState) -> GraphState:
        messages = state.get("messages", [])
        latest = state.get("latest_user_input", "")
        session_ctx = state.get("session_ctx", SessionContext())
        intent = await self._infer_intent_with_llm(latest=latest, messages=messages, session_ctx=session_ctx)
        return {"intent": intent}

    async def _infer_intent_with_llm(
        self,
        *,
        latest: str,
        messages: list[ChatMessage],
        session_ctx: SessionContext,
    ) -> IntentFlags:
        recent_turns = []
        for msg in messages[-6:]:
            role = msg.role.upper()
            recent_turns.append(f"{role}: {msg.content}")
        router_prompt = (
            f"{INTENT_ROUTER_PROMPT}\n\n"
            f"Recent conversation:\n{chr(10).join(recent_turns)}\n\n"
            f"Latest user message:\n{latest}"
        )

        try:
            response = await self._llm.ainvoke(router_prompt)
            parsed = _parse_router_output(_coerce_output_text(getattr(response, "content", response)))
            return _to_intent_flags(parsed, messages=messages, session_ctx=session_ctx, latest=latest)
        except Exception as exc:
            self._logger.warning("agent.intent_router.fallback", error=str(exc))
            return _infer_intent_keyword(latest=latest, messages=messages, session_ctx=session_ctx)

    async def _node_plan_builder(self, state: GraphState) -> GraphState:
        intent = state.get("intent")
        if intent is None:
            return {"plan": []}
        latest = state.get("latest_user_input", "")
        plan = await self._build_execution_plan_with_llm(state=state, intent=intent)
        if not plan:
            plan = _build_execution_plan(intent)
        plan = _enforce_tool_contracts(plan=plan, intent=intent, latest_user_input=latest)
        plan = await self._resolve_plan_categories(plan)
        return {"plan": plan}

    async def _build_execution_plan_with_llm(self, *, state: GraphState, intent: IntentFlags) -> list[PlannedCall]:
        latest = state.get("latest_user_input", "")
        prompt = (
            f"{TOOL_PLAN_PROMPT}\n\n"
            f"Latest user request:\n{latest}\n\n"
            f"Intent JSON:\n{json.dumps(intent.__dict__, ensure_ascii=True)}"
        )
        try:
            response = await self._llm.ainvoke(prompt)
            raw = _coerce_output_text(getattr(response, "content", response))
            planned = _parse_plan_output(raw_text=raw)
            normalized = _normalize_planned_calls(planned=planned, intent=intent)
            return _dedupe_calls(normalized)
        except Exception as exc:
            self._logger.warning("agent.plan_builder.fallback", error=str(exc))
            return []

    async def _resolve_plan_categories(self, plan: list[PlannedCall]) -> list[PlannedCall]:
        phrases: list[str] = []
        valid_set = set(self._geoapify_categories)
        for call in plan:
            raw = call.payload.get("categories")
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        phrases.append(item.strip())
        if not phrases:
            return plan

        mapping = await self._resolve_categories_with_llm(phrases)

        updated: list[PlannedCall] = []
        for call in plan:
            payload = dict(call.payload)
            raw = payload.get("categories")
            if isinstance(raw, list):
                resolved = []
                for item in raw:
                    if isinstance(item, str):
                        norm = item.strip().lower()
                        key = mapping.get(norm)
                        if isinstance(key, str) and key in valid_set:
                            resolved.append(key)
                        elif norm in valid_set:
                            resolved.append(norm)
                    else:
                        resolved.append(item)
                payload["categories"] = list(dict.fromkeys([c for c in resolved if isinstance(c, str) and c.strip()]))
            updated.append(PlannedCall(tool=call.tool, payload=payload))
        return updated

    async def _resolve_categories_with_llm(self, phrases: list[str]) -> dict[str, str]:
        if not self._geoapify_categories:
            return {}

        normalized = [p.strip().lower() for p in phrases if isinstance(p, str) and p.strip()]
        if not normalized:
            return {}

        resolved: dict[str, str] = {}
        pending: list[str] = []
        valid_set = set(self._geoapify_categories)

        def _phrase_variants(value: str) -> list[str]:
            base = value.strip().lower()
            variants = {
                base,
                base.replace("_", " "),
                base.replace("-", " "),
            }
            if base.endswith("ies") and len(base) > 3:
                variants.add(base[:-3] + "y")
            if base.endswith("es") and len(base) > 2:
                variants.add(base[:-2])
            if base.endswith("s") and len(base) > 1:
                variants.add(base[:-1])
            return [v for v in variants if v]

        def _resolve_from_cache(value: str) -> str | None:
            for variant in _phrase_variants(value):
                cached = self._category_resolution_cache.get(variant)
                if cached and cached in valid_set:
                    return cached
            return None

        for phrase in normalized:
            if phrase in valid_set:
                resolved[phrase] = phrase
                continue
            cached = _resolve_from_cache(phrase)
            if cached:
                resolved[phrase] = cached
                continue
            pending.append(phrase)

        if not pending:
            return resolved

        candidate_pool = _build_candidate_category_pool(pending, self._geoapify_categories, limit=120)
        prompt = (
            f"{CATEGORY_SELECTOR_PROMPT}\n\n"
            f"Allowed category keys:\n{json.dumps(candidate_pool, ensure_ascii=True)}\n\n"
            f"Input phrases:\n{json.dumps(pending, ensure_ascii=True)}"
        )
        try:
            response = await self._llm.ainvoke(prompt)
            raw = _coerce_output_text(getattr(response, "content", response))
            parsed = _parse_category_mapping_output(raw)
            for phrase, mapped in parsed.items():
                key = phrase.strip().lower()
                if key in pending and mapped in valid_set:
                    resolved[key] = mapped
                    self._category_resolution_cache[key] = mapped
                    if key.endswith("s") and len(key) > 1:
                        self._category_resolution_cache.setdefault(key[:-1], mapped)
        except Exception as exc:
            self._logger.warning("agent.category_mapper.fallback", error=str(exc))

        return resolved

    def _route_after_plan(self, state: GraphState) -> str:
        plan = state.get("plan", [])
        return "tool_executor" if plan else "narrator"

    async def _node_tool_executor(self, state: GraphState) -> GraphState:
        plan = state.get("plan", [])
        if not plan:
            return {"tool_results": [], "tool_errors": [], "intermediate_steps": []}

        async def _run_call(call: PlannedCall) -> dict[str, Any]:
            observation = await asyncio.wait_for(_dispatch_tool_call(self._client, call), timeout=12)
            return {
                "tool": call.tool,
                "input": call.payload,
                "log": "langgraph_tool_executor",
                "observation": observation,
            }

        results: list[dict[str, Any]] = []
        errors: list[str] = []
        try:
            raw_results = await asyncio.wait_for(
                asyncio.gather(*[_run_call(call) for call in plan], return_exceptions=True),
                timeout=16,
            )
        except Exception as exc:
            self._logger.warning("agent.tool_executor.timeout", error=str(exc))
            raw_results = []

        for item in raw_results:
            if isinstance(item, Exception):
                message = str(item) or item.__class__.__name__
                self._logger.warning("agent.tool_executor.call_failed", error=message)
                errors.append(message)
                continue
            results.append(item)

        session_key = state.get("session_key", "default_session")
        session_ctx = state.get("session_ctx", SessionContext())
        intent = state.get("intent")
        if intent is not None:
            if intent.locations:
                session_ctx.last_locations = intent.locations
            if intent.categories:
                session_ctx.last_categories = intent.categories
            session_ctx.last_radius_m = intent.radius_m
        for step in results:
            session_ctx.last_tool_results[step["tool"]] = step["observation"]
        self._session_store[session_key] = session_ctx

        return {
            "tool_results": results,
            "tool_errors": errors,
            "intermediate_steps": results,
        }

    async def _node_narrator(self, state: GraphState) -> GraphState:
        latest = state.get("latest_user_input", "")
        tool_results = state.get("tool_results", [])
        tool_errors = state.get("tool_errors", [])
        if not tool_results:
            if tool_errors:
                return {"output": _build_tool_failure_message(latest=latest, errors=tool_errors)}
            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                "No tool output available. Respond briefly and ask for missing specifics if needed.\n"
                f"User request: {latest}"
            )
        else:
            compact = _compact_tool_results(tool_results)
            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                "Summarize results for the user's request. Keep to metrics present in tool outputs.\n"
                "When map-related tools are present, provide only business-readable findings "
                "(counts, scores, competitor highlights) and avoid map internals.\n"
                f"User request: {latest}\n"
                f"Tool results JSON:\n{json.dumps(compact, ensure_ascii=True)}"
            )
        model_response = await self._llm.ainvoke(prompt)
        output = _coerce_output_text(getattr(model_response, "content", model_response))
        if _looks_like_tool_payload(output):
            output = (
                "I analyzed the requested areas and generated the map data successfully. "
                "See the map and tool panels for structured details."
            )
        return {"output": output}


def _parse_router_output(raw_text: str) -> IntentRouterOutput:
    text = raw_text.strip()
    if not text:
        raise ValueError("Empty router output")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Router output missing JSON object: {text[:200]}")
    payload = json.loads(match.group(0))
    try:
        return IntentRouterOutput.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Router schema validation failed: {exc}") from exc


def _parse_plan_output(raw_text: str) -> list[PlannedCall]:
    text = raw_text.strip()
    if not text:
        raise ValueError("Empty planner output")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Planner output missing JSON object: {text[:200]}")
    payload = json.loads(match.group(0))
    calls = payload.get("calls")
    if not isinstance(calls, list):
        raise ValueError("Planner output missing calls array")

    planned: list[PlannedCall] = []
    for item in calls:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        call_payload = item.get("payload", {})
        if isinstance(tool, str) and isinstance(call_payload, dict):
            planned.append(PlannedCall(tool=tool, payload=call_payload))
    return planned


def _parse_category_mapping_output(raw_text: str) -> dict[str, str]:
    text = raw_text.strip()
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    payload = json.loads(match.group(0))
    mappings = payload.get("mappings")
    if not isinstance(mappings, dict):
        return {}
    output: dict[str, str] = {}
    for key, value in mappings.items():
        if isinstance(key, str) and isinstance(value, str):
            output[key.strip().lower()] = value.strip()
    return output


def _build_candidate_category_pool(phrases: list[str], allowed: list[str], limit: int = 120) -> list[str]:
    pool: set[str] = set()
    for phrase in phrases:
        candidates = difflib.get_close_matches(phrase, allowed, n=40, cutoff=0.2)
        pool.update(candidates)
        tokens = [t for t in re.split(r"[^a-z0-9]+", phrase.lower()) if t]
        for category in allowed:
            cat_lower = category.lower()
            if any(token in cat_lower for token in tokens):
                pool.add(category)
        if len(pool) >= limit:
            break
    if not pool:
        return allowed[:limit]
    return sorted(list(pool))[:limit]


def _normalize_planned_calls(*, planned: list[PlannedCall], intent: IntentFlags) -> list[PlannedCall]:
    allowed = {
        "summarize_area",
        "compare_areas",
        "search_places",
        "get_demographics",
        "compare_demographics",
        "analyze_industries",
    }
    out: list[PlannedCall] = []

    def _first_location() -> str | None:
        return intent.locations[0] if intent.locations else None

    for call in planned:
        if call.tool not in allowed:
            continue
        payload = dict(call.payload)

        if call.tool == "summarize_area":
            location = payload.get("location") or _first_location()
            if not isinstance(location, str) or not location.strip():
                continue
            out.append(
                PlannedCall(
                    tool=call.tool,
                    payload={
                        "location": location,
                        "radius_m": int(payload.get("radius_m") or intent.radius_m),
                        "categories": payload.get("categories", intent.categories or None),
                        "brand": payload.get("brand", intent.brand),
                    },
                )
            )
            continue

        if call.tool == "compare_areas":
            area_a = payload.get("area_a") or (intent.locations[0] if len(intent.locations) >= 1 else None)
            area_b = payload.get("area_b") or (intent.locations[1] if len(intent.locations) >= 2 else None)
            if not isinstance(area_a, str) or not isinstance(area_b, str):
                continue
            out.append(
                PlannedCall(
                    tool=call.tool,
                    payload={
                        "area_a": area_a,
                        "area_b": area_b,
                        "radius_m": int(payload.get("radius_m") or intent.radius_m),
                        "categories": payload.get("categories", intent.categories or None),
                        "focus_brand": payload.get("focus_brand", intent.brand),
                    },
                )
            )
            continue

        if call.tool == "search_places":
            location = payload.get("location") or _first_location()
            if not isinstance(location, str) or not location.strip():
                continue
            out.append(
                PlannedCall(
                    tool=call.tool,
                    payload={
                        "location": location,
                        "radius_m": int(payload.get("radius_m") or intent.radius_m),
                        "categories": payload.get("categories", intent.categories or None),
                    },
                )
            )
            continue

        if call.tool == "get_demographics":
            location = payload.get("location") or _first_location()
            if not isinstance(location, str) or not location.strip():
                continue
            out.append(
                PlannedCall(
                    tool=call.tool,
                    payload={
                        "zip_code": location if re.fullmatch(r"\d{5}", location) else payload.get("zip_code"),
                        "location": location,
                    },
                )
            )
            continue

        if call.tool == "compare_demographics":
            queries = payload.get("queries")
            if not isinstance(queries, list):
                queries = intent.locations[:2]
            queries = [q for q in queries if isinstance(q, str) and q.strip()]
            if len(queries) < 2:
                continue
            out.append(PlannedCall(tool=call.tool, payload={"queries": queries[:2]}))
            continue

        if call.tool == "analyze_industries":
            location = payload.get("location") or _first_location()
            if not isinstance(location, str) or not location.strip():
                continue
            out.append(
                PlannedCall(
                    tool=call.tool,
                    payload={
                        "location": location,
                        "radius_m": int(payload.get("radius_m") or max(intent.radius_m, 3000)),
                        "top_n": int(payload.get("top_n") or 8),
                    },
                )
            )
            continue

    return out


def _to_intent_flags(
    routed: IntentRouterOutput,
    *,
    messages: list[ChatMessage],
    session_ctx: SessionContext,
    latest: str,
) -> IntentFlags:
    text = latest.lower()
    extracted_locations = _extract_recent_locations(messages)
    extracted_radius = _extract_radius_m(text)
    extracted_categories = _extract_categories(text)
    locations = routed.locations or extracted_locations or session_ctx.last_locations
    categories = routed.categories or extracted_categories or session_ctx.last_categories
    radius_m = routed.radius_m or extracted_radius or session_ctx.last_radius_m or 2000
    is_compare = routed.is_compare or len(locations) >= 2 or any(token in text for token in ["compare", " vs ", " versus "])
    return IntentFlags(
        wants_map=routed.wants_map or (is_compare and bool(locations)),
        wants_demographics=routed.wants_demographics,
        wants_list=routed.wants_list and not routed.wants_demographics,
        wants_industry=routed.wants_industry,
        is_compare=is_compare,
        locations=locations,
        categories=categories,
        radius_m=radius_m,
        brand=routed.brand,
    )


def _infer_intent_keyword(latest: str, messages: list[ChatMessage], session_ctx: SessionContext) -> IntentFlags:
    text = latest.lower()
    wants_demographics = "demograph" in text
    wants_industry = "industry" in text
    wants_map = any(token in text for token in [" map", "map ", "show on map", "plot", "where are", "nearby"])
    wants_list = any(token in text for token in ["how many", "list", "all "]) and not wants_demographics
    categories = _extract_categories(text) or session_ctx.last_categories
    locations = _extract_recent_locations(messages) or session_ctx.last_locations
    radius_m = _extract_radius_m(text) or session_ctx.last_radius_m or 2000
    is_compare = len(locations) >= 2 or any(token in text for token in ["compare", " vs ", " versus "])
    brand = None
    return IntentFlags(
        wants_map=wants_map,
        wants_demographics=wants_demographics,
        wants_list=wants_list,
        wants_industry=wants_industry,
        is_compare=is_compare,
        locations=locations,
        categories=categories,
        radius_m=radius_m,
        brand=brand,
    )


def _build_execution_plan(intent: IntentFlags) -> list[PlannedCall]:
    calls: list[PlannedCall] = []
    if intent.wants_industry and intent.locations:
        calls.append(
            PlannedCall(
                tool="analyze_industries",
                payload={
                    "location": intent.locations[0],
                    "radius_m": max(intent.radius_m, 3000),
                    "top_n": 8,
                },
            )
        )
    if (intent.wants_map or intent.is_compare) and intent.locations:
        if intent.is_compare and len(intent.locations) >= 2:
            calls.append(
                PlannedCall(
                    tool="compare_areas",
                    payload={
                        "area_a": intent.locations[0],
                        "area_b": intent.locations[1],
                        "radius_m": intent.radius_m,
                        "categories": intent.categories or None,
                        "focus_brand": intent.brand,
                    },
                )
            )
        else:
            calls.append(
                PlannedCall(
                    tool="summarize_area",
                    payload={
                        "location": intent.locations[0],
                        "radius_m": intent.radius_m,
                        "categories": intent.categories or None,
                        "brand": intent.brand,
                    },
                )
            )
    elif intent.wants_list and intent.locations:
        calls.append(
            PlannedCall(
                tool="search_places",
                payload={
                    "location": intent.locations[0],
                    "radius_m": intent.radius_m,
                    "categories": intent.categories or None,
                },
            )
        )
    if intent.wants_demographics and intent.locations:
        if intent.is_compare and len(intent.locations) >= 2:
            calls.append(
                PlannedCall(
                    tool="compare_demographics",
                    payload={"queries": intent.locations[:2]},
                )
            )
        else:
            loc = intent.locations[0]
            calls.append(
                PlannedCall(
                    tool="get_demographics",
                    payload={
                        "zip_code": loc if re.fullmatch(r"\d{5}", loc) else None,
                        "location": loc,
                    },
                )
            )
    return _dedupe_calls(calls)


def _dedupe_calls(calls: list[PlannedCall]) -> list[PlannedCall]:
    deduped: list[PlannedCall] = []
    seen: set[str] = set()
    for call in calls:
        key = f"{call.tool}:{json.dumps(call.payload, sort_keys=True, ensure_ascii=True, default=str)}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
    return deduped


def _enforce_tool_contracts(
    *,
    plan: list[PlannedCall],
    intent: IntentFlags,
    latest_user_input: str,
) -> list[PlannedCall]:
    """Reduce tool overlap and enforce clear tool responsibilities."""
    calls = _dedupe_calls(list(plan))
    wants_explicit_list = _is_explicit_list_request(latest_user_input)
    has_analyze = any(call.tool == "analyze_industries" for call in calls)

    # If user gave a concrete category (e.g., cafes), prefer category-filtered area tools.
    # analyze_industries is a broad mix view and is not a strict category drilldown tool.
    if (
        has_analyze
        and intent.categories
        and intent.locations
        and not _is_broad_industry_request(latest_user_input)
    ):
        if intent.is_compare and len(intent.locations) >= 2:
            calls.append(
                PlannedCall(
                    tool="compare_areas",
                    payload={
                        "area_a": intent.locations[0],
                        "area_b": intent.locations[1],
                        "radius_m": intent.radius_m,
                        "categories": intent.categories or None,
                        "focus_brand": intent.brand,
                    },
                )
            )
        else:
            calls.append(
                PlannedCall(
                    tool="summarize_area",
                    payload={
                        "location": intent.locations[0],
                        "radius_m": intent.radius_m,
                        "categories": intent.categories or None,
                        "brand": intent.brand,
                    },
                )
            )
        calls = [call for call in calls if call.tool != "analyze_industries"]
        calls = _dedupe_calls(calls)

    if intent.wants_map and intent.is_compare and len(intent.locations) >= 2:
        area_a, area_b = intent.locations[0], intent.locations[1]
        has_compare = any(call.tool == "compare_areas" for call in calls)
        if not has_compare:
            calls.append(
                PlannedCall(
                    tool="compare_areas",
                    payload={
                        "area_a": area_a,
                        "area_b": area_b,
                        "radius_m": intent.radius_m,
                        "categories": intent.categories or None,
                        "focus_brand": intent.brand,
                    },
                )
            )
        # For map-compare, prefer compare_areas over ad-hoc search/summarize per area.
        calls = [
            call
            for call in calls
            if call.tool not in {"search_places", "summarize_area"}
            or call.tool == "compare_areas"
        ]
        return _dedupe_calls(calls)

    if intent.wants_map and intent.locations:
        primary_location = intent.locations[0]
        has_summary = any(
            call.tool == "summarize_area" and call.payload.get("location") == primary_location
            for call in calls
        )
        has_search = any(
            call.tool == "search_places" and call.payload.get("location") == primary_location
            for call in calls
        )

        # Map cards should be backed by summarize_area; keep search_places only for explicit list asks.
        if has_search and not has_summary and not wants_explicit_list:
            for idx, call in enumerate(calls):
                if call.tool != "search_places":
                    continue
                location = call.payload.get("location")
                if not isinstance(location, str) or not location.strip():
                    continue
                calls[idx] = PlannedCall(
                    tool="summarize_area",
                    payload={
                        "location": location,
                        "radius_m": int(call.payload.get("radius_m") or intent.radius_m),
                        "categories": call.payload.get("categories", intent.categories or None),
                        "brand": intent.brand,
                    },
                )
                has_summary = True
                break

        if has_summary and not wants_explicit_list:
            calls = [call for call in calls if call.tool != "search_places"]

    return _dedupe_calls(calls)


def _is_explicit_list_request(latest_user_input: str) -> bool:
    text = latest_user_input.lower()
    list_tokens = [
        "list",
        "show all",
        "all ",
        "how many",
        "raw",
        "table",
        "csv",
    ]
    return any(token in text for token in list_tokens)


def _is_broad_industry_request(latest_user_input: str) -> bool:
    text = latest_user_input.lower()
    tokens = [
        "industry",
        "industries",
        "sector",
        "sector mix",
        "category mix",
        "breakdown",
        "distribution",
        "market mix",
    ]
    return any(token in text for token in tokens)


async def _dispatch_tool_call(client: MCPClient, call: PlannedCall) -> Any:
    if call.tool == "summarize_area":
        return await client.profile_area(call.payload)
    if call.tool == "compare_areas":
        return await client.compare_areas(call.payload)
    if call.tool == "search_places":
        return await client.search_places(call.payload)
    if call.tool == "get_demographics":
        return await client.demographics_profile(call.payload)
    if call.tool == "compare_demographics":
        return await client.demographics_compare(call.payload)
    if call.tool == "analyze_industries":
        return await client.industry_research(call.payload)
    if call.tool == "geocode_location":
        return await client.geocode(str(call.payload.get("query", "")))
    raise ValueError(f"Unsupported tool call: {call.tool}")


def _extract_recent_locations(messages: list[ChatMessage]) -> list[str]:
    user_text = " ".join(msg.content for msg in messages if msg.role == "user")
    zips = re.findall(r"\b\d{5}\b", user_text)
    ordered_unique: list[str] = []
    for zip_code in zips:
        if zip_code not in ordered_unique:
            ordered_unique.append(zip_code)
    if ordered_unique:
        return ordered_unique[-2:]
    if "usc" in user_text.lower() and "los angeles" in user_text.lower():
        return ["University of Southern California, Los Angeles"]
    return []


def _extract_categories(text: str) -> list[str]:
    if any(word in text for word in ["restaurant", "restaurants", "resturaunt", "resturaunts"]):
        return ["restaurant"]
    if "coffee" in text or "cafe" in text:
        return ["cafe"]
    return []


def _extract_radius_m(text: str) -> int | None:
    km_match = re.search(r"\b(\d+(?:\.\d+)?)\s*km\b", text)
    if km_match:
        return int(float(km_match.group(1)) * 1000)
    m_match = re.search(r"\b(\d{3,5})\s*m\b", text)
    if m_match:
        return int(m_match.group(1))
    return None


def _compact_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for step in tool_results:
        tool = str(step.get("tool") or "")
        observation = step.get("observation")
        compact.append(
            {
                "tool": tool,
                "input": step.get("input"),
                "observation_summary": _summarize_observation(observation),
                "observation": _sanitize_observation_for_narrator(tool=tool, observation=observation),
            }
        )
    return compact


def _sanitize_observation_for_narrator(*, tool: str, observation: Any) -> Any:
    if tool == "summarize_area":
        if not isinstance(observation, dict):
            return observation
        return _profile_narrator_view(observation)

    if tool == "compare_areas":
        if not isinstance(observation, dict):
            return observation
        profile_a = observation.get("area_a_profile")
        profile_b = observation.get("area_b_profile")
        return {
            "area_a_profile": _profile_narrator_view(profile_a) if isinstance(profile_a, dict) else profile_a,
            "area_b_profile": _profile_narrator_view(profile_b) if isinstance(profile_b, dict) else profile_b,
            "winner": observation.get("winner"),
            "rationale": observation.get("rationale"),
        }

    if tool == "search_places":
        if not isinstance(observation, list):
            return observation
        sample_names = []
        for place in observation[:8]:
            if isinstance(place, dict) and isinstance(place.get("name"), str):
                sample_names.append(place["name"])
        return {
            "result_count": len(observation),
            "sample_names": sample_names,
        }

    return observation


def _profile_narrator_view(profile: Any) -> Any:
    if not isinstance(profile, dict):
        return profile

    competitors: list[dict[str, Any]] = []
    for place in profile.get("top_competitors", [])[:5]:
        if isinstance(place, dict):
            competitors.append(
                {
                    "name": place.get("name"),
                    "distance_m": place.get("distance_m"),
                    "brand": place.get("brand"),
                }
            )

    return {
        "query": profile.get("query"),
        "brand_count": profile.get("brand_count"),
        "competitor_count": profile.get("competitor_count"),
        "saturation_score": profile.get("saturation_score"),
        "demand_proxy_score": profile.get("demand_proxy_score"),
        "top_competitors": competitors,
        "notes": profile.get("notes", []),
    }


def _sanitize_output_text(text: str) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", text.strip())
    return cleaned


def _looks_like_tool_payload(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    markers = [
        '"tool_code"',
        '"parameters"',
        '"display_map"',
        '"area_a_center"',
        '"area_b_center"',
        '"area_a_competitors"',
        '"area_b_competitors"',
    ]
    if cleaned.startswith("{") or cleaned.startswith("["):
        return any(marker in cleaned for marker in markers)
    return '"tool_code"' in cleaned and '"parameters"' in cleaned


def _coerce_output_text(output: Any) -> str:
    if isinstance(output, str):
        return _sanitize_output_text(output)
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return _sanitize_output_text("".join(parts))
    if isinstance(output, dict):
        maybe_text = output.get("text")
        if isinstance(maybe_text, str):
            return _sanitize_output_text(maybe_text)
    return _sanitize_output_text(str(output or ""))


def _build_tool_failure_message(*, latest: str, errors: list[str]) -> str:
    details = " | ".join([e for e in errors if isinstance(e, str) and e.strip()][:2]).lower()
    if "no results found for" in details:
        match = re.search(r"no results found for '([^']+)'", details)
        location = match.group(1) if match else "that location"
        return (
            f"I couldn't resolve `{location}` with the current providers, so I couldn't run the requested analysis. "
            "Please try a nearby ZIP, a city + state, or a full address."
        )
    if "no census demographics found" in details or "status 204" in details or "expecting value" in details:
        return (
            "I couldn't retrieve demographics for that location from the Census source right now. "
            "Please try a nearby ZIP code or provide a city + state."
        )
    return (
        "I couldn't complete that request because one or more data-provider calls failed. "
        "Please retry with a nearby ZIP, city + state, or a full address."
    )


def _summarize_observation(observation: Any) -> Any:
    if isinstance(observation, (str, int, float, bool)) or observation is None:
        return observation
    if isinstance(observation, list):
        return f"list[{len(observation)}]"
    if isinstance(observation, dict):
        keys = list(observation.keys())
        return {"keys": keys[:8], "truncated": len(keys) > 8}
    return str(type(observation).__name__)
