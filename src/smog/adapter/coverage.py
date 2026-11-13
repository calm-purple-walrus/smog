"""Line coverage from cargo-llvm-cov."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from smog.adapter.cargo_tools import failure_reason, first_error, locked, tool_environment
from smog.ports import ToolUnavailable


def coverage(root: str) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """Uncovered lines and coverable lines per file, with paths relative to the repository root."""
    if shutil.which("cargo-llvm-cov") is None:
        raise ToolUnavailable("cargo-llvm-cov is not installed")
    with tempfile.TemporaryDirectory() as folder:
        report = Path(folder) / "lcov.info"
        command = ["cargo", "llvm-cov", "--workspace", "--lcov", "--output-path", str(report), *locked(root)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, env=tool_environment())
        if not report.exists():
            raise ToolUnavailable(failure_reason(result.stderr) or f"cargo llvm-cov failed: {first_error(result.stderr)}")
        return parse_lcov(report.read_text(), str(Path(root).resolve()))


def parse_lcov(text: str, root: str) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """Per file, the lines with zero hits and all lines with a `DA` record."""
    uncovered: dict[str, set[int]] = {}
    coverable: dict[str, set[int]] = {}
    path = None
    for line in text.splitlines():
        if line.startswith("SF:"):
            path = str(Path(line[3:]).resolve()).removeprefix(root + "/")
            uncovered.setdefault(path, set())
            coverable.setdefault(path, set())
        elif line.startswith("DA:") and path is not None:
            number, hits = line[3:].split(",")[:2]
            coverable[path].add(int(number))
            if hits == "0":
                uncovered[path].add(int(number))
    return uncovered, coverable
