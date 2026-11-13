"""Hand-computed values for a sample of metrics, on small fixtures."""

import math
import sys

import pytest

from smog.domain.calls import CallGraph
from smog.domain.code import Codebase, Crate, Dependency, Manifest
from smog.domain.dataflow import dep_degree
from smog.domain.graph import FileGraph, page_rank, reachable, strongly_connected, use_paths
from smog.domain.lenses.checks import catch_all_names, dependency_cycles, module_path_overrides, no_type_bounds, unused_dependencies
from smog.domain.lenses.checks import tests_in_build as runner_list_check
from smog.domain.lenses.comments import decorative_comments, interface_documentation, restating_comments, stale_doc_references
from smog.domain.lenses.function import bumpy_road, is_short_name, measure_function, paragraphs
from smog.domain.lenses.function_names import declared_names
from smog.domain.lenses.tests import assertion_tier, assertions, measure_test
from smog.domain.lenses.types import correlated_option_fields, data_clumps, foreign_field_access, lcom4, measure_type, tcc
from smog.domain.measure import build_scorecard
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from smog.domain.tools import MutantOutcome, ToolResults
from tests.helpers import codebase_of, function_in, parse_source_file

SAMPLE = """
fn sample(flag: bool, items: &[u32], limit: u32) -> Result<u32, String> {
    let mut total = 0;
    if flag && limit > 0 {
        for item in items {
            if *item > limit {
                return Err(String::from("too big"));
            }
            total += item;
        }
    } else if limit == 0 {
        total = 1;
    } else {
        total = 2;
    }
    let checked = helper(total)?;
    match checked {
        0 => Ok(0),
        1 | 2 => Ok(1),
        _ => Ok(checked),
    }
}
"""


@pytest.fixture
def sample_values():
    return measure_function(function_in(SAMPLE, "sample"))


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("function.length", 21),
        ("function.parameters", 3),
        # 1 + if + && + for + inner if + else if + ? + 2 extra match arms
        ("function.cyclomatic", 9),
        # if 1, && 1, for 2, inner if 3, else if 1, else 1, match 1
        ("function.cognitive", 10),
        ("function.nesting", 3),
        # body, if, for, inner if
        ("function.block_depth", 4),
        # 1 for `let`; 6 for the `if` (1 for `&&`, 3 for the `for` holding an `if`, 2 for the `else if`); 2 for `?`; 3 arms.
        ("function.npath", 36),
        ("function.loop_depth", 1),
        # if, for, inner if, else if, ?, three arms
        ("function.branch_count", 8),
        # tail, return, ?
        ("function.return_points", 3),
        # total, item, checked
        ("function.local_bindings", 3),
        ("function.flag_params", 1),
        ("function.complex_conditional", 1),
        ("function.panic_points", 0),
        ("function.bumpy_road", 1),
        # 19 code lines, of which the match takes 5 and counts as 1.
        ("function.largest_paragraph", 15),
        # 0.02 for each line from 11 to 15
        ("function.paragraph_penalty", 0.1),
    ],
)
def test_function_metric_matches_the_hand_count(sample_values, metric, expected):
    assert sample_values[metric] == pytest.approx(expected)


def test_comments_and_blanks_do_not_count_as_length():
    function = function_in("fn f() {\n    // a comment\n\n    let a = 1;\n    a\n}\n", "f")
    assert function.lines == 4


def test_macro_calls_count_tokens_but_not_structure():
    function = function_in('fn f() {\n    assert_eq!(a.unwrap(), b.expect("x"));\n    panic!("no");\n}\n', "f")
    values = measure_function(function)
    assert values["function.panic_points"] == 3
    assert values["function.assertions"] == 1
    assert values["function.cyclomatic"] == 1


def test_a_blank_line_ends_a_paragraph():
    source = "fn f() {\n    a();\n\n    b();\n    c();\n}\n"
    assert paragraphs(function_in(source, "f")) == [1, 2]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # A macro call with braces and no semicolon is a statement.
        ("    run! { a }\n    run! { b }\n    run! { c }\n\n    run! { d }\n    run! { e }\n    run! { f }\n", [3, 3]),
        # Items in a body are statements.
        ("    const A: u32 = 1;\n    const B: u32 = 2;\n    use std::fmt;\n\n    static C: u32 = 3;\n    const D: u32 = 4;\n    const E: u32 = 5;\n", [3, 3]),
        # The tail expression of a block is a statement: `d` in the second run.
        ("    a();\n    b();\n    c();\n\n    let d = 1;\n    let e = { d };\n\n    g();\n    h();\n    i();\n", [3, 2, 3]),
        # An empty line inside a string literal neither separates nor counts.
        ('    a();\n    b();\n    let q = "select\n\n    from";\n    c();\n    d();\n', [6]),
    ],
)
def test_a_paragraph_counts_the_statements_and_lines_the_function_values_count(body, expected):
    function = function_in("fn f() {\n" + body + "}\n", "f")
    assert paragraphs(function) == expected
    assert sum(expected) == measure_function(function)["function.body_lines"]


def test_code_on_the_lines_of_the_body_braces_counts_in_a_paragraph():
    assert paragraphs(function_in("fn f() { let a = 1;\n    let b = 2;\n    let c = 3;\n    let d = 4; }\n", "f")) == [4]
    assert paragraphs(function_in("fn f() { a() }\n", "f")) == [1]
    assert paragraphs(function_in("fn f() {}\n", "f")) == []


def test_a_comment_does_not_separate_paragraphs():
    source = "fn f() {\n    a();\n    // why\n    b();\n    c();\n}\n"
    assert paragraphs(function_in(source, "f")) == [3]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # A struct literal counts as its first line.
        ("    S {\n        a,\n        b: c.into(),\n        d: D { e },\n    }\n", 3),
        # A struct pattern counts as its first line.
        ("    let S {\n        a,\n        b: B { c },\n    } = s;\n", 3),
        # A chain of method calls inside a struct literal counts.
        ("    S {\n        a: b\n            .iter()\n            .count(),\n        c,\n    }\n", 6),
        # A branch or a closure inside a struct literal counts.
        ("    S {\n        a: if b { 1 } else { 2 },\n        c: d.map(|e| e),\n    }\n", 5),
    ],
)
def test_length_counts_a_struct_literal_or_pattern_as_its_first_line(body, expected):
    assert measure_function(function_in("fn f() {\n" + body + "}\n", "f"))["function.length"] == expected


