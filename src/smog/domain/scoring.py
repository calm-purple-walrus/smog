"""Pieces of code, their penalties, and scores aggregated from function up to codebase (design section 4)."""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable

from smog.domain.curves import Curve, require_number, score_from_penalty
from smog.domain.registry import REGISTRY, MetricSpec, PieceKind
from smog.domain.settings import DEFAULT_SETTINGS


class Scored:
    """One row of a selection: how a measurement's value becomes a penalty, and which group it is charged in."""

    def __init__(self, curve: Curve, group: str, weight: float = 1.0):
        require_number("weight", weight, above=0)
        self._curve = curve
        self._group = group
        self._weight = weight

    @property
    def curve(self) -> Curve:
        return self._curve

    @property
    def group(self) -> str:
        return self._group

    @property
    def weight(self) -> float:
        return self._weight

    def penalty(self, value: float) -> float:
        return self._weight * self._curve.penalty(value)


class Piece:
    """A measured part of the codebase: its values and the pieces below it."""

    def __init__(self, kind: PieceKind, piece_id: str, lines: int, item=None, kept_in_part: bool = False):
        self._kept_in_part = kept_in_part
        self._kind = kind
        self._id = piece_id
        self._lines = lines
        self._item = item
        self._values: dict[str, float] = {}
        self._problems: dict[str, tuple[str, ...]] = {}
        self._children: list[Piece] = []

    @property
    def kind(self) -> PieceKind:
        return self._kind

    @property
    def id(self) -> str:
        return self._id

    @property
    def lines(self) -> int:
        return self._lines

    @property
    def item(self):
        """The code object behind the piece: a Function, TypeDef, SourceFile, Module, Crate or Codebase."""
        return self._item

    @property
    def kept_in_part(self) -> bool:
        """True for a module, a crate or the codebase of which a restricted run keeps only some files
        (`Policy.only`). Such a piece has no values of its own: they describe the whole of it."""
        return self._kept_in_part

    @property
    def values(self) -> dict[str, float]:
        return self._values

    @property
    def children(self) -> list["Piece"]:
        return self._children

    def add_child(self, piece: "Piece") -> None:
        self._children.append(piece)

    def set_values(self, values: dict[str, float]) -> None:
        self._values.update(values)

    def problems(self, metric_id: str) -> tuple[str, ...]:
        """What a policy's measurement named as the problems behind its value here, if it named any."""
        return self._problems.get(metric_id, ())

    def set_problems(self, metric_id: str, problems: tuple[str, ...]) -> None:
        self._problems[metric_id] = problems

    def value(self, metric_id: str, default: float = 0.0) -> float:
        return self._values.get(metric_id, default)

    def walk(self):
        yield self
        for child in self._children:
            yield from child.walk()


class ScoringModel:
    """What is measured and what is scored: the specs, the selection in force and the scoring settings.

    Only a measurement in the selection has a penalty. Every other value is carried on its piece and reported.
    `score_function` replaces the step from a penalty to a score (`Policy.score_function`).
    """

    def __init__(
        self,
        selection: dict[str, Scored],
        specs: dict[str, MetricSpec] | None = None,
        settings: dict | None = None,
        score_function: Callable[[float], float] | None = None,
    ):
        self._selection = selection
        self._specs = REGISTRY if specs is None else specs
        self._settings = DEFAULT_SETTINGS if settings is None else settings
        self._score_function = score_function

    @property
    def specs(self) -> dict[str, MetricSpec]:
        return self._specs

    @property
    def selection(self) -> dict[str, Scored]:
        return self._selection

    @property
    def settings(self) -> dict:
        return self._settings

    def lens_penalty(self, metric_id: str, value: float) -> float:
        scored = self._selection.get(metric_id)
        return scored.penalty(value) if scored else 0.0

    def group_penalties(self, piece: Piece, exclude_groups=()) -> dict[str, float]:
        """Per group of correlated measurements: the worst penalty plus a share of the others."""
        by_group: dict[str, list[float]] = defaultdict(list)
        for metric_id, value in piece.values.items():
            scored = self._selection.get(metric_id)
            if scored is None or scored.group in exclude_groups:
                continue
            penalty = scored.penalty(value)
            if penalty > 0:
                by_group[scored.group].append(penalty)
        share = self._settings["others_share"]
        return {group: max(penalties) + share * (sum(penalties) - max(penalties)) for group, penalties in by_group.items()}

    def penalty(self, piece: Piece, exclude_groups=()) -> float:
        return sum(self.group_penalties(piece, exclude_groups).values())

    def score_of(self, penalty: float) -> float:
        """A penalty as a score from 0 to 1: `exp(-score_decay * penalty)`, or what the policy's score function returns.

        Raises ValueError when the policy's function returns something that is no number from 0 to 1.
        """
        if self._score_function is None:
            return score_from_penalty(penalty, self._settings["score_decay"])
        return checked_score(self._score_function(penalty), penalty)

    def combine_worst(self, scores: Iterable[float]) -> float:
        """The scores of a file's items as one number: its `worst_items_in_file` lowest, combined as `worst_items_combine` says."""
        worst = sorted(scores)[: self._settings["worst_items_in_file"]]
        how = self._settings["worst_items_combine"]
        if how == "min":
            return worst[0]
        if how == "geometric_mean":
            return 0.0 if worst[0] <= 0 else math.exp(sum(math.log(score) for score in worst) / len(worst))
        return sum(worst) / len(worst)

    def weighted_mean(self, pairs: Iterable[tuple[float, int]]) -> float:
        """The mean of (value, lines) pairs, weighted as `aggregate_weight` says. 1.0 without a pair.

        Weighted by lines, a piece with fewer lines than `aggregate_min_lines` weighs that many: by default a
        piece without code lines weighs one line, so that its penalty reaches the pieces above it. A comment-only
        file can be charged for its length or its slop.
        """
        by_lines, least = self._settings["aggregate_weight"] == "lines", self._settings["aggregate_min_lines"]
        weighted = [(value, max(lines, least) if by_lines else 1) for value, lines in pairs]
        total = sum(weight for _, weight in weighted)
        if not weighted:
            return 1.0
        if total == 0:
            return sum(value for value, _ in weighted) / len(weighted)
        return sum(value * weight for value, weight in weighted) / total


