"""Struct and enum lenses (design section 3.3)."""

import re
from collections import Counter, defaultdict
from itertools import combinations

from smog.domain.code import Codebase, Function, TypeDef
from smog.domain.lenses.type_shape import bool_fields, exhaustive, hiding_values, public_field_share, type_expression_complexity
from smog.domain.settings import DEFAULT_SETTINGS

_REFERENCE = re.compile(r"^&\s*(?:'\w+\s+)?(?:mut\s+)?")


def is_primitive(type_text: str, settings: dict = DEFAULT_SETTINGS) -> bool:
    for wrapper in settings["primitive_wrapper_types"]:
        if type_text.startswith(wrapper + "<") and type_text.endswith(">"):
            return is_primitive(type_text[len(wrapper) + 1 : -1], settings)
    return type_text in settings["primitive_types"]


def is_primitive_or_reference_to_one(type_text: str, settings: dict = DEFAULT_SETTINGS) -> bool:
    """`is_primitive` after removing one leading `&`, with its lifetime and `mut`: `&'a str` and `&mut u64` are primitive."""
    return is_primitive(_REFERENCE.sub("", type_text), settings)


def _states_invariant(doc: str, words: tuple[str, ...]) -> bool:
    return bool(words) and bool(re.search(r"\b(" + "|".join(map(re.escape, words)) + r")\b", doc, re.IGNORECASE))


def _instance_methods(type_def: TypeDef) -> list[Function]:
    return [m for m in type_def.methods if m.body is not None and any(p.is_self for p in m.params)]


def lcom4(type_def: TypeDef) -> int:
    """Connected components among instance methods, joined by a shared field or a direct call."""
    methods = _instance_methods(type_def)
    parent = {method.name: method.name for method in methods}

    def find(name):
        while parent[name] != name:
            name = parent[name]
        return name

    for left, right in combinations(methods, 2):
        linked = left.self_fields() & right.self_fields() or right.name in left.self_calls() or left.name in right.self_calls()
        if linked:
            parent[find(left.name)] = find(right.name)
    return len({find(name) for name in parent})


def tcc(type_def: TypeDef) -> float:
    """Share of instance method pairs that use a common field."""
    methods = _instance_methods(type_def)
    pairs = list(combinations(methods, 2))
    if not pairs:
        return 1.0
    return sum(1 for left, right in pairs if left.self_fields() & right.self_fields()) / len(pairs)


def _is_constructor_with_checks(method: Function) -> bool:
    if method.body is None or "Self" not in method.return_text or any(p.is_self for p in method.params):
        return False
    return method.body.contains("if_expression", "match_expression", "try_expression") or any(
        "assert" in node.child("macro").text for node in method.body.find("macro_invocation")
    )


def _public_invariant_fields(type_def: TypeDef, words: tuple[str, ...]) -> int:
    public = [field for field in type_def.fields if field.visibility.startswith("pub")]
    if not public:
        return 0
    if any(_is_constructor_with_checks(method) for method in type_def.methods):
        return len(public)
    guarded = set()
    for method in type_def.methods:
        for node in method.body.find("if_expression", "macro_invocation") if method.body else ():
            tree = node.child("condition") if node.kind == "if_expression" else node
            if node.kind == "if_expression" or "assert" in node.child("macro").text:
                guarded.update(tree.token_texts())
    return sum(1 for field in public if field.name in guarded or _states_invariant(field.doc, words))


def _is_trivial_setter(method: Function) -> bool:
    if method.body is None or not method.name.startswith("set_"):
        return False
    statements = method.body.statements
    if len(statements) != 1:
        return False
    inner = statements[0].named[0] if statements[0].kind == "expression_statement" and statements[0].named else statements[0]
    return inner.kind == "assignment_expression" and inner.child("left").kind == "field_expression"


def _is_trivial_getter(method: Function, field: str) -> bool:
    if method.body is None or method.name not in (field, f"get_{field}") or len(method.body.statements) != 1:
        return False
    return re.fullmatch(rf"&?\s*self\.{re.escape(field)}(\.clone\(\))?", method.body.statements[0].text) is not None


def _empty_encapsulation(type_def: TypeDef) -> int:
    count = 0
    for field in type_def.fields:
        if field.visibility:
            continue
        has_setter = any(m.name == f"set_{field.name}" and _is_trivial_setter(m) for m in type_def.methods)
        has_getter = any(_is_trivial_getter(m, field.name) for m in type_def.methods)
        count += has_setter and has_getter
    return count


