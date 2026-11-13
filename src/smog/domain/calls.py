"""Who uses what. Resolved by name, or from a rust-analyzer index when one is available."""

from collections import Counter, defaultdict

from smog.domain.code import Codebase, Function, Item


class SymbolIndex:
    """References from a language server: (definition path, definition line, use path, use line). Lines count from 1."""

    def __init__(self, references: list[tuple[str, int, str, int]]):
        self._references = references

    @property
    def references(self) -> list[tuple[str, int, str, int]]:
        return self._references


def definitions_by_location(codebase: Codebase) -> dict[tuple[str, int], Item]:
    """Named items by file path and the line of their name, the place the index gives for a definition."""
    definitions = {}
    for file in codebase.files:
        for item in file.items:
            name = item.node.child("name")
            if name is not None:
                definitions[(file.path, name.start_line)] = item
    return definitions


class CallGraph:
    def __init__(self, codebase: Codebase, index: SymbolIndex | None = None):
        self._codebase = codebase
        self._callers: dict[str, list[Function]] = defaultdict(list)
        self._outgoing: dict[str, set] = defaultdict(set)
        self._cross_module: dict[str, set] = defaultdict(set)
        self._incoming: Counter = Counter()
        self._functions = {function.qualified: function for function in codebase.functions}
        self._is_indexed = index is not None
        if index is None:
            self._resolve_by_name()
        else:
            self._resolve_by_index(index)

    def _resolve_by_name(self) -> None:
        by_name: dict[str, list] = defaultdict(list)
        for function in self._codebase.functions:
            by_name[function.name].append(function)
        for file in self._codebase.files:
            for item in file.items:
                if not isinstance(item, Function) and item.kind in ("struct_item", "enum_item", "trait_item", "const_item", "static_item", "type_item"):
                    by_name[item.name].append(item)
        for function in self._codebase.functions:
            for name in function.used_names():
                definitions = by_name.get(name, [])
                if not definitions:
                    continue
                self._outgoing[function.qualified].add(name)
                if all(definition.module_path != function.module_path for definition in definitions):
                    self._cross_module[function.qualified].add(name)
                self._incoming[name] += 1
                in_crate = [d for d in definitions if isinstance(d, Function) and d.file.crate_name == function.file.crate_name]
                if len(in_crate) == 1:
                    self._callers[in_crate[0].qualified].append(function)
        self._ambiguity = {name: len(definitions) for name, definitions in by_name.items()}

    def _resolve_by_index(self, index: SymbolIndex) -> None:
        self._ambiguity = {}
        definitions = definitions_by_location(self._codebase)
        ranges = defaultdict(list)
        for file in self._codebase.files:
            for function in file.functions:
                ranges[file.path].append(function)
        for def_path, def_line, use_path, use_line in index.references:
            item = definitions.get((def_path, def_line))
            caller = next((f for f in ranges.get(use_path, ()) if f.holds_line(use_line)), None)
            if item is None or caller is None or item is caller:
                continue
            self._outgoing[caller.qualified].add(item.qualified)
            if item.module_path != caller.module_path:
                self._cross_module[caller.qualified].add(item.qualified)
            self._incoming[item.qualified] += 1
            if isinstance(item, Function) and caller not in self._callers[item.qualified]:
                self._callers[item.qualified].append(caller)

    def outgoing(self, function: Function) -> int:
        return len(self._outgoing[function.qualified])

    def outgoing_cross_module(self, function: Function) -> int:
        return len(self._cross_module[function.qualified])

    def incoming(self, function: Function) -> float:
        """Use sites. Without an index, uses of a shared name are split among its definitions."""
        if self._is_indexed:
            return self._incoming[function.qualified]
        return self._incoming[function.name] / max(self._ambiguity.get(function.name, 1), 1)

    def one_caller(self, function: Function) -> Function | None:
        """The only production caller of a private function, when it sits in the same module."""
        if not function.is_private or function.in_test_code or function.is_test_case:
            return None
        callers = [caller for caller in self._callers.get(function.qualified, ()) if not caller.in_test_code]
        if len(callers) != 1 or callers[0].module_path != function.module_path or callers[0] is function:
            return None
        return callers[0]

    def effective_lengths(self, alpha: float) -> dict[str, float]:
        """`own + alpha * sum(effective(child))` over private functions whose only caller is this one."""
        children = defaultdict(list)
        for function in self._codebase.functions:
            parent = self.one_caller(function)
            if parent is not None:
                children[parent.qualified].append(function)
        memo: dict[str, float] = {}

        def effective(function: Function, active: frozenset) -> float:
            key = function.qualified
            if key not in memo:
                inner = active | {key}
                total = sum(effective(child, inner) for child in children[key] if child.qualified not in inner)
                memo[key] = function.lines + alpha * total
            return memo[key]

        return {function.qualified: effective(function, frozenset()) for function in self._codebase.functions}

    def helper_chains(self) -> dict[str, int]:
        """Length of the chain of one-caller helpers ending at each function."""
        depths: dict[str, int] = {}

        def depth(function: Function, seen: frozenset) -> int:
            parent = self.one_caller(function)
            if parent is None or parent.qualified in seen:
                return 0
            return 1 + depth(parent, seen | {function.qualified})

        for function in self._codebase.functions:
            depths[function.qualified] = depth(function, frozenset())
        return depths
