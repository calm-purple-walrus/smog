"""The module-use graph and what is read from it: Martin's package metrics, cycle membership and centrality."""

from collections import deque
from collections.abc import Iterator

from smog.domain.code import Codebase, Module, SourceFile, TraitDef, TypeDef
from smog.domain.graph import resolve_module, reversed_graph, strongly_connected, use_paths

_SCOPED = ("scoped_identifier", "scoped_type_identifier")


def _references(file: SourceFile) -> Iterator[tuple[tuple, tuple]]:
    """(module path of the code, path it names) for each `use` path and each qualified path outside test code."""
    test_lines = file.test_code_lines
    stack = [(file.root, file.module_path, False)]
    while stack:
        node, module, is_prefix = stack.pop()
        if node.start_line in test_lines and node.kind in ("mod_item", "function_item"):
            continue
        if node.kind == "use_declaration":
            yield from ((module, path) for path in use_paths(node.child("argument")))
            continue
        if node.kind in _SCOPED and not is_prefix:
            yield module, tuple(node.text.replace(" ", "").split("::"))
        if node.kind == "mod_item" and node.child("body") is not None:
            module = (*module, node.child("name").text)
        stack.extend((child, module, node.kind in _SCOPED and child.field == "path") for child in node.children)


class ModuleGraph:
    """Which module uses which module, over the whole codebase.

    Nodes are the production modules (`Module`): crate roots, file modules outside test files and inline modules
    outside test code. A folder without a module file is no node. A module `a` has an edge to another module `b`
    when code that `a` declares itself names `b`:

    - in a `use` declaration, `pub use` included, once per path of a `use` list;
    - in a qualified path such as `crate::b::f()` or `b::Type`, taken whole, so `crate::b::c::f` names `b::c` only.

    A path names the deepest module on it: `crate::b::c::Item` names `b::c` if that is a module, else `b`, else the
    crate root. `crate`, `self` and `super` are followed; a path that starts with a workspace crate's library name
    goes to that crate; a path that starts with a submodule of the current module is relative. Every other path
    (`std`, an external crate, an enum, a name brought in by `use`) names no module. `mod b;` is a declaration and
    no use.

    What this does not see. Names are not resolved: an item reached through a re-export counts for the module
    that re-exports it, a glob import hides what is used, and a path through an alias (`use crate::b as x; x::f()`)
    counts once, for the `use`. Modules are known by file path, so a module placed with `#[path]` is known under
    its file's path and paths that use its declared name are missed. `cfg` is not evaluated: code behind any `cfg`
    counts, except test code (`#[cfg(test)]` modules, test functions, test files), which is left out on both
    ends. Paths inside macro calls are not parsed.
    """

    def __init__(self, codebase: Codebase):
        self._modules: dict[tuple, Module] = {}
        for module in codebase.modules:
            if module.declaration is not None or any(not file.is_test for file in module.files):
                self._modules[(module.crate_name, module.path)] = module
        self._edges: dict[tuple, set[tuple]] = {key: set() for key in self._modules}
        for file in codebase.files:
            if file.is_test:
                continue
            for module, path in _references(file):
                source = (file.crate_name, module)
                target = resolve_module(codebase, self._modules, file.crate_name, module, path)
                if target is not None and target != source and source in self._edges:
                    self._edges[source].add(target)

    @property
    def modules(self) -> dict[tuple, Module]:
        """(crate name, module path) to module."""
        return self._modules

    @property
    def edges(self) -> dict[tuple, set[tuple]]:
        return self._edges



def abstractness(module: Module) -> float:
    """Traits / (traits + structs + enums + unions) among the items the module declares itself.

    Martin's A: "The ratio of the number of abstract classes (and interfaces) in the analyzed package to the total
    number of classes in the analyzed package" (Robert C. Martin, Agile Software Development, 2002, as quoted by
    Wikipedia, "Software package metrics", read 2026-11-10; the book itself was not opened). No source maps this
    to Rust. Here a trait is the abstract kind and a struct, enum or union the concrete kind; type aliases,
    functions and impl blocks count on neither side. Visibility does not matter. Items in test code and in
    submodules, inline ones included, are left out. 0 for a module that declares none of these.
    """
    items = [item for item in module.items if isinstance(item, (TraitDef, TypeDef)) and not item.in_test_code]
    return sum(1 for item in items if isinstance(item, TraitDef)) / len(items) if items else 0.0


def coupling_values(graph: ModuleGraph) -> dict[tuple, dict[str, float]]:
    """Martin's package metrics per module, with the module in the place of the package.

    Definitions (Robert C. Martin, Agile Software Development, 2002, as quoted by Wikipedia, "Software package
    metrics", read 2026-11-10; the book itself was not opened): Ca is "the number of classes in other packages
    that depend upon classes within the package", Ce "the number of classes in other packages that the classes in
    a package depend upon", "I = Ce / (Ce + Ca)" and "D = | A + I - 1 |".

    Martin counts classes. The module-use graph has no edges between single items, so the unit here is the
    module: module.afferent is the number of other modules with an edge to this one, module.efferent the number
    of other modules this one has an edge to, in any crate of the codebase. This is the measurement list's
    reading, "modules that depend on it (Ca); modules it depends on (Ce)". External
    crates and `std` are no modules and count on neither side. A parent and its child are two modules.

    module.instability and module.distance_main_sequence have no value for a module with Ca + Ce = 0, where the
    ratio is undefined. module.abstractness is `abstractness`.
    """
    incoming = reversed_graph(graph.edges)
    values = {}
    for key, module in graph.modules.items():
        afferent, efferent = len(incoming.get(key, ())), len(graph.edges[key])
        abstract = abstractness(module)
        values[key] = {"module.afferent": afferent, "module.efferent": efferent, "module.abstractness": abstract}
        if afferent + efferent:
            instability = efferent / (afferent + efferent)
            values[key]["module.instability"] = instability
            values[key]["module.distance_main_sequence"] = abs(abstract + instability - 1)
    return values


