# LLM Switching with Existing SDK Components

1. Goals
- Enable switching the active LLM during a conversation (live switch) and after restore
- Keep Agent stateless (as in AgentBase); perform the switch by updating ConversationState.agent
- Reuse existing LLMRegistry and ConversationStats behavior
- Persist using current base_state.json and events (no new persisted types)

2. What Exists Today (Relevant Pieces)
- AgentBase (stateless, frozen): Holds llm: LLM and tools; persisted in base_state.json
- ConversationState: Persists agent, workspace, stats, etc.; auto-persists on field changes
- LocalConversation: Wires LLMRegistry and subscribes ConversationStats.register_llm; registers all LLMs found in agent via get_all_llms()
- LLMRegistry: add/get + notify(RegistryEvent) to subscribers
- ConversationStats: service_to_metrics keyed by LLM.service_id; on registry events it either seeds or restores llm.metrics
- Persistence example: examples/10_persistence.py

3. Constraints Derived from the Code
- Agent must remain stateless; do not mutate Agent in place
- Agent equality is enforced on resume: ConversationState.create() compares the runtime Agent to the persisted Agent via AgentBase.resolve_diff_from_deserialized(). If different, resume fails
- Therefore, “switch on restore” should happen after successful resume (treat as a live switch)

4. Switching Model Mid‑Conversation (Case 2)

4.1 API Surface (Minimal, in-place)
- Add a method on Conversation (LocalConversation): switch_llm_in_place(**overrides) -> None
  - Do not create or assign a new Agent. Mutate the existing runtime LLM object located at state.agent.llm.
  - After mutation, explicitly persist base_state.json.

4.2 Where the LLM instance lives at runtime
- LocalConversation passes the Agent to ConversationState.create(); the runtime Agent is stored at state.agent
- The LLM used for calls is state.agent.llm (a mutable pydantic model; not frozen)

4.3 Steps (in-place reconfigure)
1) Apply overrides on the existing LLM
- llm = self._state.agent.llm
- llm.reconfigure(model=..., base_url=..., api_key=..., ...)  # new public method
  - Semantics:
    - If model or base_url change: re-resolve model profile/caps (LRU keyed by (normalized_model, base_url)); do not reuse the old profile
    - Default http if base_url has no scheme
    - Update _function_calling_active from features/native override
    - Keep Metrics instance; update Telemetry model_name

2) Persist nested changes explicitly
- with self._state:
    self._state._save_base_state(self._state._fs)  # or a new public persist() helper

3) Registry + stats
- Because the LLM object identity is unchanged and service_id is unchanged, LLMRegistry and ConversationStats continue to track the same metrics object. No replacement needed.
- If you intentionally change service_id to segment metrics, re-register via a future registry.rekey(old_id, new_id) or replace(). Otherwise, keep service_id stable.

4.4 Code Sketch (using current components)

```python
# In LocalConversation
def switch_llm_in_place(self, **overrides) -> None:
    llm = self._state.agent.llm
    llm.reconfigure(**overrides)          # reinitialize model info/caps safely
    with self._state:
        # Persist nested changes (since __setattr__ doesn't see deep mutations)
        self._state._save_base_state(self._state._fs)
    # Optional: if you changed service_id intentionally, update the registry mapping
    # self.llm_registry.rekey(old_id, llm.service_id)  # future helper
```

5. Switching on Restore (Case 1)
- Resume must succeed first with a matching Agent (examples/10_persistence.py pattern)
- After resume, call conversation.switch_llm(new_llm) to change engines
- Rationale: Agent equality is enforced by resolve_diff_from_deserialized; attempting to pass a different Agent at construction time fails by design

6. Metrics and service_id
- Keep same service_id to aggregate costs/tokens across switches; requires LLMRegistry.replace() and ConversationStats to always rebind llm.metrics when a known service_id is seen
- Use a new service_id to segment usage per model; combined totals are available via ConversationStats.get_combined_metrics()

7. What Persists
- ConversationState.agent (the full Agent config including the new LLM) in base_state.json
- Events continue as before; a future optional ModelSwitch event can be added for UI traceability (not required for correctness)
- No provider‑specific request formatting is persisted

8. Tool Behavior After Switch
- No history rewrite; existing messages are provider‑neutral
- On next step, function‑calling strategy is chosen per the new model (native vs mock) using existing NonNativeToolCallingMixin + model_features

9. Minimal Internal Adjustments (if needed)
- LLMRegistry: add replace(service_id, new_llm) and emit notify
- ConversationStats.register_llm: when service_id exists, always call llm.restore_metrics(self.service_to_metrics[service_id]) to rebind; the _restored_services guard can be dropped

10. Why This Fits the Current SDK
- Aligns with Agent statelessness (we never mutate Agent; we assign a new copy into state)
- Uses existing persistence (ConversationState auto‑persist on agent assignment)
- Respects resume‑time equality checks (switch happens after resume)
- Leverages existing LLMRegistry + ConversationStats wiring (with small, optional tweaks for replace)
