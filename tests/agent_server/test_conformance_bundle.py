"""Qualification controls also runnable with python -I -S, without pytest."""

from __future__ import annotations

import copy
import io
import json
import runpy
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "conformance" / "verify.py"
VERIFY = runpy.run_path(str(VERIFIER))
REVISION = "a" * 40
SOURCES = {
    VERIFY["LAUNCH_MODULE"]: "agent = Agent(llm=llm, tools=[])\n",
    VERIFY["PACKAGE_ROOT"]
    + "router.py": "request = config.create_request(Req, agent_profile_id=pid)\n",  # noqa: E501
}


def _archive(path: Path, sources: dict[str, str], symlink: str = "") -> str:
    with tarfile.open(
        path, "w", format=tarfile.PAX_FORMAT, pax_headers={"comment": REVISION}
    ) as archive:
        for name, source in sources.items():
            member = tarfile.TarInfo(name)
            content = source.encode()
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        if symlink:
            member = tarfile.TarInfo(symlink)
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
    return VERIFY["digest"](path.read_bytes())


def _evaluate(sources: dict[str, str], symlink: str = "") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "source.tar"
        artifact_digest = _archive(archive, sources, symlink)
        return VERIFY["evaluate"](
            archive, REVISION, artifact_digest, VERIFY["bundle_digest"]()
        )


def _git_candidate(
    directory: Path, sources: dict[str, str], symlink: tuple[str, str] | None = None
) -> dict[str, Any]:
    repository = directory / "candidate"
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "--quiet")
    for name, source in sources.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    if symlink is not None:
        name, target = symlink
        (repository / name).symlink_to(target, target_is_directory=True)
    git("add", ".")
    git(
        "-c",
        "user.name=Conformance control",
        "-c",
        "user.email=control@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "--quiet",
        "-m",
        "control",
    )
    revision = git("rev-parse", "HEAD")
    (repository / ".git/info/attributes").write_text("* -export-ignore -export-subst\n")
    archive = directory / "source.tar"
    git("archive", "--format=tar", "--output", str(archive), revision)
    return VERIFY["evaluate"](
        archive,
        revision,
        VERIFY["digest"](archive.read_bytes()),
        VERIFY["bundle_digest"](),
    )


def _assert_rejected(evidence: dict[str, Any]) -> None:
    manifest = VERIFY["load_manifest"](VERIFY["bundle_digest"]())
    original = _evaluate(SOURCES)
    try:
        VERIFY["validate_evidence"](
            evidence,
            manifest,
            REVISION,
            original["subject"]["artifact_sha256"],
            VERIFY["bundle_digest"](),
        )
    except ValueError:
        return
    raise AssertionError("invalid evidence was accepted")


def test_valid_candidate_and_complete_evidence_pass():
    evidence = _evaluate(SOURCES)
    assert evidence["verdict"] == "pass", evidence
    VERIFY["validate_evidence"](
        evidence,
        VERIFY["load_manifest"](VERIFY["bundle_digest"]()),
        REVISION,
        evidence["subject"]["artifact_sha256"],
        VERIFY["bundle_digest"](),
    )


def test_every_existing_launch_violation_fails():
    for source in (
        "agent = settings.create_agent()",
        "agent = settings.create_agent_from_settings()",
        "agent = Agent(llm=llm, tools=[])",
        "agent = ACPAgent(acp_command=['x'])",
        "request = settings.create_request(StartConversationRequest, workspace=w)",
        "request = request.model_copy(update={'agent': agent})",
        "request.agent = agent",
        "launched = LaunchedAgent(agent=a, profile=None)",
    ):
        sources = {**SOURCES, VERIFY["PACKAGE_ROOT"] + "violation.py": source}
        assert _evaluate(sources)["verdict"] == "fail", source


def test_empty_missing_invalid_and_symlink_source_block():
    cases = (
        {},
        {VERIFY["LAUNCH_MODULE"]: "pass"},
        {**SOURCES, VERIFY["PACKAGE_ROOT"] + "invalid.py": "x = ("},
    )
    for sources in cases:
        assert _evaluate(sources)["verdict"] == "blocked"
    assert (
        _evaluate(SOURCES, VERIFY["PACKAGE_ROOT"] + "link.py")["verdict"] == "blocked"
    )


def test_wrong_revision_and_artifact_block():
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "source.tar"
        artifact_digest = _archive(archive, SOURCES)
        for revision, expected_artifact in (
            ("b" * 40, artifact_digest),
            (REVISION, "0" * 64),
        ):
            result = VERIFY["evaluate"](
                archive, revision, expected_artifact, VERIFY["bundle_digest"]()
            )
            assert result["verdict"] == "blocked", result


def test_unsafe_duplicate_and_oversized_source_block():
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "source.tar"
        for name, size, repetitions in (
            ("../outside.py", 0, 1),
            (VERIFY["PACKAGE_ROOT"] + "large.py", VERIFY["MAX_SOURCE_BYTES"] + 1, 1),
            (VERIFY["PACKAGE_ROOT"] + "duplicate.py", 0, 2),
        ):
            with tarfile.open(
                archive,
                "w",
                format=tarfile.PAX_FORMAT,
                pax_headers={"comment": REVISION},
            ) as output:
                for _ in range(repetitions):
                    member = tarfile.TarInfo(name)
                    member.size = size
                    output.addfile(member, io.BytesIO(b" " * size))
            result = VERIFY["evaluate"](
                archive,
                REVISION,
                VERIFY["digest"](archive.read_bytes()),
                VERIFY["bundle_digest"](),
            )
            assert result["verdict"] == "blocked", result


