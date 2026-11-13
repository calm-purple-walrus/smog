"""Module measurements that read the module's own name and items."""

from smog.domain.code import Function, Module
from smog.domain.lenses.exports import Exports
from smog.domain.lenses.function import is_forwarded, single_call
from smog.domain.lenses.structure import module_public_items
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import LintWarning


def catch_all_name(module: Module, names: tuple = DEFAULT_SETTINGS["catch_all_names"]) -> int:
    """1 when the module's own name is one of `names` (setting `catch_all_names`), compared whole and with case.

    The idea is revive's `package-naming` rule for Go: "Bad package names from the official Go blog (e.g.,
    `common`, `util`, `utils`, `misc`, `interfaces`, `types`)", with `helpers`, `models`, `shared` and `utilities`
    as an optional extra list (revive RULES_DESCRIPTIONS.md, read 2026-11-10). No Rust tool has such a rule.
    Smog's default list is `util`, `utils`, `helper`, `helpers`, `common`, `misc`, `shared`: `types`, `models` and
    `interfaces` are left out because they are common and specific enough in Rust crates. A crate root has no
    module name and scores 0. check.catch_all_names uses the same list on modules and on file path segments.
    """
    return int(bool(module.path) and module.path[-1] in names)


def name_repetition(module: Module) -> int:
    """1 when the module has the same name as its parent module, as in `foo::foo`.

    This is Clippy's `module_inception`: "module has the same name as its containing module"
    (clippy_lints/src/item_name_repetitions.rs, read 2026-11-10). Like the lint with its default configuration,
    the rule covers private modules too and does not compare a module with its crate's name, so a crate root and
    its direct children always score 0. Names are compared whole: `user::user_store` scores 0. Modules come from
    file paths, so `foo/foo.rs` scores 1 even if `foo` has no module file, and an inline `mod foo { mod foo { } }`
    scores 1 on the inner module.
    """
    path = module.path
    return int(len(path) >= 2 and path[-1] == path[-2])


def public_structs(module: Module) -> int:
    """Structs marked exactly `pub` that the module declares itself.

    The measure is revive's `max-public-structs` for Go: "Packages declaring too many public structs can be hard
    to understand/use, and could be a symptom of bad design" (revive RULES_DESCRIPTIONS.md, read 2026-11-10);
    revive counts per file and warns above 5. Here the unit is the module. Unit and tuple structs count; enums,
    unions and traits do not; `pub(crate)` and `pub(super)` structs do not. Structs in test files, in test
    modules and in submodules, inline ones included, are not counted. A `pub` struct in a private module counts.
    """
    return sum(1 for item in module_public_items(module) if item.kind == "struct_item")


def _delegates(method: Function) -> bool:
    expression = single_call(method)
    if expression is None or expression.child("function").contains("call_expression"):
        return False
    names = {param.name for param in method.params if not param.is_self}
    return all(_is_handed_on(argument, names) for argument in expression.child("arguments").named)


def _is_handed_on(argument, names: set[str]) -> bool:
    while argument.kind == "reference_expression" and argument.named:
        argument = argument.named[-1]
    if argument.kind == "self":
        return True
    if argument.kind == "field_expression":
        return argument.child("value").kind == "self"
    return is_forwarded(argument, names)


def delegation_share(module: Module) -> float:
    """Methods that only call one other function, divided by all methods the module declares itself.

    The measurement list gives the rule as "methods that only call another method / methods". Fowler names the
    smell Middle Man; no source with a counting rule was opened, so the rule below is Smog's.

    A method is a function with a body inside an `impl` block, inherent or of a trait, or a default method of a
    trait; test code is left out. It delegates when its body is one statement that is one call, with or without
    `;` or `?`, and:

    - the call builds no value (`Self(a)`, `Some(a)`, `Meters(a)` are no delegation);
    - the receiver or callee holds no further call (`self.inner.len()` delegates, `self.lock().len()` does not);
    - every argument is `self`, a field of `self`, or a parameter, each possibly behind `&`, `&mut`, `?` or
      `.into()`. A call without arguments counts, unlike function.pass_through, which needs at least one.

    A macro call is not parsed and never counts. 0 for a module without methods.
    """
    methods = [item for item in module.items if isinstance(item, Function) and item.owner and item.body is not None and not item.in_test_code]
    return sum(1 for method in methods if _delegates(method)) / len(methods) if methods else 0.0


def measure_shape(module: Module, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    return {
        "module.catch_all_name": catch_all_name(module, settings["catch_all_names"]),
        "module.name_repetition": name_repetition(module),
        "module.public_structs": public_structs(module),
        "module.delegation_share": delegation_share(module),
    }


def unreachable_pub(module: Module, exports: Exports) -> int:
    """Items marked exactly `pub` in the module that no other crate can reach, read from syntax.

    The measure is rustc's `unreachable_pub` lint, which "triggers for `pub` items not reachable from other
    crates - that means neither directly accessible, nor reexported (with `pub use`), nor leaked through things
    like return types" (rustc book, allowed-by-default lints, read 2026-11-10). With `--full` and the tool
    `clippy` the lint itself is run and replaces this count (`lint_unreachable_pub`).

    Without it, an item counts when `Exports` says it is not exported: its module is not reachable through `pub`
    modules from the crate root and no `pub use` in the crate names it, its type or a module around it. Counted
    items are those of module.public_items: functions, methods, types, traits, constants, statics, type aliases,
    `mod` declarations and macros marked `pub`. A `pub use` declaration counts once, as in the lint, when its
    module is not exported and no `pub use` in an exported module hands one of its names on. Not counted,
    though the lint reports them: `pub` fields. `pub(crate)` and `pub(super)` items are never counted.

    `Exports` lists the cases where names are matched as text. An item that reaches other crates only through
    the signature of an exported item is reachable for the compiler and counts here, so the count can be too
    high.
    """
    return len(exports.unreachable(module))


def lint_unreachable_pub(modules: list[Module], warnings: list[LintWarning]) -> dict[str, int]:
    """rustc's `unreachable_pub` warnings per module, by qualified module name.

    A warning belongs to the module that declares the line of its primary span: the deepest inline module around
    the line, else the module of the file. Every module with a production file or an inline declaration gets a
    value, 0 without a warning. A warning in a file Smog does not read is dropped.
    """
    by_path: dict[str, list[Module]] = {}
    for module in modules:
        for path in {file.path for file in module.files if not file.is_test} | ({module.declaration.file.path} if module.declaration else set()):
            by_path.setdefault(path, []).append(module)
    counts = {module.qualified: 0 for candidates in by_path.values() for module in candidates}
    for warning in warnings:
        candidates = [
            module
            for module in by_path.get(warning.path, ())
            if module.declaration is None or module.declaration.start_line <= warning.line <= module.declaration.end_line
        ]
        if candidates:
            counts[max(candidates, key=lambda module: len(module.path)).qualified] += 1
    return counts