def test_halstead_volume_and_vocabulary():
    values = measure_function(function_in("fn f(a: u32) -> u32 {\n    a + a\n}\n", "f"))
    # Operators {+}, operands {a}: vocabulary 2, three tokens, 3 * log2(2).
    assert values["function.vocabulary"] == 2
    assert values["function.halstead_volume"] == 3


def test_halstead_measures():
    values = measure_function(function_in('fn f(a: u32) -> u32 {\n    let b = a + 1;\n    g!(b, "x y");\n    b * a\n}\n', "f"))
    # Operators: let = + ! *, each once. Operands: b three times, a twice, 1 and "x y" once; g is the macro name.
    expected = {
        "function.halstead_distinct_operators": 5,
        "function.halstead_distinct_operands": 5,
        "function.halstead_total_operators": 5,
        "function.halstead_total_operands": 8,
        "function.vocabulary": 10,
        "function.halstead_length": 13,
        "function.halstead_volume": 13 * math.log2(10),
        "function.halstead_difficulty": 5 / 2 * 8 / 5,
        "function.halstead_effort": 4 * 13 * math.log2(10),
    }
    assert {name: values[name] for name in expected} == pytest.approx(expected)


def test_halstead_measures_of_an_empty_body_are_zero():
    values = measure_function(function_in("fn f() {}", "f"))
    assert values["function.halstead_volume"] == 0
    assert values["function.halstead_difficulty"] == 0
    assert values["function.halstead_effort"] == 0
    # Volume 0 and one line: both logarithms are 0.
    assert values["function.maintainability_index"] == pytest.approx(171 - 0.23)


def test_maintainability_index():
    values = measure_function(function_in("fn f(a: u32) -> u32 {\n    if a > 1 {\n        return 2;\n    }\n    a\n}\n", "f"))
    # Tokens: if a > 1 return 2 a. Seven tokens, six distinct. Cyclomatic 2, six code lines: 171 - 15.06 - 0.46 - 29.03.
    volume = 7 * math.log2(6)
    assert values["function.halstead_volume"] == pytest.approx(volume)
    assert values["function.maintainability_index"] == pytest.approx(171 - 5.2 * math.log(volume) - 0.23 * 2 - 16.2 * math.log(6))
    assert values["function.maintainability_index"] == pytest.approx(126.46, abs=0.01)


@pytest.mark.parametrize(
    ("body", "assignments", "branches", "conditions"),
    [
        ("let a; let b = c(); a = b; a += 1;", 3, 1, 0),
        ("a.b(c()); d!(e(), g());", 0, 3, 0),
        # One comparison; the condition has no operand tested without one.
        ("if a > b { c(); }", 0, 1, 1),
        # `a` and `b()` are tested without a comparison, `c == d` is one comparison.
        ("if a && !b() || c == d { }", 0, 1, 3),
        # `if a`, the `else` of `else if`, `b < 1`, the last `else`.
        ("if a { } else if b < 1 { } else { }", 0, 0, 4),
        ("if let Some(a) = b { }", 0, 0, 1),
        # Two arms, the guard's operand, one `?`.
        ("match a { 1 if b => c()?, _ => d() }", 0, 2, 4),
        ("let Some(a) = b else { return; };", 1, 0, 1),
        ("while a { } for b in c { } loop { }", 0, 0, 1),
        ("let a = b == c; d(|e| e > 1);", 1, 1, 2),
    ],
)
def test_abc_counts(body, assignments, branches, conditions):
    values = measure_function(function_in(f"fn f() {{ {body} }}", "f"))
    assert (values["function.abc_assignments"], values["function.abc_branches"], values["function.abc_conditions"]) == (assignments, branches, conditions)
    assert values["function.abc"] == pytest.approx(math.sqrt(assignments**2 + branches**2 + conditions**2))


def test_dep_degree_counts_definitions_reaching_each_use():
    straight = function_in("fn f(a: u32) -> u32 {\n    let b = a + 1;\n    let c = b + a;\n    c\n}\n", "f")
    # b uses a; c uses b and a; the tail uses c.
    assert dep_degree(["a"], straight.body) == 4
    forked = function_in("fn g(a: u32) -> u32 {\n    let mut x = 0;\n    if a > 0 {\n        x = 1;\n    }\n    x\n}\n", "g")
    # The condition uses a; the tail sees both definitions of x.
    assert dep_degree(["a"], forked.body) == 3


def test_mut_borrow_is_a_definition():
    function = function_in("fn f(a: u32) -> u32 {\n    let mut x = a;\n    fill(&mut x);\n    x\n}\n", "f")
    # x's definition uses a; the borrow uses x; the tail sees the definition made by the borrow.
    assert dep_degree(["a"], function.body) == 3


def test_bumpy_road_counts_runs_of_nested_statements():
    source = """
fn f() {
    if a { if b { c(); } }
    if d { if e { g(); } }
    h();
    if i { if j { k(); } }
}
"""
    assert bumpy_road(function_in(source, "f").body, 2) == 2


