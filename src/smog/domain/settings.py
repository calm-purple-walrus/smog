"""Named default settings: every number outside the selection that changes a score, a value or a finding.

Each row is the default, what the number does, and the measurement, check and slop rule IDs it changes. `Policy.setting` overrides a row.
"""

import math
import re

from smog.domain.slop_rules import RULES, SEVERITIES
from smog.domain.slop_rules import settings_rows as slop_rule_settings

# Every measurement computed from the commits of the history window.
_HISTORY_IDS = (
    "function.code_churn", "function.hotspot", "test.churn", "test.relative_churn", "test.assertion_churn", "file.code_churn",
    "file.relative_churn", "file.relative_deletion", "file.age_months", "file.change_coupling", "file.unstable_interface",
    "file.anchor_dominated", "file.hotspot", "file.complexity_hotspot", "crate.relative_churn", "crate.relative_deletion",
    "codebase.short_term_churn", "codebase.item_survival", "codebase.items_removed_early", "codebase.reverts", "codebase.follow_up_fixes",
    "codebase.files_changed_together", "codebase.modularity_violations", "codebase.co_changing_clones", "codebase.debt_trend",
    "codebase.debt_lowering_share", "codebase.finding_age", "codebase.findings_removed_ratio", "codebase.equilibrium",
    "codebase.flaw_counts", "diff.touched_prior_commits", "diff.touched_age_days", "codebase.unconventional_messages",
    "codebase.long_subjects", "codebase.messages_without_body", "codebase.long_body_lines", "codebase.fix_references",
    "function.szz_fixes", "file.szz_fixes", "codebase.bug_introducing_share", "codebase.active_branches", "codebase.merges_per_day",
    "codebase.branch_lifetime_days",
)  # fmt: skip

# The measurements of human review.
_REVIEW_IDS = (
    "function.unreviewed_lines", "file.unreviewed_lines", "file.unreviewed_line_share", "crate.unreviewed_lines",
    "crate.unreviewed_line_share", "codebase.unreviewed_lines", "codebase.unreviewed_line_share",
)  # fmt: skip

# The measurements that count test code or production code. Every measurement of a function, a test or a type
# also depends on which code is test code.
_TEST_CODE_IDS = (
    "file.production_lines", "file.test_lines", "crate.tests_per_100_lines", "codebase.tests_per_100_lines", "crate.test_lines_per_line",
    "codebase.test_lines_per_line", "file.duplicated_line_share",
)  # fmt: skip

