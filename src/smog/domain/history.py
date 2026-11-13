"""History lenses (design section 3.10). One commit on the first-parent line stands for one squash-merged PR."""

import re
import statistics
from datetime import UTC, datetime
from collections import Counter, defaultdict
from itertools import combinations

from smog.domain.changes import FileChange, ItemDelta
from smog.domain.code import Codebase
from smog.domain.graph import FileGraph
from smog.domain.settings import DEFAULT_SETTINGS


def is_fix_subject(subject: str, settings: dict = DEFAULT_SETTINGS) -> bool:
    """True when the subject matches `fix_commit_pattern`, in any case.

    The default is the `fix` type of Conventional Commits 1.0.0 (read 2026-11-10): "The type fix MUST be used
    when a commit represents a bug fix for your application", and the units "MUST NOT be treated as case
    sensitive".
    """
    return bool(re.search(settings["fix_commit_pattern"], subject, re.IGNORECASE))


class CommitRecord:
    """One commit of the history window with what Smog computed for it. It carries the author's name and no
    email address."""

    def __init__(
        self,
        sha,
        subject,
        timestamp,
        changes: list[FileChange],
        delta: ItemDelta,
        debt: float,
        lines: int,
        findings: set,
        *,
        author: str = "",
        body: str = "",
        trailers: tuple[tuple[str, str], ...] = (),
        parents: tuple[str, ...] = (),
        fixed: tuple[str, ...] = (),
        blamed: tuple[tuple[str, str | None, str], ...] = (),
        branch_start: int | None = None,
    ):
        self._sha = sha
        self._subject = subject
        self._timestamp = timestamp
        self._changes = changes
        self._delta = delta
        self._debt = debt
        self._lines = lines
        self._findings = findings
        self._author = author
        self._body = body
        self._trailers = trailers
        self._parents = parents
        self._fixed = fixed
        self._blamed = blamed
        self._branch_start = branch_start

    @property
    def sha(self) -> str:
        return self._sha

    @property
    def subject(self) -> str:
        return self._subject

    @property
    def timestamp(self) -> int:
        return self._timestamp

    @property
    def author(self) -> str:
        """The author's name."""
        return self._author

    @property
    def trailers(self) -> tuple[tuple[str, str], ...]:
        return self._trailers

    @property
    def parents(self) -> tuple[str, ...]:
        return self._parents

    @property
    def fixed(self) -> tuple[str, ...]:
        """The ancestor commits the `Fixes:` trailers of a fix commit name. Empty for any other commit."""
        return self._fixed

    @property
    def blamed(self) -> tuple[tuple[str, str | None, str], ...]:
        """For a fix commit, one entry per code line it removes or changes in a `.rs` file: (path, history key of
        the function that held the line before the fix or None, commit that last changed the line)."""
        return self._blamed

    @property
    def is_merge(self) -> bool:
        return len(self._parents) > 1

    @property
    def branch_start(self) -> int | None:
        """For a merge commit, the author time of the oldest commit it brought in from its second parent."""
        return self._branch_start

    @property
    def body_lines(self) -> list[str]:
        """The lines of the message body without the trailers: the paragraphs after the subject, minus the last
        one when git read trailers from it."""
        paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", self._body.strip("\n")) if paragraph.strip()]
        if self._trailers and paragraphs:
            paragraphs.pop()
        return [line for paragraph in paragraphs for line in paragraph.splitlines()]

    def has_conventional_header(self, pattern: str = DEFAULT_SETTINGS["conventional_commit_pattern"]) -> bool:
        """True when the subject matches `conventional_commit_pattern`, by default the header of Conventional Commits 1.0.0 (conventionalcommits.org,
        read 2026-11-10): "Commits MUST be prefixed with a type, which consists of a noun, feat, fix, etc.,
        followed by the OPTIONAL scope, OPTIONAL !, and REQUIRED terminal colon and space", "a scope MUST consist
        of a noun describing a section of the codebase surrounded by parenthesis", and "a description MUST
        immediately follow the colon and space".

        The type is read as a letter followed by letters, digits or hyphens, in any case; the specification
        names no closed list of types. Whether a type or scope is a noun is not checked.
        """
        return bool(re.match(pattern, self._subject))

    @property
    def changes(self) -> list[FileChange]:
        return self._changes

    @property
    def delta(self) -> ItemDelta:
        return self._delta

    @property
    def debt(self) -> float:
        """Debt from file-local lenses after this commit."""
        return self._debt

    @property
    def lines(self) -> int:
        return self._lines

    @property
    def findings(self) -> set:
        return self._findings

    @property
    def rust_paths(self) -> set[str]:
        return {change.path for change in self._changes if change.path.endswith(".rs")}

    def is_revert(self, prefixes: tuple[str, ...]) -> bool:
        return self._subject.startswith(prefixes)


