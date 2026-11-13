"""Hand-computed values of the module measurements, on small fixtures."""

from smog.domain.code import Codebase, Crate, Manifest
from smog.domain.measure import build_scorecard
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from tests.helpers import parse_source_file


def _codebase(files: dict[str, str], tracked: tuple = (), **crates: str) -> Codebase:
    """One crate `sample` at the repository root, or one crate per keyword: name to folder."""
    folders = crates or {"sample": ""}
    built = []
    for name, folder in folders.items():
        prefix = f"{folder}/" if folder else ""
        parsed = [parse_source_file(source, path, name, folder) for path, source in files.items() if path.startswith(prefix)]
        built.append(Crate(Manifest(name, folder, []), parsed))
    return Codebase(built, [], [*files, *tracked], {})


def _modules(files: dict[str, str], policy: Policy | None = None, tracked: tuple = (), **crates: str) -> dict[str, dict]:
    card = build_scorecard(_codebase(files, tracked, **crates), policy or Policy())
    return {piece.id: piece.values for piece in card.pieces(PieceKind.MODULE)}


INLINE = {
    "src/lib.rs": """pub mod a;
pub mod outer {
    pub fn f() {}
    pub mod inner {
        pub struct S;
    }
}
pub fn root() {}
#[cfg(test)]
mod tests {
    mod deeper {}
    pub fn t() {}
}
""",
    "src/a.rs": "pub fn x() {}\nfn y() {}\n",
    "tests/it.rs": "mod helper { pub fn h() {} }\n",
}


def test_inline_modules_are_modules_and_test_modules_are_not():
    modules = _modules(INLINE)
    assert sorted(modules) == ["sample", "sample::a", "sample::outer", "sample::outer::inner", "sample::tests", "sample::tests::it"]
    card = build_scorecard(_codebase(INLINE), Policy())
    assert card.find(PieceKind.CRATE, "sample").value("crate.modules") == 6
    assert card.root.value("codebase.modules") == 6


def test_submodules_are_the_direct_children():
    modules = _modules(INLINE)
    # a, outer and the folder tests; the inline test module does not count.
    assert modules["sample"]["module.submodules"] == 3
    assert modules["sample::outer"]["module.submodules"] == 1
    assert modules["sample::a"]["module.submodules"] == 0


def test_public_items_are_the_modules_own():
    modules = _modules(INLINE)
    # `pub mod a`, `pub mod outer` and `pub fn root`; `pub fn t` is in the test module.
    assert modules["sample"]["module.public_items"] == 3
    assert modules["sample::outer"]["module.public_items"] == 2
    assert modules["sample::outer::inner"]["module.public_items"] == 1
    assert modules["sample::tests::it"]["module.public_items"] == 0


def test_interface_depth_divides_own_lines_by_interface_tokens():
    modules = _modules(INLINE)
    # outer: 6 code lines minus the 3 of inner, over the 5 tokens of `pub fn f ( )`.
    assert modules["sample::outer"]["module.interface_depth"] == 3 / 5
    # a: 2 code lines over `pub fn x ( )`.
    assert modules["sample::a"]["module.interface_depth"] == 2 / 5
    # inner: its 3 code lines over 2 for the struct `S` without fields.
    assert modules["sample::outer::inner"]["module.interface_depth"] == 3 / 2


def test_an_inline_module_adds_no_lines_to_the_tree():
    card = build_scorecard(_codebase(INLINE), Policy())
    assert card.find(PieceKind.MODULE, "sample::outer").lines == 0
    assert card.find(PieceKind.MODULE, "sample").lines == card.find(PieceKind.CRATE, "sample").lines


FOLDERS = {
    "src/lib.rs": "mod flat;\nmod nested;\nmod leaf;\n",
    "src/flat.rs": "mod one;\nmod two;\n",
    "src/flat/one.rs": "",
    "src/flat/two.rs": "",
    "src/flat/deep/x.rs": "",
    "src/nested/mod.rs": "mod only;\n",
    "src/nested/only.rs": "",
    "src/leaf.rs": "",
    "tests/it.rs": "",
}


