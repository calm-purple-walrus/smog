"""Reads Cargo.toml and Cargo.lock."""

import posixpath
import tomllib

from smog.domain.code import Audits, Dependency, LockedPackage, Manifest

_SECTIONS = (("dependencies", "normal"), ("dev-dependencies", "dev"), ("build-dependencies", "build"))


class CargoManifests:
    def unreadable(self, files: dict[str, bytes]) -> dict[str, str]:
        """Why each of the files that cannot be read cannot: not valid TOML, or a `Cargo.toml` whose `[package]` has no name."""
        reasons = {}
        for path, content in files.items():
            try:
                document = tomllib.loads(content.decode("utf-8", "replace"))
            except tomllib.TOMLDecodeError as error:
                reasons[path] = f"not valid TOML: {error}"
                continue
            package = document.get("package")
            if path.endswith("Cargo.toml") and package is not None and not (isinstance(package, dict) and isinstance(package.get("name"), str)):
                reasons[path] = "its [package] table has no name"
        return reasons

    def read_manifests(self, files: dict[str, bytes]) -> list[Manifest]:
        parsed = {path: tomllib.loads(content.decode("utf-8", "replace")) for path, content in files.items()}
        workspace_deps: dict = {}
        for document in parsed.values():
            workspace_deps.update(document.get("workspace", {}).get("dependencies", {}))
        packages = {document["package"]["name"] for document in parsed.values() if "package" in document}
        manifests = []
        for path, document in parsed.items():
            if "package" in document:
                directory = path.removesuffix("Cargo.toml").rstrip("/")
                manifests.append(Manifest(document["package"]["name"], directory, _dependencies(document, workspace_deps, packages), _target_paths(document, directory)))
        return manifests

    def read_lock(self, content: bytes) -> list[LockedPackage]:
        document = tomllib.loads(content.decode("utf-8", "replace"))
        return [
            LockedPackage(
                package["name"],
                package["version"],
                [dep.split()[0] for dep in package.get("dependencies", [])],
                [(dep.split()[0], dep.split()[1] if len(dep.split()) > 1 else None) for dep in package.get("dependencies", [])],
            )
            for package in document.get("package", [])
        ]

    def read_audits(self, files: dict[str, bytes]) -> Audits | None:
        """cargo-vet's records from `supply-chain/audits.toml` and `supply-chain/imports.lock`, or None without the first."""
        if "supply-chain/audits.toml" not in files:
            return None
        tables = [tomllib.loads(files["supply-chain/audits.toml"].decode("utf-8", "replace")).get("audits", {})]
        if "supply-chain/imports.lock" in files:
            imported = tomllib.loads(files["supply-chain/imports.lock"].decode("utf-8", "replace")).get("audits", {})
            tables.extend(source.get("audits", {}) for source in imported.values() if isinstance(source, dict))
        full, deltas = set(), set()
        for table in tables:
            for name, entries in table.items():
                for entry in entries:
                    if "version" in entry:
                        full.add((name, entry["version"]))
                    elif "delta" in entry:
                        start, _, end = entry["delta"].partition("->")
                        deltas.add((name, start.strip(), end.strip()))
        return Audits(full, deltas)


def _target_paths(document: dict, directory: str) -> tuple[str, ...]:
    """The `path` of `[lib]` and of each `[[bin]]`, `[[test]]`, `[[bench]]` and `[[example]]`, and `build` of `[package]`."""
    targets = [document.get("lib", {}), *(target for kind in ("bin", "test", "bench", "example") for target in document.get(kind, []))]
    paths = [target["path"] for target in targets if isinstance(target, dict) and isinstance(target.get("path"), str)]
    if isinstance(document["package"].get("build"), str):
        paths.append(document["package"]["build"])
    return tuple(posixpath.normpath(posixpath.join(directory, path)) for path in paths)


def _dependencies(document: dict, workspace_deps: dict, packages: set[str]) -> list[Dependency]:
    """The dependencies of the three sections, at the top level and under each `[target.<cfg>]` table."""
    result = []
    tables = [document, *(table for table in document.get("target", {}).values() if isinstance(table, dict))]
    for table in tables:
        for section, kind in _SECTIONS:
            for name, spec in table.get(section, {}).items():
                resolved = workspace_deps.get(name, {}) if isinstance(spec, dict) and spec.get("workspace") else spec
                package = resolved.get("package", name) if isinstance(resolved, dict) else name
                if not any((known.name, known.kind) == (package, kind) for known in result):
                    result.append(Dependency(package, kind, package in packages))
    return result