SETTINGS = {
    # How penalties become scores.
    "others_share": (0.1, "A group charges its worst measurement plus this share of the others.", ()),
    "worst_items_in_file": (5, "A file's score takes this many of its worst items.", ()),
    "worst_items_combine": (
        "mean",
        "How the scores of a file's worst items become one number: `mean`, `geometric_mean` (one very bad item weighs more) or `min` (the worst item alone).",
        (),
    ),
    "score_decay": (
        1.0,
        "A piece's own score is e to the power of minus this times its penalty, so penalty 1 gives 0.368 by default. `policy.score_function` replaces the formula.",
        (),
    ),
    "aggregate_weight": (
        "lines",
        "What a piece weighs in the mean a module, a crate and the codebase take over what they contain, and in the score of one measurement: "
        "`lines` for its code lines, `equal` for 1 each.",
        (),
    ),
    "aggregate_min_lines": (
        1,
        "With aggregate_weight at `lines`, a piece with fewer code lines than this weighs this many, so that a file without code, "
        "which can still be charged for its length or its slop, reaches the pieces above it.",
        (),
    ),
    # The paragraph charge behind function.paragraph_penalty.
    "paragraph_free_lines": (10, "A code paragraph up to this many lines is free.", ("function.paragraph_penalty",)),
    "paragraph_tolerated_lines": (15, "Up to this many lines a paragraph costs paragraph_tolerated_cost per line past the free size.", ("function.paragraph_penalty",)),
    "paragraph_tolerated_cost": (0.02, "Charge per line between the free and the tolerated paragraph size.", ("function.paragraph_penalty",)),
    "paragraph_cost": (0.10, "Past the tolerated size, this times the square of the lines past it is added.", ("function.paragraph_penalty",)),
    "paragraph_knee_lines": (25, "Past this many lines the paragraph charge grows in a straight line.", ("function.paragraph_penalty",)),
    "report_folder": ("target/smog", "Folder, from the repository root, that each run writes its full report to: report.txt and report.json.", ()),
    "changes_min_drop": (0.01, "A function or test is listed as made worse by the change against the ref when its score fell by this much or more.", ("function.length",)),
    # Thresholds inside measurements.
    "short_names_min_names": (3, "A function with fewer names than this has a short-name share of 0.", ("function.short_names",)),
    "naming_max_words": (4, "An identifier with more words than this is a naming flaw.", ("function.naming_flaws",)),
    "bumpy_road_min_depth": (2, "Control flow nested at least this deep makes a top-level statement a bump.", ("function.bumpy_road",)),
    "feature_envy_foreign_fields_above": (3, "Feature envy needs more foreign fields read than this.", ("function.feature_envy",)),
    "feature_envy_own_share_below": (1 / 3, "Feature envy needs the share of own fields among the fields used to be below this.", ("function.feature_envy",)),
    "feature_envy_max_receivers": (2, "Feature envy needs the foreign fields to come from at most this many receivers.", ("function.feature_envy",)),
    "primitive_share_min_fields": (3, "A type with fewer fields than this has a primitive share of 0.", ("type.primitive_share",)),
    "correlated_options_min_literals": (3, "Struct literals needed before a pair of `Option` fields counts as correlated.", ("type.correlated_options",)),
    "god_type_foreign_fields_above": (5, "A god type's methods read more fields of other values than this.", ("type.god_type",)),
    "god_type_min_complexity": (47, "A god type's methods have at least this summed cyclomatic complexity.", ("type.god_type",)),
    "god_type_cohesion_below": (1 / 3, "A god type has type.tcc below this.", ("type.god_type",)),
    "data_class_weight_below": (1 / 3, "A data class has a share of functional methods among its public methods below this.", ("type.data_class",)),
    "data_class_accessors_above": (3, "A data class with complexity below data_class_complexity_below has more public fields and accessors than this.", ("type.data_class",)),
    "data_class_complexity_below": (31, "Summed method complexity below which data_class_accessors_above applies.", ("type.data_class",)),
    "data_class_many_accessors_above": (5, "A data class with complexity below data_class_high_complexity_below has more public fields and accessors than this.", ("type.data_class",)),
    "data_class_high_complexity_below": (47, "Summed method complexity below which data_class_many_accessors_above applies.", ("type.data_class",)),
    "lazy_class_max_methods": (1, "A lazy class has at most this many methods.", ("type.lazy_class",)),
    "lazy_class_max_lines": (10, "A lazy class has at most this many code lines, definition and methods together.", ("type.lazy_class",)),
    "data_clumps_min_size": (3, "A data clump is at least this many (name, type) pairs shared by two structs or signatures.", ("codebase.data_clumps",)),
    "duplication_min_tokens": (100, "A token sequence of at least this length that occurs more than once is a duplication.", ("file.duplicated_line_share",)),
    "inconsistent_clone_min_lines": (10, "A function body with fewer code lines than this is not compared as a clone.", ("function.inconsistent_clone", "codebase.inconsistent_clone_groups")),
    "inconsistent_clone_max_edits": (5, "Two function bodies are clones when at most this many lines must be inserted, removed or changed to turn one into the other.", ("function.inconsistent_clone", "codebase.inconsistent_clone_groups")),
    "inconsistent_clone_max_edit_ratio": (0.2, "Two function bodies are clones only when the lines to change are at most this share of the longer body.", ("function.inconsistent_clone", "codebase.inconsistent_clone_groups")),
    "naturalness_order": (3, "Tokens in one n-gram of the language model: a token is predicted from this many minus 1 tokens before it.", ("file.cross_entropy", "codebase.cross_entropy")),
    "naturalness_discount": (0.75, "Absolute discount of the language model's smoothing, between 0 and 1: the count taken from each seen n-gram and given to shorter contexts.", ("file.cross_entropy", "codebase.cross_entropy")),
    "adjacent_same_type_min_run": (2, "Neighboring parameters of one type count from a run of this many.", ("function.adjacent_same_type",)),
    "comment_name_max_edit_distance": (
        1,
        "A word of a doc comment matches a word of the function name when at most this many letters must be replaced, added or removed "
        "(the Levenshtein distance). The source of the measurement uses 1.",
        ("function.comment_name_overlap",),
    ),
    "maintainability_index_coefficients": (
        (171, 5.2, 0.23, 16.2),
        "The Maintainability Index is the first number, minus the second times ln(Halstead volume), minus the third times the cyclomatic "
        "complexity, minus the fourth times ln(code lines). The default is the published formula.",
        ("function.maintainability_index",),
    ),
    "type_bound_traits": (
        ("Clone", "Copy", "Debug", "Default", "Hash", "PartialEq", "Eq", "PartialOrd", "Ord"),
        "A type definition with a bound on one of these traits fails the check.",
        ("check.no_type_bounds",),
    ),
    # What is test code. Test code counts as test lines, its functions are test pieces and its types are no pieces.
    "test_attributes": (
        ("test", "rstest", "test_case", "quickcheck", "proptest", "wasm_bindgen_test"),
        "A function with an attribute whose path ends in one of these names is a test, such as `#[test]` or `#[tokio::test]`. Each is a name of letters, digits and `_`.",
        _TEST_CODE_IDS,
    ),
    "test_file_patterns": (
        (),
        "A file whose path from the repository root matches one of these glob patterns, such as `*/test_*.rs` or `crates/test-support/*`, holds only "
        "test code, besides the files below a crate's `tests` folder and those a `#[cfg(test)] mod` declares. `*` also matches `/`. Empty by default, "
        "because a file name does not keep a file out of the product.",
        _TEST_CODE_IDS,
    ),
    # Names the measurements look for. Each list can be replaced; an empty list finds nothing.
    "panic_macros": (("panic", "unreachable", "todo", "unimplemented"), "A call of one of these macros is a panic point.", ("function.panic_points",)),
    "panic_methods": (("unwrap", "expect"), "A call of a method with one of these names is a panic point, whatever the type of its receiver, and a reason for a `Panics` section.", ("function.panic_points", "function.missing_failure_docs")),
    "failure_doc_panic_macros": (("panic", "assert", "assert_eq", "assert_ne"), "A public function that calls one of these macros can panic, so its doc comment needs a `Panics` section.", ("function.missing_failure_docs",)),
    "debug_macros": (("dbg", "print", "println", "eprint", "eprintln", "todo", "unimplemented"), "A call of one of these macros in production code is a debug leftover.", ("function.debug_leftovers",)),
    "adjacent_same_type_exempt_names": (
        ("min", "max", "add", "sub", "mul", "div", "eq", "cmp", "swap", "new", "lerp", "clamp"),
        "A function with one of these names is not charged for neighboring parameters of one type: their order does not matter or is a convention.",
        ("function.adjacent_same_type",),
    ),
    "validation_name_prefixes": (("validate", "check", "verify", "ensure", "is_valid"), "A function that returns a status, changes nothing and has a name starting with one of these only validates.", ("function.validation_only",)),
    "restating_stop_words": (
        ("a", "an", "the", "of", "to", "in", "on", "is", "and", "for", "it", "this", "that"),
        "Words left out when a comment is compared with code or a doc comment with a signature.",
        ("file.restating_comments", "file.wet_docs"),
    ),
    "test_exact_output_macros": (("assert_snapshot", "assert_debug_snapshot", "assert_json_snapshot", "insta", "include_str"), "A call of one of these macros in a test compares exact output.", ("test.exact_output",)),
    "test_mystery_guest_names": (("fs", "File", "TcpStream", "TcpListener", "UdpSocket", "OpenOptions", "Command", "env"), "A token with one of these names in a test reads something outside the test.", ("test.smell.mystery_guest",)),
    "test_print_macros": (("println", "eprintln", "print", "eprint", "dbg"), "A call of one of these macros in a test prints.", ("test.smell.print",)),
    "test_resource_file_names": (("fs", "File", "OpenOptions"), "A test with one of these tokens uses a file.", ("test.smell.resource_optimism",)),
    "test_resource_existence_checks": (("exists", "try_exists", "is_file"), "A test with one of these tokens checks that a file exists before it uses it.", ("test.smell.resource_optimism",)),
    "assertion_roulette_unexplained_above": (1, "A test with more assertions without a message than this is an assertion roulette.", ("test.smell.assertion_roulette",)),
    "eager_test_calls_above": (1, "A test that calls more distinct production functions than this is eager.", ("test.smell.eager_test",)),
    "assertion_block_min_statements": (3, "Neighboring assertions that make a block when looking for blocks copied between tests.", ("test.duplicated_assertion_block",)),
    "test_size_medium_names": (
        ("fs", "File", "OpenOptions", "TcpStream", "TcpListener", "UdpSocket", "Command", "thread", "spawn", "sleep", "tempfile", "tempdir"),
        "A test whose body has one of these tokens is at least medium: it names a file, socket, process, thread or sleep API.",
        ("test.size_class", "codebase.small_test_share", "codebase.medium_test_share", "codebase.large_test_share"),
    ),
    "test_size_local_hosts": (
        ("localhost", "127.0.0.1", "[::1]", "0.0.0.0"),
        "A test with a URL in a string literal whose host is none of these is large.",
        ("test.size_class", "codebase.small_test_share", "codebase.medium_test_share", "codebase.large_test_share"),
    ),
    "test_integration_paths": (
        ("tests/*",),
        "A test in a file whose path inside its crate matches one of these patterns is an integration test.",
        ("test.scope", "codebase.unit_test_share", "codebase.integration_test_share", "codebase.end_to_end_test_share"),
    ),
    "test_end_to_end_paths": (
        ("*e2e*", "*end_to_end*"),
        "A test in a file whose path inside its crate matches one of these patterns is an end-to-end test.",
        ("test.scope", "codebase.unit_test_share", "codebase.integration_test_share", "codebase.end_to_end_test_share"),
    ),
    "test_end_to_end_names": (
        ("Command", "cargo_bin"),
        "A test whose body has one of these tokens is an end-to-end test: it runs a program.",
        ("test.scope", "codebase.unit_test_share", "codebase.integration_test_share", "codebase.end_to_end_test_share"),
    ),
    "exact_output_min_characters": (40, "A string literal of at least this many characters in an assertion counts as exact output.", ("test.exact_output",)),
    "restating_min_words": (3, "A comment with fewer words than this, not counting stop words, is never restating.", ("file.restating_comments",)),
    "restating_overlap": (0.6, "A comment restates the code when at least this share of its words appear in the next line.", ("file.restating_comments",)),
    "long_first_sentence_words": (15, "A doc comment's first sentence is long above this many words.", ("file.long_first_sentence",)),
    "wet_docs_overlap": (0.8, "A doc comment repeats the signature when at least this share of its words appear there.", ("file.wet_docs",)),
    "short_term_window": (5, "Commits before a fix commit in which it looks for the lines it removes.", ("codebase.follow_up_fixes",)),
    "short_term_churn_days": (14, "A line removed or rewritten within this many days of the commit that added it is short-term churn.", ("codebase.short_term_churn",)),
    "active_branch_days": (90, "A branch with a commit in this many days before the newest commit of the window is active.", ("codebase.active_branches",)),
    "fix_commit_pattern": (
        r"^fix(\([^()]*\))?!?: ",
        "A commit whose subject matches this regular expression, in any case, is a fix commit. The default is the `fix` type of Conventional Commits.",
        ("codebase.fix_references", "function.szz_fixes", "file.szz_fixes", "codebase.bug_introducing_share", "codebase.follow_up_fixes"),
    ),
    "files_changed_together_min_commits": (2, "A pair of files counts as changed together when at least this many commits changed both.", ("codebase.files_changed_together",)),
    "subject_max_length": (50, "A commit subject with more characters than this is long.", ("codebase.long_subjects",)),
    "body_line_max_length": (72, "A line of a commit message body with more characters than this is long.", ("codebase.long_body_lines",)),
    "early_removal_commits": (5, "A function removed within this many commits of being added was removed early.", ("codebase.items_removed_early",)),
    "large_commit_files": (50, "A commit with more Rust files than this is skipped when counting files changed together.", ("codebase.files_changed_together", "codebase.modularity_violations", "file.anchor_dominated", "file.change_coupling")),
    "change_coupling_min_revisions": (5, "A pair of files is listed as coupled when the average of their commit counts is at least this.", ("file.change_coupling",)),
    "change_coupling_min_shared": (5, "A pair of files is listed as coupled when at least this many commits changed both.", ("file.change_coupling",)),
    "modularity_min_shared": (3, "Commits two unlinked files must share to count as a modularity violation.", ("codebase.modularity_violations",)),
    "modularity_share": (0.5, "Share of one file's commits that the shared commits must reach.", ("codebase.modularity_violations", "file.anchor_dominated")),
    "unstable_min_changes": (2, "Times a dependent must change with a signature change in this file to count.", ("file.unstable_interface",)),
    "clone_min_lines": (5, "Functions shorter than this are not compared as clones.", ("codebase.co_changing_clones",)),
    "function_match_min_similarity": (
        0.7,
        "A function without a match by file and name on the ref, or in the commit before, is the renamed or moved version of a function removed there when at least this share "
        "of the lines of the longer body are equal, with names and literals normalized. 1 matches equal bodies only.",
        ("diff.debt_in_untouched_code", "diff.cosmetic_share", "diff.stale_signature_docs", "function.code_churn", "test.churn", "test.assertion_churn", "function.szz_fixes", "codebase.item_survival", "codebase.items_removed_early"),
    ),
    "file_match_min_similarity": (
        0.5,
        "A file without a file at its path on the ref is the moved or renamed version of a file gone from its path there when at least this share of the code "
        "lines of the longer file are equal, ignoring indentation. Git's own rename detection uses 0.5.",
        (),
    ),
    "moved_line_min_characters": (20, "A line needs at least this many letters or digits to count as moved.", ("diff.moved_line_share",)),
    "lenses_over_target_min_groups": (3, "A piece counts when it is charged in at least this many groups.", ("codebase.lenses_over_target",)),
    "flaw_counts_crossing_above": (5, "A file counts as a flaw when file.crossing is above this.", ("codebase.flaw_counts",)),
    "flaw_counts_unstable_min": (5, "A file counts as a flaw when file.unstable_interface is at least this.", ("codebase.flaw_counts",)),
    "hotspot_excluded_groups": (("history",), "Groups left out of the penalty a hotspot multiplies churn with.", ("function.hotspot", "file.hotspot")),
    "indentation_width": (4, "Leading spaces that count as one level of indentation.", ("function.indentation_sum",)),
    "catch_all_names": (("util", "utils", "helper", "helpers", "common", "misc", "shared"), "A module or a path segment of a Rust file with one of these names has a catch-all name.", ("module.catch_all_name", "check.catch_all_names")),
    "primitive_types": (
        ("bool", "char", "str", "String", "&str", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64", "i128", "isize", "f32", "f64"),
        "A parameter or field whose type is written as one of these is primitive. One leading `&`, with its lifetime and `mut`, is taken off first.",
        ("function.primitive_param_share", "type.primitive_share"),
    ),
    "primitive_wrapper_types": (("Vec", "Option"), "One of these around a primitive type is primitive too, such as `Vec<u8>`.", ("function.primitive_param_share", "type.primitive_share")),
    "invariant_words": (
        ("must", "always", "never", "invariant", "only if"),
        "A public field whose doc comment holds one of these words, in any case, states an invariant that the field cannot keep.",
        ("type.public_invariant_fields",),
    ),
    "assertion_helper_prefixes": (("assert", "verify", "check_", "expect_"), "A test that calls a function whose name starts with one of these checks something, so it is no test without an assertion.", ("test.no_assertion",)),
    "mock_call_patterns": (("expect_\\w+", "times", "with", "returning"), "A call of a function or method whose whole name matches one of these expressions is an assertion on an interaction.", ("test.interaction_assertions",)),
    "test_sleep_names": (("sleep",), "One of these names in a test is a sleep.", ("test.smell.sleep",)),
    "exact_output_calls": (("to_string", "format"), "An assertion that holds one of these names compares rendered text.", ("test.exact_output",)),
    "sensitive_equality_methods": (("to_string",), "A call of one of these methods on anything but a text literal, in a test, is a sensitive equality.", ("test.smell.sensitive_equality",)),
    "value_assertion_macros": (("assert_eq", "assert_ne", "assert_matches"), "An assertion with one of these macros compares a value: the highest tier.", ("check.assertion_strength",)),
    "value_assertion_words": (("matches",), "An assertion whose text holds one of these compares a value too, such as `assert!(matches!(a, B))`.", ("check.assertion_strength",)),
    "weak_assertion_patterns": (
        ("\\.(is_ok|is_err|is_some|is_none)\\b", "!\\s*.*\\.is_empty\\b"),
        "An `assert!` whose text one of these expressions finds is weak: the lowest tier.",
        ("check.assertion_strength",),
    ),
    "assertion_tier_value": (3, "The tier of an assertion that compares a value. A test whose highest tier is lower than on the ref fails check.assertion_strength.", ("check.assertion_strength",)),
    "assertion_tier_condition": (2, "The tier of an `assert!` on a condition that is not weak.", ("check.assertion_strength",)),
    "assertion_tier_weak": (1, "The tier of a weak `assert!`. A test without an assertion has tier 0.", ("check.assertion_strength",)),
    "type_complexity_reference_score": (1, "Clippy's `type_complexity`: what a reference or raw pointer adds.", ("type.type_complexity",)),
    "type_complexity_type_score": (10, "Clippy's `type_complexity`: what a named type, primitive, tuple, array or slice adds, times its nesting.", ("type.type_complexity",)),
    "type_complexity_trait_object_score": (20, "Clippy's `type_complexity`: what `dyn A + B` adds, times its nesting.", ("type.type_complexity",)),
    "type_complexity_function_score": (50, "Clippy's `type_complexity`: what an `fn` pointer or a `dyn` with a `for<'a>` bound adds, times its nesting.", ("type.type_complexity",)),
    "decorative_comment_patterns": (
        ("[-=*#~_/]{3,}.*", ".*[-=*#~_]{3,}", "(?:section|region|end ?region)\\b.*"),
        "A comment that is no doc comment and whose whole text matches one of these expressions, in any case, is decorative. The run of 3 marks is the quantifier.",
        ("file.decorative_comments",),
    ),
    "suppression_attributes": (("allow", "expect"), "An attribute with one of these names, alone or applied by `cfg_attr`, suppresses a lint.", ("file.suppressions", "codebase.suppressions")),
    "new_suppression_patterns": (
        (
            "#!?\\[\\s*(allow|expect)\\s*\\(",
            "mutants::(skip|exclude_re)",
            "ast-grep-ignore",
            "#\\[\\s*ignore\\b",
            "#\\[\\s*should_panic\\b",
            "#!?\\[\\s*cfg_attr\\s*\\(.*\\b(allow|expect|ignore|should_panic)\\b",
        ),
        "An added line of a Rust file that one of these expressions finds is a new suppression.",
        ("check.new_suppressions",),
    ),
    "manifest_suppression_patterns": (
        ("^\\s*[\\w-]+\\s*=\\s*(\"allow\"|\\{.*\\blevel\\s*=\\s*\"allow\")",),
        "An added line of a `Cargo.toml` that one of these expressions finds is a new suppression: a lint set to `allow` in a `[lints]` table.",
        ("check.new_suppressions",),
    ),
    "rust_fence_patterns": (
        ("rust", "should_panic", "no_run", "compile_fail", "standalone_crate", "test_harness", "edition.*", "E\\d{4}"),
        "A fenced code block of a doc comment is a Rust example when every word after the fence matches one of these expressions as a whole. A fence without a word is one too.",
        ("crate.example_coverage",),
    ),
    "conventional_commit_pattern": (
        "^[A-Za-z][A-Za-z0-9-]*(\\([^()\\s][^()]*\\))?!?: \\S",
        "A commit subject this expression matches from its start has the header of Conventional Commits 1.0.0: `<type>[optional scope][!]: <description>`.",
        ("codebase.unconventional_messages",),
    ),
    "revert_subject_prefixes": (("Revert", "revert"), "A commit whose subject starts with one of these is a revert.", ("codebase.reverts",)),
    "short_name_vowels": ("aeiouy", "A name longer than `short_name_max_letters` is short when none of its words holds one of these letters, such as `cfg`.", ("function.short_names",)),
    "short_name_max_letters": (1, "A name of this many letters or fewer is short.", ("function.short_names",)),
    "debt_marker_words": (("TODO", "FIXME", "HACK", "XXX"), "One of these words in a comment admits debt.", ("codebase.debt_markers",)),
    "debt_marker_macros": (("todo", "unimplemented"), "A call of one of these macros admits debt.", ("codebase.debt_markers",)),
    "getter_name_prefixes": (("get",), "A function named so, or with one of these before `_`, that returns nothing has a name that does not fit.", ("function.name_mismatch",)),
    "predicate_name_prefixes": (("is", "has", "can", "should"), "A function with one of these before `_` in its name that does not return `bool` has a name that does not fit.", ("function.name_mismatch",)),
    "setter_name_prefixes": (("set",), "A function with one of these before `_` in its name that returns a value other than `Self` or `&mut Self` has a name that does not fit.", ("function.name_mismatch",)),
    "module_cycles_skip_nested": (True, "True leaves edges between a module and its ancestors or descendants out of cycle detection; False keeps them.", ("module.cycle_size",)),
    "page_rank_damping": (0.85, "Damping factor of PageRank on the file graph.", ("file.central_position",)),
    "page_rank_rounds": (30, "Rounds of PageRank on the file graph.", ("file.central_position",)),
    "equilibrium_zero_debt_per_1000_lines": (100, "Debt added per density_per_lines added lines (1,000 by default) at which the equilibrium score is 0.", ("codebase.equilibrium",)),
    # The units of densities. A changed unit changes the value, so the targets and limits of a selected row must follow.
    "density_per_lines": (1000, "Code lines a density of the codebase is counted per: debt markers, lint warnings and debt per this many lines.", ("codebase.debt_markers", "codebase.lint_density", "codebase.debt_trend", "codebase.equilibrium")),
    "test_density_per_lines": (100, "Production code lines the test density is counted per. The measurement IDs say 100, the default.", ("codebase.tests_per_100_lines", "crate.tests_per_100_lines")),
    "change_coupling_scale": (100, "The degree of change coupling is this times the shared commits divided by the average commits of the two files: 100 gives a percentage.", ("file.change_coupling",)),
    "generated_header_bytes": (400, "A file is skipped as generated when `@generated` or `Code generated` is in its first bytes, up to this many.", ()),
    # Limits of the slop rules. A rule named here fires at its limit; `Policy.slop_allow` turns a rule off.
    "slop_counted_severities": (
        ("warn",),
        "A slop finding counts in the two measurements when its rule has one of these severities: `warn` or `metric`.",
        ("file.slop_findings", "codebase.doc_slop_findings"),
    ),
    "slop_ari_coefficients": (
        (4.71, 0.5, 21.43),
        "The Automated Readability Index is the first number times the characters per word, plus the second times the words per sentence, "
        "minus the third. The default is the published formula.",
        ("read-ari",),
    ),
    "slop_flesch_coefficients": (
        (206.835, 1.015, 84.6),
        "Flesch Reading Ease is the first number, minus the second times the words per sentence, minus the third times the syllables per word. "
        "The default is the published formula.",
        ("read-flesch",),
    ),
    "slop_min_file_words": (100, "Words a file needs before its densities can warn and its readability is reported.", ("neg-x-not-y", "neg-rather-than", "read-ari", "read-flesch")),
    "slop_len_words_metric": (25, "A sentence with more words than this is a metric hit, and can be a wind-composite hit.", ("len-words", "wind-composite")),
    "slop_len_words_warn": (30, "A sentence with more words than this is a warning.", ("len-words",)),
    "slop_len_chars": (100, "A sentence with more characters than this is a metric hit.", ("len-chars",)),
    "slop_clause_commas": (5, "Commas in a sentence at which the rule fires.", ("clause-commas",)),
    "slop_clause_coordinators": (4, "Conjunctions in a sentence at which the rule fires.", ("clause-coord",)),
    "slop_clause_markers": (3, "Clause markers in a sentence at which the rule fires.", ("clause-markers",)),
    "slop_clause_tails": (2, "Trailing clauses in a sentence at which the rule fires.", ("clause-tails",)),
    "slop_clause_semicolons": (2, "Semicolons in a sentence at which the rule fires.", ("clause-semicolons",)),
    "slop_nest_depth": (2, "Bracket nesting depth in a sentence at which the rule fires.", ("nest-depth",)),
    "slop_nest_asides": (2, "Asides in a sentence at which the rule fires.", ("nest-asides",)),
    "slop_aside_min_words": (2, "A parenthesized span counts as an aside when it has more words than this.", ("nest-asides",)),
    "slop_late_subject_words": (12, "Words before the first comma above which the rule fires.", ("nest-late-subject",)),
    "slop_wind_commas": (3, "Commas that count as one sign of a winding sentence.", ("wind-composite",)),
    "slop_wind_coordinators": (3, "Conjunctions that count as one sign of a winding sentence.", ("wind-composite",)),
    "slop_wind_markers": (3, "Clause markers that count as one sign of a winding sentence.", ("wind-composite",)),
    "slop_wind_depth": (1, "Bracket nesting depth that counts as one sign of a winding sentence.", ("wind-composite",)),
    "slop_wind_tails": (2, "Trailing clauses that count as one sign of a winding sentence.", ("wind-composite",)),
    "slop_wind_signals": (2, "Signs a long sentence needs for the rule to fire.", ("wind-composite",)),
    "slop_paragraph_words": (120, "A paragraph with more words than this fires the rule.", ("para-words",)),
    "slop_len_mean_min_sentences": (5, "Sentences a file needs before its mean sentence length is reported.", ("len-mean",)),
    "slop_rhythm_min_sentences": (8, "Sentences a file needs before the variation of their lengths is judged.", ("rhythm-cv",)),
    "slop_rhythm_cv": (0.35, "Coefficient of variation of sentence lengths below which the rule fires.", ("rhythm-cv",)),
    "slop_rhythm_min_words": (2, "Sentences with at most this many words are left out of the variation.", ("rhythm-cv",)),
    "slop_rhythm_adjacent_sentences": (3, "Neighboring sentences compared for similar length.", ("rhythm-adjacent",)),
    "slop_rhythm_adjacent_spread": (3, "Largest difference in words at which neighboring sentences count as similar.", ("rhythm-adjacent",)),
    "slop_rhythm_starters": (3, "Sentences in one block starting with the same word at which the rule fires.", ("rhythm-starters",)),
    "slop_staccato_words": (6, "A sentence with at most this many words is short.", ("rhythm-staccato",)),
    "slop_staccato_run": (4, "Short sentences in a row at which the rule fires.", ("rhythm-staccato",)),
    "slop_ngram_words": (6, "Length in words of a repeated sequence.", ("rhythm-ngram",)),
    "slop_ngram_repeats": (3, "Times a sequence must appear in a file for the rule to fire.", ("rhythm-ngram",)),
    "slop_cluster_rules": (3, "Different rules with a warning or block on one line at which the rule fires.", ("cluster-paragraph",)),
    "slop_pithy_words": (6, "A sentence with at most this many words can be a pithy fragment.", ("meta-pithy",)),
    "slop_neg_x_not_y_per_paragraph": (2, "Hits in one block at which the rule warns.", ("neg-x-not-y",)),
    "slop_neg_x_not_y_per_1000_words": (3, "Hits per slop_density_per_words words (1,000 by default) in a file at which the rule warns.", ("neg-x-not-y",)),
    "slop_neg_rather_than_per_1000_words": (3, "Hits per slop_density_per_words words (1,000 by default) in a file above which the rule warns.", ("neg-rather-than",)),
    "slop_but_balanced_words": (14, "A sentence with at most this many words can be a balanced `but` sentence.", ("but-balanced",)),
    "slop_but_balanced_difference": (2, "Largest difference in words between the two sides.", ("but-balanced",)),
    "slop_triad_count": (3, "Triads in a file at which the rule can warn.", ("triad-doc",)),
    "slop_triad_share": (0.5, "Triads per paragraph above which the rule warns.", ("triad-doc",)),
    "slop_count_announce_words": (8, "A sentence with at most this many words can announce a count.", ("count-announce",)),
    "slop_count_ordinal_matches": (2, "Ordinal phrases in one block at which the rule fires.", ("count-ordinal",)),
    "slop_vocab_distinct": (3, "Distinct weak words in one block at which the rule warns.", ("vocab-density",)),
    "slop_min_density_words": (200, "Words a file needs before its density of weak words can warn.", ("vocab-density",)),
    "slop_vocab_per_200_words": (3, "Weak words per slop_vocab_density_per_words words (200 by default) in a file at which the rule warns.", ("vocab-density",)),
    "slop_emdash_count": (6, "Em dashes a file needs for the rule to fire.", ("fmt-emdash",)),
    "slop_emdash_per_500_words": (14, "Em dashes per slop_emdash_per_words words (500 by default) a file needs for the rule to fire.", ("fmt-emdash",)),
    "slop_bold_bullets_run": (3, "List items in a row with a bold label at which the rule fires.", ("fmt-bold-bullets",)),
    "slop_title_case_min_words": (4, "Words a heading needs before its capitals are judged.", ("fmt-title-case",)),
    "slop_title_case_long_word": (4, "Letters a word needs to count in the capital share.", ("fmt-title-case",)),
    "slop_title_case_share": (0.8, "Share of capitalized long words at which the rule fires.", ("fmt-title-case",)),
    "slop_hrule_count": (3, "Thematic breaks a file needs for the rule to fire.", ("fmt-hrule",)),
    "slop_ticket_standard_prefixes": (("IEEE", "ISO", "RFC", "SHA", "UTF"), "An `ABC-123` ID whose letters are one of these names a standard, not a ticket.", ("comment-ticket",)),
    "slop_hrule_per_1000_words": (3, "Thematic breaks per slop_density_per_words words (1,000 by default) a file needs for the rule to fire.", ("fmt-hrule",)),
    # Word lists the slop rules read in their code. The lists of the rule data are the `slop_list_*` settings below.
    "slop_abbreviations": (("e.g", "i.e", "vs", "etc", "cf", "al", "approx", "No", "Fig"), "A full stop after one of these does not end a sentence. Each is written without its last full stop.", ()),
    "slop_coordinators": (("and", "or", "but", "nor", "yet"), "The conjunctions counted in a sentence. Each is a word, matched as it is written.", ("clause-coord", "wind-composite")),
    "slop_tail_relative_words": (("which", "where", "whose", "whereby"), "A comma followed by one of these words, each matched as it is written, opens a trailing clause.", ("clause-tails", "wind-composite")),
    "slop_tail_ignored_words": (
        ("including", "using", "following", "according", "assuming", "depending", "given"),
        "A comma followed by one of these words does not open a trailing clause, although the word ends in -ing or stands where one would.",
        ("stock-tail-rate", "clause-tails", "wind-composite"),
    ),
    "slop_late_subject_openers": (
        ("while", "although", "though", "because", "since", "given", "despite", "if", "when", "whereas", "assuming", "in order to"),
        "A sentence that starts with one of these, each matched as it is written, puts its subject late.",
        ("nest-late-subject",),
    ),
    "slop_starter_ignored_words": (("The", "A"), "Sentences that start with one of these words are not counted as starting alike.", ("rhythm-starters",)),
    "slop_count_density_rules": (("count-noun", "count-found", "count-there-are", "count-announce"), "The rules whose hits the density of announced counts adds up.", ("count-density",)),
    "slop_cluster_severities": (("warn",), "A finding counts toward a cluster of rules on one line when it has one of these severities.", ("cluster-paragraph",)),
    "slop_report_once": (
        (("neg-bare", "neg-not-only"), ("neg-not-about", "neg-setup-flip")),
        "Pairs of rules that match the same text: a finding of the first is dropped where the second has one on the same line.",
        ("neg-bare", "neg-not-about"),
    ),
    "slop_density_per_words": (1000, "Words a slop density is counted per. The settings named `per_1000_words` are limits in this unit.", ("meta-adverb-weak", "neg-x-not-y", "neg-rather-than", "count-density", "fmt-hrule")),
    "slop_density_min_count": (2, "Hits a file needs before a density rule warns, whatever its rate.", ("neg-rather-than", "meta-adverb-weak", "but-density", "stock-transition", "stock-tail-rate", "count-density")),
    "slop_density_per_sentences": (100, "Sentences a slop density is counted per.", ("but-density", "stock-transition", "stock-tail-rate")),
    "slop_vocab_density_per_words": (200, "Words the density of weak words is counted per. The setting slop_vocab_per_200_words is a limit in this unit.", ("vocab-density",)),
    "slop_emdash_per_words": (500, "Words the density of em dashes is counted per. The setting slop_emdash_per_500_words is a limit in this unit.", ("fmt-emdash",)),
    "slop_excerpt_characters": (60, "Characters of a sentence quoted in a slop finding about that sentence.", ("len-words", "clause-commas", "clause-coord", "clause-markers", "clause-tails", "clause-semicolons", "nest-depth", "nest-asides", "nest-late-subject", "wind-composite")),
    "slop_heading_excerpt_characters": (30, "Characters of a heading or list item quoted in a slop finding about its first character.", ("fmt-emoji-bullet",)),
    # What the output shows. None of these changes a value or a score.
    "display_pieces": (10, "Rows in the list of the worst pieces of the overview. `--comprehensive` lists every piece.", ()),
    "display_cycle_members": (4, "Members of a dependency cycle named in a failure of the check.", ("check.dependency_cycles",)),
    "display_slop_match_characters": (80, "Characters of the matched text quoted for a slop finding.", ("file.slop_findings", "codebase.doc_slop_findings")),
    # The slow tools.
    "cargo_offline": (
        True,
        "True keeps every cargo call of the slow tools off the network. A tool that needs a dependency cargo has not downloaded then counts as "
        "not run, with the reason: Smog knows this from cargo's own sentences about `--offline`. False lets cargo download.",
        (),
    ),
    "unused_code_lints": (
        ("dead_code", "unused_imports", "unused_variables", "unused_mut", "unused_macros", "unused_assignments", "unreachable_code", "unreachable_patterns", "unused_labels"),
        "A warning of the Clippy run with one of these lint names is unused code.",
        ("file.unused_code", "codebase.unused_code"),
    ),
    "mutants_scope": ("diff", "What cargo-mutants mutates with `--full`: `diff` for the lines changed against the ref, `tree` for the whole codebase.", ("function.missed_mutants", "function.mutant_timeouts", "function.mutation_score", "function.pseudo_tested", "crate.mutation_score", "crate.covered_mutation_score", "codebase.mutation_score", "codebase.covered_mutation_score", "codebase.surviving_mutants", "codebase.pseudo_tested")),
    "mutation_timeouts_caught": (False, "True counts a mutant whose tests timed out as caught; False leaves it out of the ratio.", ("function.mutation_score", "function.pseudo_tested", "crate.mutation_score", "crate.covered_mutation_score", "codebase.mutation_score", "codebase.covered_mutation_score")),
    "flaky_test_retries": (2, "Retries of a failed test under cargo-nextest; a test that then passes is flaky.", ("test.flaky", "codebase.flaky_tests")),
    "slow_test_seconds": (60, "A test whose last attempt takes more seconds than this is slow.", ("codebase.slow_tests",)),
    "test_order_seeds": ((1, 2, 3), "Seeds of the shuffled single-threaded test runs, one run per seed.", ("test.order_dependent", "codebase.order_dependent_tests")),
    # Human review.
    "human_review_marker": ("smog: human-reviewed", "The text of the review marker: a comment line at the top of a file holding this text and the hash of the reviewed commit, and nothing else, covers the lines that have not changed since that commit.", _REVIEW_IDS),
    "human_review_marker_lines": (5, "Lines at the top of a file searched for human_review_marker.", _REVIEW_IDS),
    "review_approving_states": (("APPROVED",), "A human's latest review signs a pull request off when it has one of these GitHub review states.", _REVIEW_IDS),
    "review_ignored_states": (("COMMENTED", "PENDING"), "A review in one of these GitHub review states does not replace an earlier review of the same human.", _REVIEW_IDS),
    "reviews_file": ("", "Path of a JSON file with pull requests and reviews, from the repository root; the README section `Human review` shows its form. With it the review measurements need no network; the `reviews` tool adds what it fetches to it. Empty for none.", _REVIEW_IDS),
    "reviews_api_url": (
        "https://api.github.com",
        "Base URL of the GitHub REST API the `reviews` tool reads. It must start with `https://`. The `origin` remote must be on its host, without a leading `api.`.",
        _REVIEW_IDS,
    ),
    "reviews_page_size": (100, "Rows per page the `reviews` tool asks the GitHub API for. GitHub gives at most 100.", _REVIEW_IDS),
    "reviews_max_pages": (50, "Pages of one list the `reviews` tool reads before it gives up and the tool counts as not run.", _REVIEW_IDS),
    "reviews_refetch": (
        "unmerged",
        "What the `reviews` tool asks GitHub for again, besides the commits the reviews file does not know: `unmerged` for each commit recorded "
        "without a merged pull request, because one may have been merged since; `all` for every commit and the reviews of its pull requests, "
        "which picks up a dismissed approval; `none` for nothing.",
        _REVIEW_IDS,
    ),
    # Settings with their own policy method.
    "effective_length_alpha": (0.5, "Weight of a private one-caller helper's lines in its caller's effective length.", ("function.effective_length",)),
    "history_window": (100, "Commits on the first-parent line read for history.", _HISTORY_IDS),
    "pr_size_lines": (1000, "Changed lines above which check.pr_size fails.", ("check.pr_size",)),
    "pr_size_files": (50, "Touched files above which check.pr_size fails.", ("check.pr_size",)),
}

# The slop rules as settings, generated from the rule data so that this file stays readable: one setting per rule
# that holds its parameters (`slop_rule_<id>`, with `_` for `-`), one per word list (`slop_list_<name>`), and
# `slop_number_words`, `slop_abstract_nouns` and `slop_homonyms`. `--explain <setting>` prints each.
SETTINGS.update(slop_rule_settings())

DEFAULT_SETTINGS = {name: row[0] for name, row in SETTINGS.items()}

# Number settings: (lowest value, highest value, whole numbers only). A value outside the range would end the
# run, give a score above 1 or switch a rule off without a word. A whole number is an `int`: the code counts,
# slices, indexes or compares for equality with it, or hands it to a tool, so `3.0` is refused like `2.5`.
# A number setting that is not listed takes any finite number, and whole numbers only when its default is one.
_RANGES = {
    "others_share": (0, 1, False),
    "function_match_min_similarity": (0, 1, False),
    "file_match_min_similarity": (0, 1, False),
    "naturalness_discount": (0, 1, False),
    "page_rank_damping": (0, 1, False),
    "paragraph_free_lines": (0, math.inf, False),
    "changes_min_drop": (0, 1, False),
    "paragraph_tolerated_lines": (0, math.inf, False),
    "paragraph_knee_lines": (0, math.inf, False),
    "paragraph_tolerated_cost": (0, math.inf, False),
    "paragraph_cost": (0, math.inf, False),
    "aggregate_min_lines": (0, math.inf, False),
    "score_decay": (0, math.inf, False),
    "density_per_lines": (0, math.inf, False),
    "test_density_per_lines": (0, math.inf, False),
    "change_coupling_scale": (0, math.inf, False),
    "slop_density_per_words": (0, math.inf, False),
    "slop_density_per_sentences": (0, math.inf, False),
    "slop_density_min_count": (1, math.inf, True),
    "slop_vocab_density_per_words": (0, math.inf, False),
    "slop_emdash_per_words": (0, math.inf, False),
    "equilibrium_zero_debt_per_1000_lines": (0, math.inf, False),
    "slop_excerpt_characters": (0, math.inf, True),
    "slop_heading_excerpt_characters": (0, math.inf, True),
    "display_pieces": (0, math.inf, True),
    "display_slop_match_characters": (0, math.inf, True),
    "history_window": (0, math.inf, True),
    "short_term_window": (0, math.inf, True),
    "generated_header_bytes": (0, math.inf, True),
    "flaky_test_retries": (0, math.inf, True),
    "worst_items_in_file": (1, math.inf, True),
    "display_cycle_members": (1, math.inf, True),
    "indentation_width": (1, math.inf, True),
    # The language model keeps every sequence of this many tokens, so the time of a run grows with it.
    "naturalness_order": (1, 20, True),
    "page_rank_rounds": (1, math.inf, True),
    "reviews_page_size": (1, 100, True),
    "reviews_max_pages": (1, math.inf, True),
    "duplication_min_tokens": (1, math.inf, True),
    "assertion_block_min_statements": (1, math.inf, True),
    "slop_rhythm_adjacent_sentences": (1, math.inf, True),
    "slop_ngram_words": (1, math.inf, True),
    # A minimum of 0 would divide by the number of words, sentences or names of a text or function that has none.
    "short_names_min_names": (1, math.inf, True),
    "slop_min_file_words": (1, math.inf, True),
    "slop_min_density_words": (1, math.inf, True),
    "slop_len_mean_min_sentences": (1, math.inf, True),
    "slop_rhythm_min_sentences": (1, math.inf, True),
    # A count the rule waits for: at 0 it would fire on a text with nothing in it, or read a match that is not there.
    "slop_count_ordinal_matches": (1, math.inf, True),
    "slop_bold_bullets_run": (1, math.inf, True),
    "slop_staccato_run": (1, math.inf, True),
}
# Number settings that take a fraction although their default is a whole number: sizes the curves read, units,
# rates and times.
_FRACTIONS = (
    "paragraph_free_lines", "paragraph_tolerated_lines", "paragraph_knee_lines", "aggregate_min_lines", "density_per_lines",
    "test_density_per_lines", "change_coupling_scale", "slop_density_per_words", "slop_density_per_sentences", "slop_vocab_density_per_words",
    "slop_emdash_per_words", "equilibrium_zero_debt_per_1000_lines", "slop_neg_x_not_y_per_1000_words", "slop_neg_rather_than_per_1000_words",
    "slop_vocab_per_200_words", "slop_emdash_per_500_words", "slop_hrule_per_1000_words", "slow_test_seconds", "short_term_churn_days",
    "active_branch_days",
)  # fmt: skip
# Number settings that must be above their lowest value: a unit or a divisor of 0 makes every value 0 or ends the
# run, a decay of 0 gives every piece the score 1, and the language model needs a discount above 0.
_ABOVE_LOWEST = (
    "score_decay", "density_per_lines", "test_density_per_lines", "change_coupling_scale", "slop_density_per_words", "slop_density_per_sentences",
    "slop_vocab_density_per_words", "slop_emdash_per_words", "equilibrium_zero_debt_per_1000_lines", "naturalness_discount",
    "function_match_min_similarity", "file_match_min_similarity",
)  # fmt: skip
# List settings whose numbers are whole.
_WHOLE_LISTS = ("test_order_seeds",)
# List settings whose items are names of a fixed set, or pairs of them.
_ITEM_CHOICES = {
    "slop_counted_severities": SEVERITIES,
    "slop_cluster_severities": SEVERITIES,
    "slop_count_density_rules": tuple(RULES),
    "slop_report_once": tuple(RULES),
}
# List settings whose items are names of letters, digits and `_`.
_NAME_LISTS = ("test_attributes",)
# List settings whose items are regular expressions.
_PATTERN_LISTS = ("slop_abstract_nouns", "mock_call_patterns", "weak_assertion_patterns", "decorative_comment_patterns", "new_suppression_patterns", "manifest_suppression_patterns", "rust_fence_patterns")
# List settings a slop rule matches with: empty, the rule would never fire, which `Policy.slop_allow` says openly.
_NEEDED_LISTS = (
    "slop_number_words", "slop_abstract_nouns", "slop_homonyms", "slop_coordinators", "slop_tail_relative_words", "slop_late_subject_openers",
    "slop_count_density_rules", "slop_cluster_severities", "slop_counted_severities",
)  # fmt: skip
# Text settings that may be empty.
_OPTIONAL_TEXTS = ("reviews_file",)
_CHOICES = {
    "mutants_scope": ("diff", "tree"),
    "reviews_refetch": ("unmerged", "all", "none"),
    "worst_items_combine": ("mean", "geometric_mean", "min"),
    "aggregate_weight": ("lines", "equal"),
}


def number_range(name: str) -> tuple[float, float, bool, bool]:
    """(lowest value, highest value, whole numbers only, the lowest value itself is refused) of a number setting."""
    low, high, whole = _RANGES.get(name, (-math.inf, math.inf, isinstance(DEFAULT_SETTINGS[name], int) and name not in _FRACTIONS))
    return low, high, whole, name in _ABOVE_LOWEST


def checked_setting(name: str, value):
    """The value to store for a setting. Raises ValueError unless it has the kind of the default and is in range.

    - A number setting takes a finite number within its range (`number_range`), and an `int` where the range
      says whole numbers only.
    - A true/false setting takes a bool.
    - A text setting takes a string, one of its choices if it has them; it may be empty only where that means
      "none". A regular expression must compile and must not match the empty text, which is found everywhere.
    - A list setting takes a tuple or list whose items have the kind of the default's items, and for the
      coefficients of a formula their number. It is stored as a tuple. No text item may be empty; a list of
      names, such as severities or rule IDs, takes known names only; a list a slop rule matches with may not
      be empty.
    - A setting whose default is a mapping, such as the parameters of a slop rule, takes a mapping with some or
      all of the default's keys, each checked like a setting of its own; the keys left out keep their default.
    - A list of entries, such as a word list, takes for each entry a text or a list of texts no longer than
      the default's entries; an entry is filled up with empty texts, and its expression is checked.
    """
    return _checked(name, DEFAULT_SETTINGS[name], value)


def _is_number(candidate) -> bool:
    return not isinstance(candidate, bool) and isinstance(candidate, (int, float)) and math.isfinite(candidate)


def _checked_pattern(name: str, pattern: str) -> str:
    """A regular expression. One of the slop rules may hold `{N}`, `{ABS}` and `{list:name}`, which are filled in before it compiles."""
    try:
        compiled = re.compile(re.sub(r"\{(?:N|ABS|list:\w+)\}", "x", pattern.removeprefix("(?-i)")))
    except re.error as error:
        raise ValueError(f"the setting {name} holds {pattern!r}, which is not a regular expression: {error}") from error
    if compiled.search(""):
        raise ValueError(f"the setting {name} holds {pattern!r}, which matches the empty text and so is found everywhere")
    return pattern


def _checked(name: str, default, value):
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(f"the setting {name} is True or False, not {value!r}")
    elif isinstance(default, str):
        if not isinstance(value, str):
            raise ValueError(f"the setting {name} is a text, not {value!r}")
        choices = SEVERITIES if name.endswith("severity") else _CHOICES.get(name)
        if choices and value not in choices:
            raise ValueError(f"the setting {name} is one of {', '.join(choices)}, not {value!r}")
        if not value.strip() and name not in _OPTIONAL_TEXTS:
            raise ValueError(f"the setting {name} is a text that is not empty")
        if name.endswith("_pattern"):
            _checked_pattern(name, value)
        if name.endswith("_url") and not value.startswith("https://"):
            raise ValueError(f"the setting {name} is a URL that starts with https://, not {value!r}")
    elif isinstance(default, dict):
        if not isinstance(value, dict) or not set(value) <= set(default):
            unknown = ", ".join(sorted(map(str, set(value) - set(default)))) if isinstance(value, dict) else ""
            raise ValueError(f"the setting {name} is a mapping with the keys {', '.join(default)}, not {f'with {unknown}' if unknown else repr(value)}")
        return {key: _checked(f"{name}.{key}", default[key], value[key]) if key in value else default[key] for key in default}
    elif isinstance(default, tuple):
        return _checked_list(name, default, value)
    else:
        low, high, whole, above = number_range(name)
        if not _is_number(value) or not low <= value <= high or (above and value == low) or (whole and not isinstance(value, int)):
            start = f"above {low:g}" if above else f"from {low:g}"
            between = "" if low == -math.inf else f" {start} to {high:g}" if high != math.inf else f" {start}" if above else f" of {low:g} or more"
            raise ValueError(f"the setting {name} is a finite {'whole ' if whole else ''}number{between}, not {value!r}")
    return value


def _checked_list(name: str, default: tuple, value) -> tuple:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"the setting {name} is a list, not {value!r}")
    if not value and (name in _NEEDED_LISTS or name.endswith(".patterns") or name.startswith("slop_list_")):
        raise ValueError(f"the setting {name} is a list with at least one item: a rule with nothing to match never fires. policy.slop_allow turns a rule off")
    if default and isinstance(default[0], tuple):
        return tuple(_checked_entry(name, len(default[0]), item) for item in value)
    numbers = bool(default) and all(_is_number(item) for item in default)
    if not all(_is_number(item) if numbers else isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"the setting {name} is a list of {'numbers' if numbers else 'texts that are not empty'}, not {value!r}")
    if name.endswith("_coefficients") and len(value) != len(default):
        raise ValueError(f"the setting {name} has {len(default)} numbers, not {len(value)}")
    if name in _WHOLE_LISTS and not all(isinstance(item, int) for item in value):
        raise ValueError(f"the setting {name} is a list of whole numbers, not {value!r}")
    unknown = [item for item in value if item not in _ITEM_CHOICES.get(name, value)]
    if unknown:
        known = _ITEM_CHOICES[name]
        listed = ", ".join(known) if len(known) <= 5 else "the IDs of the slop rules"
        raise ValueError(f"the setting {name} takes {listed}, not {', '.join(map(repr, unknown))}")
    if name in _NAME_LISTS and not all(re.fullmatch(r"\w+", item) for item in value):
        raise ValueError(f"the setting {name} is a list of names of letters, digits and `_`, not {value!r}")
    if name in _PATTERN_LISTS or name.endswith((".patterns", ".exceptions")):
        for item in value:
            _checked_pattern(name, item)
    return tuple(value)


