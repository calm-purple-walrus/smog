"""The standard selection: the measurements that feed the score unless the policy says otherwise.

Each row is a measurement ID with its curve numbers, group and weight, in the form `Policy.select` takes.
A measurement not listed here is still measured and reported. `Policy.select`, `Policy.deselect` and
`Policy.use_selection` change the selection in force.

Where a number comes from is noted on its row: a published default, the owner's stated number, or a choice.
No number is validated on Rust code. `codebase.mutation_score` needs a whole-tree mutation run, and
`codebase.unreviewed_line_share` needs review data once the policy lists humans; a run without that data gives no score.
"""

import math

STANDARD_SELECTION = {
    # Target: the owner's "30 to 50 lines". Limit: Clippy `too_many_lines`, default 100.
    "function.length": {"target": 40, "limit": 100, "group": "size", "weight": 1.0},
    # A choice: one unbroken paragraph of 40 lines gives penalty 1, like a function of 100 lines.
    "function.paragraph_penalty": {"target": 0, "limit": 40, "power": 1.0, "knee": math.inf, "group": "size", "weight": 1.0},
    # Target: SonarSource and PMD, default 15. Limit: a choice.
    "function.cognitive": {"target": 15, "limit": 35, "group": "complexity", "weight": 1.0},
    # Target: PMD `AvoidDeeplyNestedIfStmts`, default 3. Limit: a choice.
    "function.nesting": {"target": 3, "limit": 6, "group": "complexity", "weight": 1.0},
    # Target: PMD `TooManyFields`, default 15 (a Java rule). Limit: a choice.
    "type.fields": {"target": 15, "limit": 40, "group": "size", "weight": 1.0},
    # A choice; no published default was found.
    "file.length": {"target": 800, "limit": 4000, "group": "size", "weight": 1.0},
    # Chosen from measured distributions, not from a published source: the tightest limit for this target at which
    # no measured codebase has more than a quarter of its files lose more than 5%. A file with 6 findings loses 4.8%.
    "file.slop_findings": {"target": 0, "limit": 20, "group": "comments", "weight": 1.0},
    # Target: the SonarQube gate of 3% duplication. Limit: the whole file is a copy.
    "file.duplicated_line_share": {"target": 0.03, "limit": 1.0, "group": "duplication", "weight": 1.0},
    # A choice, as for the next two rows.
    "module.files_per_folder": {"target": 25, "limit": 120, "group": "layout", "weight": 1.0},
    "module.subfolders_per_folder": {"target": 15, "limit": 80, "group": "layout", "weight": 1.0},
    "crate.modules": {"target": 100, "limit": 400, "group": "size", "weight": 1.0},
    # A choice. Low side: five codebases measured 2.0 to 3.3 tests per 100 lines.
    "codebase.tests_per_100_lines": {"target": 15, "limit": 40, "low_target": 2, "low_limit": 0, "group": "tests", "weight": 1.0},
    # Chosen from measured distributions, not from a published source: of five codebases the worst (503 findings)
    # gets penalty 0.45 and the second worst (167) loses 4.8%. The count is not divided by the amount of text.
    "codebase.doc_slop_findings": {"target": 0, "limit": 750, "group": "documents", "weight": 1.0},
    # A choice: charged below 0.8, penalty 1 at 0. The high side is out of reach, since the value is at most 1.
    "codebase.mutation_score": {"target": 1, "limit": 2, "low_target": 0.8, "low_limit": 0, "group": "tests", "weight": 1.0},
    # A straight line up to penalty 1 when every line is unreviewed.
    "codebase.unreviewed_line_share": {"target": 0, "limit": 1, "power": 1.0, "knee": math.inf, "group": "review", "weight": 0.1},
}
