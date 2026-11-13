"""File, folder, module, crate and codebase lenses (design sections 3.4 and 3.5)."""

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from smog.domain.code import Codebase, Crate, Function, LockedPackage, Module, SourceFile
from smog.domain.graph import FileGraph, page_rank, reachable, strongly_connected, use_paths
from smog.domain.lenses.decoupling_level import decoupling_level
from smog.domain.settings import DEFAULT_SETTINGS


def _is_public_item(item) -> bool:
    """Marked exactly `pub`, outside test code, and neither a `use` nor a method of a trait impl."""
    return item.is_public and not item.in_test_code and not getattr(item, "is_trait_impl", False) and item.kind != "use_declaration"


def public_items(file: SourceFile) -> list:
    return [item for item in file.items if _is_public_item(item)]


def module_public_items(module: Module) -> list:
    """Items marked exactly `pub` that the module declares itself, outside test files: not those of the modules
    below it, inline ones included."""
    return [item for item in module.items if _is_public_item(item)]


def reexports(file: SourceFile) -> list[tuple]:
    """Paths of `pub use` declarations."""
    paths = []
    for item in file.items:
        if item.kind == "use_declaration" and item.is_public:
            paths.extend(use_paths(item.node.child("argument")))
    return paths


def measure_file(file: SourceFile, graph: FileGraph, fan_in: dict[str, int], ranks: dict) -> dict[str, float]:
    fan_out = len(graph.edges.get(file.path, ()))
    return {
        "file.length": file.line_count,
        "file.items": len([item for item in file.items if item.kind != "use_declaration"]),
        "file.crossing": min(fan_in.get(file.path, 0), fan_out),
        "file.central_position": ranks.get(file.path, 0.0),
    }


def folder_counts(tracked_paths: list[str]) -> dict[str, tuple[int, int]]:
    """Files and subfolders per folder in the git tree."""
    files: Counter = Counter()
    subfolders: dict[str, set] = defaultdict(set)
    for path in tracked_paths:
        parts = PurePosixPath(path).parent.parts
        files["/".join(parts)] += 1
        for depth in range(len(parts)):
            subfolders["/".join(parts[:depth])].add(parts[depth])
    return {folder: (files[folder], len(subfolders[folder])) for folder in set(files) | set(subfolders)}


def _interface_tokens(module: Module) -> int:
    total = 0
    for item in module_public_items(module):
        if isinstance(item, Function):
            total += len(item.signature_tokens())
        elif item.kind == "struct_item":
            total += 2 + 2 * sum(1 for field in item.fields if field.visibility == "pub")
        elif item.kind in ("enum_item", "trait_item"):
            total += len(item.node.token_texts())
    return total


def interface_depth(module: Module) -> float:
    """Code lines of the module per token of its interface. Higher is deeper.

    Ousterhout names the idea and gives no formula: "Goal for interface design: maximize functionality/(interface
    complexity)" (CS 190 lecture notes on modular design, Stanford, read 2026-11-10); the notes define neither
    term as a count. Smog's reading: functionality is the module's own code lines (`Module.own_code_lines`: its
    non-test files, test modules inside them included, without the inline modules declared in it), and interface
    complexity is the number of tokens a caller has to read: the signature tokens of each `pub` function and
    method, every token of each `pub` enum and trait, and 2 plus 2 per `pub` field for each `pub` struct. `pub`
    means exactly `pub`; `pub(crate)` items, `use` declarations, methods of trait impls and items in test files
    are no interface. 0 for a module without interface tokens. Padding the implementation raises the value.
    """
    interface = _interface_tokens(module)
    return module.own_code_lines() / interface if interface else 0.0


def module_folder(module: Module) -> str | None:
    """The folder that holds the files of the module's submodules, or None if no file says where it is.

    For a module with a `mod.rs`, `lib.rs` or `main.rs` it is the folder of that file. For a module declared as
    `foo.rs` it is the folder `foo` beside the file. For a folder without a module file, such as `tests` or
    `src/bin`, it is that folder, found from a file below it. An inline module has no folder.
    """
    file = next(iter(module.subtree_files()), None)
    if file is None:
        return None
    path = PurePosixPath(file.path)
    folder = path.parent if path.name in ("mod.rs", "lib.rs", "main.rs") else path.parent / path.stem
    for _ in range(len(file.module_path) - len(module.path)):
        folder = folder.parent
    return str(folder)


