"""Prints the overview at the requested coarseness."""

from collections import Counter

from smog.adapter.labels import check_label, problem
from smog.domain.curves import plain_number
from smog.domain.registry import PieceKind, Status
from smog.domain.code import Function, Module
from smog.domain.lenses.function import paragraph_spans
from smog.domain.lenses.structure import module_folder
from smog.domain.report import Report
from smog.domain.slop_explanations import SLOP_EXPLANATIONS
from smog.domain.tools import NOT_SELECTED, WITHOUT_FULL

NO_POLICY_CALL = "None: Smog does not compute this."
LEVELS = {
    "codebase": PieceKind.CODEBASE,
    "crate": PieceKind.CRATE,
    "module": PieceKind.MODULE,
    "file": PieceKind.FILE,
    "function": PieceKind.FUNCTION,
}
PLURALS = {"crate": "crates", "module": "modules", "file": "files", "function": "functions"}


def render(report: Report, level: str, comprehensive: bool = False, failures: str | None = None, files_by_crate: bool = False) -> str:
    """The condensed overview by default, every piece, finding and metric, only the check failures, or every
    file under its crate."""
    if failures is not None:
        return "\n".join(_failures(report, failures))
    if report.missing:
        return "\n".join(_no_score(report) + (["", *_findings(report)] if report.findings else [])).rstrip()
    if files_by_crate:
        return "\n".join(_files_by_crate(report))
    return "\n".join(_comprehensive(report, level) if comprehensive else _condensed(report, level))


def metric_data(report: Report, metric_id: str) -> dict:
    """One metric's value and score for each piece it measures, worst first, plus the codebase score of the metric."""
    card = report.card
    pieces = [
        {"piece": piece.id, "kind": piece.kind.value, "lines": piece.lines, "value": value, "score": score}
        for piece, value, score in card.metric_values(metric_id)
    ]
    selected = metric_id in card.model.selection
    spec = card.model.specs.get(metric_id)
    return {
        "id": metric_id,
        "title": problem(metric_id),
        "selected": selected,
        "higher_is_better": bool(spec and spec.higher_is_better),
        "codebase_score": card.metric_score(metric_id) if pieces else None,
        "no_value": report.unvalued.get(metric_id),
        "missing": report.missing.get(metric_id),
        "pieces": pieces,
        "note": spec.note if spec else "",
        **_coupled_pairs(report, metric_id),
    }


def _coupled_pairs(report: Report, metric_id: str) -> dict:
    """The file pairs behind file.change_coupling. The per-file value is the highest degree among a file's pairs."""
    if metric_id != "file.change_coupling" or report.history is None:
        return {}
    keys = ("file", "coupled", "degree", "shared_commits", "average_commits")
    return {"pairs": [dict(zip(keys, pair)) for pair in report.history.change_coupling()]}


def render_metric(report: Report, data: dict) -> str:
    lines = [f"{data['id']}: {data['title']}"]
    if not data["pieces"]:
        missing = "No piece has a value for this metric."
        if data.get("missing"):
            missing += f" It is in the selection in force and its data is missing, so this run has no score: {data['missing']}"
        elif data.get("no_value"):
            missing += f" It is in the selection in force and charges nothing in this run: {data['no_value']}"
        if data.get("note"):
            missing += f" What it needs: {data['note']}"
        tools = report.tools.notes if report.tools else {}
        return "\n".join(lines + [missing] + [f"  not run: {name}: {note}" for name, note in sorted(tools.items())])
    if data["codebase_score"] is None:
        order = "lowest first, because a higher value is better" if data["higher_is_better"] else "highest first"
        lines.append(f"Not in the selection in force, so this metric has no score. Pieces are listed by value, {order}.")
    else:
        lines.append(f"Codebase score of this metric  {data['codebase_score']:.3f}/1")
    lines.append(f"  {'score':<5}  {'value':>12}  {'kind':<8}  piece")
    for row in data["pieces"]:
        score = "-" if row["score"] is None else f"{row['score']:.3f}"
        lines.append(f"  {score:<5}  {plain_number(row['value']):>12}  {row['kind']:<8}  {row['piece']}")
    if data.get("pairs"):
        lines.append("Pairs, by degree: 100 x shared commits / average commits of the two files")
        lines.append(f"  {'degree':>6}  {'shared':>6}  {'average':>7}  files")
        for pair in data["pairs"]:
            lines.append(f"  {pair['degree']:>6.1f}  {pair['shared_commits']:>6}  {pair['average_commits']:>7.1f}  {pair['file']}  {pair['coupled']}")
    return "\n".join(lines)


