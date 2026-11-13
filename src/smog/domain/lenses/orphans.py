"""Orphan files: `.rs` files of a crate that no `mod` declaration includes."""

import fnmatch
import posixpath
import re
from collections.abc import Iterator

from smog.domain.code import Codebase, Crate, SourceFile
from smog.domain.syntax import COMMENT_KINDS, Node

# Where Cargo looks for the root file of a target without being told (The Cargo Book, "Package Layout").
_ROOT_PATTERNS = (
    "src/lib.rs", "src/main.rs", "build.rs", "src/bin/*.rs", "src/bin/*/main.rs", "tests/*.rs", "tests/*/main.rs", "benches/*.rs",
    "benches/*/main.rs", "examples/*.rs", "examples/*/main.rs",
)  # fmt: skip
_PATH = re.compile(r'^path\s*=\s*"([^"]*)"$')
_CONDITIONAL_PATH = re.compile(r'^cfg_attr\(.*\bpath\s*=\s*"([^"]*)"')


def _is_root(path: str, crate: Crate) -> bool:
    relative = path[len(crate.directory) + 1 :] if crate.directory else path
    in_pattern = any(fnmatch.fnmatchcase(relative, pattern) and relative.count("/") == pattern.count("/") for pattern in _ROOT_PATTERNS)
    return in_pattern or path in crate.manifest.target_paths


def _macro_includes(macro: Node, inline: tuple, folder: str) -> Iterator[list]:
    name = macro.child("macro").text.rsplit("::", 1)[-1]
    tokens = list(macro.tokens())
    if name == "include":
        yield [posixpath.join(folder, token.text[1:-1]) for token in tokens if token.kind == "string_literal"]
        return
    for first, second, third in zip(tokens, tokens[1:], tokens[2:]):
        if first.text == "mod" and second.kind == "identifier" and third.text == ";":
            yield [("mod", second.text, inline)]


def _declared(container: Node, inline: tuple, folder: str, inline_folder: str) -> Iterator[list]:
    """What the items of a file or inline module pull in. Each result is a list of candidates: a path, or
    ("mod", name, inline modules) for a declaration without a `#[path]`.

    `folder` holds the file; `inline_folder` is where a `#[path]` inside an inline module starts."""
    attributes: list[str] = []
    for node in container.named:
        if node.kind == "attribute_item":
            attributes.append(node.child_of_kind("attribute").text)
            continue
        if node.kind in COMMENT_KINDS:
            continue
        if node.kind == "mod_item" and node.child("body") is not None:
            yield from _declared(node.child("body"), (*inline, node.child("name").text), folder, inline_folder)
        elif node.kind == "mod_item":
            fixed = [match.group(1) for match in map(_PATH.match, attributes) if match]
            conditional = [match.group(1) for match in map(_CONDITIONAL_PATH.match, attributes) if match]
            default = [] if fixed else [("mod", node.child("name").text, inline)]
            start = posixpath.join(inline_folder, *inline) if inline else folder
            yield [*default, *(posixpath.join(start, path) for path in fixed + conditional)]
        else:
            for nested in node.find("mod_item"):
                if nested.child("body") is None:
                    yield [("mod", nested.child("name").text, inline)]
            for macro in node.find("macro_invocation"):
                yield from _macro_includes(macro, inline, folder)
        attributes = []


def _included_by(file: SourceFile, is_root: bool) -> set[str]:
    """Paths a file may pull in: both places a `mod name;` can live, each `#[path]` target and each `include!` target."""
    directory, name = posixpath.split(file.path)
    owns_its_folder = is_root or name == "mod.rs"
    children = directory if owns_its_folder else posixpath.join(directory, name.removesuffix(".rs"))
    paths = set()
    for candidates in _declared(file.root, (), directory, children):
        for candidate in candidates:
            if isinstance(candidate, str):
                paths.add(posixpath.normpath(candidate))
            else:
                _, module, inline = candidate
                base = posixpath.join(children, *inline, module)
                paths.update((base + ".rs", posixpath.join(base, "mod.rs")))
    return paths


def orphan_files(codebase: Codebase) -> set[str]:
    """Paths of the `.rs` files of a crate that no `mod` declaration includes, starting from the crate's root files.

    The measurement is the one of `cargo modules orphans`: "Detects unlinked source files within a crate's
    directory" (cargo-modules README and `src/command/orphans/scanner.rs`, read 2026-11-10). That tool asks
    rust-analyzer which modules exist under the default configuration and lists the files beside them that are
    no module. This rule reads syntax and differs where stated:

    - Root files are never orphans: `src/lib.rs`, `src/main.rs`, `build.rs`, the files Cargo finds by itself
      under `src/bin`, `tests`, `benches` and `examples`, and every `path` or `build` the manifest names.
    - `mod name;` includes `name.rs` or `name/mod.rs` in the folder of the declaring module: the file's own
      folder for a root file or a `mod.rs`, else the folder named after the file. Inline modules around the
      declaration add their names as folders.
    - `#[path = "p"]` on a `mod` includes `p` and not the default place. Outside an inline module `p` starts at
      the folder of the declaring file. Inside one it starts at the folder of the declaring module, with the
      inline modules as folders. A `#[path]` on an inline module itself is not followed.
    - `cfg`: a `mod` behind any `#[cfg(...)]` counts as included, whatever the condition, so a file used on one
      platform only is no orphan. `#[cfg_attr(..., path = "p")]` includes both `p` and the default place.
      cargo-modules lists a file whose `mod` is switched off in the default configuration.
    - `include!("p")` includes `p`, relative to the folder of the file with the macro. cargo-modules lists such
      a file. `include_str!` and `include_bytes!` do not include a file as code.
    - `mod name;` among the tokens of a macro call, as in `cfg_if!`, counts as a declaration.
    - A file is reached through any chain of such steps from a root file; everything else in the crate is an
      orphan, at any depth. A test fixture kept as a `.rs` file is an orphan by this rule.

    A file that belongs to no crate is not judged. A file left out by `policy.exclude` or as generated is not
    measured and is never an orphan itself, but it is read here: a root file or a `mod` declaration in it reaches
    other files like any other.
    """
    files = {file.path: file for crate in codebase.crates for file in (*crate.files, *crate.skipped_files)}
    orphans: set[str] = set()
    for crate in codebase.crates:
        if not crate.directory and crate.name == "(no crate)":
            continue
        roots = {file.path for file in (*crate.files, *crate.skipped_files) if _is_root(file.path, crate)}
        reached = set(roots)
        pending = list(roots)
        while pending:
            path = pending.pop()
            for included in _included_by(files[path], path in roots):
                if included in files and included not in reached:
                    reached.add(included)
                    pending.append(included)
        orphans.update(file.path for file in crate.files if file.path not in reached)
    return orphans - _reached_from_other_crates(codebase, files)


def _reached_from_other_crates(codebase: Codebase, files: dict[str, SourceFile]) -> set[str]:
    """Files a `#[path]` or `include!` in another crate pulls in directly."""
    reached = set()
    for crate in codebase.crates:
        own = {file.path for file in crate.files}
        for file in (*crate.files, *crate.skipped_files):
            reached.update(path for path in _included_by(file, _is_root(file.path, crate)) if path in files and path not in own)
    return reached
