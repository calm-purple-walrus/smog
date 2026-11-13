"""Every named setting, set through `policy.setting`, changes a result of a run in the expected direction."""

import json

import pytest

from smog import SETTINGS, Policy, analyze
from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.cargo_tools import use_settings, works_offline
import tempfile
from pathlib import Path
from smog.infrastructure.run import _write_report
from smog.adapter.console import changed_functions, render
from smog.adapter.git_repository import GitRepository
from smog.adapter.github_reviews import review_data
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.application.analyze import Analyzer
from smog.domain.registry import PieceKind
from smog.domain.slop_rules import LISTS, RULES, list_setting, rule_setting
from smog.domain.tools import LintWarning, MutantOutcome, TestAttempt
from smog.ports import Tooling, ToolUnavailable
from tests.helpers import MANIFEST, commit, git, make_repository, scored_policy, write_tree
from tests.test_slop import POSITIVE

LONG = "pub fn long() {\n" + "".join(f"    let x{index} = {index};\n" for index in range(60)) + "}\n"
BUMPY = "fn f() {\n    if a { if b { c(); } }\n    h();\n    if i { j(); }\n}\n"
ENVY = "fn f(a: A) -> u32 {\n    a.one + a.two + a.three + a.four\n}\n"
PARAGRAPHS = "fn f() {\n    a();\n    b();\n    c();\n\n    d();\n    e();\n    g();\n}\n"
# Two runs of one statement each, of four and three lines.
LONG_STATEMENTS = "fn f() {\n    let s = call(\n        1,\n        2,\n    );\n\n    let t = call(\n        1,\n    );\n}\n"
HELPERS = "fn f() -> u32 {\n    let a = one();\n    a\n}\n\nfn one() -> u32 {\n    let x = 1;\n    let y = 2;\n    x + y\n}\n"
GOD = "struct S { a: u32, b: bool }\nimpl S {\n    fn m(&self, o: O) -> u32 { if self.a > 1 { o.x + o.y } else { 0 } }\n}\n"
LITERALS = "struct P { a: Option<u32>, b: Option<u32> }\nfn one() { P { a: Some(1), b: Some(2) }; }\nfn two() { P { a: None, b: None }; }\n"
DATA = "pub struct D { pub a: u8, pub b: u8 }\nimpl D {\n    pub fn c(&self) -> u8 {\n        self.a\n    }\n    pub fn work(&self) -> u8 {\n        if self.a > 1 { self.b + 1 } else { 0 }\n    }\n}\n"
CLUMPS = "struct A { x: u32, y: u32 }\nstruct B { x: u32, y: u32 }\n"
TEST = 'pub fn c() -> u32 {\n    1\n}\n#[test]\nfn t() {\n    a();\n    b();\n    assert_eq!(c(), "0123456789");\n}\n'
COMMENTS = "// increment the counter now\nincrement_counter(counter);\n/// Compute total value quickly.\npub fn compute_total_value() {}\n"
BODY = "pub fn a() -> u32 {\n    let x = 1;\n    let y = 2;\n    x + y\n}\n"
NAMING = "fn load() {\n    let ctx_total = 1;\n    let load_total_load_total_load = 2;\n}\n"
SIZES = (
    'pub fn c() -> u32 {\n    1\n}\n#[test]\nfn reads() {\n    let page = "http://example.test/a";\n    assert_eq!(c(), 1);\n    assert_ne!(c(), 2);\n}\n'
    "#[test]\nfn again() {\n    assert_eq!(c(), 1);\n    assert_ne!(c(), 2);\n}\n"
)
def _copy(name: str, changed: int) -> str:
    """A function of 12 body lines, of which the first `changed` call another function than in the original."""
    lines = [f"    {'other' if index < changed else 'step'}(x{index});\n" if index < changed else f"    let y{index} = x + {index};\n" for index in range(12)]
    return f"pub fn {name}(x: u32) {{\n{''.join(lines)}}}\n"


CLONES = _copy("first", 0) + _copy("second", 3)
MOVED = "    let moved_line_with_enough_characters = 1;\n"


def _single(source: str, **more: str) -> list[dict]:
    return [{"Cargo.toml": MANIFEST, "src/lib.rs": source, **more}]


def _doc(text: str) -> list[dict]:
    return _single("pub fn f() {}\n", **{"docs/a.md": text})


def _alice(policy: Policy) -> None:
    policy.humans("alice")


def _three_warnings(policy: Policy) -> None:
    policy.warning(lambda run: ["one", "two", "three"], name="three")


def _select_churn(policy: Policy) -> None:
    policy.select("function.code_churn", target=0, limit=1, group="history")


# name -> commits on main, files changed in the working tree afterwards, and a policy hook.
# A commit is its files, or its files and its message.
def _tests(*conditions: str) -> str:
    """One test per condition, named t0, t1 and so on. `eq a, 1` stands for `assert_eq!(a, 1)`, `close a, 1` for `assert_close!(a, 1)`."""
    lines = []
    for index, condition in enumerate(conditions):
        macro, _, rest = condition.partition(" ")
        call = f"assert_{macro}!({rest})" if macro in ("eq", "close") else f"assert!({condition})"
        lines.append(f"#[test]\nfn t{index}() {{\n    {call};\n}}\n")
    return "".join(lines)


def _against_main(policy: Policy) -> None:
    policy.against("main")


