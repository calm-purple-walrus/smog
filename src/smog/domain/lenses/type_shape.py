"""Type measurements that read the definition: field visibility, field types and attributes."""

from smog.domain.code import FieldDef, Function, TypeDef
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.syntax import Node

_TYPE_KINDS = frozenset(
    {
        "reference_type", "pointer_type", "primitive_type", "type_identifier", "unit_type", "scoped_type_identifier", "generic_type",
        "tuple_type", "array_type", "function_type", "dynamic_type", "abstract_type", "bounded_type",
    }
)  # fmt: skip


def public_field_share(type_def: TypeDef) -> float:
    """Fields declared `pub` divided by all fields. 0 for a type without fields.

    The count is NPA, "the number of public attributes" (rust-code-analysis metric list, read 2026-11-10), as a
    share, for the Rust API guideline C-STRUCT-PRIVATE. Named fields, tuple fields and union fields count alike.
    `pub(crate)`, `pub(super)` and `pub(in path)` do not count: they show the field inside the crate only. An enum
    scores 0, because the fields of a variant are always as visible as the enum. The struct's own visibility is not
    read, so a `pub` field of a private struct counts.
    """
    fields = type_def.fields
    return sum(1 for field in fields if field.visibility == "pub") / len(fields) if fields else 0.0


def _is_hidden(visibility: str) -> bool:
    return visibility in ("", "pub(self)")


def hidden_fields(type_def: TypeDef) -> tuple[int, int]:
    """(hidden fields, defined fields): the type's terms A_h and A_d of the Attribute Hiding Factor.

    MOOD, Brito e Abreu, Goulão and Esteves, "Toward the Design Quality Evaluation of Object-Oriented Software
    Systems" (1995, revised version read 2026-11-10): AHF is the sum of A_h(C_i) over the sum of A_d(C_i), where
    hidden attributes are the data members in private and protected clauses and visible ones those in the public
    clause. Here a field is hidden when it has no visibility modifier or `pub(self)`, and visible with `pub`,
    `pub(crate)`, `pub(super)` or `pub(in path)`. Rust privacy ends at the module, not the type, so a hidden field
    can still be read by other types in the same module. Enums define no fields here.
    """
    fields: list[FieldDef] = type_def.fields
    return sum(1 for field in fields if _is_hidden(field.visibility)), len(fields)


def production_methods(type_def: TypeDef) -> list[Function]:
    """The methods of a type outside test code."""
    return [method for method in type_def.methods if not method.in_test_code]


def hidden_methods(type_def: TypeDef) -> tuple[int, int]:
    """(hidden methods, defined methods): the type's terms M_h and M_d of the Method Hiding Factor.

    Same source as `hidden_fields`: MHF is the sum of M_h(C_i) over the sum of M_d(C_i); methods are the function
    members, constructors and operators included, and inherited methods do not count. Here the methods are the
    functions in the type's `impl` blocks, associated functions included. A method in an inherent `impl` is hidden
    when it has no visibility modifier or `pub(self)`. A method in a trait `impl` is visible: it can be called
    wherever the trait is, and the trait's own visibility is not read. Methods in test code, such as an `impl`
    inside a `#[cfg(test)]` module, are left out. Methods a macro generates are not seen.
    """
    methods = production_methods(type_def)
    return sum(1 for method in methods if not method.is_trait_impl and _is_hidden(method.visibility)), len(methods)


def hiding_values(type_def: TypeDef) -> dict[str, float]:
    """type.attribute_hiding and type.method_hiding. A type without fields, or without methods, has no value for that one."""
    values = {}
    for metric_id, (hidden, defined) in (("type.attribute_hiding", hidden_fields(type_def)), ("type.method_hiding", hidden_methods(type_def))):
        if defined:
            values[metric_id] = hidden / defined
    return values