@pytest.mark.parametrize(
    ("source", "name", "metric", "expected"),
    [
        ("fn pass(a: u32) -> u32 { other(a) }", "pass", "function.pass_through", 1),
        ("fn pass(a: u32) -> u32 { other(&a.into())? }", "pass", "function.pass_through", 1),
        ("fn no(a: u32) -> u32 { other(a + 1) }", "no", "function.pass_through", 0),
        ("fn new(a: u32) -> Self { Self(a) }", "new", "function.pass_through", 0),
        ("fn wrap(a: u32) -> Option<u32> { Some(a) }", "wrap", "function.pass_through", 0),
        ("fn wrap(a: u32) -> Kind { Kind::wrap(a) }", "wrap", "function.pass_through", 1),
        ("impl T for X { fn pass(a: u32) -> u32 { other(a) } }", "pass", "function.pass_through", 0),
        ("fn validate_x(a: u32) -> Result<(), E> { Ok(()) }", "validate_x", "function.validation_only", 1),
        ("fn validate_x(a: &mut u32) -> Result<(), E> { Ok(()) }", "validate_x", "function.validation_only", 0),
        ("fn get_x() { }", "get_x", "function.name_mismatch", 1),
        ("fn is_x() -> u32 { 1 }", "is_x", "function.name_mismatch", 1),
        ("fn is_x() -> bool { true }", "is_x", "function.name_mismatch", 0),
        ("fn f(a: u32, b: u32, c: &str) { }", "f", "function.adjacent_same_type", 2),
        ("fn min(a: u32, b: u32) { }", "min", "function.adjacent_same_type", 0),
        ("fn f(a: Option<u32>) { if a.is_some() { } }", "f", "function.flag_params", 1),
        ("fn f(a: bool) { use_it(a); }", "f", "function.flag_params", 0),
        ("fn f<T, U, 'a>() { }", "f", "function.generic_params", 2),
        ("impl X { fn f(&self, a: bool, b: &bool, c: Option<bool>, d: bool) { } }", "f", "function.bool_params", 2),
        ("fn f() { }", "f", "function.bool_params", 0),
        # String, &str, &'a mut u64, Vec<u8> and Option<bool> are primitive; Id, &[u8], (u8, u8) and impl Into<String> are not.
        ("impl X { fn f<'a>(&self, a: String, b: &str, c: &'a mut u64, d: Vec<u8>, e: Option<bool>, g: Id, h: &[u8], i: (u8, u8), j: impl Into<String>) { } }", "f", "function.primitive_param_share", 5 / 9),
        ("impl X { fn f(&self) { } }", "f", "function.primitive_param_share", 0),
        ("fn f() -> Result<u32, ()> { Err(()) }", "f", "function.unit_error", 1),
        ("fn f() -> std::result::Result<(), ()> { Err(()) }", "f", "function.unit_error", 1),
        ("fn f() -> Result<(), E> { Ok(()) }", "f", "function.unit_error", 0),
        ("fn f() -> io::Result<()> { Ok(()) }", "f", "function.unit_error", 0),
        ("fn f() -> Option<Result<u32, ()>> { None }", "f", "function.unit_error", 0),
        ("fn f() { }", "f", "function.unit_error", 0),
        ("fn f(a: u32, b: u32, c: u32) -> u32 { other(a, &b, c + 1) }", "f", "function.pass_through_share", 1 / 3),
        ("impl X { fn f(&self, a: u32, b: u32) { self.inner.run(a, b); } }", "f", "function.pass_through_share", 1),
        ("impl T for X { fn f(a: u32) -> u32 { other(a) } }", "f", "function.pass_through_share", 1),
        ("fn f(a: u32) -> u32 { a.other(1) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> R { other(a)? }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> R { Ok(other(a)) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) { log(a); other(a) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) { other!(a) }", "f", "function.pass_through_share", 0),
        ("fn f((a, b): (u32, u32)) { other(a, b) }", "f", "function.pass_through_share", 0),
        ("fn f() { other() }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> Self { Self(a) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> Option<u32> { Some(a) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> Kind { Kind::Wrapped(a) }", "f", "function.pass_through_share", 0),
        ("fn f(a: u32) -> Kind { Kind::wrap(a) }", "f", "function.pass_through_share", 1),
        # Only `b` and `e` are bound: `c` and `d` are used in the guard, `io` starts a path, `MAX` is a constant.
        ("fn f() { match a { b if c > d => 1, io::Kind::Other => 2, MAX => 3, Some(e) => 4, _ => 5 } }", "f", "function.local_bindings", 2),
        # `fs` starts a path and is no name; the three bound names are long.
        ("fn f() { if let fs::Kind(value) = a { } let total = 1; let count = 2; }", "f", "function.short_names", 0),
        ("fn f() -> u32 { 1 }", "f", "function.return_points", 1),
        ("fn f() -> u32 { return 1; }", "f", "function.return_points", 1),
        ("fn f() -> u32 { return 1 }", "f", "function.return_points", 1),
        ("fn f(a: bool) -> u32 { if a { return 1; } g()?; return 2; }", "f", "function.return_points", 3),
        ("fn f(a: bool) -> u32 { if a { return 1; } 2 }", "f", "function.return_points", 2),
        ("fn f() { let a = v[0]; a.unwrap(); todo!(); }", "f", "function.panic_points", 3),
        ("fn f() { let a = v[0]; a.unwrap(); todo!(); }", "f", "function.panic_sites", 1),
        ('fn f() { a.unwrap().b.expect("c"); std::panic!("d"); g(|x| x.unwrap()); }', "f", "function.panic_sites", 4),
        ('fn f() { assert!(a.unwrap() > b.expect); log!("{}", c.expect("d"), panic!()); }', "f", "function.panic_sites", 3),
        ("fn f() { a.unwrap_or(1); b.unwrap_err(); unreachable!(); assert!(c); unwrap(d); }", "f", "function.panic_sites", 0),
        ('fn f() { dbg!(a); print!("b"); println!("c"); eprint!("d"); std::eprintln!("e"); todo!(); unimplemented!(); }', "f", "function.debug_leftovers", 7),
        ('fn f() { println!("{}", dbg!(a)); g(|| todo!()); }', "f", "function.debug_leftovers", 3),
        ('fn f() { writeln!(out, "a"); info!("b"); assert!(a != b); let println = 1; }', "f", "function.debug_leftovers", 0),
        ("fn f(a: u32) -> Result<(), E> { x.y = 1; if a > 1 { return Err(e); } Ok(()) }", "f", "function.late_input_checks", 1),
        ("fn f(a: u32) -> Result<(), E> { if a > 1 { return Err(e); } x.y = 1; Ok(()) }", "f", "function.late_input_checks", 0),
    ],
)
def test_function_rule(source, name, metric, expected):
    assert measure_function(function_in(source, name))[metric] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("a()", 1),
        # Two arms add 1, the guard adds 1.
        ("match a { 1 if b => c(), _ => d() }", 3),
        # `loop` tests nothing; the `if` that leaves it is the predicate.
        ("loop { if a { break; } }", 2),
        ("while a { b(); }", 2),
        ("let Some(a) = b else { return; };", 2),
        ("let a = |b| if b { 1 } else { 2 };", 2),
        ("if let Some(a) = b { c(a?); }", 3),
    ],
)
def test_cyclomatic_counts_predicates(body, expected):
    assert measure_function(function_in(f"fn f() {{ {body} }}", "f"))["function.cyclomatic"] == expected


