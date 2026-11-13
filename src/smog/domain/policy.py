"""Conditions and policy. A condition is a Python function of a Run, of one of three kinds: blocking, warning, metric.

Every declarative method on Policy builds a blocking or warning condition from the same pieces a user-written
condition can use.
"""

import fnmatch
import inspect
import json
import math
from collections.abc import Callable, Iterable
from enum import Enum

from smog.domain.curves import Curve, plain_number
from smog.domain.registry import DIFF_CHECKS, REGISTRY, Kind, MetricSpec, PieceKind, Status
from smog.domain.scoring import Scorecard, Scored, ScoringModel, checked_score
from smog.domain.selection import STANDARD_SELECTION
from smog.domain.settings import DEFAULT_SETTINGS, check_settings_together, checked_setting
from smog.domain.slop_rules import LIMIT_RULES, rule_setting
from smog.domain.slop_rules import RULES as SLOP_RULES


class Severity(Enum):
    BLOCK = "block"
    WARN = "warn"
    # A gate that could not be evaluated and does not fail the result: a warning-level gate, or one the policy allows not to run.
    NOT_RUN = "not run"


class NotRun:
    """What a condition yields in place of violations when it could not be evaluated, with the reason."""

    def __init__(self, reason: str):
        self._reason = reason

    @property
    def reason(self) -> str:
        return self._reason


def kept_in_part_reason(metric_id: str, pieces: list) -> str:
    """Why a measurement has no value on pieces of which a run restricted with `Policy.only` keeps only some files."""
    if pieces[0].kind is PieceKind.CODEBASE:
        what = "the codebase"
    else:
        what = f"the {pieces[0].kind.value}{'s' if len(pieces) > 1 else ''} {', '.join(piece.id for piece in pieces)}"
    return f"this run keeps only a part of {what} (--only or policy.only), which leaves out {metric_id}"


# A piece of a level holds the pieces of every lower level; functions, tests and types are side by side in a file.
_LEVEL_RANK = {
    PieceKind.FUNCTION: 0, PieceKind.TEST: 0, PieceKind.TYPE: 0, PieceKind.FILE: 1, PieceKind.MODULE: 2, PieceKind.CRATE: 3,
    PieceKind.CODEBASE: 4,
}  # fmt: skip


def _level(name: str) -> PieceKind:
    if name not in {kind.value for kind in _LEVEL_RANK}:
        raise ValueError(f"unknown level {name}; the levels are {', '.join(kind.value for kind in _LEVEL_RANK)}")
    return PieceKind(name)


class Finding:
    def __init__(self, severity: Severity, condition: str, message: str, piece_id: str = ""):
        self._severity = severity
        self._condition = condition
        self._message = message
        self._piece_id = piece_id

    @property
    def severity(self) -> Severity:
        return self._severity

    @property
    def condition(self) -> str:
        return self._condition

    @property
    def message(self) -> str:
        return self._message

    @property
    def piece_id(self) -> str:
        return self._piece_id


class Run:
    """What a condition can see: the scored code, the comparison with the ref, history, checks and tool results."""

    def __init__(self, card: Scorecard, comparison=None, history=None, checks=None, slop=None, tools=None, unvalued=None):
        self._card = card
        self._unvalued = unvalued or {}
        self._comparison = comparison
        self._history = history
        self._checks = checks or {}
        self._slop = slop or []
        self._tools = tools

    @property
    def card(self) -> Scorecard:
        return self._card

    @property
    def restricted(self) -> bool:
        """True for a run that keeps only some files (`Policy.only`). Such a run has no value of the whole codebase.
        A run whose patterns keep every file is not restricted."""
        return self._card.root.kept_in_part

    @property
    def codebase(self):
        return self._card.root.item

    @property
    def comparison(self):
        """The Comparison with the policy's ref, or None without a ref."""
        return self._comparison

    @property
    def history(self):
        return self._history

    @property
    def checks(self) -> dict:
        return self._checks

    @property
    def slop(self) -> list:
        return self._slop

    @property
    def tools(self):
        return self._tools

    @property
    def unvalued(self) -> dict[str, str]:
        """Each selected measurement without a value in this run, with the reason."""
        return self._unvalued

    def pieces(self, kind: str) -> list:
        return self._card.pieces(PieceKind(kind))

    # Building blocks for a product's own rules. All leave out test code.

    def files(self, pattern: str = "*") -> list:
        """Production source files whose path matches the pattern."""
        return [file for file in self.codebase.files if not file.is_test and fnmatch.fnmatch(file.path, pattern)]

    def folders(self) -> list[str]:
        """Every folder that holds a tracked file, as a path from the repository root. The root is the empty string."""
        return sorted({path.rpartition("/")[0] for path in self.codebase.tracked_paths})

    def types(self, pattern: str = "*") -> list:
        """Structs and enums outside test code whose name matches the pattern. Each has `fields`, `public_fields`, `methods` and `file`."""
        return [type_def for type_def in self.codebase.types if not type_def.in_test_code and fnmatch.fnmatchcase(type_def.name, pattern)]

    def type_uses(self, pattern: str) -> list[tuple]:
        """(file, type name) for each production file that names a type matching the pattern.

        Matched by name in the source text, so an alias or a macro hides a use.
        """
        found = []
        for file in self.files():
            names = {token.text for token in file.root.tokens() if token.kind == "type_identifier" and fnmatch.fnmatchcase(token.text, pattern)}
            found.extend((file, name) for name in sorted(names))
        return found

    def functions(self) -> list:
        """Production functions."""
        return self._card.pieces(PieceKind.FUNCTION)

    def score(self, piece=None) -> float:
        return self._card.score(piece)

    def metric_score(self, metric_id: str, piece=None) -> float | None:
        return self._card.metric_score(metric_id, piece)


