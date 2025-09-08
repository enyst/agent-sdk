import os

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Agent,
    Conversation,
    EventType,
    Message,
    TextContent,
    Tool,
    get_logger,
)
from openhands.sdk.conversation import ConversationVisualizer


logger = get_logger(__name__)


def main() -> None:
    # One prompt for all models
    task = os.getenv(
        "REASONING_TASK",
        (
            "Solve this carefully and show your internal reasoning as available: "
            "78*964 + 17. Respond with the final integer answer."
        ),
    )

    # Base URLs and API keys
    proxy_base = os.getenv("LITELLM_BASE_URL", "https://llm-proxy.eval.all-hands.dev")
    # LITELLM_API_KEY read by proxy; set in env for proxy-side auth

    deepseek_base = "https://api.deepseek.com"

    # Default models to probe. DeepSeek is called direct; others via proxy by default.
    default_models: list[dict[str, str | None]] = [
        {
            "label": "deepseek-direct/reasoner",
            "model": "deepseek/deepseek-reasoner",
            "base_url": deepseek_base,
            "api_key_env": "DEEPSEEK_KEY",
        },
        {
            "label": "proxy/deepseek-reasoner",
            "model": "litellm_proxy/deepseek/deepseek-reasoner",
            "base_url": proxy_base,
            "api_key_env": "LITELLM_API_KEY",
        },
        {
            "label": "proxy/openai-o3",
            "model": "litellm_proxy/openai/o3-2025-04-16",
            "base_url": proxy_base,
            "api_key_env": "LITELLM_API_KEY",
        },
        {
            "label": "proxy/gemini-2.5-pro",
            "model": "litellm_proxy/gemini/gemini-2.5-pro",
            "base_url": proxy_base,
            "api_key_env": "LITELLM_API_KEY",
        },
    ]

    # Allow overriding the model set via env:
    # - REASONING_MODEL=single_model
    # - REASONING_MODELS=model1,model2,model3
    models_env = os.getenv("REASONING_MODELS")
    model_env = os.getenv("REASONING_MODEL")

    def infer_entry(m: str) -> dict[str, str | None]:
        # DeepSeek: direct; everything else through proxy
        if m.startswith("deepseek/"):
            return {
                "label": f"deepseek-direct/{m.split('/')[-1]}",
                "model": m,
                "base_url": deepseek_base,
                "api_key_env": "DEEPSEEK_KEY",
            }
        # Otherwise, proxy
        return {
            "label": f"proxy/{m}",
            "model": m if m.startswith("litellm_proxy/") else f"litellm_proxy/{m}",
            "base_url": proxy_base,
            "api_key_env": "LITELLM_API_KEY",
        }

    if models_env:
        model_ids = [s.strip() for s in models_env.split(",") if s.strip()]
        model_entries = [infer_entry(m) for m in model_ids]
    elif model_env:
        model_entries = [infer_entry(model_env.strip())]
    else:
        model_entries = default_models

    print("\n=== Reasoning probe: starting ===\n")
    results: list[dict[str, str]] = []

    for entry in model_entries:
        label = str(entry["label"])  # type: ignore[index]
        model = str(entry["model"])  # type: ignore[index]
        base_url = str(entry["base_url"])  # type: ignore[index]
        api_key_env = str(entry["api_key_env"])  # type: ignore[index]

        # Resolve API key
        api_key_val = os.getenv(api_key_env)
        if not api_key_val:
            print(f"[skip] {label}: missing API key env {api_key_env}")
            results.append(
                {"model": model, "label": label, "result": "SKIPPED: no key"}
            )
            continue

        print(f"\n--- Testing {label} ({model}) ---\n")

        # Build LLM with log_completions enabled
        llm = LLM(
            model=model,
            base_url=base_url,
            api_key=SecretStr(api_key_val),
            log_completions=True,
        )

        # No external tools required to view reasoning. Built-ins are auto-added.
        tools: list[Tool] = []

        # Agent and visualizer to display tokens and content nicely
        agent = Agent(llm=llm, tools=tools)
        visualizer = ConversationVisualizer()

        saw_reasoning = False

        def on_event(event: EventType) -> None:
            nonlocal saw_reasoning
            visualizer.on_event(event)

            rc = getattr(event, "reasoning_content", None)
            if rc:
                saw_reasoning = True
                print("\n==== reasoning_content (from event) ====\n")
                print(rc)
                print("=======================================\n")

            if hasattr(event, "llm_message"):
                llm_msg = getattr(event, "llm_message")
                msg_rc = getattr(llm_msg, "reasoning_content", None)
                if msg_rc:
                    saw_reasoning = True
                    print("\n==== reasoning_content (from llm_message) ====\n")
                    print(msg_rc)
                    print("============================================\n")

        conversation = Conversation(agent=agent, callbacks=[on_event])

        try:
            conversation.send_message(
                message=Message(role="user", content=[TextContent(text=task)])
            )
            conversation.run()
            results.append(
                {
                    "model": model,
                    "label": label,
                    "result": "YES" if saw_reasoning else "NO",
                }
            )
        except Exception as e:  # noqa: BLE001
            print(f"[error] {label}: {e}")
            results.append(
                {
                    "model": model,
                    "label": label,
                    "result": f"ERROR: {type(e).__name__}: {e}",
                }
            )

    print("\n=== Reasoning probe: summary ===")
    for r in results:
        print(f"- {r['label']} ({r['model']}): {r['result']}")
    print("=== End ===\n")


if __name__ == "__main__":
    main()
