# Examples

How to run:

- uv run python -m examples.echo_offline
- uv run python -m examples.tools_quickstart
- uv run python -m examples.persistence_local
- LITELLM_API_KEY=... uv run python -m examples.hello_world

Notes:
- hello_world tries API keys in this order: LITELLM_API_KEY (LiteLLM proxy), GEMINI_API_KEY (Gemini), OPENAI_API_KEY (OpenAI). It prefers the LiteLLM proxy if LITELLM_API_KEY is set.
- Prefer module-style invocation (-m) so imports resolve correctly with repo root on sys.path.