def test_folder_counts_follow_the_module_whatever_file_declares_it():
    modules = _modules(FOLDERS, tracked=("src/flat/notes.txt",))
    # src holds lib.rs, flat.rs and leaf.rs, and the folders flat and nested.
    assert (modules["sample"]["module.files_per_folder"], modules["sample"]["module.subfolders_per_folder"]) == (3, 2)
    # A module declared as flat.rs owns the folder flat: one.rs, two.rs and notes.txt, and the folder deep.
    flat = modules["sample::flat"]
    assert (flat["module.files_per_folder"], flat["module.subfolders_per_folder"], flat["module.folder_depth"]) == (3, 1, 2)
    nested = modules["sample::nested"]
    assert (nested["module.files_per_folder"], nested["module.subfolders_per_folder"]) == (2, 0)
    # A folder without a module file is found from the file below it.
    assert modules["sample::flat::deep"]["module.files_per_folder"] == 1
    assert modules["sample::tests"]["module.files_per_folder"] == 1
    # A file module without a folder of its own has no value.
    assert "module.files_per_folder" not in modules["sample::leaf"]
    assert "module.files_per_folder" not in modules["sample::flat::one"]


def test_folders_of_a_crate_in_a_subfolder():
    files = {"crates/s/src/lib.rs": "mod a;\n", "crates/s/src/a.rs": "mod b;\n", "crates/s/src/a/b.rs": ""}
    modules = _modules(files, s="crates/s")
    assert modules["s::a"]["module.files_per_folder"] == 1
    assert modules["s::a"]["module.folder_depth"] == 4
    assert modules["s"]["module.files_per_folder"] == 2


GRAPH = {
    "src/lib.rs": "pub mod a;\npub mod b;\npub mod c;\npub mod lone;\n",
    # a uses b twice and c once; the nested prefix `crate::b` of a longer path is no second target.
    "src/a.rs": "use crate::b::{B, T};\nuse crate::c;\npub fn f() -> B {\n    crate::b::make();\n    c::g()\n}\n",
    "src/b.rs": "pub struct B;\npub enum E { X }\npub trait T {}\npub fn make() {}\n#[cfg(test)]\nmod tests {\n    use crate::lone;\n}\n",
    "src/c.rs": "use super::b::B;\npub fn g() -> B {\n    B\n}\n",
    "src/lone.rs": "pub fn alone() {}\n",
    "tests/it.rs": "use sample::a;\n",
}


def test_afferent_and_efferent_count_modules_in_the_use_graph():
    modules = _modules(GRAPH)
    assert (modules["sample::a"]["module.afferent"], modules["sample::a"]["module.efferent"]) == (0, 2)
    # b is used by a and c; its test module's use of lone does not count.
    assert (modules["sample::b"]["module.afferent"], modules["sample::b"]["module.efferent"]) == (2, 0)
    assert (modules["sample::c"]["module.afferent"], modules["sample::c"]["module.efferent"]) == (1, 1)
    assert (modules["sample::lone"]["module.afferent"], modules["sample::lone"]["module.efferent"]) == (0, 0)
    # A test file is no node of the graph.
    assert "module.afferent" not in modules["sample::tests::it"]


def test_instability_abstractness_and_distance():
    modules = _modules(GRAPH)
    assert modules["sample::a"]["module.instability"] == 1.0
    assert modules["sample::b"]["module.instability"] == 0.0
    assert modules["sample::c"]["module.instability"] == 0.5
    # b declares one trait among a struct, an enum and a trait.
    assert modules["sample::b"]["module.abstractness"] == 1 / 3
    assert modules["sample::b"]["module.distance_main_sequence"] == abs(1 / 3 + 0.0 - 1)
    assert modules["sample::c"]["module.distance_main_sequence"] == 0.5
    assert modules["sample::a"]["module.distance_main_sequence"] == 0.0
    # No edge: abstractness is 0, instability and distance have no value.
    lone = modules["sample::lone"]
    assert lone["module.abstractness"] == 0 and "module.instability" not in lone and "module.distance_main_sequence" not in lone