def hiding_factors(types: list[TypeDef]) -> dict[str, float]:
    """codebase.attribute_hiding_factor and codebase.method_hiding_factor: hidden over defined, summed over all types.

    A codebase without fields, or without methods, has no value for that factor.
    """
    values = {}
    for metric_id, count in (("codebase.attribute_hiding_factor", hidden_fields), ("codebase.method_hiding_factor", hidden_methods)):
        counts = [count(type_def) for type_def in types]
        defined = sum(total for _, total in counts)
        if defined:
            values[metric_id] = sum(hidden for hidden, _ in counts) / defined
    return values


def bool_fields(type_def: TypeDef) -> int:
    """Fields whose type is written exactly `bool`, as Clippy's `struct_excessive_bools` counts them.

    Source: `clippy_lints/src/excessive_bools.rs`, read 2026-11-10. Clippy reports a struct with more than
    `max-struct-bools` such fields and skips structs with a `#[repr]` attribute; this is the count itself, for
    every struct and union, `#[repr]` or not. `Option<bool>`, `&bool` and an alias of `bool` do not count. The
    fields of enum variants are not counted, as in Clippy.
    """
    return sum(1 for field in type_def.fields if field.type_text == "bool")


def _field_types(type_def: TypeDef) -> list[Node]:
    """Type nodes of the fields of a struct or union and of the fields of every enum variant."""
    body = type_def.node.child("body")
    if body is None:
        return []
    types = [declaration.child("type") for declaration in body.find("field_declaration")]
    for tuple_fields in body.find("ordered_field_declaration_list"):
        types.extend(child for child in tuple_fields.children if child.field == "type")
    return types


def _inner(node: Node, nest: int, scores: dict) -> int:
    """Score of the types written inside a node that is not a type itself, such as type arguments."""
    total = 0
    for child in node.children:
        if child.kind == "type_binding":
            total += type_score(child.child("type"), nest, scores)
        elif child.field == "alias":
            total += _trait(child, nest, scores)
        elif child.kind in _TYPE_KINDS:
            total += type_score(child, nest, scores)
        elif child.kind != "lifetime":
            total += _inner(child, nest, scores)
    return total


def _trait(node: Node, nest: int, scores: dict) -> int:
    """Score of the types inside a trait bound. The trait's own name is no type and adds nothing."""
    if node.kind == "generic_type":
        return _inner(node.child("type_arguments"), nest, scores)
    if node.kind == "higher_ranked_trait_bound":
        return _trait(node.child("type"), nest, scores)
    if node.kind == "function_type":
        return _call_sugar(node, nest, scores)
    return 0


def _call_sugar(node: Node, nest: int, scores: dict) -> int:
    """Types in `Fn(A) -> B` written as a trait bound. `Fn` is the trait's name."""
    return sum(_inner(child, nest, scores) if child.kind == "parameters" else type_score(child, nest, scores) for child in node.children if child.field != "trait" and child.is_named)


def _bounds(nodes: list[Node], nest: int, scores: dict) -> int:
    return sum(_trait(node, nest, scores) for node in nodes if node.is_named and node.kind != "lifetime")


def _trait_object(bounds: list[Node], nest: int, scores: dict) -> int:
    if any(bound.kind == "higher_ranked_trait_bound" for bound in bounds):
        return scores["type_complexity_function_score"] * nest + _bounds(bounds, nest + 1, scores)
    return scores["type_complexity_trait_object_score"] * nest + _bounds(bounds, nest, scores)