@pytest.mark.parametrize(
    ("source", "lines", "statements"),
    [
        ("fn f() {}", 0, 0),
        ("fn f() { a() }", 1, 1),
        # The signature, the comment, the blank line and the closing brace do not count as body lines.
        ("fn f(\n    a: u32,\n) -> u32 {\n    // why\n\n    let b = a;\n    b\n}", 2, 2),
        # Lines 2 to 5. Statements: the `if`, `b()`, the `let`, its `return`, and the macro call.
        ("fn f() {\n    if a {\n        b();\n    }\n    let Some(c) = d else { return; }; e!(g(); h());\n}", 4, 5),
        # A match arm and a closure without braces hold no statement; the closure with braces holds one.
        ("fn f() {\n    match a { 1 => b(), _ => c() }\n    d(|x| x + 1);\n    d(|x| { x + 1 });\n}", 3, 4),
        # The empty line inside the string literal does not count.
        ('fn f() {\n    let a = "one\n\ntwo";\n}', 2, 1),
    ],
)
def test_body_lines_and_statements(source, lines, statements):
    values = measure_function(function_in(source, "f"))
    assert values["function.body_lines"] == lines
    assert values["function.statements"] == statements


@pytest.mark.parametrize(
    ("body", "depth", "paths"),
    [
        ("", 1, 1),
        ("a(); b();", 1, 1),
        ("if a { b(); }", 2, 2),
        # Two independent decisions multiply.
        ("if a { b(); } if c { d(); } else { e(); }", 2, 4),
        ("if a || b && c { d(); }", 2, 4),
        ("while a { if b { c(); } }", 3, 3),
        ("loop { if a { break; } }", 3, 2),
        ("for a in b { c(); }", 2, 2),
        # The guard's `&&` adds 1 to its arm; the braces of the match are no block.
        ("match a { 1 if b && c => d(), 2 => { e() } _ => g() }", 2, 4),
        ("let a = b()?.c()?;", 1, 3),
        ("let Some(a) = b else { if c { return; } return; };", 3, 3),
        ("let a = if b { 1 } else { 2 }; let c = d(|e| { if e { 1 } else { 2 } });", 3, 4),
        ("unsafe { { a!(if b { c } else { d }); } }", 3, 1),
        ("let a = b && c;", 1, 1),
    ],
)
def test_block_depth_and_path_count(body, depth, paths):
    values = measure_function(function_in(f"fn f() {{ {body} }}", "f"))
    assert values["function.block_depth"] == depth
    assert values["function.npath"] == paths


def test_path_count_stops_at_the_largest_float():
    body = "if a { b(); } " * 1100
    assert measure_function(function_in(f"fn f() {{ {body} }}", "f"))["function.npath"] == int(sys.float_info.max)


COMMENTED = """
// Not attached.
/// Adds the items.
///
/// # Errors
/// Fails when empty.
#[inline]
pub fn add_items(items: &[u32]) -> Result<u32, E> {
    // first
    // second line of it
    let total = sum(items); // trailing words here
    /* block */
    total.checked() /* one */ /* two */
}
"""


def test_comment_density_counts_doc_lines_and_lines_with_a_comment():
    values = measure_function(function_in(COMMENTED, "add_items"))
    # Four doc lines, then lines 9, 10, 11, 12 and 13 hold a comment. Code lines: 8, 11, 13 and 14.
    assert values["function.comment_density"] == pytest.approx(9 / 13)
    assert measure_function(function_in("fn f() {\n    a();\n}\n", "f"))["function.comment_density"] == 0


def test_inline_comment_words_joins_comment_lines_that_follow_each_other():
    values = measure_function(function_in(COMMENTED, "add_items"))
    # "first second line of it" is one comment of 5 words; then 3, 1, 1 and 1 words.
    assert values["function.inline_comment_words"] == pytest.approx(11 / 5)
    source = "fn f() {\n    a(); // one two\n    b(); // three\n    // - x\n    //! inner doc\n}\n"
    # Comments after code stay apart, also from the comment line below; the doc comment does not count; `-` is no word.
    assert measure_function(function_in(source, "f"))["function.inline_comment_words"] == pytest.approx(4 / 3)
    assert measure_function(function_in("/// Doc.\nfn f() {}\n", "f"))["function.inline_comment_words"] == 0


