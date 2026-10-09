PR #5182 live review evidence, 2026-10-09 UTC

Reviewed SDK/Agent Server commit: d6a512553bf92c896dd9f2fd877f7aaa2b041fbc
Released baseline: openhands-agent-server/sdk/tools/workspace 1.53.0
Actual client: OpenHands Agent Canvas 1.25.0, commit 6e8157147936768bf358903a6341bc01e0ce1ac9
TypeScript client: 1.53.0. Automation: 1.19.0.
Live model: deepseek/deepseek-flash, actual DeepSeek API.

Start with live-results.json and static-review-notes.md. Each raw-events file is
an authenticated real server events/search response. Initial, upgraded and
cold-restored continuation results are included. No LLM responses were mocked
in those live conversations. Two released conversations were continued on the
PR; two were created on the PR; the browser was closed, the full stack restarted,
and all four conversations were restored and continued with tools again.

Run `python verify-live-evidence.py` from this directory to independently verify
the captured live transcript invariants and saved audit JSON. This checks prior
durable events stayed identical, recall before tools, continued terminal output,
and each audit event's persisted JSON payload and action linkage. The copied verifier
uses bundled persisted-audit-events instead of the original private state path.

The 653 automated Python tests and 2 client probes used controlled LLM responses;
they are separate from authentic live evidence. Exact suite logs and JUnit reports
are included. The custom secret-rotation reproductions use synthetic credentials
and real loopback HTTP. The base reproduction demonstrates inherited behavior.

QA commands used the committed control-openhands CLI. Its missing same-state
backend upgrade flags were added, tested (39 harness tests), and exercised live;
harness-upgrade.patch is included. Original tracked source was restored after QA.
The original installation and private state locations referenced by commands are
not portable setup requirements; see the repositories' onboarding/runtime guidance.

The app did not render SecurityAnalysisEvent in chat; API and persisted JSON prove
its presence. LLMSecurityAnalyzer with NeverConfirm was used in live runs. Other
providers, Docker/cloud hosting, and old Python SDK clients were not tested live.
No private configuration, browser profile, session/encryption keys, model keys,
or encrypted base_state/settings are included. All servers and browser stopped;
the container init retained an inert zombie launcher, documented in cleanup JSON.
