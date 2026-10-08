# Independently activated launch conformance bundle

This is executable groundwork for protected admission. Merging this directory
does **not** activate admission or change any GitHub repository rule. The
`Conformance bundle proposal` workflow qualifies a proposed bundle; its result is
advisory and must not be the protected admission signal.

## Initial contract

`agent-server-launch-v1` has one required scenario, `LAUNCH-ARCH-001`: only the
canonical launch pipeline constructs or changes a launch agent in Agent Server
source. `verify.py` is an independently releasable snapshot of the existing
`tests/agent_server/test_launch_architecture.py` predicate at the revision named
in `manifest.json`. It preserves those syntax rules and their scope. It is not
a second definition that automatically tracks implementation tests: changing
either source proposes a policy amendment, and requires separate activation to
change the active snapshot.

This check recognizes the existing named call and request-assignment patterns.
It does not establish dynamic-construction safety, resolve arbitrary aliases, or
verify REST/WS behavior. There are no consumer versions, baselines, exceptions,
pytest plugins, or third-party Python dependencies in this initial bundle.
Later contracts require qualified bundle releases rather than silently extending
or weakening a current active release.

## Independent evaluator entry point

An independent controller fetches the exact candidate or merge commit into a
fresh **bare** Git repository. It does not check out or run candidate code. Before
creating the uncompressed source archive, it overrides Git export attributes in
the bare repository's `info/attributes` with `* -export-ignore -export-subst`.
Otherwise candidate `.gitattributes` could hide source from `git archive` or alter
its contents. The controller verifies the fetched SHA, creates the archive,
computes its digest, and retains this provenance independently of the candidate.

The controller obtains `conformance/` from a separately approved full commit SHA,
then calls it with identities from that trusted collection step:

```sh
python -I -S /approved-bundle/conformance/verify.py \
  --archive /inert-input/candidate.tar \
  --revision "$EXACT_CANDIDATE_OR_MERGE_SHA" \
  --artifact-sha256 "$CONTROLLER_COLLECTED_ARCHIVE_SHA256" \
  --approved-bundle-sha256 "$INDEPENDENTLY_APPROVED_BUNDLE_SHA256" \
  --output /trusted-output/conformance-evidence.json
```

Exit codes are `0` (pass), `1` (observed contract failure), and `2` (blocked).
A bundle approval mismatch produces no new evidence file. Controllers must use
fresh output paths and never accept stale evidence after any nonzero exit.

The runner verifies the digest of `manifest.json` and `verify.py`, the source
artifact digest, and the `git archive` commit comment. It reads source only as
bounded regular tar members and parses the Agent Server Python AST. Links and
special members anywhere in the scanned package are blocked before file-extension
selection, including directory symlinks that could redirect imports outside the
scanned source. Ordinary directories are allowed; links are never followed. It never
extracts candidate paths or links, runs hooks, imports candidate packages or
`conftest.py`, invokes pytest, installs candidate dependencies, or uses candidate
selection/configuration. Archives are limited to 128 MiB and 20,000 members,
individual source files to 2 MiB, and parsed source to 32 MiB. Run the verifier
with a controller timeout and memory limit as well: parser resource isolation
still matters for hostile inputs.

The archive's commit comment alone is **not provenance authentication**. Anyone
can forge a tar comment. The controller must collect the archive from the expected
Git commit as above, protect its input/output files from concurrent writers, and
authenticate the evaluator's output. It must not accept a candidate-supplied
archive digest or report as proof of correctness. This source archive is the
tested artifact; it is not an attestation of a built server image.

## Evidence contract

Evidence schema version 1 contains:

| Field | Meaning |
| --- | --- |
| `subject.revision` | Exact fetched candidate or merge commit SHA |
| `subject.artifact_sha256` | Controller-collected uncompressed source archive digest |
| `subject.artifact_kind` | `git-source-tar` |
| `bundle.id`, `bundle.sha256` | Independently approved policy identity and content digest |
| `consumer_versions` | Empty for this structural contract |
| `scenarios` | Ordered, exact required roster, with explicit `pass`, `fail`, or `blocked` |
| `scenarios[].details` | Parsed file paths and observed violations, or the blocking error |
| `verdict` | `pass` only when the required scenario executed and passed |