FIXTURES = {
    "long": (_single(LONG + "pub fn ok() {}\n"), None, None),
    "warnings": (_single("pub fn ok() {}\n"), None, _three_warnings),
    "panics": (_single("pub fn f(a: Option<u32>) -> u32 {\n    assert!(a.is_some());\n    println!(\"x\");\n    if a == Some(0) {\n        todo!()\n    }\n    a.unwrap()\n}\n"), None, None),
    "status": (_single("pub fn f(a: u32) -> bool {\n    a > 1\n}\n"), None, None),
    "two_files": (_single("mod big;\npub fn ok() {}\n", **{"src/big.rs": LONG}), None, None),
    "long_twice": ([*_single(LONG), {"src/lib.rs": LONG.replace("let x0 = 0", "let x0 = 9")}], None, _select_churn),
    "grow": ([*_single("pub fn s() {}\n"), {"src/lib.rs": "pub fn s() {\n    a();\n}\n"}, {"src/lib.rs": "pub fn s() {\n    a();\n}\n" + LONG}], None, None),
    "test_names": (_single("pub mod test_support;\n#[inline]\npub fn f() {}\n", **{"src/test_support.rs": BODY}), None, None),
    "renamed": (_single(_copy("first", 0)), {"src/lib.rs": _copy("second", 3)}, lambda policy: policy.against("main")),
    # `src/a.rs` moves to `src/b.rs` with one of its four code lines changed. None deletes a file of the working tree.
    "moved_file": (
        _single("pub mod a;\n", **{"src/a.rs": "pub fn f() -> u32 {\n    let a = 1;\n    a + 1\n}\n"}),
        {"src/lib.rs": "pub mod b;\n", "src/a.rs": None, "src/b.rs": "pub fn f() -> u32 {\n    let a = 2;\n    a + 1\n}\n"},
        _against_main,
    ),
    "debt": (_single("// TODO: split this.\npub fn f() {}\n"), None, None),
    "snapshot": (_single("#[test]\nfn t() {\n    snapshot!(render());\n}\n"), None, None),
    "wrapped": (_single("pub fn f(a: Box<u32>, b: Sized) {}\n"), None, None),
    "invariant": (_single("pub struct S {\n    /// A positive number.\n    pub a: u32,\n}\n"), None, None),
    "helper_only": (_single("#[test]\nfn t() {\n    ensure_ok();\n}\n"), None, None),
    "helper": (_single("#[test]\nfn t() {\n    ensure_ok();\n    m.stub();\n    pause();\n    assert_eq!(render(a).to_owned(), b);\n}\n"), None, None),
    "weaker": (_single(_tests("a > 1", "eq a, 1", "close a, 1", "holds(a)", "a.len() > 1")), {"src/lib.rs": _tests("a.is_ok()", "a > 1", "a > 1", "a > 1", "a.is_ready()")}, _against_main),
    "complex": (_single("pub struct S {\n    a: &'static u32,\n    b: Box<dyn Send>,\n    c: fn(u32),\n}\n"), None, None),
    "decorative": (_single("// ----------\npub fn f() {}\n"), None, None),
    "suppressed": (_single("#[allow(dead_code)]\nfn f() {}\n"), None, None),
    "suppress": (_single("pub fn a() {}\n"), {"src/lib.rs": "#[allow(dead_code)]\npub fn a() {}\n"}, _against_main),
    "lint_table": (_single(BODY), {"Cargo.toml": MANIFEST + '\n[lints.rust]\nwarnings = "allow"\n'}, _against_main),
    "example": (_single("/// Does.\n///\n/// ```no_run\n/// f();\n/// ```\npub fn f() {}\n"), None, None),
    "short": (_single("fn f(cfg: u32, id: u32, name: u32) {}\n"), None, None),
    "prefixes": (_single("fn fetch_it() {}\nfn was_it() {}\nfn put_it() -> u32 {\n    1\n}\n"), None, None),
    "reverted": ([*_single(BODY), ({"src/lib.rs": BODY.replace("1", "3")}, "Undo: the change before")], None, None),
    "bumpy": (_single(BUMPY), None, None),
    "envy": (_single(ENVY), None, None),
    "paragraphs": (_single(PARAGRAPHS), None, None),
    "long_statements": (_single(LONG_STATEMENTS), None, None),
    # `f` is unchanged against main, so only a minimum drop of 0 lists it.
    "unchanged": (_single("pub fn f() -> u32 {\n    1\n}\n"), {"src/lib.rs": "pub fn f() -> u32 {\n    1\n}\npub fn g() {}\n"}, lambda policy: policy.against("main")),
    "helpers": (_single(HELPERS), None, None),
    "names": (_single("fn f(x: u32, y: u32) {}\n"), None, None),
    "overlap": (_single("/// Computes totals.\npub fn compute_total() {}\n"), None, None),
    "bounds": (_single("pub struct Wrapper<T: Send> {\n    inner: T,\n}\n"), None, None),
    "naming": (_single(NAMING), None, None),
    "mutation": (_single("pub fn f() -> u32 {\n    1\n}\n"), None, None),
    "god": (_single(GOD), None, None),
    "literals": (_single(LITERALS), None, None),
    "clumps": (_single(CLUMPS), None, None),
    "copies": (_single(BODY + BODY.replace("fn a", "fn z")), None, None),
    "data": (_single(DATA), None, None),
    "test": (_single(TEST), None, None),
    "runs": (_single(TEST), None, None),
    "lints": (_single(BODY), None, None),
    "offline": (_single(BODY), None, None),
    "comments": (_single(COMMENTS), None, None),
    "comment_history": (_single("// This no longer calls the lexer.\npub fn f() {}\n"), None, None),
    "comment_hedge": (_single("// The cast should work here.\npub fn f() {}\n"), None, None),
    "ticket": (_single("// Reads the rows of ENG-123.\npub fn f() {}\n"), None, None),
    "naturalness": (_single(BODY, **{"src/copy.rs": BODY}), None, None),
    "clones": (_single(CLONES), None, None),
    "branches": ([*_single(BODY), {"src/lib.rs": BODY.replace("1", "3")}], {"src/new.rs": "pub fn n() {}\n"}, None),
    "follow_up": (
        [*_single(BODY), ({"src/lib.rs": BODY + "pub fn extra() {}\n"}, "feat: add extra"), ({"src/other.rs": "pub fn o() {}\n"}, "feat: other"), ({"src/lib.rs": BODY}, "fix: remove extra")],
        None,
        None,
    ),
    "messages": ([*_single(BODY), ({"src/lib.rs": BODY.replace("1", "3")}, "feat: a subject of forty characters in all\n\nA body line of forty characters, exactly.")], None, None),
    "sizes": (_single(SIZES, **{"tests/api.rs": "#[test]\nfn api() {\n    run();\n}\n"}), None, None),
    "graph": (_single("pub mod a;\npub mod b;\n", **{"src/a.rs": "use crate::b::f;\npub fn g() {\n    f();\n}\n", "src/b.rs": "pub fn f() {}\n", "src/c.rs": "// @generated\npub fn g() {}\n"}), None, None),
    "nested_cycle": (_single("pub mod p;\n", **{"src/p.rs": "pub mod c;\npub use c::X;\npub struct Y;\n", "src/p/c.rs": "use super::Y;\npub struct X;\n"}), None, None),
    "history": (
        [
            *_single("pub mod b;\npub mod c;\n", **{"src/b.rs": BODY, "src/c.rs": BODY.replace("fn a", "fn z")}),
            {"src/lib.rs": "pub mod b;\npub mod c;\npub fn added() -> u32 {\n    7\n}\n"},
            {"src/b.rs": BODY.replace("1", "3"), "src/c.rs": BODY.replace("fn a", "fn z").replace("1", "3")},
            {"src/lib.rs": "pub mod b;\npub mod c;\n"},
            {"src/b.rs": BODY.replace("1", "4"), "src/c.rs": BODY.replace("fn a", "fn z").replace("1", "4")},
        ],
        None,
        None,
    ),
    "unstable": (
        [
            *_single("pub mod a;\npub mod b;\n", **{"src/a.rs": "pub fn f(x: u32) -> u32 {\n    x\n}\n", "src/b.rs": "use crate::a::f;\npub fn g() -> u32 {\n    f(1)\n}\n"}),
            {"src/a.rs": "pub fn f(x: u32, y: u32) -> u32 {\n    x + y\n}\n", "src/b.rs": "use crate::a::f;\npub fn g() -> u32 {\n    f(1, 2)\n}\n"},
        ],
        None,
        None,
    ),
    # The third line is a comment that can serve as the review marker of the first commit.
    "reviews": ([*_single(BODY), {"src/lib.rs": "// one\n// two\n// checked by hand {sha}\n" + BODY}], None, _alice),
    # Every file carries the default marker, so an empty reviews file is enough to give a value.
    "reviews_file": ([*_single(BODY, **{"reviews.json": "{}"}), {"src/lib.rs": "// smog: human-reviewed {sha}\n" + BODY}], None, _alice),
    "open_reviews": (_single(BODY), None, _alice),
    "diff": (
        _single("pub fn a() {\n" + MOVED + "}\n"),
        {"src/lib.rs": "pub fn a() {\n}\n", "src/other.rs": "pub fn b() {\n" + MOVED + "}\n"},
        lambda policy: policy.against("main"),
    ),
}


