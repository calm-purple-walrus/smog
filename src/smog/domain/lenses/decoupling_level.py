"""Decoupling Level (Mo, Cai, Kazman, Xiao, Feng, "Decoupling Level: A New Metric for Architectural Maintenance
Complexity", ICSE 2016) on the file graph, with the Design Rule Hierarchy it is computed from (Wong, Cai, Valetto,
Simeonov, Sethi, "Design Rule Hierarchies and Parallelism in Software Development Tasks", ASE 2009). Both read
2026-11-11 from the authors' copies on cs.drexel.edu. The method is patented (US 11,422,800).
"""

import math
from collections import defaultdict

from smog.domain.graph import reachable, strongly_connected

SMALL_MODULE_FILES = 5


def design_rule_hierarchy(edges: dict[str, set[str]]) -> list[list[frozenset[str]]]:
    """The layers of the Design Rule Hierarchy of a dependency graph, from the top layer to the last, each a list of
    modules, each module a set of files. `edges` maps a file to the files it depends on.

    The DL paper (section 2) describes the hierarchy and leaves the algorithm to its references: "Files in layer i
    should only depend on files in higher layers, i.e., layer j, where j < i", "files in the same layer are decoupled
    into modules that are mutually independent from each other", and "The modules in layer n, that is, the bottom
    layer of the DRH are truly Independent Modules". The ASE 2009 paper (sections III.B and IV) gives the algorithm
    on a constraint network; here the graph of influence is the file graph reversed, as a change to a file may
    influence the files that depend on it:

    1. "the condensation graph is derived from the constructed directed graph": strongly connected files are one
       vertex.
    2. "all the variables along the paths ending with the same minimal elements are put into a sub-ACN": a minimal
       element is a vertex no other file depends on, and its sub-ACN is it with everything it depends on.
    3. "our algorithm separates each region of intersection of the sub-ACNs into a separate group": files that lie
       in the same set of sub-ACNs form one module.
    4. "we first isolate the independent modules, then perform a modified breadth-first search (BFS) on the graph
       [...] a vertex is not explored until all its incoming neighbors have been explored": modules no other module
       depends on form the last layer, and every other module lies one layer below the lowest module it depends on
       ("Layer i (i >= 1) is the set of all tasks that assume at least one decision in level i - 1 and assume no
       decisions at a layer higher than i - 1").

    Figure 1c of the DL paper comes out as drawn. Figures 1a and 1b group two files the rules above keep apart
    (6 and 7 in 1a, 3 and 4 in 1b); the paper's tool, Titan, is not published, so the difference stays.
    """
    files = set(edges) | {target for targets in edges.values() for target in targets}
    graph = {file: set(edges.get(file, ())) for file in files}
    vertex_of = {file: index for index, component in enumerate(strongly_connected(graph)) for file in component}
    depends: dict[int, set[int]] = defaultdict(set)
    has_dependent: set[int] = set()
    for file, targets in graph.items():
        for target in targets:
            if vertex_of[file] != vertex_of[target]:
                depends[vertex_of[file]].add(vertex_of[target])
                has_dependent.add(vertex_of[target])
    regions: dict[int, set[int]] = defaultdict(set)
    for minimal in set(vertex_of.values()) - has_dependent:
        for vertex in reachable(depends, minimal) | {minimal}:
            regions[vertex].add(minimal)
    module_of = {file: frozenset(regions[vertex_of[file]]) for file in files}
    members: dict[frozenset, set[str]] = defaultdict(set)
    for file, region in module_of.items():
        members[region].add(file)
    uses = {region: {module_of[t] for f in group for t in graph[f]} - {region} for region, group in members.items()}
    used = {target for targets in uses.values() for target in targets}
    layer: dict[frozenset, int] = {}
    pending = [region for region in members if region in used]
    while pending:
        waiting = []
        for region in pending:
            if all(target in layer for target in uses[region]):
                layer[region] = 1 + max((layer[target] for target in uses[region]), default=-1)
            else:
                waiting.append(region)
        pending = waiting
    upper = [[] for _ in range(1 + max(layer.values(), default=-1))]
    for region, number in layer.items():
        upper[number].append(frozenset(members[region]))
    last = [frozenset(members[region]) for region in members if region not in used]
    return [sorted(modules, key=sorted) for modules in (*upper, last)]


def size_factor(module_files: int, all_files: int) -> float:
    """Equations (4) and (5) of the DL paper: "If a module, Mj, has 5 files or fewer, we calculate its SizeFactor based
    on its relative size: SizeFactor(Mj) = #Files(Mj) / #AllFiles", and "If Mj has more than 5 files, we add a
    penalty to reflect the limits of human cognitive capabilities: SizeFactor(Mj) = #Files(Mj) / #AllFiles ×
    (log5(#Files(Mj)))^-1"."""
    share = module_files / all_files
    return share if module_files <= SMALL_MODULE_FILES else share / math.log(module_files, SMALL_MODULE_FILES)


def decoupling_level(edges: dict[str, set[str]]) -> float:
    """Decoupling Level of a dependency graph; 0 for an empty graph. Section 3.1 of the DL paper:

    - (1) "Given a DRH with n layers, its DL is equal to the sum of the DLs of all the layers: DL = Σ_{Li=1..n} DL_Li".
    - (2) "For an upper layer Li, (i < n) with k modules, we calculate its DL as follows: DL_Li = Σ_{j=1..k}
      [#Files(Mj) / #AllFiles × (1 − #Deps(Mj) / #LowerLayerFiles)] where, #Deps(Mj) is the number of files within
      lower layer modules that directly or indirectly depend on Mj."
    - (3) "If the last layer, Ln, has k modules, then its DL is: DL_Li=n = Σ_{j=1..k} SizeFactor(Mj)" (`size_factor`).

    #Deps reads "files within lower layer modules that directly or indirectly depend on Mj" as all files of each
    lower module that has a file depending on Mj, directly or through other files. With this reading Figure 1a of
    the paper gives 82% as its caption states; counting only the depending files gives 83%. #LowerLayerFiles is the
    number of files in all layers below Li.
    """
    layers = design_rule_hierarchy(edges)
    all_files = sum(len(module) for modules in layers for module in modules)
    if not all_files:
        return 0.0
    dependents: dict[str, set[str]] = defaultdict(set)
    for file, targets in edges.items():
        for target in targets:
            dependents[target].add(file)
    level = sum(size_factor(len(module), all_files) for module in layers[-1])
    for number, modules in enumerate(layers[:-1]):
        lower = [module for below in layers[number + 1 :] for module in below]
        lower_files = sum(len(module) for module in lower)
        for module in modules:
            reached = {dependent for file in module for dependent in reachable(dependents, file)}
            depending = sum(len(other) for other in lower if other & reached)
            level += len(module) / all_files * (1 - depending / lower_files)
    return level