def render_explanation(entry: dict) -> str:
    """One policy ID, as labeled lines. A slop rule also shows its matches, severity, limit and replacements."""
    if entry["type"] == "slop_rule":
        rows = [
            ("Measures", entry["measures"]),
            ("Matches", "; ".join(entry["matches"]) or "Computed from counts, see Measures"),
            ("Except", "; ".join(entry["exceptions"])),
            ("Severity", f"{entry['severity']}. {entry['severity_effect']}"),
            ("Limit", entry["threshold"]),
            ("Settings", ", ".join(f"{name} = {value!r}" for name, value in (entry["settings"] or {}).items())),
            ("Replace", "; ".join(f"{match} -> {use}" for match, use in entry["replacements"].items())),
        ]
    elif entry["type"] == "setting":
        rows = [("Value", f"{entry['value']!r} (default {entry['default']!r})"), ("Changes", ", ".join(entry["affects"]))]
    else:
        settings = ", ".join(f"{name} = {value!r}" for name, value in (entry["settings"] or {}).items())
        rows = [("Measures", entry["measures"]), ("Target", entry["curve"]), ("Settings", settings), ("Accuracy", entry["accuracy"])]
    rows.extend(
        (
            ("To improve", entry["improve"]),
            ("Gaming", entry["gaming"]),
            ("Policy", " ".join(part for part in (entry["policy"] or NO_POLICY_CALL, entry["policy_note"]) if part)),
        )
    )
    if entry["turned_off"]:
        rows.append(("State", "Turned off by this policy."))
    if entry["disabled"]:
        rows.append(("State", "Disabled by this policy with policy.disable: not reported and not scored."))
    return "\n".join([f"{entry['id']}: {entry['title']}", *(f"{label:<10} {value}" for label, value in rows if value)])


def render_explanation_list(entries: list[dict]) -> str:
    width = max(len(entry["id"]) for entry in entries)
    return "\n".join(f"{entry['id']:<{width}}  {entry['title']}" for entry in entries)


def _condensed(report: Report, level: str) -> list[str]:
    card = report.card
    lines = [f"Score  {card.score():.3f}/1", *_restriction(report), *_unreadable(report), ""]
    lines.extend(_scores(report, level, False))
    lines.extend(changed_functions(report))
    lines.extend(_findings(report))
    lines.extend(_check_summary(report))
    lines.extend(_tool_failures(report))
    lines.extend(_slop_list(report))
    return lines


def _unreadable(report: Report) -> list[str]:
    unreadable = report.card.root.item.unreadable
    if not unreadable:
        return []
    return [f"Not read, so left out ({len(unreadable)}):", *(f"  {path}: {reason}" for path, reason in sorted(unreadable.items()))]


def _restriction(report: Report) -> list[str]:
    if report.restriction is None:
        return []
    patterns, kept, total = report.restriction
    if not report.card.root.kept_in_part:
        return [f"Restricted to     {', '.join(patterns)}: {kept} of {total} files."]
    return [
        f"Restricted to     {', '.join(patterns)}: {kept} of {total} files. The score and every listing cover these files only;",
        "                  values of the whole codebase, and of a crate or module kept in part, are left out.",
    ]


def _failures(report: Report, wanted: str) -> list[str]:
    wanted_id = wanted if wanted.startswith("check.") else f"check.{wanted}"
    failed = {check_id: result for check_id, result in sorted(report.checks.items()) if result.ran and not result.passed}
    selected = failed if wanted == "all" else {check_id: result for check_id, result in failed.items() if check_id == wanted_id}
    if not selected:
        return ["No failed checks." if wanted == "all" else f"No failed check called {wanted_id}."]
    lines = []
    for check_id, result in selected.items():
        lines.append(f"{check_label(check_id)}  ({check_id})")
        lines.extend(f"  {check_id}  {where}: {what}" for where, what in result.failures)
        lines.append("")
    return lines


