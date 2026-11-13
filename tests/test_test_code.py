"""Code under `#[cfg(test)]` is test code everywhere: in line counts, test density, duplication, clones and type pieces."""

import pytest

from smog import Policy, analyze
from smog.domain.lenses.clones import inconsistent_clone_groups
from smog.domain.lenses.duplication import duplicated_line_shares
from smog.domain.lenses.file import size_values
from smog.domain.measure import build_scorecard
from smog.domain.registry import PieceKind
from tests.helpers import MANIFEST, codebase_of, commit, make_repository, parse_source_file, scored_policy

PRODUCTION = "".join(f"pub fn f{index}() -> u32 {{\n    {index}\n}}\n" for index in range(30))  # 90 lines
TESTS = "#[cfg(test)]\nmod tests {\n" + "".join(f"    #[test]\n    fn t{index}() {{\n        assert_eq!(super::f{index}(), {index});\n    }}\n" for index in range(5)) + "}\n"
CFG_ITEMS = (
    "pub struct Foo {\n    a: u32,\n}\n"
    "#[cfg(test)]\nuse std::collections::HashMap;\n"
    "#[cfg(test)]\npub fn helper(a: u32) -> u32 {\n    a + 1\n}\n"
    "#[cfg(test)]\nimpl Foo {\n    pub fn build_sample() -> Self {\n        Foo { a: 1 }\n    }\n}\n"
    "#[cfg(all(test, feature = \"slow\"))]\npub struct Fake {\n    a: u32,\n    b: u32,\n}\n"
    "#[cfg(not(test))]\npub fn only_in_the_product() {}\n"
)
FIXTURES = "".join(f"pub fn fixture{index}() -> u32 {{\n    {index}\n}}\n" for index in range(10))


def _density(*files) -> float:
    return build_scorecard(codebase_of(*files), Policy()).root.value("codebase.tests_per_100_lines")


def test_the_baseline_is_five_tests_on_ninety_production_lines():
    assert _density(parse_source_file(PRODUCTION + TESTS)) == pytest.approx(500 / 90)


def test_an_item_under_cfg_test_is_test_code():
    file = parse_source_file(CFG_ITEMS)
    values = size_values(file)
    # Production: the struct Foo (3 lines) and the function under cfg(not(test)) with its attribute (2 lines).
    assert (values["file.production_lines"], values["file.test_lines"]) == (5, 17)
    assert {function.name: function.in_test_code for function in file.functions} == {"helper": True, "build_sample": True, "only_in_the_product": False}
    assert {type_def.name: type_def.in_test_code for type_def in file.types} == {"Foo": False, "Fake": True}


def test_items_under_cfg_test_do_not_change_the_test_density():
    assert _density(parse_source_file(PRODUCTION + TESTS + "#[cfg(test)]\npub fn helper(a: u32) -> u32 {\n    a + 1\n}\n#[cfg(test)]\nimpl Foo {\n    pub fn build_sample() -> u32 {\n        1\n    }\n}\n")) == pytest.approx(500 / 90)


@pytest.mark.parametrize("path", ["src/fixtures.rs", "src/fixtures/mod.rs"])
def test_the_file_behind_a_cfg_test_module_declaration_is_a_test_file(path):
    lib = parse_source_file(PRODUCTION + TESTS + "#[cfg(test)]\nmod fixtures;\n")
    fixtures = parse_source_file(FIXTURES, path)
    deeper = parse_source_file(FIXTURES, "src/fixtures/deep.rs")
    other = parse_source_file("pub fn fixtures_are_not_here() {}\n", "src/other/fixtures.rs")
    codebase = codebase_of(lib, fixtures, deeper, other)
    assert [file.is_test for file in codebase.files] == [False, True, True, False]
    assert size_values(fixtures)["file.production_lines"] == 0
    # 90 production lines in lib.rs and 1 in other/fixtures.rs.
    assert build_scorecard(codebase, Policy()).root.value("codebase.tests_per_100_lines") == pytest.approx(500 / 91)


def test_a_cfg_test_module_declared_in_a_file_module_is_found_below_it():
    parent = parse_source_file("#[cfg(test)]\nmod support;\npub fn real() {}\n", "src/store.rs")
    support = parse_source_file(FIXTURES, "src/store/support.rs")
    sibling = parse_source_file(FIXTURES, "src/support.rs")
    codebase_of(parent, support, sibling)
    assert (support.is_test, sibling.is_test) == (True, False)