def test_use_edges_follow_inline_modules_super_and_other_crates():
    files = {
        "one/src/lib.rs": "pub mod outer {\n    pub mod inner {\n        use super::sibling::S;\n        use two::deep::D;\n    }\n    pub mod sibling {\n        pub struct S;\n    }\n}\n",
        "two/src/lib.rs": "pub mod deep;\n",
        "two/src/deep.rs": "pub struct D;\nuse self::D as Again;\n",
    }
    modules = _modules(files, one="one", two="two")
    assert modules["one::outer::inner"]["module.efferent"] == 2
    assert modules["one::outer::sibling"]["module.afferent"] == 1
    assert modules["one::outer"]["module.afferent"] == 0
    # `self::D` names the module itself, which is no edge.
    assert (modules["two::deep"]["module.afferent"], modules["two::deep"]["module.efferent"]) == (1, 0)


def _use(*targets: str) -> str:
    return "".join(f"use crate::{target}::X;\n" for target in targets) + "pub struct X;\n"


def test_cycle_size_is_the_size_of_the_group_that_reaches_itself():
    files = {
        "src/lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\n",
        # a -> b -> c -> a is one group of three; d -> a only leads into it; e stands alone.
        "src/a.rs": _use("b"),
        "src/b.rs": _use("c"),
        "src/c.rs": _use("a"),
        "src/d.rs": _use("a"),
        "src/e.rs": "pub struct X;\n",
    }
    modules = _modules(files)
    assert [modules[f"sample::{name}"]["module.cycle_size"] for name in "abcde"] == [3, 3, 3, 0, 0]
    assert modules["sample"]["module.cycle_size"] == 0


NESTED = {
    "src/lib.rs": "pub mod p;\n",
    "src/p.rs": "pub mod c;\npub mod d;\npub use c::X;\npub struct Y;\n",
    "src/p/c.rs": "use super::Y;\nuse crate::p::d::Z;\npub struct X;\n",
    "src/p/d.rs": "use super::c::X;\npub struct Z;\n",
}


def test_a_parent_and_child_form_no_cycle_unless_the_setting_keeps_nested_edges():
    modules = _modules(NESTED)
    # p <-> c is left out; the siblings c <-> d remain.
    assert [modules[name]["module.cycle_size"] for name in ("sample::p", "sample::p::c", "sample::p::d")] == [0, 2, 2]
    policy = Policy()
    policy.setting("module_cycles_skip_nested", False)
    modules = _modules(NESTED, policy)
    assert [modules[name]["module.cycle_size"] for name in ("sample::p", "sample::p::c", "sample::p::d")] == [3, 3, 3]


def test_centrality_on_a_path_of_three_and_a_lone_module():
    files = {
        "src/lib.rs": "mod a;\nmod b;\nmod c;\n",
        # a -> b -> c: b lies between a and c. The crate root has no edge. n = 4.
        "src/a.rs": _use("b"),
        "src/b.rs": _use("c"),
        "src/c.rs": "pub struct X;\n",
    }
    modules = _modules(files)
    a, b, root = modules["sample::a"], modules["sample::b"], modules["sample"]
    assert (a["module.degree_centrality"], b["module.degree_centrality"], root["module.degree_centrality"]) == (1 / 3, 2 / 3, 0)
    # a reaches 2 modules at distances 1 and 2: (2 / 3) * (2 / 3). b reaches 2 at distance 1: (2 / 3) * (2 / 2).
    assert a["module.closeness_centrality"] == (2 / 3) * (2 / 3)
    assert b["module.closeness_centrality"] == 2 / 3
    assert root["module.closeness_centrality"] == 0
    # One of the three pairs of other modules, (a, c), has its only shortest path through b.
    assert b["module.betweenness_centrality"] == 1 / 3
    assert a["module.betweenness_centrality"] == 0 and root["module.betweenness_centrality"] == 0


def test_betweenness_splits_over_equal_shortest_paths():
    files = {
        "src/lib.rs": "pub struct X;\n",
        # A square a - b - d - c - a: two shortest paths between a and d, through b and through c.
        "src/a.rs": _use("b", "c"),
        "src/b.rs": _use("d"),
        "src/c.rs": _use("d"),
        "src/d.rs": "pub struct X;\n",
    }
    modules = _modules(files)
    # n = 5 with the root: 6 pairs of other modules for b. Only (a, d) passes through b, on 1 of its 2 shortest paths.
    assert modules["sample::b"]["module.betweenness_centrality"] == 0.5 / 6
    assert modules["sample::a"]["module.betweenness_centrality"] == 0.5 / 6


