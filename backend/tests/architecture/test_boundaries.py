"""Enforce the module boundaries that separate decisions from execution."""

import ast
import json
from importlib.util import resolve_name

from treasury_backend.paths import ROOT


def imported_modules(path):
    result = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and not node.level:
            result.append(node.module or "")
            result.extend((node.module or "") + "." + name.name for name in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level:
            source = ROOT / "backend/src"
            if path.is_relative_to(source):
                package = ".".join(path.parent.relative_to(source).parts)
                module = resolve_name("." * node.level + (node.module or ""), package)
                result.append(module)
                result.extend(module + "." + name.name for name in node.names)
    return result


def test_no_ambiguous_app_package_or_execution_signer_dependency():
    source = ROOT / "backend/src/treasury_backend"
    for path in source.rglob("*.py"):
        imports = imported_modules(path)
        assert not any(name == "app" or name.startswith("app.") for name in imports), path
        if path.is_relative_to(source / "modules/execution"):
            assert not any(
                name.startswith("treasury_backend.modules.signing") for name in imports
            ), path
            assert not any(name.startswith("treasury_backend.operations") for name in imports), path
        if path.is_relative_to(source / "core"):
            assert not any(name.startswith("treasury_backend.modules") for name in imports), path


def test_shared_protocol_package_does_not_depend_on_backend():
    for path in (ROOT / "packages/contracts-api/treasury_contracts").glob("*.py"):
        assert not any(name.startswith("treasury_backend") for name in imported_modules(path)), path


def test_primary_npm_entrypoints_use_the_unified_backend():
    scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    expected = {
        "dev": "uv run --locked python -m treasury_backend.api.serve",
        "local": "uv run --locked treasury local",
        "dev:local": "uv run --locked treasury local",
        "dev:fuji": "uv run --locked treasury serve --network fuji",
        "demo": "uv run --locked treasury demo --network fuji",
        "dev:mock": "uv run --locked treasury mock",
        "deploy:local": "uv run --locked treasury deploy --network local",
        "deploy:fuji": "uv run --locked treasury deploy --network fuji",
    }
    for name, command in expected.items():
        assert scripts[name] == command, name


def test_control_features_do_not_import_execution_or_workflow_coordinator():
    source = ROOT / "backend/src/treasury_backend/modules"
    for feature in source.iterdir():
        if not feature.is_dir() or feature.name in {"execution", "__pycache__"}:
            continue
        for path in feature.rglob("*.py"):
            if "tests" in path.parts:
                continue
            imports = imported_modules(path)
            assert not any(
                name.startswith("treasury_backend.modules.execution") for name in imports
            ), path
            if feature.name != "workflows":
                assert not any(
                    name.startswith("treasury_backend.modules.workflows") for name in imports
                ), path
