"""The result of one run."""

from smog.domain.policy import Finding, Severity, kept_in_part_reason
from smog.domain.registry import PieceKind, Status
from smog.domain.scoring import Scorecard
from smog.domain.tools import WITHOUT_FULL, ToolResults


def selected_without_value(card: Scorecard, tools: ToolResults | None, humans_listed: bool) -> tuple[dict[str, str], dict[str, str]]:
    """Each measurement of the selection in force that no piece has a value for in this run, with the reason; and
    the part of those whose data is missing, such as review data or a slow tool's result.

    A selected measurement with missing data makes the score wrong, so the run then gives no score.
    """
    valued = {metric_id for piece in card.root.walk() for metric_id in piece.values}
    unvalued, missing = {}, {}
    for metric_id in card.model.selection:
        if metric_id in valued:
            continue
        reason, data_missing = _why_no_value(metric_id, card, tools, humans_listed)
        unvalued[metric_id] = reason
        if data_missing:
            missing[metric_id] = reason
    return unvalued, missing


def _why_no_value(metric_id: str, card: Scorecard, tools: ToolResults | None, humans_listed: bool) -> tuple[str, bool]:
    """The reason, and whether data the measurement needs is missing (as opposed to nothing to measure)."""
    spec = card.model.specs.get(metric_id)
    name = metric_id.partition(".")[2]
    if card.root.kept_in_part and spec is not None and spec.piece is PieceKind.CODEBASE:
        return kept_in_part_reason(metric_id, [card.root]), False
    if name.startswith("unreviewed_"):
        if not humans_listed:
            return "the policy lists no humans (policy.humans), so review is not measured", False
        return (f"no review data: {tools.notes['reviews']}" if tools and "reviews" in tools.notes else "no review data"), True
    if metric_id in ("codebase.mutation_score", "codebase.covered_mutation_score") and tools and tools.mutants is not None and not tools.mutants_whole_tree:
        return (
            "cargo-mutants changed only the lines that differ from the ref (`mutants_scope` is `diff`), which describes the change "
            "and not the codebase; `--mutants tree` measures it"
        ), True
    if spec is None or spec.status is not Status.FULL_ONLY:
        return f"no {spec.piece.value if spec else 'piece'} has a value for it", False
    needs = f" {spec.note}" if spec.note else ""
    if tools is None or WITHOUT_FULL in tools.notes:
        return f"needs --full.{needs}", True
    return f"its slow tool did not run or found nothing to measure; `Slow tools` lists what did not run.{needs}", True


class Report:
    def __init__(
        self, card: Scorecard, findings: list[Finding], checks: dict, slop: list, comparison=None, history=None, tools=None, diff_values=None, unvalued=None,
        missing=None, restriction=None, policy_change=None,
    ):  # fmt: skip
        self._policy_change = policy_change
        self._card = card
        self._findings = findings
        self._checks = checks
        self._slop = slop
        self._comparison = comparison
        self._history = history
        self._tools = tools
        self._diff_values = diff_values or {}
        self._unvalued = unvalued or {}
        self._missing = missing or {}
        self._restriction = restriction

    @property
    def card(self) -> Scorecard:
        return self._card

    @property
    def findings(self) -> list[Finding]:
        return self._findings

    @property
    def blocks(self) -> list[Finding]:
        return [finding for finding in self._findings if finding.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        return [finding for finding in self._findings if finding.severity is Severity.WARN]

    @property
    def not_run(self) -> list[Finding]:
        """Gates that could not be evaluated and do not fail the result: warning-level ones and those the policy allows not to run.

        A blocking gate that did not run and is not allowed to is in `blocks`.
        """
        return [finding for finding in self._findings if finding.severity is Severity.NOT_RUN]

    @property
    def checks(self) -> dict:
        return self._checks

    @property
    def slop(self) -> list:
        return self._slop

    @property
    def comparison(self):
        return self._comparison

    @property
    def history(self):
        return self._history

    @property
    def tools(self):
        return self._tools

    @property
    def diff_values(self) -> dict[str, float]:
        return self._diff_values

    @property
    def unvalued(self) -> dict[str, str]:
        """Each selected measurement without a value in this run, with the reason (`selected_without_value`)."""
        return self._unvalued

    @property
    def missing(self) -> dict[str, str]:
        """Each selected measurement whose data is missing in this run, with the reason. The run then has no score."""
        return self._missing

    @property
    def restriction(self) -> tuple[tuple[str, ...], int, int] | None:
        """For a run restricted with `Policy.only`: its patterns, the files kept and the files of the codebase. Else None."""
        return self._restriction

    @property
    def policy_change(self):
        """The policy script compared with the ref (`PolicyChange`), or None without a ref or when the run does not know its script."""
        return self._policy_change

    @property
    def exit_code(self) -> int:
        """2 when data for the score is missing, 1 when a condition blocks, else 0."""
        return 2 if self.missing else 1 if self.blocks else 0