def _whole_tree_mutants(root, base_sha):
    """Stands in for cargo-mutants: outcomes on line 2 when asked for the whole tree, none for a diff."""
    if base_sha is not None:
        return []
    return [MutantOutcome("src/lib.rs", 2, "missed", "FnValue"), MutantOutcome("src/lib.rs", 2, "timeout", "FnValue")]


def _attempts(root, retries):
    """Stands in for cargo-nextest: the test `t` takes 90 seconds and turns out flaky on a third retry."""
    return {("sample", "t"): TestAttempt(90.0, retries >= 3, False)}


def _order_failures(root, seeds):
    """Stands in for the shuffled runs: the test `t` fails only in the order of seed 9."""
    return [set(), *({("sample", "t")} if seed == 9 else set() for seed in seeds)]


def _warnings(root):
    """Stands in for the Clippy run: one unused import and one Clippy warning."""
    return [LintWarning("unused_imports", "src/lib.rs", 1, "unused import"), LintWarning("clippy::needless_return", "src/lib.rs", 2, "unneeded return")]


def _warnings_when_online(root):
    """Stands in for a Clippy run that needs a download: it works only when cargo may use the network."""
    if works_offline():
        raise ToolUnavailable("cargo could not work offline")
    return _warnings(root)


REQUESTS: list[str] = []


def _github(root, commits, fetch, settings):
    """Stands in for GitHub behind the real adapter and counts the requests in REQUESTS. Every commit is the
    squash commit of pull request 1, which `alice` approved and then asked to change."""
    git(root, "config", "remote.origin.url", "https://github.com/owner/name.git")
    reviews = [{"user": {"login": "alice"}, "state": state, "submitted_at": f"2026-01-0{day}T00:00:00Z"} for day, state in ((1, "APPROVED"), (2, "CHANGES_REQUESTED"))]
    REQUESTS.clear()

    def get(url: str):
        if "?" not in url:
            return 200, {}, b"{}"  # who merged a pull request or authored a commit: nobody listed
        REQUESTS.append(url)
        path, _, query = url.partition("?")
        size, page = (int(pair.split("=")[1]) for pair in query.split("&"))
        rows = reviews if path.endswith("/reviews") else [{"number": 1, "merged_at": "2026-01-01T00:00:00Z", "merge_commit_sha": path.split("/")[-2]}]
        link = {"link": '<next>; rel="next"'} if page * size < len(rows) else {}
        return 200, link, json.dumps(rows[(page - 1) * size : page * size]).encode()

    return review_data(root, commits, fetch, settings, get)


def _github_with_open_pull_requests(root, commits, fetch, settings):
    """Stands in for GitHub while every commit belongs to an open pull request only, and counts the requests in REQUESTS."""
    git(root, "config", "remote.origin.url", "https://github.com/owner/name.git")
    REQUESTS.clear()

    def get(url: str):
        if "?" not in url:
            return 200, {}, b"{}"  # who merged a pull request or authored a commit: nobody listed
        REQUESTS.append(url)
        return 200, {}, json.dumps([{"number": 1, "merged_at": None, "merge_commit_sha": None}]).encode()

    return review_data(root, commits, fetch, settings, get)


# name -> the slow tools a fixture runs with, in place of the real ones, and the tools selected.
TOOLING = {
    "mutation": (Tooling(mutants=_whole_tree_mutants), ("mutants",)),
    "runs": (Tooling(test_attempts=_attempts, order_failures=_order_failures), ("nextest", "shuffle")),
    "lints": (Tooling(clippy_pedantic=_warnings), ("clippy",)),
    "offline": (Tooling(clippy_pedantic=_warnings_when_online, prepare=use_settings), ("clippy",)),
    "reviews": (Tooling(review_data=_github), ("reviews",)),
    "open_reviews": (Tooling(review_data=_github_with_open_pull_requests), ("reviews",)),
}


def _analyze(policy: Policy, root, fixture: str):
    if fixture not in TOOLING:
        return analyze(policy, str(root))
    tooling, tools = TOOLING[fixture]
    analyzer = Analyzer(GitRepository(str(root)), TreeSitterRustParser(), CargoManifests(), tooling)
    return analyzer.analyze(policy, full=True, tools=tools)


def _value(kind: PieceKind, piece_id: str, metric_id: str):
    return lambda report: report.card.find(kind, piece_id).value(metric_id)


def _function(metric_id: str, name: str = "f"):
    return _value(PieceKind.FUNCTION, f"sample::{name}", metric_id)


def _file(metric_id: str, path: str = "src/lib.rs"):
    return _value(PieceKind.FILE, path, metric_id)


def _codebase(metric_id: str):
    return lambda report: report.card.root.value(metric_id)


def _unreviewed(report) -> float:
    """The unreviewed lines of the codebase, or -1 when the run has no value for them."""
    return report.card.root.values.get("codebase.unreviewed_lines", -1)


def _slop(rule: str, severity: str):
    return lambda report: sum(1 for finding in report.slop if (finding.rule, finding.severity) == (rule, severity))


def _readability(rule: str):
    """The value a readability rule prints for the one document of the fixture, such as 3.2 for `ARI 3.2`."""
    return lambda report: next(float(finding.matched.split()[1]) for finding in report.slop if finding.rule == rule)


def _score(kind: PieceKind, piece_id: str):
    return lambda report: report.card.score(report.card.find(kind, piece_id))


UP, DOWN = 1, -1
WORDS = " ".join(["word"] * 20) + ".\n"
GOD_BASE = {"god_type_foreign_fields_above": 1, "god_type_min_complexity": 2, "god_type_cohesion_below": 2.0}
DATA_BASE = {"data_class_weight_below": 0.6}
WIND = {"slop_len_words_metric": 3}

