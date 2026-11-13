"""Turn a codebase, its history and tool results into a tree of measured pieces."""

import fnmatch
from collections import Counter, defaultdict

from smog.domain.calls import CallGraph
from smog.domain.code import Codebase, Crate, Function, Module, SourceFile, TypeDef
from smog.domain.curves import line_weighted_median
from smog.domain.graph import FileGraph, crate_graph, reversed_graph
from smog.domain.history import History
from smog.domain.lenses.clones import inconsistent_clone_groups
from smog.domain.lenses.comments import (
    admitted_debt_markers,
    decorative_comments,
    interface_documentation,
    known_names,
    restating_comments,
    stale_doc_references,
)
from smog.domain.lenses.crate_api import exposed_dependencies, measure_api
from smog.domain.lenses.crate_dependencies import LockGraph, audited_share, dependency_counts, unused_dependency_names
from smog.domain.lenses.duplication import duplicated_line_shares
from smog.domain.lenses.file import comment_density, function_count, size_values, suppressions, warning_counts
from smog.domain.lenses.module_coupling import ModuleGraph, centrality_values, coupling_values, cycle_sizes
from smog.domain.lenses.exports import Exports
from smog.domain.lenses.module_shape import lint_unreachable_pub, measure_shape, unreachable_pub
from smog.domain.lenses.naturalness import codebase_cross_entropy, cross_entropies
from smog.domain.lenses.orphans import orphan_files
from smog.domain.lenses.function import guard_signatures, measure_function
from smog.domain.lenses.function_tests import measure_with_tools, mutants_by_function, mutation_scores, production_line_coverage
from smog.domain.lenses.structure import (
    crate_line_churn,
    ratios_to_production,
    file_ranks,
    folder_counts,
    measure_codebase,
    measure_crate,
    measure_file,
    measure_module,
    names_used_by_module,
)
from smog.domain.lenses.tests import assertion_windows, class_shares, copied_assertion_windows, lazy_tests, measure_test, measure_test_runs, test_run_totals
from smog.domain.lenses.type_coupling import coupling_by_index, coupling_by_name, response_sets
from smog.domain.lenses.type_shape import hiding_factors
from smog.domain.lenses.types import correlated_option_fields, data_clumps, foreign_field_access, measure_type
from smog.domain.policy import Policy
from smog.domain.registry import PieceKind
from smog.domain.reviews import review_values
from smog.domain.scoring import Piece, Scorecard, ScoringModel
from smog.domain.tools import ToolResults