def _comprehensive(report: Report, level: str) -> list[str]:
    """The overview with every entry listed, then the score settings and what lowers the score."""
    lines = [f"Score  {report.card.score():.3f}/1", *_restriction(report), *_unreadable(report), ""]
    lines.extend(_scores(report, level, True))
    lines.extend(changed_functions(report))
    lines.extend(_findings(report))
    lines.extend(_all_checks(report))
    lines.extend(_tool_failures(report))
    lines.extend(_slop_list(report))
    lines.extend(_selection(report))
    lines.extend(_metrics(report))
    return lines


def _all_checks(report: Report) -> list[str]:
    """Every check: failed ones with each failure, passed ones, and those that did not run with the reason."""
    lines = ["Checks:"]
    # check.project_conventions only stands for the policy's own conditions, which are listed under Blocks and Warnings.
    for check_id, result in sorted((item for item in report.checks.items() if item[0] != "check.project_conventions")):
        if not result.ran:
            lines.append(f"  ⏭️  {check_id}: did not run: {result.reason}")
        elif result.passed:
            lines.append(f"  ✅ {check_id}: passed")
        else:
            lines.append(f"  ❌ {check_label(check_id)}  {check_id}")
            lines.extend(f"      {where}: {what}" for where, what in result.failures)
    lines.append("")
    return lines


def _scores(report: Report, level: str, show_all: bool) -> list[str]:
    card = report.card
    if level == "codebase":
        return []
    pieces = sorted(card.pieces(LEVELS[level]), key=lambda piece: (card.score(piece), piece.id))
    shown = pieces if show_all else pieces[: card.model.settings["display_pieces"]]
    rows = []
    for piece in shown:
        score = card.score(piece)
        # A score printed as 1.000 has no penalty worth naming, so the row names no main problem.
        policy_id = "" if f"{score:.3f}" == "1.000" else _costliest_lens(card, piece)
        rows.append((score, piece.id, _problem(card, policy_id) if policy_id else "", policy_id, _worst_place(card, piece, policy_id)))
    name_width = max((len(row[1]) for row in rows), default=0)
    problem_width = max([len(row[2]) for row in rows] + [len("main problem")])
    lines = [
        f"All {PLURALS[level]}, worst first:" if show_all else f"Worst {PLURALS[level]}:",
        f"  {'score':<5}  {level:<{name_width}}  {'main problem':<{problem_width}}  policy ID",
    ]
    for score, name, label, policy_id, place in rows:
        lines.append(f"  {score:.3f}  {name:<{name_width}}  {label:<{problem_width}}  {policy_id}".rstrip())
        if place:
            lines.append(f"         {place}")
    first = next((row[3] for row in rows if row[3]), "")
    if first:
        lines.append(f"Every piece behind a problem, worst first: --metric <policy ID>, as in --metric {first}")
    lines.append("")
    return lines


def _files_by_crate(report: Report) -> list[str]:
    """Each crate, worst first, with every file of it, worst first: score, main problem, policy ID and where the
    problem is."""
    card = report.card
    lines = [f"Score  {card.score():.3f}/1", *_restriction(report), ""]
    for crate in sorted(card.pieces(PieceKind.CRATE), key=lambda piece: (card.score(piece), piece.id)):
        files = sorted((piece for piece in crate.walk() if piece.kind is PieceKind.FILE), key=lambda piece: (card.score(piece), piece.id))
        rows = []
        for piece in files:
            score = card.score(piece)
            policy_id = "" if f"{score:.3f}" == "1.000" else _costliest_lens(card, piece)
            rows.append((score, piece.id, _problem(card, policy_id) if policy_id else "", policy_id, _worst_place(card, piece, policy_id) if policy_id else ""))
        name_width = max((len(row[1]) for row in rows), default=0)
        problem_width = max((len(row[2]) for row in rows), default=0)
        lines.append(f"{card.score(crate):.3f}  {crate.id}")
        for score, name, label, policy_id, place in rows:
            lines.append(f"  {score:.3f}  {name:<{name_width}}  {label:<{problem_width}}  {policy_id}".rstrip())
            if place:
                lines.append(f"         {place}")
        lines.append("")
    return lines


