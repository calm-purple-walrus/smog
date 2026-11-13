"""Crate measurements on the public interface: its size and how much of it is documented and has an example."""

import re

from smog.domain.code import Crate, Function, ImplBlock, Item, Module, SourceFile, TraitDef, TypeDef
from smog.domain.graph import use_paths
from smog.domain.lenses.crate_dependencies import LockGraph
from smog.domain.lenses.exports import Exports
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.syntax import COMMENT_KINDS

_DOCUMENTED_KINDS = (
    "function_item", "function_signature_item", "struct_item", "enum_item", "union_item", "trait_item", "const_item", "static_item",
    "type_item", "mod_item",
)  # fmt: skip
_EXAMPLE_KINDS = ("function_item", "function_signature_item", "struct_item", "enum_item", "union_item", "trait_item")
_FENCE = re.compile(r"^\s*\*?\s*(```+|~~~+)(.*)$")
# What rustdoc accepts on a code fence and still compiles as Rust. `ignore` is left out on purpose.


def _production_modules(crate: Crate) -> list[Module]:
    return [module for module in crate.root.walk() if module.declaration is not None or any(not file.is_test for file in module.files)]


def _trait_methods(module: Module, exports: Exports) -> list[Function]:
    """Methods declared in the `pub` traits the module exports. They carry no `pub` of their own."""
    traits = {item.name for item in exports.api_items(module) if isinstance(item, TraitDef)}
    return [item for item in module.items if isinstance(item, Function) and item.in_trait and item.owner in traits and not item.in_test_code]


def public_api_items(crate: Crate, exports: Exports) -> int:
    """`pub` items of the crate that other crates can reach.

    The measurement list gives "number of public items". cargo-public-api prints one line per item of the public
    API and needs a nightly toolchain for rustdoc JSON, so it is not run; this count reads syntax. An item counts
    when it is marked exactly `pub`, sits outside test files and test modules, and `Exports` says it is exported:
    functions, methods of inherent impls, structs, enums, unions, traits, constants, statics, type aliases, `mod`
    declarations and `pub` macros. Not counted, though cargo-public-api lists them: fields, enum variants, trait
    methods, trait impls and `pub use` lines. crate.public_items stays as it is: every `pub` item, exported or
    not. `Exports` names where reading syntax differs from the compiler.
    """
    return sum(len(exports.api_items(module)) for module in _production_modules(crate))


def _module_has_inner_doc(module: Module) -> bool:
    """True when the module opens with a `//!` or `/*! */` comment."""
    if module.declaration is not None:
        first, last = module.declaration.start_line, module.declaration.end_line
        return any(comment.is_module_doc and first <= comment.start_line <= last for comment in module.declaration.file.comments)
    for file in module.files:
        first_item = min((item.start_line for item in file.items), default=file.line_count + 1)
        if any(comment.is_module_doc and comment.start_line < first_item for comment in file.comments):
            return True
    return False


def _variant_docs(type_def: TypeDef) -> list[bool]:
    """Per enum variant, whether a doc comment stands before it."""
    documented, pending = [], False
    for child in type_def.node.child("body").named:
        if child.kind in COMMENT_KINDS:
            pending = pending or child.child("doc") is not None
        elif child.kind == "enum_variant":
            documented.append(pending)
            pending = False
    return documented


def has_example(doc: str, patterns: tuple[str, ...] = DEFAULT_SETTINGS["rust_fence_patterns"]) -> bool:
    """True when a doc comment holds a fenced code block that rustdoc compiles as a Rust example.

    rustdoc counts an item as having an example when it finds a code block that is Rust and not ignored
    (`find_testable_code` with `config.rust && config.ignore == Ignore::None`,
    src/librustdoc/passes/check_doc_test_visibility.rs, read 2026-11-10). Here a fence of three or more backticks
    or tildes opens a block; it is Rust when every word after the fence matches one of `rust_fence_patterns`: by
    default `rust`, `should_panic`, `no_run`, `compile_fail`, `standalone_crate`, `test_harness`, an `edition…`
    or an error code such as `E0308`. A fence without a word is Rust. A block marked `ignore`, `text` or with another language is no example. An indented code block,
    which rustdoc also compiles, is not seen.
    """
    inside = False
    for line in doc.splitlines():
        match = _FENCE.match(line)
        if not match:
            continue
        if inside:
            inside = False
            continue
        inside = True
        words = [word for word in re.split(r"[,\s{}]+", match.group(2).strip()) if word]
        if all(any(re.fullmatch(pattern, word) for pattern in patterns) for word in words):
            return True
    return False