# setting, value, fixture name or Markdown text, probe, direction, settings in force for both runs.
CASES = [
    ("others_share", 1.0, "long", _score(PieceKind.FUNCTION, "sample::long"), DOWN, {}),
    ("worst_items_in_file", 1, "long", _score(PieceKind.FILE, "src/lib.rs"), DOWN, {}),
    ("worst_items_combine", "min", "long", _score(PieceKind.FILE, "src/lib.rs"), DOWN, {}),
    ("score_decay", 2.0, "long", _score(PieceKind.FUNCTION, "sample::long"), DOWN, {}),
    # The long function is most of the lines, so it weighs less when every piece weighs the same or the small file weighs 100 lines.
    ("aggregate_weight", "equal", "two_files", lambda report: report.card.score(), UP, {}),
    ("aggregate_min_lines", 100, "two_files", lambda report: report.card.score(), UP, {}),
    ("paragraph_free_lines", 5, "long", _function("function.paragraph_penalty", "long"), UP, {}),
    ("paragraph_tolerated_lines", 20, "long", _function("function.paragraph_penalty", "long"), DOWN, {}),
    ("paragraph_tolerated_cost", 0.5, "long", _function("function.paragraph_penalty", "long"), UP, {}),
    ("paragraph_cost", 1.0, "long", _function("function.paragraph_penalty", "long"), UP, {}),
    ("paragraph_knee_lines", 40, "long", _function("function.paragraph_penalty", "long"), UP, {}),
    # The path of the written text report grows with a longer folder name.
    ("report_folder", "target/smog-elsewhere", "body", lambda report: len(_write_report(report, Path(tempfile.mkdtemp()) / report.card.model.settings["report_folder"], "text", "crate")[0]), UP, {}),
    ("changes_min_drop", 0.0, "unchanged", lambda report: sum(line.startswith("  ") for line in changed_functions(report)), UP, {}),
    ("short_names_min_names", 2, "names", _function("function.short_names"), UP, {}),
    ("naming_max_words", 5, "naming", _function("function.naming_flaws", "load"), DOWN, {}),
    ("bumpy_road_min_depth", 1, "bumpy", _function("function.bumpy_road"), UP, {}),
    ("feature_envy_foreign_fields_above", 4, "envy", _function("function.feature_envy"), DOWN, {}),
    ("feature_envy_own_share_below", 0.0, "envy", _function("function.feature_envy"), DOWN, {}),
    ("feature_envy_max_receivers", 0, "envy", _function("function.feature_envy"), DOWN, {}),
    ("primitive_share_min_fields", 2, "god", _value(PieceKind.TYPE, "sample::S", "type.primitive_share"), UP, {}),
    ("correlated_options_min_literals", 2, "literals", _value(PieceKind.TYPE, "sample::P", "type.correlated_options"), UP, {}),
    ("god_type_foreign_fields_above", 5, "god", _value(PieceKind.TYPE, "sample::S", "type.god_type"), DOWN, GOD_BASE),
    ("god_type_min_complexity", 47, "god", _value(PieceKind.TYPE, "sample::S", "type.god_type"), DOWN, GOD_BASE),
    ("god_type_cohesion_below", 0.3, "god", _value(PieceKind.TYPE, "sample::S", "type.god_type"), DOWN, GOD_BASE),
    ("data_class_weight_below", 0.6, "data", _value(PieceKind.TYPE, "sample::D", "type.data_class"), UP, {"data_class_accessors_above": 2}),
    ("data_class_accessors_above", 2, "data", _value(PieceKind.TYPE, "sample::D", "type.data_class"), UP, DATA_BASE),
    ("data_class_complexity_below", 3, "data", _value(PieceKind.TYPE, "sample::D", "type.data_class"), DOWN, {**DATA_BASE, "data_class_accessors_above": 2, "data_class_many_accessors_above": 9}),
    ("data_class_many_accessors_above", 2, "data", _value(PieceKind.TYPE, "sample::D", "type.data_class"), UP, {**DATA_BASE, "data_class_accessors_above": 9}),
    ("data_class_high_complexity_below", 3, "data", _value(PieceKind.TYPE, "sample::D", "type.data_class"), DOWN, {**DATA_BASE, "data_class_accessors_above": 9, "data_class_many_accessors_above": 2}),
    ("lazy_class_max_methods", 2, "data", _value(PieceKind.TYPE, "sample::D", "type.lazy_class"), UP, {}),
    ("lazy_class_max_lines", 5, "data", _value(PieceKind.TYPE, "sample::D", "type.lazy_class"), DOWN, {"lazy_class_max_methods": 2}),
    ("data_clumps_min_size", 2, "clumps", _codebase("codebase.data_clumps"), UP, {}),
    ("duplication_min_tokens", 10, "copies", _file("file.duplicated_line_share"), UP, {}),
    ("inconsistent_clone_min_lines", 13, "clones", _codebase("codebase.inconsistent_clone_groups"), DOWN, {"inconsistent_clone_max_edit_ratio": 0.5}),
    ("inconsistent_clone_max_edits", 2, "clones", _codebase("codebase.inconsistent_clone_groups"), DOWN, {"inconsistent_clone_max_edit_ratio": 0.5}),
    ("inconsistent_clone_max_edit_ratio", 0.5, "clones", _codebase("codebase.inconsistent_clone_groups"), UP, {}),
    # A model of longer sequences finds more of the copy in the other file; a full discount leaves only the uniform share.
    ("naturalness_order", 1, "naturalness", _file("file.cross_entropy"), UP, {}),
    ("naturalness_discount", 1.0, "naturalness", _file("file.cross_entropy"), UP, {}),
    ("adjacent_same_type_min_run", 3, "names", _function("function.adjacent_same_type"), DOWN, {}),
    ("comment_name_max_edit_distance", 0, "overlap", _function("function.comment_name_overlap", "compute_total"), DOWN, {}),
    ("maintainability_index_coefficients", (100, 5.2, 0.23, 16.2), "names", _function("function.maintainability_index"), DOWN, {}),
    ("type_bound_traits", ("Send",), "bounds", lambda report: len(report.checks["check.no_type_bounds"].failures), UP, {}),
    ("test_attributes", ("test", "inline"), "test_names", _file("file.test_lines"), UP, {}),
    ("test_file_patterns", ("src/test_*.rs",), "test_names", _file("file.production_lines", "src/test_support.rs"), DOWN, {}),
    ("function_match_min_similarity", 1.0, "renamed", lambda report: len(report.comparison.function_matches()), DOWN, {}),
    ("file_match_min_similarity", 1.0, "moved_file", lambda report: sum(1 for _, before, _ in report.comparison.file_scores() if before is not None), DOWN, {}),
    ("panic_macros", ("panic",), "panics", _function("function.panic_points"), DOWN, {}),
    ("panic_methods", ("expect",), "panics", _function("function.panic_points"), DOWN, {}),
    ("failure_doc_panic_macros", (), "panics", _function("function.missing_failure_docs"), DOWN, {"panic_methods": ()}),
    ("debug_macros", ("dbg",), "panics", _function("function.debug_leftovers"), DOWN, {}),
    ("adjacent_same_type_exempt_names", ("f",), "names", _function("function.adjacent_same_type"), DOWN, {}),
    ("validation_name_prefixes", ("f",), "status", _function("function.validation_only"), UP, {}),
    ("restating_stop_words", ("increment", "counter"), "comments", _file("file.restating_comments"), DOWN, {}),
    ("test_exact_output_macros", ("assert_eq",), "sizes", _value(PieceKind.TEST, "sample::again", "test.exact_output"), UP, {}),
    ("test_mystery_guest_names", ("c",), "sizes", _value(PieceKind.TEST, "sample::again", "test.smell.mystery_guest"), UP, {}),
    ("test_print_macros", ("assert_eq",), "sizes", _value(PieceKind.TEST, "sample::again", "test.smell.print"), UP, {}),
    ("test_resource_file_names", ("c",), "sizes", _value(PieceKind.TEST, "sample::again", "test.smell.resource_optimism"), UP, {}),
    ("test_resource_existence_checks", ("assert_ne",), "sizes", _value(PieceKind.TEST, "sample::again", "test.smell.resource_optimism"), DOWN, {"test_resource_file_names": ("c",)}),
    ("assertion_roulette_unexplained_above", 2, "sizes", _value(PieceKind.TEST, "sample::again", "test.smell.assertion_roulette"), DOWN, {}),
    ("files_changed_together_min_commits", 3, "history", _codebase("codebase.files_changed_together"), DOWN, {}),
    ("slop_counted_severities", ("metric",), "Run it now. Run it then.\n", _codebase("codebase.doc_slop_findings"), DOWN, {"slop_rhythm_starters": 2}),
    ("slop_ari_coefficients", (4.71, 0.5, 0.0), WORDS, _readability("read-ari"), UP, {"slop_min_file_words": 1}),
    ("slop_flesch_coefficients", (100.0, 1.015, 84.6), WORDS, _readability("read-flesch"), DOWN, {"slop_min_file_words": 1}),
    ("eager_test_calls_above", 0, "test", _value(PieceKind.TEST, "sample::t", "test.smell.eager_test"), UP, {}),
    ("assertion_block_min_statements", 2, "sizes", _value(PieceKind.TEST, "sample::reads", "test.duplicated_assertion_block"), UP, {}),
    ("test_size_medium_names", ("c",), "sizes", _value(PieceKind.TEST, "sample::again", "test.size_class"), UP, {}),
    ("test_size_local_hosts", ("example.test",), "sizes", _value(PieceKind.TEST, "sample::reads", "test.size_class"), DOWN, {}),
    ("test_integration_paths", (), "sizes", _codebase("codebase.integration_test_share"), DOWN, {}),
    ("test_end_to_end_paths", ("tests/*",), "sizes", _codebase("codebase.end_to_end_test_share"), UP, {}),
    ("test_end_to_end_names", ("run",), "sizes", _codebase("codebase.end_to_end_test_share"), UP, {}),
    ("exact_output_min_characters", 10, "test", _value(PieceKind.TEST, "sample::t", "test.exact_output"), UP, {}),
    ("restating_min_words", 4, "comments", _file("file.restating_comments"), DOWN, {}),
    ("restating_overlap", 0.9, "comments", _file("file.restating_comments"), DOWN, {}),
    ("long_first_sentence_words", 3, "comments", _file("file.long_first_sentence"), UP, {}),
    ("wet_docs_overlap", 0.75, "comments", _file("file.wet_docs"), UP, {}),
    ("short_term_window", 1, "follow_up", _codebase("codebase.follow_up_fixes"), DOWN, {}),
    # The commits of the fixture are seconds apart, so only a negative number of days leaves a later commit out.
    ("short_term_churn_days", -1, "history", _codebase("codebase.short_term_churn"), DOWN, {}),
    ("active_branch_days", -1, "branches", _codebase("codebase.active_branches"), DOWN, {}),
    ("fix_commit_pattern", "^feat: a subject", "messages", _file("file.szz_fixes"), UP, {}),
    ("subject_max_length", 30, "messages", _codebase("codebase.long_subjects"), UP, {}),
    ("body_line_max_length", 30, "messages", _codebase("codebase.long_body_lines"), UP, {}),
    ("early_removal_commits", 1, "history", _codebase("codebase.items_removed_early"), DOWN, {}),
    ("large_commit_files", 1, "history", _codebase("codebase.files_changed_together"), DOWN, {}),
    ("change_coupling_min_revisions", 2, "history", _file("file.change_coupling", "src/b.rs"), UP, {"change_coupling_min_shared": 2}),
    ("change_coupling_min_shared", 2, "history", _file("file.change_coupling", "src/b.rs"), UP, {"change_coupling_min_revisions": 2}),
    ("modularity_min_shared", 2, "history", _codebase("codebase.modularity_violations"), UP, {}),
    ("modularity_share", 1.5, "history", _codebase("codebase.modularity_violations"), DOWN, {"modularity_min_shared": 2}),
    ("unstable_min_changes", 1, "unstable", _file("file.unstable_interface", "src/a.rs"), UP, {}),
    ("clone_min_lines", 6, "history", _codebase("codebase.co_changing_clones"), DOWN, {}),
    ("moved_line_min_characters", 100, "diff", lambda report: report.diff_values["diff.moved_line_share"], DOWN, {}),
    ("lenses_over_target_min_groups", 1, "long", _codebase("codebase.lenses_over_target"), UP, {}),
    ("flaw_counts_crossing_above", -1, "graph", _codebase("codebase.flaw_counts"), UP, {}),
    ("flaw_counts_unstable_min", 1, "unstable", _codebase("codebase.flaw_counts"), UP, {"unstable_min_changes": 1}),
    ("hotspot_excluded_groups", (), "long_twice", _function("function.hotspot", "long"), UP, {}),
    ("indentation_width", 2, "bumpy", _function("function.indentation_sum"), UP, {}),
    ("catch_all_names", ("a",), "graph", _value(PieceKind.MODULE, "sample::a", "module.catch_all_name"), UP, {}),
    ("module_cycles_skip_nested", False, "nested_cycle", _value(PieceKind.MODULE, "sample::p", "module.cycle_size"), UP, {}),
    # Less damping gives every file a larger equal share, which outweighs what src/b.rs loses from its one user.
    ("page_rank_damping", 0.5, "graph", _file("file.central_position", "src/b.rs"), UP, {}),
    ("page_rank_rounds", 1, "graph", _file("file.central_position", "src/b.rs"), UP, {}),
    ("equilibrium_zero_debt_per_1000_lines", 1, "grow", _codebase("codebase.equilibrium"), DOWN, {}),
    ("generated_header_bytes", 5, "graph", lambda report: len(report.card.pieces(PieceKind.FILE)), UP, {}),
    ("mutants_scope", "tree", "mutation", _function("function.missed_mutants"), UP, {}),
    ("mutation_timeouts_caught", True, "mutation", _function("function.mutation_score"), UP, {"mutants_scope": "tree"}),
    ("unused_code_lints", ("unused_imports", "clippy::needless_return"), "lints", _codebase("codebase.unused_code"), UP, {}),
    ("flaky_test_retries", 3, "runs", _value(PieceKind.TEST, "sample::t", "test.flaky"), UP, {}),
    ("slow_test_seconds", 100, "runs", _codebase("codebase.slow_tests"), DOWN, {}),
    ("test_order_seeds", (9,), "runs", _value(PieceKind.TEST, "sample::t", "test.order_dependent"), UP, {}),
    ("effective_length_alpha", 1.0, "helpers", _function("function.effective_length"), UP, {}),
    ("history_window", 1, "history", lambda report: report.history.commit_count, DOWN, {}),
    ("pr_size_lines", 1, "diff", lambda report: len(report.checks["check.pr_size"].failures), UP, {}),
    ("pr_size_files", 1, "diff", lambda report: len(report.checks["check.pr_size"].failures), UP, {}),
    ("slop_min_file_words", 5, "We ship the parser today and tomorrow.\n", _slop("read-ari", "metric"), UP, {}),
    ("slop_len_words_metric", 10, WORDS, _slop("len-words", "metric"), UP, {}),
    ("slop_len_words_warn", 10, WORDS, _slop("len-words", "warn"), UP, {}),
    ("slop_len_chars", 10, "A short sentence here.\n", _slop("len-chars", "metric"), UP, {}),
    ("slop_clause_commas", 2, "One, two, three.\n", _slop("clause-commas", "warn"), UP, {}),
    ("slop_clause_coordinators", 1, "It reads and stores the file.\n", _slop("clause-coord", "warn"), UP, {}),
    ("slop_clause_markers", 1, "It stops if the file is gone.\n", _slop("clause-markers", "metric"), UP, {}),
    ("slop_clause_tails", 1, "It reads the file, which holds rows.\n", _slop("clause-tails", "warn"), UP, {}),
    ("slop_clause_semicolons", 1, "One; two.\n", _slop("clause-semicolons", "warn"), UP, {}),
    ("slop_nest_depth", 1, "A (b) c.\n", _slop("nest-depth", "warn"), UP, {}),
    ("slop_nest_asides", 1, "A (one two three) c.\n", _slop("nest-asides", "warn"), UP, {}),
    ("slop_aside_min_words", 0, "A (b) c.\n", _slop("nest-asides", "warn"), UP, {"slop_nest_asides": 1}),
    ("slop_late_subject_words", 1, "Although it is slow, it works.\n", _slop("nest-late-subject", "warn"), UP, {}),
    ("slop_wind_commas", 1, "One, two (three) four five.\n", _slop("wind-composite", "warn"), UP, WIND),
    ("slop_wind_coordinators", 1, "One and two (three) four five.\n", _slop("wind-composite", "warn"), UP, WIND),
    ("slop_wind_markers", 1, "One if two (three) four five.\n", _slop("wind-composite", "warn"), UP, WIND),
    ("slop_wind_depth", 5, "One, two, three, (four) five six.\n", _slop("wind-composite", "warn"), DOWN, WIND),
    ("slop_wind_tails", 1, "One two (three) four, which five.\n", _slop("wind-composite", "warn"), UP, WIND),
    ("slop_wind_signals", 1, "One, two (three) four five.\n", _slop("wind-composite", "warn"), UP, WIND),
    ("slop_paragraph_words", 10, WORDS, _slop("para-words", "warn"), UP, {}),
    ("slop_len_mean_min_sentences", 1, "We ship it today.\n", _slop("len-mean", "metric"), UP, {}),
    ("slop_rhythm_min_sentences", 2, "One two three four. Five six seven eight.\n", _slop("rhythm-cv", "metric"), UP, {}),
    ("slop_rhythm_cv", 0.1, "One two three four. One two three four five six seven eight.\n", _slop("rhythm-cv", "metric"), DOWN, {"slop_rhythm_min_sentences": 2}),
    ("slop_rhythm_min_words", 0, "One two three four. Five six seven eight. Go.\n", _slop("rhythm-cv", "metric"), DOWN, {"slop_rhythm_min_sentences": 2}),
    ("slop_rhythm_adjacent_sentences", 2, "One two three four. Five six seven eight.\n", _slop("rhythm-adjacent", "metric"), UP, {}),
    ("slop_rhythm_adjacent_spread", 1, "One two three four. One two three four five six.\n", _slop("rhythm-adjacent", "metric"), DOWN, {"slop_rhythm_adjacent_sentences": 2}),
    ("slop_rhythm_starters", 2, "Run it now. Run it then.\n", _slop("rhythm-starters", "warn"), UP, {}),
    ("slop_staccato_words", 1, "Go now. Stop now.\n", _slop("rhythm-staccato", "warn"), DOWN, {"slop_staccato_run": 2}),
    ("slop_staccato_run", 2, "Go now. Stop now.\n", _slop("rhythm-staccato", "warn"), UP, {}),
    ("slop_ngram_words", 3, "One two three. One two three.\n", _slop("rhythm-ngram", "metric"), UP, {"slop_ngram_repeats": 2}),
    ("slop_ngram_repeats", 2, "One two three four five six. One two three four five six.\n", _slop("rhythm-ngram", "metric"), UP, {}),
    ("slop_cluster_rules", 1, "One, two, three, four, five, six.\n", _slop("cluster-paragraph", "warn"), UP, {}),
    ("slop_pithy_words", 1, "Reads the file, not memory.\n", _slop("meta-pithy", "warn"), DOWN, {}),
    ("slop_neg_x_not_y_per_paragraph", 1, "Returns bytes, not characters.\n", _slop("neg-x-not-y", "warn"), UP, {}),
    ("slop_neg_x_not_y_per_1000_words", 100000, "Returns bytes, not characters.\n", _slop("neg-x-not-y", "warn"), DOWN, {"slop_min_file_words": 1}),
    ("slop_neg_rather_than_per_1000_words", 100000, "We parse rather than guess the kind.\n", _slop("neg-rather-than", "warn"), DOWN, {"slop_min_file_words": 1, "slop_density_min_count": 1}),
    ("slop_but_balanced_words", 1, "The parser reads files, but the lexer reads bytes.\n", _slop("but-balanced", "warn"), DOWN, {}),
    ("slop_but_balanced_difference", 10, "The slow old parser reads every file, but it works.\n", _slop("but-balanced", "warn"), UP, {}),
    ("slop_triad_count", 1, "It reads files, parses rows, and stores data.\n", _slop("triad-doc", "warn"), UP, {}),
    ("slop_triad_share", 5, "It reads files, parses rows, and stores data.\n", _slop("triad-doc", "warn"), DOWN, {"slop_triad_count": 1}),
    ("slop_count_announce_words", 1, "Two constraints shape the design.\n", _slop("count-announce", "warn"), DOWN, {}),
    ("slop_count_ordinal_matches", 1, "The first problem is memory.\n", _slop("count-ordinal", "warn"), UP, {}),
    ("slop_vocab_distinct", 1, "A crucial design has properties.\n", _slop("vocab-density", "warn"), UP, {}),
    ("slop_min_density_words", 1, "A crucial design has properties.\n", _slop("vocab-density", "warn"), UP, {}),
    ("slop_vocab_per_200_words", 100000, "A crucial design has properties.\n", _slop("vocab-density", "warn"), DOWN, {"slop_min_density_words": 1}),
    ("slop_emdash_count", 1, "One — two — three.\n", _slop("fmt-emdash", "metric"), UP, {}),
    ("slop_emdash_per_500_words", 100000, "One — two — three.\n", _slop("fmt-emdash", "metric"), DOWN, {"slop_emdash_count": 1}),
    ("slop_bold_bullets_run", 1, "- **Label:** some text\n", _slop("fmt-bold-bullets", "metric"), UP, {}),
    ("slop_title_case_min_words", 2, "# Big Title Here\n\nSome text.\n", _slop("fmt-title-case", "metric"), UP, {}),
    ("slop_title_case_long_word", 3, "# The Big Red Dog Runs fast\n\nSome text.\n", _slop("fmt-title-case", "metric"), UP, {}),
    ("slop_title_case_share", 0.4, "# The Big Red Dog Runs fast\n\nSome text.\n", _slop("fmt-title-case", "metric"), UP, {}),
    ("slop_hrule_count", 1, "Some text here.\n\n---\n\nMore text here.\n", _slop("fmt-hrule", "metric"), UP, {}),
    ("slop_ticket_standard_prefixes", ("ENG",), "ticket", _slop("comment-ticket", "warn"), DOWN, {}),
    ("human_review_marker", "checked by hand", "reviews", _unreviewed, DOWN, {}),
    ("human_review_marker_lines", 2, "reviews", _unreviewed, UP, {"human_review_marker": "checked by hand"}),
    ("review_approving_states", ("CHANGES_REQUESTED",), "reviews", _unreviewed, DOWN, {}),
    ("review_ignored_states", ("CHANGES_REQUESTED",), "reviews", _unreviewed, DOWN, {}),
    # The reviews file is read without --full; without one the run has no value.
    ("reviews_file", "reviews.json", "reviews_file", _unreviewed, UP, {}),
    # The origin remote is on github.com, so with another API host nothing is fetched and the run has no value.
    ("reviews_api_url", "https://code.example/api/v3", "reviews", _unreviewed, DOWN, {}),
    # Two reviews on pages of one row take one request more than on one page.
    ("reviews_page_size", 1, "reviews", lambda report: len(REQUESTS), UP, {}),
    # A list of two pages is not read to its end when one page is the limit, so the run has no value.
    ("reviews_max_pages", 1, "reviews", _unreviewed, DOWN, {"reviews_page_size": 1}),
    # The first run writes the file with every commit recorded without a merged pull request. The second asks again for none of them.
    ("reviews_refetch", "none", "open_reviews", lambda report: len(REQUESTS), DOWN, {"reviews_file": "reviews.json"}),
    ("cargo_offline", False, "offline", _codebase("codebase.warnings"), UP, {}),
    ("density_per_lines", 100, "lints", _codebase("codebase.lint_density"), DOWN, {}),
    ("test_density_per_lines", 1000, "test", _codebase("codebase.tests_per_100_lines"), UP, {}),
    ("change_coupling_scale", 1, "history", _file("file.change_coupling", "src/b.rs"), DOWN, {"change_coupling_min_shared": 2, "change_coupling_min_revisions": 2}),
    ("slop_density_per_words", 10, "Returns bytes, not characters.\n", _slop("neg-x-not-y", "warn"), DOWN, {"slop_min_file_words": 1, "slop_neg_x_not_y_per_paragraph": 9}),
    # One "rather than" in a short file passes the rate limit and warns only when one hit is enough.
    ("slop_density_min_count", 1, "Use a plain list rather than a set here.\n", _slop("neg-rather-than", "warn"), UP, {"slop_min_file_words": 1}),
    ("slop_density_per_sentences", 1000, "It reads the file, but stops early.\n", lambda report: next(float(finding.matched.split(", ")[1].split()[0]) for finding in report.slop if finding.rule == "but-density"), UP, {}),
    ("slop_vocab_density_per_words", 1, "A crucial design has properties.\n", _slop("vocab-density", "warn"), DOWN, {"slop_min_density_words": 1}),
    ("slop_emdash_per_words", 1, "One — two — three.\n", _slop("fmt-emdash", "metric"), DOWN, {"slop_emdash_count": 1, "slop_emdash_per_500_words": 3}),
    ("slop_excerpt_characters", 10, WORDS, lambda report: max(len(finding.matched) for finding in report.slop if finding.rule == "len-words"), DOWN, {"slop_len_words_metric": 10}),
    ("slop_heading_excerpt_characters", 5, "- 🚀 Launch the parser on every file of the folder\n", lambda report: max(len(finding.matched) for finding in report.slop if finding.rule == "fmt-emoji-bullet"), DOWN, {}),
    ("display_pieces", 1, "long", lambda report: len(render(report, "function").splitlines()), DOWN, {}),
    ("display_cycle_members", 1, "nested_cycle", lambda report: len(report.checks["check.dependency_cycles"].failures[0][1]), DOWN, {}),
    ("display_slop_match_characters", 3, "ticket", lambda report: len(next(f.shown(report.card.model.settings["display_slop_match_characters"]) for f in report.slop if f.rule == "comment-ticket")), DOWN, {}),
    ("slop_hrule_per_1000_words", 100000, "Some text here.\n\n---\n\nMore text here.\n", _slop("fmt-hrule", "metric"), DOWN, {"slop_hrule_count": 1}),
]