def test_git_export_attributes_cannot_hide_a_violation():
    with tempfile.TemporaryDirectory() as directory:
        result = _git_candidate(
            Path(directory),
            {
                **SOURCES,
                VERIFY["PACKAGE_ROOT"] + "violation.py": "agent = Agent()",
                ".gitattributes": "*violation.py export-ignore\n",
            },
        )
        assert result["verdict"] == "fail", result
        assert any(
            "violation.py" in violation
            for violation in result["scenarios"][0]["details"]["violations"]
        )


def test_git_directory_symlink_cannot_hide_source_outside_package():
    with tempfile.TemporaryDirectory() as directory:
        result = _git_candidate(
            Path(directory),
            {
                **SOURCES,
                VERIFY["PACKAGE_ROOT"] + "router.py": "from .hidden.bad import build",
                "openhands-agent-server/openhands/shared/bad.py": (
                    "def build(): return Agent()"
                ),
            },
            (VERIFY["PACKAGE_ROOT"] + "hidden", "../shared"),
        )
        assert result["verdict"] == "blocked", result
        assert result["scenarios"][0]["status"] == "blocked", result
        assert "link or special file" in result["scenarios"][0]["details"]["error"]


def test_non_python_special_members_block():
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "source.tar"
        for member_type in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            with tarfile.open(
                archive,
                "w",
                format=tarfile.PAX_FORMAT,
                pax_headers={"comment": REVISION},
            ) as output:
                member = tarfile.TarInfo(VERIFY["PACKAGE_ROOT"] + "hidden")
                member.type = member_type
                member.linkname = "../shared"
                output.addfile(member)
            result = VERIFY["evaluate"](
                archive,
                REVISION,
                VERIFY["digest"](archive.read_bytes()),
                VERIFY["bundle_digest"](),
            )
            assert result["verdict"] == "blocked", result
            assert "link or special file" in result["scenarios"][0]["details"]["error"]


def test_missing_duplicate_skipped_and_blocked_evidence_reject():
    original = _evaluate(SOURCES)
    for scenarios in (
        [],
        original["scenarios"] * 2,
        [{"id": VERIFY["SCENARIO"], "status": "skipped", "details": {}}],
        [{"id": VERIFY["SCENARIO"], "status": "blocked", "details": {}}],
        [{"id": "CANDIDATE-SELECTED", "status": "pass", "details": {}}],
    ):
        _assert_rejected({**original, "scenarios": scenarios})


def test_evidence_identity_and_execution_tampering_reject():
    original = _evaluate(SOURCES)
    for key, value in (
        ("subject", {**original["subject"], "revision": "b" * 40}),
        ("subject", {**original["subject"], "artifact_sha256": "0" * 64}),
        ("bundle", {**original["bundle"], "sha256": "0" * 64}),
        ("consumer_versions", {"unapproved-client": "latest"}),
        ("verdict", "blocked"),
    ):
        _assert_rejected({**original, key: value})
    evidence = copy.deepcopy(original)
    evidence["scenarios"][0]["details"]["scanned_files"] = []
    _assert_rejected(evidence)
    evidence = copy.deepcopy(original)
    evidence["scenarios"][0]["details"]["violations"] = ["observed violation"]
    _assert_rejected(evidence)


def test_candidate_runner_plugins_and_manifest_are_inert():
    malicious = "raise RuntimeError('candidate code executed')\n"
    sources = {
        **SOURCES,
        "conftest.py": malicious,
        "sitecustomize.py": malicious,
        "conformance/verify.py": malicious,
        "conformance/manifest.json": '{"required_scenarios": []}',
        "pytest.ini": "[pytest]\naddopts = --ignore=openhands-agent-server\n",
    }
    assert _evaluate(sources)["verdict"] == "pass"
    sources[VERIFY["PACKAGE_ROOT"] + "violation.py"] = "agent = Agent()"
    assert _evaluate(sources)["verdict"] == "fail"


def test_unapproved_activation_and_bundle_tampering_reject():
    approved = VERIFY["bundle_digest"]()
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory)
        for name in ("verify.py", "manifest.json"):
            (bundle / name).write_bytes((VERIFIER.parent / name).read_bytes())
        copied = runpy.run_path(str(bundle / "verify.py"))
        for rejected_digest in ("", "latest", "0" * 64):
            try:
                copied["load_manifest"](rejected_digest)
            except ValueError:
                continue
            raise AssertionError("unapproved activation was accepted")
        for name in ("manifest.json", "verify.py"):
            path = bundle / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            try:
                copied["load_manifest"](approved)
            except ValueError:
                pass
            else:
                raise AssertionError("tampered bundle was accepted")
            path.write_bytes(original)
        manifest = json.loads((bundle / "manifest.json").read_text())
        manifest["required_scenarios"] = []
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        try:
            copied["load_manifest"](copied["bundle_digest"]())
        except ValueError:
            return
        raise AssertionError("empty collection was accepted")


def test_external_cli_exercises_and_writes_required_roster():
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "source.tar"
        output = Path(directory) / "evidence.json"
        artifact_digest = _archive(archive, SOURCES)
        command = [
            sys.executable,
            "-I",
            "-S",
            str(VERIFIER),
            "--archive",
            str(archive),
            "--revision",
            REVISION,
            "--artifact-sha256",
            artifact_digest,
            "--approved-bundle-sha256",
            VERIFY["bundle_digest"](),
            "--output",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert json.loads(output.read_text())["scenarios"][0]["status"] == "pass"
        command[command.index("--approved-bundle-sha256") + 1] = "0" * 64
        output.unlink()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert not output.exists()


if __name__ == "__main__":
    tests = [value for key, value in list(globals().items()) if key.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Qualified: {len(tests)} control groups")
