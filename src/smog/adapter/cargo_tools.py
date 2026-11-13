"""Clippy, cargo test, a clean build and the message-wording probe, each run through cargo."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

from smog.adapter.tree_sitter_parser import TreeSitterRustParser
from smog.domain.code import SourceFile, crate_folder, mark_test_modules
from smog.domain.tools import LintWarning, TestAttempt, TestReport
from smog.ports import ToolIncomplete, ToolUnavailable

_TEST_RESULT = re.compile(r"^test (.+?) \.\.\. (ok|FAILED|ignored)", re.M)
_TEST_LIST = re.compile(r"^(.+): test$", re.M)
_TEST_BINARY = re.compile(r"^\s*Running (?:unittests )?\S+ \(.*?([^/\\]+)-[0-9a-f]{16}\)\s*$")
_TEST_FAILED = re.compile(r"^test (.+?) \.\.\. FAILED")
_SEMVER_CRATE = re.compile(r"^\s*Checking (\S+) v", re.M)
_SEMVER_RESULT = re.compile(r"^\s*Checked \[[^\]]*\] \d+ checks: \d+ pass, (?:(\d+) fail, )?", re.M)
_COMPILE_ERROR = re.compile(r"E\d{4}")
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_PROSE = re.compile(r"[A-Za-z]+ [A-Za-z]+")


# What cargo prints when it needs a download and may not use the network (cargo 1.92, read 2026-11-11). A crate,
# file or test that is called `offline` is in cargo's output as well, so only these sentences count.
_OFFLINE_ERRORS = re.compile(
    r"attempting to make an HTTP request, but --offline was specified|you're using offline mode \(--offline\)|you are in the offline mode \(--offline\)"
)
# What cargo prints when it would have to change Cargo.lock and `--locked` forbids it.
_LOCKED_ERROR = "--locked was passed"

_settings = {"cargo_offline": True}


def use_settings(settings: dict) -> None:
    """Keep every cargo call of the tools off the network when the setting `cargo_offline` is true.

    Each tool process then runs with `CARGO_NET_OFFLINE`, cargo's own switch (the configuration value
    `net.offline`). Unlike `--offline` on a command line it also reaches the cargo calls a tool makes itself,
    such as the builds of cargo-mutants and cargo-semver-checks. The variable is set for the tool's process
    only (`tool_environment`), never in this one.
    """
    _settings["cargo_offline"] = settings["cargo_offline"]


def works_offline() -> bool:
    """True when the tools keep cargo off the network: by the setting (`use_settings`), or because this process was started that way."""
    return _settings["cargo_offline"] or os.environ.get("CARGO_NET_OFFLINE") == "true"


def tool_environment(extra: dict | None = None) -> dict:
    """The environment of a tool process: this process's, with cargo's offline switch when the tools stay offline."""
    return {**os.environ, **({"CARGO_NET_OFFLINE": "true"} if works_offline() else {}), **(extra or {})}


def locked(root: str, manifest: str = "Cargo.toml") -> list[str]:
    """`--locked` when a Cargo.lock exists beside the manifest or in a folder above it, up to the root: cargo
    then fails where it would rewrite the lock file. Without a lock file cargo has to write one, so the
    option is left out."""
    folder = (Path(root) / manifest).resolve().parent
    top = Path(root).resolve()
    while True:
        if (folder / "Cargo.lock").is_file():
            return ["--locked"]
        if folder == top or folder == folder.parent:
            return []
        folder = folder.parent


def first_error(output: str) -> str:
    """The first line of a tool's output that starts with `error`, with the indented lines that follow it; else
    the last line with text. At most 200 characters."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("error"):
            following = []
            for later in lines[index + 1 :]:
                if not later.startswith((" ", "\t")) or not later.strip():
                    break
                following.append(later.strip())
            return " ".join((line.strip(), *following))[:200]
    return next((line.strip() for line in reversed(lines) if line.strip()), "")[:200]


