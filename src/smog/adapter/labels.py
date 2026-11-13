"""Plain descriptions of metrics and checks, for the condensed overview. The text lives in `smog.domain.explanations`."""

from smog.domain.explanations import EXPLANATIONS

PROBLEMS = {policy_id: text["title"] for policy_id, text in EXPLANATIONS.items() if not policy_id.startswith("check.")}
CHECKS = {policy_id: text["title"] for policy_id, text in EXPLANATIONS.items() if policy_id.startswith("check.")}


def problem(metric_id: str) -> str:
    return PROBLEMS.get(metric_id, metric_id)


def check_label(check_id: str) -> str:
    return CHECKS.get(check_id, check_id)