def checked_score(score, penalty: float) -> float:
    """What a policy's score function returned for a penalty. Raises ValueError unless it is a number from 0 to 1."""
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise ValueError(f"the policy's score function returned {score!r} for the penalty {penalty:g}; a score is a number from 0 to 1")
    return score


class Scorecard:
    """Scores for one tree of pieces. An item's score is `exp(-penalty)`; a file takes the mean of its worst items;
    a module, crate and codebase take the line-weighted mean of what they contain. Each level also charges its
    own selected measurements. Each of these steps reads its settings from the model (`ScoringModel`)."""

    def __init__(self, root: Piece, model: ScoringModel):
        self._root = root
        self._model = model
        self._scores: dict[int, float] = {}
        self._by_id: dict[tuple, Piece] = {(piece.kind, piece.id): piece for piece in root.walk()}

    @property
    def root(self) -> Piece:
        return self._root

    @property
    def model(self) -> ScoringModel:
        return self._model

    def pieces(self, *kinds: PieceKind) -> list[Piece]:
        return [piece for piece in self._root.walk() if piece.kind in kinds]

    def find(self, kind: PieceKind, piece_id: str) -> Piece | None:
        return self._by_id.get((kind, piece_id))

    def score(self, piece: Piece | None = None) -> float:
        piece = piece or self._root
        key = id(piece)
        if key not in self._scores:
            self._scores[key] = self._compute(piece)
        return self._scores[key]

    def _compute(self, piece: Piece) -> float:
        own = self._model.score_of(self._model.penalty(piece))
        if not piece.children:
            return own
        if piece.kind is PieceKind.FILE:
            return own * self._model.combine_worst(self.score(child) for child in piece.children)
        return own * self._model.weighted_mean((self.score(child), child.lines) for child in piece.children)

    def metric_score(self, metric_id: str, piece: Piece | None = None) -> float | None:
        """One selected measurement as a score: the score of its penalty where it applies, as a weighted mean over the pieces below (`ScoringModel.weighted_mean`). None if unmeasured or not selected."""
        piece = piece or self._root
        if metric_id not in self._model.selection:
            return None
        pairs = [
            (self._model.score_of(self._model.lens_penalty(metric_id, p.value(metric_id))), p.lines)
            for p in piece.walk()
            if metric_id in p.values
        ]
        return self._model.weighted_mean(pairs) if pairs else None

    def metric_values(self, metric_id: str) -> list[tuple[Piece, float, float | None]]:
        """Each piece measured by this metric, with its value and its score, worst first. The score is None if the metric is not selected.

        A selected metric is ordered by score. An unselected one is ordered by value: highest first, or lowest
        first when the registry says a higher value is better.
        """
        charged = metric_id in self._model.selection
        spec = self._model.specs.get(metric_id)
        worst_is_high = -1 if spec is None or not spec.higher_is_better else 1
        rows = [
            (p, p.values[metric_id], self._model.score_of(self._model.lens_penalty(metric_id, p.values[metric_id])) if charged else None)
            for p in self._root.walk()
            if metric_id in p.values
        ]
        return sorted(rows, key=lambda row: (row[2] if charged else worst_is_high * row[1], row[0].id))

    def debt(self, piece: Piece | None = None) -> float:
        """Sum of penalties over every piece below. It adds up across changes, unlike a mean."""
        return sum(self._model.penalty(p) for p in (piece or self._root).walk())