@pytest.mark.parametrize(
    ("doc", "name", "expected"),
    [
        # "adds" is one letter from "add", "items." loses its dot.
        ("/// Adds the items.", "add_items", 2 / 3),
        ("/// Returns the `HTTPServer` name!", "getHTTPServerName", 1 / 4),
        ("/// Sum of all values.", "compute", 0),
        ("", "compute", 0),
        ("/// # - ```", "compute", 0),
        # Special characters are removed: `(compute)` and `com-pute` are both `compute`.
        ("/// (compute) com-pute it", "compute", 2 / 3),
        # "do" is one letter from "to".
        ("/// Do it.", "to_string", 1 / 2),
        ("/** Parse\n * text */", "parse_text", 2 / 2),
    ],
)
def test_comment_name_overlap(doc, name, expected):
    values = measure_function(function_in(f"{doc}\nfn {name}() {{}}\n", name))
    assert values["function.comment_name_overlap"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("pub fn f() -> Result<u32, E> { Ok(1) }", 1),
        ("/// Doc.\n///\n/// # Errors\n/// When it fails.\npub fn f() -> Result<u32, E> { Ok(1) }", 0),
        ("/// Doc with # Errors in a line.\npub fn f() -> io::Result<u32> { Ok(1) }", 1),
        ("/// # Errors\npub fn f() -> fmt::Result { a.unwrap(); Ok(()) }", 1),
        ("/// # Errors\n/// # Panics\npub fn f() -> Result<u32, E> { assert!(a); Ok(1) }", 0),
        ('pub fn f() -> Result<u32, E> { g(|| panic!("no")); h!(a.expect("b")) }', 2),
        ("pub fn f() -> Option<Result<u32, E>> { unreachable!(); todo!(); debug_assert!(a); v[0] }", 0),
        ("pub fn f() -> AppResult<u32> { Ok(1) }", 1),
        ("pub fn f() -> Outcome<u32> { Ok(1) }", 0),
        ("pub(crate) fn f() -> Result<u32, E> { a.unwrap() }", 0),
        ("fn f() -> Result<u32, E> { a.unwrap() }", 0),
        ("impl T for X { fn f() -> Result<u32, E> { a.unwrap() } }", 0),
        ("impl X { pub fn f(&self) -> Result<u32, E> { a.unwrap() } }", 2),
        # A method declared in a public trait is checked for `# Errors` only.
        ("pub trait T { fn f() -> Result<u32, E> { a.unwrap() } }", 1),
        ("pub trait T {\n    /// # Errors\n    fn f() -> Result<u32, E> { a.unwrap() }\n}", 0),
        ("trait T { fn f() -> Result<u32, E> { a.unwrap() } }", 0),
        ("#[doc(hidden)]\npub fn f() -> Result<u32, E> { a.unwrap() }", 0),
    ],
)
def test_missing_failure_docs(source, expected):
    assert measure_function(function_in(source, "f"))["function.missing_failure_docs"] == expected


NAMES = """
impl X {
    fn load(&self, a: u32, (b, total): (u32, u32), _c: u32) -> u32 {
        let d = a;
        let d = b;
        let Point { x, y: height } = point;
        if let Some(e) = total.checked() { }
        for (i, item) in items.iter().enumerate() { }
        match kind { io::Kind::Other => 0, MAX => 1, g @ 2 if h > 1 => g, _ => 0 };
        items.map(|j, (k, last): (u32, Foo)| j + k)
    }
}
"""


def test_declared_names_and_single_character_names():
    function = function_in(NAMES, "load")
    assert declared_names(function) == ["a", "b", "total", "_c", "d", "x", "height", "e", "i", "item", "g", "j", "k", "last"]
    # a b d x e i g j k: `_c` has two characters, `h` in the guard and `y` as a field name are not bound.
    assert measure_function(function)["function.single_char_names"] == 9
    assert measure_function(function_in("fn f() { let _ = 1; }", "f"))["function.single_char_names"] == 0


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Short or abbreviated words are no flaw: no dictionary is checked.
        ("fn ld(total: u32) { let cnt = 1; let x = 2; }", 0),
        # Digits are dropped and underscores at the ends are ignored.
        ("fn load2(_total: u32) { let count_ = 1; let utf8_count = 2; }", 0),
        # `loadTotal` holds a capital and is one identifier, as function and as binding; `Total` is read as a constant pattern.
        ("fn loadTotal() { let loadTotal = 1; let Total = 2; }", 1),
        ("fn LOAD() { }", 1),
        # Five words is one too many; four are fine.
        ("fn load() { let load_total_count_x_load = 1; let load_total_count_x = 2; }", 1),
        # One identifier with two flaws counts once.
        ("fn load() { let cntTotal_load_load_load_load = 1; }", 1),
        ("impl T for X { fn LOAD(&self) { } }", 0),
        ("impl X { fn LOAD(&self) { } }", 1),
        ("fn load() { run(|aB| aB); }", 1),
    ],
)
def test_naming_flaws(source, expected):
    function = parse_source_file(source).functions[0]
    assert measure_function(function)["function.naming_flaws"] == expected


TOOLED = "fn f() {\n    a();\n}\nfn g() {\n    b();\n    c();\n}\nimpl X {\n    fn h(&self) {\n        d();\n    }\n}\n"
MUTANTS = [
    # f, lines 1 to 3: the whole-body mutant is missed.
    MutantOutcome("src/lib.rs", 2, "missed", "FnValue"),
    MutantOutcome("src/lib.rs", 2, "caught", "BinaryOperator"),
    MutantOutcome("src/lib.rs", 2, "timeout", "BinaryOperator"),
    MutantOutcome("src/lib.rs", 2, "unviable", "FnValue"),
    # g, lines 4 to 7: one whole-body mutant is caught.
    MutantOutcome("src/lib.rs", 5, "caught", "FnValue"),
    MutantOutcome("src/lib.rs", 5, "missed", "FnValue"),
    MutantOutcome("src/lib.rs", 6, "missed", "BinaryOperator"),
    # h, lines 9 to 11, inside the impl block.
    MutantOutcome("src/lib.rs", 10, "unviable", "FnValue"),
    # No function holds line 8 or a line of another file.
    MutantOutcome("src/lib.rs", 8, "missed", "FnValue"),
    MutantOutcome("src/other.rs", 2, "missed", "FnValue"),
]


def _tooled_values(policy=None, **results):
    tools = ToolResults()
    tools.record(**results)
    card = build_scorecard(codebase_of(parse_source_file(TOOLED)), policy or Policy(), tools=tools)
    return {piece.id.rsplit("::", 1)[-1]: piece.values for piece in card.pieces(PieceKind.FUNCTION)}