def is_code_text(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("//")


def whole_months(start: int, end: int) -> int:
    """Whole calendar months from one Unix time to a later one, both read in UTC. From 31 January to 28 February is 0."""
    first, last = datetime.fromtimestamp(start, UTC), datetime.fromtimestamp(end, UTC)
    months = (last.year - first.year) * 12 + last.month - first.month
    if (last.day, last.time()) < (first.day, first.time()):
        months -= 1
    return max(months, 0)


def theil_sen(values: list[float]) -> float:
    slopes = [(b - a) / (j - i) for (i, a), (j, b) in combinations(enumerate(values), 2)]
    return statistics.median(slopes) if slopes else 0.0


class History:
    """`branch_tips` maps each branch of the clone other than the one checked out to the commit time of its newest commit.
    `has_blame` is False when the records hold no blamed lines because `git blame` cannot be trusted, as in a shallow clone."""

    def __init__(self, records: list[CommitRecord], settings: dict = DEFAULT_SETTINGS, branch_tips: dict[str, int] | None = None, has_blame: bool = True):
        self._settings = settings
        self._records = records
        self._branch_tips = branch_tips
        self._has_blame = has_blame

    @property
    def has_blame(self) -> bool:
        """False when the measurements built on `git blame` have no value: the fixes per file and function and the bug-introducing share."""
        return self._has_blame

    @property
    def commit_count(self) -> int:
        return len(self._records)

    @property
    def records(self) -> list[CommitRecord]:
        return self._records

    def _follow(self, count_of) -> Counter:
        counts: Counter = Counter()
        for record in self._records:
            for old, new in record.delta.moved.items():
                if old in counts:
                    counts[new] += counts.pop(old)
            for key in count_of(record):
                counts[key] += 1
        return counts

    def function_churn(self) -> Counter:
        """Commits that changed each function, followed through moves."""
        return self._follow(lambda record: record.delta.changed.keys())

    def assertion_churn(self) -> Counter:
        return self._follow(lambda record: record.delta.assertion_changed())

    def file_churn(self) -> Counter:
        counts: Counter = Counter()
        for record in self._records:
            counts.update(record.rust_paths)
        return counts

    def folder_churn(self) -> Counter:
        counts: Counter = Counter()
        for record in self._records:
            counts.update({path.rpartition("/")[0] for path in record.rust_paths if not path.endswith("tests.rs")})
        return counts

    def file_line_churn(self) -> dict[str, tuple[int, int]]:
        """Per `.rs` file: (added lines, deleted lines) summed over the commits of the window.

        These are the inputs of the relative churn measures of Nagappan and Ball, "Use of Relative Code Churn
        Measures to Predict System Defect Density" (ICSE 2005, read 2026-11-10): "Churned LOC is the sum of the
        added and changed lines of code between a baseline version and a new version", "Deleted LOC is the number
        of lines of code deleted", "M1: Churned LOC / Total LOC", "M2: Deleted LOC / Total LOC". The paper compares
        two releases; here the commits of the window are summed, so a line changed twice counts twice.

        Git shows a changed line as one deleted and one added line. The added lines are therefore the churned LOC
        exactly, and the deleted lines include the old side of every changed line, which the paper leaves out of
        Deleted LOC. Blank lines and lines that start with `//` are not counted, to match Total LOC, which the
        paper gives as non-commented lines; a line inside a block comment still counts. Renames are not followed:
        a renamed file starts again with all its lines added.
        """
        totals: dict[str, tuple[int, int]] = {}
        for record in self._records:
            for change in record.changes:
                if not change.path.endswith(".rs"):
                    continue
                added, deleted = totals.get(change.path, (0, 0))
                added += sum(1 for _, text in change.added if is_code_text(text))
                deleted += sum(1 for _, text in change.removed if is_code_text(text))
                totals[change.path] = (added, deleted)
        return totals

    def file_ages(self) -> dict[str, int]:
        """Per `.rs` file changed in the window: whole months from its last change to the newest commit read.

        code-maat's `age` analysis "grades each module based on the date of last change. The measurement unit is
        age in months" (README and `analysis/code_age.clj`, read 2026-11-10). code-maat counts up to the current
        date unless `--age-time-now` names another; here the end is the time of the newest commit of the window,
        so the value is the same on every machine and on every day. As in code-maat, a file with no change in the
        log that was read has no value: its last change is older than the window. Commit times are read in UTC.
        """
        if not self._records:
            return {}
        last_change: dict[str, int] = {}
        for record in self._records:
            for path in record.rust_paths:
                last_change[path] = max(record.timestamp, last_change.get(path, record.timestamp))
        end = max(record.timestamp for record in self._records)
        return {path: whole_months(changed, end) for path, changed in last_change.items()}

    def change_coupling(self) -> list[tuple[str, str, float, int, float]]:
        """Pairs of `.rs` files that changed together: (file, coupled file, degree, shared commits, average commits).

        The degree is code-maat's: "the number of shared revisions divided by the average number of revisions for
        the two coupled modules", as a percentage (`analysis/logical_coupling.clj` and README, read 2026-11-10):
        100 x shared / ((commits of one + commits of the other) / 2). code-maat prints the whole-number part; the
        value here keeps the fraction.

        A pair is listed when the average is at least `change_coupling_min_revisions` and the shared commits at
        least `change_coupling_min_shared`; code-maat's defaults for both are 5. A commit with more than
        `large_commit_files` Rust files is left out of every count; code-maat's default for that limit is 30
        files of any kind. code-maat's lower bound on the degree, 30, is not applied. One commit on the
        first-parent line counts as one revision, and renames are not followed. The pairs are sorted by degree,
        highest first, then by path.
        """
        pairs, singles = self._pair_counts()
        found = []
        for (left, right), shared in pairs.items():
            average = (singles[left] + singles[right]) / 2
            if average >= self._settings["change_coupling_min_revisions"] and shared >= self._settings["change_coupling_min_shared"]:
                found.append((left, right, self._settings["change_coupling_scale"] * shared / average, shared, average))
        return sorted(found, key=lambda pair: (-pair[2], pair[0], pair[1]))

    def strongest_coupling(self) -> dict[str, float]:
        """Per file: the highest degree among its pairs in `change_coupling`. A file in no listed pair is absent."""
        strongest: dict[str, float] = {}
        for left, right, degree, _, _ in self.change_coupling():
            for path in (left, right):
                strongest[path] = max(degree, strongest.get(path, 0.0))
        return strongest

    def short_term_churn(self) -> float:
        """Lines added in the window that a later commit removes or rewrites within `short_term_churn_days` / lines added.

        GitClear's churn ("AI Code Quality" signal graphs, gitclear.com, read 2026-11-10): "Share of authored
        lines that were subsequently rewritten or removed within two weeks. A proxy for defect or rework rate."
        GitClear follows each line with an engine that "keeps lines connected from initial inception, through
        possible file moves & find/replaces" and does not publish its rule. Here a line added to a `.rs` file
        counts as rewritten or removed when a later commit of the window, committed at most that many days
        after, removes a line of the same file with the same text, white space at the ends aside; each removed
        line answers for one added line, the earliest that fits. Blank lines are not counted. A line moved to another file counts as
        removed, and lines added in the last days of the window have had less time to be rewritten. 0 without an
        added line.
        """
        added = rewritten = 0
        limit = self._settings["short_term_churn_days"] * 86400
        # Per commit, the removed lines that have not answered for an added line yet.
        removed = [Counter((change.path, text.strip()) for change in record.changes for _, text in change.removed) for record in self._records]
        for index, record in enumerate(self._records):
            in_time = [later for later in range(index + 1, len(self._records)) if self._records[later].timestamp - record.timestamp <= limit]
            for change in record.changes:
                for _, text in change.added:
                    if not text.strip() or not change.path.endswith(".rs"):
                        continue
                    added += 1
                    key = (change.path, text.strip())
                    answering = next((later for later in in_time if removed[later][key] > 0), None)
                    if answering is not None:
                        removed[answering][key] -= 1
                        rewritten += 1
        return rewritten / added if added else 0.0

    def _share(self, flagged) -> float | None:
        """Commits of the window for which `flagged` holds / commits of the window. None without a commit."""
        if not self._records:
            return None
        return sum(1 for record in self._records if flagged(record)) / len(self._records)

    def unconventional_messages(self) -> float | None:
        """Commits whose subject does not follow the Conventional Commits header / commits of the window.

        The header rule is quoted in `CommitRecord.has_conventional_header`. Every commit of the window counts,
        also merge commits and reverts with the subject git writes for them, which do not follow the header.
        """
        return self._share(lambda record: not record.has_conventional_header(self._settings["conventional_commit_pattern"]))

    def long_subjects(self) -> float | None:
        """Commits whose subject has more than `subject_max_length` characters / commits of the window.

        git-commit(1), "Discussion" (git-scm.com/docs/git-commit, read 2026-11-10): "it's a good idea to begin the
        commit message with a single short (no more than 50 characters) line summarizing the change, followed by
        a blank line and then a more thorough description". The subject is the text up to the first blank line.
        """
        limit = self._settings["subject_max_length"]
        return self._share(lambda record: len(record.subject) > limit)

    def messages_without_body(self) -> float | None:
        """Commits whose message has no body / commits of the window.

        The body is the "more thorough description" after the blank line (git-commit(1), as quoted in
        `long_subjects`). Trailers such as `Co-authored-by:` are no body (`CommitRecord.body_lines`).
        """
        return self._share(lambda record: not record.body_lines)

    def long_body_lines(self) -> float | None:
        """Commits with a body line of more than `body_line_max_length` characters / commits of the window.

        The default of 72 is from Tim Pope, "A Note About Git Commit Messages" (tbaggery.com, 2008, read
        2026-11-10): "More detailed explanatory text, if necessary. Wrap it to about 72 characters or so." The
        Linux kernel asks for "the body of the explanation, line wrapped at 75 columns" (docs.kernel.org,
        "Submitting patches", read 2026-11-10). A line without white space, such as a URL, cannot be wrapped and
        is not counted; that exception is Smog's own. Trailers are not body lines.
        """
        limit = self._settings["body_line_max_length"]
        return self._share(lambda record: any(len(line) > limit and len(line.split()) > 1 for line in record.body_lines))

    def fix_references(self) -> float | None:
        """Fix commits with a `Fixes:` trailer that names an ancestor commit / fix commits. None without a fix commit.

        The trailer is the Linux kernel's ("Submitting patches", docs.kernel.org, read 2026-11-10): "A Fixes: tag
        indicates that the patch fixes a bug in a previous commit", written as `Fixes: 54a4f0239f2e ("KVM: MMU:
        make kvm_mmu_zap_page() return the number of pages it actually freed")`. The kernel asks for "at least
        the first 12 characters of the SHA-1 ID, and the one line summary"; here any hash of 4 or more
        characters that git resolves to an ancestor of the fix counts, and the summary is not compared. A fix
        commit is one whose subject matches `fix_commit_pattern` (`is_fix_subject`).
        """
        fixes = [record for record in self._records if is_fix_subject(record.subject, self._settings)]
        return sum(1 for record in fixes if record.fixed) / len(fixes) if fixes else None

    def szz_file_fixes(self) -> Counter:
        """Per `.rs` file: the fix commits of the window that removed or changed a code line of it. See `szz_function_fixes`."""
        counts: Counter = Counter()
        for record in self._records:
            counts.update({path for path, _, _ in record.blamed})
        return counts

    def szz_function_fixes(self) -> Counter:
        """Per function: the fix commits of the window that removed or changed a code line inside it, followed through moves.

        This is the SZZ algorithm in its basic form (B-SZZ). Borg et al., "SZZ Unleashed" (arXiv:1903.01742,
        section 2, read 2026-11-10), a secondary source for Sliwerski, Zimmermann and Zeller 2005, whose paper could
        not be opened: "For each of the bug-fixing commits ... SZZ uses the git blame command to identify all
        commits that previously made changes to the same lines of code", which gives the "bug-introducing commit
        candidates"; commit messages "that contain the word 'fix' ... are assumed to be bug fixes" when no bug
        tracker is linked.

        Here: a fix commit is one whose subject matches `fix_commit_pattern`. For each `.rs` file it changes,
        `git blame --first-parent` runs on the fix's parent for the lines the fix removes or changes. Blank lines
        and lines that start with `//` are skipped, a small part of the cosmetic-change filter of Kim et al.,
        whose annotation graph is not built. The commit blame names is the introducing commit; the line's file
        and function are where the fix landed.

        Not done: SZZ rules out a candidate committed after the bug was reported. No bug tracker is read, so
        every candidate counts.

        Known errors: a fix that only adds lines blames nothing; a commit that only reformatted, renamed or moved
        a line is blamed in place of the one that wrote the bug; a fix that also tidies correct lines blames
        their commits; a fix whose subject does not match the pattern is missed and a commit that matches without
        fixing a bug is counted; files other than `.rs` are not read.
        """
        return self._follow(lambda record: {record.delta.moved.get(key, key) for _, key, _ in record.blamed if key})

    def bug_introducing_share(self) -> float | None:
        """Commits of the window that a later fix commit of the window blames / commits of the window.

        A commit is blamed when `szz_function_fixes`' blame names it for a line a fix removes or changes. A
        blamed commit older than the window is not counted on either side. None without a commit or without blame.
        """
        if not self._records or not self._has_blame:
            return None
        blamed = {sha for record in self._records for _, _, sha in record.blamed}
        return sum(1 for record in self._records if record.sha in blamed) / len(self._records)

    def active_branches(self) -> int | None:
        """Branches of the clone, other than the one checked out, with a commit in the `active_branch_days` before
        the newest commit of the window. None when the branches were not read or the window is empty.

        DORA, "Trunk-based development" (dora.dev, read 2026-11-10): "Measure how many active branches you have
        on your application repositories' version control systems", with the goal "Three or fewer active
        branches". DORA does not say what active means. The rule here is GitHub's branch view (docs.github.com,
        "Viewing branches in your repository", read 2026-11-10): "all branches (excluding the default branch)
        that anyone has committed to within the last three months", with the checked-out branch in place of the
        default branch and the newest commit of the window in place of today, so the value does not change
        with the day it is computed. It does change with the branches the clone holds.
        """
        if self._branch_tips is None or not self._records:
            return None
        newest = max(record.timestamp for record in self._records)
        return sum(1 for time in self._branch_tips.values() if time >= newest - self._settings["active_branch_days"] * 86400)

    def merges_per_day(self) -> float | None:
        """Merge commits of the window / days from its oldest to its newest commit. None when that span is 0.

        DORA's goal is "Merging at least once per day" (as cited in `active_branches`). A merge commit is a
        commit of the first-parent line with more than one parent. A branch that was squashed or rebased onto
        the line leaves no merge commit and is not counted, so a repository that only squashes has 0.
        """
        if not self._records:
            return None
        times = [record.timestamp for record in self._records]
        days = (max(times) - min(times)) / 86400
        return sum(1 for record in self._records if record.is_merge) / days if days else None

    def branch_lifetime_days(self) -> float | None:
        """Median days from the first commit of a merged branch to its merge, over the merge commits of the window.

        DORA gives no counting rule: "branches in trunk-based development typically last no more than a few
        hours" (as cited in `active_branches`). Here the start is the earliest author time among the commits the
        merge brought in (`<merge>^1..<merge>^2`) and the end is the commit time of the merge. None without a
        merge commit: a squashed branch leaves its first commit only at the repository host.
        """
        spans = [(record.timestamp - record.branch_start) / 86400 for record in self._records if record.is_merge and record.branch_start is not None]
        return statistics.median(spans) if spans else None

    def item_survival(self) -> tuple[float, float]:
        """Median commits until removal, and share of added functions removed within a few commits."""
        born: dict[str, int] = {}
        ages = []
        for index, record in enumerate(self._records):
            for old, new in record.delta.moved.items():
                if old in born:
                    born[new] = born.pop(old)
            for key in record.delta.added:
                born[key] = index
            for key in record.delta.removed:
                if key in born:
                    ages.append(index - born.pop(key))
        total = len(ages) + len(born)
        early = sum(1 for age in ages if age <= self._settings["early_removal_commits"])
        return statistics.median(ages) if ages else 0.0, early / total if total else 0.0

    def reverts(self) -> int:
        return sum(1 for record in self._records if record.is_revert(self._settings["revert_subject_prefixes"]))

    def follow_up_fixes(self) -> int:
        """Fix commits (`is_fix_subject`) that remove lines added by one of the previous commits in a short window."""
        count = 0
        for index, record in enumerate(self._records):
            if not is_fix_subject(record.subject, self._settings):
                continue
            removed = {(change.path, text.strip()) for change in record.changes for _, text in change.removed if text.strip()}
            earlier = self._records[max(0, index - self._settings["short_term_window"]) : index]
            added = {(change.path, text.strip()) for prior in earlier for change in prior.changes for _, text in change.added}
            count += bool(removed & added)
        return count

    def _pair_counts(self) -> tuple[Counter, Counter]:
        pairs: Counter = Counter()
        singles: Counter = Counter()
        for record in self._records:
            paths = sorted(record.rust_paths)
            if len(paths) > self._settings["large_commit_files"]:
                continue
            singles.update(paths)
            pairs.update(combinations(paths, 2))
        return pairs, singles

    def files_changed_together(self) -> int:
        """File pairs that changed together in at least `files_changed_together_min_commits` commits."""
        pairs, _ = self._pair_counts()
        return sum(1 for count in pairs.values() if count >= self._settings["files_changed_together_min_commits"])

    def modularity_violations(self, graph: FileGraph) -> list[tuple[str, str]]:
        pairs, singles = self._pair_counts()
        edges = graph.edges
        found = []
        for (left, right), shared in pairs.items():
            if shared < self._settings["modularity_min_shared"] or right in edges.get(left, ()) or left in edges.get(right, ()):
                continue
            if max(shared / singles[left], shared / singles[right]) >= self._settings["modularity_share"]:
                found.append((left, right))
        return found

    def unstable_interfaces(self, graph: FileGraph) -> dict[str, int]:
        """Per file: dependents that changed with it at least twice in commits where its public signatures changed."""
        dependents = defaultdict(set)
        for source, targets in graph.edges.items():
            for target in targets:
                dependents[target].add(source)
        changed_with: dict[tuple, int] = Counter()
        for record in self._records:
            for path in record.delta.public_changed_paths:
                for dependent in dependents[path] & record.rust_paths:
                    changed_with[(path, dependent)] += 1
        result: Counter = Counter()
        for (path, _), count in changed_with.items():
            if count >= self._settings["unstable_min_changes"]:
                result[path] += 1
        return result

    def anchor_dominated(self, graph: FileGraph) -> dict[str, int]:
        """Per file: dependents whose changes pull this file along more often than the reverse."""
        pairs, singles = self._pair_counts()
        result: Counter = Counter()
        for source, targets in graph.edges.items():
            for target in targets:
                shared = pairs[tuple(sorted((source, target)))]
                if shared and shared / singles[target] > shared / singles[source] and shared / singles[target] >= self._settings["modularity_share"]:
                    result[target] += 1
        return result

    def co_changing_clones(self, codebase: Codebase) -> int:
        """Pairs of functions with equal shape that also changed in the same commit."""
        by_shape = defaultdict(list)
        for function in codebase.functions:
            if function.lines >= self._settings["clone_min_lines"]:
                by_shape[function.shape_hash()].append(function.history_key)
        clone_pairs = {pair for group in by_shape.values() if len(group) > 1 for pair in combinations(sorted(group), 2)}
        found = set()
        for record in self._records:
            changed = record.delta.changed.keys()
            found |= {(left, right) for left, right in clone_pairs if left in changed and right in changed}
        return len(found)

    def debt_trend(self) -> tuple[float, float]:
        """Theil-Sen slope of debt per `density_per_lines` lines (1,000 by default) per commit, and the share of commits that lowered debt."""
        per_lines = self._settings["density_per_lines"]
        densities = [per_lines * record.debt / record.lines for record in self._records if record.lines]
        lowered = sum(1 for before, after in zip(self._records, self._records[1:]) if after.debt < before.debt)
        return theil_sen(densities), lowered / max(len(self._records) - 1, 1)

    def finding_age(self) -> tuple[float, float]:
        """Median age in commits of the findings alive at the end, and findings removed over findings added."""
        first_seen: dict = {}
        added = removed = 0
        previous: set = set()
        for index, record in enumerate(self._records):
            new, gone = record.findings - previous, previous - record.findings
            if index:
                added += len(new)
                removed += len(gone)
            for finding in new:
                first_seen.setdefault(finding, index)
            previous = record.findings
        ages = [len(self._records) - 1 - first_seen[finding] for finding in previous]
        return statistics.median(ages) if ages else 0.0, removed / added if added else 0.0

    def equilibrium(self) -> float:
        """Where the score is heading: `1 - (d / l) * 1000 / equilibrium_zero_debt_per_1000_lines` from recent debt added and lines added per commit."""
        if len(self._records) < 2:
            return 1.0
        debt = self._records[-1].debt - self._records[0].debt
        lines = self._records[-1].lines - self._records[0].lines
        if lines <= 0:
            return 1.0
        return min(1.0, 1 - (debt / lines) * self._settings["density_per_lines"] / self._settings["equilibrium_zero_debt_per_1000_lines"])

    def touched_state(self, paths: list[str], now: int) -> tuple[float, float]:
        """Prior commits on the touched files, and days since their last change."""
        commits = 0
        ages = []
        for path in paths:
            touches = [record for record in self._records if path in {change.path for change in record.changes}]
            commits += len(touches)
            if touches:
                ages.append((now - touches[-1].timestamp) / 86400)
        return commits, sum(ages) / len(ages) if ages else 0.0