class Condition:
    def __init__(self, name: str, severity: Severity, function: Callable[[Run], Iterable], allow_not_run: bool = False, detail: str = ""):
        """`detail` holds the numbers a declarative gate was given, for `describe`."""
        self._name = name
        self._severity = severity
        self._function = function
        self._allow_not_run = allow_not_run
        self._detail = detail

    def describe(self) -> str:
        """The gate in one line, such as `block floor function.nesting (block_below=0.5, piece=function)`. The
        body of a function the policy wrote itself is not part of it."""
        details = ", ".join(part for part in (self._detail, "may not run" if self._allow_not_run else "") if part)
        return f"{self._severity.value} {self._name}" + (f" ({details})" if details else "")

    @property
    def name(self) -> str:
        return self._name

    @property
    def severity(self) -> Severity:
        return self._severity

    def evaluate(self, run: Run) -> list[Finding]:
        """The function yields a message, or a (piece or piece id, message) pair, per violation.

        A function that returns True has one violation, "the condition holds"; False or None has none.
        A `NotRun` it yields becomes a finding that says so. It blocks when the condition is blocking, unless the
        condition was declared with `allow_not_run`. Raises TypeError for a function that returns one string.
        """
        results = self._function(run)
        if isinstance(results, bool):
            results = ("the condition holds",) if results else ()
        results = results or ()
        if isinstance(results, str):
            raise TypeError(f"the condition {self._name} returned a string; yield each message, or return a list of them")
        findings = []
        for result in results:
            if isinstance(result, NotRun):
                fails = self._severity is Severity.BLOCK and not self._allow_not_run
                findings.append(Finding(Severity.BLOCK if fails else Severity.NOT_RUN, self._name, f"did not run: {result.reason}"))
            elif isinstance(result, str):
                findings.append(Finding(self._severity, self._name, result))
            else:
                piece, message = result
                findings.append(Finding(self._severity, self._name, message, getattr(piece, "id", str(piece))))
        return findings


class CustomMetric:
    def __init__(self, spec: MetricSpec, function: Callable):
        self._spec = spec
        self._function = function

    @property
    def spec(self) -> MetricSpec:
        return self._spec

    @property
    def doc(self) -> str:
        """The function's docstring, or an empty string."""
        return inspect.getdoc(self._function) or ""

    def measure(self, item) -> tuple[float, tuple[str, ...]]:
        """The function's value for one code object, and the problems it named. A finite number is the value; True
        and False are 1 and 0; a list or tuple of strings names the problems, and their count is the value.
        Anything else raises TypeError."""
        value = self._function(item)
        if isinstance(value, (list, tuple)) and all(isinstance(problem, str) for problem in value):
            return len(value), tuple(value)
        if isinstance(value, bool):
            return int(value), ()
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise TypeError(f"the policy's measurement {self._spec.id} returned {value!r}; it must return a finite number, True, False or a list of problems")
        return value, ()


class DependencyRule:
    """Allows or forbids dependencies from what matches `source` to what matches `target`."""

    def __init__(self, source: str, target: str, allow: bool, reason: str = ""):
        self._source = source
        self._target = target
        self._allow = allow
        self._reason = reason

    @property
    def allow(self) -> bool:
        return self._allow

    def covers(self, source_names: Iterable[str], target_names: Iterable[str]) -> bool:
        """True if one of the names of each end matches its pattern."""
        return any(fnmatch.fnmatch(name, self._source) for name in source_names) and any(fnmatch.fnmatch(name, self._target) for name in target_names)

    def describe(self) -> str:
        return f"{self._source} -> {self._target}" + (f" ({self._reason})" if self._reason else "")


def _describe_row(scored: Scored) -> str:
    """A row of the selection in one line: target, limit, the other curve numbers that are not the defaults, group and weight."""
    numbers = scored.curve.numbers()
    shown = [f"target {numbers['target']:g}", f"limit {numbers['limit']:g}"]
    shown += [f"{name} {value:g}" for name, value in numbers.items() if name not in ("target", "limit") and value is not None and value != Curve(0, 1).numbers()[name]]
    return ", ".join((*shown, f"group {scored.group}", *([f"weight {scored.weight:g}"] if scored.weight != 1 else [])))


def policy_differences(before: dict, after: dict) -> list[str]:
    """What differs between two descriptions of `Policy.describe`, one line per list or entry that changed."""
    lines = []
    for topic in after:
        old, new = before.get(topic), after[topic]
        if isinstance(new, dict) and isinstance(old, dict):
            lines += [f"{topic} {key}: {_shown(old.get(key))} -> {_shown(new.get(key))}" for key in sorted(old.keys() | new.keys()) if old.get(key) != new.get(key)]
        elif isinstance(new, list) and isinstance(old, list):
            for label, items in (("removed", [item for item in old if item not in new]), ("added", [item for item in new if item not in old])):
                if items:
                    lines.append(f"{topic} {label}: {', '.join(map(str, items))}")
        elif old != new:
            lines.append(f"{topic}: {_shown(old)} -> {_shown(new)}")
    return lines


def _shown(value, characters: int = 80) -> str:
    text = "not set" if value is None else value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= characters else text[:characters] + "..."


