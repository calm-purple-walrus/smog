"""Hand-computed values of the crate measurements, on small fixtures."""

from smog.adapter.cargo_manifests import CargoManifests
from smog.domain.code import Codebase, Crate
from smog.domain.measure import build_scorecard
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from tests.helpers import parse_source_file

READER = CargoManifests()


def _package(name: str, body: str = "") -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\n{body}'


def _locked(*packages: tuple) -> str:
    """Cargo.lock text from (name, version, dependency, ...) rows."""
    entries = []
    for name, version, *dependencies in packages:
        listed = f"dependencies = {list(dependencies)!r}\n".replace("'", '"') if dependencies else ""
        entries.append(f'[[package]]\nname = "{name}"\nversion = "{version}"\n{listed}')
    return "\n".join(entries)


def _crates(manifests: dict[str, str], sources: dict[str, str], lock: str = "", audits: dict[str, str] | None = None, policy: Policy | None = None) -> dict[str, dict]:
    """Values per crate. `manifests` maps a crate folder to its Cargo.toml text; `sources` maps paths to Rust."""
    read = READER.read_manifests({f"{folder}/Cargo.toml".lstrip("/"): text.encode() for folder, text in manifests.items()})
    crates = []
    for manifest in read:
        prefix = f"{manifest.directory}/" if manifest.directory else ""
        files = [parse_source_file(source, path, manifest.name, manifest.directory) for path, source in sources.items() if path.startswith(prefix)]
        crates.append(Crate(manifest, files))
    records = READER.read_audits({path: text.encode() for path, text in (audits or {}).items()})
    codebase = Codebase(crates, READER.read_lock(lock.encode()) if lock else [], list(sources), {}, records)
    card = build_scorecard(codebase, policy or Policy())
    return {piece.id: piece.values for piece in card.pieces(PieceKind.CRATE)}


TREE_MANIFESTS = {
    "app": _package(
        "app",
        '[dependencies]\nlib = { path = "../lib" }\nserde = "1"\n[dev-dependencies]\nserde = "1"\ntempfile = "3"\n'
        '[build-dependencies]\ncc = "1"\n[target."cfg(unix)".dependencies]\nlibc = "0.2"\n',
    ),
    "lib": _package("lib", '[dependencies]\nrand = "0.8"\n[dev-dependencies]\nproptest = "1"\n'),
}
TREE_SOURCES = {"app/src/main.rs": "use lib::f;\nuse serde::Serialize;\nfn main() {}\n", "lib/src/lib.rs": "pub fn f() {}\n"}
TREE_LOCK = _locked(
    ("app", "0.1.0", "cc", "lib", "libc", "serde", "tempfile"),
    ("lib", "0.1.0", "proptest", "rand 0.8.5"),
    ("serde", "1.0.0", "serde_derive"),
    ("serde_derive", "1.0.0"),
    ("cc", "1.0.0"),
    ("libc", "0.2.0"),
    ("tempfile", "3.0.0", "rand 0.9.0", "libc"),
    ("rand", "0.8.5", "libc"),
    ("rand", "0.9.0"),
    ("proptest", "1.0.0"),
)


def test_dependency_counts_split_direct_total_and_dev_only():
    crates = _crates(TREE_MANIFESTS, TREE_SOURCES, TREE_LOCK)
    app = crates["app"]
    # Direct and external under [dependencies]: serde and the unix-only libc. tempfile is the only dev-only one.
    assert (app["crate.dependencies_external"], app["crate.dependencies_dev"]) == (2, 1)
    # Normal and build tree: serde, serde_derive, cc, libc, and rand 0.8.5 through the workspace crate lib.
    # proptest is a dev-dependency of lib and is not part of app's tree.
    assert app["crate.dependencies_total"] == 5
    # Only through tempfile: tempfile and rand 0.9.0.
    assert app["crate.dependencies_total_dev"] == 2
    assert app["crate.duplicate_versions"] == 1
    lib = crates["lib"]
    assert (lib["crate.dependencies_external"], lib["crate.dependencies_dev"]) == (1, 1)
    assert (lib["crate.dependencies_total"], lib["crate.dependencies_total_dev"], lib["crate.duplicate_versions"]) == (2, 1, 0)


