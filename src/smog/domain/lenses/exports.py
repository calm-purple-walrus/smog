"""Which `pub` items a crate exports, read from syntax."""

from smog.domain.code import Codebase, Function, ImplBlock, Item, Module
from smog.domain.graph import use_paths
from smog.domain.lenses.structure import module_public_items


class Exports:
    """Which modules and `pub` items other crates can reach, as far as syntax shows.

    A module is exported when it is a crate root, or when its parent is exported and its `mod` declaration is
    exactly `pub`. A declaration that is not found in the parent's own items, as for a module placed with
    `#[path]`, declared inside a macro call or below a folder without a module file, counts as `pub`.

    A `pub` item is exported when its module is exported, or when a `pub use` in a production file of the same
    crate ends in the item's name, in the name of the type whose impl block holds it, or in the name of one of
    the modules around it. `pub use a::b::*` ends in `b`, so it exports what `b` declares. `pub(crate) use`
    exports nothing.

    A `pub use` declaration is itself exported when its module is, or when a `pub use` in an exported module of
    the crate ends in one of the names it brings in or in the name of a module around it.

    Differences from the compiler: names are compared as text within a crate, so a `pub use` of another item with
    the same name counts. For an item, a `pub use` inside a module that is itself not exported counts as export:
    in practice such an item is handed out through the signature of something exported, which the compiler
    accepts as reachable and syntax cannot follow. An item that leaks only through a signature, with no `pub use`
    at all, counts as not exported. A binary crate is read like a library. `cfg` is not evaluated.
    """

    def __init__(self, codebase: Codebase):
        self._exported: set[tuple] = set()
        self._reexported: dict[str, set[str]] = {}
        self._reexported_outward: dict[str, set[str]] = {}
        for crate in codebase.crates:
            self._mark(crate.root)
            names = self._reexported.setdefault(crate.name, set())
            outward = self._reexported_outward.setdefault(crate.name, set())
            for module in crate.root.walk():
                for item in public_uses(module):
                    found = {path[-1] for path in use_paths(item.node.child("argument")) if path}
                    names.update(found)
                    if self.is_exported(module):
                        outward.update(found)

    def _mark(self, module: Module) -> None:
        self._exported.add((module.crate_name, module.path))
        declared = {item.name: item for item in module.items if item.kind == "mod_item"}
        for child in module.children:
            declaration = child.declaration or declared.get(child.path[-1])
            if declaration is None or declaration.is_public:
                self._mark(child)

    def is_exported(self, module: Module) -> bool:
        return (module.crate_name, module.path) in self._exported

    def exports(self, item: Item, module: Module) -> bool:
        """True when `item`, declared in `module`, can be reached from another crate."""
        if self.is_exported(module):
            return True
        names = self._reexported.get(module.crate_name, set())
        return _export_name(item, module) in names or any(segment in names for segment in module.path)

    def exports_use(self, item: Item, module: Module) -> bool:
        """True when the `pub use` declaration `item`, in `module`, hands its names on to other crates."""
        if self.is_exported(module):
            return True
        outward = self._reexported_outward.get(module.crate_name, set())
        brought = {path[-1] for path in use_paths(item.node.child("argument")) if path}
        return bool(brought & outward) or any(segment in outward for segment in module.path)

    def unreachable(self, module: Module) -> list[Item]:
        """The module's own `pub` items and `pub use` declarations that are not exported."""
        items = [item for item in module_public_items(module) if not self.exports(item, module)]
        return [*items, *(item for item in public_uses(module) if not self.exports_use(item, module))]

    def api_items(self, module: Module) -> list[Item]:
        """The module's own `pub` items that are exported."""
        return [item for item in module_public_items(module) if self.exports(item, module)]


def public_uses(module: Module) -> list[Item]:
    """The `pub use` declarations the module holds itself, outside test code."""
    return [item for item in module.items if item.kind == "use_declaration" and item.is_public and not item.in_test_code]


def _export_name(item: Item, module: Module) -> str:
    """The name a `pub use` must end in to export the item: the type of the impl block around it, else its own."""
    if isinstance(item, Function) and item.owner:
        return item.owner
    for block in module.items:
        if isinstance(block, ImplBlock) and block.file is item.file and block.start_line < item.start_line and item.end_line <= block.end_line:
            return block.type_name
    return item.name
