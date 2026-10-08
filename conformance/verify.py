"""Evaluate inert candidate source with an independently activated policy snapshot."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


BUNDLE_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = "openhands-agent-server/openhands/agent_server/"
LAUNCH_MODULE = PACKAGE_ROOT + "launch.py"
SCENARIO = "LAUNCH-ARCH-001"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 20000
MAX_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_digest() -> str:
    result = hashlib.sha256()
    for name in ("manifest.json", "verify.py"):
        content = (BUNDLE_ROOT / name).read_bytes()
        result.update(name.encode() + b"\0" + str(len(content)).encode() + b"\0")
        result.update(content)
    return result.hexdigest()


def load_manifest(expected_digest: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise ValueError("an independently approved bundle SHA-256 is required")
    if bundle_digest() != expected_digest:
        raise ValueError("bundle differs from the independently approved digest")
    manifest = json.loads((BUNDLE_ROOT / "manifest.json").read_text())
    if (
        manifest.get("schema_version") != 1
        or manifest.get("required_scenarios") != [SCENARIO]
        or not isinstance(manifest.get("id"), str)
        or manifest.get("consumer_versions") != {}
    ):
        raise ValueError("unsupported or empty scenario roster")
    return manifest


def _name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_request(node: ast.expr) -> bool:
    return "request" in ast.unparse(node).lower()


def _updates_agent(call: ast.Call) -> bool:
    return any(
        keyword.arg == "update"
        and isinstance(keyword.value, ast.Dict)
        and any(
            isinstance(key, ast.Constant) and key.value == "agent"
            for key in keyword.value.keys
        )
        for keyword in call.keywords
    )


def launch_violations(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _name(node.func)
            if name in {"create_agent", "create_agent_from_settings"}:
                found.append((node.lineno, f"{name}() builds an agent"))
            elif name in {"Agent", "ACPAgent"}:
                found.append((node.lineno, f"{name}(...) constructs an agent"))
            elif name == "LaunchedAgent":
                found.append((node.lineno, "LaunchedAgent is built by finalize()"))
            elif name == "create_request" and not any(
                keyword.arg in {"agent", "agent_settings", "agent_profile_id"}
                for keyword in node.keywords
            ):
                found.append(
                    (node.lineno, "create_request() without a source builds an agent")
                )
            elif (
                name == "model_copy"
                and isinstance(node.func, ast.Attribute)
                and _is_request(node.func.value)
                and _updates_agent(node)
            ):
                found.append((node.lineno, "a start request's agent is replaced"))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "agent"
                    and _is_request(target.value)
                ):
                    found.append((node.lineno, "a start request's agent is assigned"))
    return found


def scan_archive(path: Path, revision: str, artifact_digest: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("expected revision must be an exact 40-character commit SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", artifact_digest):
        raise ValueError("expected source archive SHA-256 is required")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("source archive exceeds the resource budget")
    if digest(path.read_bytes()) != artifact_digest:
        raise ValueError("source archive differs from the expected artifact")

    violations = []
    scanned = []
    names = set()
    total_bytes = 0
    with tarfile.open(path, mode="r:") as archive:
        if not archive.pax_headers or archive.pax_headers.get("comment") != revision:
            raise ValueError("git archive revision differs from expected revision")
        for index, member in enumerate(archive):
            if index >= MAX_MEMBERS:
                raise ValueError("archive member count exceeds the resource budget")
            name = member.name.rstrip("/")
            parts = PurePosixPath(name).parts
            if (
                name in names
                or not parts
                or name.startswith("/")
                or any(part in {".", ".."} for part in parts)
            ):
                raise ValueError("duplicate or unsafe archive path")
            names.add(name)
            if name != PACKAGE_ROOT.rstrip("/") and not name.startswith(PACKAGE_ROOT):
                continue
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("package source contains a link or special file")
            if not name.endswith(".py"):
                continue
            if member.size > MAX_SOURCE_BYTES:
                raise ValueError("Python source is not a bounded regular file")
            total_bytes += member.size
            if total_bytes > MAX_TOTAL_SOURCE_BYTES:
                raise ValueError("Python source exceeds the resource budget")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("required source could not be read")
            with source:
                tree = ast.parse(source.read(), filename=name)
            scanned.append(name)
            if name != LAUNCH_MODULE:
                violations.extend(
                    f"{name}:{line}: {reason}"
                    for line, reason in launch_violations(tree)
                )
    if LAUNCH_MODULE not in scanned or len(scanned) < 2:
        raise ValueError("required launch module or non-launch source is missing")
    return {
        "id": SCENARIO,
        "status": "fail" if violations else "pass",
        "details": {"scanned_files": scanned, "violations": violations},
    }


def validate_evidence(
    evidence: dict[str, Any],
    manifest: dict[str, Any],
    revision: str,
    artifact_digest: str,
    approved_bundle_digest: str,
) -> None:
    if evidence.get("schema_version") != 1:
        raise ValueError("unsupported evidence version")
    if evidence.get("subject") != {
        "revision": revision,
        "artifact_sha256": artifact_digest,
        "artifact_kind": "git-source-tar",
    }:
        raise ValueError("evidence does not identify the expected candidate artifact")
    if evidence.get("bundle") != {
        "id": manifest["id"],
        "sha256": approved_bundle_digest,
    }:
        raise ValueError("evidence does not identify the approved bundle")
    if evidence.get("consumer_versions") != manifest["consumer_versions"]:
        raise ValueError("evidence does not identify the expected consumer versions")
    scenarios = evidence.get("scenarios")
    if (
        not isinstance(scenarios, list)
        or [
            result.get("id") if isinstance(result, dict) else None
            for result in scenarios
        ]
        != manifest["required_scenarios"]
    ):
        raise ValueError(
            "required scenario evidence is missing, duplicate, or unexpected"
        )
    for result in scenarios:
        details = result.get("details", {})
        if (
            result.get("status") != "pass"
            or not isinstance(details, dict)
            or not isinstance(details.get("scanned_files"), list)
            or LAUNCH_MODULE not in details["scanned_files"]
            or len(details["scanned_files"]) < 2
            or details.get("violations") != []
        ):
            raise ValueError("required scenario did not establish a pass")
    if evidence.get("verdict") != "pass":
        raise ValueError("verification did not pass")


def evaluate(
    archive: Path, revision: str, artifact_digest: str, approved_bundle_digest: str
) -> dict[str, Any]:
    manifest = load_manifest(approved_bundle_digest)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "subject": {
            "revision": revision,
            "artifact_sha256": artifact_digest,
            "artifact_kind": "git-source-tar",
        },
        "bundle": {"id": manifest["id"], "sha256": approved_bundle_digest},
        "consumer_versions": manifest["consumer_versions"],
        "scenarios": [{"id": SCENARIO, "status": "blocked", "details": {}}],
        "verdict": "blocked",
    }
    try:
        result = scan_archive(archive, revision, artifact_digest)
        evidence["scenarios"] = [result]
        evidence["verdict"] = result["status"]
        if result["status"] == "pass":
            validate_evidence(
                evidence, manifest, revision, artifact_digest, approved_bundle_digest
            )
    except (
        OSError,
        ValueError,
        SyntaxError,
        tarfile.TarError,
        RecursionError,
    ) as error:
        evidence["verdict"] = "blocked"
        evidence["scenarios"] = [
            {"id": SCENARIO, "status": "blocked", "details": {"error": str(error)}}
        ]
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-bundle-digest", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--revision")
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--approved-bundle-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.print_bundle_digest:
        print(bundle_digest())
        return 0
    if any(
        value is None
        for value in (
            args.archive,
            args.revision,
            args.artifact_sha256,
            args.approved_bundle_sha256,
            args.output,
        )
    ):
        parser.error("archive, expected identities, and evidence output are required")
    try:
        evidence = evaluate(
            args.archive,
            args.revision,
            args.artifact_sha256,
            args.approved_bundle_sha256,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Activation blocked: {error}", file=sys.stderr)
        return 2
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Conformance: {evidence['verdict']}")
    return {"pass": 0, "fail": 1, "blocked": 2}[evidence["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
