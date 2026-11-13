"""Turning raw values into penalties and penalties into scores (design section 4.3)."""

import math

from smog.domain.settings import DEFAULT_SETTINGS

DEFAULT_POWER = 2.0
DEFAULT_KNEE = 3.0


def require_number(name: str, value, *, above: float | None = None, finite: bool = True) -> None:
    """Raise ValueError unless `value` is a real number, finite unless `finite` is False, and greater than `above` if given."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value) or (finite and math.isinf(value)):
        raise ValueError(f"{name} must be a {'finite ' if finite else ''}number, not {value!r}")
    if above is not None and not value > above:
        raise ValueError(f"{name} must be greater than {above:g}, not {value!r}")


class Curve:
    """Charges a value above `target`, one unit of penalty at `limit`.

    Past `knee` (in units of target-to-limit distance) the penalty grows on a straight line at the same
    slope, so one enormous item cannot dominate and further decline is never free.
    A range curve also charges values below `low_target`, one unit at `low_limit`.

    Raises ValueError for a number that is not finite (`knee` may be infinite: no straight line), a `power` or
    `knee` that is not above 0, or a `base` that is not above 1: such a curve charges nothing or gives a negative penalty.
    """

    def __init__(self, target, limit, power=DEFAULT_POWER, knee=DEFAULT_KNEE, low_target=None, low_limit=None, base=None):
        require_number("target", target)
        require_number("limit", limit)
        require_number("power", power, above=0)
        require_number("knee", knee, above=0, finite=False)
        for name, value in (("low_target", low_target), ("low_limit", low_limit)):
            if value is not None:
                require_number(name, value)
        if base is not None:
            require_number("base", base, above=1)
        if limit <= target:
            raise ValueError(f"limit {limit} must exceed target {target}")
        if (low_target is None) != (low_limit is None) or (low_target is not None and not low_limit < low_target <= target):
            raise ValueError("a range curve needs low_limit < low_target <= target")
        self._target = target
        self._limit = limit
        self._power = power
        self._knee = knee
        self._low_target = low_target
        self._low_limit = low_limit
        self._base = base

    @property
    def target(self):
        return self._target

    @property
    def limit(self):
        return self._limit

    def numbers(self) -> dict:
        """Every parameter of the curve, by the name `Policy.select` takes."""
        return {
            "target": self._target,
            "limit": self._limit,
            "power": self._power,
            "knee": self._knee,
            "low_target": self._low_target,
            "low_limit": self._low_limit,
            "base": self._base,
        }

    def charged_side(self, higher_is_better: bool = False) -> tuple[float, float]:
        """The target and limit to show for the curve: those of the low side when a higher value is better and
        the curve has one. Its high side then lies where no value reaches, such as a mutation score above 1."""
        if higher_is_better and self._low_target is not None:
            return self._low_target, self._low_limit
        return self._target, self._limit

    def describe(self, higher_is_better: bool = False) -> str:
        """The curve in words, from the values `penalty` computes with. For a measurement where a higher value is
        better, the low side alone when the curve has one."""
        target, limit = self._target, self._limit
        if higher_is_better and self._low_target is not None:
            rise = "in a straight line" if self._power == 1 else f"with the distance below the target to the power {self._power:g}"
            return f"No penalty from {self._low_target:g} up. Penalty 1 at {self._low_limit:g}, growing {rise}"
        if self._base is not None:
            rise = f"exponentially with base {self._base:g}"
        elif self._power == 1:
            rise = "in a straight line"
        else:
            rise = f"with the distance past the target to the power {self._power:g}"
        text = f"No penalty up to {target:g}. Penalty 1 at {limit:g}, growing {rise}"
        if self._base is None and self._power != 1 and self._knee != math.inf:
            text += f", then in a straight line past {target + self._knee * (limit - target):g}"
        if self._low_target is not None:
            text += f". Also charged below {self._low_target:g}, penalty 1 at {self._low_limit:g}"
        return text

    def penalty(self, value) -> float:
        if self._low_target is not None and value < self._low_target:
            return ((self._low_target - value) / (self._low_target - self._low_limit)) ** self._power
        if value <= self._target:
            return 0.0
        x = (value - self._target) / (self._limit - self._target)
        if self._base is not None:
            return (self._base**x - 1) / (self._base - 1)
        if x <= self._knee:
            return x**self._power
        slope = self._power * self._knee ** (self._power - 1)
        return self._knee**self._power + slope * (x - self._knee)


def paragraph_penalty(lines: int, settings: dict = DEFAULT_SETTINGS) -> float:
    """The charge for one code paragraph: free up to a size, cheap per line up to a tolerated size, then quadratic.

    Past the knee the charge continues on a straight line at the same slope (the tail form in section 4.3).
    The sizes and costs are the `paragraph_*` settings.
    """
    free, tolerated, knee = settings["paragraph_free_lines"], settings["paragraph_tolerated_lines"], settings["paragraph_knee_lines"]
    cheap, cost = settings["paragraph_tolerated_cost"], settings["paragraph_cost"]
    at_tolerated = cheap * (tolerated - free)
    if lines <= free:
        return 0.0
    if lines <= tolerated:
        return cheap * (lines - free)
    if lines <= knee:
        return at_tolerated + cost * (lines - tolerated) ** 2
    return at_tolerated + cost * (knee - tolerated) ** 2 + 2 * cost * (knee - tolerated) * (lines - knee)


def score_from_penalty(penalty: float, decay: float = DEFAULT_SETTINGS["score_decay"]) -> float:
    """The default step from a penalty to a score: e to the power of minus `decay` times the penalty (setting `score_decay`)."""
    return math.exp(-decay * penalty)


def line_weighted_median(pairs: list[tuple[float, int]]) -> float:
    """The value at which half of all lines sit in pieces with a smaller value. `pairs` is (value, lines)."""
    total = sum(lines for _, lines in pairs)
    if total == 0:
        return 0.0
    seen = 0
    for value, lines in sorted(pairs):
        seen += lines
        if seen * 2 >= total:
            return value
    return 0.0


def plain_number(value: float) -> str:
    """A measured value for a listing. A whole number below 10^15 is printed whole, such as `335544320`; any other value in short form with six digits."""
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:g}"
