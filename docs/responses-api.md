Title: OpenAI Responses API via LiteLLM (gpt-5) — Inputs, Tools, Reasoning, Stateful vs Stateless

Overview
- This doc explains how the OpenAI Responses API works when called natively through LiteLLM in this project.
- You’ll find concrete JSON examples under examples/responses_api/ and guidance on stateless/stateful usage, images, tool calls, and reasoning (including encrypted reasoning).

Install and build
1) make build
   - Uses uv to create a local .venv and install dependencies (including litellm and openai)
   - Installs pre-commit hooks

Key packages present in .venv
- litellm (responses support lives under litellm/responses/)
- openai (official types for Responses API)

How LiteLLM wires to the OpenAI Responses API
- Entrypoints: litellm/responses/main.py
  - responses(...) and aresponses(...) implement the OpenAI Responses API surface.
  - If the provider supports native Responses, LiteLLM uses BaseLLMHTTPHandler.response_api_handler to call it.
  - If a provider lacks native Responses, LiteLLM transforms to a compatible flow via litellm.responses.litellm_completion_transformation.
- Utilities: litellm/responses/utils.py
  - ResponsesAPIRequestUtils.get_optional_params_responses_api(...) maps/filters optional params per provider.
  - convert_text_format_to_text_param(...) converts a Pydantic/dict schema to the text.format payload.
  - _build/_decode_responses_api_response_id(...) encodes provider+model into response ids; previous_response_id is decoded before sending upstream.
  - ResponseAPILoggingUtils._transform_response_api_usage_to_chat_usage maps Responses usage to common Usage.
- MCP integration: aresponses_api_with_mcp(...) in main.py handles MCP tools, auto-exec if configured, and merges events into streamed output.

Core OpenAI Responses API types (from openai-python)
- Input items: response_input_item.py and response_input_content.py
  - Message: { type: "message", role: "user"|"system"|"developer", content: [ ... ] }
  - Content list items include:
    - input_text { type: "input_text", text }
    - input_image { type: "input_image", image_url | file_id, detail }
    - input_file, input_audio
- Tools: tool.py
  - Variants include function, file_search, computer, web_search, mcp, code_interpreter, image_generation, local_shell, custom_tool (and preview variants)
  - Function tool calls are ResponseFunctionToolCall objects; follow-ups use function_call_output items
- Reasoning: shared/reasoning.py and responses/response_reasoning_item.py
  - request.reasoning: { effort: minimal|low|medium|high, summary: auto|concise|detailed }
  - response contains reasoning items: { type: "reasoning", summary: [...], content?: [...], encrypted_content?: string }
  - To receive encrypted reasoning text, include: ["reasoning.encrypted_content"]

Stateless vs. stateful
- Stateless: You send full context in input each call. No previous_response_id.
- Stateful: Set store: true and reuse previous_response_id from the prior response. LiteLLM encodes provider+model into ids; it decodes before hitting OpenAI upstream but you pass the encoded id back in subsequent calls.

Examples in this repo (JSON)
1) System + User with images (stateless)
   - examples/responses_api/01_system_user_images.json
2) Tool call (function); then follow-up with tool output
   - examples/responses_api/02_tool_call_and_output.json
   - examples/responses_api/02b_tool_call_followup_with_output_item.json
3) Reasoning (stateless)
   - Plain reasoning (no encrypted content): examples/responses_api/03_stateless_reasoning_plain.json
   - Encrypted reasoning included: examples/responses_api/03b_stateless_reasoning_encrypted.json
4) Reasoning (stateful)
   - Plain: examples/responses_api/04_stateful_reasoning_plain.json
   - Encrypted reasoning included: examples/responses_api/04b_stateful_reasoning_encrypted.json


5) Reasoning response snapshots (shape returned by API)
   - examples/responses_api/05_reasoning_response_examples.json

Notes on correctness
- Content discriminator fields must match the OpenAI types (e.g., input_text, input_image).
- For function call follow-up, use type: "function_call_output" with the prior call_id and an output that MUST be a JSON string (per OpenAI types).
- To request encrypted reasoning, add "reasoning.encrypted_content" to include. The API then returns reasoning items with encrypted_content.
- previous_response_id should be the id returned from the prior Responses call. When using LiteLLM, that id includes encoded provider/model info; return it as-is in the next call.

Minimal Python usage sketch
"""
from openai import OpenAI

client = OpenAI()
resp = client.responses.create(
    model="gpt-5",
    input=[
        {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Hello"}
        ]},
    ],
    reasoning={"effort": "low", "summary": "concise"},
    include=["reasoning.encrypted_content"],
)
print(resp.id, resp.output_text)
"""

Troubleshooting
- VIRTUAL_ENV mismatch: use uv run commands (e.g., uv run pytest, uv run python) or activate the project .venv explicitly. LiteLLM/OpenAI should import from /agent-sdk/.venv.