def test_mutants_are_counted_on_the_function_that_holds_their_line():
    values = _tooled_values(mutants=MUTANTS)
    assert values["f"]["function.missed_mutants"] == 1
    assert values["f"]["function.mutant_timeouts"] == 1
    # One caught, one missed; the timeout and the unviable mutant are left out.
    assert values["f"]["function.mutation_score"] == pytest.approx(1 / 2)
    assert values["g"]["function.missed_mutants"] == 2
    assert values["g"]["function.mutation_score"] == pytest.approx(1 / 3)
    assert values["h"]["function.missed_mutants"] == 0
    assert "function.mutation_score" not in values["h"]


def test_a_timeout_counts_as_caught_when_the_setting_says_so():
    policy = Policy()
    policy.setting("mutation_timeouts_caught", True)
    assert _tooled_values(policy, mutants=MUTANTS)["f"]["function.mutation_score"] == pytest.approx(2 / 3)


def test_pseudo_tested_needs_coverage_and_only_missed_whole_body_mutants():
    assert all("function.pseudo_tested" not in found for found in _tooled_values(mutants=MUTANTS).values())
    lines = {"src/lib.rs": {2, 5, 6}}
    values = _tooled_values(mutants=MUTANTS, coverable=lines, uncovered={"src/lib.rs": {6}})
    assert values["f"]["function.pseudo_tested"] == 1
    assert values["g"]["function.pseudo_tested"] == 0
    assert "function.pseudo_tested" not in values["h"]
    # No test runs f: it is untested, not pseudo-tested.
    values = _tooled_values(mutants=MUTANTS, coverable=lines, uncovered={"src/lib.rs": {2}})
    assert values["f"]["function.pseudo_tested"] == 0


def test_function_coverage_is_the_share_of_coverable_lines_with_a_hit():
    values = _tooled_values(coverable={"src/lib.rs": {2, 5, 6}}, uncovered={"src/lib.rs": {6}})
    assert values["f"]["function.coverage"] == 1
    assert values["g"]["function.coverage"] == pytest.approx(1 / 2)
    assert "function.coverage" not in values["h"]
    assert "function.missed_mutants" not in values["f"]
    assert _tooled_values(coverable={"src/lib.rs": {2}}, uncovered={"src/lib.rs": {2}})["f"]["function.coverage"] == 0


def test_short_names():
    assert is_short_name("x")
    assert is_short_name("cfg")
    assert not is_short_name("config")
    assert not is_short_name("max_len")


TYPES = """
/// Doc.
#[derive(Clone)]
pub struct Account<T: Clone> {
    /// The balance must stay positive.
    pub balance: u64,
    pub(crate) owner: String,
    active: bool,
    alias: Option<String>,
    note: Option<String>,
    extra: T,
}

impl<T: Clone> Account<T> {
    pub fn new() -> Self {
        Self { balance: 0 }
    }
    fn read(&self) -> u64 { self.balance + self.other() }
    fn other(&self) -> u64 { self.balance }
    fn lonely(&self) -> bool { self.active }
    pub fn set_note(&mut self, value: Option<String>) { self.note = value; }
    pub fn note(&self) -> Option<String> { self.note.clone() }
}

enum Kind { A, B, C(u32) }
"""


def _type(name: str):
    code = codebase_of(parse_source_file(TYPES))
    return next(item for item in code.types if item.name == name)


def test_type_lenses():
    values = measure_type(_type("Account"), {})
    assert values["type.fields"] == 6
    assert values["type.methods"] == 6
    assert values["type.on_off_fields"] == 3
    assert values["type.public_invariant_fields"] == 1
    assert values["type.plain_setters"] == 1
    assert values["type.empty_encapsulation"] == 1
    assert values["type.missing_traits"] == 1
    assert values["type.primitive_share"] == pytest.approx(5 / 6)
    assert measure_type(_type("Kind"), {})["type.variants"] == 3


def test_lcom4_counts_components_of_methods():
    # read and other share balance and call; lonely uses active; set_note and note share note.
    assert lcom4(_type("Account")) == 3


def test_tcc_is_the_share_of_method_pairs_sharing_a_field():
    # 5 instance methods give 10 pairs; (read, other) and (set_note, note) share a field.
    assert tcc(_type("Account")) == pytest.approx(2 / 10)


def test_correlated_option_fields_need_enough_literals():
    source = """
struct P { a: Option<u32>, b: Option<u32> }
fn one() { P { a: Some(1), b: Some(2) }; }
fn two() { P { a: None, b: None }; }
fn three() { P { a: Some(3), b: Some(4) }; }
"""
    assert correlated_option_fields(codebase_of(parse_source_file(source)))["sample::P"] == 1
    shorter = source.replace("fn three() { P { a: Some(3), b: Some(4) }; }", "")
    assert correlated_option_fields(codebase_of(parse_source_file(shorter)))["sample::P"] == 0


def test_foreign_field_access_counts_other_modules_only():
    owner = parse_source_file("pub struct S { pub unique: u32 }\nfn here(s: S) -> u32 { s.unique }\n", "src/a.rs")
    other = parse_source_file("fn there(s: S) -> u32 { s.unique + s.unique }\n", "src/b.rs")
    assert foreign_field_access(codebase_of(owner, other))["sample::a::S"] == 2


def test_data_clumps_need_three_shared_pairs():
    source = "struct A { x: u32, y: u32, z: u32 }\nstruct B { x: u32, y: u32, z: u32, w: u8 }\nstruct C { x: u32, y: u32 }\n"
    assert len(data_clumps(codebase_of(parse_source_file(source)))) == 1


TEST_SOURCE = """
#[test]
fn checks_things() {
    let value = compute();
    assert_eq!(value, 42);
    assert_eq!(value, 42);
    if value > 1 { println!("big"); }
    std::thread::sleep(d);
}

#[test]
fn asserts_nothing() {
    compute();
}

#[test]
#[ignore]
fn weak() {
    assert!(compute().is_ok());
    assert!(true);
}
"""