def failure_reason(output: str) -> str | None:
    """Why a failed cargo run is no result: it needed the network, or it would have had to change Cargo.lock. Else None."""
    if works_offline() and _OFFLINE_ERRORS.search(output):
        return f"cargo could not work offline: {first_error(output)}. Run `cargo fetch` first, or set the setting cargo_offline to False"
    if _LOCKED_ERROR in output:
        return f"cargo may not change Cargo.lock: {first_error(output)}. Update the lock file and commit it"
    return None


def _run(command: list[str], cwd: str, env: dict | None = None, unavailable_fails: bool = True) -> subprocess.CompletedProcess:
    """Run a tool. A cargo run that fails because it may not use the network or may not change Cargo.lock is no
    result: the tool did not run. With `unavailable_fails` off the caller judges that itself, for a tool that
    reports on several crates in one run."""
    if shutil.which(command[0]) is None:
        raise ToolUnavailable(f"{command[0]} is not installed")
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=tool_environment(env))
    reason = failure_reason(result.stderr) if unavailable_fails and result.returncode != 0 else None
    if reason:
        raise ToolUnavailable(reason)
    return result


def _tracked_lock_files(root: str) -> dict[Path, bytes]:
    listed = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", "Cargo.lock", "*/Cargo.lock"], capture_output=True)
    paths = [Path(root) / name for name in listed.stdout.decode().split("\0") if name]
    return {path: path.read_bytes() for path in paths if path.is_file()}


def _run_keeping_lock_files(command: list[str], root: str, **options) -> subprocess.CompletedProcess:
    """`_run` for a tool that takes no `--locked`. A tracked Cargo.lock the run changed is put back, and the tool did not run."""
    before = _tracked_lock_files(root)
    result = _run(command, root, **options)
    changed = [path for path, content in before.items() if not path.is_file() or path.read_bytes() != content]
    for path in changed:
        path.write_bytes(before[path])
    if changed:
        names = ", ".join(path.relative_to(root).as_posix() for path in changed)
        raise ToolUnavailable(f"{' '.join(command[:2])} cannot run with the lock file as it is: it changed {names}, which Smog put back. Update the lock file and commit it")
    return result


def clippy_passes(root: str) -> bool:
    return _run(["cargo", "clippy", "--workspace", "--all-targets", "--quiet", *locked(root), "--", "-D", "warnings"], root).returncode == 0


def parse_lint_warnings(output: str) -> list[LintWarning]:
    """The diagnostics with a lint name and a primary span in cargo's `--message-format=json` output.

    A diagnostic that cargo prints once per target, such as for the library and for its tests, counts once. A
    compile error (a code such as `E0308`) is no lint: the build stopped, so the list would be a part of the
    warnings, and the tool counts as not run.
    """
    warnings = {}
    for line in output.splitlines():
        if not line.startswith("{"):
            continue
        message = json.loads(line).get("message") or {}
        code = (message.get("code") or {}).get("code")
        spans = [span for span in message.get("spans", []) if span.get("is_primary")]
        if code and _COMPILE_ERROR.fullmatch(code):
            raise ToolUnavailable(f"the code does not compile: {code} {message.get('message', '')}".strip())
        if code and spans:
            text = message.get("message", "")
            warnings.setdefault((code, spans[0]["file_name"], spans[0]["line_start"], text), LintWarning(code, spans[0]["file_name"], spans[0]["line_start"], text))
    return list(warnings.values())


def _clippy_warnings(root: str, lint: str) -> list[LintWarning]:
    result = _run(["cargo", "clippy", "--workspace", "--message-format=json", *locked(root), "--", "-W", lint], root)
    warnings = parse_lint_warnings(result.stdout)
    if result.returncode != 0 and not warnings:
        raise ToolUnavailable(f"cargo clippy failed: {first_error(result.stderr)}")
    return warnings


