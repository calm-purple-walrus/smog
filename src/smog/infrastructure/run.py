"""Entry point for a policy script: `from smog import Policy, run`."""

import argparse
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from smog.adapter.cargo_manifests import CargoManifests
from smog.adapter.cargo_tools import (
    build_time,
    cargo_test,
    clippy_passes,
    clippy_pedantic,
    message_probe,
    order_failures,
    semver_violations,
    test_attempts,
    unformatted_files,
    unreachable_pub,
    unsafe_in_dependencies,
    use_settings,
)
from smog.adapter.console import LEVELS, metric_data, render, render_explanation, render_explanation_list, render_metric, report_data
from smog.adapter.coverage import coverage
from smog.adapter.git_repository import GitRepository
from smog.adapter.github_reviews import review_data
from smog.adapter.mutants import mutants
from smog.adapter.rust_analyzer import symbol_index
from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.application.analyze import ALL_TOOLS, NETWORK_TOOLS, Analyzer
from smog.domain.explain import closest_ids, explain, explain_all
from smog.domain.measure import NoFileMatches
from smog.domain.policy import Policy, PolicyChange, policy_differences
from smog.domain.report import Report
from smog.ports import Tooling


def build_analyzer(root: str) -> Analyzer:
    tooling = Tooling(
        clippy_passes=clippy_passes, clippy_pedantic=clippy_pedantic, cargo_test=cargo_test, coverage=coverage, mutants=mutants,
        symbol_index=symbol_index, build_time=build_time, message_probe=message_probe, unformatted_files=unformatted_files,
        unreachable_pub=unreachable_pub, unsafe_in_dependencies=unsafe_in_dependencies, semver_violations=semver_violations,
        test_attempts=test_attempts, order_failures=order_failures, review_data=review_data, prepare=use_settings,
    )  # fmt: skip
    return Analyzer(GitRepository(root), TreeSitterRustParser(), CargoManifests(), tooling)


