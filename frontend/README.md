# Frontend (`frontend`)

Next.js app for chat-driven geo-intelligence workflows.

## Responsibilities

- Chat UI for user prompts and agent responses
- Tool call console for observability
- Map/profile cards for area results
- Demographics cards/charts
- Worksheet export

## Run

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Required Configuration

Set in `frontend/.env.local`:

- `NEXT_PUBLIC_AGENT_API_BASE` (usually `http://localhost:8002`)
- `NEXT_PUBLIC_GEOAPIFY_STATIC_KEY` (for static map rendering where applicable)

API key setup walkthrough (Gemini, Geoapify, Census) is in the root README: `../README.md` under **API Key Setup**.

## Data Display Behavior

- UI processes structured `tool_calls` returned by the agent.
- Map and demographics sections update independently.
- Current behavior is replace-on-new-data per turn for each data type.

## Useful Commands

```bash
npm run dev
npm run build
npm run lint
```
