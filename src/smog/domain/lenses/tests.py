"""Test lenses (design section 3.8). Each reads one test function.

The `test.smell.*` values follow the 19 rules of tsDetect (testsmells.org/pages/testsmells.html, read 2026-11-10),
which are written for Java and JUnit. The rule each value applies is quoted in `measure_test`. Three rules have
no meaning in Rust and no ID: Constructor Initialization ("A test class that contains a constructor
declaration") and General Fixture ("Not all fields instantiated within the setUp method of a test class are
utilized by all test methods") need test classes with a `setUp` method, which libtest does not have, and Default
Test ("A test class is named either `ExampleUnitTest' or `ExampleInstrumentedTest'") names files that Android
Studio creates. Unknown Test is `test.no_assertion`.
"""

import fnmatch
import re
from collections import Counter

from smog.domain.code import Function
from smog.domain.lenses.function import complexity
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.tools import ToolResults
from smog.domain.syntax import Node

_NUMBER_KINDS = ("integer_literal", "float_literal")
_CONTROL_KINDS = ("if_expression", "match_expression", "for_expression", "while_expression", "loop_expression")
_URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://(\[[^\]]*\]|[^/:\s\"]+)")
SMALL, MEDIUM, LARGE = 1, 2, 3
UNIT, INTEGRATION, END_TO_END = 1, 2, 3


def macro_name(node: Node) -> str:
    return node.child("macro").text.rsplit("::", 1)[-1]


def assertions(function: Function) -> list[Node]:
    if function.body is None:
        return []
    return [node for node in function.body.find("macro_invocation") if "assert" in macro_name(node)]


def _helper_assertions(function: Function, prefixes: tuple[str, ...]) -> int:
    return sum(1 for call in function.calls() if call.name.startswith(prefixes))


def assertion_tier(node: Node, settings: dict = DEFAULT_SETTINGS) -> int:
    """With the default settings 3: compares a value. 2: `assert!` on another condition. 1: `assert!` on is_ok, is_some and the like."""
    if macro_name(node) in settings["value_assertion_macros"] or any(word in node.text for word in settings["value_assertion_words"]):
        return settings["assertion_tier_value"]
    weak = any(re.search(pattern, node.text) for pattern in settings["weak_assertion_patterns"])
    return settings["assertion_tier_weak" if weak else "assertion_tier_condition"]


def test_tier(function: Function, settings: dict = DEFAULT_SETTINGS) -> int:
    return max((assertion_tier(node, settings) for node in assertions(function)), default=0)


def split_arguments(macro: Node) -> list[str]:
    """Top-level comma-separated arguments of a macro call, as text."""
    tree = macro.child_of_kind("token_tree")
    parts: list[list[str]] = [[]]
    for child in tree.children[1:-1] if tree else ():
        if child.text == ",":
            parts.append([])
        else:
            parts[-1].append(child.text)
    return ["".join(part) for part in parts if part]


def _assertion_runs(body: Node) -> list[list[Node]]:
    """Runs of neighboring top-level assertion statements, in source order."""
    runs: list[list[Node]] = [[]]
    for statement in body.statements:
        inner = statement.named[0] if statement.kind == "expression_statement" and statement.named else statement
        if inner.kind == "macro_invocation" and "assert" in macro_name(inner):
            runs[-1].append(inner)
        elif runs[-1]:
            runs.append([])
    return [run for run in runs if run]


def _longest_assertion_run(body: Node) -> int:
    return max((len(run) for run in _assertion_runs(body)), default=0)


def assertion_windows(function: Function, size: int) -> set[tuple[str, ...]]:
    """Every sequence of `size` neighboring top-level assertion statements of the function, as token texts.

    Two sequences are equal when their tokens are, so white space and comments do not matter.
    """
    if function.body is None or size < 1:
        return set()
    windows = set()
    for run in _assertion_runs(function.body):
        texts = ["".join(node.token_texts()) for node in run]
        windows.update(tuple(texts[start : start + size]) for start in range(len(texts) - size + 1))
    return windows