def _worst_place(card, piece, metric_id: str) -> str:
    place = _place(card, piece, metric_id)
    problems = _worst_problems(card, piece, metric_id)
    if not problems:
        return place
    return f"{place}: {'; '.join(problems)}" if place else "; ".join(problems)


def _worst_problems(card, piece, metric_id: str) -> tuple[str, ...]:
    """The problems a policy's measurement named for the part of the piece it charges most."""
    worst = _worst_child(card, piece, metric_id)
    return worst.problems(metric_id) if worst else ()


def _worst_child(card, piece, metric_id: str):
    charged = [(card.model.lens_penalty(metric_id, child.values[metric_id]) * max(child.lines, 1), child) for child in piece.walk() if metric_id in child.values]
    return max(charged, key=lambda entry: entry[0])[1] if charged else None


def _place(card, piece, metric_id: str) -> str:
    """Where the measurement costs the piece most: the part of it with the largest penalty times lines, by file
    and line, or folder. For code paragraphs, the lines of the longest paragraph of that function."""
    if not metric_id:
        return ""
    worst = _worst_child(card, piece, metric_id)
    if worst is None:
        return ""
    item = worst.item
    # A row of the piece itself needs no name, only the place.
    name = worst.id.split("::", 1)[1] if "::" in worst.id and worst is not piece else ""
    label = "worst:" if worst is not piece else "at"
    if isinstance(item, Function):
        settings = card.model.settings
        spans = paragraph_spans(item) if metric_id == "function.paragraph_penalty" else []
        if spans:
            first, last, size = max(spans, key=lambda span: span[2])
            return f"{label} {item.file.path}:{first}-{last}, a paragraph of {size} code lines{' in ' + name if name else ''}"
        return f"{label} {item.file.path}:{item.start_line} {name}".rstrip()
    if isinstance(item, Module):
        return f"worst: folder {module_folder(item) or '.'}"
    if hasattr(item, "file") and hasattr(item, "start_line"):
        return f"{label} {item.file.path}:{item.start_line} {name}".rstrip()
    path = getattr(item, "path", None)
    return f"worst: {path}" if isinstance(path, str) and worst is not piece else ""

def changed_functions(report: Report) -> list[str]:
    """The functions and tests whose score fell by `changes_min_drop` or more against the ref, each with its score
    before and after and the selected measurement that costs it most. New functions are not listed: they had no
    score to fall from. Empty without a ref."""
    comparison = report.comparison
    if comparison is None:
        return []
    head = comparison.head
    least = report.card.model.settings["changes_min_drop"]
    rows = [(after - before, f"{before:.3f} -> {after:.3f}", piece) for piece, before, after in comparison.score_drops() if before - after >= least]
    if not rows:
        return [f"Functions this change made worse, against {comparison.ref}: none", ""]
    rows.sort(key=lambda row: (row[0], row[2].id))
    name_width = max(len(piece.id) for _, _, piece in rows)
    lines = [f"Functions this change made worse, against {comparison.ref}:"]
    for _, scores, piece in rows:
        policy_id = _costliest_lens(head, piece)
        lines.append(f"  {scores:<14}  {piece.id:<{name_width}}  {_problem(head, policy_id) if policy_id else ''}  {policy_id}".rstrip())
    lines.append("")
    return lines


def _problem(card, metric_id: str) -> str:
    """The problem a measurement names, or for a measurement the policy added, its name."""
    label = problem(metric_id)
    spec = card.model.specs.get(metric_id)
    return spec.design_name if label == metric_id and spec else label


def _costliest_lens(card, piece) -> str:
    """The selected measurement that costs the piece most: the largest sum of penalty times lines over the piece
    and everything below it. A penalty of the piece itself applies to all its lines."""
    charged = Counter()
    for child in piece.walk():
        for metric_id, value in child.values.items():
            charged[metric_id] += card.model.lens_penalty(metric_id, value) * max(child.lines, 1)
    top = charged.most_common(1)
    return top[0][0] if top and top[0][1] > 0 else ""


