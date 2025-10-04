# Model Info and Capabilities Initialization

Problem
- `_init_model_info_and_caps()` mixes network I/O, name fallback heuristics, capability derivation, and policy (e.g., Claude 64k override). This reduces readability, slows object construction, and complicates testing.

Goals
- Keep initialization fast and predictable.
- Isolate provider-specific probing and capability derivation.
- Make Anthropic-specific rules easy to find and change.
- Avoid repeated network calls for the same model/base_url.

Proposed Structure
1) Resolver with cache
- `resolve_model_info(model: str, base_url: str | None, api_key: SecretStr | None) -> dict | None`
- Tries in order:
  1. If model.startswith("openrouter"): litellm.get_model_info(model)
  2. If model.startswith("litellm_proxy/"): fetch from `{base_url}/v1/model/info`, find matching `model_name`, return `model_info`
  3. Fallback: litellm.get_model_info(model.split(":")[0])
  4. Fallback: litellm.get_model_info(model.split("/")[-1])
- Wrap in an LRU cache keyed by `(provider_tag, normalized_model, base_url)`.
- Apply a short timeout on httpx.get and handle errors gracefully.

2) Pure derivations
- `derive_token_limits(model: str, model_info: dict | None, existing_max_in: int | None, existing_max_out: int | None) -> tuple[int | None, int | None]`
  - Respect existing values when already provided by the user.
  - If Anthropic family and no explicit max_output_tokens, apply a practical cap (e.g., 64k) via a shared Anthropic helper.
  - Use model_info["max_input_tokens"] / ["max_output_tokens"] / ["max_tokens"] as fallbacks.
- `compute_function_calling_active(native_override: bool | None, features) -> bool`
  - If user sets `native_tool_calling` use it; otherwise features.supports_function_calling.

3) Anthropic helpers (co-located)
- `anthropic/cache.py` → apply_prompt_caching(messages)
- `anthropic/tokens.py` → claude_practical_max_output(model) -> int | None
- `anthropic/reasoning.py` → headers and interleaved-thinking beta logic

4) Initialization flow inside LLM
- During validation: set telemetry/metrics/tokenizer.
- Call `self._initialize_model_profile()` (small):
  - `self._model_info = resolve_model_info(self.model, self.base_url, self.api_key)`
  - `(self.max_input_tokens, self.max_output_tokens) = derive_token_limits(...)`
  - `self._function_calling_active = compute_function_calling_active(self.native_tool_calling, get_features(self.model))`
- Optionally lazy: if we defer resolver to first use, ensure `clone()` carries resolved profile forward to avoid surprises.

Base URL Scheme for Local/Proxy
- If `base_url` lacks a scheme, default to `http://` for localhost/intranet friendliness, with a clear debug log: "No scheme in base_url, defaulting to http://".
- Optionally add `force_https: bool = False` flag to override behavior when desired.

Why This Works
- Readability: every function does one thing; the big method is gone.
- Testability: resolver can be mocked, derivations are pure and easy to unit test.
- Performance: model info cached across instances; no repeated network calls.
- Extensibility: Anthropic rules live together; adding providers won’t bloat LLM.

Open Questions
- Should we always default to `http://` when no scheme, or default to `https://` and special-case `localhost`/`127.0.0.1`? Defaulting to `http://` is convenient for local dev; we can add a security note in docs.
- How large should the resolver LRU cache be? Likely tiny (e.g., 64 entries) since models are a short list.
