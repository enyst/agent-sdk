import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
STATE = ROOT / "persisted-audit-events"
CASES = {
    "release-plain": ("4f0a9b02-da2a-40e1-9666-a3c880ddb15f", False, "cedar-5182-blue", "38", "17", "upgraded-plain"),
    "release-analyzer": ("e5e42175-88c9-4151-9447-115bd9f619a3", True, "amber-5182-otter", "8.0", "20.0", "upgraded-analyzer"),
    "pr-plain": ("ea6492a1-7911-44f4-ae38-e227a64b0e99", False, "violet-5182-lark", "720", "120", "pr-plain"),
    "pr-analyzer": ("127bc200-3e89-4f1d-8e77-f5312ce575dc", True, "silver-5182-badger", "21", "13", "pr-analyzer"),
}


def read_events(name):
    data = json.loads((ROOT / f"{name}-raw-events.json").read_text())
    assert data["ok"] and data["status"] == 200, name
    assert not data["body"].get("next_page_id"), name
    return data["body"]["items"]


results = []
for label, (conversation_id, analyzer, marker, old_result, new_result, preclose) in CASES.items():
    before = read_events(preclose)
    after = read_events(f"restored-{label}")
    initial = read_events(label)
    prior = {e["id"]: e for e in before}
    assert all(prior.get(e["id"]) == e for e in initial if e["kind"] != "ConversationStateUpdateEvent"), label
    assert any(e["kind"] == "ObservationEvent" and e.get("tool_name") == "terminal" and old_result in json.dumps(e["observation"]) for e in initial), label
    durable = {e["id"]: e for e in before if e["kind"] != "ConversationStateUpdateEvent"}
    restored = {e["id"]: e for e in after}
    assert all(restored.get(event_id) == event for event_id, event in durable.items()), label
    assert len(restored) == len(after), label
    actions = {e["id"]: e for e in after if e["kind"] == "ActionEvent"}
    audits = [e for e in after if e["kind"] == "SecurityAnalysisEvent"]
    assert bool(audits) == analyzer, label
    persisted_paths = list((STATE / conversation_id.replace("-", "")).rglob("events/*.json"))
    persisted_events = {json.loads(p.read_text())["id"]: json.loads(p.read_text()) for p in persisted_paths}
    for event in audits:
        assert event["analyzer"] == "LLMSecurityAnalyzer", label
        assert event["policy"] == "NeverConfirm", label
        assert event["source"] == "environment", label
        assert event["risks"] and set(event["risks"]) <= actions.keys(), label
        assert persisted_events.get(event["id"]) == event, label
        for action_id in event["risks"]:
            assert actions[action_id]["timestamp"] < event["timestamp"], label
            observations = [e for e in after if e["kind"] == "ObservationEvent" and e.get("action_id") == action_id]
            assert observations and all(event["timestamp"] < e["timestamp"] for e in observations), label
    user = [e for e in after if e["kind"] == "MessageEvent" and e["source"] == "user"][-1]
    followup = [e for e in after if e["timestamp"] > user["timestamp"]]
    terminal_actions = [e for e in followup if e["kind"] == "ActionEvent" and e.get("tool_name") == "terminal"]
    assert terminal_actions, label
    first_thought = " ".join(item.get("text", "") for item in terminal_actions[0].get("thought", []))
    assert marker in first_thought and old_result in first_thought, (label, first_thought)
    terminal_observations = [e for e in followup if e["kind"] == "ObservationEvent" and e.get("tool_name") == "terminal"]
    assert any(new_result in json.dumps(e["observation"]) for e in terminal_observations), label
    finish = [e for e in followup if e["kind"] == "ActionEvent" and e.get("tool_name") == "finish"]
    replies = [e for e in followup if e["kind"] == "MessageEvent" and e["source"] == "agent"]
    status = json.loads((ROOT / f"restored-{label}-continue.json").read_text())["status"]
    assert status == "finished" and (finish or replies), label
    results.append({
        "case": label,
        "conversation_id": conversation_id,
        "analyzer": analyzer,
        "initial_tools_completed": True,
        "released_events_preserved_across_upgrade": label.startswith("release-"),
        "restored_events_equal": True,
        "context_marker": marker,
        "previous_result": old_result,
        "new_terminal_result": new_result,
        "recalled_before_tools": True,
        "audit_events_before_restart": sum(e["kind"] == "SecurityAnalysisEvent" for e in before),
        "audit_events_after_continuation": len(audits),
        "audit_ids_link_to_actions": True,
        "audit_events_persisted": True,
        "event_counts": dict(Counter(e["kind"] for e in after)),
    })

print(json.dumps({"pr_head": "d6a512553bf92c896dd9f2fd877f7aaa2b041fbc", "released_server": "1.53.0", "model": "deepseek/deepseek-flash", "all_passed": True, "cases": results}, indent=2))