def _findings(report: Report) -> list[str]:
    """Every block and every warning."""
    lines = [f"❌ Blocks ({len(report.blocks)}):" if report.blocks else "✅ Blocks: none"]
    lines.extend(f"  ❌ {finding.condition}: {finding.piece_id} {finding.message}" for finding in report.blocks)
    lines.append(f"⚠️  Warnings ({len(report.warnings)}):" if report.warnings else "✅ Warnings: none")
    lines.extend(f"  ⚠️  {finding.condition}: {finding.piece_id} {finding.message}" for finding in report.warnings)
    if report.not_run:
        lines.append("Did not run:")
        lines.extend(f"  {finding.condition}: {finding.message.removeprefix('did not run: ')}" for finding in report.not_run)
    lines.append("")
    return lines


def _check_summary(report: Report) -> list[str]:
    failed = [(check_id, result) for check_id, result in sorted(report.checks.items()) if result.ran and not result.passed]
    if not failed:
        return ["✅ Checks: all passed", ""]
    width = max(len(check_label(check_id)) for check_id, _ in failed)
    lines = [f"❌ Failed checks ({len(failed)}):"]
    for check_id, result in failed:
        count = len(result.failures)
        lines.append(f"  ❌ {check_label(check_id):<{width}}  {count:>4} {'failure ' if count == 1 else 'failures'}  {check_id}")
    lines.append("")
    return lines


def _selection(report: Report) -> list[str]:
    lines = [
        "Score settings: a value at the target lowers the score not at all, a value at the limit lowers it fully.",
        f"  {'target':>8}  {'limit':>8}  {'weight':>6}  {'group':<14}  measurement",
    ]
    specs = report.card.model.specs
    for metric_id, scored in report.card.model.selection.items():
        numbers = scored.curve.numbers()
        low_only = specs[metric_id].higher_is_better and numbers["low_target"] is not None
        target, limit = scored.curve.charged_side(specs[metric_id].higher_is_better)
        notes = []
        if low_only:
            notes.append("lowers the score below the target")
        elif numbers["low_target"] is not None:
            notes.append(f"also lowers the score below {numbers['low_target']:g}, fully at {numbers['low_limit']:g}")
        lines.append(f"  {target:>8g}  {limit:>8g}  {scored.weight:>6g}  {scored.group:<14}  {metric_id}{'  ' + '; '.join(notes) if notes else ''}")
    lines.extend(_unvalued(report))
    lines.append("")
    return lines


def _unvalued(report: Report) -> list[str]:
    """The selected measurements without a value in this run, because there was nothing to measure."""
    if not report.unvalued:
        return []
    return [f"No value in this run, so not charged ({len(report.unvalued)} of the selection):", *(f"  {metric_id}: {reason}" for metric_id, reason in report.unvalued.items())]


def _no_score(report: Report) -> list[str]:
    """In place of the overview when a selected measurement lacks its data: any score would be wrong. When a slow
    tool's value is missing in a run with `--full`, the slow tools that did not run follow, as its reason says."""
    lines = ["No score: data for these measurements in the score is missing.", *(f"  {metric_id}: {reason}" for metric_id, reason in report.missing.items())]
    specs = report.card.model.specs
    if report.tools and WITHOUT_FULL not in report.tools.notes and any(specs[metric_id].status is Status.FULL_ONLY for metric_id in report.missing):
        lines.extend(["Slow tools:", *(f"  not run: {name}: {note}" for name, note in sorted(report.tools.notes.items()))])
    return lines


def _metrics(report: Report) -> list[str]:
    card = report.card
    charged = Counter()
    over_target = Counter()
    worst = {}
    for piece in card.root.walk():
        for metric_id, value in piece.values.items():
            penalty = card.model.lens_penalty(metric_id, value)
            if penalty > 0:
                charged[metric_id] += penalty * max(piece.lines, 1)
                over_target[metric_id] += 1
                worst[metric_id] = max(worst.get(metric_id, value), value)
    lines = ["What lowers the score most:", f"  {'penalty x lines':>15}  {'pieces above target':>19}  {'highest value':>13}  measurement"]
    for metric_id, total in charged.most_common():
        lines.append(f"  {total:>15.1f}  {over_target[metric_id]:>19}  {worst[metric_id]:>13g}  {metric_id}")
    lines.append("")
    return lines