class _Context:
    def __init__(self, codebase: Codebase, policy: Policy, history: History | None, tools: ToolResults | None, slop_counts: Counter):
        self.codebase = codebase
        self.policy = policy
        self.history = history
        self.tools = tools
        self.slop_counts = slop_counts
        self.file_graph = FileGraph(codebase)
        self.fan_in = self.file_graph.fan_in()
        self.ranks = file_ranks(self.file_graph, policy.settings)
        index = tools.index if tools else None
        self.calls = CallGraph(codebase, index)
        self.coupling = coupling_by_name(codebase) if index is None else coupling_by_index(codebase, index)
        self.response_sets = response_sets(codebase, index)
        self.duplicated = duplicated_line_shares(codebase, policy.settings)
        self.orphans = orphan_files(codebase)
        self.clone_groups = inconsistent_clone_groups(codebase, policy.settings)
        self.cross_entropies = cross_entropies(codebase, policy.settings)
        self.cloned = {(f.file.path, f.start_line) for group in self.clone_groups for f in group}
        self.exports = Exports(codebase)
        self.lock_graph = LockGraph(codebase)
        lint = tools.unreachable_pub if tools else None
        self.lint_unreachable = lint_unreachable_pub(codebase.modules, lint) if lint is not None else {}
        self.module_graph = ModuleGraph(codebase)
        self.module_values = coupling_values(self.module_graph)
        cycles = cycle_sizes(self.module_graph, policy.settings["module_cycles_skip_nested"])
        for key, centrality in centrality_values(self.module_graph).items():
            self.module_values[key].update({"module.cycle_size": cycles[key], **centrality})
        self.effective = self.calls.effective_lengths(policy.alpha)
        self.chains = self.calls.helper_chains()
        self.folders = folder_counts(codebase.tracked_paths)
        self.names = known_names(codebase)
        self.used_names = names_used_by_module(codebase)
        self.crates_graph = crate_graph(codebase)
        self.crates_reverse = reversed_graph(self.crates_graph)
        self.function_churn = history.function_churn() if history else Counter()
        self.assertion_churn = history.assertion_churn() if history else Counter()
        self.file_churn = history.file_churn() if history else Counter()
        self.folder_churn = history.folder_churn() if history else Counter()
        self.line_churn = history.file_line_churn() if history else {}
        self.file_ages = history.file_ages() if history else {}
        # None in place of the counts when `git blame` gave nothing to count, so that no piece gets a 0 it did not earn.
        blamed = history is None or history.has_blame
        self.szz_files = (history.szz_file_fixes() if history else Counter()) if blamed else None
        self.szz_functions = (history.szz_function_fixes() if history else Counter()) if blamed else None
        self.coupled = history.strongest_coupling() if history else {}
        self.unstable = history.unstable_interfaces(self.file_graph) if history else {}
        self.anchored = history.anchor_dominated(self.file_graph) if history else {}
        self.correlated = correlated_option_fields(codebase, policy.settings)
        self.foreign_fields = foreign_field_access(codebase)
        self.private_names = {f.name for f in codebase.functions if f.is_private}
        self.public_names = {item.name for file in codebase.files for item in file.items if item.is_public}
        self.production_names = frozenset(f.name for f in codebase.functions if not f.in_test_code)
        self.copied_assertions = copied_assertion_windows([f for f in codebase.functions if f.in_test_code], policy.settings)
        self.lazy_tests = {
            (file.path, line) for file in codebase.files for line in lazy_tests([f for f in file.functions if f.is_test_case], self.production_names)
        }
        self.function_values = {f.qualified: measure_function(f, policy.settings) for f in codebase.functions if f.body is not None and not f.in_test_code}
        self.function_callers = _callers_by_name(codebase)
        self.unreviewed = tools.unreviewed if tools else None
        self.function_mutants = mutants_by_function(codebase, tools.mutants) if tools and tools.mutants is not None else {}
        self.helper_counts: Counter = Counter()
        self.helper_depths: dict[str, int] = defaultdict(int)
        for function in codebase.functions:
            if self.calls.one_caller(function) is not None:
                module = "::".join((function.file.crate_name, *function.module_path))
                self.helper_counts[module] += 1
                self.helper_depths[module] = max(self.helper_depths[module], self.chains[function.qualified])