_PLAIN_GETTER = re.compile(r"&?\s*(?:mut\s+)?self\.\w+(?:\.clone\(\))?")


def _is_accessor(method: Function) -> bool:
    """A plain setter (`set_x` with one assignment to a field) or a plain getter: `self` is the only parameter and
    the body is `self.x`, `&self.x`, `&mut self.x` or `self.x.clone()`, whatever the method is called."""
    if _is_trivial_setter(method):
        return True
    if method.body is None or len(method.params) != 1 or not method.params[0].is_self or len(method.body.statements) != 1:
        return False
    return _PLAIN_GETTER.fullmatch(method.body.statements[0].text) is not None


def _is_constructor(method: Function, type_name: str) -> bool:
    returned = set(re.findall(r"\w+", method.return_text))
    return not any(p.is_self for p in method.params) and bool(returned & {"Self", type_name})


def data_class(type_def: TypeDef, wmc: float, settings: dict = DEFAULT_SETTINGS) -> int:
    """1 for a data class by the detection rule of Lanza and Marinescu, else 0.

    Source: PMD's `DataClassRule.java` and the metric texts in PMD's `JavaMetrics.java`, read 2026-11-10; they
    implement "Object-Oriented Metrics in Practice" (Lanza and Marinescu 2006), which was not opened itself. The
    rule is WOC < 1/3 and ((NOPA + NOAM > 3 and WMC < 31) or (NOPA + NOAM > 5 and WMC < 47)). Each number is a
    setting.

    - NOPA: fields declared `pub`. `pub(crate)` does not count.
    - NOAM: public accessor methods, see `_is_accessor`.
    - WOC, weight of class: "functional" public methods divided by all public methods, where constructors,
      getters and setters are not functional. 0 for a type without a public method.
    - WMC: type.wmc.

    A public method is a `pub` method of an inherent `impl`, or any method of a trait `impl`, outside test code.
    A constructor is an associated function without `self` whose return type names `Self` or the type, so
    `Default::default` and `From::from` are constructors. Derived traits are not seen. An enum has no fields
    here, so it is never a data class. The rule flags plain data structs, which Rust code uses on purpose.
    """
    public = [m for m in type_def.methods if not m.in_test_code and (m.is_trait_impl or m.visibility == "pub")]
    accessors = sum(1 for m in public if _is_accessor(m))
    functional = sum(1 for m in public if not _is_accessor(m) and not _is_constructor(m, type_def.name))
    weight = functional / len(public) if public else 0.0
    revealed = sum(1 for f in type_def.fields if f.visibility == "pub") + accessors
    few = revealed > settings["data_class_accessors_above"] and wmc < settings["data_class_complexity_below"]
    many = revealed > settings["data_class_many_accessors_above"] and wmc < settings["data_class_high_complexity_below"]
    return int(weight < settings["data_class_weight_below"] and (few or many))


def lazy_class(type_def: TypeDef, settings: dict = DEFAULT_SETTINGS) -> int:
    """1 for a type with at most `lazy_class_max_methods` methods and at most `lazy_class_max_lines` lines, else 0.

    Fowler names the smell ("Refactoring", 1999) and gives no numbers, and no detection rule from a paper was
    read. The rule and its defaults, 1 method and 10 lines, are those of the Rust crate cha-core 1.7.1
    (`src/plugins/lazy_class.rs`, read 2026-11-10), which skips interfaces; a trait is no type piece here.
    Methods are the functions in the type's `impl` blocks outside test code, trait impls included; derived
    traits add none. Lines are the code lines of the definition plus those of these methods. A type in test
    code scores 0. The rule flags newtypes, markers and small enums, which Rust code uses on purpose.
    """
    if type_def.in_test_code:
        return 0
    methods = [method for method in type_def.methods if not method.in_test_code]
    lines = type_def.lines + sum(method.lines for method in methods)
    return int(len(methods) <= settings["lazy_class_max_methods"] and lines <= settings["lazy_class_max_lines"])


