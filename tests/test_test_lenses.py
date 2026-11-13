"""Hand-computed values of the test measurements read from syntax."""

from smog.adapter.cargo_tools import parse_junit, parse_test_failures
from smog.domain.code import Codebase, Crate, Manifest
from smog.domain.lenses.tests import (
    assertion_windows,
    assertions,
    copied_assertion_windows,
    has_message,
    lazy_tests,
    measure_test,
    measure_test_runs,
    runner_key,
    scope,
    size_class,
    test_run_totals,
)
from smog.domain.measure import build_scorecard
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import MutantOutcome, TestAttempt, ToolResults
from tests.helpers import function_in, parse_source_file

SMELLS = """
pub fn open() {}
pub fn load() {}
pub fn store() {}

#[test]
fn roulette() {
    let text = load().to_string();
    assert!(text.is_empty());
    assert_eq!(text, "a".to_string(), "the text");
    assert_eq!(text.len(), 0u32);
    loop { break; }
}

#[test]
fn explained() {
    assert!(open(), "opens");
    assert_eq!(load(), 1.5, "loads {}", 2);
    assert_ne!(store(), 1);
}

#[test]
fn empty() {
    // nothing yet
}

#[test]
#[should_panic(expected = "boom")]
fn panics() {
    store();
}

#[test]
fn by_hand() {
    let file = std::fs::File::open("data.txt");
    if file.is_err() { panic!("no file"); }
    let caught = std::panic::catch_unwind(|| store());
}

#[test]
fn checked_file() {
    if std::path::Path::new("data.txt").exists() { std::fs::read("data.txt"); }
}
"""


def _values(name: str, production=frozenset({"open", "load", "store"})) -> dict:
    return measure_test(function_in(SMELLS, name), production_names=production)


def test_assertion_count_and_messages():
    assert _values("roulette")["test.assertions"] == 3
    assert _values("empty")["test.assertions"] == 0
    # `assert!` has a message from the second argument on, `assert_eq!` from the third.
    assert [has_message(node) for node in assertions(function_in(SMELLS, "roulette"))] == [False, True, False]
    assert [has_message(node) for node in assertions(function_in(SMELLS, "explained"))] == [True, True, False]


def test_assertion_roulette_needs_two_assertions_without_a_message():
    assert _values("roulette")["test.smell.assertion_roulette"] == 1
    assert _values("explained")["test.smell.assertion_roulette"] == 0


def test_a_should_panic_test_is_not_without_assertion():
    assert _values("panics")["test.no_assertion"] == 0
    assert _values("empty")["test.no_assertion"] == 1


def test_empty_test_has_no_statement():
    assert _values("empty")["test.smell.empty_test"] == 1
    assert _values("panics")["test.smell.empty_test"] == 0


def test_loop_is_conditional_logic():
    assert _values("roulette")["test.smell.conditional_logic"] == 1
    assert _values("by_hand")["test.smell.conditional_logic"] == 1


def test_magic_numbers_are_all_numeric_literals_in_assertions():
    # roulette: `0u32`. explained: 1.5, 2 and 1; the 2 is a message argument and still inside the assertion.
    assert _values("roulette")["test.smell.magic_number"] == 1
    assert _values("explained")["test.smell.magic_number"] == 3


def test_exception_handling_counts_panic_and_catch_unwind():
    assert _values("by_hand")["test.smell.exception_handling"] == 2
    assert _values("panics")["test.smell.exception_handling"] == 0


def test_resource_optimism_is_a_file_without_an_existence_check():
    assert _values("by_hand")["test.smell.resource_optimism"] == 1
    assert _values("checked_file")["test.smell.resource_optimism"] == 0
    assert _values("roulette")["test.smell.resource_optimism"] == 0


def test_sensitive_equality_skips_string_literals():
    # `load().to_string()` counts, `"a".to_string()` does not.
    assert _values("roulette")["test.smell.sensitive_equality"] == 1


def test_eager_test_counts_distinct_production_functions():
    assert _values("explained")["test.smell.eager_test"] == 1  # open, load, store
    assert _values("roulette")["test.smell.eager_test"] == 0  # load only
    assert "test.smell.eager_test" not in measure_test(function_in(SMELLS, "explained"))
    # `len` and `is_empty` are no production functions here; they are once a production function has that name.
    assert _values("roulette", frozenset({"load", "len"}))["test.smell.eager_test"] == 1


