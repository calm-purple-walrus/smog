"""What a policy ID means and what to do about it. Joins the registry, the policy's selection and settings, and the hand-written text."""

import difflib
import math
import re

from smog.domain.explanations import EXPLANATIONS
from smog.domain.policy import Policy
from smog.domain.registry import Kind, MetricSpec, PieceKind, Status
from smog.domain.settings import SETTINGS
from smog.domain.slop_explanations import SEVERITY_EFFECTS, SLOP_EXPLANATIONS
from smog.domain.slop import rule_set
from smog.domain.slop_rules import RULES, list_setting, rule_setting

_SHARED_PIECES = (PieceKind.CODEBASE, PieceKind.DIFF)
_CUSTOM_IMPROVE = "Read the metric's function in the policy script, then change the code it measures."
_FIELDS = (
    "id", "type", "title", "kind", "status", "piece", "selected", "group", "section", "design_name", "target", "limit", "weight", "shape", "curve",
    "settings", "value", "default", "affects", "accuracy",
    "accuracy_note", "heuristic", "measures", "improve", "gaming", "policy", "policy_note", "defined_by_policy", "docstring", "severity",
    "severity_effect", "class", "scope", "strip", "source", "matches", "exceptions", "threshold", "replacements", "turned_off", "disabled",
)  # fmt: skip


def explain(policy: Policy, wanted: str) -> dict | None:
    """One explanation with stable field names, or None for an unknown ID."""
    if wanted in RULES:
        return _slop_entry(wanted, policy)
    if wanted in SETTINGS:
        return _setting_entry(wanted, policy)
    spec = policy.specs.get(wanted)
    return _metric_entry(spec, policy) if spec else None


def explain_all(policy: Policy) -> list[dict]:
    return [explain(policy, policy_id) for policy_id in all_ids(policy)]


def all_ids(policy: Policy) -> list[str]:
    return [*policy.specs, *RULES, *SETTINGS]


def closest_ids(policy: Policy, wanted: str) -> list[str]:
    return difflib.get_close_matches(wanted, all_ids(policy), n=5, cutoff=0.4)


def _fill(text: str | None, settings: dict) -> str | None:
    """Replace each `{setting_name}` in a hand-written text with the value in force."""

    def value(match) -> str:
        found = settings.get(match.group(1))
        if found is None:
            return match.group(0)
        if isinstance(found, (str, bool)):
            return str(found)
        if isinstance(found, tuple):
            return ", ".join(str(item) for item in found)
        return str(int(found)) if float(found).is_integer() else f"{found:.3g}"

    return re.sub(r"\{([a-z][a-z0-9_]*)\}", value, text) if text else text


def _entry(**values) -> dict:
    return {**dict.fromkeys(_FIELDS), **values}


def _metric_entry(spec: MetricSpec, policy: Policy) -> dict:
    custom = policy.custom_metrics.get(spec.id)
    text = {} if custom else EXPLANATIONS[spec.id]
    doc = custom.doc if custom else ""
    measures = f"Defined by the policy script. {doc}".strip() if custom else _fill(text["measures"], policy.settings)
    title = (doc.splitlines()[0] if doc else spec.design_name) if custom else text["title"]
    scored = policy.selection.get(spec.id)
    curve = scored.curve if scored else None
    heuristic = text.get("heuristic", False)
    return _entry(
        id=spec.id,
        type="metric",
        title=title,
        kind=spec.kind.value,
        status=spec.status.value,
        piece=spec.piece.value,
        selected=scored is not None,
        group=scored.group if scored else None,
        section=spec.section,
        design_name=spec.design_name,
        target=curve.target if curve else None,
        limit=curve.limit if curve else None,
        weight=scored.weight if scored else None,
        shape=_shape(curve) if curve else None,
        curve=_target_text(spec, scored),
        settings={name: policy.settings[name] for name, row in SETTINGS.items() if spec.id in row[2]} or None,
        accuracy=_accuracy(spec, heuristic),
        accuracy_note=spec.note or None,
        heuristic=heuristic,
        measures=measures,
        improve=_CUSTOM_IMPROVE if custom else text["improve"],
        gaming=_fill(text.get("gaming"), policy.settings),
        policy=_policy_call(spec, text, scored is not None),
        policy_note=_policy_note(spec),
        defined_by_policy=custom is not None,
        disabled=spec.id in policy.disabled,
        docstring=doc or None,
    )


def _shape(curve) -> dict:
    """The curve numbers besides target and limit. A knee of None means the curve never turns into a straight line."""
    shape = {name: value for name, value in curve.numbers().items() if name not in ("target", "limit")}
    return {**shape, "knee": None if shape["knee"] == math.inf else shape["knee"]}


def _target_text(spec: MetricSpec, scored) -> str:
    where = f"{'the' if spec.piece in _SHARED_PIECES else 'each'} {spec.piece.value}"
    if spec.status is Status.LEFT_OUT:
        return "None. Left out, so it has no value."
    if spec.kind is Kind.CHECK:
        return "None. Pass/fail check: it never feeds the score, and changes the exit code only if the policy calls policy.check."
    if spec.piece is PieceKind.DIFF:
        return "None. A value of the diff against the ref: reported and never charged to the score."
    if scored is None:
        return (
            f"None. Not in the selection in force: measured on {where} and reported, not charged to the score. "
            f'policy.select("{spec.id}", target=..., limit=..., group=...) adds it.'
        )
    weight = f" Penalty times weight {scored.weight:g}." if scored.weight != 1.0 else ""
    curve = scored.curve
    target, limit = curve.charged_side(spec.higher_is_better)
    return f"{target:g}, limit {limit:g} (in the selection in force, on {where}, group {scored.group}). {curve.describe(spec.higher_is_better)}.{weight}"


