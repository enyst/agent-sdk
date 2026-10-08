# Add independently activated launch conformance bundle groundwork

## Problem

Implementation agents can change a repository's tests and then submit code that
violates the former rule. Running the current candidate's test definitions does
not preserve an architectural decision across that two-PR sequence. A successful
check name also does not establish who evaluated the candidate or which required
scenarios ran.

## Agreed first slice

Create a bounded, independently releasable snapshot of the existing Agent Server
launch-construction predicate. Its evaluator must inspect source as inert data,
identify the exact candidate and approved policy, and emit complete pass, fail,
or blocked evidence. Repository CI may qualify proposed bundles, but source
merges must not implicitly activate protected admission.

This implements the protected-bundle groundwork in the
[architecture enforcement strategy](https://enyst.github.io/arch/openhands-sdk-architecture-testing.html).

## Acceptance criteria

- A fixed manifest declares the initial required launch scenario and the exact
  existing syntax policy being preserved.
- A stdlib-only evaluator reads a bounded Git source archive without importing
  or executing candidate code, dependencies, pytest plugins, or hooks.
- Evidence binds the expected source revision, controller-collected artifact
  digest, and independently approved bundle digest. Missing, incomplete,
  tampered, or unavailable verification cannot produce a successful verdict.
- Positive and deliberate negative controls qualify the policy and collection
  boundary, including candidate export attributes and symlinked source.
- Advisory proposal CI and an inactive controller example exercise the actual
  entry point. Permanent documentation specifies the separate activation,
  publisher identity, repository protection, and merge freshness responsibilities.
- The implementation clearly states that merging this groundwork does not deploy
  a protected check or demonstrate dynamic construction or REST/WS conformance.

## Outside this issue

Creating or granting GitHub Apps, changing rulesets or bypass authority, deploying
the independent controller, or certifying a running server image. Those are owner
activation tasks after the bundle is qualified and selected.