_DESCRIBE_POLICY = """
import json, runpy, sys
import smog

def describe(policy, **_):
    print(chr(0) + json.dumps(policy.describe()))
    raise SystemExit(0)

smog.run = describe
sys.path.insert(0, sys.argv[2])
sys.argv = sys.argv[1:2]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def _policy_at_ref(source: bytes, script: Path) -> dict:
    """The description (`Policy.describe`) of the policy a script built at another commit. Raises ValueError if it cannot be loaded.

    The source runs in a process of its own with `run` replaced, so it measures nothing. It runs from a
    temporary file, with the folder of the script as it is now on the import path: a module it imports from
    there is the one of the working tree.
    """
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / script.name
        copy.write_bytes(source)
        environment = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(Path(__file__).parents[2]), os.environ.get("PYTHONPATH"))))}
        result = subprocess.run([sys.executable, "-c", _DESCRIBE_POLICY, str(copy), str(script.parent)], capture_output=True, text=True, env=environment)
    _, marker, description = result.stdout.rpartition(chr(0))
    if result.returncode != 0 or not marker:
        raise ValueError((result.stderr.strip().splitlines() or ["it did not call run(policy)"])[-1])
    return json.loads(description)


def policy_change(policy: Policy, root: str, script: str) -> PolicyChange | None:
    """The policy script of this run compared with the same file at the merge base of the policy's ref and HEAD.

    `script` is the path of the script, from the repository root or absolute. None without a ref, and for a
    script outside the repository, which no commit holds. When the script differs, the policy of the ref is
    loaded (`_policy_at_ref`) for its gate files and for what it enforces differently.
    """
    repository = GitRepository(root)
    path = Path(repository.root, script).resolve()
    if policy.ref is None or not path.is_relative_to(repository.root):
        return None
    name = path.relative_to(repository.root).as_posix()
    now = json.loads(json.dumps(policy.describe()))
    before = repository.read_files([name], repository.merge_base(policy.ref)).get(name)
    fallback = "so the gate files are those this policy names now"
    if before is None:
        return PolicyChange(name, policy.ref, False, [], policy.gate_patterns, f"is not in {policy.ref}, {fallback}")
    if path.is_file() and before == path.read_bytes():
        return PolicyChange(name, policy.ref, False, [], policy.gate_patterns)
    try:
        at_ref = _policy_at_ref(before, path)
    except ValueError as error:
        return PolicyChange(name, policy.ref, True, [], policy.gate_patterns, f"The policy of {policy.ref} could not be loaded ({error}), {fallback}")
    return PolicyChange(name, policy.ref, True, policy_differences(at_ref, now), at_ref["gate files"])


def analyze(policy: Policy, root: str, full: bool = False, tools: tuple[str, ...] = ALL_TOOLS, policy_script: str | None = None, compare: bool = True) -> Report:
    """Analyze the repository at `root`. With `policy_script`, the path of the script that built the policy,
    and a ref, the script is compared with the ref (`policy_change`)."""
    change = policy_change(policy, root, policy_script) if policy_script else None
    return build_analyzer(root).analyze(policy, full, tools, change, compare)


def _repository_of(path: Path) -> str:
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()


def _explain(policy: Policy, wanted: str, as_json: bool) -> int:
    """Print the explanation of one ID, or of all with an empty `wanted`, and return the exit code."""
    if not wanted:
        entries = explain_all(policy)
        print(json.dumps(entries, indent=2) if as_json else render_explanation_list(entries))
        return 0
    entry = explain(policy, wanted)
    if entry is not None:
        print(json.dumps(entry, indent=2) if as_json else render_explanation(entry))
        return 0
    closest = closest_ids(policy, wanted)
    if as_json:
        print(json.dumps({"error": "unknown id", "id": wanted, "closest": closest}, indent=2))
    else:
        print(f"Unknown policy ID {wanted}. Closest: {', '.join(closest) or 'none'}. --explain with no ID lists every ID.", file=sys.stderr)
    return 2


def run(policy: Policy, *, root: str | None = None, argv: list[str] | None = None) -> None:
    """Parse the command line, analyze the repository, print the overview, and exit nonzero if anything blocks.

    `root` defaults to the git repository that holds the calling script.
    """
    parser = argparse.ArgumentParser(description="Smog overview")
    parser.add_argument("--level", choices=list(LEVELS), default="crate", help="coarseness of the score listing")
    parser.add_argument("--full", action="store_true", help="also run the slow tools")
    parser.add_argument(
        "--tools",
        default=",".join(ALL_TOOLS),
        help=f"with --full, which tools to run, separated by commas. The default is all of {','.join(ALL_TOOLS)}. Not in the default, because they use the network: {','.join(NETWORK_TOOLS)}",
    )
    parser.add_argument("--reviews-file", metavar="PATH", help="JSON file with pull requests and reviews. Overrides the setting reviews_file")
    parser.add_argument("--mutants", choices=["diff", "tree"], help="with --full, mutate the diff against the ref or the whole codebase. Overrides the setting mutants_scope")
    parser.add_argument("--comprehensive", action="store_true", help="list every piece, failure, slop hit and metric")
    parser.add_argument("--files-by-crate", action="store_true", help="list every crate with every file of it, worst first, with each file's score and main problem")
    parser.add_argument("--failures", nargs="?", const="all", metavar="CHECK", help="list only what failed, in every check or in the named one")
    parser.add_argument("--root", default=root, help="repository to analyze")
    parser.add_argument("--only", action="append", default=[], metavar="PATTERN", help="report and score only the files whose path, folder or crate name matches this glob. Can be repeated")
    parser.add_argument("--explain", nargs="?", const="", metavar="ID", help="say what a policy ID means and what to do about it, or list every ID. Does not analyze the repository")
    parser.add_argument("--metric", metavar="ID", help="print one metric's value and score for each piece, worst first")
    parser.add_argument("--json", action="store_true", help="with --explain or --metric, print JSON")
    parser.add_argument(
        "--changes",
        nargs="?",
        const="",
        metavar="REF",
        help="also compare with REF (default the policy's ref, else main): the checks on the diff and the functions made worse. Without it, the run measures the code as it is",
    )
    parser.add_argument(
        "--report",
        choices=("both", "text", "json", "none"),
        default="both",
        help="which full report files to write to the setting report_folder: report.txt, report.json, both or none",
    )
    args = parser.parse_args(argv)
    unknown_tools = sorted(set(args.tools.split(",")) - {*ALL_TOOLS, *NETWORK_TOOLS})
    if unknown_tools:
        parser.error(f"unknown tool {', '.join(unknown_tools)} in --tools; the tools are {','.join((*ALL_TOOLS, *NETWORK_TOOLS))}")
    if args.json and args.explain is None and args.metric is None:
        parser.error("--json needs --explain or --metric")
    if args.explain is not None:
        sys.exit(_explain(policy, args.explain, args.json))
    if args.metric is not None and args.metric not in policy.specs:
        print(f"Unknown metric {args.metric}. Closest: {', '.join(closest_ids(policy, args.metric)) or 'none'}.", file=sys.stderr)
        sys.exit(2)
    if args.metric is not None and args.metric in policy.disabled:
        print(f"{args.metric} is disabled by this policy (policy.disable), so it has no values.", file=sys.stderr)
        sys.exit(2)
    if args.metric is not None and args.metric.startswith("check."):
        print(f"{args.metric} is a check with no value. Use --failures {args.metric}.", file=sys.stderr)
        sys.exit(2)
    if args.failures not in (None, "all"):
        check_id = args.failures if args.failures.startswith("check.") else f"check.{args.failures}"
        if check_id not in policy.specs:
            checks = [found for found in closest_ids(policy, check_id) if found.startswith("check.")]
            print(f"Unknown check {args.failures}. Closest: {', '.join(checks) or 'none'}.", file=sys.stderr)
            sys.exit(2)
    if args.mutants:
        policy.setting("mutants_scope", args.mutants)
    policy.only(*args.only)
    if args.reviews_file:
        policy.setting("reviews_file", str(Path(args.reviews_file).resolve()))
    if args.changes is not None and policy.ref is None:
        policy.against(args.changes or "main")
    elif args.changes:
        policy.against(args.changes)
    caller = Path(inspect.stack()[1].filename).resolve()
    repository = args.root or _repository_of(caller.parent)
    try:
        report = analyze(policy, repository, args.full, tuple(args.tools.split(",")), str(caller), compare=args.changes is not None)
    except NoFileMatches as error:
        print(f"{error}. The patterns are matched against file paths, folders and crate names.", file=sys.stderr)
        sys.exit(2)
    result = {0: "passes", 1: "blocked", 2: "no score"}[report.exit_code]
    written = [str(Path(path).relative_to(Path(repository).resolve())) for path in _write_report(report, Path(repository).resolve() / policy.settings["report_folder"], args.report, args.level)]
    if args.metric is not None and args.json:
        print(json.dumps({**metric_data(report, args.metric), "result": result}, indent=2))
        sys.exit(report.exit_code)
    if args.metric is not None:
        print(render_metric(report, metric_data(report, args.metric)))
    else:
        print(render(report, args.level, args.comprehensive, args.failures, args.files_by_crate))
    if written:
        print(f"Full report: {', '.join(written)}")
    print(f"\n{'✅' if report.exit_code == 0 else '❌'} Result: {result}.")
    sys.exit(report.exit_code)


def _write_report(report, folder: Path, which: str, level: str) -> list[str]:
    """Write the full report as text and as JSON, as `which` says, and return the paths written."""
    if which == "none":
        return []
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    if which in ("both", "text"):
        (folder / "report.txt").write_text(render(report, "function", comprehensive=True) + "\n")
        written.append(str(folder / "report.txt"))
    if which in ("both", "json"):
        (folder / "report.json").write_text(json.dumps(report_data(report), indent=1, default=str) + "\n")
        written.append(str(folder / "report.json"))
    return written