def _measure_function_piece(function: Function, context: _Context) -> Piece:
    calls = context.calls
    is_test = function.in_test_code
    churn = context.function_churn[function.history_key]
    piece = Piece(PieceKind.TEST if is_test else PieceKind.FUNCTION, function.qualified, function.lines, function)
    if is_test:
        used = function.used_names()
        known = used & (context.private_names | context.public_names)
        directory = function.file.path.rpartition("/")[0]
        production_changes = context.folder_churn[directory]
        piece.set_values(measure_test(function, context.policy.settings, context.production_names))
        piece.set_values(
            {
                "test.smell.lazy_test": int((function.file.path, function.start_line) in context.lazy_tests),
                "test.duplicated_assertion_block": int(
                    bool(assertion_windows(function, context.policy.settings["assertion_block_min_statements"]) & context.copied_assertions)
                ),
                "test.non_api_references": len(used & context.private_names) / len(known) if known else 0.0,
                "test.churn": churn,
                "test.relative_churn": churn / production_changes if production_changes else 0.0,
                "test.assertion_churn": context.assertion_churn[function.history_key],
            }
        )
        if context.tools and function.is_test_case:
            piece.set_values(measure_test_runs(function, context.tools))
        return _with_custom_metrics(piece, context)
    piece.set_values(context.function_values[function.qualified])
    piece.set_values(
        {
            "function.effective_length": context.effective.get(function.qualified, function.lines),
            "function.outgoing_deps": calls.outgoing(function),
            "function.outgoing_cross_module": calls.outgoing_cross_module(function),
            "function.incoming_deps": calls.incoming(function),
            "function.code_churn": churn,
            "function.inconsistent_clone": int((function.file.path, function.start_line) in context.cloned),
            "function.literal_flag_calls": _literal_flag_share(function, context),
        }
    )
    if context.szz_functions is not None:
        piece.set_values({"function.szz_fixes": context.szz_functions[function.history_key]})
    if context.tools:
        piece.set_values(measure_with_tools(function, context.tools, context.function_mutants, context.policy.settings["mutation_timeouts_caught"]))
    if context.unreviewed is not None:
        lines = context.unreviewed.get(function.file.path, ())
        piece.set_values({"function.unreviewed_lines": sum(1 for line in lines if function.holds_line(line))})
    return _with_custom_metrics(piece, context)


def _with_custom_metrics(piece: Piece, context: _Context) -> Piece:
    for metric in context.policy.custom_metrics.values():
        if metric.spec.piece is piece.kind:
            value, problems = metric.measure(piece.item)
            piece.set_values({metric.spec.id: value})
            if problems:
                piece.set_problems(metric.spec.id, problems)
    return piece


def _literal_flag_share(function: Function, context: _Context) -> float:
    """1 per `bool` parameter whose every call site, at least one, passes a literal."""
    positions = [i for i, p in enumerate(p for p in function.params if not p.is_self) if p.type_text == "bool"]
    if not positions:
        return 0
    sites = [
        call
        for caller in context.function_callers.get(function.name, ())
        for call in caller.calls()
        if call.name == function.name and call.arguments is not None
    ]
    if not sites:
        return 0
    flags = 0
    for position in positions:
        arguments = [call.arguments[position] for call in sites if position < len(call.arguments)]
        if arguments and all(argument.kind == "boolean_literal" for argument in arguments):
            flags += 1
    return flags


def _measure_type_piece(type_def: TypeDef, context: _Context) -> Piece:
    piece = Piece(PieceKind.TYPE, type_def.qualified, type_def.lines + sum(m.lines for m in type_def.methods), type_def)
    piece.set_values(measure_type(type_def, context.function_values, context.policy.settings))
    piece.set_values(
        {
            "type.correlated_options": context.correlated.get(type_def.qualified, 0),
            "type.foreign_field_access": context.foreign_fields.get(type_def.qualified, 0),
            "type.cbo": context.coupling[type_def],
            "type.rfc": context.response_sets[type_def],
        }
    )
    return _with_custom_metrics(piece, context)