def _any_slop(rule: str):
    return lambda report: sum(1 for finding in report.slop if finding.rule == rule)


def _mean_sentence_words(report) -> float:
    return next(float(finding.matched.split()[0]) for finding in report.slop if finding.rule == "len-mean")


# The word lists the rules read in their code, each replaced by a list that leaves the fixture's word out, or takes it in.
CASES += [
    ("slop_abbreviations", ("works",), "It works. Then it stops.\n", _mean_sentence_words, UP, {"slop_len_mean_min_sentences": 1}),
    ("slop_coordinators", ("und",), "It reads and stores the file.\n", _slop("clause-coord", "warn"), DOWN, {"slop_clause_coordinators": 1}),
    ("slop_tail_relative_words", ("whereby",), "It reads the file, which holds rows.\n", _slop("clause-tails", "warn"), DOWN, {"slop_clause_tails": 1}),
    ("slop_tail_ignored_words", ("holding",), "It reads the file, holding rows.\n", _slop("clause-tails", "warn"), DOWN, {"slop_clause_tails": 1}),
    ("slop_late_subject_openers", ("whereas",), "Although it is slow, it works.\n", _slop("nest-late-subject", "warn"), DOWN, {"slop_late_subject_words": 1}),
    ("slop_starter_ignored_words", ("Run",), "Run it now. Run it then.\n", _slop("rhythm-starters", "warn"), DOWN, {"slop_rhythm_starters": 2}),
    ("slop_count_density_rules", ("count-announce",), "There are two constraints on this.\n", _any_slop("count-density"), DOWN, {}),
    ("slop_cluster_severities", ("metric",), "One, two, three, four, five, six.\n", _slop("cluster-paragraph", "warn"), DOWN, {"slop_cluster_rules": 1}),
    # `neg-bare` and `neg-not-only` match the same words; the first is reported only when the pair is taken out.
    ("slop_report_once", (), "This not only returns the value but also caches it.\n", _any_slop("neg-bare"), UP, {}),
    ("slop_number_words", ("zwei", "drei"), POSITIVE["count-there-are"] + "\n", _any_slop("count-there-are"), DOWN, {}),
    ("slop_abstract_nouns", ("gadgets?",), POSITIVE["count-noun"] + "\n", _any_slop("count-noun"), DOWN, {}),
    ("slop_homonyms", (("harbour", r"\bharbours?\b"),), POSITIVE["vocab-context"] + "\n", _any_slop("vocab-context"), DOWN, {}),
]