def clippy_pedantic(root: str) -> list[LintWarning]:
    return _clippy_warnings(root, "clippy::pedantic")


def unreachable_pub(root: str) -> list[LintWarning]:
    """rustc's `unreachable_pub` warnings in the library and binary targets of the workspace's own crates.

    Runs `cargo clippy --workspace --message-format=json -- -W unreachable_pub` and keeps the diagnostics of that
    lint. Clippy is used because it hands the flags after `--` to the workspace's crates only; `RUSTFLAGS` would
    rebuild every dependency. Test targets are not built, so `pub` items in test code are not reported. Paths are
    relative to the workspace root, which must be the repository root.
    """
    return [warning for warning in _clippy_warnings(root, "unreachable_pub") if warning.lint == "unreachable_pub"]


def parse_format_listing(output: str, root: str) -> set[str]:
    """Paths of the files `cargo fmt -- --check -l` lists, relative to the repository root. Files outside it are dropped."""
    prefix = str(Path(root).resolve()) + "/"
    return {line.strip().removeprefix(prefix) for line in output.splitlines() if line.strip().startswith(prefix)}


def unformatted_files(root: str) -> set[str]:
    """Files rustfmt would change, with the repository's own rustfmt configuration.

    Runs `cargo fmt --all -- --check -l`. rustfmt's README (read 2026-11-10): `-l` "prints the names of files that
    would be formatted when used with `--check` mode", and rustfmt exits "with `0` if Rustfmt would not make any
    formatting changes to the input, and `1` if Rustfmt would make changes". Any other exit status counts as not run.
    """
    result = _run_keeping_lock_files(["cargo", "fmt", "--all", "--", "--check", "-l"], root)
    if result.returncode not in (0, 1):
        raise ToolUnavailable(f"cargo fmt failed: {first_error(result.stderr)}")
    return parse_format_listing(result.stdout, root)


def cargo_test(root: str) -> TestReport:
    started = time.monotonic()
    result = _run(["cargo", "test", "--workspace", "--no-fail-fast", *locked(root)], root)
    seconds = time.monotonic() - started
    outcomes = _TEST_RESULT.findall(result.stdout)
    if result.returncode != 0 and not outcomes:
        raise ToolUnavailable(f"cargo test could not build: {first_error(result.stderr)}")
    listing = _run(["cargo", "test", "--workspace", *locked(root), "--", "--list"], root)
    failed = {name for name, outcome in outcomes if outcome == "FAILED"}
    return TestReport(failed, set(_TEST_LIST.findall(listing.stdout)), seconds)


def parse_junit(text: str) -> dict[tuple[str, str], TestAttempt]:
    """Per test, the result in the JUnit report of cargo-nextest.

    nextest writes one `testsuite` per test binary, named by its binary ID (`my-crate` for the unit tests of the
    library, `my-crate::api` for `tests/api.rs`, `my-crate::bin/tool` for a binary), and one `testcase` per test
    with its path as `name` and the seconds of its last attempt as `time`. "Flaky tests are marked with
    `<flakyFailure>` or `<flakyError>` tags", and tests that failed every attempt have `<failure>` or `<error>`
    (nexte.st/docs/features/retries, read 2026-11-10). The key is (binary, test path); the binary is the last
    part of the binary ID without `bin/` and with `-` as `_`, which is the name libtest binaries have on disk.
    Two binaries of a workspace can share that name and hold a test of the same path. They then share one
    entry: flaky or failed when either is, with the longer time.
    """
    attempts = {}
    for suite in ElementTree.fromstring(text).iter("testsuite"):
        binary = suite.get("name", "").rsplit("::", 1)[-1].removeprefix("bin/").replace("-", "_")
        for case in suite.iter("testcase"):
            flaky = case.find("flakyFailure") is not None or case.find("flakyError") is not None
            failed = case.find("failure") is not None or case.find("error") is not None
            key, seconds = (binary, case.get("name", "")), float(case.get("time", 0))
            same = attempts.get(key)
            if same:
                seconds, flaky, failed = max(seconds, same.seconds), flaky or same.flaky, failed or same.failed
            attempts[key] = TestAttempt(seconds, flaky, failed)
    return attempts