def measure_module(module: Module, folders: dict, graph: FileGraph, helper_counts: Counter, helper_depths: dict) -> dict[str, float]:
    """Values of one module. A module is a crate root, a file module or an inline module (`Module`).

    module.submodules is the number of direct submodules: file modules, inline modules and folders without a
    module file each count once, test files included, inline modules in test code not. The owner asked for the
    number of modules; no source defines it.

    module.files_per_folder and module.subfolders_per_folder count the tracked files of every type and the
    subfolders directly in the module's folder (`module_folder`), and module.folder_depth is that folder's
    number of path segments from the repository root. A module whose folder holds no tracked file, such as a
    `foo.rs` with no folder `foo`, has no value, and neither has a folder that holds no Rust module.
    """
    values = {
        "module.public_items": len(module_public_items(module)),
        "module.interface_depth": interface_depth(module),
        "module.submodules": len(module.children),
        "module.one_caller_helpers": helper_counts[module.qualified],
        "module.one_caller_chain": helper_depths.get(module.qualified, 0),
    }
    if module.declaration is None:
        edges = [(file.path, target) for file in module.subtree_files() for target in graph.edges.get(file.path, ())]
        inside_paths = {file.path for file in module.subtree_files()}
        inside = sum(1 for _, target in edges if target in inside_paths)
        values["module.internal_edge_share"] = inside / len(edges) if edges else 1.0
    folder = module_folder(module)
    if folder in folders:
        file_count, subfolder_count = folders[folder]
        values["module.files_per_folder"] = file_count
        values["module.subfolders_per_folder"] = subfolder_count
        values["module.folder_depth"] = len(PurePosixPath(folder).parts)
    return values


def _leaked_external_types(crate: Crate, dependencies: set[str]) -> int:
    leaked = 0
    for file in crate.files:
        for item in public_items(file):
            text = " ".join(item.signature_tokens()) if isinstance(item, Function) else ""
            leaked += any(re.search(rf"\b{re.escape(dep)}\s*::", text) for dep in dependencies)
    return leaked


def _multiple_public_paths(crate: Crate) -> int:
    """Items that are public at their own module and also re-exported by a `pub use` inside the crate."""
    public = {(file.module_path, item.name) for file in crate.files for item in public_items(file)}
    count = 0
    for file in crate.files:
        for path in reexports(file):
            if path and path[0] in ("crate", "self", "super") and any(name == path[-1] for _, name in public):
                count += 1
    return count


def _over_wide(crate: Crate, used_by_module: dict[str, set]) -> int:
    """`pub` items whose name is never used outside their own module."""
    count = 0
    for file in crate.files:
        if file.is_test:
            continue
        for item in public_items(file):
            if item.name and used_by_module.get(item.name, set()) <= {item.module_path}:
                count += 1
    return count


def names_used_by_module(codebase: Codebase) -> dict[str, set]:
    used: dict[str, set] = defaultdict(set)
    for file in codebase.files:
        for token in file.root.tokens():
            if token.kind in ("identifier", "type_identifier") and not file.is_test:
                used[token.text].add(file.module_path)
    return used


def ratios_to_production(prefix: str, files: list[SourceFile], per_lines: float = DEFAULT_SETTINGS["test_density_per_lines"]) -> dict[str, float]:
    """`<prefix>.tests_per_100_lines` and `<prefix>.test_lines_per_line` over some files: test cases per
    `per_lines` production code lines (setting `test_density_per_lines`, 100 by default), and test code lines
    per production code line.

    Test lines and production lines are the sums of file.test_lines and file.production_lines (`size_values`):
    a whole test file, every item under `#[cfg(test)]` and a test function outside such an item are test code.
    A test case is a function with a test attribute, or such an attribute among the tokens of a macro call
    (`SourceFile.test_case_count`). Without a production line neither ratio has a value: there is nothing to
    divide by, and 0 would read as "no tests".
    """
    test_cases = sum(file.test_case_count for file in files)
    test_lines = sum(file.test_code_line_count for file in files)
    production_lines = sum(file.code_line_count for file in files) - test_lines
    if not production_lines:
        return {}
    return {f"{prefix}.tests_per_100_lines": per_lines * test_cases / production_lines, f"{prefix}.test_lines_per_line": test_lines / production_lines}



