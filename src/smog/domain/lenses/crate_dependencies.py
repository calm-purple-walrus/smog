"""Crate measurements read from Cargo.toml, Cargo.lock and the audit records: dependency counts, duplicate
versions, unused dependencies and the audited share."""

import re
from collections import Counter

from smog.domain.code import Audits, Codebase, Crate, LockedPackage


class LockGraph:
    """The packages of Cargo.lock and what each needs.

    A package is a (name, version) pair. A workspace crate is followed through the normal and build dependencies
    its manifest declares, so the dev-dependencies of a workspace crate that another crate depends on are not
    part of that other crate's tree. Every other package is followed through all dependencies the lock file lists
    for it. Cargo.lock holds the dependencies for every target platform and every feature the workspace can
    switch on, so a tree read from it is the largest tree Cargo may build, not the tree of one build.
    """

    def __init__(self, codebase: Codebase):
        self._by_name: dict[str, list[LockedPackage]] = {}
        for package in codebase.lock:
            self._by_name.setdefault(package.name, []).append(package)
        self._crates = {crate.name: crate for crate in codebase.crates}

    def lists(self, crate: Crate) -> bool:
        return self._find(crate.name, None) is not None

    def is_external(self, key: tuple[str, str]) -> bool:
        return key[0] not in self._crates

    def _find(self, name: str, version: str | None) -> LockedPackage | None:
        candidates = self._by_name.get(name, [])
        return next((package for package in candidates if version in (None, package.version)), None)

    def needed_by(self, crate: Crate, kinds: tuple[str, ...]) -> list[LockedPackage]:
        """The locked packages behind the crate's direct dependencies of these kinds (`normal`, `dev`, `build`)."""
        entry = self._find(crate.name, None)
        if entry is None:
            return []
        wanted = {dependency.name for dependency in crate.manifest.dependencies if dependency.kind in kinds}
        found = [self._find(name, version) for name, version in entry.requirements if name in wanted]
        return [package for package in found if package is not None]

    def tree(self, starts: list[LockedPackage]) -> set[tuple[str, str]]:
        """Every package reachable from `starts`, the starts included."""
        seen: set[tuple[str, str]] = set()
        pending = list(starts)
        while pending:
            package = pending.pop()
            key = (package.name, package.version)
            if key in seen:
                continue
            seen.add(key)
            crate = self._crates.get(package.name)
            if crate is not None:
                pending.extend(self.needed_by(crate, ("normal", "build")))
            else:
                found = [self._find(name, version) for name, version in package.requirements]
                pending.extend(following for following in found if following is not None)
        return seen


def dependency_trees(crate: Crate, lock: LockGraph) -> tuple[set, set]:
    """External packages in the crate's tree: (through normal and build dependencies, through any dependency)."""
    built = {key for key in lock.tree(lock.needed_by(crate, ("normal", "build"))) if lock.is_external(key)}
    everything = {key for key in lock.tree(lock.needed_by(crate, ("normal", "build", "dev"))) if lock.is_external(key)}
    return built, everything


def dependency_counts(crate: Crate, lock: LockGraph) -> dict[str, float]:
    """Distinct external packages a crate depends on: direct and in total, with dev-only ones apart.

    The measurement list asks for "distinct external packages, direct and total; dev-only separately". No tool's
    rule is copied; the counts are read from Cargo.toml and Cargo.lock, which need neither cargo nor the registry
    cache on the machine. `cargo metadata --locked` resolves the same lock file.

    - crate.dependencies_external (existing): packages under `[dependencies]` that are no workspace crate.
    - crate.dependencies_dev: packages under `[dev-dependencies]` that are no workspace crate and are declared
      under neither `[dependencies]` nor `[build-dependencies]`.
    - crate.dependencies_total: (name, version) pairs outside the workspace in the tree below the crate's normal
      and build dependencies (`LockGraph`). Workspace crates on the way are followed and not counted.
    - crate.dependencies_total_dev: the pairs that enter the tree only when the crate's dev-dependencies are
      followed too.
    - crate.duplicate_versions: package names with more than one version in the tree with dev-dependencies. This
      is the per-crate form of codebase.duplicate_versions, which reads the whole lock file.

    Direct dependencies include those under `[target.<cfg>.dependencies]` tables, whatever the platform. An
    optional dependency counts whether or not a feature switches it on. A dependency renamed with `package =`
    counts under its package name. Two versions of one package are two packages in the totals. The three values
    read from the lock file have no value when the repository has no Cargo.lock or the lock file does not list
    the crate.
    """
    declared = crate.manifest.dependencies
    built_names = {dependency.name for dependency in declared if dependency.kind in ("normal", "build")}
    dev_only = {dependency.name for dependency in declared if dependency.kind == "dev" and not dependency.is_internal} - built_names
    values: dict[str, float] = {"crate.dependencies_dev": len(dev_only)}
    if not lock.lists(crate):
        return values
    built, everything = dependency_trees(crate, lock)
    versions = Counter(name for name, _ in everything)
    values.update(
        {
            "crate.dependencies_total": len(built),
            "crate.dependencies_total_dev": len(everything - built),
            "crate.duplicate_versions": sum(1 for count in versions.values() if count > 1),
        }
    )
    return values