def _measure_file_piece(file: SourceFile, context: _Context) -> Piece:
    piece = Piece(PieceKind.FILE, file.path, file.code_line_count, file)
    piece.set_values(size_values(file))
    piece.set_values(measure_file(file, context.file_graph, context.fan_in, context.ranks))
    piece.set_values(interface_documentation(file, context.policy.settings))
    piece.set_values(
        {
            "file.restating_comments": restating_comments(file, context.policy.settings),
            "file.decorative_comments": decorative_comments(file, context.policy.settings),
            "file.slop_findings": context.slop_counts[file.path],
            "file.functions": function_count(file),
            "file.suppressions": suppressions(file, context.policy.settings),
            "file.duplicated_line_share": context.duplicated[file.path],
            "file.orphan": int(file.path in context.orphans),
            "file.comment_density": comment_density(file),
            "file.stale_docs": stale_doc_references(file, context.names),
            "file.code_churn": context.file_churn[file.path],
            "file.unstable_interface": context.unstable.get(file.path, 0),
            "file.anchor_dominated": context.anchored.get(file.path, 0),
        }
    )
    if context.szz_files is not None:
        piece.set_values({"file.szz_fixes": context.szz_files[file.path]})
    added, deleted = context.line_churn.get(file.path, (0, 0))
    piece.set_values(
        {
            "file.relative_churn": added / file.code_line_count if file.code_line_count else 0.0,
            "file.relative_deletion": deleted / file.code_line_count if file.code_line_count else 0.0,
            "file.change_coupling": context.coupled.get(file.path, 0.0),
        }
    )
    if context.tools and context.tools.unformatted is not None:
        piece.set_values({"file.unformatted": int(file.path in context.tools.unformatted)})
    piece.set_values(_test_tool_values("file", [file], context))
    piece.set_values(_review_values("file", [file], context))
    if context.tools and context.tools.pedantic_warnings is not None:
        here = [warning for warning in context.tools.pedantic_warnings if warning.path == file.path]
        piece.set_values({"file.unused_code": warning_counts(here, context.policy.settings)["unused_code"]})
    if file.path in context.cross_entropies:
        piece.set_values({"file.cross_entropy": context.cross_entropies[file.path][0]})
    if file.path in context.file_ages:
        piece.set_values({"file.age_months": context.file_ages[file.path]})
    children = [_measure_function_piece(function, context) for function in file.functions if function.body is not None]
    complexity = sum(child.value("function.cyclomatic") for child in children if child.kind is PieceKind.FUNCTION)
    piece.set_values({"file.complexity_hotspot": context.file_churn[file.path] * complexity})
    for child in children:
        piece.add_child(child)
    for type_def in file.types:
        if not type_def.in_test_code:
            piece.add_child(_measure_type_piece(type_def, context))
    return _with_custom_metrics(piece, context)


def _measure_module_piece(module: Module, context: _Context) -> Piece:
    lines = sum(file.code_line_count for file in module.subtree_files())
    piece = Piece(PieceKind.MODULE, module.qualified, lines, module)
    piece.set_values(measure_module(module, context.folders, context.file_graph, context.helper_counts, context.helper_depths))
    piece.set_values(context.module_values.get((module.crate_name, module.path), {}))
    piece.set_values(measure_shape(module, context.policy.settings))
    by_syntax = unreachable_pub(module, context.exports)
    piece.set_values({"module.unreachable_pub": context.lint_unreachable.get(module.qualified, by_syntax)})
    for file in module.files:
        piece.add_child(_measure_file_piece(file, context))
    for child in module.children:
        piece.add_child(_measure_module_piece(child, context))
    return _with_custom_metrics(piece, context)


def _measure_crate_piece(crate: Crate, context: _Context) -> Piece:
    lines = sum(file.code_line_count for file in crate.files)
    piece = Piece(PieceKind.CRATE, crate.name, lines, crate)
    piece.set_values(measure_crate(crate, context.codebase, context.crates_graph, context.crates_reverse, context.used_names, context.policy.settings))
    piece.set_values(crate_line_churn(crate, context.line_churn))
    piece.set_values(dependency_counts(crate, context.lock_graph))
    piece.set_values(measure_api(crate, context.exports, context.policy.settings))
    piece.set_values(exposed_dependencies(crate, context.exports, context.lock_graph))
    piece.set_values({"crate.unused_dependencies": len(unused_dependency_names(crate, context.policy.dependency_ignores))})
    for metric_id, found in (("crate.unsafe_in_dependencies", "unsafe_in_dependencies"), ("crate.semver_violations", "semver_violations")):
        by_crate = context.tools.result(found) if context.tools else None
        if by_crate is not None and crate.name in by_crate:
            piece.set_values({metric_id: by_crate[crate.name]})
    piece.set_values(_test_tool_values("crate", crate.files, context))
    piece.set_values(_review_values("crate", crate.files, context))
    audited = audited_share(crate, context.lock_graph, context.codebase.audits)
    if audited is not None:
        piece.set_values({"crate.audited_dependency_share": audited})
    piece.add_child(_measure_module_piece(crate.root, context))
    return _with_custom_metrics(piece, context)


