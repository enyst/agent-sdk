# Runtime LLM Switching (SDK + agent-server)

This repo supports **runtime LLM switching** without any “agent immutability” or
resume-time diff enforcement. The guiding principle is:

- An `Agent` is a *composition* of (effectively) immutable components (`LLM`,
  `AgentContext`, etc.).
- The composition is **switchable**: at runtime the conversation can replace
  components (currently the agent’s primary `LLM`) and persist the change.

## Persistence model (single rule)

Conversation snapshots (`base_state.json`) persist the agent’s LLM as:

- `{"profile_id": "<id>"}` when `LLM.profile_id` is present
- a full inline LLM payload when `LLM.profile_id` is absent

Snapshots are written with `context={"expose_secrets": True}` so inline LLMs can
restore without “reconciliation” against a runtime agent.

## SDK API

Local conversations support two LLM update paths:

- `LocalConversation.switch_llm(profile_id: str)`:
  loads `<profile_id>.json` from the registry’s profile dir and swaps the active
  LLM for the agent’s `usage_id`.
- `LocalConversation.set_llm(llm: LLM)`:
  replaces the active LLM instance for the agent’s `usage_id` (useful for remote
  clients that can’t rely on server-side profile files).

Both are persisted immediately via the conversation’s base state snapshot.

## agent-server API

For a running (or paused/idle) conversation:

- `POST /api/conversations/{conversation_id}/llm`
  - `{"profile_id": "<id>"}`: switch via server-side profile loading
  - `{"llm": {...}}`: set an inline LLM payload (client-supplied config)

There is also a convenience alias:

- `POST /api/conversations/{conversation_id}/llm/switch`
  - `{"profile_id": "<id>"}`

## Remote clients (VS Code extension)

VS Code LLM Profiles are **local-only**. The recommended remote flow is:

1. Resolve `profileId` locally to an LLM configuration.
2. Start the conversation with an expanded `agent.llm` payload (no `profile_id`).
3. On profile changes, call `POST /api/conversations/{id}/llm` with
   `{"llm": <expanded payload>}` so the server persists the new LLM.
4. On restore, the server’s persisted LLM is the source of truth; the client
   can re-apply its selected profile before triggering a new run if desired.