# A word list of the rule data, replaced by one word the example of its first rule does not hold.
CASES += [
    (list_setting(name), ("zzzz",), POSITIVE[SETTINGS[list_setting(name)][2][0]] + "\n", _any_slop(SETTINGS[list_setting(name)][2][0]), DOWN, {})
    for name in LISTS
]

# A rule in a Rust comment, for the rules that read comments only, and the one rule that reads a list after a paragraph.
RULE_FIXTURES = {"comment-ticket": "ticket", "comment-history": "comment_history", "comment-hedge": "comment_hedge", "count-mismatch": "There are three steps:\n\n- one\n- two\n"}


def _other_severity(rule_id: str) -> str:
    # The limit finding of len-words has severity warn by default.
    current = "warn" if rule_id == "len-words" else RULES[rule_id]["severity"]
    return "metric" if current == "warn" else "warn"


# The parameters of each rule: its severity is changed, and the rule's example then has a finding of the new severity.
# The example of `len-words` is past the rule's limit, where the finding has the severity of the limit.
CASES += [
    (
        rule_setting(rule_id),
        {"limit_severity" if rule_id == "len-words" else "severity": _other_severity(rule_id)},
        RULE_FIXTURES.get(rule_id) or POSITIVE[rule_id] + "\n",
        _slop(rule_id, _other_severity(rule_id)),
        UP,
        {},
    )
    for rule_id in RULES
]