def _is_documented(item: Item, module: Module) -> bool:
    if item.doc.strip():
        return True
    if item.kind != "mod_item":
        return False
    child = next((child for child in module.children if child.path[-1] == item.name), None)
    return child is not None and _module_has_inner_doc(child)


def documentation_counts(crate: Crate, exports: Exports, settings: dict = DEFAULT_SETTINGS) -> tuple[int, int, int, int]:
    """(documented items, items, items with an example, items that can have one) of the crate's public interface.

    The measures are those of `rustdoc --show-coverage`: the documented items of the public interface, and the
    items with a code example among those that can have one (counting rules read 2026-11-10 from
    src/librustdoc/passes/calculate_doc_coverage.rs at tag 1.92.0 and check_doc_test_visibility.rs). The option
    needs a nightly toolchain, so the counts are taken from the syntax tree.

    Counted as items, as rustdoc does: the crate root (documented by `//!` at the top of its root file), and
    every exported `pub` function, inherent method, struct, enum, union, trait, constant, static, type alias and
    module (`Exports`), the methods of exported traits, the named `pub` fields of exported structs and the
    variants of exported enums. As in rustdoc, `use` declarations, impl blocks and methods of trait impls are not
    counted, and tuple fields are not. An item is documented when it has a `///` or `/** */` comment with text;
    a module also when it opens with `//!`.

    An example can be had by functions, methods, structs, enums, unions and traits; rustdoc leaves out fields,
    variants, type aliases, statics, constants, modules and impl blocks (`should_have_doc_example`).
    `has_example` says what an example is.

    Differences from rustdoc: `#[doc = "..."]` attributes, `#[doc(hidden)]`, `#[allow(missing_docs)]`, macros,
    fields of enum variants, associated constants and types, and items a macro generates are not read. Which
    items are exported is read from syntax, so a `pub` item in a private module that only leaks through a
    signature is left out, and `cfg` is not evaluated.
    """
    documented = total = with_example = can_have_example = 0
    for module in _production_modules(crate):
        items = [item for item in exports.api_items(module) if item.kind in _DOCUMENTED_KINDS]
        entries = [(item, _is_documented(item, module)) for item in [*items, *_trait_methods(module, exports)]]
        total += len(entries)
        documented += sum(1 for _, has_docs in entries if has_docs)
        examples = [item for item, _ in entries if item.kind in _EXAMPLE_KINDS]
        can_have_example += len(examples)
        with_example += sum(1 for item in examples if has_example(item.doc, settings["rust_fence_patterns"]))
        for item in items:
            if isinstance(item, TypeDef):
                parts = _variant_docs(item) if item.is_enum else [bool(field.doc.strip()) for field in item.fields if field.visibility == "pub" and not field.name.isdigit()]
                total += len(parts)
                documented += sum(parts)
    if total or any(not file.is_test for file in crate.root.files):
        total += 1
        documented += _module_has_inner_doc(crate.root)
    return documented, total, with_example, can_have_example