def _check_failures(report: Report) -> list[str]:
    """Every failed check with each of its failures, and the checks that did not run."""
    failed = [(check_id, result) for check_id, result in sorted(report.checks.items()) if result.ran and not result.passed]
    lines = [f"❌ Failed checks ({len(failed)}):" if failed else "✅ Checks: all passed"]
    for check_id, result in failed:
        lines.append(f"  ❌ {check_label(check_id)}  {check_id}")
        lines.extend(f"      {where}: {what}" for where, what in result.failures)
    skipped = [(check_id, result) for check_id, result in sorted(report.checks.items()) if not result.ran]
    if skipped:
        lines.append("Checks that did not run:")
        lines.extend(f"  {check_id}: {result.reason}" for check_id, result in skipped)
    lines.append("")
    return lines


def _tool_failures(report: Report) -> list[str]:
    """The slow tools this run asked for that did not run, and why. Empty when none was asked for."""
    notes = {name: note for name, note in (report.tools.notes.items() if report.tools else ()) if name != WITHOUT_FULL and note != NOT_SELECTED}
    if not notes:
        return []
    return [f"⚠️  Tools that did not run ({len(notes)}):", *(f"  ⚠️  {name}: {note}" for name, note in sorted(notes.items())), ""]


def _slop_list(report: Report) -> list[str]:
    """Every slop finding that counts toward the score, Rust files first."""
    counted = report.card.model.settings["slop_counted_severities"]
    found = sorted((f for f in report.slop if f.severity in counted), key=lambda f: (not f.path.endswith(".rs"), f.path, f.line))
    if not found:
        return ["✅ Potential slop: none", ""]
    lines = [f"🧹 Potential slop ({len(found)}):"]
    for finding in found:
        where = f"{finding.path}:{finding.line}" if finding.line else finding.path
        title = SLOP_EXPLANATIONS.get(finding.rule, {}).get("title", finding.rule)
        lines.append(f"  ⚠️  {where}  {title}: {finding.shown(report.card.model.settings['display_slop_match_characters'])}  {finding.rule}")
    lines.append("")
    return lines


def report_data(report: Report) -> dict:
    """The whole report as plain data: score, every piece with its values, findings, checks and slop findings."""
    card = report.card
    comparison = report.comparison
    least = card.model.settings["changes_min_drop"]
    return {
        "score": None if report.missing else card.score(),
        "missing_data": report.missing,
        "without_value": report.unvalued,
        "tools_not_run": dict(report.tools.notes) if report.tools else {},
        "pieces": [
            {"id": piece.id, "kind": piece.kind.value, "lines": piece.lines, "score": card.score(piece), "values": dict(piece.values)}
            for piece in card.root.walk()
        ],
        "made_worse": [
            {"piece": piece.id, "before": before, "after": after, "main_problem": _costliest_lens(comparison.head, piece)}
            for piece, before, after in (comparison.score_drops() if comparison else [])
            if before - after >= least
        ],
        "change_values": dict(report.diff_values),
        "score_settings": {
            metric_id: {"target": row.curve.charged_side(card.model.specs[metric_id].higher_is_better)[0], "limit": row.curve.charged_side(card.model.specs[metric_id].higher_is_better)[1], "weight": row.weight, "group": row.group}
            for metric_id, row in card.model.selection.items()
        },
        "blocks": [_finding_data(finding) for finding in report.blocks],
        "warnings": [_finding_data(finding) for finding in report.warnings],
        "not_run": [_finding_data(finding) for finding in report.not_run],
        "checks": {
            check_id: {"ran": result.ran, "passed": result.passed, "reason": result.reason, "failures": [{"where": where, "message": message} for where, message in result.failures]}
            for check_id, result in sorted(report.checks.items())
        },
        "slop": [
            {"rule": finding.rule, "severity": finding.severity, "path": finding.path, "line": finding.line, "matched": finding.matched}
            for finding in report.slop
        ],
    }


def _finding_data(finding) -> dict:
    return {"condition": finding.condition, "piece": finding.piece_id, "message": finding.message}
