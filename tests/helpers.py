"""Helpers for tests: parse Rust from strings, and build small git repositories."""

import os
import subprocess
from pathlib import Path

from smog import Policy
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.domain.code import Codebase, Crate, Function, Manifest, SourceFile

_PARSER = TreeSitterRustParser()


def parse_source_file(source: str, path: str = "src/lib.rs", crate: str = "sample", crate_dir: str = "") -> SourceFile:
    data = source.encode()
    return SourceFile(path, data, _PARSER.parse(data), crate, crate_dir)


def codebase_of(*files: SourceFile) -> Codebase:
    """One crate named `sample` from parsed files."""
    return Codebase([Crate(Manifest("sample", "", []), list(files))], [], [file.path for file in files], {})


def function_in(source: str, name: str) -> Function:
    return next(f for f in parse_source_file(source).functions if f.name == name)


def scored_policy() -> Policy:
    """A new policy without `codebase.mutation_score`, whose data only a whole-tree mutation run gives, so a run without `--full` has a score."""
    policy = Policy()
    policy.deselect("codebase.mutation_score")
    return policy


def write_tree(root: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def git(root: Path, *args: str, date: str | None = None) -> str:
    """Run git. `date`, such as `2026-03-01`, sets the author and commit time of a new commit to noon UTC of that day."""
    env = {**os.environ, **({"GIT_AUTHOR_DATE": f"{date}T12:00:00+0000", "GIT_COMMITTER_DATE": f"{date}T12:00:00+0000"} if date else {})}
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True, env=env).stdout


def make_repository(root: Path, files: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    commit(root, files, "base")


def commit(root: Path, files: dict[str, str], message: str) -> None:
    write_tree(root, files)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


MANIFEST = '[package]\nname = "sample"\nversion = "0.1.0"\nedition = "2021"\n'