def test_lock_values_need_a_lock_file_that_lists_the_crate():
    without = _crates(TREE_MANIFESTS, TREE_SOURCES)["app"]
    assert without["crate.dependencies_dev"] == 1 and "crate.dependencies_total" not in without
    other = _crates(TREE_MANIFESTS, TREE_SOURCES, _locked(("elsewhere", "1.0.0")))["app"]
    assert "crate.dependencies_total" not in other and "crate.duplicate_versions" not in other
    bare = _crates({"": _package("bare")}, {"src/lib.rs": ""}, _locked(("bare", "0.1.0")))["bare"]
    assert (bare["crate.dependencies_total"], bare["crate.dependencies_total_dev"]) == (0, 0)


def test_unused_dependencies_are_those_whose_name_is_in_no_source_token():
    manifests = {"": _package("sample", '[dependencies]\nserde = "1"\nserde-json = "1"\nlog = "0.4"\n[dev-dependencies]\nrstest = "0.18"\nidle = "1"\n')}
    sources = {"src/lib.rs": "#[derive(serde::Serialize)]\npub struct S;\npub fn f() {\n    serde_json::to_string(&S);\n}\n", "tests/it.rs": "use rstest::rstest;\n"}
    assert _crates(manifests, sources)["sample"]["crate.unused_dependencies"] == 2
    policy = Policy()
    policy.ignore_unused_dependencies("log")
    assert _crates(manifests, sources, policy=policy)["sample"]["crate.unused_dependencies"] == 1


AUDITS = """
[[audits.serde]]
criteria = "safe-to-deploy"
version = "0.9.0"

[[audits.serde]]
criteria = "safe-to-deploy"
delta = "0.9.0 -> 0.9.5"

[[audits.serde]]
criteria = "safe-to-run"
delta = "0.9.5 -> 1.0.0"

[[audits.cc]]
criteria = "safe-to-deploy"
delta = "0.9.0 -> 1.0.0"

[[audits.libc]]
criteria = "safe-to-deploy"
violation = "*"
"""
IMPORTS = """
[[publisher.tempfile]]
version = "3.0.0"

[[audits.other.audits.rand]]
criteria = "safe-to-deploy"
version = "0.8.5"

[[audits.other.wildcard-audits.libc]]
criteria = "safe-to-deploy"
user-id = 1
"""


def test_audited_share_counts_full_audits_and_delta_chains():
    records = {"supply-chain/audits.toml": AUDITS, "supply-chain/imports.lock": IMPORTS}
    crates = _crates(TREE_MANIFESTS, TREE_SOURCES, TREE_LOCK, records)
    # app's tree with dev-dependencies has 7 packages. Audited: serde 1.0.0 by a full audit and two deltas, and
    # rand 0.8.5 by an imported full audit. cc has a delta from a version nobody audited; the publisher entry,
    # the wildcard audit and the violation are no audits; serde_derive, tempfile and rand 0.9.0 have no record.
    assert crates["app"]["crate.audited_dependency_share"] == 2 / 7
    # lib: rand 0.8.5 and libc are in its tree, and proptest through its own dev-dependencies.
    assert crates["lib"]["crate.audited_dependency_share"] == 1 / 3


def test_audited_share_has_no_value_without_records_or_packages():
    assert "crate.audited_dependency_share" not in _crates(TREE_MANIFESTS, TREE_SOURCES, TREE_LOCK)["app"]
    assert "crate.audited_dependency_share" not in _crates(TREE_MANIFESTS, TREE_SOURCES, TREE_LOCK, {"supply-chain/imports.lock": IMPORTS})["app"]
    bare = _crates({"": _package("bare")}, {"src/lib.rs": ""}, _locked(("bare", "0.1.0")), {"supply-chain/audits.toml": AUDITS})["bare"]
    assert "crate.audited_dependency_share" not in bare


API = {
    "src/lib.rs": """//! The crate.
pub mod open;
mod closed;
pub use closed::Shown;

/// Adds.
///
/// ```
/// add();
/// ```
pub fn add() {}
pub(crate) fn inside() {}
""",
    "src/open.rs": """/// A point.
pub struct Point {
    /// Across.
    pub x: u8,
    pub y: u8,
    z: u8,
}
impl Point {
    /// Makes one.
    ///
    /// ```ignore
    /// Point::new();
    /// ```
    pub fn new() -> Self { todo!() }
    fn private(&self) {}
}
impl Default for Point {
    fn default() -> Self { todo!() }
}
pub enum Kind {
    /// The first.
    A,
    B(u8),
}
pub trait Shape {
    /// The area.
    fn area(&self) -> u8;
    fn name(&self) -> u8 { 0 }
}
pub const LIMIT: u8 = 1;
#[cfg(test)]
mod tests {
    pub fn in_test() {}
}
""",
    "src/closed.rs": """//! Hidden things.
/// Shown through a re-export.
///
/// ```rust,no_run
/// let s = Shown;
/// ```
pub struct Shown;
pub struct Hidden;
""",
    "tests/it.rs": "pub fn helper() {}\n",
}
API_MANIFEST = {"": _package("sample")}


