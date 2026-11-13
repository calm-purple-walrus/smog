"""Pass/fail checks (design section 3.1). A check never feeds the score."""

import fnmatch

from smog.domain.code import Codebase
from smog.domain.graph import FileGraph, crate_graph, strongly_connected
from smog.domain.lenses.crate_dependencies import unused_dependency_names
from smog.domain.policy import Policy
from smog.domain.registry import DIFF_CHECKS
from smog.domain.settings import DEFAULT_SETTINGS


class CheckResult:
    def __init__(self, check_id: str, failures: list[tuple[str, str]], ran: bool = True, reason: str = ""):
        self._check_id = check_id
        self._failures = failures
        self._ran = ran
        self._reason = reason

    @property
    def check_id(self) -> str:
        return self._check_id

    @property
    def failures(self) -> list[tuple[str, str]]:
        """(where, what) per failure."""
        return self._failures

    @property
    def ran(self) -> bool:
        return self._ran

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def passed(self) -> bool:
        return self._ran and not self._failures


def _skipped(check_id: str, reason: str) -> CheckResult:
    return CheckResult(check_id, [], ran=False, reason=reason)


def layer_violations(codebase: Codebase, graph: FileGraph, policy: Policy) -> CheckResult:
    """Dependencies the policy's dependency rules do not allow. `Policy.dependency_rule` states how a rule is matched."""
    check_id = "check.layer_violations"
    if not policy.dependency_rules:
        return _skipped(check_id, "no dependency rule in the policy")
    failures = []
    # The names a pattern can match a crate by. A file of another crate is matched by its path and by these names of its crate.
    crates = {crate.name: (crate.name, crate.directory, f"{crate.directory}/Cargo.toml".lstrip("/")) for crate in codebase.crates}
    for source, targets in crate_graph(codebase).items():
        for target in sorted(targets):
            rule = policy.deciding_rule(crates[source], crates[target])
            if rule is None:
                failures.append((source, f"depends on crate {target}, which no rule allows"))
            elif not rule.allow:
                failures.append((source, f"depends on crate {target}, forbidden by {rule.describe()}"))
    crate_of = {file.path: file.crate_name for file in codebase.files}
    for source, targets in graph.edges.items():
        for target in sorted(targets):
            same_crate = crate_of[source] == crate_of[target]
            rule = policy.deciding_rule((source,) if same_crate else (source, *crates[crate_of[source]]), (target,) if same_crate else (target, *crates[crate_of[target]]))
            if rule is None and not same_crate:
                failures.append((source, f"uses file {target} of crate {crate_of[target]}, which no rule allows"))
            elif rule is not None and not rule.allow:
                failures.append((source, f"uses file {target}, forbidden by {rule.describe()}"))
    return CheckResult(check_id, failures)


def dependency_cycles(codebase: Codebase, graph: FileGraph, named: int = DEFAULT_SETTINGS["display_cycle_members"]) -> CheckResult:
    """One failure per cycle of crates or files, which names its first `named` members in alphabetical order."""
    failures = []
    for label, edges in (("crate", crate_graph(codebase)), ("file", graph.edges)):
        for component in strongly_connected(edges):
            if len(component) > 1:
                failures.append((sorted(component)[0], f"{label} cycle of {len(component)}: {', '.join(sorted(component)[:named])}"))
    return CheckResult("check.dependency_cycles", failures)


def no_type_bounds(codebase: Codebase, traits: tuple = DEFAULT_SETTINGS["type_bound_traits"]) -> CheckResult:
    failures = []
    for type_def in codebase.types:
        named = set(traits) & set(type_def.generic_bounds)
        if named:
            failures.append((type_def.qualified, f"bounds on the definition: {', '.join(sorted(named))}"))
    return CheckResult("check.no_type_bounds", failures)


def unused_dependencies(codebase: Codebase, policy: Policy) -> CheckResult:
    failures = [
        (crate.name, f"{name} is declared and its name never appears in source")
        for crate in codebase.crates
        for name in unused_dependency_names(crate, policy.dependency_ignores)
    ]
    return CheckResult("check.unused_dependencies", failures)