def copied_assertion_windows(functions: list[Function], settings: dict = DEFAULT_SETTINGS) -> set[tuple[str, ...]]:
    """The assertion sequences (`assertion_windows`) that occur in more than one of the functions.

    This is the basis of test.duplicated_assertion_block: a test has the value 1 when one of its sequences of
    `assertion_block_min_statements` neighboring assertions is in this set. No source with a counting rule was
    found for copied assertion blocks; the rule and the default of 3 statements are Smog's own.
    """
    seen: Counter = Counter()
    for function in functions:
        seen.update(assertion_windows(function, settings["assertion_block_min_statements"]))
    return {window for window, count in seen.items() if count > 1}


def size_class(function: Function, settings: dict = DEFAULT_SETTINGS) -> int:
    """The test size of "Software Engineering at Google", chapter 11 (abseil.io/resources/swe-book, read 2026-11-10),
    read from the names in the test's own body: 1 small, 2 medium, 3 large.

    The book: small tests "must run in a single process" and "aren't allowed to sleep, perform I/O operations, or
    make any other blocking calls"; medium tests "can span multiple processes, use threads, and can make blocking
    calls" but "aren't allowed to make network calls to any system other than localhost"; large tests lift that
    restriction. Google enforces the sizes at run time. Smog reads syntax:

    - large: a string literal holds a URL (`scheme://host`) whose host is not in `test_size_local_hosts`;
    - medium: otherwise, a token of the body is one of `test_size_medium_names`, the names of file, socket,
      process, thread and sleep APIs;
    - small: otherwise.

    What a helper or the code under test does is not seen, so a test can be larger than its class.
    """
    body = function.body
    if body is None:
        return SMALL
    local = settings["test_size_local_hosts"]
    for token in body.tokens():
        if token.kind in ("string_literal", "raw_string_literal") and any(host not in local for host in _URL_HOST.findall(token.text)):
            return LARGE
    return MEDIUM if set(settings["test_size_medium_names"]) & set(body.token_texts()) else SMALL


def scope(function: Function, settings: dict = DEFAULT_SETTINGS) -> int:
    """The scope of a test, read from where it lives and what it names: 1 unit, 2 integration, 3 end-to-end.

    "Software Engineering at Google", chapter 11 (read 2026-11-10) defines scope by what a test validates:
    narrow-scoped unit tests "validate the logic in a small, focused part of the codebase", medium-scoped
    integration tests "verify interactions between a small number of components", and large-scoped end-to-end
    tests "validate the interaction of several distinct parts of the system". No source gives a counting rule;
    this one is Smog's own:

    - end-to-end: the file's path inside its crate matches one of `test_end_to_end_paths`, or the body names one
      of `test_end_to_end_names`, which by default are the names used to run a program (`Command`, `cargo_bin`);
    - integration: otherwise, the file's path inside its crate matches one of `test_integration_paths`, by
      default Cargo's `tests` folder, whose files see only the crate's public interface;
    - unit: otherwise, which covers tests inside `src`.

    In a pattern `*` also matches `/`.
    """
    path = function.file.crate_path
    names = set(function.body.token_texts()) if function.body else set()
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in settings["test_end_to_end_paths"]) or names & set(settings["test_end_to_end_names"]):
        return END_TO_END
    if any(fnmatch.fnmatchcase(path, pattern) for pattern in settings["test_integration_paths"]):
        return INTEGRATION
    return UNIT


def class_shares(pieces_values: list[dict[str, float]]) -> dict[str, float]:
    """Shares of the test cases in each size class and each scope, from the values of the test pieces.

    codebase.small_test_share, .medium_test_share and .large_test_share are test cases with that
    test.size_class over all test cases; codebase.unit_test_share, .integration_test_share and
    .end_to_end_test_share the same for test.scope. The book quoted in `scope` aims at "around 80%" unit tests,
    "15%" integration tests and "5% end-to-end tests", counted by test case. No value without a test case.
    """
    sizes = Counter(values["test.size_class"] for values in pieces_values if "test.size_class" in values)
    scopes = Counter(values["test.scope"] for values in pieces_values if "test.scope" in values)
    total = sum(sizes.values())
    if not total:
        return {}
    return {
        "codebase.small_test_share": sizes[SMALL] / total,
        "codebase.medium_test_share": sizes[MEDIUM] / total,
        "codebase.large_test_share": sizes[LARGE] / total,
        "codebase.unit_test_share": scopes[UNIT] / total,
        "codebase.integration_test_share": scopes[INTEGRATION] / total,
        "codebase.end_to_end_test_share": scopes[END_TO_END] / total,
    }