def test_a_type_in_test_code_is_no_type_piece():
    source = CFG_ITEMS + "#[cfg(test)]\nmod tests {\n    mod deep {\n        struct InTest {\n            a: u32,\n            b: u32,\n        }\n    }\n}\n"
    card = build_scorecard(codebase_of(parse_source_file(source), parse_source_file("pub struct Fixture {\n    a: u32,\n}\n", "tests/common.rs")), Policy())
    assert [piece.id for piece in card.pieces(PieceKind.TYPE)] == ["sample::Foo"]


def test_a_copy_under_cfg_test_is_no_duplication_and_no_clone():
    body = "".join(f"    let value{index} = compute(input, {index}) + offset * {index};\n" for index in range(14))
    source = f"pub fn real(input: u32, offset: u32) {{\n{body}}}\n#[cfg(test)]\npub fn copy(input: u32, offset: u32) {{\n{body.replace('+ offset * 3;', '- offset * 3;')}}}\n"
    codebase = codebase_of(parse_source_file(source))
    assert duplicated_line_shares(codebase)["src/lib.rs"] == 0
    assert inconsistent_clone_groups(codebase) == []
    twins = codebase_of(parse_source_file(source.replace("#[cfg(test)]\n", "")))
    assert duplicated_line_shares(twins)["src/lib.rs"] > 0.5 and len(inconsistent_clone_groups(twins)) == 1


@pytest.mark.parametrize("files", [[], [("tests/api.rs", "#[test]\nfn works() {}\n")], [("src/lib.rs", TESTS)]])
def test_without_a_production_line_there_is_no_test_density(files):
    root = build_scorecard(codebase_of(*(parse_source_file(source, path) for path, source in files)), Policy()).root
    assert "codebase.tests_per_100_lines" not in root.values and "codebase.test_lines_per_line" not in root.values


def test_a_test_attribute_inside_a_macro_call_is_a_test_case():
    """`proptest! { #[test] fn ... }` is a macro call: its tokens are not parsed, but the attribute is visible."""
    macro = "proptest! {\n    #[test]\n    fn holds(a in 0u32..10) {\n        prop_assert!(a < 10);\n    }\n    #[test]\n    fn also_holds(a in 0u32..10) {\n        prop_assert!(a < 10);\n    }\n}\n"
    file = parse_source_file(PRODUCTION + macro + "#[wasm_bindgen_test]\nfn in_a_browser() {}\n")
    assert file.test_case_count == 3
    # The macro call (10 lines) and the test function with its attribute (2 lines) are test code.
    assert size_values(file)["file.test_lines"] == 12
    assert _density(file) == pytest.approx(300 / 90)
    assert parse_source_file("fn f() {\n    log!(\"#[test]\");\n    quote! { #[derive(Debug)] struct A; }\n}\n").test_case_count == 0


DEEP = "pub fn price(a: u32) -> u32 {\n" + "".join("    " * depth + f"if a > {depth} {{\n" for depth in range(1, 8)) + "        return 1;\n" + "".join("    " * depth + "}\n" for depth in range(7, 0, -1)) + "    0\n}\n"


@pytest.mark.parametrize(
    ("attribute", "is_test"),
    [
        ("cfg(test)", True),
        ("cfg( test )", True),
        ('cfg(all(test, feature = "slow"))', True),
        ("cfg(all(unix, all(test, windows)))", True),
        ("cfg(all(test, not(test)))", True),
        ("cfg(any(test, not(test)))", False),
        ("cfg(any(unix, test))", False),
        ('cfg(any(test, feature = "testing"))', False),
        ("cfg(all(unix, any(test, windows)))", False),
        ("cfg(not(test))", False),
        ("cfg(all(not(test), unix))", False),
        ('cfg(feature = "test")', False),
        ('cfg(all(feature = "test", unix))', False),
        ("cfg_attr(test, inline)", False),
    ],
)
def test_only_a_cfg_that_needs_test_makes_test_code(attribute, is_test):
    file = parse_source_file(f"#[{attribute}]\npub fn guarded() -> u32 {{\n    1\n}}\n#[{attribute}]\nmod guarded_module {{\n    pub fn inside() {{}}\n}}\n")
    assert [function.in_test_code for function in file.functions] == [is_test, is_test]
    assert size_values(file)["file.test_lines"] == (8 if is_test else 0)