def _review_values(prefix: str, files: list[SourceFile], context: _Context) -> dict[str, float]:
    """The review values of some files, or none without review data."""
    return review_values(prefix, files, context.unreviewed) if context.unreviewed is not None else {}


def _test_tool_values(prefix: str, files: list[SourceFile], context: _Context) -> dict[str, float]:
    """Line coverage and the mutation scores of some files, for the tools that ran. A file has coverage only.

    The codebase has mutation scores only after a whole-tree run: the mutants of a diff describe the change.
    """
    tools = context.tools
    if tools is None:
        return {}
    values = {}
    coverage = production_line_coverage(files, tools)
    if coverage is not None:
        values[f"{prefix}.coverage"] = coverage
    if tools.mutants is not None and (prefix == "crate" or (prefix == "codebase" and tools.mutants_whole_tree)):
        paths = {file.path for file in files}
        scores = mutation_scores([m for m in tools.mutants if m.path in paths], tools, context.policy.settings["mutation_timeouts_caught"])
        values.update({f"{prefix}.{name}": value for name, value in scores.items()})
    return values


def _median_values(pieces: list[Piece]) -> float:
    return line_weighted_median([(piece.value("function.length"), piece.lines) for piece in pieces])


def _codebase_values(root: Piece, codebase: Codebase, context: _Context, doc_slop: int) -> dict[str, float]:
    functions = [piece for piece in root.walk() if piece.kind is PieceKind.FUNCTION]
    code_lines = sum(file.code_line_count for file in codebase.files) or 1
    markers = sum(admitted_debt_markers(file, context.policy.settings) for file in codebase.files)
    guards: Counter = Counter()
    for function in codebase.functions:
        guards.update(set(guard_signatures(function)))
    values = {
        **measure_codebase(codebase, context.file_graph),
        "codebase.median_function_length": _median_values(functions),
        **ratios_to_production("codebase", codebase.files, context.policy.settings["test_density_per_lines"]),
        "codebase.debt_markers": context.policy.settings["density_per_lines"] * markers / code_lines,
        "codebase.suppressions": sum(suppressions(file, context.policy.settings) for file in codebase.files),
        "codebase.inconsistent_clone_groups": len(context.clone_groups),
        "codebase.repeated_guards": sum(1 for count in guards.values() if count > 1),
        "codebase.data_clumps": len(data_clumps(codebase, context.policy.settings)),
        "codebase.doc_slop_findings": doc_slop,
        **hiding_factors(codebase.types),
        **class_shares([piece.values for piece in root.walk() if piece.kind is PieceKind.TEST]),
    }
    entropy = codebase_cross_entropy(context.cross_entropies)
    if entropy is not None:
        values["codebase.cross_entropy"] = entropy
    values.update(_history_values(context, code_lines))
    if context.tools:
        values.update(_tool_values(context.tools, codebase, code_lines, context.policy.settings["density_per_lines"]))
        if context.tools.pedantic_warnings is not None:
            counts = warning_counts(context.tools.pedantic_warnings, context.policy.settings)
            values.update({f"codebase.{name}": count for name, count in counts.items()})
        values.update(_test_tool_values("codebase", codebase.files, context))
        values.update(test_run_totals(context.tools, context.policy.settings))
    values.update(_review_values("codebase", codebase.files, context))
    return values