def _failures(check: str):
    return lambda report: len(report.checks[check].failures)


def _test(metric_id: str):
    return _value(PieceKind.TEST, "sample::t", metric_id)


WEAKER = _failures("check.assertion_strength")
COMPLEXITY = _value(PieceKind.TYPE, "sample::S", "type.type_complexity")

# The word lists, expressions and numbers that define a measurement.
CASES += [
    ("primitive_types", ("u64",), "names", _function("function.primitive_param_share"), DOWN, {}),
    ("primitive_wrapper_types", ("Box",), "wrapped", _function("function.primitive_param_share"), UP, {}),
    ("invariant_words", ("positive",), "invariant", _value(PieceKind.TYPE, "sample::S", "type.public_invariant_fields"), UP, {}),
    ("assertion_helper_prefixes", ("ensure",), "helper_only", _test("test.no_assertion"), DOWN, {}),
    ("mock_call_patterns", ("stub",), "helper", _test("test.interaction_assertions"), UP, {}),
    ("test_sleep_names", ("pause",), "helper", _test("test.smell.sleep"), UP, {}),
    ("exact_output_calls", ("render",), "helper", _test("test.exact_output"), UP, {}),
    ("sensitive_equality_methods", ("to_owned",), "helper", _test("test.smell.sensitive_equality"), UP, {}),
    # By default t0 falls from a condition to a weak one and t1 from a comparison to a condition.
    ("weak_assertion_patterns", (r"\.is_ok\b", r"\.is_ready\b"), "weaker", WEAKER, UP, {}),
    ("value_assertion_macros", ("assert_eq", "assert_close"), "weaker", WEAKER, UP, {}),
    ("value_assertion_words", ("holds",), "weaker", WEAKER, UP, {}),
    ("assertion_tier_weak", 5, "weaker", WEAKER, DOWN, {}),
    ("assertion_tier_condition", 0, "weaker", WEAKER, DOWN, {}),
    ("assertion_tier_value", 0, "weaker", WEAKER, DOWN, {}),
    # `&u32` scores 11, `Box<dyn Send>` 50 and `fn(u32)` 70 by default.
    ("type_complexity_reference_score", 100, "complex", COMPLEXITY, UP, {}),
    ("type_complexity_type_score", 11, "complex", COMPLEXITY, UP, {}),
    ("type_complexity_trait_object_score", 100, "complex", COMPLEXITY, UP, {}),
    ("type_complexity_function_score", 60, "complex", COMPLEXITY, UP, {}),
    ("decorative_comment_patterns", ("zzzz",), "decorative", _file("file.decorative_comments"), DOWN, {}),
    ("suppression_attributes", ("deny",), "suppressed", _file("file.suppressions"), DOWN, {}),
    ("new_suppression_patterns", ("zzzz",), "suppress", _failures("check.new_suppressions"), DOWN, {}),
    ("manifest_suppression_patterns", ("zzzz",), "lint_table", _failures("check.new_suppressions"), DOWN, {}),
    ("rust_fence_patterns", ("rust",), "example", _value(PieceKind.CRATE, "sample", "crate.example_coverage"), DOWN, {}),
    ("conventional_commit_pattern", "^zzzz", "messages", _codebase("codebase.unconventional_messages"), UP, {}),
    ("revert_subject_prefixes", ("Undo",), "reverted", _codebase("codebase.reverts"), UP, {}),
    ("short_name_vowels", "aeiouyc", "short", _function("function.short_names"), DOWN, {"short_names_min_names": 1}),
    ("short_name_max_letters", 2, "short", _function("function.short_names"), UP, {"short_names_min_names": 1}),
    ("debt_marker_words", ("LATER",), "debt", _codebase("codebase.debt_markers"), DOWN, {}),
    ("debt_marker_macros", ("pending",), "panics", _codebase("codebase.debt_markers"), DOWN, {}),
    ("getter_name_prefixes", ("fetch",), "prefixes", _function("function.name_mismatch", "fetch_it"), UP, {}),
    ("predicate_name_prefixes", ("was",), "prefixes", _function("function.name_mismatch", "was_it"), UP, {}),
    ("setter_name_prefixes", ("put",), "prefixes", _function("function.name_mismatch", "put_it"), UP, {}),
]