def test_catch_all_name_and_name_repetition_read_the_last_path_segment():
    files = {
        "src/lib.rs": "mod util;\nmod user;\nmod sample;\npub mod wrap { pub mod wrap { pub mod utils {} } }\n",
        "src/util.rs": "",
        "src/user.rs": "mod user;\nmod user_store;\n",
        "src/user/user.rs": "",
        "src/user/user_store.rs": "",
        "src/sample.rs": "",
    }
    modules = _modules(files)
    flagged = {name for name, values in modules.items() if values["module.catch_all_name"]}
    assert flagged == {"sample::util", "sample::wrap::wrap::utils"}
    repeated = {name for name, values in modules.items() if values["module.name_repetition"]}
    # `user::user_store` only starts with its parent's name, and a module named like its crate is not compared with it.
    assert repeated == {"sample::user::user", "sample::wrap::wrap"}
    policy = Policy()
    policy.setting("catch_all_names", ("user",))
    assert {name for name, values in _modules(files, policy).items() if values["module.catch_all_name"]} == {"sample::user", "sample::user::user"}


def test_public_structs_counts_pub_structs_the_module_declares():
    files = {
        "src/lib.rs": """pub struct Unit;
pub struct Tuple(u8);
pub struct Named { a: u8 }
pub(crate) struct Inside;
struct Private;
pub enum E { A }
pub mod inline {
    pub struct Deeper;
}
#[cfg(test)]
mod tests {
    pub struct InTest;
}
""",
    }
    modules = _modules(files)
    assert modules["sample"]["module.public_structs"] == 3
    assert modules["sample::inline"]["module.public_structs"] == 1


DELEGATION = """pub struct W { inner: Vec<u8>, lock: L }
impl W {
    pub fn len(&self) -> usize { self.inner.len() }
    pub fn push(&mut self, x: u8) { self.inner.push(x); }
    pub fn get(&self, i: usize) -> Result<u8, E> { lookup(&self.inner, i)? }
    pub fn new(inner: Vec<u8>) -> Self { Self::from_parts(inner.into()) }
    pub fn wrap(x: u8) -> Option<u8> { Some(x) }
    pub fn locked(&self) -> usize { self.lock.lock().len() }
    pub fn plus(&self, x: u8) -> usize { self.inner.len_with(x + 1) }
    pub fn two(&self) -> usize { let n = self.inner.len(); n }
    pub fn shout(&self) { println!("{}", self.inner.len()) }
}
impl Clone for W {
    fn clone(&self) -> Self { self.duplicate() }
}
trait T {
    fn sig(&self);
    fn default(&self) { self.sig() }
}
fn free(w: &W) -> usize { w.len() }
#[cfg(test)]
mod tests {
    impl super::W { fn t(&self) -> usize { self.len() } }
}
"""


def test_delegation_share_counts_methods_that_are_one_plain_call():
    modules = _modules({"src/lib.rs": DELEGATION, "src/empty.rs": "pub fn f() {}\n"})
    # Delegating: len, push, get, new, clone and default. Not: wrap builds a value, locked calls on a call's result,
    # plus changes its argument, two has two statements, shout is a macro. The free function and the trait method
    # without a body are no methods.
    assert modules["sample"]["module.delegation_share"] == 6 / 11
    assert modules["sample::empty"]["module.delegation_share"] == 0


UNREACHABLE = {
    "src/lib.rs": "pub mod open;\nmod closed;\nmod named;\nmod glob;\npub use named::Kept;\npub use glob::*;\npub fn root() {}\n",
    "src/open.rs": "pub fn a() {}\npub(crate) fn b() {}\nmod inner {\n    pub fn hidden() {}\n    pub mod deeper {\n        pub struct Far;\n    }\n}\n",
    "src/closed.rs": "pub struct S;\nimpl S {\n    pub fn m(&self) {}\n    fn private(&self) {}\n}\npub(crate) fn c() {}\nfn d() {}\n",
    "src/named.rs": "pub struct Kept;\nimpl Kept {\n    pub const ALL: u8 = 1;\n    pub fn m(&self) {}\n}\npub struct Dropped;\n",
    "src/glob.rs": "pub fn everything() {}\npub struct Too;\n",
}