def cycle_sizes(graph: ModuleGraph, skip_nested: bool) -> dict[tuple, int]:
    """Per module, the number of modules in its cycle group, or 0 if it is in no cycle.

    A cycle group is a strongly connected component of the module-use graph with more than one module: every
    module in it reaches every other along use edges. This is the graph-theory definition; no tool's rule is
    copied.

    With `skip_nested` (setting `module_cycles_skip_nested`, on by default) an edge between a module and one of
    its ancestors or descendants in the same crate is dropped first. A parent that re-exports from its child
    while the child uses `super::` is idiomatic Rust and would otherwise put most module trees into one group.
    Cycles between siblings, cousins and modules of different crates remain.
    """
    edges = graph.edges
    if skip_nested:
        edges = {source: {target for target in targets if not _nested(source, target)} for source, targets in edges.items()}
    sizes = dict.fromkeys(graph.modules, 0)
    for component in strongly_connected(edges):
        if len(component) > 1:
            sizes.update(dict.fromkeys(component, len(component)))
    return sizes


def _nested(first: tuple, second: tuple) -> bool:
    (crate, path), (other_crate, other_path) = first, second
    shorter = min(len(path), len(other_path))
    return crate == other_crate and path[:shorter] == other_path[:shorter]


def centrality_values(graph: ModuleGraph) -> dict[tuple, dict[str, float]]:
    """Degree, closeness and betweenness centrality per module, each from 0 to 1.

    The three are Freeman's point centralities ("Centrality in social networks: conceptual clarification",
    Social Networks 1, 1978/79; formulas read 2026-11-10 from Wikipedia, "Centrality", and the networkx
    documentation of `closeness_centrality`, not from the paper). Freeman defines them on undirected graphs, so
    the direction of a use edge is dropped: two modules are neighbours when either uses the other. Direction is
    what module.afferent and module.efferent report. n is the number of modules in the graph.

    - module.degree_centrality: neighbours / (n - 1).
    - module.closeness_centrality: (r / (n - 1)) * (r / sum of the shortest distances to the r modules it can
      reach). On a connected graph r = n - 1 and this is Freeman's (n - 1) / sum of distances. The first factor
      is Wasserman and Faust's correction for a graph in several parts, as networkx applies it by default, so a
      module in a small island does not look central. 0 for a module without neighbours.
    - module.betweenness_centrality: the sum over pairs of other modules (s, t) of the share of shortest paths
      between s and t that pass through the module, divided by the number of such pairs, (n - 1)(n - 2) / 2.
      Computed with Brandes' algorithm. 0 when n < 3.
    """
    linked: dict[tuple, set[tuple]] = {key: set(targets) for key, targets in graph.edges.items()}
    for source, targets in graph.edges.items():
        for target in targets:
            linked[target].add(source)
    # Sorted, so sums of floats add up in the same order on every run.
    neighbours = {key: sorted(found) for key, found in linked.items()}
    count = len(neighbours)
    betweenness = dict.fromkeys(neighbours, 0.0)
    values = {}
    for start in neighbours:
        order, distance, paths, parents = _shortest_paths(neighbours, start)
        reached = len(order) - 1
        total = sum(distance.values())
        values[start] = {
            "module.degree_centrality": len(neighbours[start]) / (count - 1) if count > 1 else 0.0,
            "module.closeness_centrality": (reached / (count - 1)) * (reached / total) if total else 0.0,
        }
        dependency = dict.fromkeys(order, 0.0)
        for node in reversed(order):
            for parent in parents[node]:
                dependency[parent] += paths[parent] / paths[node] * (1 + dependency[node])
            if node != start:
                betweenness[node] += dependency[node]
    pairs = (count - 1) * (count - 2)
    for key in neighbours:
        # Each undirected path was found from both ends, so the sum is twice the count; `pairs` is twice the pairs.
        values[key]["module.betweenness_centrality"] = betweenness[key] / pairs if pairs > 0 else 0.0
    return values


def _shortest_paths(neighbours: dict, start) -> tuple[list, dict, dict, dict]:
    """Breadth-first search: nodes in the order reached, their distance, the number of shortest paths to each,
    and the previous nodes on those paths."""
    order = []
    distance = {start: 0}
    paths = {start: 1}
    parents: dict = {start: []}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        order.append(node)
        for following in neighbours[node]:
            if following not in distance:
                distance[following] = distance[node] + 1
                paths[following] = 0
                parents[following] = []
                queue.append(following)
            if distance[following] == distance[node] + 1:
                paths[following] += paths[node]
                parents[following].append(node)
    return order, distance, paths, parents