def _checked_entry(name: str, size: int, entry) -> tuple[str, ...]:
    """One entry of a list of entries: a text, or up to `size` texts, filled up with empty texts.

    The first text of a word list is its expression. A homonym is a name, the expression of its mannered use
    and, if wanted, one that excepts a sentence; a pair of rules is two rule IDs.
    """
    texts = (entry,) if isinstance(entry, str) else tuple(entry) if isinstance(entry, (tuple, list)) else None
    if not texts or len(texts) > size or not all(isinstance(text, str) for text in texts):
        raise ValueError(f"the setting {name} takes entries of 1 to {size} texts, not {entry!r}")
    texts = (*texts, *[""] * (size - len(texts)))
    if name in _ITEM_CHOICES:
        unknown = [text for text in texts if text not in _ITEM_CHOICES[name]]
        if unknown:
            raise ValueError(f"the setting {name} takes the IDs of the slop rules, not {', '.join(map(repr, unknown))}")
    elif name == "slop_homonyms":
        if not texts[0].strip():
            raise ValueError(f"the setting {name} takes a name, the expression of the mannered use and one that excepts a sentence, not {entry!r}")
        _checked_pattern(name, texts[1])
        if texts[2]:
            _checked_pattern(name, texts[2])
    else:
        _checked_pattern(name, texts[0])
    return texts


def check_settings_together(settings: dict) -> None:
    """Raise ValueError for settings that are each valid and contradict each other."""
    if not settings["paragraph_free_lines"] <= settings["paragraph_tolerated_lines"] <= settings["paragraph_knee_lines"]:
        raise ValueError(
            "the paragraph settings need paragraph_free_lines <= paragraph_tolerated_lines <= paragraph_knee_lines, not "
            f"{settings['paragraph_free_lines']}, {settings['paragraph_tolerated_lines']}, {settings['paragraph_knee_lines']}"
        )
