import { beforeEach, describe, expect, it } from "vitest";
import { useEventStore } from "#/stores/use-event-store";
import type { OHEvent } from "#/stores/use-event-store";
import { asSessionFrame } from "#/types/agent-server/session-frames";
import { isAgentServerEvent } from "#/types/agent-server/type-guards";
import { shouldRenderEvent } from "#/components/conversation-events/chat/event-content-helpers/should-render-event";
import { deriveLiveActivity } from "#/components/features/chat/typing-indicator";
import { RemoteEventsList } from "@openhands/typescript-client/events/remote-events-list";
import { HttpClient } from "@openhands/typescript-client/client/http-client";

// An additive event from SDK PR #5182, intentionally absent from Canvas's
// installed TypeScript union. Exercise runtime ingestion without editing it.
const audit = {
  kind: "SecurityAnalysisEvent", id: "audit-1", timestamp: "2026-10-09T01:00:01Z",
  source: "environment", analyzer: "LLMSecurityAnalyzer", policy: "NeverConfirm",
  risks: { "action-1": "LOW" }, details: { "action-1": { confidence: 0.95 } },
} as unknown as OHEvent;
const action = {
  kind: "ActionEvent", id: "action-1", timestamp: "2026-10-09T01:00:00Z",
  source: "agent", thought: [], thinking_blocks: [], tool_name: "terminal",
  tool_call_id: "tool-1", llm_response_id: "response-1", security_risk: "LOW",
  action: { kind: "TerminalAction", command: "printf client-contract-ok", reset: false, is_input: false, timeout: 10 },
  tool_call: { id: "tool-1", type: "function", function: { name: "terminal", arguments: "{}" } },
  summary: "Print the compatibility marker",
} as unknown as OHEvent;
const observation = {
  kind: "ObservationEvent", id: "obs-1", timestamp: "2026-10-09T01:00:02Z",
  source: "environment", action_id: "action-1", tool_name: "terminal", tool_call_id: "tool-1",
  observation: { kind: "TerminalObservation", command: "printf client-contract-ok", content: [{ type: "text", text: "client-contract-ok" }], exit_code: 0, is_error: false, timeout: false, metadata: {} },
} as unknown as OHEvent;

describe("SDK #5182 event compatibility with installed Agent Canvas", () => {
  beforeEach(() => useEventStore.getState().clearEvents());

  it("retains new audit events live and on history restoration while continuing tool display", () => {
    const frame = asSessionFrame({ type: "durable", seq: 10, event: audit });
    expect(frame?.type).toBe("durable");
    expect(isAgentServerEvent(audit)).toBe(true);

    for (const event of [action, audit]) useEventStore.getState().addEvent(event);
    expect(deriveLiveActivity(useEventStore.getState().events)).toEqual({ kind: "text", text: "Print the compatibility marker" });
    useEventStore.getState().addEvent(observation);
    const liveState = useEventStore.getState();
    expect(liveState.events.map(e => e.id)).toEqual(["action-1", "audit-1", "obs-1"]);
    expect(liveState.uiEvents.filter(shouldRenderEvent).map(e => e.id)).toEqual(["obs-1"]);
    expect(shouldRenderEvent(audit)).toBe(false);

    const saved = JSON.parse(JSON.stringify(liveState.events)) as OHEvent[];
    useEventStore.getState().clearEvents();
    // useConversationHistory reverses descending REST pages before ingestion.
    useEventStore.getState().addEvents(saved);
    expect(useEventStore.getState().events.map(e => e.id)).toEqual(["action-1", "audit-1", "obs-1"]);
    expect(useEventStore.getState().uiEvents.filter(shouldRenderEvent).map(e => e.id)).toEqual(["obs-1"]);
    useEventStore.getState().addEvent(audit); // reconnect replay must dedupe
    expect(useEventStore.getState().events).toHaveLength(3);
  });

  it("keeps unknown kinds in the published TS client's REST history, cache and iterator", async () => {
    class HistoryClient extends HttpClient {
      constructor() { super({ baseUrl: "http://127.0.0.1:9999" }); }
      async get(path: string) {
        expect(path).toBe("/api/conversations/compat/events/search");
        return { data: { items: [action, audit, observation], next_page_id: null } };
      }
    }
    const events = new RemoteEventsList(new HistoryClient(), "compat");
    await events.addEvent(audit);
    await events.addEvent(audit);
    expect(await events.length()).toBe(1);
    expect((await events.search()).items[1]).toEqual(audit);
    expect(await events.getEvents()).toEqual([action, audit, observation]);
    const iterated: unknown[] = [];
    for await (const event of events) iterated.push(event);
    expect(iterated).toEqual([action, audit, observation]);
  });
});