def test_lazy_tests_share_a_production_function():
    file = parse_source_file(SMELLS)
    tests = {f.start_line: f.name for f in file.functions if f.is_test_case}
    lazy = lazy_tests([f for f in file.functions if f.is_test_case], frozenset({"open", "load", "store"}))
    # load: roulette and explained. store: explained, panics and by_hand. Nothing else is shared.
    assert {tests[line] for line in lazy} == {"roulette", "explained", "panics", "by_hand"}


def test_the_scorecard_carries_the_test_smells():
    codebase = Codebase([Crate(Manifest("sample", "", []), [parse_source_file(SMELLS)])], [], [], {})
    card = build_scorecard(codebase, Policy())
    assert card.find(PieceKind.TEST, "sample::explained").value("test.smell.lazy_test") == 1
    assert card.find(PieceKind.TEST, "sample::empty").value("test.smell.lazy_test") == 0
    assert card.find(PieceKind.TEST, "sample::explained").value("test.smell.eager_test") == 1


COMPLEX = """
#[test]
fn branches() {
    for case in cases() {
        if case.ok && case.ready {
            assert!(run(case));
        }
    }
}

#[test]
fn straight() {
    assert!(run(1));
}
"""


def test_test_complexity_uses_the_function_rules():
    # Cyclomatic: 1 + for + if + &&. Cognitive: for 1, nested if 2, one run of && 1.
    values = measure_test(function_in(COMPLEX, "branches"))
    assert (values["test.cyclomatic"], values["test.cognitive"]) == (4, 4)
    values = measure_test(function_in(COMPLEX, "straight"))
    assert (values["test.cyclomatic"], values["test.cognitive"]) == (1, 0)


BLOCKS = """
#[test]
fn first() {
    let s = make();
    assert_eq!(s.a, 1);
    assert_eq!(s.b, 2);
    assert_eq!( s.c, 3 ); // spacing differs
    assert!(s.d);
}

#[test]
fn second() {
    let s = other();
    assert!(s.z);
    assert_eq!(s.a, 1);
    assert_eq!(s.b, 2);
    assert_eq!(s.c, 3);
}

#[test]
fn third() {
    assert_eq!(s.a, 1);
    assert_eq!(s.b, 2);
    let t = 1;
    assert_eq!(s.c, 3);
}
"""


def test_a_copied_assertion_block_is_three_neighboring_assertions_with_equal_tokens():
    functions = parse_source_file(BLOCKS).functions
    copied = copied_assertion_windows(functions)
    # first and second share a, b, c; third's block is split by the `let`.
    assert copied == {("assert_eq!(s.a,1)", "assert_eq!(s.b,2)", "assert_eq!(s.c,3)")}
    assert [bool(assertion_windows(f, 3) & copied) for f in functions] == [True, True, False]
    # With blocks of two, third's first two assertions are a copy as well.
    pairs = copied_assertion_windows(functions, {**DEFAULT_SETTINGS, "assertion_block_min_statements": 2})
    assert [bool(assertion_windows(f, 2) & pairs) for f in functions] == [True, True, True]


def test_the_scorecard_flags_tests_with_a_copied_assertion_block():
    codebase = Codebase([Crate(Manifest("sample", "", []), [parse_source_file(BLOCKS)])], [], [], {})
    card = build_scorecard(codebase, Policy())
    values = [card.find(PieceKind.TEST, f"sample::{name}").value("test.duplicated_assertion_block") for name in ("first", "second", "third")]
    assert values == [1, 1, 0]


SIZES = """
#[test]
fn small() {
    assert_eq!(add(1, 2), 3);
}

#[test]
fn local_server() {
    let url = "http://127.0.0.1:8080/health";
    assert!(get(url));
}

#[test]
fn file() {
    let text = std::fs::read_to_string("a.txt");
}

#[test]
fn remote() {
    let text = std::fs::read_to_string("a.txt");
    assert!(get("https://example.com/health"));
}

#[test]
fn program() {
    Command::new("tool").status();
}

fn helper() {}
"""


def _test_in(name: str, path: str = "src/lib.rs", crate_dir: str = ""):
    return next(f for f in parse_source_file(SIZES, path, crate_dir=crate_dir).functions if f.name == name)


