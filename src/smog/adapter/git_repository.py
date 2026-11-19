"""Reads a repository through the git command line."""

import io
import re
import subprocess
import tarfile
import time
from pathlib import Path

from smog.domain.changes import CommitInfo, FileChange

# No email address is asked for: nothing uses one.
# Every field ends with a NUL byte, which no commit message can hold.
_COMMIT_FIELDS = 7
_COMMIT_FORMAT = "%H%x00%P%x00%ct%x00%an%x00%s%x00%b%x00%(trailers:only,unfold)%x00"
_TRAILER = re.compile(r"^([^\s:]+):\s*(.*)$")
_HEX = re.compile(r"^[0-9a-fA-F]{4,40}$")
_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


# Configuration every git call runs with, so that the user's or the repository's settings cannot change a
# result: paths are not quoted, diffs carry the `a/` and `b/` prefixes and use the default algorithm and hunk
# rules, and the log holds no signature output and is UTF-8. `blame` clears the ignored revisions on its command line.
_NEUTRAL_CONFIG = tuple(
    part
    for setting in (
        "core.quotePath=false",
        "diff.noprefix=false",
        "diff.mnemonicPrefix=false",
        "diff.algorithm=myers",
        "diff.indentHeuristic=true",
        "diff.interHunkContext=0",
        "diff.submodule=short",
        "log.showSignature=false",
        "i18n.logOutputEncoding=UTF-8",
    )
    for part in ("-c", setting)
)
# How every diff is asked for. The prefixes are named because newer git versions can change them by configuration.
_DIFF_OPTIONS = ("--no-color", "--no-ext-diff", "--no-textconv", "--unified=0", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/")


class GitRepository:
    def __init__(self, root: str):
        self._root = str(Path(root).resolve())

    @property
    def root(self) -> str:
        return self._root

    def _git(self, *args: str, input_bytes: bytes | None = None) -> bytes:
        result = subprocess.run(["git", *_NEUTRAL_CONFIG, "-C", self._root, *args], input=input_bytes, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}")
        return result.stdout

    def tracked_paths(self, ref: str | None = None) -> list[str]:
        if ref is None:
            output = self._git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
            return [path for path in output.decode().split("\0") if path and (Path(self._root) / path).is_file()]
        return [path for path in self._git("ls-tree", "-r", "--name-only", "-z", ref).decode().split("\0") if path]

    def read_files(self, paths: list[str], ref: str | None = None) -> dict[str, bytes]:
        if ref is None:
            return {path: (Path(self._root) / path).read_bytes() for path in paths}
        if not paths:
            return {}
        request = "".join(f"{ref}:{path}\n" for path in paths).encode()
        output = self._git("cat-file", "--batch", input_bytes=request)
        contents = {}
        position = 0
        for path in paths:
            end = output.index(b"\n", position)
            header = output[position:end].split()
            position = end + 1
            if header[-1] == b"missing":
                continue
            size = int(header[2])
            contents[path] = output[position : position + size]
            position += size + 1
        return contents

    def merge_base(self, ref: str) -> str:
        """The merge base of `ref` and HEAD. A ref with no branch or tag of that name here is read as `origin/<ref>`,
        as in a CI checkout of a pull request, which holds `origin/main` but no `main`."""
        if subprocess.run(["git", "-C", self._root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], capture_output=True).returncode != 0:
            ref = f"origin/{ref}"
        return self._git("merge-base", ref, "HEAD").decode().strip()

    def diff_against(self, sha: str, *, detect_renames: bool = False) -> list[FileChange]:
        """Committed and uncommitted changes, with untracked files counted as added.

        Only suppression checks request rename detection. Other diff consumers keep deleted and added paths.
        The explicit threshold and unlimited search make rename detection independent of git configuration.
        """
        options = (*_DIFF_OPTIONS, "--find-renames=50%", "-l0") if detect_renames else _DIFF_OPTIONS
        changes = _parse_diff(self._git("diff", *options, sha))
        for path in self._git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0"):
            if path and (Path(self._root) / path).is_file():
                text = (Path(self._root) / path).read_text(errors="replace")
                changes.append(FileChange(path, list(enumerate(text.splitlines(), 1)), [], "A"))
        return changes

    def first_parent_commits(self, limit: int) -> list[CommitInfo]:
        """The last `limit` commits on the first-parent line of HEAD, oldest first, each with its parents, commit
        time, author name, subject, body and trailers. Trailers are the ones git itself reads from the
        message (`%(trailers:only,unfold)`)."""
        output = self._git("log", "--first-parent", f"-n{limit}", "--reverse", f"--format={_COMMIT_FORMAT}", "HEAD")
        commits = []
        fields = output.decode(errors="replace").split("\0")
        for start in range(0, len(fields) - _COMMIT_FIELDS, _COMMIT_FIELDS):
            sha, parents, time, author, subject, body, trailers = fields[start : start + _COMMIT_FIELDS]
            sha = sha.lstrip("\n")
            pairs = tuple(match.groups() for match in map(_TRAILER.match, trailers.splitlines()) if match)
            commits.append(
                CommitInfo(
                    sha,
                    subject,
                    int(time),
                    parents.split()[0] if parents else None,
                    parents=tuple(parents.split()),
                    author=author,
                    body=body.strip("\n"),
                    trailers=pairs,
                )
            )
        return commits

    def changes_in(self, sha: str) -> list[FileChange]:
        """The commit against its first parent."""
        output = self._git("show", "--first-parent", *_DIFF_OPTIONS, "--format=", sha)
        return _parse_diff(output)

    def ancestor_commit(self, name: str, descendant: str) -> str | None:
        """Only a hash of 4 to 40 hexadecimal characters is looked up, so a branch or tag name names nothing."""
        if not _HEX.match(name):
            return None
        found = subprocess.run(["git", "-C", self._root, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"], capture_output=True, text=True)
        sha = found.stdout.strip()
        if found.returncode != 0 or sha == descendant:
            return None
        is_ancestor = subprocess.run(["git", "-C", self._root, "merge-base", "--is-ancestor", sha, descendant], capture_output=True)
        return sha if is_ancestor.returncode == 0 else None

    def blame(self, sha: str | None, path: str, lines: list[int] | None) -> dict[int, str]:
        """Runs `git blame --porcelain --first-parent` on the runs of neighboring lines, or on the whole file with
        `lines=None`. With `--first-parent` a line that came in through a merge is blamed on the merge commit, which
        is the commit the history window holds. With `-M -C` a line moved within its file, or from another file
        changed in the same commit, keeps the commit that wrote it. `sha=None` blames the working tree: a line no
        commit holds yet gets a hash of 40 zeros. A file git cannot blame at that commit gives no line."""
        if lines is not None and not lines:
            return {}
        ranges = []
        for line in sorted(set(lines or ())):
            if ranges and line == ranges[-1][1] + 1:
                ranges[-1][1] = line
            else:
                ranges.append([line, line])
        try:
            # The empty `--ignore-revs-file` clears the revisions a `blame.ignoreRevsFile` of the configuration names.
            output = self._git("blame", "--porcelain", "--first-parent", "-M", "-C", "--ignore-revs-file=", *(f"-L{start},{end}" for start, end in ranges), *([sha] if sha else []), "--", path)
        except RuntimeError:
            return {}
        origin = {}
        for row in output.decode("utf-8", "replace").split("\n"):
            header = _BLAME_HEADER.match(row)
            if header:
                origin[int(header.group(2))] = header.group(1)
        return origin

    def ancestors(self, commit: str) -> set[str]:
        result = subprocess.run(["git", "-C", self._root, "rev-list", commit, "--"], capture_output=True, text=True)
        return set(result.stdout.split()) if result.returncode == 0 else set()

    def is_shallow(self) -> bool:
        return self._git("rev-parse", "--is-shallow-repository").strip() == b"true"

    def branch_tips(self) -> dict[str, int]:
        """Reads `refs/heads` and `refs/remotes`. `origin/topic` and a local `topic` are one branch, with the newer
        of the two commit times. The branch checked out is left out; when HEAD is detached, as in a CI checkout,
        every branch whose newest commit is HEAD is. The result depends on which branches this clone holds."""
        head = subprocess.run(["git", "-C", self._root, "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        detached_at = "" if head else subprocess.run(["git", "-C", self._root, "rev-parse", "--verify", "--quiet", "HEAD"], capture_output=True, text=True).stdout.strip()
        output = self._git("for-each-ref", "--format=%(refname)%00%(committerdate:unix)%00%(objectname)", "refs/heads", "refs/remotes").decode(errors="replace")
        rows = [row.split("\0") for row in output.splitlines()]
        names = {ref: "/".join(ref.split("/")[2:] if ref.split("/")[1] == "heads" else ref.split("/")[3:]) for ref, _, _ in rows}
        checked_out = {head} | {names[ref] for ref, _, sha in rows if sha == detached_at}
        tips: dict[str, int] = {}
        for ref, committed, _ in rows:
            name = names[ref]
            if name and name != "HEAD" and name not in checked_out and committed:
                tips[name] = max(int(committed), tips.get(name, 0))
        return tips

    def merged_branch_start(self, merge_sha: str) -> int | None:
        times = self._git("log", "--format=%at", f"{merge_sha}^1..{merge_sha}^2").decode().split()
        return min(map(int, times)) if times else None

    def commit_sizes_since(self, sha: str) -> list[int]:
        output = self._git("log", "--first-parent", "--numstat", "--format=%x01", f"{sha}..HEAD").decode(errors="replace")
        sizes = []
        for block in output.split("\x01")[1:]:
            total = 0
            for line in block.strip().splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                    total += int(parts[0]) + int(parts[1])
            sizes.append(total)
        return sizes

    def now(self) -> int:
        return int(time.time())

    def export(self, sha: str, destination: str) -> None:
        archive = self._git("archive", "--format=tar", sha)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(destination, filter="data")


def _parse_diff(output: bytes) -> list[FileChange]:
    changes = []
    path = None
    previous_path = None
    status = "M"
    added: list[tuple[int, str]] = []
    removed: list[tuple[int, str]] = []
    old_line = new_line = 0

    def flush():
        if path is not None:
            changes.append(FileChange(path, added, removed, status, previous_path=previous_path))

    for raw in output.decode("utf-8", "replace").split("\n"):
        if raw.startswith("diff --git "):
            flush()
            path, status, added, removed = _path_from_header(raw), "M", [], []
            previous_path = None
        elif raw.startswith("new file mode"):
            status = "A"
        elif raw.startswith("deleted file mode"):
            status = "D"
        elif raw.startswith("rename from "):
            previous_path = raw.removeprefix("rename from ")
        elif raw.startswith("rename to "):
            path = raw.removeprefix("rename to ")
        elif raw.startswith("@@ "):
            match = _HUNK.match(raw)
            old_line, new_line = int(match.group(1)), int(match.group(2))
        elif raw.startswith("+") and not raw.startswith("+++ "):
            added.append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("--- "):
            removed.append((old_line, raw[1:]))
            old_line += 1
    flush()
    return changes


def _path_from_header(line: str) -> str:
    """Read a same-path header. A rename's destination is read from its subsequent `rename to` line."""
    body = line.removeprefix("diff --git ")
    middle = (len(body) - 1) // 2
    return body[middle + 3 :] if body[middle] == " " else body.rsplit(" b/", 1)[-1]
