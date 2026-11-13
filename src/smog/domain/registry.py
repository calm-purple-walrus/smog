"""Every measurement in sections 3.1 to 3.10 of the design: what it is and whether Smog computes it.

The registry does not say whether or how a measurement is scored. The selection in force does (`smog.domain.selection`).
"""

from enum import Enum


class Kind(Enum):
    CHECK = "check"
    MEASUREMENT = "measurement"


class Status(Enum):
    COMPUTED = "computed"
    APPROXIMATE = "approximate"
    FULL_ONLY = "full-only"
    LEFT_OUT = "left out"


class PieceKind(Enum):
    FUNCTION = "function"
    TEST = "test"
    TYPE = "type"
    FILE = "file"
    MODULE = "module"
    CRATE = "crate"
    CODEBASE = "codebase"
    DIFF = "diff"


class MetricSpec:
    def __init__(self, metric_id, section, design_name, kind, piece, status, note="", higher_is_better=False):
        self._id = metric_id
        self._section = section
        self._design_name = design_name
        self._kind = kind
        self._piece = piece
        self._status = status
        self._note = note
        self._higher_is_better = higher_is_better

    @property
    def id(self) -> str:
        return self._id

    @property
    def section(self) -> str:
        return self._section

    @property
    def design_name(self) -> str:
        return self._design_name

    @property
    def kind(self) -> Kind:
        return self._kind

    @property
    def piece(self) -> PieceKind:
        return self._piece

    @property
    def status(self) -> Status:
        return self._status

    @property
    def note(self) -> str:
        return self._note

    @property
    def higher_is_better(self) -> bool:
        """True when a low value is the bad one, as for coverage. Listings then put the lowest value first.

        A curve for such a measurement needs `low_target` and `low_limit`. False also covers values with no
        good direction, such as function.comment_density.
        """
        return self._higher_is_better

    @property
    def can_be_scored(self) -> bool:
        """True for a number measured on a piece of code. Checks, diff values and left-out rows have no such number."""
        return self._kind is Kind.MEASUREMENT and self._status is not Status.LEFT_OUT and self._piece is not PieceKind.DIFF


C, A, F, X = Status.COMPUTED, Status.APPROXIMATE, Status.FULL_ONLY, Status.LEFT_OUT
FN, TS, TY, FL, MD, CR, CB, DF = (
    PieceKind.FUNCTION, PieceKind.TEST, PieceKind.TYPE, PieceKind.FILE, PieceKind.MODULE, PieceKind.CRATE,
    PieceKind.CODEBASE, PieceKind.DIFF,
)  # fmt: skip

_NO_INDEX = "Resolved by name without the index; `--full` uses the rust-analyzer index."
_BY_NAME = "Resolved by name, not by the rust-analyzer index."
_MACRO_CODE = "Exact for parsed code. Code inside a macro call is not parsed, so an `if`, a `match` or a logical operator there is not counted."
_MACRO_TESTS = (
    "A test attribute among the tokens of a macro call counts, as in `proptest! { #[test] fn ... }`. A test that only a macro's "
    "expansion creates, such as one per case of a `macro_rules!` macro, is not seen, and a function with several cases counts once."
)
_COMMITS = "Commits stand in for PRs, assuming squash merges."
_REVIEWS = (
    "Needs `policy.humans` and review data. `--full --tools reviews` reads pull requests and reviews from GitHub; the setting "
    "`reviews_file` or `--reviews-file` reads them from a file, without `--full` and without the network."
)


def _check(metric_id, section, name, status=C, note=""):
    return MetricSpec(f"check.{metric_id}", section, name, Kind.CHECK, CB, status, note)


def _value(metric_id, section, name, piece, status=C, note="", higher_is_better=False):
    return MetricSpec(metric_id, section, name, Kind.MEASUREMENT, piece, status, note, higher_is_better)


def _higher(metric_id, section, name, piece, status=C, note=""):
    """A measurement where a higher value is better."""
    return _value(metric_id, section, name, piece, status, note, higher_is_better=True)


def _out(metric_id, section, name, reason):
    return MetricSpec(metric_id, section, name, Kind.MEASUREMENT, CB, X, reason)


