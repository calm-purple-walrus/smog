"""Hand-computed values of the codebase measurements and of the graph they read."""

import math

import pytest

from smog.domain.code import Codebase, Crate, Dependency, Manifest
from smog.domain.graph import FileGraph, named_paths
from smog.domain.lenses.module_coupling import ModuleGraph
from smog.domain.lenses.checks import dependency_cycles
from smog.domain.lenses.clones import edit_distance, inconsistent_clone_groups, normalized_lines
from smog.domain.lenses.file import suppressions, warning_counts
from smog.domain.lenses.naturalness import codebase_cross_entropy, cross_entropies
from smog.domain.lenses.structure import propagation_cost
from smog.domain.measure import build_scorecard
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import LintWarning, ToolResults
from tests.helpers import codebase_of, parse_source_file


def _codebase(sources: dict[str, str]) -> Codebase:
    return codebase_of(*(parse_source_file(source, path) for path, source in sources.items()))


CFG_MODULES = """
#[cfg(feature = "latest")]
mod latest { pub fn a() {} }

#[cfg(test)]
mod tests { fn b() {} }

#[cfg(all(test, feature = "slow"))]
mod slow { fn c() {} }

#[cfg(not(test))]
mod production { pub fn d() {} }

#[cfg_attr(test, allow(dead_code))]
mod lenient { pub fn e() {} }

#[cfg(all(feature = "test", not(any(test, doc))))]
mod named { pub fn f() {} }
"""


def test_only_a_cfg_that_names_the_test_predicate_makes_a_test_module():
    file = parse_source_file(CFG_MODULES)
    assert {function.name: function.in_test_code for function in file.functions} == {
        "a": False, "b": True, "c": True, "d": False, "e": False, "f": False,
    }  # fmt: skip
    # The two test modules have one code line each besides their attribute.
    assert file.test_code_line_count == 4


def test_a_crate_without_a_workspace_edge_has_no_instability_and_no_distance():
    def crate(name: str, *dependencies: str) -> Crate:
        manifest = Manifest(name, name, [Dependency(dependency, "normal", True) for dependency in dependencies])
        return Crate(manifest, [parse_source_file("pub struct S;\n", f"{name}/src/lib.rs", name, name)])

    codebase = Codebase([crate("app", "core"), crate("core"), crate("alone")], [], [], {})
    values = {piece.id: piece.values for piece in build_scorecard(codebase, Policy()).pieces(PieceKind.CRATE)}
    # app depends on core: I = 1 / (0 + 1) and 0 / (1 + 0). No traits, so A = 0 and D = |0 + I - 1|.
    assert (values["app"]["crate.instability"], values["app"]["crate.distance_main_sequence"]) == (1, 0)
    assert (values["core"]["crate.instability"], values["core"]["crate.distance_main_sequence"]) == (0, 1)
    assert "crate.instability" not in values["alone"] and "crate.distance_main_sequence" not in values["alone"]


PATHS = {
    "src/lib.rs": "pub mod a;\npub mod c;\npub mod d;\npub mod e;\npub mod g;\n",
    "src/a.rs": "pub mod b;\npub fn top() {}\n",
    "src/a/b.rs": "pub struct T;\npub fn f() {}\n",
    "src/c.rs": "pub fn c() {\n    crate::a::b::f();\n}\n",
    "src/d.rs": "use crate::a::b::{f, T};\n",
    "src/e.rs": "pub fn e() -> crate::a::b::T {\n    crate::a::top();\n    crate::a::b::T\n}\n",
    "src/g.rs": "pub fn g() {\n    let v = Vec::<crate::a::b::T>::new();\n}\n",
}


def test_a_qualified_path_is_one_edge_to_its_deepest_module():
    edges = FileGraph(_codebase(PATHS)).edges
    # `crate::a::b::f` names the file of a::b and not the file of a.
    assert edges["src/c.rs"] == {"src/a/b.rs"}
    assert edges["src/d.rs"] == {"src/a/b.rs"}
    # e names `crate::a::top` as well, which is in the file of a.
    assert edges["src/e.rs"] == {"src/a.rs", "src/a/b.rs"}
    # A path inside generic arguments is a path of its own.
    assert edges["src/g.rs"] == {"src/a/b.rs"}
    assert edges["src/a.rs"] == set()


def test_named_paths_lists_each_path_once_in_full():
    paths = named_paths(parse_source_file(PATHS["src/e.rs"]).root)
    assert sorted(paths) == [("crate", "a", "b", "T"), ("crate", "a", "b", "T"), ("crate", "a", "top")]


