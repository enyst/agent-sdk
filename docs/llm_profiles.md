LLM Profiles (design)

Overview

This document records the design decision for "LLM profiles" (named LLM configuration files) and how they map to the existing LLM model and persistence in the SDK.

Key decisions

- Reuse the existing LLM Pydantic model schema. A profile file is simply the JSON dump of an LLM instance (the same shape produced by LLM.model_dump(exclude_none=True) or LLM.load_from_json).
- Storage location: ~/.openhands/llm-profiles/<profile_name>.json. The profile_name is the filename (no extension) used to refer to the profile.
- Do not change ConversationState or Agent serialization format for now. Profiles are a convenience for creating LLM instances and registering them in the runtime LLMRegistry.
- Secrets: do NOT store plaintext API keys in profile files by default. Prefer storing the env var name in the LLM.api_key (via LLM.load_from_env) or keep the API key in runtime SecretsManager. The LLMRegistry.save_profile API exposes an include_secrets flag; default False.
- LLM.service_id semantics: keep current behavior (a small set of runtime "usage" identifiers such as 'agent', 'condenser', 'title-gen', etc.). Do not use service_id as the profile name. We will evaluate a rename (service_id -> usage_id) in a separate task (see agent-sdk-23).

LLMRegistry profile API (summary)

- list_profiles() -> list[str]
- load_profile(name: str) -> LLM
- save_profile(name: str, llm: LLM, include_secrets: bool = False) -> str (path)
- register_profiles(profile_ids: Iterable[str] | None = None) -> None

Implementation notes

- LLMRegistry is the single entry point for both in-memory registration and on-disk profile persistence. Pass ``profile_dir`` to the constructor to override the default location when embedding the SDK.
- Use LLM.load_from_json(path) for loading and llm.model_dump(exclude_none=True) for saving.
- Default directory: os.path.expanduser('~/.openhands/llm-profiles/')
- When loading, do not inject secrets. The runtime should reconcile secrets via ConversationState/Agent resolve_diff_from_deserialized or via SecretsManager.
- When saving, respect include_secrets flag; if False, ensure secret fields (api_key, aws_* keys) are omitted or masked.

CLI

- Use a single flag: --llm <profile_name> to select a profile for the agent LLM.
- Also support an environment fallback: OPENHANDS_LLM_PROFILE.
- Provide commands: `openhands llm list`, `openhands llm show <profile_name>` (redacts secrets).

Migration

- Migration from inline configs to profiles: provide a migration helper script to extract inline LLMs from ~/.openhands/agent_settings.json and conversation base_state.json into ~/.openhands/llm-profiles/<name>.json and update references (manual opt-in by user).

Notes on service_id rename

- There is an ongoing discussion about renaming `LLM.service_id` to a clearer name (e.g., `usage_id` or `token_tracking_id`) because `service_id` is overloaded. We will not rename immediately; agent-sdk-23 will investigate the migration and impact.


## Proposed changes for agent-sdk-19 (profile references in persistence)

### Goals
- Allow agent settings and conversation snapshots to reference stored LLM profiles by name instead of embedding full JSON payloads.
- Maintain backward compatibility with existing inline configurations.
- Enable a migration path so that users can opt in to profiles without losing existing data.

### Persistence format updates
- **Agent settings (`~/.openhands/agent_settings.json`)**
  - Add an optional `profile_id` (or `llm_profile`) field wherever an LLM is configured (agent, condenser, router, etc.).
  - When `profile_id` is present, omit the inline LLM payload in favor of the reference.
  - Continue accepting inline definitions when `profile_id` is absent.
- **Conversation base state (`~/.openhands/conversations/<id>/base_state.json`)**
  - Store `profile_id` for any LLM that originated from a profile when the conversation was created.
  - Inline the full LLM payload only when no profile reference exists.

### Loader behavior
- On startup, configuration loaders must detect `profile_id` and load the corresponding LLM via `LLMRegistry.load_profile(profile_id)`.
- If the referenced profile cannot be found, fall back to existing inline data (if available) and surface a clear warning.
- Inject secrets after loading (same flow used today when constructing LLM instances).

### Writer behavior
- When persisting updated agent settings or conversation snapshots, write back the `profile_id` whenever the active LLM was sourced from a profile.
- Only write the raw LLM configuration for ad-hoc instances (no associated profile), preserving current behavior.
- Respect the `OPENHANDS_INLINE_CONVERSATIONS` flag (default: true for reproducibility). When enabled, always inline full LLM payloads—even if `profile_id` exists—and surface an error if a conversation only contains `profile_id` entries.

### Migration helper
- Provide a utility (script or CLI command) that:
  1. Scans existing agent settings and conversation base states for inline LLM configs.
  2. Uses `LLMRegistry.save_profile` to serialize them into `~/.openhands/llm-profiles/<generated-name>.json`.
  3. Rewrites the source files to reference the new profiles via `profile_id`.
- Keep the migration opt-in and idempotent so users can review changes before adopting profiles.

### Testing & validation
- Extend persistence tests to cover:
  - Loading agent settings with `profile_id` only.
  - Mixed scenarios (profile reference plus inline fallback).
  - Conversation snapshots that retain profile references across reloads.
- Add regression tests ensuring legacy inline-only configurations continue to work.

### Follow-up coordination
- Subsequent tasks (agent-sdk-20/21/22) will build on this foundation to expose CLI flags, update documentation, and improve secrets handling.

