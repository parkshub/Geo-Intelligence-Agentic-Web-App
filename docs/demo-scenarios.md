# Demo Scenarios

Use these scripted flows when recording the interview video. Each scenario demonstrates a distinct reasoning path and ensures the panel sees tool-call traces, proxy demand disclaimers, and comparison logic.

## 1. Starbucks Near USC (ZIP 90007)
- Prompt: `Profile 90007. How competitive is Starbucks nearby?`
- Expected: `geocode_location` → `search_places` → `summarize_area`. Agent returns saturation + demand proxy with disclaimer.
- Talking points:
  - Show Geoapify credits estimate in UI footer.
  - Highlight tool-call console entries and explain how MCP hides API keys.

## 2. Campaign Decision: 90007 vs 90210
- Prompt: `Compare 90007 vs 90210 for coffee campaigns with 2km radius.`
- Expected: `compare_areas` tool triggers two area profiles + comparison card in UI.
- Talking points:
  - Discuss deterministic scoring (density vs proxy demand).
  - Show scenario worksheet export and mention documentation philosophy.

## 3. Industry Targeting Near Universities
- Prompt: `What industries should advertise near USC within 3km?`
- Expected: Agent references existing metrics + suggests verticals. Even if only `summarize_area` is called, highlight prompt macros + guidance.
- Talking points:
  - Explain foot-traffic proxy logic (rank.popularity + chain presence).
  - Mention fallback connectors (Overpass + Ticketmaster) and free-tier guardrails.

## 4. Events Overlay (Optional)
- Prompt: `Overlay upcoming events around 90007 within 10km.`
- After the main flow, describe how Ticketmaster connector would be toggled for event-based recommendations without leaving free tiers.