def test_attempts(root: str, retries: int) -> dict[tuple[str, str], TestAttempt]:
    """Every test of the workspace under `cargo nextest run --workspace --no-fail-fast --retries <retries>`.

    "If a test succeeds during a retry, the test is marked flaky", and "`--retries 2` means that the test is
    retried twice, for a total of three attempts" (nexte.st/docs/features/retries, read 2026-11-10). The JUnit
    report is written to a temporary folder through a tool configuration file, which the repository's own
    nextest configuration overrides. The result is not deterministic: it depends on timing and on what else
    the machine does.
    """
    if shutil.which("cargo-nextest") is None:
        raise ToolUnavailable("cargo-nextest is not installed")
    with tempfile.TemporaryDirectory() as folder:
        report, config = Path(folder) / "junit.xml", Path(folder) / "nextest.toml"
        config.write_text(f'[profile.default.junit]\npath = "{report.as_posix()}"\n')
        command = ["cargo", "nextest", "run", "--workspace", "--no-fail-fast", "--retries", str(retries), "--tool-config-file", f"smog:{config}", *locked(root)]
        result = _run(command, root)
        if not report.exists():
            raise ToolUnavailable(f"cargo nextest wrote no report: {first_error(result.stderr)}")
        return parse_junit(report.read_text())


test_attempts.__test__ = False


def parse_test_failures(output: str) -> set[tuple[str, str]]:
    """The failed tests in the merged output of `cargo test`, as (binary, test path).

    cargo prints `Running unittests src/lib.rs (target/debug/deps/my_crate-0123456789abcdef)` before the output
    of each test binary; the binary is the file name without its hash. libtest prints `test <path> ... FAILED`.
    """
    failed = set()
    binary = ""
    for line in output.splitlines():
        running, test = _TEST_BINARY.match(line), _TEST_FAILED.match(line)
        if running:
            binary = running.group(1)
        elif test:
            failed.add((binary, test.group(1)))
    return failed


def order_failures(root: str, seeds: tuple[int, ...]) -> list[set[tuple[str, str]]]:
    """The failed tests of the workspace in the default order and in one shuffled order per seed, each on one thread.

    Runs `cargo +nightly test --workspace --no-fail-fast --lib --bins --tests -- -Z unstable-options
    --shuffle-seed <seed> --test-threads 1`, and the same without the shuffle first. libtest (rustc book,
    "Tests", read 2026-11-10): `--shuffle` "runs the tests in random order, as opposed to the default
    alphabetical order", "calling the test harness with `--shuffle-seed` SEED twice runs the tests in the same
    order both times", and "this option is unstable, and requires the `-Z unstable-options` flag". It therefore
    needs a nightly toolchain. Doc tests are left out. The builds go to a temporary target folder. A test that
    is flaky for another reason can differ between the runs as well, so the result is not deterministic.
    """
    if _run(["cargo", "+nightly", "--version"], root).returncode != 0:
        raise ToolUnavailable("no nightly toolchain: libtest's --shuffle-seed is unstable")
    runs = []
    with tempfile.TemporaryDirectory() as target:
        base = ["cargo", "+nightly", "test", "--workspace", "--no-fail-fast", "--lib", "--bins", "--tests", "--target-dir", target, *locked(root), "--"]
        for arguments in ([], *(["-Z", "unstable-options", "--shuffle-seed", str(seed)] for seed in seeds)):
            command = [*base, *arguments, "--test-threads", "1"]
            result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=tool_environment())
            if "Running " not in result.stdout:
                raise ToolUnavailable(failure_reason(result.stdout) or f"cargo +nightly test could not build: {first_error(result.stdout)}")
            runs.append(parse_test_failures(result.stdout))
    return runs


