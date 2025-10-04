# LLM Refactor Plan: Simplicity, Streaming/Async, Stateful Responses

Context
- The current LLM class (openhands/sdk/llm/llm.py) has grown large and mixes several concerns: config, feature detection, message formatting, tool strategy (native vs mock), provider option selection, transport calls, retry+telemetry, and post-processing.
- Today: sync-only, non-streaming for both Chat Completions and OpenAI Responses API. No stateful Responses API.
- Goals: improve readability, keep public API stable, and create clear extension points for stateful Responses API, streaming, async, and on‑the‑fly LLM switching.

Design Principles
- Thin Facade: Keep LLM as a small, readable entry point that delegates.
- Small Modules, One Responsibility: favor 50–150 LOC modules that do one thing well.
- Composition over Inheritance: avoid complex adapter hierarchies; use simple functions/classes.
- Backward Compatible: keep LLM.completion and LLM.responses behavior intact.

Proposed Architecture
1) Formatters (pure):
   - formatters/chat.py
     - prepare_chat_messages(llm, messages) -> list[dict]
       - Applies Anthropic cache markers only when relevant.
       - Applies vision/function-calling flags.
       - Uses Message.to_llm_dict().
   - formatters/responses.py
     - prepare_responses_input(llm, messages) -> (instructions: str | None, input_items: list[dict])
       - Vision only; no cache flags.
       - Uses Message.to_responses_value().

2) Tools:
   - tools/prepare.py
     - build_chat_tools(tools) -> list[ChatCompletionToolParam]
     - build_responses_tools(tools) -> list[Responses ToolParam]
   - tools/strategy.py
     - choose_tool_strategy(llm, chat_tools) -> strategy
       - NativeToolStrategy: send tools natively (when supported)
       - MockToolStrategy: pre/post transforms for prompt-mocked tool calls

3) Options (rename normalize_* → select_options_*):
   - options/chat_options.py
     - select_chat_options(llm, user_kwargs, has_tools: bool) -> dict
   - options/responses_options.py
     - select_responses_options(llm, user_kwargs, include, store) -> dict

2.1) Tool Strategy (Chat path)

- Purpose: Decide once per request whether to send tools natively or to prompt-mock tool calls when function calling is unavailable.
- Interface:
  - has_native_tools: bool
  - pre_request(messages, chat_tools, kwargs) -> (messages, kwargs)
  - post_response(resp, nonfncall_msgs, chat_tools) -> resp
- Strategies:
  - NativeToolStrategy: send tools as-is; no message transforms.
  - MockToolStrategy: delegate to NonNativeToolCallingMixin for pre/post transforms.
- Selector:
  - choose_tool_strategy(llm, chat_tools):
    - if no tools → NativeToolStrategy(has_tools=False)
    - elif llm.is_function_calling_active() → NativeToolStrategy(has_tools=True)
    - else → MockToolStrategy(llm)

Code example

```
from typing import Protocol, Tuple
from litellm import ChatCompletionToolParam
from litellm.types.utils import ModelResponse

class ToolStrategy(Protocol):
    has_native_tools: bool
    def pre_request(self, messages: list[dict], chat_tools: list[ChatCompletionToolParam] | None, kwargs: dict) -> Tuple[list[dict], dict]: ...
    def post_response(self, resp: ModelResponse, nonfncall_msgs: list[dict], chat_tools: list[ChatCompletionToolParam] | None) -> ModelResponse: ...

class NativeToolStrategy:
    def __init__(self, has_tools: bool):
        self.has_native_tools = has_tools
    def pre_request(self, messages, chat_tools, kwargs):
        return messages, kwargs
    def post_response(self, resp, nonfncall_msgs, chat_tools):
        return resp

class MockToolStrategy:
    def __init__(self, llm):
        self.llm = llm
        self.has_native_tools = False
    def pre_request(self, messages, chat_tools, kwargs):
        assert chat_tools
        return self.llm.pre_request_prompt_mock(messages, chat_tools, kwargs)
    def post_response(self, resp, nonfncall_msgs, chat_tools):
        assert chat_tools
        return self.llm.post_response_prompt_mock(resp, nonfncall_msgs, chat_tools)

def choose_tool_strategy(llm, chat_tools: list[ChatCompletionToolParam] | None) -> ToolStrategy:
    if not chat_tools:
        return NativeToolStrategy(has_tools=False)
    if llm.is_function_calling_active():
        return NativeToolStrategy(has_tools=True)
    return MockToolStrategy(llm)
```

4) Transport (litellm boundary):
   - transport/chat.py
     - transport_chat_sync(model, messages, options) -> ModelResponse
     - (future) transport_chat_stream/async
   - transport/responses.py
     - transport_responses_sync(model, instructions, input_items, tools, options) -> ResponsesAPIResponse
     - (future) transport_responses_stream/async
   - Keep litellm.modify_params guard centralized here.

5) Invocation (retry + telemetry):
   - invocation/chat_invoker.py
     - call_sync(ctx) -> LLMResponse
     - (future) call_stream/call_async/call_async_stream
   - invocation/responses_invoker.py
     - call_sync(ctx) -> LLMResponse