def measure_crate(crate: Crate, codebase: Codebase, graph: dict, reverse: dict, used_names: dict, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    """Values of one crate.

    crate.instability is Martin's I = Ce / (Ca + Ce) over the workspace crates: Ce the workspace crates this one
    depends on, Ca those that depend on it. A crate with no workspace edge has no instability, because the ratio
    is 0 / 0, and so no crate.distance_main_sequence, which is |A + I - 1|.
    """
    production = [file for file in crate.files if not file.is_test]
    external = crate.external_dependencies()
    efferent = len(graph.get(crate.name, ()))
    afferent = len(reverse.get(crate.name, ()))
    items = [item for file in production for item in file.items if item.kind in ("struct_item", "enum_item", "trait_item")]
    abstract_items = sum(1 for item in items if item.kind == "trait_item")
    abstractness = abstract_items / len(items) if items else 0.0
    dependency_names = {name.replace("-", "_") for name in external}
    coupling = {}
    if efferent + afferent:
        instability = efferent / (efferent + afferent)
        coupling = {"crate.instability": instability, "crate.distance_main_sequence": abs(abstractness + instability - 1)}
    return {
        **coupling,
        "crate.lines": sum(file.line_count for file in crate.files),
        "crate.modules": sum(1 for _ in crate.root.walk()),
        "crate.public_items": sum(len(public_items(file)) for file in production),
        "crate.dependencies_internal": len(crate.internal_dependencies()),
        "crate.dependencies_external": len(external),
        "crate.over_wide_visibility": _over_wide(crate, used_names),
        "crate.leaked_external_types": _leaked_external_types(crate, dependency_names),
        "crate.reexports_foreign": sum(1 for file in production for path in reexports(file) if path and path[0] in dependency_names),
        "crate.reexports_internal": sum(1 for file in production for path in reexports(file) if path and path[0] not in dependency_names),
        "crate.multiple_public_paths": _multiple_public_paths(crate),
        "crate.rebuild_radius": len(reachable(reverse, crate.name)),
        **ratios_to_production("crate", crate.files, settings["test_density_per_lines"]),
    }


def crate_line_churn(crate: Crate, line_churn: dict[str, tuple[int, int]]) -> dict[str, float]:
    """The two relative churn measures of Nagappan and Ball for a crate: churned lines and deleted lines, each
    over the crate's code lines now.

    "M1: Churned LOC / Total LOC" and "M2: Deleted LOC / Total LOC" (Nagappan and Ball, ICSE 2005, as quoted in
    `History.file_line_churn`, which states how lines are counted). crate.relative_churn is M1 and
    crate.relative_deletion is M2, each summed over the Rust files the crate has now, test files included, and
    divided by their code lines. The paper defines two ratios; adding churned and deleted lines into one counts
    every changed line twice. A file deleted during the window is not counted, because its lines are no longer
    part of Total LOC, and renames are not followed. 0 for a crate without code lines or without history.
    """
    lines = sum(file.code_line_count for file in crate.files)
    added = sum(line_churn.get(file.path, (0, 0))[0] for file in crate.files)
    deleted = sum(line_churn.get(file.path, (0, 0))[1] for file in crate.files)
    return {
        "crate.relative_churn": added / lines if lines else 0.0,
        "crate.relative_deletion": deleted / lines if lines else 0.0,
    }


def dependency_weight(lock: list[LockedPackage], codebase: Codebase) -> dict[str, float]:
    by_name: dict[str, LockedPackage] = {}
    versions: Counter = Counter()
    for package in lock:
        by_name[package.name] = package
        versions[package.name] += 1
    graph = {package.name: set(package.dependencies) for package in lock}
    internal = {crate.name for crate in codebase.crates}
    transitive = [len(reachable(graph, crate.name) - internal) for crate in codebase.crates]
    direct = [dep for crate in codebase.crates for dep in crate.external_dependencies()]
    brought = [len(reachable(graph, dep)) for dep in set(direct)]
    return {
        "codebase.transitive_packages": max(transitive, default=0),
        "codebase.packages_per_direct": sum(brought) / len(brought) if brought else 0.0,
        "codebase.duplicate_versions": sum(1 for count in versions.values() if count > 1),
    }


def propagation_cost(edges: dict[str, set[str]]) -> float:
    """The density of the visibility matrix of a dependency graph: the pairs (a, b) where a reaches b through
    zero or more edges, over the square of the number of elements.

    MacCormack, Rusnak and Baldwin, "Exploring the Duality between Product and Organizational Architectures"
    (Harvard Business School working paper 08-039, pp. 13-14, read 2026-11-10): "By summing these matrices
    together we derive the visibility matrix V, showing the dependencies that exist between all system elements
    for all possible path lengths", "we compute the density of the visibility matrix, which we refer to as the
    system's Propagation Cost", and in a footnote "we choose to include the matrix for n=0 meaning that each
    element depends upon itself". So every element counts as reaching itself, and a graph without an edge has
    the value 1 / N. The paper's elements are source files and its dependencies function calls; here the
    elements are the production files and the dependencies the edges of `FileGraph`. 0 for an empty graph.
    """
    reach = sum(len(reachable(edges, node) | {node}) for node in edges)
    return reach / (len(edges) ** 2) if edges else 0.0


def measure_codebase(codebase: Codebase, file_graph: FileGraph) -> dict[str, float]:
    edges = file_graph.edges
    components = strongly_connected(edges)
    propagation = propagation_cost(edges)
    return {
        "codebase.modules": sum(1 for _ in codebase.modules),
        "codebase.largest_cyclic_group": max((len(component) for component in components if len(component) > 1), default=0),
        "codebase.propagation_cost": propagation,
        "codebase.decoupling_level": decoupling_level(edges),
        **dependency_weight(codebase.lock, codebase),
    }


def file_ranks(file_graph: FileGraph, settings: dict) -> dict:
    return page_rank(file_graph.edges, settings["page_rank_damping"], settings["page_rank_rounds"])