def test_public_api_items_are_the_exported_pub_items():
    values = _crates(API_MANIFEST, API)["sample"]
    # Root: `pub mod open` and `add`. open: Point, new, Kind, Shape and LIMIT. closed: Shown only.
    assert values["crate.public_api_items"] == 8
    # Every `pub` item outside test code, exported or not: the 8, and Hidden. `in_test` and `helper` are test code.
    assert values["crate.public_items"] == 9


def test_documentation_coverage_counts_items_fields_variants_and_trait_methods():
    values = _crates(API_MANIFEST, API)["sample"]
    # Items: the crate root, `pub mod open`, add, Point, x, y, new, Kind, A, B, Shape, area, name, LIMIT and Shown: 15.
    # Documented: the root, add, Point, x, new, A, area and Shown: 8. `open` has neither `///` nor `//!`.
    assert values["crate.documentation_coverage"] == 8 / 15


def test_example_coverage_counts_rust_code_blocks_that_are_not_ignored():
    values = _crates(API_MANIFEST, API)["sample"]
    # Can have an example: add, Point, new, Kind, Shape, area, name and Shown. With one: add and Shown.
    assert values["crate.example_coverage"] == 2 / 8


def test_a_module_is_documented_by_an_inner_comment_and_empty_crates_have_no_share():
    sources = {"src/lib.rs": "pub mod a;\n/// Outer.\npub mod b;\npub mod c { //! Inner.\n}\npub mod d {}\n", "src/a.rs": "//! Inner.\n", "src/b.rs": ""}
    # The root (undocumented) and the four modules; a, b and c are documented.
    assert _crates(API_MANIFEST, sources)["sample"]["crate.documentation_coverage"] == 3 / 5
    only_tests = _crates(API_MANIFEST, {"tests/it.rs": "pub fn helper() {}\n"})["sample"]
    assert "crate.documentation_coverage" not in only_tests and "crate.example_coverage" not in only_tests
    assert only_tests["crate.public_api_items"] == 0


def test_code_fences():
    from smog.domain.lenses.crate_api import has_example

    assert has_example(" Text.\n\n ```\n code\n ```\n")
    assert has_example(" ```rust,should_panic\n code\n ```\n")
    assert has_example(" * ~~~edition2021\n * code\n * ~~~\n")
    assert not has_example(" ```text\n words\n ```\n")
    assert not has_example(" ```ignore\n code\n ```\n")
    assert not has_example(" ```toml\n a = 1\n ```\n")
    # The closing fence of a non-Rust block opens nothing.
    assert not has_example(" ```sh\n ls\n ```\n Then more text.\n")
    assert not has_example(" No code here.\n")


EXPOSED_MANIFEST = {
    "": _package(
        "sample",
        '[dependencies]\nby-path = "0.3"\nimported = "1"\nfielded = "0.9"\nimplemented = "2"\nprivate-only = "0.1"\nbody-only = "0.1"\n'
        '[dev-dependencies]\ntesting = "0.1"\n',
    )
}
EXPOSED = {
    "src/lib.rs": """use imported::deep::Thing;
use body_only::Helper;
mod hidden;
pub fn takes(arg: by_path::Options) -> u8 { Helper::run(); 0 }
pub fn gives() -> Option<Thing> { None }
pub struct Wide { pub inner: fielded::Inner, quiet: private_only::Q }
pub struct Error;
impl From<implemented::Failure> for Error {
    fn from(e: implemented::Failure) -> Self { Error }
}
fn internal(arg: private_only::Q) {}
pub(crate) fn inside(arg: private_only::Q) {}
""",
    "src/hidden.rs": "pub fn unexported(arg: private_only::Q) {}\n",
    "tests/it.rs": "pub fn helper(arg: testing::T) {}\n",
}
EXPOSED_LOCK = _locked(
    ("sample", "0.1.0", "by-path", "imported", "fielded", "implemented", "private-only", "body-only", "testing"),
    ("by-path", "0.3.1"),
    ("imported", "1.2.0"),
    ("fielded", "0.9.0"),
    ("implemented", "2.0.0"),
    ("private-only", "0.1.0"),
    ("body-only", "0.1.0"),
    ("testing", "0.1.0"),
)


