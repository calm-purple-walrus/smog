"""Smog: code quality metrics, scores and merge conditions for Rust repositories.

Write a policy script that imports from here, then call `run(policy)`:

    from smog import Policy, run

    policy = Policy()
    policy.metric_floor("function.length", warn_below=0.95, block_below=0.9)

    @policy.blocking
    def no_sleep_in_domain(run):
        for piece in run.functions():
            if "domain" in piece.id and "sleep" in piece.item.text:
                yield piece, "calls sleep"

    run(policy)
"""

from smog.domain.code import Codebase, Crate, Function, Module, SourceFile, TypeDef
from smog.domain.curves import Curve, line_weighted_median, paragraph_penalty, score_from_penalty
from smog.domain.policy import Finding, Policy, Run, Severity
from smog.domain.registry import REGISTRY, Kind, MetricSpec, PieceKind, Status
from smog.domain.report import Report
from smog.domain.scoring import Piece, Scorecard
from smog.domain.selection import STANDARD_SELECTION
from smog.domain.settings import SETTINGS
from smog.infrastructure.run import analyze, run

__all__ = [
    "Codebase",
    "Crate",
    "Curve",
    "Finding",
    "Function",
    "Kind",
    "MetricSpec",
    "Module",
    "Piece",
    "PieceKind",
    "Policy",
    "REGISTRY",
    "Report",
    "Run",
    "SETTINGS",
    "STANDARD_SELECTION",
    "Scorecard",
    "Severity",
    "SourceFile",
    "Status",
    "TypeDef",
    "analyze",
    "line_weighted_median",
    "paragraph_penalty",
    "run",
    "score_from_penalty",
]