class PolicyChange:
    """The policy script of a run compared with the same file at the ref (`smog.infrastructure.run.policy_change`)."""

    def __init__(self, path: str, ref: str, changed: bool, differences: list[str], gate_patterns: list[str], note: str = ""):
        self._path = path
        self._ref = ref
        self._changed = changed
        self._differences = differences
        self._gate_patterns = gate_patterns
        self._note = note

    @property
    def path(self) -> str:
        """The policy script, from the repository root."""
        return self._path

    @property
    def ref(self) -> str:
        return self._ref

    @property
    def changed(self) -> bool:
        """True when the script is at the ref and differs from it."""
        return self._changed

    @property
    def differences(self) -> list[str]:
        """What the policy as it is now enforces differently from the policy of the ref (`policy_differences`)."""
        return self._differences

    @property
    def gate_patterns(self) -> list[str]:
        """The gate files check.gate_untouched uses: those of the policy at the ref, or those of the policy as
        it is now when the ref has no policy script or its policy could not be loaded. `note` then says so."""
        return self._gate_patterns

    @property
    def note(self) -> str:
        return self._note


class Policy:
    """What a product measures, scores and enforces. A new policy scores the standard selection with the default settings."""

    def __init__(self):
        self._conditions: list[Condition] = []
        self._metrics: dict[str, CustomMetric] = {}
        self._selection: dict[str, Scored] = {}
        self._disabled: set[str] = set()
        self._settings: dict = dict(DEFAULT_SETTINGS)
        # (gate name, measurement ID, whether the gate needs the measurement's score) per declarative gate on a measurement.
        self._gates: list[tuple[str, str, bool]] = []
        self.use_selection(STANDARD_SELECTION)
        self._ref: str | None = None
        self._exclude: tuple[str, ...] = ()
        self._dependency_rules: list[DependencyRule] = []
        self._layers: dict[str, tuple[str, ...]] = {}
        self._gate_files: list[str] = []
        self._suppression_exceptions: list[str] = []
        self._unused_dependency_ignores: set[str] = set()
        self._slop_exempt: list[str] = []
        self._slop_allow: set[str] = set()
        self._humans: set[str] = set()
        self._only: tuple[str, ...] = ()
        self._score_function: Callable[[float], float] | None = None

    # The three kinds of condition.

    def blocking(self, function=None, *, name: str | None = None):
        """Register a function as a condition that fails the run. Usable as a decorator.

        The function takes the Run and yields a message per violation, or returns True when the condition is violated.
        """
        return self._register(Severity.BLOCK, function, name)

    def warning(self, function=None, *, name: str | None = None):
        """Register a function as a condition that warns. Usable as a decorator."""
        return self._register(Severity.WARN, function, name)

    def _register(self, severity, function, name):
        def add(inner):
            self._conditions.append(Condition(name or inner.__name__, severity, inner))
            return inner

        return add(function) if function is not None else add

    def metric(self, metric_id: str, *, piece: str = "function", target: float | None = None, limit: float | None = None, group: str = "custom", weight: float = 1.0, name: str = ""):
        """Register a function of one code object as a measurement. Usable as a decorator.

        With `target` and `limit` the measurement also joins the selection, so it feeds the score.
        Without them it is measured and reported only; `select` can add it later.
        Raises ValueError for the ID of a built-in measurement. The function must return a finite number, True or
        False for a yes/no measurement (1 and 0), or a list of strings, one per problem: the value is their count,
        and the report names them where it names the piece.
        """

        if metric_id in REGISTRY:
            raise ValueError(f"{metric_id} is a built-in measurement; give the policy's measurement another ID")

        def add(function):
            spec = MetricSpec(metric_id, "custom", name or metric_id, Kind.MEASUREMENT, PieceKind(piece), Status.COMPUTED, "Added by the policy.")
            self._metrics[metric_id] = CustomMetric(spec, function)
            if target is not None or limit is not None:
                self.select(metric_id, target=target, limit=limit, group=group, weight=weight)
            return function

        return add

    # The selection: which measurements feed the score, and with which numbers.

    def select(self, metric_id: str, *, target=None, limit=None, group: str | None = None, weight=None, power=None, knee=None, low_target=None, low_limit=None, base=None) -> None:
        """Put a measurement in the selection, or change the numbers of one that is in it.

        A measurement in the selection is charged to the score: no penalty up to `target`, penalty 1 at `limit`,
        times `weight`. `power`, `knee`, `low_target`, `low_limit` and `base` shape the curve as in `Curve`.
        Measurements in one `group` are charged together: the worst one plus a share of the others.
        A new row needs `target`, `limit` and `group`. For a row already selected, numbers left out keep their value;
        to drop one, such as `low_target`, deselect the row and select it again.
        Raises ValueError for an unknown ID, or one with no number on a piece of code (a check, a diff value, a left-out row).
        """
        spec = self.specs.get(metric_id)
        if spec is None:
            raise ValueError(f"unknown measurement {metric_id}; declare your own with policy.metric before selecting it")
        if not spec.can_be_scored:
            raise ValueError(f"{metric_id} has no number on a piece of code, so it cannot be scored")
        if metric_id in self._disabled:
            raise ValueError(f"{metric_id} is disabled by policy.disable, so it has no value to score; remove it from policy.disable to select it")
        given = {"target": target, "limit": limit, "power": power, "knee": knee, "low_target": low_target, "low_limit": low_limit, "base": base}
        given = {name: value for name, value in given.items() if value is not None}
        current = self._selection.get(metric_id)
        if current is None:
            if target is None or limit is None or group is None:
                raise ValueError(f"{metric_id} is not in the selection; adding it needs target, limit and group")
            self._selection[metric_id] = Scored(Curve(**given), group, 1.0 if weight is None else weight)
        else:
            curve = Curve(**{**current.curve.numbers(), **given})
            self._selection[metric_id] = Scored(curve, group or current.group, current.weight if weight is None else weight)

    def deselect(self, *metric_ids: str) -> None:
        """Take measurements out of the selection. They are still measured and reported.

        Raises ValueError for one that is not selected, or one whose score a floor or `any_function(score_below=...)` reads.
        """
        for metric_id in metric_ids:
            if metric_id not in self._selection:
                raise ValueError(f"{metric_id} is not in the selection")
            kept = {other: scored for other, scored in self._selection.items() if other != metric_id}
            self._check_gates(kept, self._disabled)
            self._selection = kept

    def disable(self, *metric_ids: str) -> None:
        """Switch measurements or checks off for this repository. A disabled ID is reported nowhere.

        A disabled measurement has no value on any piece, so the overview, `--comprehensive`, `--json`, the
        listings of pieces and the registry listing leave it out, and a condition that reads it sees no value.
        `--metric ID` and `--explain ID` say that the policy disabled it. Smog still computes it during the run,
        because other measurements read some values, and removes it before anything reads the result.

        A disabled measurement cannot be in the selection: this raises ValueError for one that is selected, and
        `policy.select` raises for one that is disabled. Deselect it first.

        A disabled check is not reported: it is not in the results, so it is listed neither as passed, failed nor
        skipped. Its work is still done where other results need it. `policy.check` on a disabled check raises
        ValueError, and so does disabling a check that `policy.check` already made count.

        Raises ValueError for an unknown ID. A check is named in full, such as `check.pr_size`.
        """
        for metric_id in metric_ids:
            if metric_id not in self.specs:
                raise ValueError(f"unknown measurement or check {metric_id}; --explain with no ID lists every ID")
            if metric_id in self._selection:
                raise ValueError(f"{metric_id} is in the selection, so it feeds the score and cannot be disabled; call policy.deselect first")
            if any(condition.name == metric_id for condition in self._conditions):
                raise ValueError(f"{metric_id} was made to count with policy.check, so it cannot be disabled")
            self._check_gates(self._selection, self._disabled | {metric_id})
            self._disabled.add(metric_id)

    @property
    def disabled(self) -> frozenset[str]:
        """The IDs switched off with `disable`."""
        return frozenset(self._disabled)

    def use_selection(self, rows: dict[str, dict]) -> None:
        """Replace the whole selection. `rows` maps a measurement ID to the arguments of `select`, like `smog.STANDARD_SELECTION`.

        An empty dict leaves nothing selected, so every score is 1.
        Raises ValueError, and keeps the selection as it was, if a row is not valid or a gate needs the score of a
        measurement the rows leave out.
        """
        before = self._selection
        self._selection = {}
        try:
            for metric_id, numbers in rows.items():
                self.select(metric_id, **numbers)
            self._check_gates(self._selection, self._disabled)
        except ValueError:
            self._selection = before
            raise

    def _check_gates(self, selection: dict, disabled: set[str], gates: list | None = None) -> None:
        """Raise ValueError if a gate reads a measurement that is unknown, disabled or, where it needs the score, not selected."""
        for gate, metric_id, needs_score in self._gates if gates is None else gates:
            if metric_id not in self.specs:
                raise ValueError(f"unknown measurement {metric_id} in {gate}; declare your own with policy.metric first")
            if metric_id in disabled:
                raise ValueError(f"{metric_id} is disabled by policy.disable, and {gate} reads it; a disabled measurement has no value")
            if needs_score and metric_id not in selection:
                raise ValueError(
                    f"{metric_id} is not in the selection, and {gate} needs its score; a measurement outside the selection has no score, "
                    "so the gate would never fire. Call policy.select first, or gate on its value with policy.any_function(..., above=...)"
                )

    def _add_gate(self, gate: str, metric_id: str, needs_score: bool) -> None:
        self._check_gates(self._selection, self._disabled, [(gate, metric_id, needs_score)])
        self._gates.append((gate, metric_id, needs_score))

    def validate(self) -> None:
        """Raise ValueError if a gate can no longer be evaluated or settings contradict each other. A run calls this before it measures anything."""
        self._check_gates(self._selection, self._disabled)
        check_settings_together(self._settings)

    def setting(self, name: str, value) -> None:
        """Override one named setting from `smog.SETTINGS`.

        Raises ValueError for an unknown name and for a value of the wrong kind or out of range (`checked_setting`).
        A setting that is a mapping, such as the parameters of a slop rule, takes the keys to change.
        """
        if name not in self._settings:
            raise ValueError(f"unknown setting {name}; --explain with no ID lists every setting")
        if isinstance(self._settings[name], dict) and isinstance(value, dict):
            # The keys left out keep the value in force, not the default.
            value = {**self._settings[name], **value}
        self._settings[name] = checked_setting(name, value)

    @property
    def has_score_function(self) -> bool:
        return self._score_function is not None

    def score_function(self, function: Callable[[float], float]) -> Callable[[float], float]:
        """Replace how a penalty becomes a score, for every piece and every measurement. Usable as a decorator.

        The default is `exp(-score_decay * penalty)`. The function takes a penalty, a number of 0 or more, and
        returns a score from 0 to 1, such as `lambda penalty: 1 / (1 + penalty)`. It should fall as the penalty
        grows. Raises ValueError unless it returns 1 for no penalty and a number from 0 to 1 for the penalties
        0.5, 1 and 10; a run raises for any other penalty it answers out of that range.
        """
        if function(0.0) != 1:
            raise ValueError(f"the score function returns {function(0.0)!r} for no penalty; a piece without a penalty scores 1")
        for penalty in (0.5, 1.0, 10.0):
            checked_score(function(penalty), penalty)
        self._score_function = function
        return function

    # Declarative conditions.

    def metric_floor(
        self, metric_id: str, *, warn_below: float | None = None, block_below: float | None = None, piece: str = "codebase", allow_not_run: bool = False
    ) -> None:
        """This metric warns below one score and blocks below another, for the codebase or for each piece of a kind.

        Raises ValueError for an unknown or disabled metric, one that is not in the selection, an unknown level, a
        level whose pieces never hold the metric (`file.length` on a function), or a call with neither bound.
        Declare or select a metric before its floor; deselecting it afterwards raises.

        When the metric has no value in a run, such as a slow tool's value without `--full`, the floor did not
        run: the report says so and the result fails if the floor blocks. `allow_not_run=True` reports it without failing.
        The same holds in a run restricted with `only` for a floor on a measurement of a piece that is kept only
        in part, which has no value there: the codebase, or a crate or module of which some files are left out.
        """
        level = _level(piece)
        if warn_below is None and block_below is None:
            raise ValueError(f"a floor on {metric_id} needs `warn_below` or `block_below`")
        name = f"floor {metric_id}"
        self._add_gate(name, metric_id, needs_score=True)
        measured_on = self.specs[metric_id].piece
        if level is not measured_on and _LEVEL_RANK[level] <= _LEVEL_RANK[measured_on]:
            raise ValueError(f"{metric_id} is measured on a {measured_on.value}, so no {piece} carries it and a floor there never fires; use piece=\"{measured_on.value}\" or a higher level")

        def scores(run: Run):
            for candidate in run.pieces(piece):
                score = run.metric_score(metric_id, candidate)
                if score is not None:
                    yield candidate, score

        def not_run(run: Run) -> NotRun | None:
            in_part = [candidate for candidate in run.card.pieces(measured_on) if candidate.kept_in_part]
            if in_part:
                return NotRun(kept_in_part_reason(metric_id, in_part))
            measurable = any(True for _ in run.card.pieces(measured_on))
            if not measurable or run.metric_score(metric_id) is not None:
                return None
            return NotRun(run.unvalued.get(metric_id, f"no {measured_on.value} has a value for {metric_id}"))

        self._add_floor(name, scores, warn_below, block_below, not_run, allow_not_run, piece)

    def score_floor(self, level: str, *, warn_below: float | None = None, block_below: float | None = None) -> None:
        """The overall score of a level warns or blocks below these values. Raises ValueError for an unknown level or a call with neither bound."""
        _level(level)
        if warn_below is None and block_below is None:
            raise ValueError(f"a floor on the {level} score needs `warn_below` or `block_below`")

        def scores(run: Run):
            for candidate in run.pieces(level):
                yield candidate, run.score(candidate)

        self._add_floor(f"floor {level} score", scores, warn_below, block_below)

    def _add_floor(self, name, scores, warn_below, block_below, not_run=None, allow_not_run=False, piece="") -> None:
        """`not_run` gives a `NotRun` when the floor could not be evaluated, or None. Only one of the two conditions reports it."""
        where = f", piece={piece}" if piece else ""

        def violations(run: Run, low, high, reports_not_run):
            skipped = not_run(run) if not_run and reports_not_run else None
            if skipped:
                yield skipped
            for piece, score in scores(run):
                if (high is None or score >= high) and score < low:
                    yield piece, f"score {score:.3f} is below {low}"

        if block_below is not None:
            self._conditions.append(Condition(name, Severity.BLOCK, lambda run: violations(run, block_below, None, True), allow_not_run, f"block_below={block_below:g}{where}"))
        if warn_below is not None:
            self._conditions.append(
                Condition(name, Severity.WARN, lambda run: violations(run, warn_below, block_below, block_below is None), allow_not_run, f"warn_below={warn_below:g}{where}")
            )

    def any_function(
        self, concern, *, above: float | None = None, score_below: float | None = None, severity: str = "block", name: str = "", allow_not_run: bool = False
    ) -> None:
        """Fire if any function violates a concern: a metric id with `above` or `score_below`, or a predicate of the piece.

        Raises ValueError for a metric id that is unknown, disabled or not measured on a function, for one given
        neither `above` nor `score_below`, and for `score_below` on a metric outside the selection. Deselecting or
        disabling the metric afterwards raises.

        When functions exist and none has a value for the metric, such as a slow tool's value without `--full`,
        the gate did not run: the report says so and the result fails if the gate blocks. `allow_not_run=True`
        reports it without failing. A function without the value is not judged.
        """
        label = name or f"any function: {concern if isinstance(concern, str) else concern.__name__}"
        if not callable(concern):
            if above is None and score_below is None:
                raise ValueError(f"any_function on {concern} needs `above` or `score_below`")
            self._add_gate(label, concern, needs_score=score_below is not None)
            measured_on = self.specs[concern].piece
            if self.specs[concern].kind is not Kind.MEASUREMENT or measured_on is not PieceKind.FUNCTION:
                raise ValueError(f"{concern} is measured on a {measured_on.value}; policy.any_function reads functions only")

        def violations(run: Run):
            functions = run.functions()
            if not callable(concern) and functions and not any(concern in piece.values for piece in functions):
                yield NotRun(f"no function has a value for it in this run. {self.specs[concern].note}".rstrip())
            for piece in functions:
                if callable(concern):
                    if concern(piece):
                        yield piece, "violates the concern"
                    continue
                if concern not in piece.values:
                    continue
                value = piece.values[concern]
                if above is not None and value > above:
                    yield piece, f"{concern} is {plain_number(value)}, above {plain_number(above)}"
                if score_below is not None:
                    score = run.metric_score(concern, piece)
                    if score is not None and score < score_below:
                        yield piece, f"{concern} score {score:.3f} is below {score_below}"

        numbers = ", ".join(f"{name}={value:g}" for name, value in (("above", above), ("score_below", score_below)) if value is not None)
        self._conditions.append(Condition(label, Severity(severity), violations, allow_not_run, numbers))

    def function_drop(self, ref: str, *, warn_by: float = 0.2, block_at: float = 0.4, new_functions: bool = False) -> None:
        """Warn when a function's score falls by `warn_by` against the ref. Block when it falls to `block_at` or below.

        Only a function that is in both versions can fall (`smog.domain.matching.match_functions` says which
        function is which): a new function is never compared with another one. So a function that is rewritten
        under a new name passes this gate at any score. `new_functions=True` also blocks a production function
        that is new against the ref and scores `block_at` or below.

        Both sides are scored without slow tools, and with review data only when it can be had for both. With a
        selected measurement of functions or tests that needs what is left out, such as `function.coverage`, the gate
        did not run: the scores would leave that measurement out. A review measurement needs review data only when
        the policy lists humans.
        """
        self.against(ref)

        def left_out(run: Run) -> NotRun | None:
            specs = run.card.model.specs
            needed = [
                metric_id for metric_id in run.card.model.selection
                if specs[metric_id].piece in (PieceKind.FUNCTION, PieceKind.TEST)
                and (specs[metric_id].status is Status.FULL_ONLY or (self.human_logins and not run.comparison.with_reviews and metric_id.partition(".")[2].startswith("unreviewed_")))
            ]  # fmt: skip
            if not needed:
                return None
            return NotRun(f"both sides of the comparison with {ref} are scored without slow tools or review data, which {', '.join(needed)} needs")

        def warnings(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            if left_out(run):
                return
            for piece, before, after in run.comparison.score_drops():
                if before - after >= warn_by and not (after <= block_at and after < before):
                    yield piece, f"score fell from {before:.3f} to {after:.3f} against {ref}"

        def blocks(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            if skipped := left_out(run):
                yield skipped
                return
            for piece, before, after in run.comparison.score_drops():
                if after <= block_at and after < before:
                    yield piece, f"score fell from {before:.3f} to {after:.3f}, at or below {block_at}, against {ref}"

        def new(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            if skipped := left_out(run):
                yield skipped
                return
            for piece, score in run.comparison.new_functions():
                if score <= block_at:
                    yield piece, f"new against {ref} with score {score:.3f}, at or below {block_at}"

        self._conditions.append(Condition(f"function drop by {warn_by}", Severity.WARN, warnings, detail=f"against {ref}"))
        self._conditions.append(Condition(f"function drop to {block_at}", Severity.BLOCK, blocks, detail=f"against {ref}"))
        if new_functions:
            self._conditions.append(Condition(f"new function at {block_at}", Severity.BLOCK, new, detail=f"against {ref}"))

    def file_drop(self, ref: str, *, new_below: float, existing_below: float) -> None:
        """Block a file that is new against the ref and scores below `new_below`, and a file that scored at or above
        `existing_below` on the ref and now scores below it. A file already below `existing_below` on the ref is not
        judged. A moved or renamed file is judged as the file it came from (`Comparison.file_scores`)."""
        self.against(ref)

        def blocks(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            for piece, before, after in run.comparison.file_scores():
                if before is None and after < new_below:
                    yield piece, f"new against {ref} with score {after:.3f}, below {new_below}"
                elif before is not None and before >= existing_below > after:
                    yield piece, f"score fell from {before:.3f} to {after:.3f}, below {existing_below}, against {ref}"

        self._conditions.append(Condition("file drop", Severity.BLOCK, blocks, detail=f"against {ref}, new_below={new_below:g}, existing_below={existing_below:g}"))

    def score_drop(self, ref: str, *, block_above: float) -> None:
        """Block when the score of the codebase falls by more than `block_above` against the ref."""
        self.against(ref)

        def blocks(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            before, after = run.comparison.base.score(), run.comparison.head.score()
            if before - after > block_above:
                yield f"score fell from {before:.3f} to {after:.3f} against {ref}, by more than {block_above:g}"

        self._conditions.append(Condition("score drop", Severity.BLOCK, blocks, detail=f"against {ref}, block_above={block_above:g}"))

    def forbid_dependency(self, dependency: str, *, crates: str = "*", severity: str = "block", reason: str = "") -> None:
        """A hard rule: no matching crate may depend directly on this dependency."""

        def violations(run: Run):
            for crate in run.codebase.crates:
                if fnmatch.fnmatch(crate.name, crates):
                    for dep in crate.manifest.dependencies:
                        if fnmatch.fnmatch(dep.name, dependency):
                            yield crate.name, f"depends on {dep.name}" + (f": {reason}" if reason else "")

        self._conditions.append(Condition(f"forbidden dependency {dependency}", Severity(severity), violations, detail=f"crates={crates}"))

    def warn_added_module(self, pattern: str = "*", *, ref: str = "main", severity: str = "warn") -> None:
        """Fire for each module in the diff against the ref whose qualified name matches."""
        self.against(ref)

        def violations(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            for name in run.comparison.added_modules():
                if fnmatch.fnmatch(name, pattern):
                    yield name, f"module added since {run.comparison.ref}"

        self._conditions.append(Condition(f"added module {pattern}", Severity(severity), violations, detail=f"against {ref}"))

    def warn_added_struct(self, pattern: str = "*", *, ref: str = "main", severity: str = "warn") -> None:
        """Fire for each struct or enum in the diff against the ref whose qualified or short name matches."""
        self.against(ref)

        def violations(run: Run):
            if run.comparison is None:  # a run without --changes compares nothing
                return
            for name in run.comparison.added_structs():
                if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(name.rsplit("::", 1)[-1], pattern):
                    yield name, f"type added since {run.comparison.ref}"

        self._conditions.append(Condition(f"added struct {pattern}", Severity(severity), violations, detail=f"against {ref}"))

    def check(self, check_id: str, severity: str = "block", *, allow_not_run: bool = False) -> None:
        """Make a design check fire when it fails. Checks are otherwise reported without changing the exit code.

        A check that did not run in a run, such as `tests_pass` without `--full` or `gate_untouched` without a
        ref, is reported as "did not run" with the reason. With severity `block` the result then fails, because
        a check that was not evaluated has not passed. `allow_not_run=True` reports it without failing.
        """
        full_id = check_id if check_id.startswith("check.") else f"check.{check_id}"
        if full_id not in REGISTRY or REGISTRY[full_id].status is Status.LEFT_OUT:
            raise ValueError(f"unknown check {check_id}")
        if full_id in self._disabled:
            raise ValueError(f"{full_id} is disabled by policy.disable, so it is not reported and cannot fire")

        def violations(run: Run):
            result = run.checks.get(full_id)
            if run.comparison is None and full_id in DIFF_CHECKS:
                return []  # A run without --changes measures the code as it is and judges no diff.
            if result is None or not result.ran:
                return [NotRun(result.reason if result else "the check is not part of this run")]
            return result.failures

        self._conditions.append(Condition(full_id, Severity(severity), violations, allow_not_run))

    # Settings.

    def against(self, ref: str) -> None:
        if self._ref not in (None, ref):
            raise ValueError(f"a policy compares against one ref, already {self._ref}")
        self._ref = ref

    def exclude(self, *patterns: str) -> None:
        self._exclude = (*self._exclude, *patterns)

    def only(self, *patterns: str) -> None:
        """Restrict the run to the files that match one of the patterns. Further calls add patterns.

        A pattern is a shell-style glob in which `*` also matches `/`. A file matches by its path, by a folder
        above it (`code/domain` keeps everything below that folder) or by the name of its crate. Everything is
        still measured, because many values need the whole codebase. Then only the matching files and what they
        hold are reported and scored: a module, crate and the codebase take their lines and score from the kept
        files below them. One that is kept only in part has no values of its own, since those describe the whole
        of it; so a restricted run has no `codebase.*` value except the median function length of the kept
        functions. Gates judge the kept pieces, and a floor on a measurement of a piece kept in part did not run
        (`metric_floor`); the checks and the comparison with a ref still read the whole codebase. Patterns that
        keep every file give the run on the whole codebase. A run raises ValueError when no file matches.
        """
        self._only = (*self._only, *patterns)

    @property
    def only_patterns(self) -> tuple[str, ...]:
        """The patterns given to `only`. Empty for a run on the whole codebase."""
        return self._only

    def dependency_rule(self, source: str, target: str, *, allow: bool = True, reason: str = "") -> None:
        """Allow or forbid dependencies from what matches `source` to what matches `target`.

        A pattern is a shell-style glob in which `*` also matches `/`. It matches a crate by its name, its folder or
        the path of its Cargo.toml, and a file by its path or, seen from another crate, by any of these three names
        of its crate. So a crate or file added later
        is covered by every rule whose pattern it matches, without a change to the policy.

        check.layer_violations reads the rules. It checks each dependency of one workspace crate on another
        (Cargo.toml, without dev-dependencies) and each `use` of one production file by another. The last rule that
        matches a dependency decides it. With no matching rule, a dependency between two crates is a violation, and
        a dependency between two files of one crate is allowed. For files of one crate only the file paths are matched.
        Without any rule the check is skipped. The check changes the exit code only after `policy.check("layer_violations")`.
        """
        self._dependency_rules.append(DependencyRule(source, target, allow, reason))

    def deciding_rule(self, source_names: Iterable[str], target_names: Iterable[str]) -> DependencyRule | None:
        """The last dependency rule that covers both ends, or None."""
        source_names, target_names = tuple(source_names), tuple(target_names)
        covering = [rule for rule in self._dependency_rules if rule.covers(source_names, target_names)]
        return covering[-1] if covering else None

    def layer(self, name: str, *patterns: str) -> None:
        """Name the paths of a layer. Only diff.layers_touched reads the names; dependency rules use patterns."""
        self._layers[name] = patterns

    def layer_of(self, path: str) -> str | None:
        """The first named layer with a pattern that matches the path."""
        for name, patterns in self._layers.items():
            if any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
                return name
        return None

    def gate_files(self, *patterns: str) -> None:
        self._gate_files = list(patterns)

    def pr_size(self, *, lines: int, files: int) -> None:
        self.setting("pr_size_lines", lines)
        self.setting("pr_size_files", files)

    def suppression_exceptions(self, *patterns: str) -> None:
        self._suppression_exceptions = list(patterns)

    def ignore_unused_dependencies(self, *names: str) -> None:
        self._unused_dependency_ignores.update(names)

    def effective_length(self, *, alpha: float) -> None:
        self.setting("effective_length_alpha", alpha)

    def slop_exempt(self, *patterns: str) -> None:
        """Paths the slop rules skip, such as documents that discuss slop."""
        self._slop_exempt = list(patterns)

    def slop_severity(self, rule_id: str, severity: str, *, at_limit: str | None = None) -> None:
        """Set the severity of one slop rule: `warn` or `metric`. Slop never blocks: no rule detects it reliably.

        `warn` counts in the two slop measurements, `metric` is reported only (setting `slop_counted_severities`). A rule that reports each hit and fires again at a
        limit, such as `len-words`, also takes `at_limit`, the severity of that second finding.
        Raises ValueError for an unknown rule or severity, and for `at_limit` on a rule without a limit finding.
        It is short for `policy.setting("slop_rule_<id>", {"severity": ...})`.
        """
        if rule_id not in SLOP_RULES:
            raise ValueError(f"unknown slop rule {rule_id}; --explain with no ID lists every rule")
        if at_limit is not None and rule_id not in LIMIT_RULES:
            raise ValueError(f"the slop rule {rule_id} has one finding and no limit; the rules with `at_limit` are {', '.join(LIMIT_RULES)}")
        self.setting(rule_setting(rule_id), {"severity": severity, **({"limit_severity": at_limit} if at_limit is not None else {})})

    def slop_allow(self, *rule_ids: str) -> None:
        """Rules this repository turns off, such as `meta-seam` where a seam is a glossary term."""
        self._slop_allow.update(rule_ids)

    def humans(self, *logins: str) -> None:
        """The GitHub logins that count as human reviewers. Further calls add to the list.

        A merged pull request is human-reviewed when the latest review of one of them is an approval; the
        `*.unreviewed_lines` and `*.unreviewed_line_share` measurements count the code lines outside such pull
        requests. Without a login they have no value. A login is compared without case.
        Raises ValueError for an empty login or one with an `@`: an email address is never stored.
        """
        for login in logins:
            if not isinstance(login, str) or not login.strip() or "@" in login:
                raise ValueError("policy.humans takes GitHub logins, such as `octocat`; an email address is not a login")
        self._humans.update(login.strip().lower() for login in logins)

    def history_window(self, commits: int) -> None:
        self.setting("history_window", commits)

    @property
    def conditions(self) -> list[Condition]:
        return self._conditions

    @property
    def custom_metrics(self) -> dict[str, CustomMetric]:
        return self._metrics

    @property
    def specs(self) -> dict[str, MetricSpec]:
        """Every measurement and check: the registry plus the policy's own measurements."""
        return {**REGISTRY, **{metric_id: metric.spec for metric_id, metric in self._metrics.items()}}

    @property
    def selection(self) -> dict[str, Scored]:
        """The selection in force: the measurements that feed the score, with their numbers."""
        return self._selection

    @property
    def settings(self) -> dict:
        """The settings in force, by name."""
        return self._settings

    def describe(self) -> dict:
        """What the policy enforces, as lists and mappings of texts and numbers that can be written as JSON:
        the ref, the gate files, each gate with its numbers, the selection, the settings and every other list.

        Two policies with equal descriptions judge a change alike, apart from the bodies of the functions a
        policy script wrote itself (`blocking`, `warning`, `metric`, `score_function`), which are named only.
        """
        return {
            "ref": self._ref,
            "gate files": sorted(self._gate_files),
            "gates": sorted(condition.describe() for condition in self._conditions),
            "selection": {metric_id: _describe_row(scored) for metric_id, scored in self._selection.items()},
            "settings": dict(self._settings),
            "disabled": sorted(self._disabled),
            "own measurements": sorted(self._metrics),
            "own score function": self._score_function is not None,
            "excluded paths": list(self._exclude),
            "only": list(self._only),
            "dependency rules": [f"{'allow' if rule.allow else 'forbid'} {rule.describe()}" for rule in self._dependency_rules],
            "suppression exceptions": list(self._suppression_exceptions),
            "ignored unused dependencies": sorted(self._unused_dependency_ignores),
            "slop exempt paths": list(self._slop_exempt),
            "slop rules turned off": sorted(self._slop_allow),
            "humans": sorted(self._humans),
        }

    def scoring_model(self) -> ScoringModel:
        specs = {metric_id: spec for metric_id, spec in self.specs.items() if metric_id not in self._disabled}
        return ScoringModel(self._selection, specs, self._settings, self._score_function)

    @property
    def ref(self) -> str | None:
        return self._ref

    @property
    def excluded(self) -> tuple[str, ...]:
        return self._exclude

    @property
    def dependency_rules(self) -> list[DependencyRule]:
        return self._dependency_rules

    @property
    def gate_patterns(self) -> list[str]:
        return self._gate_files

    @property
    def pr_limits(self) -> tuple[int, int]:
        return self._settings["pr_size_lines"], self._settings["pr_size_files"]

    @property
    def suppression_patterns(self) -> list[str]:
        return self._suppression_exceptions

    @property
    def dependency_ignores(self) -> set[str]:
        return self._unused_dependency_ignores

    @property
    def alpha(self) -> float:
        return self._settings["effective_length_alpha"]

    @property
    def slop_exempt_paths(self) -> list[str]:
        return self._slop_exempt

    @property
    def slop_allowed_rules(self) -> set[str]:
        return self._slop_allow

    @property
    def human_logins(self) -> frozenset[str]:
        """The logins given to `humans`, in lower case."""
        return frozenset(self._humans)

    @property
    def window(self) -> int:
        return self._settings["history_window"]