def _needs_review_data(spec: MetricSpec) -> bool:
    """True for the human-review measurements. They have a value only with review data, which a file gives
    without `--full`; their registry note says how."""
    return spec.id.partition(".")[2].startswith("unreviewed_")


def _accuracy(spec: MetricSpec, heuristic: bool) -> str:
    if spec.status is Status.LEFT_OUT:
        return f"Left out: {spec.note}"
    if _needs_review_data(spec):
        return spec.note
    if spec.status is Status.FULL_ONLY:
        return f"Needs --full: {spec.note}"
    if spec.status is Status.APPROXIMATE:
        return f"Approximate: {spec.note}"
    if heuristic:
        return f"Computed from a match on names or text, see Measures. {spec.note}".strip()
    return f"Computed. {spec.note}" if spec.note else "Exact"


def _policy_call(spec: MetricSpec, text: dict, selected: bool) -> str | None:
    metric_id = spec.id
    if spec.status is Status.LEFT_OUT:
        return None
    if "policy" in text:
        return text["policy"]
    if spec.kind is Kind.CHECK:
        return f'policy.check("{metric_id.removeprefix("check.")}")'
    if selected:
        return f'policy.select("{metric_id}", target=..., limit=...)'
    if spec.piece is PieceKind.DIFF:
        return 'policy.against("main")'
    if spec.piece is PieceKind.FUNCTION:
        return f'policy.any_function("{metric_id}", above=...)'
    condition = f'((piece, "{metric_id} too high") for piece in run.pieces("{spec.piece.value}") if piece.value("{metric_id}") > ...)'
    return f'policy.warning(lambda run: {condition}, name="{metric_id}")'


def _policy_note(spec: MetricSpec) -> str | None:
    notes = []
    if spec.piece is PieceKind.DIFF and spec.status is not Status.LEFT_OUT:
        notes.append("Sets the ref; the value then appears in --comprehensive.")
    if spec.status is Status.FULL_ONLY and not _needs_review_data(spec):
        notes.append("Run with --full.")
    return " ".join(notes) or None


def _setting_entry(name: str, policy: Policy) -> dict:
    default, title, affects = SETTINGS[name]
    return _entry(
        id=name,
        type="setting",
        title=title,
        kind="setting",
        value=policy.settings[name],
        default=default,
        affects=list(affects),
        policy=f'policy.setting("{name}", {default!r})',
        policy_note="This policy sets policy.score_function, so the value is not read." if name == "score_decay" and policy.has_score_function else None,
    )


def _slop_entry(rule_id: str, policy: Policy) -> dict:
    """A slop rule with the parameters in force: the severity, patterns, exceptions and word lists of the policy's settings."""
    rule, text, settings = RULES[rule_id], SLOP_EXPLANATIONS[rule_id], policy.settings
    parameters = settings[rule_setting(rule_id)]
    patterns = parameters.get("patterns", ())
    homonyms = settings["slop_homonyms"]
    return _entry(
        id=rule_id,
        type="slop_rule",
        title=text["title"],
        kind="slop",
        status="computed" if rule["kind"] == "computed" else "pattern",
        accuracy="Regular expression match" if patterns else "Computed from counts",
        heuristic=True,
        measures=_fill(text["measures"], settings),
        improve=text["improve"],
        gaming=text.get("gaming"),
        settings={name: settings[name] for name, row in SETTINGS.items() if rule_id in row[2] and name != rule_setting(rule_id)} or None,
        policy=f'policy.slop_allow("{rule_id}")',
        severity=parameters["severity"],
        severity_effect=SEVERITY_EFFECTS[parameters["severity"]]
        + (f" At its limit the rule adds a finding of severity {parameters['limit_severity']}." if "limit_severity" in parameters else "")
        + f' `policy.slop_severity("{rule_id}", ...)` changes the severity, and the setting {rule_setting(rule_id)} holds every parameter of the rule.',
        scope=rule["scope"],
        strip=rule["strip"],
        source=rule["source"],
        matches=_matches(rule_id, patterns, text, settings),
        exceptions=[excepted for _, _, excepted in homonyms if excepted] if rule_id == "vocab-context" else list(parameters.get("exceptions", ())),
        threshold=_fill(text.get("limit"), settings),
        replacements=_replacements(patterns, text, settings),
        turned_off=rule_id in policy.slop_allowed_rules,
        **{"class": rule["class"]},
    )


def _rule_lists(patterns: tuple, text: dict) -> list[str]:
    found = [name for pattern in patterns for name in re.findall(r"\{list:(\w+)\}", pattern)]
    return [*found, *text.get("lists", ())]


def _matches(rule_id: str, patterns: tuple, text: dict, settings: dict) -> list[str]:
    if rule_id == "vocab-context":
        return [match for _, match, _ in settings["slop_homonyms"]]
    rules = rule_set(settings)
    readable = [re.sub(r"\(\?<!\\w\)(\(\?:.*?\))\(\?!\\w\)", r"\1", rules.expand(pattern)) if "{list:" in pattern else rules.expand(pattern) for pattern in patterns]
    return [*readable, *(entry[0] for name in text.get("lists", ()) for entry in settings[list_setting(name)])]


def _replacements(patterns: tuple, text: dict, settings: dict) -> dict[str, str]:
    return {entry[0]: entry[1] for name in _rule_lists(patterns, text) for entry in settings[list_setting(name)] if entry[1]}