def measure_api(crate: Crate, exports: Exports, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    """crate.public_api_items, crate.documentation_coverage and crate.example_coverage.

    The two coverages are shares from 0 to 1 of `documentation_counts`. A crate with nothing to count has no
    value for a share.
    """
    documented, total, with_example, can_have_example = documentation_counts(crate, exports, settings)
    values: dict[str, float] = {"crate.public_api_items": public_api_items(crate, exports)}
    if total:
        values["crate.documentation_coverage"] = documented / total
    if can_have_example:
        values["crate.example_coverage"] = with_example / can_have_example
    return values


def _interface_tokens(crate: Crate, exports: Exports) -> list[tuple[SourceFile, list[str]]]:
    """Per piece of the crate's public interface, its file and the tokens that name types."""
    found = []
    exported_types = set()
    for module in _production_modules(crate):
        for item in exports.api_items(module):
            if isinstance(item, Function):
                tokens = item.signature_tokens()
            elif isinstance(item, TypeDef) and not item.is_enum:
                tokens = [token for field in item.fields if field.visibility == "pub" for token in re.findall(r"\w+|::", field.type_text)]
            elif item.kind in ("const_item", "static_item"):
                tokens = item.node.token_texts()
                tokens = tokens[: tokens.index("=")] if "=" in tokens else tokens
            elif item.kind == "trait_item":
                bounds = item.node.child("bounds")
                tokens = bounds.token_texts() if bounds else []
            elif item.kind in ("enum_item", "type_item"):
                tokens = item.node.token_texts()
            else:
                continue
            found.append((item.file, tokens))
            if isinstance(item, (TypeDef, TraitDef)):
                exported_types.add(item.name)
        found.extend((method.file, method.signature_tokens()) for method in _trait_methods(module, exports))
    for module in _production_modules(crate):
        for item in module.items:
            if isinstance(item, ImplBlock) and item.trait_name and item.type_name in exported_types and not item.in_test_code:
                found.append((item.file, item.node.child("trait").token_texts()))
    return found


def _imported_from(file: SourceFile, dependencies: set[str]) -> dict[str, str]:
    """Name to dependency for each name a `use` in the file brings in from one of the dependencies."""
    names = {}
    for node in file.root.find("use_declaration"):
        for path in use_paths(node.child("argument")):
            if len(path) > 1 and path[0] in dependencies:
                names[path[-1]] = path[0]
    return names


def exposed_dependencies(crate: Crate, exports: Exports, lock: LockGraph) -> dict[str, float]:
    """External dependencies whose types appear in the crate's public interface, and those of them below 1.0.

    The rule is C-STABLE of the Rust API Guidelines: "Public dependencies are crates from which types are used
    in the public API of the current crate", and "A crate cannot be stable (>=1.0.0) without all of its public
    dependencies being stable" (Necessities chapter, read 2026-11-10). rustc's `exported_private_dependencies`
    lint finds the same leaks and needs the nightly `public-dependency` feature (rustc book, warn-by-default
    lints, read 2026-11-10), so the syntax is read instead.

    The public interface is, for the items the crate exports (`Exports`): the signature of each `pub` function,
    inherent method and method of an exported trait; the types of `pub` fields of structs and unions; every
    token of a `pub` enum and of a `pub` type alias; the type of a `pub` constant or static; the supertraits of a
    `pub` trait; and, as in the guideline's `From` example, the trait named by each trait impl for an exported
    type. A normal external dependency is exposed when one of these holds a path that starts with the
    dependency's name (`dep::Thing`), or a name that a `use dep::...` in the same file brings in.

    crate.exposed_dependencies counts such dependencies; crate.leaked_external_types stays and counts functions.
    crate.exposed_unstable_dependencies counts those whose version in Cargo.lock starts with `0.`; it has no
    value when the lock file does not list the crate.

    Not seen: a name imported with `as` or through a glob, a dependency renamed in Cargo.toml or whose library
    name differs from its package name, a type that reaches the interface through a type alias or a re-export of
    another module, generic bounds in a `where` clause of a type, and types in macro-made items. Workspace crates
    are not counted: they are released together.
    """
    dependencies = {name.replace("-", "_"): name for name in crate.external_dependencies()}
    exposed = set()
    imports: dict[str, dict[str, str]] = {}
    for file, tokens in _interface_tokens(crate, exports):
        if file.path not in imports:
            imports[file.path] = _imported_from(file, set(dependencies))
        for index, token in enumerate(tokens):
            if token in dependencies and tokens[index + 1 : index + 2] == ["::"]:
                exposed.add(dependencies[token])
            elif token in imports[file.path] and tokens[index - 1 : index] != ["::"]:
                exposed.add(dependencies[imports[file.path][token]])
    values: dict[str, float] = {"crate.exposed_dependencies": len(exposed)}
    if lock.lists(crate):
        versions = {package.name: package.version for package in lock.needed_by(crate, ("normal",))}
        values["crate.exposed_unstable_dependencies"] = sum(1 for name in exposed if versions.get(name, "").startswith("0."))
    return values