_ROWS = [
    # 3.1 Pass/fail checks
    _check("tests_pass", "3.1", "Tests pass", F, "Runs `cargo test`."),
    _check("lints_pass", "3.1", "Lints pass", F, "Runs `cargo clippy` with warnings denied."),
    _check("security_advisories", "3.1", "No security advisories added", X, "Needs cargo-deny and a network fetch of the advisory database."),
    _check("layer_violations", "3.1", "No layer violations", A, "Crate edges from Cargo.toml are exact; file edges follow `use` paths, so a re-export can dodge them."),
    _check("dependency_cycles", "3.1", "No dependency cycles", A, "Crate cycles are exact; module cycles follow `use` paths."),
    _check("project_conventions", "3.1", "Project conventions", C, "Each project writes these as blocking or warning conditions in its policy."),
    _check("new_suppressions", "3.1", "No new suppressions", C, "Needs a ref."),
    _check("gate_untouched", "3.1", "Gate is untouched", C, "Needs a ref."),
    _check("tests_not_weakened", "3.1", "Tests are not weakened", C, "Needs a ref."),
    _check("tests_in_build", "3.1", "Tests stay in the build", F, "Compares syntax with `cargo test -- --list`."),
    _check("assertion_strength", "3.1", "Assertions keep their strength", C, "Needs a ref."),
    _check("pr_size", "3.1", "PR size limit", C, "The diff against the ref stands in for the PR."),
    _check("no_type_bounds", "3.1", "No bounds on type definitions"),
    _check("unused_dependencies", "3.1", "Unused dependencies", A, "Looks for the dependency name in source tokens; cargo-machete is not used."),
    _check("catch_all_names", "3.1", "Catch-all names"),
    _check("module_path_overrides", "3.1", "No module path overrides"),
    # 3.2 Function lenses
    _value("function.length", "3.2", "Length", FN),
    _value("function.body_lines", "3.2", "Body lines", FN),
    _value("function.macro_lines", "3.2", "Lines inside macro calls", FN),
    _value("function.macro_line_share", "3.2", "Lines inside macro calls", FN),
    _value("function.statements", "3.2", "Statements", FN, A, "No source fixes what a Rust statement is; the rule is in `--explain`."),
    _value("function.effective_length", "3.2", "Effective length", FN, A, _NO_INDEX),
    _value("function.largest_paragraph", "3.2", "Largest paragraph", FN),
    _value("function.paragraph_penalty", "3.2", "Largest paragraph", FN),
    _value("function.cyclomatic", "3.2", "Cyclomatic complexity", FN, A, _MACRO_CODE),
    _value("function.cognitive", "3.2", "Cognitive complexity", FN, A, _MACRO_CODE),
    _value("function.nesting", "3.2", "Nesting depth", FN, A, _MACRO_CODE),
    _value("function.block_depth", "3.2", "Block depth", FN),
    _value("function.npath", "3.2", "Path count (NPath)", FN, A, "Nejmeh's rules for C; the rules for `?`, `let`-`else`, `loop` and match guards are Smog's own."),
    _value("function.parameters", "3.2", "Parameters", FN),
    _value("function.return_points", "3.2", "Return points", FN),
    _value("function.outgoing_deps", "3.2", "Outgoing dependencies", FN, A, _NO_INDEX),
    _value("function.outgoing_cross_module", "3.2", "Outgoing dependencies", FN, A, _NO_INDEX),
    _value("function.incoming_deps", "3.2", "Incoming dependencies", FN, A, _NO_INDEX),
    _value("function.generic_params", "3.2", "Generic parameters", FN),
    _value("function.dep_degree", "3.2", "Data-flow edges (DepDegree)", FN, A, "Structured reaching definitions, no control-flow graph; early exits are not modeled."),
    _value("function.vocabulary", "3.2", "Vocabulary", FN),
    _value("function.branch_count", "3.2", "Branch count, loop depth", FN),
    _value("function.loop_depth", "3.2", "Branch count, loop depth", FN),
    _value("function.local_bindings", "3.2", "Local bindings", FN),
    _value("function.flag_params", "3.2", "Flag parameters", FN),
    _value("function.bool_params", "3.2", "`bool` parameters", FN),
    _value("function.primitive_param_share", "3.2", "Primitive-typed parameter share", FN, A, "Types are compared as text, so an alias of a primitive type is not seen."),
    _value("function.literal_flag_calls", "3.2", "Literal flag calls", FN, A, _BY_NAME),
    _value("function.adjacent_same_type", "3.2", "Adjacent same-typed parameters", FN),
    _value("function.pass_through", "3.2", "Pass-through functions", FN),
    _value("function.pass_through_share", "3.2", "Pass-through share", FN),
    _value("module.one_caller_helpers", "3.2", "One-caller helpers and chains", MD, A, _NO_INDEX),
    _value("module.one_caller_chain", "3.2", "One-caller helpers and chains", MD, A, _NO_INDEX),
    _value("function.panic_points", "3.2", "Panic points", FN),
    _value("function.panic_sites", "3.2", "Panic sites", FN),
    _value("function.debug_leftovers", "3.2", "Debug leftovers", FN),
    _value("function.unit_error", "3.2", "Uninformative error type", FN, A, "Reads the return type as written, so a `Result` alias with `()` as error is not seen."),
    _value("codebase.repeated_guards", "3.2", "Repeated guards", CB),
    _value("function.validation_only", "3.2", "Validation-only functions", FN),
    _value("function.late_input_checks", "3.2", "Late input checks (report)", FN),
    _value("function.assertions", "3.2", "Assertion density (report)", FN),
    _value("function.name_mismatch", "3.2", "Name and behavior mismatch", FN),
    _value("function.short_names", "3.2", "Identifier words, short names", FN, A, "One letter or no vowel; no dictionary."),
    _value("function.single_char_names", "3.2", "Short names", FN),
    _value("function.naming_flaws", "3.2", "Naming flaws", FN, A, "Two of Butler's twelve guidelines: the number of words and capital letters. The dictionary guideline is not checked."),
    _value("function.indentation_sum", "3.2", "Indentation sum", FN),
    _value("function.bumpy_road", "3.2", "Bumpy road", FN),
    _value("function.complex_conditional", "3.2", "Complex conditional", FN),
    _value("function.halstead_volume", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_distinct_operators", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_distinct_operands", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_total_operators", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_total_operands", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_length", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_difficulty", "3.2", "Halstead, ABC (report)", FN),
    _value("function.halstead_effort", "3.2", "Halstead, ABC (report)", FN),
    _value("function.abc", "3.2", "Halstead, ABC (report)", FN),
    _value("function.abc_assignments", "3.2", "Halstead, ABC (report)", FN),
    _value("function.abc_branches", "3.2", "Halstead, ABC (report)", FN),
    _value("function.abc_conditions", "3.2", "Halstead, ABC (report)", FN),
    _higher("function.maintainability_index", "3.2", "Maintainability Index", FN),
    # 3.3 Struct and type lenses
    _value("type.fields", "3.3", "Fields", TY, A, "A type declared inside a macro call, such as `bitflags!` or `pin_project!`, is not seen, so it has no value."),
    _value("type.methods", "3.3", "Methods", TY),
    _value("type.variants", "3.3", "Enum variants", TY),
    _value("type.cbo", "3.3", "Coupling (CBO)", TY, A, "Without resolved types: a use is a name that matches a struct, enum, union or trait of the codebase. " + _NO_INDEX),
    _value("type.rfc", "3.3", "Response set (RFC)", TY, A, "Without resolved types: a called method is known by its name. " + _NO_INDEX),
    _value("type.lcom4", "3.3", "Cohesion (LCOM4)", TY),
    _value("type.on_off_fields", "3.3", "On/off fields", TY),
    _value("type.bool_fields", "3.3", "`bool` fields", TY),
    _value("type.primitive_share", "3.3", "Primitive share", TY),
    _value("type.public_field_share", "3.3", "Public-field share", TY),
    _higher("type.attribute_hiding", "3.3", "Attribute and method hiding", TY, A, "A field with no visibility modifier counts as hidden, though other types in its module can read it."),
    _higher("type.method_hiding", "3.3", "Attribute and method hiding", TY, A, "A method of a trait `impl` counts as visible; the trait's own visibility is not read."),
    _higher("codebase.attribute_hiding_factor", "3.3", "Attribute and method hiding", CB, A, "A field with no visibility modifier counts as hidden, though other types in its module can read it."),
    _higher("codebase.method_hiding_factor", "3.3", "Attribute and method hiding", CB, A, "A method of a trait `impl` counts as visible; the trait's own visibility is not read."),
    _value("type.type_complexity", "3.3", "Type-expression complexity", TY, A, "Clippy's `type_complexity` score on syntax, for the worst field type. An alias is not resolved."),
    _value("type.exhaustive", "3.3", "Exhaustiveness", TY, A, "Reads `pub` as written, so a `pub` type in a private module counts as exported."),
    _value("type.correlated_options", "3.3", "Correlated `Option` fields", TY, A, "Struct literals matched by name."),
    _value("type.public_invariant_fields", "3.3", "Public fields with a visible invariant", TY),
    _value("type.foreign_field_access", "3.3", "Foreign field access", TY, A, "Field accesses matched by field name; names shared by several structs are skipped."),
    _value("type.plain_setters", "3.3", "Plain setters, empty encapsulation", TY),
    _value("type.empty_encapsulation", "3.3", "Plain setters, empty encapsulation", TY),
    _value("codebase.data_clumps", "3.3", "Data clumps", CB),
    _value("function.feature_envy", "3.3", "Feature envy", FN, A, "Field receivers counted without types; getters hide access."),
    _value("function.foreign_fields", "3.3", "Feature envy", FN, A, "Field receivers counted without types; getters hide access."),
    _value("type.wmc", "3.3", "Type complexity, god type", TY),
    _higher("type.tcc", "3.3", "Type complexity, god type", TY),
    _value("type.god_type", "3.3", "Type complexity, god type", TY),
    _value("type.data_class", "3.3", "Data class", TY, A, "Accessors are recognized by the shape of their body; derived traits are not seen."),
    _value("type.lazy_class", "3.3", "Lazy class", TY, A, "No published rule with numbers was found; the rule is the one of the crate cha-core."),
    _value("type.missing_traits", "3.3", "Missing common traits", TY, A, "Checks `Debug` by derive or impl block; compiler warnings are not used."),
    _out("type.memory_layout", "3.3", "Memory layout size (report)", "Needs nightly `-Z print-type-sizes`."),
    # 3.4 File, folder, module and crate lenses
    _value("file.length", "3.4", "Length", FL),
    _value("file.code_lines", "3.4", "Size", FL),
    _value("file.comment_lines", "3.4", "Size", FL),
    _value("file.blank_lines", "3.4", "Size", FL),
    _value("file.production_lines", "3.4", "Size", FL),
    _value("file.test_lines", "3.4", "Size", FL),
    _value("file.macro_lines", "3.4", "Lines inside macro calls", FL),
    _value("file.macro_line_share", "3.4", "Lines inside macro calls", FL),
    _value("file.items", "3.4", "Items per file", FL),
    _value("file.unformatted", "3.4", "Formatter conformance", FL, F, "Runs `cargo fmt --all -- --check -l`."),
    _value("file.orphan", "3.4", "Orphan", FL, A, "Follows `mod` declarations in syntax. A `mod` behind any `cfg` counts as included, and a file read only by a build script or as test data counts as an orphan."),
    _value("file.duplicated_line_share", "3.4", "Duplicated-line share", FL, A, "Smog's own detector on its syntax tokens, not PMD CPD; test code is left out."),
    _value("file.functions", "3.4", "Function count", FL),
    _value("module.files_per_folder", "3.4", "Files per folder", MD),
    _value("module.subfolders_per_folder", "3.4", "Subfolders per folder", MD),
    _value("module.folder_depth", "3.4", "Folder depth", MD),
    _value("module.submodules", "3.4", "Modules", MD),
    _value("crate.modules", "3.4", "Modules", CR),
    _value("codebase.modules", "3.4", "Modules", CB),
    _value("module.public_items", "3.4", "Public items", MD),
    _value("crate.public_items", "3.4", "Public items", CR),
    _value("crate.public_api_items", "3.4", "Public API size", CR, A, "Exported `pub` items from `pub mod` and `pub use` syntax; cargo-public-api needs nightly and is not run. Fields, variants and trait methods are not counted."),
    _higher("crate.documentation_coverage", "3.6", "Interface documentation", CR, A, "Read from syntax; which items are exported follows `pub mod` and `pub use`, and rustdoc's nightly `--show-coverage` is not run."),
    _higher("crate.example_coverage", "3.6", "Example coverage", CR, A, "Read from syntax; which items are exported follows `pub mod` and `pub use`, and rustdoc's nightly `--show-coverage` is not run."),
    _value("crate.lines", "3.4", "Lines", CR),
    _value("crate.dependencies_internal", "3.4", "Crate dependencies, internal and external", CR),
    _value("crate.dependencies_external", "3.4", "Crate dependencies, internal and external", CR),
    _value("crate.dependencies_dev", "3.4", "Crate dependencies, internal and external", CR),
    _value("crate.dependencies_total", "3.4", "Dependency count", CR, A, "Read from Cargo.lock, which holds every platform and feature; no value without a lock file."),
    _value("crate.dependencies_total_dev", "3.4", "Dependency count", CR, A, "Read from Cargo.lock, which holds every platform and feature; no value without a lock file."),
    _value("crate.duplicate_versions", "3.4", "Duplicate versions", CR, A, "Read from Cargo.lock, which holds every platform and feature; no value without a lock file."),
    _value("crate.unused_dependencies", "3.4", "Unused dependencies", CR, A, "Looks for the dependency name in source tokens, as cargo-machete does; the compiler is not asked."),
    _higher("crate.audited_dependency_share", "3.4", "Audited-dependency share", CR, A, "Reads cargo-vet's audits.toml and imports.lock in `supply-chain`; exemptions and trusted publishers do not count, criteria are not compared, and cargo-crev is not read. No value without those files."),
    _value("crate.instability", "3.4", "Instability, distance from the main sequence", CR, C, "A crate with no dependency on or from another workspace crate has no value."),
    _value("crate.distance_main_sequence", "3.4", "Instability, distance from the main sequence", CR, C, "A crate with no dependency on or from another workspace crate has no value."),
    _value("module.afferent", "3.4", "Incoming and outgoing module dependencies", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("module.efferent", "3.4", "Incoming and outgoing module dependencies", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("module.instability", "3.4", "Instability, distance from the main sequence", MD, A, "Module-use graph from `use` paths and qualified paths. A module with no edge has no value."),
    _value("module.abstractness", "3.4", "Abstractness", MD, A, "No source maps abstractness to Rust: traits count as abstract, structs, enums and unions as concrete."),
    _value("module.distance_main_sequence", "3.4", "Instability, distance from the main sequence", MD, A, "Built on module.abstractness and module.instability. A module with no edge has no value."),
    _value("module.catch_all_name", "3.4", "Catch-all names", MD),
    _value("module.name_repetition", "3.4", "Name repetition", MD),
    _value("module.public_structs", "3.4", "Public struct count", MD),
    _value("module.delegation_share", "3.4", "Delegation share", MD, A, "No source gives a counting rule; a delegating method is recognized by the shape of its body."),
    _value("module.unreachable_pub", "3.4", "Unreachable `pub`", MD, A, "From `pub mod` and `pub use` syntax, so a leak through a signature is not seen; with `--full` and the tool `clippy`, rustc's `unreachable_pub` lint replaces it."),
    _value("module.cycle_size", "3.4", "Cycle membership", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("module.degree_centrality", "3.4", "Centrality", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("module.closeness_centrality", "3.4", "Centrality", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("module.betweenness_centrality", "3.4", "Centrality", MD, A, "Module-use graph from `use` paths and qualified paths, without name resolution."),
    _value("codebase.propagation_cost", "3.4", "Propagation cost", CB, A, "File graph from `use` paths and qualified paths; the source counts function calls between files."),
    _higher("codebase.decoupling_level", "3.4", "Decoupling Level", CB, A, "File graph from `use` paths and qualified paths. Modules from the Design Rule Hierarchy algorithm of ASE 2009, not from the paper's unpublished tool, so a module can differ from the paper's."),
    _out(
        "codebase.balanced_coupling",
        "3.4",
        "Balanced-coupling score",
        "Needs every reference classified by strength (intrusive, functional, model, contract); cargo-coupling does that in 2,660 lines and gives no value per module.",
    ),
    _higher("module.interface_depth", "3.4", "Interface depth", MD),
    _value("crate.over_wide_visibility", "3.4", "Over-wide visibility", CR, A, "Public names used only in their own module, matched by name."),
    _value("crate.leaked_external_types", "3.4", "Leaked external types", CR, A, "Finds dependency paths in public signatures; a `use` import hides them."),
    _value("crate.unsafe_in_dependencies", "3.4", "Unsafe code in dependencies", CR, F, "Runs cargo-geiger once per crate, offline."),
    _value("crate.semver_violations", "3.4", "SemVer violations", CR, F, "Runs cargo-semver-checks against the ref; needs a ref and a library crate that builds at both commits."),
    _value("crate.exposed_dependencies", "3.4", "Exposed private dependencies", CR, A, "Dependency names and imported names matched in the syntax of the public interface; rustc's `exported_private_dependencies` needs nightly."),
    _value("crate.exposed_unstable_dependencies", "3.4", "Exposed private dependencies", CR, A, "Built on crate.exposed_dependencies and the versions in Cargo.lock; no value without a lock file."),
    _value("crate.reexports_foreign", "3.4", "Re-exports", CR),
    _value("crate.reexports_internal", "3.4", "Re-exports", CR),
    _value("crate.multiple_public_paths", "3.4", "Multiple public paths", CR, A, "From `pub use` syntax; rustdoc JSON needs nightly."),
    _value("codebase.largest_cyclic_group", "3.4", "Largest cyclic group", CB, A, "File graph from `use` paths."),
    _value("file.crossing", "3.4", "Crossing", FL, A, "File graph from `use` paths."),
    _value("file.central_position", "3.4", "Central position (report)", FL, A, "PageRank on the file graph from `use` paths."),
    _higher("module.internal_edge_share", "3.4", "Internal edge share (report)", MD, A, "File edges, not item edges."),
    _value("crate.rebuild_radius", "3.4", "Rebuild radius", CR),
    # 3.5 Codebase lenses
    _value("codebase.lenses_over_target", "3.5", "Lenses over target", CB),
    _value("codebase.lint_density", "3.5", "Lint warning density", CB, F, "Runs `cargo clippy` with pedantic lints."),
    _value("codebase.warnings", "3.5", "Warning count", CB, F, "Runs `cargo clippy` with pedantic lints on library and binary targets; test code is not linted."),
    _value("codebase.compiler_warnings", "3.5", "Warning count", CB, F, "Runs `cargo clippy` with pedantic lints on library and binary targets; test code is not linted."),
    _value("codebase.clippy_warnings", "3.5", "Warning count", CB, F, "Runs `cargo clippy` with pedantic lints on library and binary targets; test code is not linted."),
    _value("file.suppressions", "3.5", "Lint suppressions", FL),
    _value("codebase.suppressions", "3.5", "Lint suppressions", CB),
    _value("file.unused_code", "3.5", "Unused code", FL, F, "Runs `cargo clippy` with pedantic lints on library and binary targets; test code is not linted. A `pub` item of a library is never reported."),
    _value("codebase.unused_code", "3.5", "Unused code", CB, F, "Runs `cargo clippy` with pedantic lints on library and binary targets; test code is not linted. A `pub` item of a library is never reported."),
    _value("function.inconsistent_clone", "3.5", "Inconsistent clones", FN, A, "Whole function bodies are compared line by line with names and literals normalized; a copied block inside two different functions is not found, and intended differences count."),
    _value("codebase.inconsistent_clone_groups", "3.5", "Inconsistent clones", CB, A, "Whole function bodies are compared line by line with names and literals normalized; a copied block inside two different functions is not found, and intended differences count."),
    _value("file.cross_entropy", "3.5", "Naturalness", FL, A, "An n-gram model of the other files with absolute discounting, not the Kneser-Ney smoothing and 10-fold cross-validation of the source."),
    _value("codebase.cross_entropy", "3.5", "Naturalness", CB, A, "An n-gram model of the other files with absolute discounting, not the Kneser-Ney smoothing and 10-fold cross-validation of the source."),
    _value("codebase.flaw_counts", "3.5", "Flaw counts beside averages", CB, A, "Built on the file graph and on commits."),
    _value("codebase.transitive_packages", "3.5", "Dependency weight", CB),
    _value("codebase.packages_per_direct", "3.5", "Dependency weight", CB),
    _value("codebase.duplicate_versions", "3.5", "Dependency weight", CB),
    _out("codebase.dependency_age", "3.5", "Dependency age (report)", "Needs a network fetch of the registry index."),
    _value("codebase.debt_markers", "3.5", "Admitted-debt markers", CB),
    _out("codebase.technical_debt_ratio", "3.5", "Technical debt ratio", "Needs a time estimate for the fix of each finding, which Smog does not have. Its debt is a sum of penalties."),
    _value("codebase.build_time", "3.5", "Build time (report)", CB, F, "Clean build in a temporary target folder; the rebuild after touching a low-level file is not run."),
    _value("codebase.debt_trend", "3.5", "Debt trend (report)", CB, A, "File-local lenses per commit. " + _COMMITS),
    _higher("codebase.debt_lowering_share", "3.5", "Debt trend (report)", CB, A, "File-local lenses per commit. " + _COMMITS),
    _value("codebase.finding_age", "3.5", "Finding age (report)", CB, A, "File-local lenses per commit. " + _COMMITS),
    _higher("codebase.findings_removed_ratio", "3.5", "Finding age (report)", CB, A, "File-local lenses per commit. " + _COMMITS),
    _higher("codebase.equilibrium", "3.5", "Equilibrium score", CB, A, "File-local lenses per commit. " + _COMMITS),
    # 3.6 Comment lenses
    _value("file.slop_findings", "3.6", "Slop findings", FL),
    _value("codebase.doc_slop_findings", "3.6", "Slop findings", CB, C, "Markdown documents."),
    _value("file.restating_comments", "3.6", "Comments that restate the code", FL),
    _value("file.decorative_comments", "3.6", "Section-header and decorative comments", FL),
    _value("file.comment_density", "3.6", "Comment density (report)", FL),
    _value("function.comment_density", "3.6", "Comment density (report)", FN),
    _value("function.comment_name_overlap", "3.6", "Comment–name overlap", FN),
    _value("function.inline_comment_words", "3.6", "Inline comment length", FN),
    _value("function.missing_failure_docs", "3.6", "Missing failure documentation", FN, A, "Reads `pub` and the return type as written: a `pub` function in a private module counts, any return type whose name ends in `Result` counts as `Result`, and a panic in a called function is not seen."),
    _value("file.undocumented_public", "3.6", "Interface documentation", FL),
    _value("file.missing_module_doc", "3.6", "Interface documentation", FL),
    _value("file.long_first_sentence", "3.6", "Interface documentation", FL),
    _value("file.wet_docs", "3.6", "Interface documentation", FL),
    _value("file.stale_docs", "3.6", "Stale documentation", FL, A, "Names resolve against syntax. Signature changes need a ref and are reported as diff.stale_signature_docs."),
    _out(
        "file.comment_code_inconsistency",
        "3.6",
        "Comment–code inconsistency",
        "Needs a trained classifier, which Smog does not ship. file.stale_docs and diff.stale_signature_docs are the rules it has.",
    ),
    _value("diff.stale_signature_docs", "3.6", "Stale documentation", DF, C, "Needs a ref."),
    # 3.7 PR lenses. The diff against the named ref stands in for the PR.
    _value("diff.lines_changed", "3.7", "Lines changed, excluding generated files", DF),
    _value("diff.added_lines", "3.7", "Added lines", DF),
    _value("diff.deleted_lines", "3.7", "Added lines", DF),
    _value("diff.files_touched", "3.7", "Files touched", DF),
    _value("diff.crates_touched", "3.7", "Crates and layers touched", DF),
    _value("diff.layers_touched", "3.7", "Crates and layers touched", DF, C, "Needs layers named with `policy.layer`."),
    _value("diff.entropy", "3.7", "Entropy of the change over files", DF),
    _value("diff.debt_in_untouched_code", "3.7", "Debt added to code the PR did not touch", DF),
    _value("diff.change_groups", "3.7", "Disconnected change groups", DF, A, "Links functions by name."),
    _value("diff.outside_largest_group", "3.7", "Disconnected change groups", DF, A, "Links functions by name."),
    _value("diff.moved_line_share", "3.7", "Moved-line share", DF),
    _value("diff.cosmetic_share", "3.7", "Cosmetic lines", DF, A, "Functions only."),
    _value("diff.touched_lines", "3.7", "State of the touched files (report)", DF),
    _value("diff.touched_directories", "3.7", "State of the touched files (report)", DF),
    _value("diff.touched_prior_commits", "3.7", "State of the touched files (report)", DF, C, _COMMITS),
    _value("diff.touched_age_days", "3.7", "State of the touched files (report)", DF, C, _COMMITS),
    _value("diff.speculative_additions", "3.7", "Speculative additions", DF, A, "Uses matched by name; generics with one instantiation are not checked."),
    _value("diff.public_api_changes", "3.7", "Public API change", DF, A, "Signature hashes from syntax; cargo-public-api and cargo-semver-checks are not used."),
    _value("diff.lockfile_changes", "3.7", "Lockfile change", DF),
    _value("diff.changed_expected_values", "3.7", "Changed expected values", DF),
    _value("diff.warnings_added", "3.7", "Warnings added", DF, F, "Runs Clippy on the ref and on the working tree."),
    _value("diff.patch_variation", "3.7", "Patch variation (report)", DF, C, "Commits between the ref and HEAD."),
    # 3.8 Test lenses
    _value("codebase.surviving_mutants", "3.8", "Surviving mutants", CB, F, "Runs cargo-mutants on the diff against the ref, or on the whole codebase with the setting `mutants_scope`."),
    _value("function.missed_mutants", "3.8", "Surviving mutants", FN, F, "Runs cargo-mutants. With the setting `mutants_scope` at `diff`, only functions with lines changed against the ref have mutants."),
    _value("function.mutant_timeouts", "3.8", "Surviving mutants", FN, F, "Runs cargo-mutants."),
    _higher("function.mutation_score", "3.8", "Mutation score", FN, F, "Runs cargo-mutants. A function without a caught or missed mutant has no value."),
    _value("function.pseudo_tested", "3.8", "Pseudo-tested functions", FN, F, "Combines coverage and the whole-body mutants of cargo-mutants. A function without such a mutant has no value."),
    _higher("function.coverage", "3.8", "Coverage", FN, F, "Runs cargo-llvm-cov. A function without a coverable line has no value."),
    _higher("crate.mutation_score", "3.8", "Mutation score", CR, F, "Runs cargo-mutants. With the setting `mutants_scope` at `diff`, only lines changed against the ref have mutants. No value without a caught or missed mutant."),
    _higher("codebase.mutation_score", "3.8", "Mutation score", CB, F, "Runs cargo-mutants on the whole codebase: `--full --mutants tree`, or the setting `mutants_scope` at `tree`. A run on the diff gives no value. No value without a caught or missed mutant."),
    _higher("crate.covered_mutation_score", "3.8", "Mutation score", CR, F, "Runs cargo-mutants and cargo-llvm-cov. No value without a caught or missed mutant on a covered line."),
    _higher("codebase.covered_mutation_score", "3.8", "Mutation score", CB, F, "Runs cargo-mutants on the whole codebase (`--full --mutants tree`) and cargo-llvm-cov. A run on the diff gives no value. No value without a caught or missed mutant on a covered line."),
    _higher("file.coverage", "3.8", "Coverage", FL, F, "Runs cargo-llvm-cov. Test code is left out; no value without a coverable production line."),
    _higher("crate.coverage", "3.8", "Coverage", CR, F, "Runs cargo-llvm-cov. Test code is left out; no value without a coverable production line."),
    _higher("codebase.coverage", "3.8", "Coverage", CB, F, "Runs cargo-llvm-cov. Test code is left out; no value without a coverable production line."),
    _value("codebase.pseudo_tested", "3.8", "Pseudo-tested functions", CB, F, "Combines coverage and cargo-mutants."),
    _value("codebase.uncovered_lines", "3.8", "Uncovered lines", CB, F, "Runs cargo-llvm-cov."),
    _value("diff.uncovered_lines", "3.8", "Uncovered lines", DF, F, "Runs cargo-llvm-cov."),
    _value("crate.tests_per_100_lines", "3.8", "Tests per 100 lines", CR, A, _MACRO_TESTS),
    _value("codebase.tests_per_100_lines", "3.8", "Tests per 100 lines", CB, A, _MACRO_TESTS),
    _value("crate.test_lines_per_line", "3.8", "Test lines per production line", CR),
    _value("codebase.test_lines_per_line", "3.8", "Test lines per production line", CB),
    _value("test.no_assertion", "3.8", "Tests without an assertion", TS),
    _value("test.assertions", "3.8", "Assertion count", TS, A, "Assertion macros in the test's own body; assertions in called helpers are not counted."),
    _value("test.length", "3.8", "Test length", TS),
    _value("test.cyclomatic", "3.8", "Complexity of a test", TS),
    _value("test.cognitive", "3.8", "Complexity of a test", TS),
    _value("test.size_class", "3.8", "Size class", TS, A, "Read from names in the test's own body, not enforced at run time; what helpers and the code under test do is not seen."),
    _higher("codebase.small_test_share", "3.8", "Size class", CB, A, "Read from names in the test's own body, not enforced at run time; what helpers and the code under test do is not seen."),
    _value("codebase.medium_test_share", "3.8", "Size class", CB, A, "Read from names in the test's own body, not enforced at run time; what helpers and the code under test do is not seen."),
    _value("codebase.large_test_share", "3.8", "Size class", CB, A, "Read from names in the test's own body, not enforced at run time; what helpers and the code under test do is not seen."),
    _value("test.scope", "3.8", "Pyramid ratio", TS, A, "No source gives a counting rule; read from the file's path and the names in the test's own body."),
    _value("codebase.unit_test_share", "3.8", "Pyramid ratio", CB, A, "No source gives a counting rule; read from the file's path and the names in the test's own body."),
    _value("codebase.integration_test_share", "3.8", "Pyramid ratio", CB, A, "No source gives a counting rule; read from the file's path and the names in the test's own body."),
    _value("codebase.end_to_end_test_share", "3.8", "Pyramid ratio", CB, A, "No source gives a counting rule; read from the file's path and the names in the test's own body."),
    _value("codebase.test_run_time", "3.8", "Test run time", CB, F, "Whole workspace, not per crate."),
    _out("test.redundant", "3.8", "Redundant tests", "Needs a mutant-by-test matrix that cargo-mutants does not report."),
    _out("test.checked_coverage", "3.8", "Checked coverage", "Needs a test run with dynamic slicing from each assertion; Smog has no tool for that."),
    _value("codebase.message_probe_failures", "3.8", "Message-wording probe", CB, F, "Rewrites prose string literals in a temporary copy and runs the tests."),
    _out("test.behavior_probe", "3.8", "Behavior-preserving probe", "Renaming private items safely needs edits driven by the index; the design calls it speculative."),
    _value("test.non_api_references", "3.8", "Non-API references", TS, A, "Item names matched against private items."),
    _value("test.interaction_assertions", "3.8", "Interaction assertions", TS),
    _value("test.exact_output", "3.8", "Exact-output assertions", TS),
    _value("test.smell.assertion_roulette", "3.8", "Test smell rules", TS),
    _value("test.smell.conditional_logic", "3.8", "Test smell rules", TS),
    _value("test.smell.duplicate_assert", "3.8", "Test smell rules", TS),
    _value("test.smell.eager_test", "3.8", "Test smell rules", TS, A, "tsDetect's rule for Java; production functions are matched by name."),
    _value("test.smell.empty_test", "3.8", "Test smell rules", TS),
    _value("test.smell.exception_handling", "3.8", "Test smell rules", TS, A, "Rust has no throw or catch; `panic!` and `catch_unwind` stand for them."),
    _value("test.smell.ignored_test", "3.8", "Test smell rules", TS),
    _value("test.smell.lazy_test", "3.8", "Test smell rules", TS, A, "tsDetect's rule for Java; production functions are matched by name. The file stands for the test class."),
    _value("test.smell.magic_number", "3.8", "Test smell rules", TS),
    _value("test.smell.mystery_guest", "3.8", "Test smell rules", TS),
    _value("test.smell.print", "3.8", "Test smell rules", TS),
    _value("test.smell.redundant_assertion", "3.8", "Test smell rules", TS),
    _value("test.smell.resource_optimism", "3.8", "Test smell rules", TS, A, "Reads names in the test's own body; a check in a helper is not seen."),
    _value("test.smell.sensitive_equality", "3.8", "Test smell rules", TS, A, "Counts `.to_string()` on anything but a string literal; the receiver's type is not known."),
    _value("test.smell.sleep", "3.8", "Test smell rules", TS),
    _value("test.assertion_block", "3.8", "Assertion blocks", TS),
    _value("test.duplicated_assertion_block", "3.8", "Assertion blocks", TS, A, "No source gives a counting rule; blocks are compared as token text, so a renamed variable hides a copy."),
    _value("codebase.flake_count", "3.8", "Flake rate", CB, F, "Runs the tests twice on the same tree."),
    _value("test.flaky", "3.8", "Flaky tests", TS, F, "Runs cargo-nextest with retries. Not deterministic: the same code can give 0 on one run and 1 on the next. A test is matched to the runner's name by crate and module path."),
    _value("codebase.flaky_tests", "3.8", "Flaky tests", CB, F, "Runs cargo-nextest with retries. Not deterministic: the same code can give 0 on one run and 1 on the next."),
    _value("test.order_dependent", "3.8", "Order-dependent tests", TS, F, "Runs the tests with a nightly toolchain in shuffled orders on one thread. Not deterministic: a test that is flaky for another reason also counts. A test is matched to the runner's name by crate and module path."),
    _value("codebase.order_dependent_tests", "3.8", "Order-dependent tests", CB, F, "Runs the tests with a nightly toolchain in shuffled orders on one thread. Not deterministic: a test that is flaky for another reason also counts."),
    _value("test.duration", "3.8", "Duration", TS, F, "Runs cargo-nextest. Not deterministic: wall-clock time of one run on this machine. A test is matched to the runner's name by crate and module path."),
    _value("codebase.slow_tests", "3.8", "Duration", CB, F, "Runs cargo-nextest. Not deterministic: wall-clock time of one run on this machine."),
    # 3.9 Unreviewed lines
    _value("function.unreviewed_lines", "3.9", "Unreviewed lines", FN, C, _REVIEWS),
    _value("file.unreviewed_lines", "3.9", "Unreviewed lines", FL, C, _REVIEWS),
    _value("file.unreviewed_line_share", "3.9", "Unreviewed line share", FL, C, _REVIEWS),
    _value("crate.unreviewed_lines", "3.9", "Unreviewed lines", CR, C, _REVIEWS),
    _value("crate.unreviewed_line_share", "3.9", "Unreviewed line share", CR, C, _REVIEWS),
    _value("codebase.unreviewed_lines", "3.9", "Unreviewed lines", CB, C, _REVIEWS),
    _value("codebase.unreviewed_line_share", "3.9", "Unreviewed line share", CB, C, _REVIEWS),
    # 3.10 History lenses
    _value("test.churn", "3.10", "Test churn", TS, C, _COMMITS),
    _value("test.relative_churn", "3.10", "Relative test churn", TS, A, "Maps a test to code in its folder. " + _COMMITS),
    _out("test.breakage_rate", "3.10", "Test breakage rate", "Needs a build per commit with base tests spliced in; the design defers it."),
    _value("test.assertion_churn", "3.10", "Assertion churn", TS, C, _COMMITS),
    _value("function.code_churn", "3.10", "Code churn", FN, C, _COMMITS),
    _value("file.code_churn", "3.10", "Code churn", FL, C, _COMMITS),
    _value("crate.relative_churn", "3.10", "Relative code churn", CR, A, "Lines added in the commits of the window, in the files the crate has now, over its code lines now. A line changed twice counts twice, and renames are not followed."),
    _value("crate.relative_deletion", "3.10", "Relative code churn", CR, A, "Lines deleted in the commits of the window, in the files the crate has now, over its code lines now. Git counts the old side of a changed line as deleted."),
    _value("file.relative_churn", "3.10", "Relative code churn", FL, A, "Lines added in the commits of the window over code lines now. A line changed twice counts twice, and renames are not followed."),
    _value("file.relative_deletion", "3.10", "Relative code churn", FL, A, "Lines deleted in the commits of the window over code lines now. Git counts the old side of a changed line as deleted."),
    _value("file.age_months", "3.10", "Age", FL, A, "Counted to the newest commit read, not to today. A file with no change in the window has no value."),
    _value("file.change_coupling", "3.10", "Change coupling", FL, C, _COMMITS),
    _value("codebase.short_term_churn", "3.10", "Short-term churn", CB, A, "Lines are matched by file and text, not tracked through edits; GitClear does not publish its rule for a rewritten line."),
    _higher("codebase.item_survival", "3.10", "Item survival", CB, C, "Median commits until removal. " + _COMMITS),
    _value("codebase.items_removed_early", "3.10", "Item survival", CB, C, _COMMITS),
    _value("codebase.reverts", "3.10", "Reverts", CB, C, _COMMITS),
    _value("codebase.follow_up_fixes", "3.10", "Follow-up fixes", CB, A, "Fix commits recognized by subject; lines matched by text."),
    _value("codebase.unconventional_messages", "3.10", "Message structure", CB, C, "Over the commits of the history window on the first-parent line. Merge and revert commits with git's own subject count as not following the header."),
    _out("codebase.imperative_subjects", "3.10", "Message form: imperative mood", "Needs a part-of-speech tagger or a list of verbs; Smog ships neither."),
    _out("codebase.message_content", "3.10", "Message content", "Needs a trained classifier of what a message says, which Smog does not ship."),
    _out("codebase.working_commits", "3.10", "Working commits", "Needs a build and a test run for every commit of the history window."),
    _value("codebase.long_subjects", "3.10", "Message form", CB, C, "Over the commits of the history window on the first-parent line."),
    _value("codebase.messages_without_body", "3.10", "Message form", CB, C, "Over the commits of the history window on the first-parent line."),
    _value("codebase.long_body_lines", "3.10", "Message form", CB, C, "Over the commits of the history window on the first-parent line."),
    _higher("codebase.fix_references", "3.10", "Fix references", CB, C, "Fix commits are recognized by subject. No value without a fix commit in the window."),
    _value("function.szz_fixes", "3.10", "Bug-introducing commits (SZZ)", FN, A, "Basic SZZ with `git blame --first-parent`; fix commits are recognized by subject, no bug tracker is read, and a commit that only reformatted or moved a line can be blamed."),
    _value("file.szz_fixes", "3.10", "Bug-introducing commits (SZZ)", FL, A, "Basic SZZ with `git blame --first-parent`; fix commits are recognized by subject, no bug tracker is read, and a commit that only reformatted or moved a line can be blamed."),
    _value("codebase.bug_introducing_share", "3.10", "Bug-introducing commits (SZZ)", CB, A, "Basic SZZ with `git blame --first-parent`; fix commits are recognized by subject, no bug tracker is read, and a commit that only reformatted or moved a line can be blamed."),
    _value("codebase.active_branches", "3.10", "Branch and merge measures", CB, A, "Reads the branches of this clone, so the value depends on what was fetched; no source says what an active branch is."),
    _value("codebase.merges_per_day", "3.10", "Branch and merge measures", CB, A, "From merge commits on the first-parent line; a squashed or rebased branch leaves none."),
    _out(
        "codebase.deployment_measures",
        "3.10",
        "Branch and merge measures: time to deployment, failed deployments",
        "The time from commit to deployment and the share of deployments that need a fix come from a deployment system, not from the repository.",
    ),
    _value("codebase.branch_lifetime_days", "3.10", "Branch and merge measures", CB, A, "From merge commits on the first-parent line; a squashed or rebased branch leaves none. No value without a merge commit in the window."),
    _value("codebase.files_changed_together", "3.10", "Files changed together", CB, C, _COMMITS),
    _value("codebase.modularity_violations", "3.10", "Modularity violation", CB, A, "Dependencies from `use` paths. " + _COMMITS),
    _value("file.unstable_interface", "3.10", "Unstable interface", FL, A, "Dependents from `use` paths. " + _COMMITS),
    _value("file.anchor_dominated", "3.10", "Anchor patterns", FL, A, "Dependents from `use` paths. " + _COMMITS),
    _value("codebase.co_changing_clones", "3.10", "Co-changing clones (report)", CB, C, _COMMITS),
    _value("function.hotspot", "3.10", "Hotspots", FN, C, "Commits changing the function times its penalty."),
    _value("file.hotspot", "3.10", "Hotspots", FL, C, "Commits changing the file times its penalty."),
    _value("file.complexity_hotspot", "3.10", "Hotspots", FL, A, "Commits changing the file times the summed cyclomatic complexity of its functions. The sources rank by both numbers and give no formula; the product is Smog's."),
    # Section 4.4: tracked as a lens so a median creeping toward the target stays visible.
    _value("codebase.median_function_length", "4.4", "Line-weighted median", CB),
]

# Measurements that read the syntax of a function body, a test or a method. Code inside a macro call is a run of
# tokens without syntax, so the same code written there gives another value: each is approximate and says so.
# tests/test_macro_status.py measures one body plainly and inside a macro call and names a row that is missing here.
_IN_MACRO = "Code inside a macro call is not parsed, so the same code written there gives another value."
_READS_SYNTAX = (
    "function.abc", "function.abc_assignments", "function.abc_branches", "function.abc_conditions", "function.assertions", "function.block_depth",
    "function.body_lines", "function.branch_count", "function.bumpy_road", "function.complex_conditional", "function.dep_degree",
    "function.feature_envy", "function.flag_params", "function.foreign_fields", "function.halstead_difficulty", "function.halstead_distinct_operands",
    "function.halstead_distinct_operators", "function.halstead_effort", "function.halstead_length", "function.halstead_total_operands",
    "function.halstead_volume", "function.largest_paragraph", "function.local_bindings", "function.loop_depth", "function.maintainability_index",
    "function.npath", "function.panic_points", "function.paragraph_penalty", "function.return_points", "function.short_names", "function.single_char_names",
    "function.statements", "function.vocabulary", "test.assertion_block", "test.cognitive", "test.cyclomatic", "test.exact_output", "test.no_assertion",
    "test.smell.assertion_roulette", "test.smell.conditional_logic", "test.smell.magic_number", "test.smell.print", "type.wmc", "file.cross_entropy",
    "codebase.cross_entropy", "file.complexity_hotspot",
)  # fmt: skip


def _with_macro_limit(row: MetricSpec) -> MetricSpec:
    if row.id not in _READS_SYNTAX:
        return row
    status = A if row.status is C else row.status
    return MetricSpec(row.id, row.section, row.design_name, row.kind, row.piece, status, f"{row.note} {_IN_MACRO}".strip(), row.higher_is_better)


REGISTRY = {row.id: _with_macro_limit(row) for row in _ROWS}
assert set(_READS_SYNTAX) <= set(REGISTRY)



# The checks that judge the diff against the ref. A run that compares nothing does not apply them.
DIFF_CHECKS = ("check.new_suppressions", "check.gate_untouched", "check.tests_not_weakened", "check.assertion_strength", "check.pr_size")