def test_size_class_reads_urls_and_resource_names():
    assert [size_class(_test_in(name)) for name in ("small", "local_server", "file", "remote", "program")] == [1, 1, 2, 3, 2]


def test_scope_reads_the_path_inside_the_crate_and_program_names():
    assert scope(_test_in("small")) == 1
    assert scope(_test_in("small", "tests/api.rs")) == 2
    assert scope(_test_in("small", "crates/a/tests/api.rs", "crates/a")) == 2
    # A `tests` folder inside `src` holds unit tests.
    assert scope(_test_in("small", "src/parser/tests/cases.rs")) == 1
    assert scope(_test_in("small", "tests/e2e/login.rs")) == 3
    assert scope(_test_in("program")) == 3


def test_only_test_cases_have_a_size_and_a_scope_and_the_codebase_has_their_shares():
    assert "test.size_class" not in measure_test(_test_in("helper", "tests/api.rs"))
    files = [parse_source_file(SIZES), parse_source_file("#[test]\nfn api() {\n    assert!(true);\n}\n", "tests/api.rs")]
    card = build_scorecard(Codebase([Crate(Manifest("sample", "", []), files)], [], [], {}), Policy())
    root = card.root
    # Six test cases. Sizes: small, local_server and api are small, file and program medium, remote large.
    assert [root.value(f"codebase.{name}_test_share") for name in ("small", "medium", "large")] == [3 / 6, 2 / 6, 1 / 6]
    # Scopes: api is in `tests`, program runs a program, the other four are unit tests.
    assert [root.value(f"codebase.{name}_test_share") for name in ("unit", "integration", "end_to_end")] == [4 / 6, 1 / 6, 1 / 6]
    empty = build_scorecard(Codebase([Crate(Manifest("sample", "", []), [parse_source_file("pub fn f() {}\n")])], [], [], {}), Policy())
    assert "codebase.unit_test_share" not in empty.root.values


TOOLED = """pub fn checked(x: u32) -> u32 {
    x + 1
}

pub fn unchecked(x: u32) -> u32 {
    x + 2
}

pub fn never_run() -> u32 {
    3
}

#[test]
fn runs() {
    assert_eq!(checked(1), 2);
    unchecked(1);
}
"""


def _tooled_card(whole_tree: bool = True, **results):
    tools = ToolResults()
    tools.record(mutants_whole_tree=whole_tree, **results)
    files = [parse_source_file(TOOLED), parse_source_file("pub fn other() -> u32 {\n    4\n}\n", "src/other.rs")]
    return build_scorecard(Codebase([Crate(Manifest("sample", "", []), files)], [], [], {}), Policy(), tools=tools)


MUTANTS = [
    MutantOutcome("src/lib.rs", 2, "caught"),
    MutantOutcome("src/lib.rs", 2, "caught"),
    MutantOutcome("src/lib.rs", 6, "missed"),
    MutantOutcome("src/lib.rs", 10, "missed"),
    MutantOutcome("src/lib.rs", 10, "unviable"),
    MutantOutcome("src/other.rs", 2, "timeout"),
]
# Lines 15 to 17 are test code. Line 10 and the line of src/other.rs have no hit.
COVERABLE = {"src/lib.rs": {1, 2, 5, 6, 9, 10, 15, 16, 17}, "src/other.rs": {1, 2}}
UNCOVERED = {"src/lib.rs": {9, 10}, "src/other.rs": {1, 2}}


def test_mutation_score_is_caught_over_caught_and_missed_for_crate_and_codebase():
    card = _tooled_card(mutants=MUTANTS)
    crate = card.find(PieceKind.CRATE, "sample")
    # 2 caught, 2 missed; the unviable mutant and the timeout are left out.
    assert crate.value("crate.mutation_score") == card.root.value("codebase.mutation_score") == 2 / 4
    assert "crate.covered_mutation_score" not in crate.values  # coverage did not run
    policy_counts_timeouts = Policy()
    policy_counts_timeouts.setting("mutation_timeouts_caught", True)
    tools = ToolResults()
    tools.record(mutants=MUTANTS, mutants_whole_tree=True)
    codebase = Codebase([Crate(Manifest("sample", "", []), [parse_source_file(TOOLED), parse_source_file("pub fn other() {}\n", "src/other.rs")])], [], [], {})
    assert build_scorecard(codebase, policy_counts_timeouts, tools=tools).root.value("codebase.mutation_score") == 3 / 5