def test_a_parent_that_re_exports_from_its_child_is_no_cycle_with_users_of_the_child():
    sources = {
        "src/lib.rs": "pub mod a;\n",
        "src/a.rs": "pub mod b;\npub mod c;\npub use b::T;\n",
        "src/a/b.rs": "pub struct T;\n",
        "src/a/c.rs": "pub fn c() -> crate::a::b::T {\n    crate::a::b::T\n}\n",
    }
    codebase = _codebase(sources)
    graph = FileGraph(codebase)
    assert graph.edges["src/a/c.rs"] == {"src/a/b.rs"}
    assert dependency_cycles(codebase, graph).passed
    # A child that names an item of its parent, which re-exports from the child, is a cycle.
    sources["src/a/b.rs"] = "pub struct T;\npub fn f() -> crate::a::T {\n    T\n}\n"
    codebase = _codebase(sources)
    assert not dependency_cycles(codebase, FileGraph(codebase)).passed


@pytest.mark.parametrize(
    ("edges", "cost"),
    [
        ({}, 0.0),
        # Each file reaches itself: 2 of 4 pairs.
        ({"a": set(), "b": set()}, 2 / 4),
        # a reaches a, b, c; b reaches b, c; c reaches c: 6 of 9 pairs.
        ({"a": {"b"}, "b": {"c"}, "c": set()}, 6 / 9),
        # In a cycle every file reaches every file.
        ({"a": {"b"}, "b": {"a"}}, 4 / 4),
    ],
)
def test_propagation_cost_is_the_density_of_the_visibility_matrix_with_its_diagonal(edges, cost):
    assert propagation_cost(edges) == cost


def test_the_codebase_carries_the_propagation_cost_of_its_file_graph():
    card = build_scorecard(_codebase(PATHS), Policy())
    # 7 files. lib names no path; a and a/b reach only themselves; c, d and g reach a/b; e reaches a and a/b.
    assert card.root.value("codebase.propagation_cost") == (7 + 1 + 1 + 1 + 2) / 49


def test_the_codebase_carries_the_decoupling_level_of_its_file_graph():
    card = build_scorecard(_codebase(PATHS), Policy())
    # a/b is a design rule for c, d, g and e. a is used by e alone, so a and e form one module of the last layer,
    # beside lib, c, d and g. Last layer 6/7; a/b keeps 1/7 * (1 - 5/6), since 5 of the 6 lower files depend on it.
    assert card.root.value("codebase.decoupling_level") == pytest.approx(6 / 7 + 1 / 7 * (1 - 5 / 6))


SUPPRESSED = """#![allow(clippy::too_many_lines)]
#![deny(missing_docs)]

#[allow(dead_code, unused_variables)]
fn a() {
    #[expect(clippy::cast_possible_truncation)]
    let x = 1u64 as u8;
}

#[cfg_attr(feature = "serde", allow(unused_imports))]
#[cfg_attr(test, derive(Debug))]
#[derive(Clone)]
pub struct S {
    #[allow(dead_code)]
    field: u8,
}

#[cfg(test)]
mod tests {
    #[test]
    #[allow(clippy::unwrap_used)]
    fn t() {}
}
"""


def test_suppressions_are_allow_and_expect_attributes_anywhere_in_the_file():
    # The inner allow, the allow on `a`, the expect on the statement, the allow inside cfg_attr, the allow on the
    # field and the one in the test module. `deny`, `derive` and a cfg_attr without allow are no suppressions.
    assert suppressions(parse_source_file(SUPPRESSED)) == 6
    assert suppressions(parse_source_file("pub fn allow() {}\n")) == 0


WARNINGS = [
    LintWarning("dead_code", "src/lib.rs", 5, "function `a` is never used"),
    LintWarning("unused_imports", "src/other.rs", 1, "unused import"),
    LintWarning("clippy::cast_possible_truncation", "src/lib.rs", 7, "casting"),
    LintWarning("clippy::needless_return", "src/lib.rs", 9, "unneeded return"),
    LintWarning("non_snake_case", "src/lib.rs", 9, "should have a snake case name"),
]


def test_warnings_are_counted_in_all_by_kind_and_as_unused_code():
    assert warning_counts(WARNINGS) == {"warnings": 5, "clippy_warnings": 2, "compiler_warnings": 3, "unused_code": 2}
    assert warning_counts([]) == {"warnings": 0, "clippy_warnings": 0, "compiler_warnings": 0, "unused_code": 0}
    only_dead = {**DEFAULT_SETTINGS, "unused_code_lints": ("dead_code",)}
    assert warning_counts(WARNINGS, only_dead)["unused_code"] == 1


