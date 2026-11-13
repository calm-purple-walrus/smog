"""Items declared inside a function body, or in the block of a `const`, are pieces like any other, and the function around them counts only its own code."""

from smog import Policy
from smog.domain.lenses.file import function_count
from smog.domain.lenses.function import paragraphs
from smog.domain.lenses.function_comments import comment_density
from smog.domain.lenses.function_tests import line_coverage
from smog.domain.measure import build_scorecard
from smog.domain.registry import PieceKind
from tests.helpers import codebase_of, parse_source_file

SOURCE = """pub fn outer(a: u32) -> u32 {
    struct Local {
        a: u32,
        b: u32,
    }
    impl Local {
        fn sum(&self) -> u32 {
            self.a + self.b
        }
    }
    fn inner(z: u32) -> u32 {
        if z > 0 {
            1
        } else {
            0
        }
    }
    let twice = |x: u32| {
        fn double(y: u32) -> u32 {
            y * 2
        }
        double(x)
    };
    twice(inner(a)) + Local { a, b: 1 }.sum()
}
const _: () = {
    fn hidden() -> u32 {
        if true { 1 } else { 2 }
    }
};
"""


def _card():
    return build_scorecard(codebase_of(parse_source_file(SOURCE)), Policy())


def test_functions_and_types_in_a_body_are_pieces_named_after_the_function_around_them():
    card = _card()
    functions = {piece.id: piece for piece in card.pieces(PieceKind.FUNCTION)}
    assert sorted(functions) == ["sample::hidden", "sample::outer", "sample::outer::Local::sum", "sample::outer::double", "sample::outer::inner"]
    assert (functions["sample::outer::inner"].value("function.length"), functions["sample::outer::inner"].value("function.cyclomatic")) == (7, 2)
    assert (functions["sample::hidden"].value("function.length"), functions["sample::hidden"].value("function.cyclomatic")) == (3, 2)
    local = card.find(PieceKind.TYPE, "sample::outer::Local")
    assert (local.value("type.fields"), local.value("type.methods")) == (2, 1)
    file = card.find(PieceKind.FILE, "src/lib.rs")
    assert file.value("file.functions") == function_count(file.item) == len(functions) + 1  # the closure counts as well


def test_a_function_counts_only_its_own_code():
    """Of `outer`: the signature, the closure with its one call, the last expression and the closing brace."""
    card = _card()
    outer = card.find(PieceKind.FUNCTION, "sample::outer")
    own = ("function.length", "function.body_lines", "function.statements", "function.cyclomatic", "function.cognitive", "function.nesting", "function.indentation_sum")
    assert [outer.value(metric_id) for metric_id in own] == [6, 4, 3, 1, 0, 0, 5]
    assert outer.lines == 6
    # No line is counted twice: the functions, the struct and the two lines of the `impl` header and brace are the 25 lines of `outer`.
    inside = [piece.lines for piece in card.pieces(PieceKind.FUNCTION) if piece.id.startswith("sample::outer")]
    assert sum(inside) + card.find(PieceKind.TYPE, "sample::outer::Local").item.lines + 2 == 25
    file = card.find(PieceKind.FILE, "src/lib.rs")
    assert file.value("file.code_lines") == 30


PARAGRAPHS = """pub fn outer() {
    a();
    b();
    c();
    /// Docs of the item.
    #[inline]
    fn inner() {
        // A note in the item.
        x();

        y();
    }
    d();
    e();
    f();
}
"""


def test_an_item_in_the_body_neither_counts_nor_separates_in_the_paragraphs_and_keeps_its_comments():
    file = parse_source_file(PARAGRAPHS)
    outer, inner = file.functions
    assert (paragraphs(outer), paragraphs(inner)) == ([6], [1, 1])
    # The doc comment, the attribute, the note and the blank line of the item are no lines of `outer`.
    assert outer.item_lines == frozenset(range(5, 13))
    assert (comment_density(outer), comment_density(inner)) == (0.0, 2 / 6)


def test_a_line_inside_an_item_belongs_to_the_item_only():
    outer, inner = parse_source_file(PARAGRAPHS).functions
    assert [function.name for function in (outer, inner) if function.holds_line(9)] == ["inner"]
    assert [function.name for function in (outer, inner) if function.holds_line(13)] == ["outer"]
    # Coverage of `outer` reads its own six body lines: the uncovered line 9 is one of `inner`.
    coverable = {2, 3, 4, 9, 11, 13, 14, 15}
    assert (line_coverage(outer, coverable, {9}), line_coverage(inner, coverable, {9})) == (1.0, 1 / 2)


def test_a_function_and_an_item_on_one_line_both_keep_the_line():
    outer, inner = parse_source_file("pub fn outer() -> u32 { fn inner() -> u32 { 1 } inner() }\n").functions
    assert (outer.lines, inner.lines) == (1, 1)
    assert outer.holds_line(1) and inner.holds_line(1)
    assert [call.name for call in outer.calls()] == ["inner"] and inner.calls() == []


def test_an_item_in_a_body_is_no_item_of_the_module():
    file = parse_source_file(SOURCE)
    assert [item.name for item in file.items] == ["outer", "_"]
    assert [type_def.name for type_def in file.types] == ["Local"]


def test_an_item_in_a_test_function_is_test_code():
    file = parse_source_file("#[test]\nfn works() {\n    fn helper() -> u32 {\n        1\n    }\n    struct Fixture {\n        a: u32,\n    }\n    assert_eq!(helper(), 1);\n}\n")
    assert [(function.name, function.in_test_code) for function in file.functions] == [("works", True), ("helper", True)]
    assert all(type_def.in_test_code for type_def in file.types)