def test_test_lenses():
    values = measure_test(function_in(TEST_SOURCE, "checks_things"))
    assert values["test.no_assertion"] == 0
    assert values["test.assertion_block"] == 2
    assert values["test.smell.duplicate_assert"] == 1
    assert values["test.smell.conditional_logic"] == 1
    assert values["test.smell.print"] == 1
    assert values["test.smell.sleep"] == 1
    assert values["test.smell.magic_number"] == 2
    assert measure_test(function_in(TEST_SOURCE, "asserts_nothing"))["test.no_assertion"] == 1
    weak = measure_test(function_in(TEST_SOURCE, "weak"))
    assert weak["test.smell.ignored_test"] == 1
    assert weak["test.smell.redundant_assertion"] == 1


def test_assertion_tiers():
    function = function_in("#[test]\nfn t() {\n    assert_eq!(a, 1);\n    assert!(a > 1);\n    assert!(a.is_ok());\n}\n", "t")
    assert [assertion_tier(node) for node in assertions(function)] == [3, 2, 1]


def test_item_split_and_test_detection():
    file = parse_source_file(
        """
mod inner {
    pub struct S;
    impl S { pub fn m(&self) {} }
}
#[cfg(test)]
mod tests {
    #[test]
    fn t() {}
    fn helper() {}
}
trait Tr { fn sig(&self); }
"""
    )
    names = {function.name: function for function in file.functions}
    assert names["m"].qualified == "sample::inner::S::m"
    assert names["t"].is_test_case and names["t"].in_test_code
    assert names["helper"].in_test_code and not names["helper"].is_test_case
    assert not names["m"].in_test_code
    assert names["sig"].body is None
    assert file.types[0].qualified == "sample::inner::S"
    assert len(file.traits) == 1 and len(file.impls) == 1
    assert parse_source_file("fn a() {}\n", "tests/it.rs").is_test


def test_comments_are_available():
    file = parse_source_file("//! Module doc.\n\n// Plain.\nfn a() {}\n")
    assert [(c.text, c.is_doc, c.is_module_doc) for c in file.comments] == [("Module doc.", True, True), ("Plain.", False, False)]


def test_file_comment_density_counts_each_comment_line_once():
    source = "//! Module doc.\n/// Doc one.\n/// Doc two.\nfn a() {\n    b(); /* x */ /* y */\n    /* two\n       lines */\n}\n"
    card = build_scorecard(codebase_of(parse_source_file(source)), Policy())
    # Comment lines 1, 2, 3, 5, 6 and 7; code lines 4, 5 and 8.
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.comment_density") == pytest.approx(6 / 9)


def test_restating_and_decorative_comments():
    file = parse_source_file("// increment the counter value\nincrement_counter_value(counter);\n// ------ Section ------\nfn a() {}\n")
    assert restating_comments(file) == 1
    assert decorative_comments(file) == 1


def test_interface_documentation():
    file = parse_source_file(
        "/// This documentation sentence runs on for far longer than any reader of an interface would want it to go on.\npub fn a() {}\npub fn b() {}\n/// Short.\npub fn c() {}\n/// Compute total value.\npub fn compute_total_value() {}\n",
        "src/m.rs",
    )
    values = interface_documentation(file)
    assert values["file.undocumented_public"] == 1
    assert values["file.long_first_sentence"] == 1
    assert values["file.wet_docs"] == 1
    assert values["file.missing_module_doc"] == 1


def test_stale_doc_references():
    file = parse_source_file("/// Calls `real_function` and `gone_function`.\nfn real_function() {}\n")
    assert stale_doc_references(file, {"real_function"}) == 1


def test_graph_algorithms():
    graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}}
    assert sorted(sorted(c) for c in strongly_connected(graph)) == [["a", "b", "c"], ["d"]]
    assert reachable(graph, "d") == {"a", "b", "c"}
    ranks = page_rank(graph, 0.85, 30)
    assert ranks["a"] > ranks["d"]
    assert sum(ranks.values()) == pytest.approx(1.0, abs=0.01)
    assert page_rank({}, 0.85, 30) == {}


def test_use_paths_expand_lists():
    file = parse_source_file("use crate::a::{b, c as d, e::f};\n")
    assert use_paths(file.items[0].node.child("argument")) == [("crate", "a", "b"), ("crate", "a", "c"), ("crate", "a", "e", "f")]


def test_file_graph_resolves_use_paths_and_finds_cycles():
    a = parse_source_file("use crate::b::thing;\n", "src/a.rs")
    b = parse_source_file("use super::a::other;\n", "src/b.rs")
    code = codebase_of(a, b)
    graph = FileGraph(code)
    assert graph.edges == {"src/a.rs": {"src/b.rs"}, "src/b.rs": {"src/a.rs"}}
    assert len(dependency_cycles(code, graph).failures) == 1


def test_call_graph_one_caller_only_for_private_functions_in_the_module():
    source = "pub fn top() { low(); shared(); }\nfn low() {}\nfn shared() {}\nfn other() { shared(); }\n"
    code = codebase_of(parse_source_file(source))
    functions = {f.name: f for f in code.functions}
    graph = CallGraph(code)
    assert graph.one_caller(functions["low"]) is functions["top"]
    assert graph.one_caller(functions["shared"]) is None
    assert graph.one_caller(functions["top"]) is None


def test_catch_all_and_bounds_checks():
    code = Codebase([Crate(Manifest("sample", "", []), [parse_source_file("pub struct S<T: Clone>(T);\n", "src/utils.rs")])], [], ["src/utils.rs"], {})
    assert catch_all_names(code).failures
    assert no_type_bounds(code).failures