@pytest.mark.parametrize(
    ("path", "is_test"),
    [
        ("tests/api.rs", True),
        ("tests/common/mod.rs", True),
        ("src/test_support.rs", False),
        ("src/tests.rs", False),
        ("src/test.rs", False),
        ("src/store_tests.rs", False),
        ("src/tests/real.rs", False),
        ("benches/speed.rs", False),
        ("examples/demo.rs", False),
    ],
)
def test_a_file_name_does_not_make_test_code(path, is_test):
    assert parse_source_file("pub fn f() {}\n", path).is_test is is_test


def test_the_tests_folder_is_the_one_of_the_crate():
    assert parse_source_file("pub fn f() {}\n", "crates/shop/tests/api.rs", crate_dir="crates/shop").is_test
    assert not parse_source_file("pub fn f() {}\n", "tests/shop/src/lib.rs", crate_dir="tests/shop").is_test


def _repository(tmp_path, **files):
    root = tmp_path / "repo"
    make_repository(root, {"Cargo.toml": MANIFEST, "src/lib.rs": "pub mod price;\n", "src/price.rs": "pub fn price(a: u32) -> u32 {\n    a\n}\n", **files})
    return root


@pytest.mark.parametrize(
    "change",
    [
        {"src/price.rs": "#[cfg(any(test, not(test)))]\n" + DEEP},
        {"src/price.rs": "pub use crate::test_support::price;\n", "src/lib.rs": "pub mod price;\npub mod test_support;\n", "src/test_support.rs": DEEP},
    ],
)
def test_a_production_function_marked_as_test_code_still_meets_the_gates(tmp_path, change):
    root = _repository(tmp_path)
    commit(root, change, "feat: nest")
    policy = scored_policy()
    policy.any_function("function.nesting", above=6)
    policy.metric_floor("function.nesting", block_below=0.5, piece="function")
    report = analyze(policy, str(root))
    assert sorted((finding.condition, finding.piece_id.rsplit("::", 1)[-1]) for finding in report.blocks) == [("any function: function.nesting", "price"), ("floor function.nesting", "price")]
    assert not report.card.pieces(PieceKind.TEST)


def test_a_policy_can_name_test_files_and_test_attributes(tmp_path):
    root = _repository(tmp_path, **{"src/lib.rs": "pub mod price;\npub mod test_support;\n#[my_test]\nfn checks() {}\n", "src/test_support.rs": DEEP})
    policy = Policy()
    assert [piece.id for piece in analyze(policy, str(root)).card.pieces(PieceKind.TEST)] == []
    policy.setting("test_file_patterns", ("src/test_*.rs",))
    policy.setting("test_attributes", ("test", "my_test"))
    assert sorted(piece.id for piece in analyze(policy, str(root)).card.pieces(PieceKind.TEST)) == ["sample::checks", "sample::test_support::price"]


def test_code_lines_inside_macro_calls_are_counted():
    """A body moved into a macro call is not parsed, so its nesting is not seen. Its lines are."""
    wrapped = "macro_rules! item {\n    ($($t:tt)*) => { $($t)* };\n}\n\nitem! {\n" + DEEP + "}\n"
    inside = "pub fn price(a: u32) -> u32 {\n    let b = a + 1;\n    block! {\n        if b > 1 {\n            if b > 2 {\n                return 1;\n            }\n        }\n    }\n    println!(\"{b}\");\n    0\n}\n"
    file_values = size_values(parse_source_file(wrapped))
    # The definition (3 lines) and the call with the whole function (20 lines) are every code line of the file.
    assert (file_values["file.macro_lines"], file_values["file.macro_line_share"]) == (23, 1.0)
    card = build_scorecard(codebase_of(parse_source_file(wrapped, "src/a.rs"), parse_source_file(inside, "src/b.rs"), parse_source_file(DEEP, "src/c.rs")), Policy())
    values = {piece.id: (piece.value("function.macro_lines"), piece.value("function.macro_line_share"), piece.value("function.nesting")) for piece in card.pieces(PieceKind.FUNCTION)}
    assert values == {"sample::b::price": (8, 8 / 12, 0), "sample::c::price": (0, 0.0, 7)}
    assert card.find(PieceKind.FILE, "src/b.rs").value("file.macro_lines") == 8
    tests = size_values(parse_source_file("#[cfg(test)]\nmod tests {\n    #[test]\n    fn t() {\n        assert!(true);\n    }\n}\n"))
    assert tests["file.macro_lines"] == 0 and tests["file.macro_line_share"] == 0.0
