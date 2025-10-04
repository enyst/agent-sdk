# LLM Switching: Design and Flow

1. Goals
- Allow switching the active LLM during a conversation (live switch) and on restore (after persistence)
- Keep the Agent stateless; the Conversation State holds the current LLM reference
- Preserve readability: small, explicit components; minimal flags
- Avoid provider-specific state leaking into persisted data

2. Key Concepts
- LLMRegistry: Source of truth for constructing LLM instances by a registry key (profile name). Provides secrets and defaults.
- LLMRef (persisted): Lightweight, serializable pointer to the current LLM. Contains either a registry_key or an inline descriptor (provider, model, base_url, options). No secrets are stored.
- LLMHandle (in-memory): Small wrapper the Agent holds to swap the underlying LLM instance atomically.
- ConversationStats: Aggregates usage per-LLM segment; each segment keyed by an llm_signature (provider/model/base_url) so we can attribute tokens/costs to the right engine.

3. Data Structures

```python
from pydantic import BaseModel
from typing import Optional, Dict, Any

class LLMDescriptor(BaseModel):
    provider: str
    model: str
    base_url: Optional[str] = None
    options: Dict[str, Any] = {}

class LLMRef(BaseModel):
    # Prefer registry_key; fall back to inline descriptor when necessary
    registry_key: Optional[str] = None
    descriptor: Optional[LLMDescriptor] = None
    # Versioning for future migrations
    version: int = 1

    def resolve(self, registry) -> "LLM":
        if self.registry_key:
            return registry.create(self.registry_key)
        assert self.descriptor is not None
        return registry.create_from_descriptor(self.descriptor)

# Signature used by stats; avoids secrets and is stable
class LLMSignature(BaseModel):
    provider: str
    model: str
    base_url: Optional[str]

    @classmethod
    def from_llm(cls, llm: "LLM") -> "LLMSignature":
        return cls(provider=llm.provider, model=llm.model, base_url=llm.base_url)
```

4. Agent Holding an LLM (LLMHandle)

```python
class LLMHandle:
    def __init__(self, llm: "LLM"):
        self._llm = llm

    def get(self) -> "LLM":
        return self._llm

    def set(self, new_llm: "LLM") -> None:
        # Reset ephemeral provider contexts (e.g., stateful Responses thread ids)
        # by constructing a fresh instance; nothing else to clean here.
        self._llm = new_llm
```

5. State Shape and Persistence
- Conversation persists:
  - messages (provider-neutral Message model)
  - llm_ref: LLMRef (not the LLM instance)
  - stats: ConversationStats with per-LLM segments
  - events: optional list of ModelSwitch events
- Do not persist provider-specific formatting (e.g., Anthropic cache markers). Those are applied on formatters per request.

6. Live Switch Flow (Case 2)

1) Client requests switch with either registry_key or descriptor
- Example: { "registry_key": "claude-sonnet" } or inline descriptor

2) Agent validates and resolves
- new_llm = llm_ref.resolve(LLMRegistry)
- LRU-cached model_info makes instantiation fast; new_llm eagerly resolves its profile

3) Agent swaps in-memory LLM
- llm_handle.set(new_llm)
- state.llm_ref = llm_ref (persist new reference)
- stats.start_segment(LLMSignature.from_llm(new_llm))
- events.append(ModelSwitch(...)) (optional)

4) Next turns use the new LLM automatically
- Tool strategy adjusts per model (native vs mock) without rewriting history
- Messages remain provider-neutral; formatters handle provider quirks

5) Persistence
- When the conversation is saved, the latest llm_ref and stats (with multiple segments) are stored. No secrets.

7. Restore and Switch (Case 1)
- Load conversation: messages + llm_ref + stats
- If user supplies a new LLM (registry_key or descriptor), treat it exactly as a live switch (steps 2–5 above). Otherwise, resolve llm_ref and continue.

8. ConversationStats: Per-LLM Segments

```python
class ConversationStats(BaseModel):
    segments: list[dict] = []  # [{"llm": LLMSignature, "usage": Usage, "from_turn": int}]

    def start_segment(self, sig: LLMSignature, from_turn: int | None = None):
        self.segments.append({"llm": sig, "usage": Usage.zero(), "from_turn": from_turn})

    def add_usage(self, sig: LLMSignature, delta: "Usage"):
        # Add to last segment; safeguard if model switched externally
        if not self.segments or self.segments[-1]["llm"] != sig:
            self.start_segment(sig)
        self.segments[-1]["usage"] += delta
```

9. Agent API Surface (Minimal Changes)
- Agent remains stateless; it keeps an LLMHandle and updates state.llm_ref.
- New helper:
  - agent.switch_llm(ref: LLMRef) -> None
- Example usage:

```python
def switch_llm(self, ref: LLMRef):
    new_llm = ref.resolve(self.registry)
    self.llm_handle.set(new_llm)
    self.state.llm_ref = ref
    self.state.stats.start_segment(LLMSignature.from_llm(new_llm), from_turn=self.state.turn_index)
```

10. Compatibility and Simplicity
- Backward compatible: if an older conversation serialized a full LLM, we can read it and convert to LLMRef on load (provide a migration hook); new saves use LLMRef only.
- No flags added; switching is explicit via LLMRef.
- Provider-specific sessions (e.g., Responses stateful) are owned by the LLM instance and are not persisted unless we deliberately design a portable format later.

11. Notes on Model Profile Resolution
- clone() vs switch: switching always constructs a new LLM instance (from registry or descriptor).
- Eager profile init with shared LRU cache keeps it fast and deterministic.
- If lazy init is added later, the new instance may lazy-resolve on first use; this doesn’t affect semantics, only performance.

12. What Happens to Tools and Messages on Switch?
- Tools: We re-evaluate the tool strategy per request. If the new model doesn’t support function calling, MockToolStrategy applies; otherwise tools are sent natively. No changes to saved messages.
- Messages: Persisted messages are provider-neutral; per-provider formatting (Anthropic cache markers, reasoning headers) happens during request preparation and never gets persisted.

13. Optional: User-Facing Trace
- Add a synthetic system message “Switched model to <provider>/<model>” when switch occurs, controlled by a debug flag in higher-level UI code (not persisted by default in SDK).
