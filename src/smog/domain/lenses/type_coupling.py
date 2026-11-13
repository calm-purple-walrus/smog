"""Coupling between types (CBO) and the response set of a type (RFC), after Chidamber and Kemerer."""

from collections import defaultdict

from smog.domain.calls import SymbolIndex, definitions_by_location
from smog.domain.code import Codebase, Function, Item, TraitDef, TypeDef
from smog.domain.lenses.type_shape import production_methods


def _classes(codebase: Codebase) -> list[Item]:
    """The pieces that stand for a class: structs, enums, unions and traits."""
    return [item for file in codebase.files for item in (*file.types, *file.traits)]


def _trait_methods(codebase: Codebase, trait: TraitDef) -> list[Function]:
    return [f for f in trait.file.functions if f.in_trait and f.owner == trait.name and f.module_path == trait.module_path]


def _names_used_by_class(codebase: Codebase, item: Item) -> set[str]:
    """Names a class uses: type names in its definition, the traits of its impl blocks, and every name in its methods."""
    names = {token.text for token in item.node.tokens() if token.kind == "type_identifier"}
    if isinstance(item, TypeDef):
        methods = production_methods(item)
        names.update(block.trait_name for file in codebase.files for block in file.impls if block.type_name == item.name and file.crate_name == item.file.crate_name)
    else:
        methods = _trait_methods(codebase, item)
    for method in methods:
        names.update(method.used_names())
    return names


def coupling_by_name(codebase: Codebase) -> dict[TypeDef, int]:
    """CBO per type, with names in place of resolved types.

    Chidamber and Kemerer, "A Metrics Suite for Object Oriented Design" (IEEE TSE 1994, read 2026-11-10): "CBO for
    a class is a count of the number of other classes to which it is coupled", and "two classes are coupled when
    methods declared in one class use methods or instance variables defined by the other class". The relation has
    no direction, so a type that is only used by another is coupled to it as well.

    A class here is a struct, enum, union or trait defined in the codebase; types of the standard library and of
    dependencies are not counted. Type A uses class B when B's name appears in A's definition (field types and
    bounds), as the trait of one of A's `impl` blocks, or anywhere in A's methods outside test code. The value is
    the number of distinct other class names that A uses or that use A. Classes that share a name count as one.
    A use that never writes the name is not seen: a method called on a value whose type is inferred, or a type
    behind an alias. Method names are not matched, because a name such as `min` or `send` also belongs to the
    standard library. Derived traits add nothing. Code inside macro calls is read as tokens.
    """
    classes = _classes(codebase)
    class_names = {item.name for item in classes}
    uses: dict[str, set[str]] = defaultdict(set)
    for item in classes:
        uses[item.name] |= (_names_used_by_class(codebase, item) & class_names) - {item.name}
    used_by: dict[str, set[str]] = defaultdict(set)
    for name, targets in uses.items():
        for target in targets:
            used_by[target].add(name)
    return {item: len(uses[item.name] | used_by[item.name]) for item in classes if isinstance(item, TypeDef)}


class _Resolved:
    """Index references mapped onto classes and functions."""

    def __init__(self, codebase: Codebase, index: SymbolIndex):
        self._definitions = definitions_by_location(codebase)
        self._class_of_method: dict[Function, Item] = {}
        self._ranges: dict[str, list[Item]] = defaultdict(list)
        self._functions: dict[str, list[Function]] = defaultdict(list)
        for item in _classes(codebase):
            self._ranges[item.file.path].append(item)
            methods = item.methods if isinstance(item, TypeDef) else _trait_methods(codebase, item)
            for method in methods:
                self._class_of_method[method] = item
        for file in codebase.files:
            self._functions[file.path].extend(file.functions)
        self.class_edges: set[tuple[Item, Item]] = set()
        self.called: dict[Function, set[Function]] = defaultdict(set)
        for def_path, def_line, use_path, use_line in index.references:
            target = self._definitions.get((def_path, def_line))
            caller = self._function_at(use_path, use_line)
            if isinstance(target, Function) and caller is not None and target is not caller:
                self.called[caller].add(target)
            source_class = self._class_at(use_path, use_line, caller)
            target_class = self._class_at(def_path, def_line, target if isinstance(target, Function) else None, target)
            if source_class is not None and target_class is not None and source_class is not target_class:
                self.class_edges.add((source_class, target_class))

    def _function_at(self, path: str, line: int) -> Function | None:
        return next((f for f in self._functions.get(path, ()) if f.holds_line(line)), None)

    def _class_at(self, path: str, line: int, function: Function | None, item: Item | None = None) -> Item | None:
        if isinstance(item, (TypeDef, TraitDef)):
            return item
        if function is not None:
            return None if function.in_test_code else self._class_of_method.get(function)
        return next((found for found in self._ranges.get(path, ()) if found.start_line <= line <= found.end_line), None)


def coupling_by_index(codebase: Codebase, index: SymbolIndex) -> dict[TypeDef, int]:
    """CBO per type from the rust-analyzer index: see `coupling_by_name` for the definition.

    A reference couples the class at its use to the class at its definition. The class at a use is the type
    whose method outside test code holds the line, or the type or trait whose definition holds it. The class at a
    definition is the type or trait itself, the owner of a method, or the type whose definition holds the line,
    which covers fields and variants. Only definitions inside the repository are in the index.
    """
    resolved = _Resolved(codebase, index)
    coupled: dict[Item, set[Item]] = defaultdict(set)
    for source, target in resolved.class_edges:
        coupled[source].add(target)
        coupled[target].add(source)
    return {item: len(coupled[item]) for item in _classes(codebase) if isinstance(item, TypeDef)}


def response_sets(codebase: Codebase, index: SymbolIndex | None = None) -> dict[TypeDef, int]:
    """RFC per type: the type's methods plus the methods they call.

    Chidamber and Kemerer 1994 (read 2026-11-10): "RFC = |RS| where RS is the response set for the class",
    "RS = {M} ∪ all i {R_i} where {R_i} = set of methods called by method i and {M} = set of all methods in the
    class". Only direct calls count, not the calls of the called methods.

    The methods are the functions in the type's `impl` blocks outside test code, trait impls and associated
    functions included. Without the index a called method is known by its name alone: function calls, method
    calls and calls inside macro arguments count, a macro itself does not, and two methods of different types
    with one name count once. A call to one of the type's own method names adds nothing, and neither does a
    called name that starts with a capital, such as `Some(x)` or `Kind::Wrapped(x)`: that builds a value of a tuple
    struct or enum variant. With the index, a call
    to a function defined in the repository is that function, and every other call counts by its name. Calls to
    the standard library and to dependencies count, as the definition names no exception.
    """
    resolved = _Resolved(codebase, index) if index is not None else None
    defined = {function.name for function in codebase.functions}
    result = {}
    for type_def in codebase.types:
        methods = production_methods(type_def)
        own_names = {method.name for method in methods}
        called_names: set[str] = set()
        called_functions: set[Function] = set()
        for method in methods:
            names = {call.name for call in method.calls() if not call.name[:1].isupper()}
            if resolved is None:
                called_names |= names - own_names
            else:
                called_functions |= resolved.called[method]
                called_names |= names - defined
        result[type_def] = len(methods) + len(called_names) + len(called_functions - set(methods))
    return result