6) Caching (Anthropic-only flags today):
   - caching/anthropic_cache.py
     - apply_prompt_caching(messages) -> None

7) Streaming/Async (future):
   - streaming/events.py: {TextDelta, ToolCallDelta, ReasoningDelta, UsageDelta, Error, End}
   - streaming/aggregator.py: fold deltas into final Message/Usage

Public LLM Surface (unchanged now, future-ready)
- completion(...)
- responses(...)
- (future) completion_stream(...), responses_stream(...)
- (future) acompletion(...), aresponses(...), acompletion_stream(...), aresponses_stream(...)

On‑the‑fly LLM switching
- Prefer clone-and-swap: LLM.clone(**overrides) returns a new configured instance; Agent swaps atomically.
- Semantics: if model/base_url are unchanged, the clone may reuse the resolved model profile (copy). If either differs, the clone invalidates and re‑resolves its model profile.
- LRU cache keyed by (normalized_model, base_url) speeds up re‑resolution across instances without affecting correctness.
- Optionally use a lightweight LLMHandle wrapper that the Agent holds; handle.set(new_llm) hot-swaps internally.

Stateful Responses API (future)
- responses_invoker + responses transport accept store=True and session/thread identifiers from select_responses_options.
- No changes required in LLM facade beyond plumbing.

Refactor of _init_model_info_and_caps()
Current behavior (mixed concerns): performs provider-specific model_info fetches (including network), sets token limits and function-calling capability. This couples init-time side effects, network I/O, and policy.

We will:
- Extract a resolver: resolve_model_info(model, base_url, api_key) with an LRU cache. Supports openrouter, litellm_proxy, and basename fallbacks.
- Extract pure derivations:
  - derive_token_limits(model, model_info)
  - compute_function_calling_active(native_override, features)
- Consider lazy loading guarded by ensure_model_info_loaded(), but be mindful of clone(): clone should carry over resolved model profile so we avoid late surprises.

Anthropic-specific logic
- Group Anthropic-specific concerns behind a small module anthropic/: 
  - anthropic/cache.py: apply_prompt_caching(...)
  - anthropic/tokens.py: optional token/output caps overrides (e.g., Claude practical 64k)
  - anthropic/reasoning.py: extended thinking headers, interleaved-thinking beta, etc.
- Used only on the Chat Completions path: call these helpers when get_features(model).is_anthropic is true. Responses path never uses Anthropic helpers (Responses applies only to select OpenAI models).

Base URL scheme for local/proxy
- If base_url has no scheme, default to http:// to support localhost/intranet usage, and log a concise debug message.

Short example: Anthropic usage in llm.completion()

```
from openhands.sdk.llm.model_features import get_features
from openhands.sdk.llm.anthropic.cache import apply_prompt_caching

# inside LLM.completion(...)
feats = get_features(self.model)

ser_msgs = [m.to_chat_dict() for m in messages]

if feats.is_anthropic:
    apply_prompt_caching(ser_msgs)

chat_tools = build_chat_tools(kwargs.get("tools"))
strategy = choose_tool_strategy(self, chat_tools)
ser_msgs, kwargs = strategy.pre_request(ser_msgs, chat_tools, kwargs)
has_tools = strategy.has_native_tools

# Provider-specific option decisions happen inside this function
options = select_chat_options(self, kwargs, has_tools)

raw = transport_chat_sync(self.model, ser_msgs, options)
raw = strategy.post_response(raw, ser_msgs, chat_tools)
return build_llm_response(raw)
```

select_chat_options injects Anthropic specifics internally:

```
from openhands.sdk.llm.model_features import get_features
from openhands.sdk.llm.anthropic.reasoning import extended_thinking_headers
from openhands.sdk.llm.anthropic.tokens import claude_practical_max_output

def select_chat_options(llm, user_kwargs, has_tools):
    opts = coerce_and_default(user_kwargs)
    feats = get_features(llm.model)
    if feats.is_anthropic:
        opts.setdefault("extra_headers", {}).update(extended_thinking_headers(llm))
        if opts.get("max_output_tokens") is None:
            cap = claude_practical_max_output(llm.model)
            if cap is not None:
                opts["max_output_tokens"] = cap
    return opts
```

Migration Plan (incremental)
1) Extract prepare_* and select_options_* helpers (rename from normalize_*). No behavior change.
2) Extract chat/responses transport and centralize litellm.modify_params guard.
3) Introduce ToolStrategy (native/mock) using existing mixin logic.
4) Add Chat/Responses invokers (retry + telemetry) and delegate from LLM.
5) Introduce model_info resolver + derivations; replace _init_model_info_and_caps with a small initializer that calls the resolver and derivations.
6) Add streaming/async in invokers.

Readability Wins
- Each module is short, with purpose-revealing names.
- LLM methods read as: prepare → select options → transport → postprocess → wrap.
- Provider quirks (Anthropic) are grouped and opt-in by features.