def test_module_path_overrides_names_each_path_attribute_and_include_of_a_rust_file():
    source = (
        '#[path = "other.rs"]\nmod x;\nmod y {\n    #![path = "z"]\n}\n#[cfg(test)]\n#[path = "t.rs"]\nmod t;\n'
        'fn f() {\n    include!("gen.rs");\n    let s = include_str!("a.rs");\n    let t = include!("table.in");\n}\n'
        'const A: u8 = std::include!(concat!(env!("OUT_DIR"), "/b.rs"));\n'
    )
    failures = module_path_overrides(codebase_of(parse_source_file(source))).failures
    assert sorted(failures) == [
        ("src/lib.rs:1", "`#[path]` attribute"),
        ("src/lib.rs:10", "`include!` of a Rust file"),
        ("src/lib.rs:14", "`include!` of a Rust file"),
        ("src/lib.rs:4", "`#[path]` attribute"),
        ("src/lib.rs:7", "`#[path]` attribute"),
    ]


def test_tests_in_build_compares_syntax_with_the_runner_list():
    file = parse_source_file("#[test]\nfn listed() {}\n#[rstest]\nfn parametrized() {}\n#[test]\nfn compiled_out() {}\n")
    code = codebase_of(file)
    failures = runner_list_check(code, {"tests::listed", "tests::parametrized::case_1"}).failures
    assert [where for where, _ in failures] == ["sample::compiled_out"]


def test_unused_dependency_check():
    file = parse_source_file("use serde::Deserialize;\n")
    manifest = Manifest("sample", "", [Dependency("serde", "normal", False), Dependency("rand-core", "normal", False)])
    code = Codebase([Crate(manifest, [file])], [], [], {})
    assert [what.split()[0] for _, what in unused_dependencies(code, Policy()).failures] == ["rand-core"]


def _deep(body: str) -> dict:
    return measure_function(function_in(f"pub fn deep(a: u32, b: B) -> u32 {{\n    {body}\n}}\n", "deep"))


def test_a_long_expression_chain_is_measured_without_a_recursion_error():
    """Generated code and lookup tables hold chains far longer than Python's recursion limit of 1,000 frames."""
    size = 3000
    total = _deep(" + ".join(["1"] * size))
    assert (total["function.cyclomatic"], total["function.block_depth"], total["function.npath"], total["function.dep_degree"]) == (1, 1, 1, 0)
    calls = _deep("b" + "".join(f".f{index}()" for index in range(size)))
    assert (calls["function.abc_branches"], calls["function.dep_degree"]) == (size, 1)
    branches = _deep("if a == 0 { 0 }" + "".join(f" else if a == {index} {{ {index} }}" for index in range(1, size)) + " else { 9 }")
    assert (branches["function.cyclomatic"], branches["function.cognitive"], branches["function.nesting"]) == (size + 1, size + 1, 1)
    assert (branches["function.npath"], branches["function.block_depth"], branches["function.dep_degree"]) == (size + 1, 2, size)
    condition = _deep("if " + " && ".join(["b.ok"] * size) + " { 1 } else { 2 }")
    assert (condition["function.cyclomatic"], condition["function.cognitive"]) == (size + 1, 3)
    assert (condition["function.complex_conditional"], condition["function.abc_conditions"], condition["function.npath"]) == (size - 1, size + 1, size + 1)
    nested = _deep("if a > 0 { " * size + "1" + " } else { 0 }" * size)
    assert (nested["function.nesting"], nested["function.block_depth"], nested["function.bumpy_road"]) == (size, size + 1, 1)


def test_the_logical_operators_of_a_let_chain_count():
    """`if let Some(x) = a && b && x > 3`: the grammar gives a let chain whose `&&` are plain tokens, not binary expressions."""
    chain = measure_function(function_in("fn f(a: Option<u32>, b: bool) -> u32 {\n    if let Some(x) = a && b && x > 3 {\n        return x;\n    }\n    0\n}\n", "f"))
    # Cyclomatic: 1, the `if` and two `&&`. Cognitive: the `if` and one run of `&&`. NPath: two `&&`, the block and the path around it.
    assert (chain["function.cyclomatic"], chain["function.cognitive"], chain["function.complex_conditional"], chain["function.npath"]) == (4, 2, 2, 4)
    mixed = measure_function(function_in("fn f(a: Option<u32>, b: bool, c: bool) -> u32 {\n    if (b || c) && let Some(x) = a {\n        return x;\n    }\n    0\n}\n", "f"))
    # One `&&` of the chain and one `||` in the parentheses: two operators, two runs.
    assert (mixed["function.cyclomatic"], mixed["function.cognitive"], mixed["function.complex_conditional"]) == (4, 3, 2)


def test_a_function_without_a_mutant_has_no_count_of_missed_mutants():
    """In a run that mutates the diff only, 0 would read as "none survived"."""
    from smog.domain.lenses.function_tests import measure_mutants

    assert measure_mutants([], None, False) == {}


def test_one_long_statement_set_off_by_blank_lines_is_a_paragraph_of_its_own():
    literal = "    let {name} = call(\n        1,\n        2,\n        3,\n        4,\n    );\n"
    source = "fn f() {\n" + literal.format(name="x") + "\n" + literal.format(name="y") + "}\n"
    assert paragraphs(function_in(source, "f")) == [6, 6]


def test_a_match_counts_as_its_first_line_apart_from_the_statements_in_an_arm_block():
    arms = "".join(f"        K::V{index} => {index},\n" for index in range(12))
    source = f"fn f(k: K) -> u8 {{\n    match k {{\n{arms}    }}\n}}\n"
    assert paragraphs(function_in(source, "f")) == [1]
    block = "fn f(k: K) {\n    match k {\n        K::A => {\n            a();\n            b();\n            c();\n        }\n        K::B => d(),\n    }\n}\n"
    # The match line and the three statements in the arm's block.
    assert paragraphs(function_in(block, "f")) == [4]


def test_a_struct_literal_or_pattern_counts_as_its_first_line():
    source = "fn f(s: S) {\n    let S {\n        a,\n        b,\n    } = s;\n    g(T {\n        a: 1,\n        b: 2,\n    })\n}\n"
    assert paragraphs(function_in(source, "f")) == [2]