def test_exposed_dependencies_are_named_in_the_exported_interface():
    values = _crates(EXPOSED_MANIFEST, EXPOSED, EXPOSED_LOCK)["sample"]
    # by-path in a signature, imported through `use`, fielded in a `pub` field, implemented in a `From` impl.
    # private-only is in a private field, private functions and an unexported module; body-only is in a body.
    assert values["crate.exposed_dependencies"] == 4
    # by-path 0.3.1 and fielded 0.9.0 are below 1.0.
    assert values["crate.exposed_unstable_dependencies"] == 2
    without_lock = _crates(EXPOSED_MANIFEST, EXPOSED)["sample"]
    assert without_lock["crate.exposed_dependencies"] == 4 and "crate.exposed_unstable_dependencies" not in without_lock


def _count(unsafe: int) -> dict:
    return {"safe": 5, "unsafe_": unsafe}


def _geiger_entry(name: str, used: tuple, unused: int = 9) -> dict:
    kinds = ("functions", "exprs", "item_impls", "item_traits", "methods")
    return {
        "package": {"id": {"name": name, "version": "1.0.0", "source": {"Path": "."}}, "dependencies": [], "dev_dependencies": [], "build_dependencies": []},
        "unsafety": {"used": dict(zip(kinds, map(_count, used))), "unused": dict.fromkeys(kinds, _count(unused)), "forbids_unsafe": False},
    }


def test_the_geiger_report_sums_used_unsafe_items_of_dependencies():
    import json

    from smog.adapter.cargo_tools import parse_geiger_report

    report = {"packages": [_geiger_entry("app", (7, 7, 7, 7, 7)), _geiger_entry("dep", (1, 2, 0, 0, 3)), _geiger_entry("other", (0, 4, 1, 1, 0))], "packages_without_metrics": []}
    output = "warning: something\n" + json.dumps(report) + "\n"
    # dep: 1 + 2 + 3. other: 4 + 1 + 1. The workspace crate app and the unused code are left out.
    assert parse_geiger_report(output, {"app"}) == 12
    assert parse_geiger_report("error: no report\n", {"app"}) is None


def test_the_semver_report_gives_failed_checks_per_crate():
    from smog.adapter.cargo_tools import parse_semver_report

    output = """     Parsing lib v0.2.0 (current)
    Checking lib v0.1.0 -> v0.1.0 (no change)
     Checked [   0.012s] 94 checks: 92 pass, 2 fail, 0 warn, 0 skip

--- failure function_missing: pub fn removed or renamed ---
     Summary semver requires new major version: 2 major and 0 minor checks failed
    Checking clean v0.1.0 -> v0.2.0 (minor change)
     Checked [   0.010s] 120 checks: 120 pass, 45 skip
    Checking broken v0.1.0 -> v0.1.0 (no change)
"""
    assert parse_semver_report(output) == {"lib": 2, "clean": 0}


def _run_with_tools(root, tools, ref=None, **given):
    from smog.adapter.git_repository import GitRepository
    from smog.adapter.tree_sitter_parser import TreeSitterRustParser
    from smog.application.analyze import Analyzer
    from smog.ports import Tooling

    policy = Policy()
    if ref:
        policy.against(ref)
    return Analyzer(GitRepository(str(root)), TreeSitterRustParser(), READER, Tooling(**given)).analyze(policy, full=True, tools=tools)


