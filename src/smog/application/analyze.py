"""The use case: load code, measure it, compare it with the ref, and apply the policy."""

import os
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from smog.domain.changes import CommitInfo, FileChange, ItemDelta
from smog.domain.code import Codebase, SourceFile, crate_folder, mark_test_modules
from smog.domain.comparison import Comparison
from smog.domain.graph import FileGraph
from smog.domain.history import CommitRecord, History, is_code_text, is_fix_subject
from smog.domain.lenses.checks import CheckResult, diff_checks, diff_checks_skipped, static_checks, tests_in_build
from smog.domain.measure import build_scorecard, local_debt, restrict_scorecard
from smog.domain.policy import Policy, Run
from smog.domain.registry import PieceKind
from smog.domain.report import Report, selected_without_value
from smog.domain.reviews import review_marker_commit, reviewed_commits, unreviewed_lines
from smog.domain.settings import DEFAULT_SETTINGS
from smog.domain.slop import is_exempt, scan_markdown, scan_rust_file
from smog.domain.slop_explanations import SLOP_EXPLANATIONS
from smog.domain.syntax import Node
from smog.domain.tools import NOT_SELECTED, WITHOUT_FULL, ToolResults
from smog.ports import ToolIncomplete, ManifestReader, Repository, RustParser, Tooling, ToolUnavailable

AUDIT_FILES = ("supply-chain/audits.toml", "supply-chain/imports.lock")
ALL_TOOLS = ("clippy", "tests", "coverage", "mutants", "index", "build", "probe", "fmt", "geiger", "semver", "nextest", "shuffle")
# Tools that use the network. They run only when named: `--full` alone does not run them.
NETWORK_TOOLS = ("reviews",)
SHALLOW_CLONE = (
    "the clone is shallow, so `git blame` cannot name the commit that last changed a line: it names the oldest commit the clone holds "
    "for every older line. The review measurements and function.szz_fixes, file.szz_fixes and codebase.bug_introducing_share have no "
    "value, and the history window ends where the clone ends. `git fetch --unshallow`, or a checkout with full history, gives them"
)


# Which commits a fetch asks for again, by the setting `reviews_refetch`. `none` asks for no commit again.
_ASKED_AGAIN = {
    "unmerged": "that were recorded without a merged pull request",
    "all": "of the reviews file, among them commits of merged pull requests whose reviews may have changed since,",
    "none": "of the reviews file",
}


def _name_slop(card, slop: list, settings: dict) -> None:
    """Each Rust file's counted slop findings as the problems behind its file.slop_findings: line, rule title and text."""
    by_path: dict[str, list[str]] = {}
    for finding in sorted(slop, key=lambda finding: (finding.path, finding.line)):
        if finding.severity in settings["slop_counted_severities"] and finding.path.endswith(".rs"):
            title = SLOP_EXPLANATIONS.get(finding.rule, {}).get("title", finding.rule)
            by_path.setdefault(finding.path, []).append(f"line {finding.line} {title}: {finding.shown(settings['display_slop_match_characters'])}")
    for path, problems in by_path.items():
        piece = card.find(PieceKind.FILE, path)
        if piece is not None:
            piece.set_problems("file.slop_findings", tuple(problems))


def _counted_slop(slop: list, policy: Policy) -> tuple[Counter, int]:
    """The slop findings that count toward a score: per Rust file, and in all documents."""
    counted = [finding for finding in slop if finding.severity in policy.settings["slop_counted_severities"]]
    return Counter(finding.path for finding in counted if finding.path.endswith(".rs")), sum(1 for finding in counted if finding.path.endswith(".md"))


