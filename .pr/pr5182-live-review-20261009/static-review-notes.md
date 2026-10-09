PR head reviewed: `d6a512553bf92c896dd9f2fd877f7aaa2b041fbc`.

Independent static review traced analyzer dispatch, the legacy batch-override
adapter, Event registration, EventLog parent stamping, incremental View filtering,
cancellation, and secret masking. No confirmed new conversation-restoration or
legacy-analyzer regression was found in those paths. The new event is excluded
from the LLM View by the existing `LLMConvertibleEvent` filter; action batches stay
adjacent in that View, and EventLog adds the audit event to the normal parent chain.

Focused verification: 15 tests passed from
`test_security_analysis_event.py` and `test_async_secret_masking.py`, running the
exact-head source via `PYTHONPATH` and the existing dependency environment.
`OH_PERSISTENCE_DIR` was redirected to `/tmp/pr5182-static-state` because the
executor's default `/home/agent/.openhands` directory is read-only. A duplicate
broader suite was interrupted when another reviewer reported covering it.

Two additional observations are reproducible, but should not be presented as
unequivocal new blocking defects:

1. The new `analyze_action()` docstring says detailed analyzers should override it
   instead of `security_risk()`, but `security_risk()` remains abstract. A subclass
   implementing only the new hook cannot instantiate. Existing analyzer subclasses
   are unaffected; this is an incomplete contract for the new extension hook.
   Relevant changed lines: `security/analyzer.py:97-105`.

2. The new audit persistence path inherits an existing secret-source replacement
   cache flaw. `static-mask-rotation.py` uses public `Conversation.arun()` and a
   real HTTP loopback secret service. The server calls supported
   `conversation.update_secrets()` to replace `TEST_TOKEN` while its original
   lookup is in flight. A custom analyzer's detail contains the synthetic new
   credential. The first lookup caches the original value under the same key;
   the new stabilization loop retries but the registry skips the replaced source
   because that key is already cached. Both the emitted audit and its persisted
   event JSON contain the replacement credential in plaintext. See
   `static-mask-rotation.json`; relevant changed lines: `agent/agent.py:1153-1160`.

   To establish attribution, `base-mask-rotation.py` was also run on PR base
   `cd17bd89d52ef209abbfca5870631d0474ca8f66`. That base already emits and persists
   the replacement credential in an ordinary `MessageEvent` after resolving the
   original value and calling `update_secrets()` with the same key. See
   `base-mask-rotation.json`. `conversation/secret_registry.py` is unchanged in
   this PR. The audit event is a new plaintext sink, but the cache flaw is older.

   A narrow audit fix would explicitly resolve replaced secret sources before
   remasking, bypassing their prior name-based cache. A general registry fix would
   track cache entries by source/version and preserve older known values for
   masking. The latter should account for the existing 60-second failed-lookup
   cache as well. All credentials used by these reproductions are synthetic.