def test_unreachable_pub_counts_pub_items_below_a_private_module_that_nothing_reexports():
    modules = _modules(UNREACHABLE)
    assert modules["sample"]["module.unreachable_pub"] == 0
    assert modules["sample::open"]["module.unreachable_pub"] == 0
    # `pub fn hidden` and `pub mod deeper` sit in the private inline module; `Far` sits below it.
    assert modules["sample::open::inner"]["module.unreachable_pub"] == 2
    assert modules["sample::open::inner::deeper"]["module.unreachable_pub"] == 1
    # `S` and its `pub` method; `pub(crate)` and private items never count.
    assert modules["sample::closed"]["module.unreachable_pub"] == 2
    # `Kept`, its constant and its method are re-exported by the type's name; `Dropped` is not.
    assert modules["sample::named"]["module.unreachable_pub"] == 1
    # `pub use glob::*` exports what the module declares.
    assert modules["sample::glob"]["module.unreachable_pub"] == 0


def test_a_module_declared_out_of_sight_counts_as_exported():
    files = {"src/lib.rs": "", "src/odd.rs": "pub fn f() {}\n", "src/folder/x.rs": "pub fn g() {}\n"}
    modules = _modules(files)
    assert modules["sample::odd"]["module.unreachable_pub"] == 0
    assert modules["sample::folder::x"]["module.unreachable_pub"] == 0


def test_the_compiler_lint_replaces_the_syntax_count():
    from smog.domain.tools import LintWarning, ToolResults

    tools = ToolResults()
    # Line 4 of open.rs is inside `inner`, line 6 inside `inner::deeper`, line 1 in the file module itself.
    tools.record(unreachable_pub=[LintWarning("unreachable_pub", "src/open.rs", line, "unreachable `pub` item") for line in (1, 4, 6)])
    card = build_scorecard(_codebase(UNREACHABLE), Policy(), tools=tools)
    values = {piece.id: piece.value("module.unreachable_pub") for piece in card.pieces(PieceKind.MODULE)}
    assert (values["sample::open"], values["sample::open::inner"], values["sample::open::inner::deeper"]) == (1, 1, 1)
    # The lint ran and reported nothing here, though the syntax count is 2.
    assert values["sample::closed"] == 0


def test_lint_warnings_are_read_from_cargo_json():
    from smog.adapter.cargo_tools import parse_lint_warnings

    line = '{"reason":"compiler-message","message":{"code":{"code":"unreachable_pub"},"message":"unreachable `pub` item","spans":[{"file_name":"src/a.rs","line_start":3,"is_primary":true}]}}'
    (warning,) = parse_lint_warnings(line + '\n{"reason":"build-finished","success":true}\nnot json\n')
    assert (warning.lint, warning.path, warning.line) == ("unreachable_pub", "src/a.rs", 3)


def test_a_pub_use_in_a_private_module_counts_unless_an_exported_module_hands_it_on():
    files = {
        "src/lib.rs": "mod wire;\npub use wire::Onward;\n",
        "src/wire.rs": "mod a;\nmod b;\nmod c;\npub use a::Inner;\npub use b::Onward;\npub(crate) use c::Crate;\n",
        "src/wire/a.rs": "pub struct Inner;\n",
        "src/wire/b.rs": "pub struct Onward;\n",
        "src/wire/c.rs": "pub struct Crate;\n",
    }
    modules = _modules(files)
    # `pub use a::Inner` stops in the private module wire. `pub use b::Onward` is handed on by the crate root.
    assert modules["sample::wire"]["module.unreachable_pub"] == 1
    # `Inner` is named by a `pub use`, so the item itself does not count; `Crate` only by a `pub(crate) use`.
    assert modules["sample::wire::a"]["module.unreachable_pub"] == 0
    assert modules["sample::wire::c"]["module.unreachable_pub"] == 1
    assert modules["sample"]["module.unreachable_pub"] == 0


def test_one_caller_helpers_count_on_the_inline_module_that_holds_them():
    files = {"src/lib.rs": "pub mod inner {\n    pub fn run() -> u8 {\n        helper()\n    }\n    fn helper() -> u8 {\n        1\n    }\n}\n"}
    modules = _modules(files)
    assert modules["sample::inner"]["module.one_caller_helpers"] == 1
    assert modules["sample"]["module.one_caller_helpers"] == 0
