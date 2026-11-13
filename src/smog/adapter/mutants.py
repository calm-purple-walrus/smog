"""Mutation testing with cargo-mutants, on the diff against the ref or on the whole tree."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from smog.adapter.cargo_tools import failure_reason, first_error, locked, tool_environment
from smog.domain.tools import MutantOutcome
from smog.ports import ToolUnavailable

_STATUS = {"CaughtMutant": "caught", "MissedMutant": "missed", "Timeout": "timeout", "Unviable": "unviable"}


def mutants(root: str, base_sha: str | None) -> list[MutantOutcome]:
    """Outcomes of `cargo mutants`. With a commit, only lines changed against it are mutated; with None, every package of the workspace."""
    if shutil.which("cargo-mutants") is None:
        raise ToolUnavailable("cargo-mutants is not installed")
    with tempfile.TemporaryDirectory() as folder:
        command = ["cargo", "mutants", "--output", folder, "--no-shuffle", *(f"--cargo-arg={option}" for option in locked(root))]
        if base_sha is None:
            command.append("--workspace")
        else:
            diff = Path(folder) / "change.diff"
            diff.write_bytes(subprocess.run(["git", "-C", root, "diff", base_sha], capture_output=True).stdout)
            if not diff.read_bytes().strip():
                return []
            command.extend(["--in-diff", str(diff)])
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, env=tool_environment())
        outcomes = Path(folder) / "mutants.out" / "outcomes.json"
        if not outcomes.exists():
            if result.returncode == 0:
                # cargo-mutants found nothing to mutate in the diff, such as a change to documents only.
                return []
            raise ToolUnavailable(failure_reason(result.stderr) or f"cargo mutants failed: {first_error(result.stderr)}")
        try:
            return parse_outcomes(outcomes.read_text())
        except ToolUnavailable as error:
            log = Path(folder) / "mutants.out" / "log" / "baseline.log"
            output = log.read_text(errors="replace") if log.exists() else ""
            raise ToolUnavailable(failure_reason(output) or (f"{error}: {first_error(output)}" if output.strip() else str(error))) from error


def parse_outcomes(text: str) -> list[MutantOutcome]:
    """The outcome of each mutant. A baseline that did not succeed means cargo-mutants tried no mutant, because
    the tests fail or the code does not build without one: the tool did not run."""
    found = []
    for outcome in json.loads(text)["outcomes"]:
        scenario = outcome["scenario"]
        if not isinstance(scenario, dict):
            if scenario == "Baseline" and outcome.get("summary") != "Success":
                raise ToolUnavailable(f"cargo mutants: the tests fail or the build fails before any mutant (baseline: {outcome.get('summary')})")
            continue
        mutant = scenario["Mutant"]
        line = mutant["span"]["start"]["line"]
        found.append(MutantOutcome(mutant["file"], line, _STATUS.get(outcome["summary"], outcome["summary"]), mutant.get("genre", "")))
    return found
