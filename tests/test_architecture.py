"""Enforces the layer rules: allowed import directions, no outside dependencies in the domain, no public fields on its models."""

import ast
import os
import re
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent.parent / "src" / "smog"
ALLOWED = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapter": {"domain", "ports", "adapter"},
    "infrastructure": {"domain", "ports", "application", "adapter", "infrastructure"},
}


def modules_of(layer: str) -> list[Path]:
    return sorted((PACKAGE / layer).rglob("*.py"))


def imported_names(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_layer_imports_only_allowed_layers(layer):
    assert modules_of(layer), f"no modules in {layer}"
    for path in modules_of(layer):
        for name in imported_names(path):
            parts = name.split(".")
            if parts[0] == "smog":
                assert len(parts) > 1 and parts[1] in ALLOWED[layer], f"{path.name} imports {name}"


def test_domain_uses_only_the_standard_library():
    allowed = set(sys.stdlib_module_names) - {"subprocess", "socket", "os", "tomllib", "tempfile", "shutil", "pathlib_"}
    for path in modules_of("domain"):
        for name in imported_names(path):
            root = name.split(".")[0]
            assert root == "smog" or root in allowed, f"{path.name} imports {name}"


def test_only_the_adapter_imports_tree_sitter():
    for layer in ("domain", "ports", "application", "infrastructure"):
        for path in modules_of(layer):
            assert not any(name.startswith("tree_sitter") for name in imported_names(path)), path.name


def test_public_domain_classes_have_no_public_fields():
    for path in modules_of("domain"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                continue
            for inner in ast.walk(node):
                if isinstance(inner, (ast.Assign, ast.AnnAssign)):
                    targets = inner.targets if isinstance(inner, ast.Assign) else [inner.target]
                    for target in targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            assert target.attr.startswith("_"), f"{path.name}: {node.name}.{target.attr}"
            decorators = [ast.unparse(item) for item in node.decorator_list]
            assert not any("dataclass" in item for item in decorators), f"{path.name}: {node.name}"


@pytest.mark.skipif(not os.environ.get("SMOG_PRIVATE_NAMES"), reason="set SMOG_PRIVATE_NAMES to a comma-separated list")
def test_private_data_stays_out_of_the_repository():
    root = PACKAGE.parent.parent
    names = [name.strip().lower() for name in os.environ["SMOG_PRIVATE_NAMES"].split(",")]
    for path in _published_files(root):
        text = path.read_text(errors="replace").lower()
        assert not any(name in text for name in names), path


def _published_files(root: Path) -> list[Path]:
    """The code, the tests, the documents and the package description."""
    found = [*root.glob("src/**/*.py"), *root.glob("tests/**/*"), *root.glob("docs/**/*"), root / "README.md", root / "pyproject.toml"]
    return [path for path in found if path.is_file() and "__pycache__" not in str(path)]


def test_no_file_holds_a_path_of_somebodys_machine():
    # `/Users/name/`, `/home/name/`, and the same folders written with `-` for `/`, as in the name of a session folder.
    home = re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/|/-(?:Users|home)-[A-Za-z0-9_.]+-")
    assert home.search("/private/tmp/tool-501/-Users-somebody-work/1/notes.py") and home.search("/home/somebody/x")
    for path in _published_files(PACKAGE.parent.parent):
        if path != Path(__file__):
            assert not home.search(path.read_text(errors="replace")), path