def _history_values(context: _Context, code_lines: int) -> dict[str, float]:
    history = context.history
    if history is None:
        return {}
    survival, early = history.item_survival()
    slope, lowered = history.debt_trend()
    age, removed_ratio = history.finding_age()
    violations = history.modularity_violations(context.file_graph)
    messages = {
        "codebase.unconventional_messages": history.unconventional_messages(),
        "codebase.long_subjects": history.long_subjects(),
        "codebase.messages_without_body": history.messages_without_body(),
        "codebase.long_body_lines": history.long_body_lines(),
        "codebase.fix_references": history.fix_references(),
        "codebase.bug_introducing_share": history.bug_introducing_share(),
        "codebase.active_branches": history.active_branches(),
        "codebase.merges_per_day": history.merges_per_day(),
        "codebase.branch_lifetime_days": history.branch_lifetime_days(),
    }
    return {
        **{metric_id: value for metric_id, value in messages.items() if value is not None},
        "codebase.short_term_churn": history.short_term_churn(),
        "codebase.item_survival": survival,
        "codebase.items_removed_early": early,
        "codebase.reverts": history.reverts(),
        "codebase.follow_up_fixes": history.follow_up_fixes(),
        "codebase.files_changed_together": history.files_changed_together(),
        "codebase.modularity_violations": len(violations),
        "codebase.co_changing_clones": history.co_changing_clones(context.codebase),
        "codebase.debt_trend": slope,
        "codebase.debt_lowering_share": lowered,
        "codebase.finding_age": age,
        "codebase.findings_removed_ratio": removed_ratio,
        "codebase.equilibrium": history.equilibrium(),
    }


def _tool_values(tools: ToolResults, codebase: Codebase, code_lines: int, per_lines: float) -> dict[str, float]:
    values: dict[str, float] = {}
    if tools.pedantic_warnings is not None:
        values["codebase.lint_density"] = per_lines * len(tools.pedantic_warnings) / code_lines
    if tools.tests is not None:
        values["codebase.test_run_time"] = tools.tests.seconds
    if tools.flaky_tests() is not None:
        values["codebase.flake_count"] = tools.flaky_tests()
    if tools.build_seconds is not None:
        values["codebase.build_time"] = tools.build_seconds
    if tools.uncovered is not None:
        values["codebase.uncovered_lines"] = sum(len(lines) for lines in tools.uncovered.values())
    if tools.mutants is not None:
        values["codebase.surviving_mutants"] = sum(1 for mutant in tools.mutants if mutant.survived)
    if tools.pseudo_tested(codebase) is not None:
        values["codebase.pseudo_tested"] = tools.pseudo_tested(codebase)
    if tools.probe_failures is not None:
        values["codebase.message_probe_failures"] = len(tools.probe_failures)
    return values


def build_scorecard(
    codebase: Codebase,
    policy: Policy,
    history: History | None = None,
    tools: ToolResults | None = None,
    slop_counts: Counter | None = None,
    doc_slop: int = 0,
) -> Scorecard:
    context = _Context(codebase, policy, history, tools, slop_counts or Counter())
    root = Piece(PieceKind.CODEBASE, "codebase", sum(file.code_line_count for file in codebase.files), codebase)
    for crate in codebase.crates:
        root.add_child(_measure_crate_piece(crate, context))
    root.set_values(_codebase_values(root, codebase, context, doc_slop))
    _with_custom_metrics(root, context)
    model = policy.scoring_model()
    card = Scorecard(root, model)
    _set_derived_values(card, context)
    for piece in root.walk():
        for metric_id in policy.disabled & piece.values.keys():
            del piece.values[metric_id]
    return card


class NoFileMatches(ValueError):
    """The patterns of a restricted run keep no file."""