`validate_evidence()` rejects missing, empty, duplicate, unexpected, skipped, or
blocked scenario evidence, mismatched identities, empty file coverage, and a
passing verdict containing violations. It is a consistency check, **not a
signature verifier**. A publisher must use evidence generated by an authenticated
execution of the approved verifier; an adversary could otherwise forge all of the
JSON fields consistently.

## Qualification

Run the qualification controls without project dependencies or pytest:

```sh
python -I -S tests/agent_server/test_conformance_bundle.py
```

The controls exercise a valid archive, every existing prohibited construction
pattern, missing/invalid/symlink source, wrong revision/artifact, incomplete or
tampered evidence, candidate-owned runner/plugin/config files, and unapproved or
tampered bundle activation. A real Git archive containing a nested package symlink
to unscanned source is blocked, as are non-Python hard links and special members.
Proposal CI also evaluates the actual candidate
source archive and retains the complete scenario report. The initial policy's
current source passes; a deliberate non-launch `Agent()` construction fails.

## Activation owned outside ordinary implementation PRs

The activation authority must complete these deployment steps before describing
this as enforced admission:

1. Qualify a specific bundle commit. Compute its content digest with
   `python -I -S conformance/verify.py --print-bundle-digest`. Record both values
   in a controller configuration whose write/activation authority ordinary
   implementation agents do not have. Never resolve the active policy from
   mutable `main`, a candidate input, a mutable tag, or repository variables that
   implementation agents can update. Merely approving a source PR is not bundle
   activation; a two-PR weakening sequence must still use the old active bundle.
2. Deploy `independent-workflow.yml.example` to that separately governed
   controller repository, replace the approval placeholders there, and control
   workflow, action, Python runtime, and runner updates under the same authority.
   It is an inert example here, and collects evidence only. Pin the complete
   evaluator environment for the deployment's assurance level; this example uses
   hosted Python 3.13 and GitHub-authored action versions, so it does not itself
   promise a bit-for-bit immutable hosted runtime.
3. Connect a dedicated GitHub App or independently governed result publisher.
   Keep its publication credential outside all candidate execution environments.
   The publisher authenticates the controller job and checks its exact revision,
   artifact, active bundle, complete evidence, and exit result before publishing
   success. Missing runs, missing output, timeout, fail, or blocked must produce
   failure/pending admission, never success/neutral/skipped. No App, credential,
   publisher, or external activation is created by this PR.
4. Require the exact admission check name **and the designated App identity** in
   branch protection or an enforced ruleset. Restrict bypass and activation
   authority according to the repository's unattended-merge policy. A check name
   or PR-editable `GITHUB_TOKEN` workflow is insufficient. An organization-required
   workflow from a separately governed source repository is an alternative where
   the organization's plan and rules support it; its source and configuration
   must still be controlled independently.
5. Schedule evaluation for the actual revision GitHub will admit: refreshed test
   merge commits or merge-group commits when those mechanisms are used. Invalidate
   old results when PR head or merge base changes. The dispatch-only example is
   not a PR/merge-queue scheduler and does not implement this freshness policy.
   Before activation, demonstrate that an ordinary implementation agent cannot
   change the active digest, submit a accepted self-authored result, or bypass the
   expected publisher identity. Re-run the weakening-PR then violation-PR control
   against the deployed boundary.

GitHub documents [expected App identities and organization-required workflows](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
It also documents [skipped jobs being successful for required-check purposes](https://docs.github.com/en/pull-requests/reference/status-checks)
and [merge-group triggers and expected-App failures](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
These deployment requirements cannot be enforced by changing repository source
alone. This PR neither modifies those settings nor claims they are already active.