def test_the_scorecard_carries_warnings_suppressions_and_unused_code():
    codebase = _codebase({"src/lib.rs": SUPPRESSED, "src/other.rs": "#[allow(unused)]\nuse std::fmt;\n"})
    plain = build_scorecard(codebase, Policy())
    assert plain.find(PieceKind.FILE, "src/lib.rs").value("file.suppressions") == 6
    assert plain.root.value("codebase.suppressions") == 7
    # Without the Clippy run there are no warning counts.
    assert "codebase.warnings" not in plain.root.values and "file.unused_code" not in plain.find(PieceKind.FILE, "src/lib.rs").values
    tools = ToolResults()
    tools.record(pedantic_warnings=WARNINGS)
    card = build_scorecard(codebase, Policy(), tools=tools)
    root = card.root
    assert [root.value(f"codebase.{name}") for name in ("warnings", "clippy_warnings", "compiler_warnings", "unused_code")] == [5, 2, 3, 2]
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.unused_code") == 1
    assert card.find(PieceKind.FILE, "src/other.rs").value("file.unused_code") == 1


def _steps(name: str, lines: list[str]) -> str:
    return f"pub fn {name}(input: u32) -> u32 {{\n" + "".join(f"    {line}\n" for line in lines) + "}\n"


BASE = [f"let v{index} = input + {index};" for index in range(11)] + ["v0"]
RENAMED = [f"let w{index} = other + {index * 7};" for index in range(11)] + ["w0"]
TWO_CHANGED = ["let v0 = input - 0;", *BASE[1:5], "check(v4);", *BASE[5:]]
SIX_CHANGED = [f"call{index}(input);" for index in range(6)] + BASE[6:]
SHORT = BASE[:8] + ["v0"]


def _groups(*functions: str, **settings) -> list[list[str]]:
    codebase = _codebase({"src/lib.rs": "".join(functions)})
    return [[function.name for function in group] for group in inconsistent_clone_groups(codebase, {**DEFAULT_SETTINGS, **settings})]


def test_names_and_literals_do_not_distinguish_two_lines():
    file = parse_source_file(_steps("a", ['let total = input + 10;', 'print("x", total)']) + _steps("b", ['let sum = value + 7;', 'show("yy", sum)']))
    first, second = (normalized_lines(function) for function in file.functions)
    assert first == second == ["let N = N + L ;", "N ( L , N )"]


def test_edit_distance_counts_inserted_removed_and_changed_lines():
    assert edit_distance(list("abcd"), list("abcd"), 5) == 0
    assert edit_distance(list("abcd"), list("abxd"), 5) == 1
    assert edit_distance(list("abcd"), list("acd"), 5) == 1
    assert edit_distance(list("abcd"), list("xaycd"), 5) == 2
    # More than the limit gives the limit plus 1.
    assert edit_distance(list("abcd"), list("wxyz"), 2) == 3


def test_copies_that_differ_in_a_few_lines_are_an_inconsistent_clone_group():
    # 12 lines against 13: one line changed and one inserted is an edit distance of 2, within 5 and within 0.2 x 13.
    assert _groups(_steps("first", BASE), _steps("second", TWO_CHANGED)) == [["first", "second"]]


def test_copies_that_differ_only_in_names_and_literals_are_consistent():
    assert _groups(_steps("first", BASE), _steps("second", RENAMED)) == []
    # A third copy that differs makes the group of all three inconsistent.
    assert _groups(_steps("first", BASE), _steps("second", RENAMED), _steps("third", TWO_CHANGED)) == [["first", "second", "third"]]


def test_too_many_differences_too_short_bodies_and_test_code_are_no_clones():
    assert _groups(_steps("first", BASE), _steps("second", SIX_CHANGED)) == []
    # 3 of 12 lines is above the ratio of 0.2 (2 lines) though within 5 edits.
    three = [f"call{index}(input);" for index in range(3)] + BASE[3:]
    assert _groups(_steps("first", BASE), _steps("second", three)) == []
    assert _groups(_steps("first", BASE), _steps("second", three), inconsistent_clone_max_edit_ratio=0.25) == [["first", "second"]]
    # Bodies of 9 lines are below the minimum of 10; with a minimum of 9, one changed line of 9 is within the ratio.
    shorter = _steps("first", SHORT), _steps("second", [*SHORT[:-1], "v1 + v2"])
    assert _groups(*shorter) == []
    assert _groups(*shorter, inconsistent_clone_min_lines=9) == [["first", "second"]]
    assert _groups(_steps("first", BASE), "#[cfg(test)]\nmod tests {\n" + _steps("second", TWO_CHANGED) + "}\n") == []