def test_every_setting_has_an_override_case():
    assert sorted(case[0] for case in CASES) == sorted(SETTINGS)


# A setting that is read in several places, probed at each of the others: the cases above probe one.
OTHER_PLACES = [
    ("density_per_lines", 100, "debt", _codebase("codebase.debt_markers"), DOWN, {}),
    ("density_per_lines", 100, "grow", _codebase("codebase.debt_trend"), DOWN, {}),
    ("density_per_lines", 100, "grow", _codebase("codebase.equilibrium"), UP, {"equilibrium_zero_debt_per_1000_lines": 1000}),
    ("test_density_per_lines", 1000, "test", _value(PieceKind.CRATE, "sample", "crate.tests_per_100_lines"), UP, {}),
    ("restating_stop_words", ("quickly",), "comments", _file("file.wet_docs"), UP, {}),
    # `snapshot!` is no assertion, so only the count of the test's macro calls can find it.
    ("test_exact_output_macros", ("snapshot",), "snapshot", _value(PieceKind.TEST, "sample::t", "test.exact_output"), UP, {}),
    ("slop_rule_triad_doc", {"exceptions": ("reads",)}, "It reads files, checks tokens, and writes output.\n", _any_slop("triad-doc"), DOWN, {}),
    ("slop_rule_stock_tail_rate", {"exceptions": ("keeping",)}, "It holds every row, keeping the order.\n", _any_slop("stock-tail-rate"), DOWN, {}),
    # A pattern without a group for the letters of the ticket.
    ("slop_rule_comment_ticket", {"patterns": (r"\bcast\b",)}, "comment_hedge", _any_slop("comment-ticket"), UP, {}),
]

# The patterns of each rule that has them, replaced by one its example does not hold: the rule then finds nothing there.
OTHER_PLACES += [
    (rule_setting(rule_id), {"patterns": ("zzzz",)}, RULE_FIXTURES.get(rule_id) or POSITIVE[rule_id] + "\n", _any_slop(rule_id), DOWN, {})
    for rule_id in RULES
    if "patterns" in SETTINGS[rule_setting(rule_id)][0]
]


def _build(root, fixture: str):
    commits, working_tree, hook = FIXTURES[fixture] if fixture in FIXTURES else (_doc(fixture), None, None)
    make_repository(root, commits[0])
    for index, entry in enumerate(commits[1:]):
        files, message = entry if isinstance(entry, tuple) else (entry, f"feat: change {index}")
        # `{sha}` in a file stands for the commit before, as a review marker names it.
        previous = git(root, "rev-parse", "HEAD").strip()[:12]
        commit(root, {path: text.replace("{sha}", previous) for path, text in files.items()}, message)
    if working_tree:
        git(root, "checkout", "-q", "-b", "work")
        for path in [path for path, text in working_tree.items() if text is None]:
            (root / path).unlink()
        write_tree(root, {path: text for path, text in working_tree.items() if text is not None})
    return hook


ALL_CASES = [*CASES, *OTHER_PLACES]


@pytest.mark.parametrize(
    ("setting", "value", "fixture", "probe", "direction", "base"), ALL_CASES, ids=[f"{case[0]}{'' if index < len(CASES) else '-also'}" for index, case in enumerate(ALL_CASES)]
)
def test_a_setting_from_the_policy_changes_the_result(tmp_path, setting, value, fixture, probe, direction, base):
    root = tmp_path / "repo"
    hook = _build(root, fixture)

    def result(settings: dict) -> float:
        policy = scored_policy()
        if hook:
            hook(policy)
        for name, number in settings.items():
            policy.setting(name, number)
        return probe(_analyze(policy, root, fixture))

    before, after = result(base), result({**base, setting: value})
    assert (after - before) * direction > 0, f"{setting}: {before} -> {after}"