def type_score(node: Node, nest: int = 1, scores: dict = DEFAULT_SETTINGS) -> int:
    """Score of one written type by the rule of Clippy's `type_complexity`.

    Source: `clippy_lints/src/types/type_complexity.rs`, read 2026-11-10. The four
    `type_complexity_*_score` settings hold Clippy's constants, which the list below states. Starting at
    nesting 1, each part of the type adds a score and may raise the nesting for the parts inside it:

    - a reference or raw pointer adds 1 and keeps the nesting;
    - a named type, primitive, `Self`, tuple, `()`, array or slice adds 10 times the nesting and raises it by 1;
    - an `fn` pointer adds 50 times the nesting and raises it by 1; an `extern` one adds nothing;
    - `dyn A + B` adds 20 times the nesting and keeps it; with a `for<'a>` bound it adds 50 times the nesting
      and raises it by 1;
    - `impl Trait`, `!`, lifetimes and trait names add nothing. Types written in their arguments are scored.

    `Vec<Vec<Box<(u32, u32, u32, u32)>>>` scores 10 + 20 + 30 + 40 + 4 x 50 = 300. Clippy's default limit is 250.
    A type written by a macro call scores 0. Clippy resolves no alias either, so an alias hides what it stands for.
    """
    kind = node.kind
    if kind in ("reference_type", "pointer_type"):
        return scores["type_complexity_reference_score"] + _inner(node, nest, scores)
    if kind in ("primitive_type", "type_identifier", "unit_type"):
        return scores["type_complexity_type_score"] * nest
    if kind == "generic_type":
        return scores["type_complexity_type_score"] * nest + _inner(node.child("type_arguments"), nest + 1, scores) + _path_arguments(node.child("type"), nest + 1, scores)
    if kind == "scoped_type_identifier":
        return scores["type_complexity_type_score"] * nest + _path_arguments(node, nest + 1, scores)
    if kind in ("tuple_type", "array_type"):
        return scores["type_complexity_type_score"] * nest + _inner(node, nest + 1, scores)
    if kind == "function_type":
        if node.child_of_kind("fn") is None:
            return _call_sugar(node, nest, scores)
        if node.child_of_kind("function_modifiers") is not None and "extern" in node.child_of_kind("function_modifiers").text:
            return _inner(node, nest, scores)
        return scores["type_complexity_function_score"] * nest + _inner(node, nest + 1, scores)
    if kind == "dynamic_type":
        return _trait_object(node.named, nest, scores)
    if kind == "bounded_type":
        first, *others = _flat_bounds(node)
        if first.kind == "dynamic_type":
            return _trait_object([*first.named, *others], nest, scores)
        if first.kind == "abstract_type":
            return _bounds([*first.named, *others], nest, scores)
        return _inner(node, nest, scores)
    if kind == "abstract_type":
        return _bounds(node.named, nest, scores)
    return 0


def _flat_bounds(node: Node) -> list[Node]:
    """The parts of `dyn A + B + 'a`, which the grammar nests pair by pair."""
    parts = []
    for child in node.named:
        parts.extend(_flat_bounds(child) if child.kind == "bounded_type" else [child])
    return parts


def _path_arguments(node: Node, nest: int, scores: dict) -> int:
    """Types inside the path of a named type, such as `T` in `<T as Trait>::Out` or `A` in `a::B<A>::C`. The last name is the type itself."""
    if node.kind != "scoped_type_identifier":
        return 0
    path = node.child("path")
    return _inner(path, nest, scores) if path is not None and path.children else 0


def type_expression_complexity(type_def: TypeDef, settings: dict = DEFAULT_SETTINGS) -> int:
    """The highest `type_score` among the types written for the type's fields. 0 for a type without fields.

    The fields of a struct or union and the fields of every enum variant are read. Clippy checks each written
    type against its limit, in fields, signatures and `let` statements; this takes the worst field of one type.
    """
    return max((type_score(node, 1, settings) for node in _field_types(type_def)), default=0)


def exhaustive(type_def: TypeDef) -> int:
    """1 for a `pub` struct or enum without `#[non_exhaustive]`, else 0.

    Source: Clippy's `exhaustive_structs` and `exhaustive_enums`, `clippy_lints/src/exhaustive_items.rs`, read
    2026-11-10. As there, a struct counts only when every field is `pub`, which includes a struct without fields:
    a private field already stops code outside from building or matching the struct in full. An enum counts
    whatever its variants hold. A union never counts. `#[cfg_attr(..., non_exhaustive)]` counts as the attribute.
    Clippy asks whether the item is exported from the crate; this reads `pub` as written, so a `pub` type in a
    private module counts. A type in test code scores 0.
    """
    if not type_def.is_public or type_def.in_test_code or type_def.has_attribute(r"\bnon_exhaustive\b"):
        return 0
    if type_def.is_enum:
        return 1
    return int(type_def.is_struct and all(field.visibility == "pub" for field in type_def.fields))