def measure_type(type_def: TypeDef, method_values: dict[str, dict], settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    methods = type_def.methods
    fields = type_def.fields
    wmc = sum(method_values.get(m.qualified, {}).get("function.cyclomatic", 0) for m in methods)
    atfd = sum(method_values.get(m.qualified, {}).get("function.foreign_fields", 0) for m in methods)
    cohesion = tcc(type_def)
    primitive_share = sum(is_primitive_or_reference_to_one(f.type_text, settings) for f in fields) / len(fields) if len(fields) >= settings["primitive_share_min_fields"] else 0.0
    return {
        "type.fields": len(fields),
        "type.methods": len(methods),
        "type.variants": len(type_def.variants),
        "type.lcom4": lcom4(type_def),
        "type.on_off_fields": sum(1 for f in fields if f.type_text == "bool" or f.type_text.startswith("Option<")),
        "type.bool_fields": bool_fields(type_def),
        "type.public_field_share": public_field_share(type_def),
        **hiding_values(type_def),
        "type.type_complexity": type_expression_complexity(type_def, settings),
        "type.exhaustive": exhaustive(type_def),
        "type.primitive_share": primitive_share,
        "type.public_invariant_fields": _public_invariant_fields(type_def, settings["invariant_words"]),
        "type.plain_setters": sum(1 for m in methods if _is_trivial_setter(m)),
        "type.empty_encapsulation": _empty_encapsulation(type_def),
        "type.wmc": wmc,
        "type.tcc": cohesion,
        "type.god_type": int(
            atfd > settings["god_type_foreign_fields_above"] and wmc >= settings["god_type_min_complexity"] and cohesion < settings["god_type_cohesion_below"]
        ),
        "type.data_class": data_class(type_def, wmc, settings),
        "type.lazy_class": lazy_class(type_def, settings),
        "type.missing_traits": int(
            type_def.is_public and "Debug" not in type_def.derives and not any(m.trait_name == "Debug" for m in methods)
        ),
    }


def _literal_states(node) -> dict | None:
    body = node.child("body")
    if body is None or body.contains("base_field_initializer"):
        return None
    states = {}
    for initializer in body.named:
        if initializer.kind == "field_initializer":
            value = initializer.child("value")
            if value.kind == "identifier" and value.text == "None":
                states[initializer.child("field").text] = False
            elif value.kind == "call_expression" and value.child("function").text == "Some":
                states[initializer.child("field").text] = True
    return states


def correlated_option_fields(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> dict[str, int]:
    """Option field pairs per struct that are always equal or never both `Some` across struct literals."""
    literals = defaultdict(list)
    for function in codebase.functions:
        for node in function.body.find("struct_expression") if function.body else ():
            states = _literal_states(node)
            if states is not None:
                literals[node.child("name").text].append(states)
    counts: dict[str, int] = {}
    for type_def in codebase.types:
        options = [f.name for f in type_def.fields if f.type_text.startswith("Option<")]
        seen = literals.get(type_def.name, [])
        flagged = 0
        for left, right in combinations(options, 2):
            known = [(states[left], states[right]) for states in seen if left in states and right in states]
            if len(known) >= settings["correlated_options_min_literals"] and (all(a == b for a, b in known) or not any(a and b for a, b in known)):
                flagged += 1
        counts[type_def.qualified] = flagged
    return counts


def foreign_field_access(codebase: Codebase) -> dict[str, int]:
    """Field reads and writes outside the struct's module, matched by field name. Shared names are skipped."""
    owners = Counter(field.name for type_def in codebase.types for field in type_def.fields)
    accesses = defaultdict(Counter)
    for function in codebase.functions:
        for node in function.body.find("field_expression") if function.body else ():
            if node.child("field").kind == "field_identifier":
                accesses[node.child("field").text][function.module_path] += 1
    result = {}
    for type_def in codebase.types:
        total = 0
        for field in type_def.fields:
            if owners[field.name] == 1:
                total += sum(n for module, n in accesses[field.name].items() if module != type_def.module_path)
        result[type_def.qualified] = total
    return result


def data_clumps(codebase: Codebase, settings: dict = DEFAULT_SETTINGS) -> list[tuple[frozenset, int]]:
    """Sets of at least `data_clumps_min_size` (name, type) pairs shared by at least two structs or signatures."""
    min_size = settings["data_clumps_min_size"]
    groups = []
    for type_def in codebase.types:
        groups.append(frozenset((field.name, field.type_text) for field in type_def.fields))
    for function in codebase.functions:
        if not function.in_test_code:
            groups.append(frozenset((p.name, p.type_text) for p in function.params if not p.is_self))
    groups = [group for group in groups if len(group) >= min_size]
    overlaps = Counter()
    for left, right in combinations(groups, 2):
        shared = left & right
        if len(shared) >= min_size:
            overlaps[shared] += 1
    return list(overlaps.items())
