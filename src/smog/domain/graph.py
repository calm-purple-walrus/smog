"""Graph algorithms, and the file dependency graph resolved from `use` paths and qualified paths."""

from collections import defaultdict

from smog.domain.code import Codebase, SourceFile
from smog.domain.syntax import Node


def strongly_connected(graph: dict) -> list[list]:
    """Tarjan's algorithm, iterative so deep graphs cannot overflow the stack."""
    index: dict = {}
    low: dict = {}
    on_stack: set = set()
    stack: list = []
    components = []
    for start in graph:
        if start in index:
            continue
        work = [(start, iter(graph.get(start, ())))]
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        while work:
            node, successors = work[-1]
            for successor in successors:
                if successor not in index:
                    index[successor] = low[successor] = len(index)
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(graph.get(successor, ()))))
                    break
                if successor in on_stack:
                    low[node] = min(low[node], index[successor])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    components.append(component)
    return components


def reachable(graph: dict, start) -> set:
    seen = set()
    stack = list(graph.get(start, ()))
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(graph.get(node, ()))
    return seen


def page_rank(graph: dict, damping: float, rounds: int) -> dict:
    nodes = set(graph) | {successor for successors in graph.values() for successor in successors}
    if not nodes:
        return {}
    rank = dict.fromkeys(nodes, 1 / len(nodes))
    for _ in range(rounds):
        updated = dict.fromkeys(nodes, (1 - damping) / len(nodes))
        for node, successors in graph.items():
            for successor in successors:
                updated[successor] += damping * rank[node] / len(successors)
        rank = updated
    return rank


def use_paths(argument: Node, prefix: tuple = ()) -> list[tuple]:
    """Expand the argument of a `use` declaration into full paths."""
    kind = argument.kind
    if kind in ("identifier", "crate", "self", "super"):
        return [(*prefix, argument.text)]
    if kind == "scoped_identifier":
        return [(*prefix, *argument.text.replace(" ", "").split("::"))]
    if kind == "use_as_clause":
        return use_paths(argument.child("path"), prefix)
    if kind == "use_wildcard":
        return use_paths(argument.named[0], prefix) if argument.named else [prefix]
    if kind == "use_list":
        return [path for child in argument.named for path in use_paths(child, prefix)]
    if kind == "scoped_use_list":
        base = use_paths(argument.child("path"), prefix)[0] if argument.child("path") else prefix
        return use_paths(argument.child("list"), base)
    return []


_PATH_PREFIX_KINDS = ("scoped_identifier", "identifier", "crate", "self", "super")


def named_paths(root: Node) -> list[tuple]:
    """Every path a file names, each once in full: the paths of its `use` declarations and its qualified paths.

    A qualified path such as `crate::a::b::f` is one path. Its prefixes `crate::a::b` and `crate::a` are parts
    of it in the syntax tree and are not paths of their own. Generic arguments inside a path, as in
    `a::B::<c::D>::new`, are separate paths.
    """
    paths = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.kind == "use_declaration":
            paths.extend(use_paths(node.child("argument")))
            continue
        if node.kind in ("scoped_identifier", "scoped_type_identifier"):
            paths.append(tuple(node.text.replace(" ", "").split("::")))
            prefix = node.child("path")
            stack.extend(child for child in node.children if child is not prefix or child.kind not in _PATH_PREFIX_KINDS)
            continue
        stack.extend(node.children)
    return paths


class FileGraph:
    """Edges between production files. Resolution is by path and module name, without an index.

    A file has an edge to the file of the deepest known module on each path it names (`resolve`). A path gives
    one edge: `crate::a::b::f` leads to the file of `a::b` and adds no edge to the file of `a`.
    """

    def __init__(self, codebase: Codebase):
        self._codebase = codebase
        self._by_module = {(file.crate_name, file.module_path): file for file in codebase.files if not file.is_test}
        self._edges: dict[str, set[str]] = {file.path: set() for file in codebase.files if not file.is_test}
        for file in codebase.files:
            if not file.is_test:
                self._edges[file.path] = {target.path for target in self._targets(file) if target.path != file.path}

    @property
    def edges(self) -> dict[str, set[str]]:
        return self._edges

    def fan_in(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for targets in self._edges.values():
            for target in targets:
                counts[target] += 1
        return counts

    def _targets(self, file: SourceFile) -> list[SourceFile]:
        targets = (self.resolve(file, path) for path in named_paths(file.root))
        return [target for target in targets if target is not None]

    def resolve(self, file: SourceFile, path: tuple) -> SourceFile | None:
        """The file of the deepest known module on the path, or None if the path leaves the codebase."""
        module = resolve_module(self._codebase, self._by_module, file.crate_name, file.module_path, path)
        return self._by_module[module] if module else None


def resolve_module(codebase: Codebase, known, crate_name: str, base: tuple, path: tuple) -> tuple | None:
    """(crate name, module path) of the deepest module in `known` that a path names, or None if it leaves the codebase.

    `base` is the module the path is written in. `crate`, `self` and `super` are followed. Any other first
    segment is a module below `base` if there is one, and otherwise a crate of the codebase with a library,
    the code's own crate included: a binary names its library that way.
    """
    segments = list(path)
    if not segments:
        return None
    head = segments[0]
    if head == "crate":
        base, segments = (), segments[1:]
    elif head == "self":
        segments = segments[1:]
    elif head == "super":
        while segments and segments[0] == "super":
            base, segments = base[:-1], segments[1:]
    elif (crate_name, (*base, head)) not in known:
        crate = codebase.crate_with_lib(head)
        if crate is None:
            return None
        crate_name, base, segments = crate.name, (), segments[1:]
    best = (crate_name, base) if (crate_name, base) in known else None
    for segment in segments:
        base = (*base, segment)
        if (crate_name, base) not in known:
            break
        best = (crate_name, base)
    return best


def crate_graph(codebase: Codebase) -> dict[str, set[str]]:
    names = {crate.name for crate in codebase.crates}
    return {crate.name: {d for d in crate.internal_dependencies() if d in names} for crate in codebase.crates}


def reversed_graph(graph: dict) -> dict:
    result: dict = {node: set() for node in graph}
    for node, successors in graph.items():
        for successor in successors:
            result.setdefault(successor, set()).add(node)
    return result