def test_the_scorecard_names_the_members_and_counts_the_groups():
    source = _steps("first", BASE) + _steps("second", TWO_CHANGED) + _steps("lone", SIX_CHANGED)
    card = build_scorecard(_codebase({"src/lib.rs": source}), Policy())
    values = [card.find(PieceKind.FUNCTION, f"sample::{name}").value("function.inconsistent_clone") for name in ("first", "second", "lone")]
    assert values == [1, 1, 0]
    assert card.root.value("codebase.inconsistent_clone_groups") == 1


def _entropies(sources: dict[str, str], **settings) -> dict[str, tuple[float, int]]:
    return cross_entropies(_codebase(sources), {**DEFAULT_SETTINGS, **settings})


def test_cross_entropy_of_a_file_under_single_token_counts_of_the_other_file():
    # Each file has the 6 tokens `fn`, a name, `(`, `)`, `{`, `}`; the codebase has 7 different tokens.
    found = _entropies({"src/a.rs": "fn a() {}", "src/b.rs": "fn b() {}"}, naturalness_order=1, naturalness_discount=0.5)
    # For a.rs the model is b.rs: 6 tokens, 6 kinds. A token seen once: (1 - 0.5) / 6 + 0.5 * 6 / 6 * 1 / 8 = 7 / 48.
    # The name `a` is not in b.rs: 0.5 * 6 / 6 * 1 / 8 = 1 / 16.
    expected = -(5 * math.log2(7 / 48) + math.log2(1 / 16)) / 6
    assert found["src/a.rs"] == (pytest.approx(expected), 6)
    assert found["src/b.rs"] == (pytest.approx(expected), 6)
    assert codebase_cross_entropy(found) == pytest.approx(expected)


def test_cross_entropy_backs_off_from_pairs_to_single_tokens():
    found = _entropies({"src/a.rs": "fn a() {}", "src/b.rs": "fn b() {}"}, naturalness_order=2, naturalness_discount=0.5)
    # Pairs of a.rs against b.rs, with a start mark before `fn`:
    # (start, fn), ((, )), (), {), ({, }): seen once after a context seen once: 0.5 + 0.5 * 7 / 48.
    # (fn, a): `fn` was seen once, before `b`: 0.5 * 1 / 16. (a, (): the context `a` was never seen: 7 / 48.
    expected = -(4 * math.log2(0.5 + 0.5 * 7 / 48) + math.log2(0.5 / 16) + math.log2(7 / 48)) / 6
    assert found["src/a.rs"][0] == pytest.approx(expected)


def test_a_copy_is_less_surprising_than_new_code_and_a_lone_file_gets_the_uniform_value():
    body = "pub fn run(input: u32) -> u32 {\n    let doubled = input * 2;\n    doubled + 1\n}\n"
    found = _entropies({"src/a.rs": body, "src/b.rs": body, "src/c.rs": "struct Odd<'x>(&'x [u8; 4]);\n"})
    assert found["src/a.rs"][0] == found["src/b.rs"][0] < found["src/c.rs"][0]
    # One file with 6 tokens of 6 kinds and nothing to train on: every token has probability 1 / 7.
    assert _entropies({"src/a.rs": "fn a() {}"})["src/a.rs"] == (pytest.approx(math.log2(7)), 6)
    assert _entropies({"src/a.rs": ""}) == {} and codebase_cross_entropy({}) is None


def test_the_scorecard_carries_the_cross_entropies():
    body = "pub fn run(input: u32) -> u32 {\n    input + 1\n}\n"
    sources = {"src/a.rs": body, "src/b.rs": body}
    card = build_scorecard(_codebase(sources), Policy())
    expected = cross_entropies(_codebase(sources))["src/a.rs"][0]
    assert card.find(PieceKind.FILE, "src/a.rs").value("file.cross_entropy") == expected
    assert card.root.value("codebase.cross_entropy") == pytest.approx(expected)


def test_the_file_graph_and_the_module_graph_resolve_a_path_the_same_way():
    """A binary names its own library by the crate name; a module of that name comes first."""
    sources = {
        "src/lib.rs": "pub mod a;\npub mod shadow;\n",
        "src/a.rs": "pub fn f() {}\n",
        "src/main.rs": "use sample::a::f;\nfn main() {\n    f();\n}\n",
        "src/shadow.rs": "pub mod sample;\nuse sample::inner;\n",
        "src/shadow/sample.rs": "pub fn inner() {}\n",
    }
    codebase = _codebase(sources)
    files = FileGraph(codebase).edges
    assert files["src/main.rs"] == {"src/a.rs"} and files["src/shadow.rs"] == {"src/shadow/sample.rs"}
    modules = ModuleGraph(codebase).edges
    assert ("sample", ("a",)) in modules[("sample", ())]
    assert modules[("sample", ("shadow",))] == {("sample", ("shadow", "sample"))}