class Analyzer:
    def __init__(self, repository: Repository, parser: RustParser, manifests: ManifestReader, tooling: Tooling | None = None):
        self._repository = repository
        self._parser = parser
        self._manifests = manifests
        self._tooling = tooling
        self._parsed: dict[bytes, Node] = {}

    def _parse(self, source: bytes) -> Node:
        if source not in self._parsed:
            self._parsed[source] = self._parser.parse(source)
        return self._parsed[source]

    def load_codebase(self, policy: Policy, ref: str | None = None) -> Codebase:
        tracked = self._repository.tracked_paths(ref)
        wanted = [p for p in tracked if p.endswith((".rs", ".md")) or p.rsplit("/", 1)[-1] in ("Cargo.toml", "Cargo.lock") or p in AUDIT_FILES]
        contents = self._repository.read_files(wanted, ref)
        unreadable = self._manifests.unreadable({path: source for path, source in contents.items() if not path.endswith((".rs", ".md"))})
        contents = {path: source for path, source in contents.items() if path not in unreadable}
        parsed = [(path, source, self._parse(source)) for path, source in contents.items() if path.endswith(".rs")]
        manifest_files = {path: source for path, source in contents.items() if path.endswith("Cargo.toml")}
        lock = self._manifests.read_lock(contents["Cargo.lock"]) if "Cargo.lock" in contents else []
        documents = {path: source.decode("utf-8", "replace") for path, source in contents.items() if path.endswith(".md")}
        audits = self._manifests.read_audits({path: source for path, source in contents.items() if path in AUDIT_FILES})
        settings = policy.settings
        manifests = self._manifests.read_manifests(manifest_files)
        return Codebase.build(parsed, manifests, lock, tracked, documents, policy.excluded, settings, audits, unreadable)

    def load_history(self, policy: Policy, shallow: bool = False) -> History:
        """The commits of the history window. In a shallow clone no line is blamed (`SHALLOW_CLONE`).

        A file of an old commit is test code by the same rule as now (`SourceFile.is_test`), with the crate
        folders the working tree has."""
        commits = self._repository.first_parent_commits(policy.window)
        branch_tips = self._repository.branch_tips()
        if not commits:
            return History([], policy.settings, branch_tips, not shallow)
        model = policy.scoring_model()
        start = commits[0].parent or commits[0].sha
        walked = commits if commits[0].parent else commits[1:]
        paths = [p for p in self._repository.tracked_paths(start) if p.endswith(".rs")]
        tracked_now = self._repository.tracked_paths()
        files = {path: self._source_file(path, source, policy.settings, tracked_now) for path, source in self._repository.read_files(paths, start).items()}
        mark_test_modules(files.values(), files.values())
        local = {path: local_debt(file, model, policy.settings) for path, file in files.items()}
        records = []
        for commit in walked:
            changes = self._repository.changes_in(commit.sha)
            rust_changes = [change.path for change in changes if change.path.endswith(".rs")]
            contents = self._repository.read_files([c.path for c in changes if c.path.endswith(".rs") and not c.is_deleted], commit.sha)
            old_files = [files[path] for path in rust_changes if path in files]
            is_fix = is_fix_subject(commit.subject, policy.settings)
            fixed = self._fixed_commits(commit) if is_fix else ()
            blamed = self._blamed_lines(commit, changes, files) if is_fix and not shallow else ()
            new_files = [self._source_file(path, source, policy.settings, tracked_now) for path, source in contents.items()]
            for path in rust_changes:
                files.pop(path, None)
                local.pop(path, None)
            files.update({file.path: file for file in new_files})
            was_test = {path: file.is_test for path, file in files.items()}
            mark_test_modules(files.values(), files.values())
            for path, file in files.items():
                if path not in local or file.is_test != was_test[path]:
                    local[path] = local_debt(file, model, policy.settings)
            debt = sum(value for value, _ in local.values())
            lines = sum(file.code_line_count for file in files.values())
            findings = {finding for _, found in local.values() for finding in found}
            message = {"author": commit.author, "body": commit.body, "trailers": commit.trailers, "parents": commit.parents, "fixed": fixed, "blamed": blamed}
            if len(commit.parents) > 1:
                message["branch_start"] = self._repository.merged_branch_start(commit.sha)
            records.append(CommitRecord(commit.sha, commit.subject, commit.timestamp, changes, ItemDelta(old_files, new_files, policy.settings["function_match_min_similarity"]), debt, lines, findings, **message))
        return History(records, policy.settings, branch_tips, not shallow)

    def _fixed_commits(self, commit: CommitInfo) -> tuple[str, ...]:
        """The ancestors of a commit that its `Fixes:` trailers name by hash."""
        hashes = [value.split()[0] for token, value in commit.trailers if token.lower() == "fixes" and value.split()]
        found = [self._repository.ancestor_commit(name, commit.sha) for name in hashes]
        return tuple(sha for sha in found if sha)

    def _blamed_lines(self, commit: CommitInfo, changes: list[FileChange], files_before: dict[str, SourceFile]) -> tuple:
        """For a fix commit: (path, function key or None, blamed commit) per code line it removes in a `.rs` file."""
        blamed = []
        for change in changes:
            lines = [line for line, text in change.removed if is_code_text(text)]
            if not change.path.endswith(".rs") or not lines or commit.parent is None:
                continue
            origin = self._repository.blame(commit.parent, change.path, lines)
            before = files_before.get(change.path)
            for line in lines:
                holders = [f for f in before.functions if f.start_line <= line <= f.end_line] if before else []
                key = max(holders, key=lambda f: f.start_line).history_key if holders else None
                if line in origin:
                    blamed.append((change.path, key, origin[line]))
        return tuple(blamed)

    def _source_file(self, path: str, source: bytes, settings: dict, tracked_paths: list[str]) -> SourceFile:
        return SourceFile(path, source, self._parse(source), "", crate_folder(path, tracked_paths), settings)

    def scan_slop(self, codebase: Codebase, policy: Policy) -> list:
        findings = []
        for file in codebase.files:
            if not is_exempt(file.path, policy.slop_exempt_paths):
                findings.extend(scan_rust_file(file, policy.slop_allowed_rules, policy.settings))
        for path, text in codebase.documents.items():
            if not is_exempt(path, policy.slop_exempt_paths):
                findings.extend(scan_markdown(path, text, policy.slop_allowed_rules, policy.settings))
        return findings

    def run_tools(
        self, selected: tuple[str, ...], base_sha: str | None, mutants_scope: str = "diff", manifests: dict[str, str] | None = None, settings: dict = DEFAULT_SETTINGS
    ) -> ToolResults:
        """`mutants_scope` is `diff` to mutate the lines changed against `base_sha`, or `tree` to mutate the whole codebase.

        `manifests` maps each crate name to its Cargo.toml, for the tools that run once per crate. `settings` gives
        the number of retries and the shuffle seeds of the test runs."""
        if mutants_scope not in ("diff", "tree"):
            raise ValueError(f"mutants_scope must be 'diff' or 'tree', not {mutants_scope!r}")
        results = ToolResults()
        root = self._repository.root
        self._tooling.prepare(settings)

        def attempt(name, label, tool, *args):
            if name not in selected:
                results.note(label, NOT_SELECTED)
                return None
            try:
                return tool(*args)
            except ToolIncomplete as error:
                results.note(label, str(error))
                return error.partial
            except ToolUnavailable as error:
                results.note(label, str(error))
                return None

        tool = self._tooling.tool
        results.record(
            lint_passed=attempt("clippy", "clippy", tool("clippy_passes"), root),
            pedantic_warnings=attempt("clippy", "clippy pedantic", tool("clippy_pedantic"), root),
            tests=attempt("tests", "cargo test", tool("cargo_test"), root),
            index=attempt("index", "rust-analyzer", tool("symbol_index"), root),
            build_seconds=attempt("build", "cargo build", tool("build_time"), root),
            probe_failures=attempt("probe", "message probe", tool("message_probe"), root, self._repository.tracked_paths()),
            unformatted=attempt("fmt", "cargo fmt", tool("unformatted_files"), root),
            unreachable_pub=attempt("clippy", "unreachable_pub lint", tool("unreachable_pub"), root),
        )
        results.record(second_tests=attempt("tests", "cargo test, second run", tool("cargo_test"), root))
        results.record(
            test_attempts=attempt("nextest", "cargo nextest", tool("test_attempts"), root, settings["flaky_test_retries"]),
            order_failures=attempt("shuffle", "shuffled tests", tool("order_failures"), root, tuple(settings["test_order_seeds"])),
        )
        lines = attempt("coverage", "cargo llvm-cov", tool("coverage"), root)
        if lines is not None:
            results.record(uncovered=lines[0], coverable=lines[1])
        if mutants_scope == "tree":
            results.record(mutants=attempt("mutants", "cargo mutants", tool("mutants"), root, None), mutants_whole_tree=True)
        elif base_sha:
            results.record(mutants=attempt("mutants", "cargo mutants", tool("mutants"), root, base_sha))
        else:
            results.note("cargo mutants", "needs a ref, or the setting mutants_scope set to tree")
        results.record(unsafe_in_dependencies=attempt("geiger", "cargo geiger", tool("unsafe_in_dependencies"), root, manifests or {}))
        if base_sha:
            results.record(semver_violations=attempt("semver", "cargo semver-checks", tool("semver_violations"), root, base_sha))
        else:
            results.note("cargo semver-checks", "needs a ref")
        if not base_sha:
            results.note("warnings added", "needs a ref")
        elif "clippy" in selected:
            results.record(base_warnings=self._base_warnings(base_sha, attempt, tool))
        return results

    def review_lines(self, head: Codebase, policy: Policy, fetch: bool, results: ToolResults, shallow: bool = False, sha: str | None = None) -> None:
        """Record the code lines no human reviewed, per file, or the reason they are not known.

        `git blame --first-parent` on the working tree, or on the commit `sha`, names the commit that last changed each line; the review
        data says which of those commits a listed human signed off (`smog.domain.reviews`). With `fetch` the data
        comes from GitHub for the commits the reviews file does not know. A commit the data does not know leaves
        the result unset: an unknown commit is not counted as unreviewed.

        A shallow clone leaves the result unset too, because its blame is wrong (`SHALLOW_CLONE`).
        """
        settings = policy.settings
        try:
            if not fetch and not settings["reviews_file"]:
                raise ToolUnavailable("no reviews file is set (`--reviews-file`) and the `reviews` tool did not run (`--full --tools reviews`)")
            if not policy.human_logins:
                raise ToolUnavailable("the policy lists no humans; call policy.humans with their GitHub logins")
            if shallow:
                raise ToolUnavailable(SHALLOW_CLONE)
            # Each blame is its own git process, so they run side by side.
            with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
                origins = dict(zip((file.path for file in head.files), pool.map(lambda file: self._repository.blame(sha, file.path, None), head.files)))
            # A file's review marker covers the commit it names and every commit before it.
            covered = {file.path: self._repository.ancestors(sha) for file in head.files if (sha := review_marker_commit(file, settings))}
            commits = {
                sha for file in head.files for line, sha in origins[file.path].items()
                if file.is_code_line(line) and sha not in covered.get(file.path, ())
            }  # fmt: skip
            data = self._tooling.tool("review_data")(self._repository.root, sorted(commits), fetch, settings)
            unknown = data.unknown(commits)
            if unknown:
                raise ToolUnavailable(
                    f"no review data for {len(unknown)} of the {len(commits)} commits that last changed a code line"
                )
            stale, reason = data.not_refreshed
            if stale:
                results.note(
                    "reviews, asked again",
                    f"{reason}. The saved verdict is used for {len(stale)} commits {_ASKED_AGAIN[settings['reviews_refetch']]} "
                    f"and could not be asked for again: {', '.join(sha[:10] for sha in stale)}",
                )
            reviewed = reviewed_commits(data, policy.human_logins, settings)
            results.record(
                unreviewed={file.path: unreviewed_lines(file, origins.get(file.path, {}), reviewed | covered.get(file.path, set()), settings) for file in head.files}
            )
        except ToolUnavailable as error:
            results.note("reviews", str(error))

    def _base_warnings(self, base_sha, attempt, tool):
        with tempfile.TemporaryDirectory() as folder:
            self._repository.export(base_sha, folder)
            return attempt("clippy", "clippy on the ref", tool("clippy_pedantic"), folder)

    def analyze(self, policy: Policy, full: bool = False, tools: tuple[str, ...] = ALL_TOOLS, policy_change=None, compare: bool = True) -> Report:
        """`policy_change` is the policy script compared with the ref (`PolicyChange`), when the run knows its script.
        Without `compare` the run ignores the policy's ref: nothing is compared, and the checks and conditions that
        need a ref do not run."""
        policy.validate()
        head = self.load_codebase(policy)
        shallow = self._repository.is_shallow()
        history = self.load_history(policy, shallow)
        slop = self.scan_slop(head, policy)
        base_sha = self._repository.merge_base(policy.ref) if compare and policy.ref else None
        manifests = {crate.name: f"{crate.directory}/Cargo.toml".lstrip("/") for crate in head.crates if crate.name != "(no crate)"}
        tool_results = self.run_tools(tools, base_sha, policy.settings["mutants_scope"], manifests, policy.settings) if full and self._tooling else None
        # Without listed humans no line is unreviewed, so a full run that does not name the tool has nothing to report.
        wants_reviews = self._tooling and (policy.settings["reviews_file"] or policy.human_logins or (full and "reviews" in tools))
        if tool_results is None and (wants_reviews or shallow):
            tool_results = ToolResults()
            tool_results.note(WITHOUT_FULL, "needs --full")
        if shallow:
            tool_results.note("git blame", SHALLOW_CLONE)
        if wants_reviews:
            self.review_lines(head, policy, full and "reviews" in tools, tool_results, shallow)
        rust_counts, doc_slop = _counted_slop(slop, policy)
        whole = build_scorecard(head, policy, history, tool_results, rust_counts, doc_slop)
        _name_slop(whole, slop, policy.settings)
        card, restriction = whole, None
        if policy.only_patterns:
            card = restrict_scorecard(whole, policy.only_patterns)
            restriction = (policy.only_patterns, len(card.pieces(PieceKind.FILE)), len(head.files))
        comparison = self._compare(policy, head, base_sha, history, rust_counts, doc_slop, whole, tool_results, full, shallow) if base_sha else None
        checks = self._checks(head, policy, comparison, slop, tool_results, policy_change)
        diff_values = comparison.measure(history, self._repository.now(), policy.layer_of) if comparison else {}
        if comparison and tool_results:
            diff_values.update(_tool_diff_values(tool_results, comparison))
        if tool_results:
            _apply_tool_checks(checks, tool_results, head)
        checks = {check_id: result for check_id, result in checks.items() if check_id not in policy.disabled}
        diff_values = {metric_id: value for metric_id, value in diff_values.items() if metric_id not in policy.disabled}
        unvalued, missing = selected_without_value(card, tool_results, bool(policy.human_logins))
        run = Run(card, comparison, history, checks, slop, tool_results, unvalued)
        # Without the data of a selected measurement every score is wrong, so no condition compares one.
        findings = [] if missing else [finding for condition in policy.conditions for finding in condition.evaluate(run)]
        return Report(card, findings, checks, slop, comparison, history, tool_results, diff_values, unvalued, missing, restriction, policy_change)

    def _compare(self, policy, head, base_sha, history, rust_counts, doc_slop, whole, tool_results, full, shallow) -> Comparison:
        """Both sides use name resolution, the same history and their own slop findings, so differences come from the code and the documents.

        Neither side uses slow tools. Both use review data when the run has it for the head and it can be had for the
        ref; otherwise neither does. When the run's own card was scored on that basis, it serves as the head side.
        """
        base_code = self.load_codebase(policy, base_sha)
        head_unreviewed = tool_results.unreviewed if tool_results else None
        base_tools = None
        if head_unreviewed is not None:
            base_tools = ToolResults()
            self.review_lines(base_code, policy, False, base_tools, shallow, base_sha)
            if base_tools.unreviewed is None:
                tool_results.note("reviews on the ref", f"the comparison with {policy.ref} leaves review data out on both sides: {base_tools.notes.get('reviews', '')}")
                base_tools = None
        base = build_scorecard(base_code, policy, history, base_tools, *_counted_slop(self.scan_slop(base_code, policy), policy))
        if not full and (head_unreviewed is None or base_tools is not None):
            same_basis_head = whole
        else:
            head_tools = None
            if base_tools is not None:
                head_tools = ToolResults()
                head_tools.record(unreviewed=head_unreviewed)
            same_basis_head = build_scorecard(head, policy, history, head_tools, rust_counts, doc_slop)
        changes = self._repository.diff_against(base_sha)
        return Comparison(policy.ref, base, same_basis_head, changes, self._repository.commit_sizes_since(base_sha), policy.settings, base_tools is not None)

    def _checks(self, head: Codebase, policy: Policy, comparison, slop, tool_results, policy_change=None) -> dict:
        checks = static_checks(head, FileGraph(head), policy)
        checks.update(diff_checks(comparison, policy, policy_change) if comparison else diff_checks_skipped())
        for check_id in ("check.tests_pass", "check.lints_pass", "check.tests_in_build"):
            checks.setdefault(check_id, CheckResult(check_id, [], ran=False, reason="needs --full"))
        return checks


def _tool_diff_values(tools: ToolResults, comparison: Comparison) -> dict[str, float]:
    values: dict[str, float] = {}
    added = tools.added_warnings()
    if added is not None:
        values["diff.warnings_added"] = added
    if tools.uncovered is not None:
        values["diff.uncovered_lines"] = sum(
            1 for change in comparison.changes for line, _ in change.added if line in tools.uncovered.get(change.path, ())
        )
    return values


def _apply_tool_checks(checks: dict, tools: ToolResults, head: Codebase) -> None:
    if tools.lint_passed is not None:
        failures = [] if tools.lint_passed else [("workspace", "cargo clippy with warnings denied failed")]
        checks["check.lints_pass"] = CheckResult("check.lints_pass", failures)
    if tools.tests is not None:
        failures = [(name, "test failed") for name in sorted(tools.tests.failed)]
        checks["check.tests_pass"] = CheckResult("check.tests_pass", failures)
        checks["check.tests_in_build"] = tests_in_build(head, tools.tests.listed)
