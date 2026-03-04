# MCP Server (`backend/mcp_server`)

FastAPI service that wraps provider APIs and returns normalized data for agent tools.

## Responsibilities

- Geocoding and place search (Geoapify)
- Area profiling and area comparison
- Demographics (US Census ACS)
- Industry mix analysis
- Provider caching and quota guardrails

## Run

```bash
cd backend/mcp_server
pip install -r requirements.txt
uvicorn app.main:app --port 8101
```

## Required Configuration

Set in `backend/mcp_server/.env`:

- `MCP_GEOAPIFY__API_KEY`
- `MCP_CENSUS__API_KEY` (optional but recommended)
- Overpass settings (`MCP_OVERPASS__*`)

API key setup walkthrough (with screenshots) is in the root README: `../../README.md` under **API Key Setup**.

## Main Endpoints

- `POST /places/geocode`
- `POST /places/search`
- `POST /places/profile`
- `POST /places/compare`
- `POST /places/demographics`
- `POST /places/demographics/compare`
- `POST /places/industries`

## Error Semantics

- `400` for invalid/unresolvable inputs (e.g., location not found, bad ZIP)
- `429` for quota/rate guard issues
- `500` for unexpected provider/service errors

## Notes

- Geocoding is currently country-filtered to US.
- Industry analysis uses broad seed categories and industry bucketing logic.