def test_tool_values_land_on_their_crates_and_missing_tools_are_named(tmp_path):
    from tests.helpers import MANIFEST, make_repository

    make_repository(tmp_path / "repo", {"Cargo.toml": MANIFEST, "src/lib.rs": "mod a;\n", "src/a.rs": "pub fn f() {}\n"})
    seen = {}

    def geiger(root, manifests):
        seen["manifests"] = manifests
        return {"sample": 12}

    def semver(root, base_sha):
        return {"sample": 2, "elsewhere": 5}

    def lint(root):
        from smog.domain.tools import LintWarning

        return [LintWarning("unreachable_pub", "src/a.rs", 1, "unreachable `pub` item")]

    report = _run_with_tools(tmp_path / "repo", ("geiger", "semver", "clippy"), "main", unsafe_in_dependencies=geiger, semver_violations=semver, unreachable_pub=lint)
    crate = report.card.find(PieceKind.CRATE, "sample")
    assert (crate.value("crate.unsafe_in_dependencies"), crate.value("crate.semver_violations")) == (12, 2)
    assert seen["manifests"] == {"sample": "Cargo.toml"}
    assert report.card.find(PieceKind.MODULE, "sample::a").value("module.unreachable_pub") == 1

    without = _run_with_tools(tmp_path / "repo", ("geiger", "semver", "clippy"))
    crate = without.card.find(PieceKind.CRATE, "sample")
    assert "crate.unsafe_in_dependencies" not in crate.values and "crate.semver_violations" not in crate.values
    assert without.tools.notes["cargo geiger"] == "no cargo-geiger run was given"
    assert without.tools.notes["cargo semver-checks"] == "needs a ref"
    assert without.tools.notes["unreachable_pub lint"] == "no unreachable_pub lint was given"
    # Without the lint the syntax count stays: `mod a` is private and nothing re-exports `f`.
    assert without.card.find(PieceKind.MODULE, "sample::a").value("module.unreachable_pub") == 1

    off = _run_with_tools(tmp_path / "repo", ("tests",), "main", unsafe_in_dependencies=geiger, semver_violations=semver)
    assert off.tools.notes["cargo geiger"] == "not selected" and off.tools.notes["cargo semver-checks"] == "not selected"


def test_a_tool_that_ran_for_some_crates_gives_their_values_and_says_what_is_missing(tmp_path):
    from smog.ports import ToolIncomplete
    from tests.helpers import MANIFEST, make_repository

    make_repository(tmp_path / "repo", {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})

    def semver(root, base_sha):
        raise ToolIncomplete("reported on 1 crates and failed for the rest: error: no network", {"sample": 2})

    report = _run_with_tools(tmp_path / "repo", ("semver",), "main", semver_violations=semver)
    assert report.card.find(PieceKind.CRATE, "sample").value("crate.semver_violations") == 2
    assert report.tools.notes["cargo semver-checks"] == "reported on 1 crates and failed for the rest: error: no network"


TESTED = """pub fn a() -> u8 {
    1
}

#[cfg(test)]
mod tests {
    use super::*;

    fn helper() -> u8 {
        1
    }

    #[test]
    fn t() {
        assert_eq!(a(), helper());
    }
}
"""


def test_crate_and_codebase_test_lines_are_the_sum_of_file_test_lines():
    sources = {"src/lib.rs": TESTED, "tests/it.rs": "use sample::a;\n#[test]\nfn it() {\n    a();\n}\n"}
    crates = [Crate(READER.read_manifests({"Cargo.toml": _package("sample").encode()})[0], [parse_source_file(text, path) for path, text in sources.items()])]
    card = build_scorecard(Codebase(crates, [], list(sources), {}), Policy())
    files = card.pieces(PieceKind.FILE)
    # lib.rs: 3 production lines and the 11 code lines of the test module, `use` and braces included. it.rs: 5 test lines.
    assert [(file.value("file.production_lines"), file.value("file.test_lines")) for file in files] == [(3, 11), (0, 5)]
    crate = card.find(PieceKind.CRATE, "sample")
    assert crate.value("crate.test_lines_per_line") == 16 / 3
    assert card.root.value("codebase.test_lines_per_line") == 16 / 3
    # Two test cases over 3 production lines.
    assert crate.value("crate.tests_per_100_lines") == 200 / 3
    assert card.root.value("codebase.tests_per_100_lines") == 200 / 3


def test_a_listing_without_values_says_what_the_metric_needs(tmp_path):
    from smog.adapter.console import metric_data, render_metric
    from tests.helpers import MANIFEST, make_repository

    make_repository(tmp_path / "repo", {"Cargo.toml": MANIFEST, "src/lib.rs": "pub fn f() {}\n"})
    report = _run_with_tools(tmp_path / "repo", ("geiger",))
    text = render_metric(report, metric_data(report, "crate.unsafe_in_dependencies"))
    assert "No piece has a value for this metric. What it needs: Runs cargo-geiger once per crate, offline." in text
    assert "not run: cargo geiger: no cargo-geiger run was given" in text
    audited = render_metric(report, metric_data(report, "crate.audited_dependency_share"))
    assert "No value without those files." in audited