def build_time(root: str) -> float:
    """Clean build in a temporary target folder, so the repository's own target folder stays as it is."""
    with tempfile.TemporaryDirectory() as target:
        started = time.monotonic()
        result = _run(["cargo", "build", "--workspace", "--quiet", "--target-dir", target, *locked(root)], root)
        seconds = time.monotonic() - started
    if result.returncode != 0:
        raise ToolUnavailable(f"cargo build failed: {first_error(result.stderr)}")
    return seconds


def _rewrite_message(literal: str) -> str:
    """Change every letter run outside placeholders, so the wording differs and the format arguments still match."""
    pieces = []
    last = 0
    for match in _PLACEHOLDER.finditer(literal):
        pieces.append(re.sub(r"[A-Za-z]+", "probe", literal[last : match.start()]))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(re.sub(r"[A-Za-z]+", "probe", literal[last:]))
    return "".join(pieces)


def _probe_source(file: SourceFile) -> bytes:
    source = file.source
    if file.is_test:
        return source
    test_spans = [(f.node.start_byte, f.node.end_byte) for f in file.functions if f.in_test_code]
    rewritten = source
    literals = sorted(file.root.find("string_literal"), key=lambda node: node.start_byte, reverse=True)
    for literal in literals:
        text = literal.text
        inside_test = any(start <= literal.start_byte < end for start, end in test_spans)
        if inside_test or not _PROSE.search(text):
            continue
        rewritten = rewritten[: literal.start_byte] + _rewrite_message(text).encode() + rewritten[literal.end_byte :]
    return rewritten


def message_probe(root: str, tracked_paths: list[str]) -> set[str]:
    """Rewrite prose strings in production code in a temporary copy. A test that newly fails is a candidate pin."""
    baseline = cargo_test(root).failed
    parser = TreeSitterRustParser()
    files = {}
    for path in tracked_paths:
        if path.endswith(".rs"):
            source = (Path(root) / path).read_bytes()
            files[path] = SourceFile(path, source, parser.parse(source), "", crate_folder(path, tracked_paths))
    mark_test_modules(files.values(), files.values())
    with tempfile.TemporaryDirectory() as folder:
        for path in tracked_paths:
            copy = Path(folder) / path
            copy.parent.mkdir(parents=True, exist_ok=True)
            if path in files:
                copy.write_bytes(_probe_source(files[path]))
            else:
                shutil.copy2(Path(root) / path, copy)
        return cargo_test(folder).failed - baseline


def parse_geiger_report(output: str, workspace: set[str]) -> int | None:
    """Unsafe items in the used code of the dependencies in a cargo-geiger JSON report, or None without a report.

    The report lists one entry per package with `unsafety.used`, "unsafe usage statistics for code used by the
    project", split into `functions`, `exprs`, `item_impls`, `item_traits` and `methods`, each with a `safe` and
    an `unsafe_` count (cargo-geiger-serde/src/report.rs, read 2026-11-10). The result is the sum of the five
    `unsafe_` counts over every package that is no workspace crate. Code the build does not use (`unused`) is
    left out.
    """
    line = next((line for line in output.splitlines() if line.startswith("{")), None)
    if line is None:
        return None
    total = 0
    for entry in json.loads(line).get("packages", []):
        if entry["package"]["id"]["name"] not in workspace:
            total += sum(count["unsafe_"] for count in entry["unsafety"]["used"].values())
    return total