def test_the_mutants_of_a_diff_give_the_codebase_no_mutation_score():
    card = _tooled_card(whole_tree=False, mutants=MUTANTS, coverable=COVERABLE, uncovered=UNCOVERED)
    assert "codebase.mutation_score" not in card.root.values and "codebase.covered_mutation_score" not in card.root.values
    assert card.root.value("codebase.surviving_mutants") == 2
    assert card.find(PieceKind.CRATE, "sample").value("crate.mutation_score") == 2 / 4


def test_covered_mutation_score_leaves_out_mutants_on_lines_no_test_ran():
    card = _tooled_card(mutants=MUTANTS, coverable=COVERABLE, uncovered=UNCOVERED)
    # On covered lines: 2 caught on line 2 and 1 missed on line 6. Line 10 and src/other.rs were not run.
    assert card.root.value("codebase.covered_mutation_score") == 2 / 3
    assert card.find(PieceKind.CRATE, "sample").value("crate.covered_mutation_score") == 2 / 3
    assert card.root.value("codebase.mutation_score") == 2 / 4


def test_a_score_without_a_caught_or_missed_mutant_has_no_value():
    card = _tooled_card(mutants=[MutantOutcome("src/lib.rs", 2, "unviable")], coverable=COVERABLE, uncovered=UNCOVERED)
    assert "codebase.mutation_score" not in card.root.values
    assert "codebase.covered_mutation_score" not in card.root.values


def test_line_coverage_of_file_crate_and_codebase_leaves_out_test_code():
    card = _tooled_card(coverable=COVERABLE, uncovered=UNCOVERED)
    # src/lib.rs: production lines 1, 2, 5, 6, 9, 10 with 9 and 10 not hit. src/other.rs: 2 lines, none hit.
    assert card.find(PieceKind.FILE, "src/lib.rs").value("file.coverage") == 4 / 6
    assert card.find(PieceKind.FILE, "src/other.rs").value("file.coverage") == 0
    assert card.find(PieceKind.CRATE, "sample").value("crate.coverage") == card.root.value("codebase.coverage") == 4 / 8
    assert "file.mutation_score" not in card.find(PieceKind.FILE, "src/lib.rs").values


def test_coverage_has_no_value_without_the_tool_or_without_a_coverable_line():
    assert "codebase.coverage" not in _tooled_card(mutants=[]).root.values
    card = _tooled_card(coverable={"src/lib.rs": {16}}, uncovered={})
    assert "file.coverage" not in card.find(PieceKind.FILE, "src/lib.rs").values


JUNIT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="nextest-run" tests="4" failures="1" errors="0">
    <testsuite name="my-crate::api" tests="1">
        <testcase name="api" classname="my-crate::api" time="0.018"></testcase>
    </testsuite>
    <testsuite name="my-crate" tests="3">
        <testcase name="inner::tests::passes" classname="my-crate" time="61.5"></testcase>
        <testcase name="inner::tests::flaky" classname="my-crate" time="0.012">
            <flakyFailure time="0.018" message="panicked" type="test failure with exit code 101">first run</flakyFailure>
        </testcase>
        <testcase name="inner::tests::fails" classname="my-crate" time="0.018">
            <failure message="panicked" type="test failure with exit code 101">left: 1</failure>
            <rerunFailure time="0.012" message="panicked" type="test failure with exit code 101">left: 1</rerunFailure>
        </testcase>
    </testsuite>
    <testsuite name="my-crate::bin/my-tool" tests="1">
        <testcase name="tests::runs" classname="my-crate::bin/my-tool" time="0.5"></testcase>
    </testsuite>
</testsuites>
"""

CARGO_TEST = """   Compiling my-crate v0.1.0 (/work/repo)
     Running unittests src/lib.rs (/tmp/x/debug/deps/my_crate-934bbc7179260f35)

running 2 tests (shuffle seed: 7)
test inner::tests::fails ... FAILED
test inner::tests::passes ... ok

     Running tests/api.rs (/tmp/x/debug/deps/api-e6cefb68b7fc9df3)