def _is_redundant(node: Node) -> bool:
    arguments = split_arguments(node)
    if macro_name(node) == "assert" and arguments[:1] == ["true"]:
        return True
    return macro_name(node) in ("assert_eq", "assert_ne") and len(arguments) >= 2 and arguments[0] == arguments[1]


def has_message(node: Node) -> bool:
    """True when an assertion macro has an argument after the values it compares.

    `assert!` and other one-value macros take the message from the second argument on; a macro whose name ends
    in `_eq` or `_ne`, and `assert_matches!`, from the third.
    """
    name = macro_name(node)
    values = 2 if name.endswith(("_eq", "_ne", "_matches")) else 1
    return len(split_arguments(node)) > values


def _sensitive_equality(body: Node, methods: tuple[str, ...]) -> int:
    """`.to_string()` calls, or those of another method of `sensitive_equality_methods`, whose receiver is not a string literal."""
    tokens = list(body.tokens())
    return sum(
        1
        for before, dot, name in zip(tokens, tokens[1:], tokens[2:])
        if name.text in methods and dot.text == "." and before.kind not in ("string_literal", "raw_string_literal")
    )


def production_calls(function: Function, production_names: frozenset[str]) -> set[str]:
    """Names the function calls that are names of functions outside test code. Matched by name, not by resolution."""
    return {call.name for call in function.calls()} & production_names


def _is_exact_output(node: Node, settings: dict) -> bool:
    if macro_name(node) in settings["test_exact_output_macros"]:
        return True
    tokens = list(node.tokens())
    if any(token.kind == "string_literal" and len(token.text) - 2 >= settings["exact_output_min_characters"] for token in tokens):
        return True
    return any(token.text in settings["exact_output_calls"] for token in tokens)