def unused_dependency_names(crate: Crate, ignored: set[str] = frozenset()) -> list[str]:
    """Dependencies of any kind that the crate declares and whose name appears nowhere in its Rust files.

    The method is the one of cargo-machete, which "detects unused dependencies in Rust projects, in a fast (yet
    imprecise) way" (README, read 2026-11-10; the README does not spell the search out). cargo-udeps asks the
    compiler and needs a nightly toolchain, so it is not used. A dependency is used when its name, with `-`
    written as `_`, is an identifier anywhere in a `.rs` file of the crate, test files and build script
    included, or a word inside an attribute such as `#[derive(...)]` or `#[serde(...)]`.

    False positives, as cargo-machete lists them: a crate whose library name differs from its package name, a
    dependency renamed in Cargo.toml (the package name is searched, not the new name), a crate used only by code
    that a build script or a macro generates, and one needed only for its features. False negatives: any
    identifier with the dependency's name counts, such as a local variable called `log`. Names passed to
    `policy.ignore_unused_dependencies` are skipped.
    """
    used = {token.text for file in crate.files for token in file.root.tokens() if token.kind in ("identifier", "crate", "type_identifier")}
    used |= {word for file in crate.files for attribute in file.root.find("attribute", "inner_attribute_item") for word in re.findall(r"\w+", attribute.text)}
    names = []
    for dependency in crate.manifest.dependencies:
        if dependency.name not in ignored and dependency.name.replace("-", "_") not in used and dependency.name not in names:
            names.append(dependency.name)
    return names


def audited_share(crate: Crate, lock: LockGraph, audits: Audits | None) -> float | None:
    """Audited external packages / external packages in the crate's tree, dev-dependencies included.

    The records are cargo-vet's, read from `supply-chain/audits.toml` (the project's own audits, tables
    `[[audits.<crate>]]`) and `supply-chain/imports.lock` (audits imported from others, tables
    `[[audits.<source>.audits.<crate>]]`) at the repository root. An entry with `version` "corresponds to an
    absolute version that was audited for the relevant criteria in its entirety"; an entry with `delta`,
    written `version_a -> version_b`, certifies the change between two versions (cargo-vet book, "Audit
    Entries", and cargo-vet's own supply-chain files, read 2026-11-10). A package version is audited when a full
    audit of some version and a chain of delta audits lead to it, in the direction each delta is written.

    Not counted as audited: exemptions in `config.toml`, wildcard audits and trusted publishers (they trust a
    publisher and name no version), and nothing is subtracted for `violation` entries. The criteria of an audit
    are not compared with a policy: any criteria count. A store moved with `[package.metadata.vet] store` is not
    found. cargo-crev keeps its proofs in the user's home folder, not in the repository, so they are not read.

    None, so no value, when the repository has no `supply-chain/audits.toml`, no Cargo.lock, or the crate has no
    external package in its tree.
    """
    if audits is None or not lock.lists(crate):
        return None
    _, everything = dependency_trees(crate, lock)
    if not everything:
        return None
    return sum(1 for name, version in everything if audits.covers(name, version)) / len(everything)
