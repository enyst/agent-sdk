#!/usr/bin/env python3
"""
Check import dependency rules across openhands packages.

Rules:
1. openhands.sdk should NOT import from:
   - openhands.tools
   - openhands.workspace
   - openhands.agent_server

2. openhands.tools can import from:
   - openhands.sdk
   BUT NOT from:
   - openhands.workspace
   - openhands.agent_server

3. openhands.workspace can import from:
   - openhands.sdk
   - openhands.tools
   BUT NOT from:
   - openhands.agent_server
   Exception: docker/dev_workspace.py uses openhands.agent_server.docker.build
   for development-only image building through the canonical server builder.

4. openhands.agent_server can import from:
   - openhands.sdk
   - openhands.tools
   BUT NOT from:
   - openhands.workspace
"""

import ast
import sys
from importlib.util import resolve_name
from pathlib import Path


PACKAGE_RULES = {
    "sdk": ("tools", "workspace", "agent_server"),
    "tools": ("workspace", "agent_server"),
    "workspace": ("agent_server",),
    "agent_server": ("workspace",),
}
IMPORT_EXCEPTIONS = {
    "openhands-workspace/openhands/workspace/docker/dev_workspace.py": (
        "openhands.agent_server.docker.build",
    ),
}


class ImportChecker(ast.NodeVisitor):
    """Extract absolute dependency names from static import statements."""

    def __init__(self, package: str):
        self.package = package
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.update(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level:
            module = resolve_name("." * node.level + module, self.package)
        self.imports.add(module)
        self.imports.update(
            f"{module}.{alias.name}" for alias in node.names if alias.name != "*"
        )


def get_imports_from_file(file_path: Path, package: str) -> set[str]:
    """Extract dependencies, resolving relative imports in their package."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    checker = ImportChecker(package)
    checker.visit(tree)
    return checker.imports


def check_package_imports(
    package_path: Path,
    package: str,
    forbidden: tuple[str, ...],
    exceptions: dict[Path, tuple[str, ...]],
) -> list[tuple[Path, str]]:
    violations = []
    forbidden_modules = tuple(f"openhands.{name}" for name in forbidden)
    for py_file in sorted(package_path.rglob("*.py")):
        relative_parent = py_file.parent.relative_to(package_path)
        file_package = ".".join(("openhands", package, *relative_parent.parts))
        imports = get_imports_from_file(py_file, file_package)
        for imp in sorted(imports):
            if any(
                imp == module or imp.startswith(f"{module}.")
                for module in exceptions.get(py_file, ())
            ):
                continue
            if any(
                imp == module or imp.startswith(f"{module}.")
                for module in forbidden_modules
            ):
                violations.append((py_file, imp))
    return violations


def main(files: list[str] | None = None) -> int:
    """Check all packages, or packages containing the supplied filenames."""
    repo_root = Path(__file__).resolve().parent.parent
    selected_files = [Path(file).resolve() for file in files or []]
    exceptions = {
        repo_root / path: modules for path, modules in IMPORT_EXCEPTIONS.items()
    }
    failed = False
    for package, forbidden in PACKAGE_RULES.items():
        distribution = f"openhands-{package.replace('_', '-')}"
        package_path = repo_root / distribution / "openhands" / package
        if not package_path.exists():
            continue
        if selected_files and not any(
            file.is_relative_to(package_path) for file in selected_files
        ):
            continue
        try:
            violations = check_package_imports(
                package_path, package, forbidden, exceptions
            )
        except (OSError, SyntaxError, ImportError) as exc:
            print(
                f"[ERROR] Unable to check openhands.{package}: {exc}", file=sys.stderr
            )
            failed = True
            continue
        for file, imp in violations:
            print(
                f"[ERROR] {file.relative_to(repo_root)}: imports {imp} "
                f"({package} cannot import {'/'.join(forbidden)})"
            )
            failed = True

    if failed:
        return 1
    print("All import dependency rules satisfied!")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