def measure_test(function: Function, settings: dict = DEFAULT_SETTINGS, production_names: frozenset[str] | None = None) -> dict[str, float]:
    """The values that read one function in test code. tsDetect's rule is quoted where a value follows one.

    - test.assertions: macro calls with `assert` in the name. Assertions inside called helpers are not counted.
    - test.no_assertion (Unknown Test: "A test method that does not contain a single assertion statement and
      @Test(expected) annotation parameter"): 1 for a test case with no assertion macro, no call to a helper named
      `assert*`, `verify*`, `check_*` or `expect_*`, and no `#[should_panic]`, which is Rust's `expected`.
    - assertion_roulette ("A test method contains more than one assertion statement without an
      explanation/message"): 1 when more than one assertion has no message argument (`has_message`).
    - conditional_logic ("A test method that contains one or more control statements (i.e if, switch,
      conditional expression, for, foreach and while statement)"): the number of `if`, `match`, `for`, `while`
      and `loop` expressions. `loop` is Rust's `while (true)`.
    - duplicate_assert ("more than one assertion statement with the same parameters"): assertions whose text
      equals an earlier one.
    - eager_test ("A test method contains multiple calls to multiple production methods"): 1 when the test calls
      more than `eager_test_calls_above` distinct production functions (`production_calls`). No value when
      `production_names` is None.
    - empty_test ("A test method that does not contain a single executable statement"): 1 for a test case whose
      body holds no statement and no expression.
    - exception_handling ("A test method that contains either a throw statement or a catch clause"): the number
      of `panic!` calls and `catch_unwind` names. Rust has neither statement; these are the two ways a test
      decides by hand whether it fails, where `assert!` and `#[should_panic]` would do it.
    - ignored_test ("contains the @Ignore annotation"): 1 with an `#[ignore]` attribute.
    - magic_number ("An assertion method that contains a numeric literal as an argument"): integer and float
      literals anywhere inside assertions, 0 and 1 included, as in tsDetect.
    - mystery_guest ("object instances of files and databases classes"): tokens that name a file, socket,
      process or environment type.
    - print ("invokes either the print or println or printf or write method of the System class"): print macros.
    - redundant_assertion ("the expected and actual parameters are the same"): `assert!(true)` and comparisons
      of a text with itself.
    - resource_optimism ("utilizes an instance of a File class without calling the exists(), isFile() or
      notExists() methods"): 1 when the body names `fs`, `File` or `OpenOptions` and none of `exists`,
      `try_exists` and `is_file`.
    - sensitive_equality ("A test method invokes the toString() method of an object"): `.to_string()` calls on
      anything but a string literal, where `to_string` only builds a `String`.
    - sleep ("invokes the Thread.sleep() method"): tokens equal to `sleep`.

    Lazy Test needs the other tests of the file and is computed by `lazy_tests`.

    test.cyclomatic and test.cognitive are the two complexity numbers of a production function
    (`lenses.function._Facts`), applied to the test's body. test.size_class (`size_class`) and test.scope (`scope`)
    are set for test cases only; a helper in test code has no size and no scope of its own.
    """
    body = function.body
    values = {"test.length": function.lines}
    if body is None:
        return values
    asserted = assertions(function)
    texts = Counter(node.text for node in asserted)
    tokens = body.token_texts()
    macros = [macro_name(node) for node in body.find("macro_invocation")]
    numbers = sum(1 for node in asserted for token in node.tokens() if token.kind in _NUMBER_KINDS)
    unchecked = not asserted and not _helper_assertions(function, settings["assertion_helper_prefixes"]) and not function.has_attribute(r"^should_panic")
    cyclomatic, cognitive = complexity(body)
    if function.is_test_case:
        values.update({"test.size_class": size_class(function, settings), "test.scope": scope(function, settings)})
    values.update(
        {
            "test.assertions": len(asserted),
            "test.cyclomatic": cyclomatic,
            "test.cognitive": cognitive,
            "test.no_assertion": int(function.is_test_case and unchecked),
            "test.interaction_assertions": sum(1 for call in function.calls() if any(re.fullmatch(pattern, call.name) for pattern in settings["mock_call_patterns"])),
            "test.exact_output": sum(1 for node in asserted if _is_exact_output(node, settings))
            + sum(m in settings["test_exact_output_macros"] for m in macros),
            "test.assertion_block": _longest_assertion_run(body),
            "test.smell.assertion_roulette": int(sum(1 for node in asserted if not has_message(node)) > settings["assertion_roulette_unexplained_above"]),
            "test.smell.conditional_logic": sum(1 for _ in body.find(*_CONTROL_KINDS)),
            "test.smell.duplicate_assert": sum(count - 1 for count in texts.values()),
            "test.smell.empty_test": int(function.is_test_case and not body.statements),
            "test.smell.exception_handling": macros.count("panic") + tokens.count("catch_unwind"),
            "test.smell.ignored_test": int(function.has_attribute(r"^ignore")),
            "test.smell.magic_number": numbers,
            "test.smell.mystery_guest": sum(1 for token in tokens if token in settings["test_mystery_guest_names"]),
            "test.smell.print": sum(1 for name in macros if name in settings["test_print_macros"]),
            "test.smell.redundant_assertion": sum(1 for node in asserted if _is_redundant(node)),
            "test.smell.resource_optimism": int(bool(set(settings["test_resource_file_names"]) & set(tokens)) and not set(settings["test_resource_existence_checks"]) & set(tokens)),
            "test.smell.sensitive_equality": _sensitive_equality(body, settings["sensitive_equality_methods"]),
            "test.smell.sleep": sum(1 for token in tokens if token in settings["test_sleep_names"]),
        }
    )
    if production_names is not None:
        values["test.smell.eager_test"] = int(len(production_calls(function, production_names)) > settings["eager_test_calls_above"])
    return values