def catch_all_names(codebase: Codebase, names: tuple = DEFAULT_SETTINGS["catch_all_names"]) -> CheckResult:
    failures = []
    for module in codebase.modules:
        if module.path and module.path[-1] in names:
            failures.append((module.qualified, f"catch-all module name {module.path[-1]}"))
    for path in codebase.tracked_paths:
        if path.endswith(".rs"):
            for segment in path.removesuffix(".rs").split("/"):
                if segment in names:
                    failures.append((path, f"catch-all name {segment}"))
    return CheckResult("check.catch_all_names", failures)


def module_path_overrides(codebase: Codebase) -> CheckResult:
    """One failure per `#[path = ...]` attribute, inner or outer, and per `include!` call whose arguments hold a string
    ending in `.rs`, in every Rust file of the codebase, test code included. Either puts a file's code into a module
    other than the one its path names, which Smog assumes for file modules."""
    failures = []
    for file in codebase.files:
        for node in file.root.walk():
            if node.kind == "attribute" and [child.text for child in node.children[:2]] == ["path", "="]:
                failures.append((f"{file.path}:{node.start_line}", "`#[path]` attribute"))
            elif (
                node.kind == "macro_invocation"
                and node.child("macro").text.rsplit("::", 1)[-1] == "include"
                and any(content.text.endswith(".rs") for content in node.find("string_content"))
            ):
                failures.append((f"{file.path}:{node.start_line}", "`include!` of a Rust file"))
    return CheckResult("check.module_path_overrides", failures)


def project_conventions(policy: Policy) -> CheckResult:
    return _skipped("check.project_conventions", f"{len(policy.conditions)} conditions in the policy report on their own")


def static_checks(codebase: Codebase, graph: FileGraph, policy: Policy) -> dict[str, CheckResult]:
    results = [
        layer_violations(codebase, graph, policy),
        dependency_cycles(codebase, graph, policy.settings["display_cycle_members"]),
        no_type_bounds(codebase, policy.settings["type_bound_traits"]),
        unused_dependencies(codebase, policy),
        catch_all_names(codebase, policy.settings["catch_all_names"]),
        module_path_overrides(codebase),
        project_conventions(policy),
    ]
    return {result.check_id: result for result in results}


def diff_checks(comparison, policy: Policy, policy_change=None) -> dict[str, CheckResult]:
    """The checks that read the diff against the ref. With a `PolicyChange`, check.gate_untouched fails for a
    policy script that differs from the ref and takes the gate files from it."""
    lines_limit, files_limit = policy.pr_limits
    lines = sum(change.line_count for change in comparison.changes)
    files = len(comparison.changes)
    size = []
    if lines > lines_limit:
        size.append(("diff", f"{lines} lines changed, limit {lines_limit}"))
    if files > files_limit:
        size.append(("diff", f"{files} files touched, limit {files_limit}"))
    script = policy_change.path if policy_change and policy_change.changed else None
    patterns = policy_change.gate_patterns if policy_change else policy.gate_patterns
    gate = [(script, f"the policy script differs from {policy_change.ref}")] if script else []
    gate += [(path, "gate file changed") for path in sorted(comparison.changed_paths()) if path != script and any(fnmatch.fnmatch(path, p) for p in patterns)]
    suppressed = [(f"{path}:{line}", text) for path, line, text in comparison.suppressions_added(policy.suppression_patterns)]
    weakened = comparison.weakened_tests()
    tiers = [(key, f"assertion tier fell from {before} to {after}") for key, before, after in comparison.weakened_assertions()]
    results = [
        CheckResult("check.new_suppressions", suppressed),
        CheckResult("check.gate_untouched", gate),
        CheckResult("check.tests_not_weakened", weakened),
        CheckResult("check.assertion_strength", tiers),
        CheckResult("check.pr_size", size),
    ]
    return {result.check_id: result for result in results}


def diff_checks_skipped() -> dict[str, CheckResult]:
    return {check_id: _skipped(check_id, "runs only when comparing, with --changes") for check_id in DIFF_CHECKS}


def tests_in_build(codebase: Codebase, listed: set[str]) -> CheckResult:
    """Test names found in syntax must appear in the runner's list. Any path segment counts, because a parametrized
    test such as `#[rstest]` is listed as `module::name::case_1`."""
    names = {segment for entry in listed for segment in entry.split("::")}
    failures = [
        (function.qualified, "test is in the source and not in the runner's list")
        for function in codebase.functions
        if function.is_test_case and function.name not in names
    ]
    return CheckResult("check.tests_in_build", failures)