def unsafe_in_dependencies(root: str, manifests: dict[str, str]) -> dict[str, int]:
    """Per crate, the unsafe items in the dependencies cargo-geiger scans from that crate.

    Runs `cargo geiger --output-format Json --manifest-path <Cargo.toml>` once per crate, because cargo-geiger
    reports on one root package. `manifests` maps a crate name to its Cargo.toml, relative to the repository
    root; cargo-geiger 0.13.0 refuses a relative path, so the path is made absolute. The report is one JSON line on stdout; cargo's build
    output goes to stderr. With the setting `cargo_offline` the dependency sources must already be in cargo's
    cache (`use_settings`). A crate whose lock file would have to change has no report (`locked`).

    Raises ToolIncomplete with the counts of the other crates when the run of some crates prints no report, and
    ToolUnavailable when none does. Checked against cargo-geiger 0.13.0 on a workspace of 18 crates, 2026-11-11.
    """
    if shutil.which("cargo-geiger") is None:
        raise ToolUnavailable("cargo-geiger is not installed")
    counts, failed, reason = {}, [], ""
    for name, manifest in manifests.items():
        command = ["cargo", "geiger", "--output-format", "Json", "--manifest-path", str(Path(root).resolve() / manifest), *locked(root, manifest)]
        result = _run(command, root, unavailable_fails=False)
        count = parse_geiger_report(result.stdout, set(manifests))
        if count is None:
            failed.append(name)
            reason = reason or failure_reason(result.stderr) or first_error(result.stderr)
        else:
            counts[name] = count
    if failed and not counts:
        raise ToolUnavailable(f"cargo geiger printed no report: {reason}")
    if failed:
        raise ToolIncomplete(f"no report for {len(failed)} of {len(manifests)} crates ({', '.join(sorted(failed))}): {reason}", counts)
    return counts


def parse_semver_report(output: str) -> dict[str, int]:
    """Failed checks per crate, from the status lines of cargo-semver-checks.

    The tool prints to stderr `Checking <crate> v<old> -> v<new> (...)` and then `Checked [<time>] <n> checks:
    <p> pass, <f> fail, <w> warn, <s> skip`, or `<n> checks: <p> pass, <s> skip` when nothing failed
    (src/check_release.rs, read 2026-11-10; the output of cargo-semver-checks 0.51.0, 2026-11-11). A crate with
    no `Checked` line after it has no entry.
    """
    counts = {}
    crates = list(_SEMVER_CRATE.finditer(output))
    for index, crate in enumerate(crates):
        end = crates[index + 1].start() if index + 1 < len(crates) else len(output)
        result = _SEMVER_RESULT.search(output, crate.end(), end)
        if result:
            counts[crate.group(1)] = int(result.group(1) or 0)
    return counts


def semver_violations(root: str, base_sha: str) -> dict[str, int]:
    """Per crate, the semver checks that fail between a commit and the working tree.

    Runs `cargo semver-checks --workspace --baseline-rev <commit>`: each crate is compared with itself at that
    commit, and a check fails when the API changed in a way the change of its version number does not allow.
    The tool builds rustdoc JSON for both sides, with every feature it does not take for unstable, so the code
    must build at both commits and the optional dependencies must be in cargo's cache when `cargo_offline` is
    on. It prints its status lines to stderr and reports on the library crates it can check. Exit status 100
    means violations were found; any other status but 0 means it could not check at least one crate, and it
    still prints the result of the others.

    Raises ToolIncomplete with the counts of the crates it checked when it fails for some, and ToolUnavailable
    when it reports on none. Checked against cargo-semver-checks 0.51.0 on a workspace of 18 crates, 2026-11-11.
    """
    if shutil.which("cargo-semver-checks") is None:
        raise ToolUnavailable("cargo-semver-checks is not installed")
    result = _run_keeping_lock_files(["cargo", "semver-checks", "--workspace", "--baseline-rev", base_sha], root, unavailable_fails=False)
    counts = parse_semver_report(result.stdout + "\n" + result.stderr)
    if result.returncode in (0, 100):
        return counts
    reason = failure_reason(result.stderr) or first_error(result.stderr)
    if not counts:
        raise ToolUnavailable(f"cargo semver-checks failed: {reason}")
    raise ToolIncomplete(f"reported on {len(counts)} crates and then failed: {reason}", counts)