def runner_key(function: Function) -> tuple[str, str]:
    """(test binary, test path) of a test case, as Cargo and libtest name it.

    A test in `tests/api.rs` is `api` in the binary `api`, and a test in `src/bin/tool.rs` is in the binary
    `tool`. Every other test is in the binary named after the crate, with `-` as `_`, under its module path.
    A test in a shared module of the `tests` folder, such as `tests/common/mod.rs`, runs in each binary that
    includes it and is not matched.
    """
    path = function.module_path
    folders = function.file.crate_path.split("/")
    if (folders[0] == "tests" or folders[:2] == ["src", "bin"]) and len(path) >= 2:
        return path[1].replace("-", "_"), "::".join((*path[2:], function.name))
    return function.file.crate_name.replace("-", "_"), "::".join((*path, function.name))


def _runs_of(key: tuple[str, str], names) -> list[tuple[str, str]]:
    """The runner's tests that belong to a test function: the one with its name, and those one level below it.

    A parametrized test, such as one with `rstest` cases, runs as several tests named `<function>::<case>`.
    """
    binary, path = key
    return [name for name in names if name[0] == binary and (name[1] == path or name[1].startswith(path + "::"))]


def measure_test_runs(function: Function, tools: ToolResults) -> dict[str, float]:
    """The values of one test case from the test runs behind `--full`. A test the runner did not report has none.

    - test.flaky: 1 when the test failed and then passed on a retry under cargo-nextest, with
      `flaky_test_retries` retries. A test that failed every attempt is 0: it is broken, not flaky.
    - test.duration: seconds of the test's last attempt in that run.
    - test.order_dependent: 1 when the test failed in at least one of the single-threaded runs (the default
      order and one shuffled order per seed in `test_order_seeds`) and passed in another.

    For a parametrized test the cases are taken together (`_runs_of`): it is flaky or order-dependent when one
    case is, and its duration is the sum over its cases. All three depend on the run and can differ between two
    runs on the same code.
    """
    key = runner_key(function)
    values: dict[str, float] = {}
    attempts = tools.test_attempts
    runs = _runs_of(key, attempts) if attempts is not None else []
    if runs:
        values["test.flaky"] = int(any(attempts[run].flaky for run in runs))
        values["test.duration"] = sum(attempts[run].seconds for run in runs)
    dependent = tools.order_dependent()
    if dependent is not None and tools.order_failures:
        values["test.order_dependent"] = int(bool(_runs_of(key, dependent)))
    return values


def test_run_totals(tools: ToolResults, settings: dict = DEFAULT_SETTINGS) -> dict[str, float]:
    """Codebase counts over every test the runners reported, matched to a test function or not.

    codebase.flaky_tests: tests that failed and then passed on a retry. codebase.slow_tests: tests whose last
    attempt took more than `slow_test_seconds`; cargo-nextest marks a test as slow after 60 seconds by default
    (nexte.st/docs/features/slow-tests, read 2026-11-10). codebase.order_dependent_tests: tests whose result
    differs between the ordered runs.
    """
    values: dict[str, float] = {}
    if tools.test_attempts is not None:
        attempts = tools.test_attempts.values()
        values["codebase.flaky_tests"] = sum(1 for attempt in attempts if attempt.flaky)
        values["codebase.slow_tests"] = sum(1 for attempt in attempts if attempt.seconds > settings["slow_test_seconds"])
    dependent = tools.order_dependent()
    if dependent is not None:
        values["codebase.order_dependent_tests"] = len(dependent)
    return values


test_run_totals.__test__ = False


def lazy_tests(test_cases: list[Function], production_names: frozenset[str]) -> set[int]:
    """Start lines of the test cases of one file that call a production function another test case of the file calls.

    tsDetect's Lazy Test: "Multiple test methods calling the same production method", read within one test class;
    the file stands for the class here. Calls are matched by name (`production_calls`), so two tests that call
    different functions of the same name both count.
    """
    callers: dict[str, list[int]] = {}
    for test in test_cases:
        for name in production_calls(test, production_names):
            callers.setdefault(name, []).append(test.start_line)
    return {line for lines in callers.values() if len(lines) > 1 for line in lines}