def restrict_scorecard(card: Scorecard, patterns: tuple[str, ...]) -> Scorecard:
    """The scorecard of the files that match one of the patterns, by the rules of `Policy.only`."""

    def is_kept(file: SourceFile) -> bool:
        return any(fnmatch.fnmatch(name, pattern) for pattern in patterns for name in (file.path, file.crate_name)) or any(
            fnmatch.fnmatch(file.path, pattern.rstrip("/") + "/*") for pattern in patterns
        )

    def restricted(piece: Piece) -> tuple[Piece | None, bool]:
        """The piece without what is not kept, or None if nothing of it is, and whether all of it is kept."""
        if piece.kind is PieceKind.FILE:
            return (piece, True) if is_kept(piece.item) else (None, False)
        below = [restricted(child) for child in piece.children]
        children = [child for child, _ in below if child is not None]
        # An inline module holds no file: it is kept with the files that declare it.
        declared_in = [is_kept(declaration.file) for declaration in piece.item.declarations] if piece.kind is PieceKind.MODULE else []
        whole = all(is_whole for _, is_whole in below) and all(declared_in)
        if not children and not any(declared_in):
            return None, False
        copy = Piece(piece.kind, piece.id, sum(child.lines for child in children), piece.item, kept_in_part=not whole)
        if whole:
            copy.set_values(piece.values)
        for child in children:
            copy.add_child(child)
        return copy, whole

    root, whole = restricted(card.root)
    if root is None:
        raise NoFileMatches(f"no file matches the patterns of policy.only or --only: {', '.join(patterns)}")
    if not whole:
        root.set_values({"codebase.median_function_length": _median_values([piece for piece in root.walk() if piece.kind is PieceKind.FUNCTION])})
    return Scorecard(root, card.model)


def local_debt(file: SourceFile, model: ScoringModel, settings: dict) -> tuple[float, set]:
    """Debt from lenses that read one function, and the (function, lens) pairs over target. For per-commit history."""
    debt = 0.0
    findings = set()
    for function in file.functions:
        if function.body is None:
            continue
        is_test = function.in_test_code
        piece = Piece(PieceKind.TEST if is_test else PieceKind.FUNCTION, function.history_key, function.lines, function)
        piece.set_values(measure_test(function, settings) if is_test else measure_function(function, settings))
        debt += model.penalty(piece)
        findings.update((function.history_key, metric_id) for metric_id, value in piece.values.items() if model.lens_penalty(metric_id, value) > 0)
    return debt, findings


def _callers_by_name(codebase: Codebase) -> dict[str, list[Function]]:
    callers = defaultdict(list)
    for function in codebase.functions:
        for name in {call.name for call in function.calls()}:
            callers[name].append(function)
    return callers


def _set_derived_values(card: Scorecard, context: _Context) -> None:
    """Values that depend on penalties: hotspots, lenses over target and flaw counts."""
    model = card.model
    settings = context.policy.settings
    excluded = tuple(settings["hotspot_excluded_groups"])
    over_lines = total_lines = 0
    for piece in card.pieces(PieceKind.FUNCTION, PieceKind.TEST, PieceKind.TYPE):
        total_lines += piece.lines
        if len(model.group_penalties(piece)) >= settings["lenses_over_target_min_groups"]:
            over_lines += piece.lines
    for piece in card.pieces(PieceKind.FUNCTION):
        piece.set_values({"function.hotspot": piece.value("function.code_churn") * model.penalty(piece, exclude_groups=excluded)})
    for piece in card.pieces(PieceKind.FILE):
        penalty = sum(model.penalty(child, exclude_groups=excluded) for child in piece.children)
        piece.set_values({"file.hotspot": piece.value("file.code_churn") * penalty})
    crossings = sum(1 for piece in card.pieces(PieceKind.FILE) if piece.value("file.crossing") > settings["flaw_counts_crossing_above"])
    unstable = sum(1 for count in context.unstable.values() if count >= settings["flaw_counts_unstable_min"])
    violations = len(context.history.modularity_violations(context.file_graph)) if context.history else 0
    cycles = card.root.value("codebase.largest_cyclic_group")
    card.root.set_values(
        {
            "codebase.lenses_over_target": over_lines / total_lines if total_lines else 0.0,
            "codebase.flaw_counts": crossings + unstable + violations + cycles,
        }
    )