running 1 test (shuffle seed: 7)
test api ... FAILED
"""


def _attempts():
    return parse_junit(JUNIT)


def test_the_junit_report_gives_time_and_flakiness_per_binary_and_test():
    attempts = _attempts()
    assert set(attempts) == {("api", "api"), ("my_crate", "inner::tests::passes"), ("my_crate", "inner::tests::flaky"), ("my_crate", "inner::tests::fails"), ("my_tool", "tests::runs")}
    flaky, fails = attempts[("my_crate", "inner::tests::flaky")], attempts[("my_crate", "inner::tests::fails")]
    assert (flaky.flaky, flaky.failed, flaky.seconds) == (True, False, 0.012)
    assert (fails.flaky, fails.failed) == (False, True)


def test_cargo_test_output_gives_the_failed_tests_per_binary():
    assert parse_test_failures(CARGO_TEST) == {("my_crate", "inner::tests::fails"), ("api", "api")}


RUNS = """
pub mod inner {
    #[cfg(test)]
    mod tests {
        #[test]
        fn flaky() {}
        #[test]
        fn passes() {}
        #[test]
        fn unknown() {}
    }
}
"""


def _run_function(name: str, source: str = RUNS, path: str = "src/lib.rs"):
    return next(f for f in parse_source_file(source, path, crate="my-crate").functions if f.name == name)


def test_a_test_is_named_by_its_binary_and_its_path_in_it():
    assert runner_key(_run_function("flaky")) == ("my_crate", "inner::tests::flaky")
    assert runner_key(_run_function("api", "#[test]\nfn api() {}\n", "tests/api.rs")) == ("api", "api")
    assert runner_key(_run_function("runs", "mod tests {\n    #[test]\n    fn runs() {}\n}\n", "src/bin/my-tool.rs")) == ("my_tool", "tests::runs")


def _run_tools(**results) -> ToolResults:
    tools = ToolResults()
    tools.record(**results)
    return tools


def test_flaky_and_duration_come_from_the_retried_run():
    tools = _run_tools(test_attempts=_attempts())
    assert measure_test_runs(_run_function("flaky"), tools) == {"test.flaky": 1, "test.duration": 0.012}
    assert measure_test_runs(_run_function("passes"), tools) == {"test.flaky": 0, "test.duration": 61.5}
    # A test the runner did not report, and a run without the tool, give no value.
    assert measure_test_runs(_run_function("unknown"), tools) == {}
    assert measure_test_runs(_run_function("flaky"), ToolResults()) == {}
    # A parametrized test runs as one test per case: flaky when a case is, and its duration is their sum.
    cases = {("my_crate", "inner::tests::flaky::case_1_low"): TestAttempt(0.25, False, False), ("my_crate", "inner::tests::flaky::case_2_high"): TestAttempt(0.5, True, False)}
    assert measure_test_runs(_run_function("flaky"), _run_tools(test_attempts=cases)) == {"test.flaky": 1, "test.duration": 0.75}
    assert measure_test_runs(_run_function("flaky"), _run_tools(test_attempts={("my_crate", "inner::tests::flaky_too"): TestAttempt(1.0, True, False)})) == {}
    # One flaky test; one test above 60 seconds. A test that fails every attempt is not flaky.
    assert test_run_totals(tools) == {"codebase.flaky_tests": 1, "codebase.slow_tests": 1}
    assert test_run_totals(tools, {**DEFAULT_SETTINGS, "slow_test_seconds": 0.4})["codebase.slow_tests"] == 2


def test_order_dependent_tests_fail_in_some_orders_and_pass_in_others():
    always, sometimes = ("my_crate", "inner::tests::passes"), ("my_crate", "inner::tests::flaky")
    tools = _run_tools(order_failures=[{always}, {always, sometimes}, {always}])
    assert tools.order_dependent() == {sometimes}
    assert measure_test_runs(_run_function("flaky"), tools) == {"test.order_dependent": 1}
    assert measure_test_runs(_run_function("passes"), tools) == {"test.order_dependent": 0}
    case = _run_tools(order_failures=[set(), {("my_crate", "inner::tests::passes::case_2")}])
    assert measure_test_runs(_run_function("passes"), case) == {"test.order_dependent": 1}
    assert test_run_totals(tools) == {"codebase.order_dependent_tests": 1}
    assert test_run_totals(ToolResults()) == {}
    assert _run_tools(order_failures=[{always}]).order_dependent() == set()
