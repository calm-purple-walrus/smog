# More metrics for what is good and bad

Researched 2026-11-08.

## Answer

This file lists 68 metrics that the measurement model does not have, each with a computation. I ran none of them. I found no evidence on Rust code for any of them, and only a few entries cite studies of agent-written code.

Start with these, because each measures something in `good-bad-1.md` or `good-bad-2.md` that no model lens measures:

| Gap in the model | Metrics |
| --- | --- |
| Section 3.10 says nothing catches new pinned tests at merge time | T1 private access, T3 whole-output assertions |
| A PR with one purpose, or a tangled PR | P1 change partitions, P2 moved-line share, P3 cosmetic changes |
| Over-engineering, part of the top group of causes of reverted agent code | P9 speculative items |
| Unstable interfaces, ranked highest by Mo et al. together with crossings | M2 interface churn, M4 modularity violation, M5 anchor patterns, M6 crossing |
| Struct invariants, which the model's size lenses do not reach | S1 on/off fields, S2 bypassable public fields |
| Over-splitting and entanglement, the named cost of "small" | F7 pass-through functions, F8 one-caller chains |
| "Near every limit at once", which is in section 2 and has no lens | C1 lenses over target |
| Rubber-stamp approvals, where section 3.7 says nothing can do better | P7 approval speed, P8 lines changed after approval |

Three limits apply to the whole list:

- **Understandability:** the F metrics are proxies. [Scalabrino et al.](https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf) tested 121 metrics and found none captures code understandability (from `good-bad-2.md`, not reopened).
- **Size:** most of these will correlate with size. Evaluate them against the length lens before charging for them.
- **Design decisions:** I found no way to compute whether a module hides a design decision, or whether a test asserts something the spec requires. M1 and T1 to T3 only approximate these.

## How to read this

**Who designed what.** Each entry states what its source defines. Unless an entry says the source gives the computation, the Rust computation, including any threshold, is my design.

**How sources were read:**

- "Read directly" means I read the PDF pages.
- All other linked pages came through a fetch tool that summarizes, so check any wording before reusing it.
- "via good-bad-N" means the claim comes from that input file and I did not reopen the source. It is unverified by me.

**Inputs:**

| Input | Meaning |
| --- | --- |
| Syntax | `syn` parse of the source. Production metrics skip `#[cfg(test)]` items and `tests/` |
| Index | The rust-analyzer index the model already uses, for resolved definitions and uses |
| Rustdoc | rustdoc JSON. It needs a nightly toolchain ([cargo-public-api](https://github.com/Enselic/cargo-public-api)), and its format can change and break tools ([cargo-semver-checks](https://github.com/obi1kenobi/cargo-semver-checks)) |
| History | Commits on `main`, each one PR, as in the model. "Window" means the model's rolling window of recent PRs |
| Host | The Git host API. Links below are to GitHub's |

**Kinds:** check and lens as in the model. "Report" means shown beside the score and not charged, which I suggest where the evidence is weak or the direction is unclear.

## Function

### F1. Flag parameters (lens, syntax)

- **Measures:** "many optional or boolean parameters" ([rust-analyzer style](https://rust-analyzer.github.io/book/contributing/style.html), one project's opinion). Clippy's `max-fn-params-bools` defaults to 3 ([configuration](https://doc.rust-lang.org/clippy/lint_configuration.html)). The model counts parameters but not their type.
- **Compute:** for each `fn`, count parameters whose type is `bool`, and separately those whose type is `Option<_>`.
- **Gap:** an `Option` parameter can be a legitimate absent value.

### F2. Literal flag calls (lens, syntax and index)

- **Measures:** rust-analyzer says a function always called with literals should be [split into separate functions](https://rust-analyzer.github.io/book/contributing/style.html).
- **Compute:** for each `fn` with a `bool` parameter, take its call sites from the index. For each `bool` position, compute the share of call sites whose argument is the literal `true` or `false`. Flag the position at 100%.
- **Gap:** a function with one caller reaches 100% trivially. Report the number of call sites too.

### F3. Local variables (lens, syntax)

- **Measures:** too many locals. The Linux kernel says they ["shouldn't exceed 5-10"](https://www.kernel.org/doc/html/latest/process/coding-style.html) (via good-bad-1).
- **Compute:** in each `fn` body, count identifier bindings in `let`, `for`, `if let`, `while let`, match arm and closure parameter patterns. Exclude `_`.
- **Gap:** shadowing counts as a new variable, and Rust style uses it often.

### F4. Indentation sum (lens, text)

- **Measures:** length and nesting together. The kernel says length should fall as complexity and indentation rise (via good-bad-1). The model's nesting lens takes only the maximum.
- **Source:** [Hindle et al.](https://plg.uwaterloo.ca/~migod/papers/2008/icpc08-abram.pdf) (read directly, pages 1 to 4) measured logical indentation on about 13 million diff chunks from 278 projects. They call it "a cheap and accurate proxy" for the complexity of revisions.
- **Compute:** on rustfmt-formatted code, for each non-blank, non-comment line in the function, take leading spaces divided by 4, minus the function's own indentation. Report the sum and the standard deviation. Hindle's example gives a sum of 5 for 6 lines. It also works on diff hunks that do not parse.
- **Gap:** their languages were C, C++, Java, Perl, PHP and Python. Rust match arms and method chains indent more, so targets need local data.

### F5. Bumpy road (lens, syntax)

- **Measures:** a function holding several separate chunks of logic ([CodeScene](https://codescene.io/docs/guides/technical/code-health.html)). The page gives the concept and no algorithm or thresholds.
- **Compute:** walk the top-level statements of the body. Mark a statement deep if it contains control flow nested at least 2 levels. Count maximal runs of consecutive deep statements. Flag at 2 or more.
- **Gap:** my definition may differ from CodeScene's.

### F6. Complex conditional (lens, syntax)

- **Measures:** a branch condition with several AND or OR operators ([CodeScene](https://codescene.io/docs/guides/technical/code-health.html)).
- **Compute:** for each `if`, `while` and match guard condition, count `&&` and `||` nodes. The function's value is the maximum.
- **Gap:** a helper function hides the count without reducing what the reader must follow.

### F7. Pass-through functions (lens, syntax)

- **Measures:** shallow functions. Ousterhout says methods that hide little behind an interface are ["usually pointless"](https://github.com/johnousterhout/aposd-vs-clean-code). He does not define a pass-through in the part I read; the closest example is Martin's one-line `doSomething`.
- **Compute:** flag a `fn` when its body is one call expression, optionally followed by `?`, `.await` or `.into()`, and every argument is one of its own parameters, unchanged and in order. Exclude trait impls. Report the count and the share per module.
- **Gap:** delegation on a newtype and visibility bridges are legitimate.

### F8. One-caller chains (lens, index)

- **Measures:** fragments that must be read together, which Ousterhout calls entangled. Section 3.10 names "functions with one caller" as a guard but gives no formula.
- **Compute:** build the call graph without test callers. A function is one-caller if it is private, has exactly one distinct caller, and the caller is in the same module. For each function, compute the longest path that follows only one-caller callees. Report that length, and the count of one-caller functions per module.
- **Gap:** this cannot see whether two functions are really entangled. [Chowdhury et al.](https://arxiv.org/abs/2205.01842) report that decomposition lowers maintenance effort (via good-bad-2), so extracted helpers are not bad in themselves. Martin and Ousterhout disagree on this.

### F9. Feature envy (lens, index)

- **Measures:** a method tied to another type's data. Fault-proneness rose by a factor of 8 in [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) (via good-bad-1).
- **Source:** the rule is ATFD > few, LAA < 1/3, FDP <= few ([Figueiredo's slides on Lanza and Marinescu](https://homepages.dcc.ufmg.br/~figueiredo/disciplinas/lectures/detection-strategy_v01.pdf), read directly). "Few" is not a number there.
- **Compute:** for each method with `self`:
  - `own` = distinct fields of `Self` read or written.
  - `ATFD` = distinct fields of other types read or written, resolved by the index.
  - `LAA` = `own / (own + ATFD)`.
  - `FDP` = distinct types that own those foreign fields.
- **Gap:** getters hide field access unless trivial getters are counted as fields. Free functions have no `Self`, so they are out of scope.

### F10. Validation-only functions (lens, syntax)

- **Measures:** a check whose result is thrown away. King says to ["Treat functions that return `m ()` with deep suspicion"](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/). Opinion.
- **Compute:** flag a `fn` that returns `Result<(), _>` or `bool`, takes no `&mut` parameter, and has a name matching `^(validate|check|verify|ensure|is_valid)`. Report the count per crate.
- **Gap:** naming-based, so a rename evades it. Predicates such as `is_empty` are not matched and are fine.

### F11. Late input checks (report, syntax)

- **Measures:** shotgun parsing, where validation is mixed into processing and can leave work half done ([King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)). Opinion.
- **Compute:** in each `fn`, find the first statement with a visible effect: an assignment to a non-local, or a call passing `&mut`. Count later statements of the form `if <expr using a parameter> { return Err(..) }`.
- **Gap:** heuristic. A false-positive rate must be measured first, as section 3.4 requires for comment lenses.

### F12. Assertion density (report, syntax)

- **Measures:** TigerBeetle requires an [average of two assertions per function](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md). rust-analyzer says ["Assert liberally"](https://rust-analyzer.github.io/book/contributing/style.html).
- **Compute:** count `assert!`, `assert_eq!`, `assert_ne!` and their `debug_` forms outside tests, skipping those with a constant condition. Divide by the number of functions, per crate.
- **Gap:** trivial assertions pass. These are project policies, not findings.

### F13. Short names (lens, syntax)

- **Measures:** Google wants a name ["long enough to fully communicate"](https://google.github.io/eng-practices/review/reviewer/looking-for.html) what an item is (via good-bad-2). Clippy's `single-char-binding-names-threshold` [defaults to 4](https://doc.rust-lang.org/clippy/lint_configuration.html).
- **Compute:** per `fn`, count bindings with a one-character name, excluding `_`.
- **Gap:** length is not meaning, and `i` in a short loop is fine.

### F14. Halstead and ABC (report, tool)

- **Measures:** other size and complexity views. [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) computes both, so they cost nothing to add.
- **Compute:** read `HALSTEAD` and `ABC` from its output per function.
- **Gap:** Hindle et al. note that these metrics all seem correlated with lines of code. Expect little new information.

## Struct

### S1. On/off fields (lens, syntax)

- **Measures:** states the type allows but may not mean. [Effective Rust](https://effective-rust.com/use-types.html) replaces a `bool` plus a dependent field with an enum, to "make invalid states inexpressible". Clippy's `max-struct-bools` [defaults to 3](https://doc.rust-lang.org/clippy/lint_configuration.html).
- **Compute:** per struct, `n` = `bool` fields + `Option<_>` fields. The fields allow up to `2^n` combinations. Report `n`.
- **Gap:** independent options are legitimate, for example in a config type.

### S2. Bypassable public fields (lens, syntax)

- **Measures:** a public field on a type that has an invariant. Good-bad-2 says only public-field count looks computable and an invariant does not. This entry approximates the invariant. [C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/future-proofing.html) and [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) both allow public fields on passive data, and that is why a plain count is wrong.
- **Compute:** a struct has an invariant signal if either holds:
  - An associated `fn` returns `Self`, `Option<Self>` or `Result<Self, _>`, and its body contains `if`, `match`, `?` or an assertion.
  - A field's doc comment matches `must|only if|invariant`, as in Effective Rust's "`fg_color` must be (0, 0, 0) if `monochrome` is true".

  The value is the number of `pub` and `pub(crate)` fields on structs with the signal.
- **Gap:** invariants with neither signal are missed.

### S3. Primitive fields and parameters (lens, syntax)

- **Measures:** primitive obsession ([CodeScene](https://codescene.io/docs/guides/technical/code-health.html), [M-DESIGN-FOR-AI](https://microsoft.github.io/rust-guidelines/agents/all.txt)). Opinion.
- **Compute:** in public signatures and fields, compute the share whose type is `bool`, an integer, a float, `char`, `String` or `&str`. Separately count adjacent parameters of the same primitive type, which can be swapped by accident.
- **Gap:** a low-level crate is legitimately primitive, so targets vary by layer.

### S4. Data clumps (lens, syntax)

- **Measures:** ["identical groups of variables"](https://refactoring.guru/smells/data-clumps) in different places. Data clumps raised editing effort in [Soh et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf), an experiment with 6 developers (via good-bad-2).
- **Compute:** make a set of `(name, normalized type)` pairs for each `fn` parameter list, excluding `self`, and each struct's fields. Intersect every pair of sets. Keep intersections of size 3 or more. For each, report the number of items that contain it.
- **Gap:** renamed parameters escape. The size of 3 is my choice.

### S5. Type complexity and god type (lens, syntax and index)

- **Measures:** while classes were god classes, median changes were 46, against 12 while they were not ([Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf), via good-bad-1). The model has methods and LCOM4, but not complexity across methods.
- **Source:** the rule is ATFD > few, WMC >= very high, TCC < 1/3 ([slides](https://homepages.dcc.ufmg.br/~figueiredo/disciplinas/lectures/detection-strategy_v01.pdf), read directly). [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) defines WMC as the sum of cyclomatic complexity over a class's methods.
- **Compute:**
  - `WMC` = sum of cyclomatic complexity over methods in all `impl` blocks of the type.
  - `ATFD` = distinct fields of other types used by its methods.
  - `TCC` = method pairs sharing at least one field, divided by all method pairs.
- **Gap:** size is a confound. "Very high" needs local percentiles. Good-bad-1 records an unopened study that may contradict the god class finding after controlling for size.

### S6. Plain setters (lens, syntax)

- **Measures:** rust-analyzer says ["Never provide setters"](https://rust-analyzer.github.io/book/contributing/style.html). One project's opinion.
- **Compute:** count `fn set_*(&mut self, v: T)` whose body is one assignment to a field of `self`.
- **Gap:** a setter that validates is not matched. That is intended.

### S7. Foreign field access (lens, index)

- **Measures:** how much outside code relies on a representation, per [Hyrum's Law](https://www.hyrumslaw.com/) (via good-bad-1). A public field nobody uses costs little, and the model's counts cannot show that.
- **Compute:** per struct, count field reads and writes located in a module other than the struct's own.
- **Gap:** passive data types score high and may be fine.

### S8. Bounds on type definitions (check, syntax)

- **Measures:** [C-STRUCT-BOUNDS](https://rust-lang.github.io/api-guidelines/future-proofing.html): generic data structures should not use bounds that can be derived.
- **Compute:** in `struct` and `enum` generics and `where` clauses, flag any bound naming `Clone`, `Copy`, `Debug`, `Default`, `Hash`, `PartialEq`, `Eq`, `PartialOrd` or `Ord`.
- **Gap:** guidance for public library types. It may not matter in an application.

### S9. Missing common traits (lens, compiler)

- **Measures:** C-COMMON-TRAITS (via good-bad-1), for libraries.
- **Compute:** run `cargo check --message-format=json` with `-W missing_debug_implementations -W missing_copy_implementations`, and count the warnings per crate. Both [lints exist](https://doc.rust-lang.org/rustc/lints/listing/allowed-by-default.html) and cover public types.
- **Gap:** not every type should be `Copy`. Treat that count as report-only.

## Module

### M1. Module depth (lens, syntax or rustdoc)

- **Measures:** Ousterhout's "maximize functionality/(interface complexity)" ([lecture notes](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign), via good-bad-1). The model counts public items, so one function with 12 parameters counts the same as one with none.
- **Compute:**
  - `interface_tokens` = tokens in the signatures of the module's public items, including public fields.
  - `implementation_lines` = non-blank, non-comment lines in the module, private items included, tests excluded.
  - The value is `implementation_lines / interface_tokens`. Low means shallow.
- **Gap:** lines are not functionality, so padding raises the value. Read it with the length lens. I found no study of this ratio.

### M2. Interface churn (lens, history)

- **Measures:** unstable interfaces, ["a widely-used interface that changes frequently"](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html). Good-bad-2 reports from the same summary that unstable interfaces and crossings "contribute the most by far". Association across 19 projects, and I did not confirm that quote myself.
- **Compute:** for each commit on `main`, parse before and after, and hash the normalized signature of every public item per module. Count PRs that added, changed or removed an item, each separately. Report these beside the module's dependents. [`cargo public-api diff ref1..ref2`](https://github.com/Enselic/cargo-public-api) gives the same data but needs nightly per commit.
- **Gap:** a young API churns legitimately, and additions are less suspicious than changes.

### M3. Breaking changes per PR (lens, tool)

- **Measures:** the same instability, at merge time instead of in history.
- **Compute:** run [`cargo semver-checks --baseline-rev <base>`](https://github.com/obi1kenobi/cargo-semver-checks) for each changed crate, and count the failed lints.
- **Gap:** its README says it misses breaking type changes, generics and lifetimes, among others. It is built for published crates. Using it on internal crates is my inference.

### M4. Modularity violation (lens, history and index)

- **Measures:** files that change together with no structural link, sharing an assumption the code does not state. The model's "files changed together" does not compare against the dependency graph.
- **Source:** [Xiao et al. 2016](https://personal.stevens.edu/~lxiao6/papers/ICSE-16-Debt.pdf), equation 10 (read directly, pages 3 to 5).
- **Compute:**
  - `HCP[x,y]` = PRs that changed both x and y, divided by PRs that changed x.
  - Flag a file pair when neither depends on the other and `max(HCP[x,y], HCP[y,x]) >= t`, with at least `n` shared PRs. Checking transitive dependencies as well is my choice.
  - Report flagged pairs per module.
- **Gap:** the paper's worked example discards values below 0.3, but I did not find a stated `t` for flagging. `n` is my addition, because a pair changed once together has a probability of 1. Generated files and lockfiles must be excluded.

### M5. Anchor patterns (lens, history and index)

- **Measures:** whether changes flow the right way across a dependency. An interface should change its dependents, and not the reverse.
- **Source:** [Xiao et al. 2016](https://personal.stevens.edu/~lxiao6/papers/ICSE-16-Debt.pdf), equations 8 and 9 (read directly). They call these two forms of unstable interface.
- **Compute:** for each file `a` and each file `m` that depends on `a`, where `a` does not depend on `m`:
  - `m` dominates if `HCP[m,a] >= HCP[a,m]` and `HCP[m,a] != 0`.
  - `a` dominates if `HCP[a,m] >= HCP[m,a]` and `HCP[a,m] != 0`.
  - Anchor submissive count = dependents that dominate `a`. Anchor dominant count = dependents `a` dominates.
- **Gap:** the paper works per release and I adapt it to a window. Small counts give unstable probabilities.

### M6. Crossing (lens, index)

- **Measures:** [a file with both high fan-in and high fan-out](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html). The model has both directions on items, not this combination on files.
- **Compute:** per file, take distinct files that depend on it and distinct files it depends on. The value is `min(fan_in, fan_out)`, so a high value requires both.
- **Gap:** I could not open the [Mo et al. paper](https://www.cs.drexel.edu/~yc349/papers/2019/tse2019.pdf), so its thresholds are unread and `min` is my choice.

### M7. Dependency neighborhood and centrality (report, index)

- **Measures:** central units are more defect-prone.
- **Source:** [Zimmermann and Nagappan 2008](https://thomas-zimmermann.com/publications/files/zimmermann-icse-2008.pdf) (read directly, pages 3 to 6). On Windows Server 2003, Spearman correlation with defects was .462 for degree and ego size, .466 for effective size, .428 for eigenvector and .319 for betweenness. Lines, parameters and complexity totals reached about .5, so the case rests mainly on recall: closeness found 60% of critical binaries, against 30% for complexity metrics.
- **Compute:** lift item edges to a module graph, ignoring multiplicity, as the paper lifts to binaries. Per module:
  - `ego_size` = the module plus its in-neighbors and out-neighbors.
  - `effective_size` = neighbors minus the average number of ties among them. The paper's example gives 3 for three unconnected neighbors, and 1 for three fully connected ones.
  - `eigenvector` = eigenvector centrality by power iteration.
- **Gap:** these are binaries in one product, not Rust modules. Betweenness did worse than simpler measures, so I would not start with it.

### M8. Leaked external types (lens, tool)

- **Measures:** [M-DONT-LEAK-TYPES](https://microsoft.github.io/rust-guidelines/agents/all.txt): do not leak third-party types if you can avoid it.
- **Compute:** run [`cargo +nightly check-external-types`](https://lib.rs/crates/cargo-check-external-types) with its `markdown-table` output, and count rows per crate. An allow-list is available in `Cargo.toml`.
- **Gap:** library guidance. An internal crate may share a dependency on purpose.

### M9. Re-exports (lens, syntax)

- **Measures:** [M-FOREIGN-REEXPORTS](https://microsoft.github.io/rust-guidelines/agents/all.txt), and rust-analyzer's ["By default, avoid re-exports"](https://rust-analyzer.github.io/book/contributing/style.html), because a `pub use` can break encapsulation.
- **Compute:** count `pub use` items per crate. Classify one as foreign when the path's first segment is an external dependency, using the dependency names from [`cargo metadata`](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html).
- **Gap:** a crate root that defines its public shape with `pub use` is common, so internal re-exports may need a separate target.

### M10. Multiple public paths (lens, rustdoc)

- **Measures:** [M-SINGLE-ITEM-PATH](https://microsoft.github.io/rust-guidelines/agents/all.txt): a public item should be reachable through one path.
- **Compute:** walk rustdoc JSON from the crate root through public modules and public `use` items. Map each item ID to the set of paths reaching it. Count items with 2 or more.
- **Gap:** I did not test the walk against the rustdoc JSON format.

### M11. Over-visible items (lens, compiler and index)

- **Measures:** minimal visibility ([Effective Rust, item 22](https://effective-rust.com/visibility.html), via good-bad-2).
- **Compute:** count [`unreachable_pub`](https://doc.rust-lang.org/rustc/lints/listing/allowed-by-default.html) warnings per crate. In a workspace, also count `pub` items of a library crate that the index shows used only inside that crate.
- **Gap:** new API not yet used counts as over-visible. P9 has the same problem.

### M12. Catch-all modules (lens, text)

- **Measures:** folders such as `utils` ([matklad](https://matklad.github.io/2021/08/22/large-rust-workspaces.html), via good-bad-2). Opinion, about crate folders.
- **Compute:** match crate, folder and module names against `^(util|utils|helper|helpers|common|misc|shared)$`. Report the share of lines inside matches.
- **Gap:** a rename evades it, and the name list is my choice.

### M13. Internal edge share (report, index)

- **Measures:** whether a module groups related functionality ([The Rust Book, ch. 7](https://doc.rust-lang.org/book/ch07-00-managing-growing-projects-with-packages-crates-and-modules.html), via good-bad-1).
- **Compute:** count item dependency edges inside the module, and edges crossing its boundary in either direction. The value is `inside / (inside + crossing)`.
- **Gap:** no source gives this formula or a target. Grouping everything into one module maximizes it.

### M14. Interface documentation (lens, compiler and syntax)

- **Measures:** using a function without reading its body. Ousterhout says ["It should be possible to use a method without reading its code"](https://github.com/johnousterhout/aposd-vs-clean-code). Good-bad-2 warns that the model's comment density lens could charge for this documentation, so documentation should be measured separately.
- **Compute:**
  - Undocumented public items: count [`missing_docs`](https://doc.rust-lang.org/rustc/lints/listing/allowed-by-default.html) warnings, or use [`rustdoc --show-coverage --output-format json`](https://doc.rust-lang.org/rustdoc/unstable-features.html), which gives `total`, `with_docs`, `total_examples` and `with_examples` but is unstable.
  - Missing module docs: a public module with no `//!` ([M-MODULE-DOCS](https://microsoft.github.io/rust-guidelines/agents/all.txt)).
  - Long summaries: a first sentence over 15 words ([M-FIRST-DOC-SENTENCE](https://microsoft.github.io/rust-guidelines/agents/all.txt), a rule of thumb).
  - Docs that restate the signature: Jaccard overlap between the first sentence's words and the identifier words in the signature, split on `_`, with stop words removed. Flag at 0.8 or above, which is my threshold.
- **Gap:** presence does not show accuracy. Agents can generate text that passes all four.

## Pull request

### P1. Change partitions (lens, diff and index)

- **Measures:** a tangled PR. In [ClusterChanges](https://blog.acolyer.org/2015/06/26/helping-developers-help-themselves-automatic-decomposition-of-code-review-changes/), a sample of 1,000 Office 2013 changesets had about 45% with one non-trivial partition and nearly 42% with more than one. 16 of 20 developers judged the non-trivial partitions correct and complete. I read a summary, not the paper.
- **Source:** the three linking rules below come from that summary.
- **Compute:** make each diff hunk a node. Link two hunks when any of these holds:
  1. They are in the same function.
  2. One changes a definition and the other changes a use of it.
  3. Both change uses of the same item, which is defined in the changeset but not changed.

  Take connected components. A component is trivial if it sits inside one function, or is one hunk outside any function. Report non-trivial components, trivial components, and the share of changed lines outside the largest component.
- **Gap:** the authors note over-partitioning from common attributes, repeated refactorings and overridden methods. [Herzig et al.](https://www.microsoft.com/en-us/research/publication/the-impact-of-tangled-code-changes-on-defect-prediction-models/) show tangling harms defect data, not that it harms code (via good-bad-1).

### P2. Moved-line share (lens, diff)

- **Measures:** refactoring mixed with behavior changes, which Google says should be [separate](https://google.github.io/eng-practices/review/developer/small-cls.html) (via good-bad-1). A move also inflates the model's "lines changed".
- **Compute:** strip whitespace from removed and added lines, and keep lines with at least 20 alphanumeric characters, the block threshold in [`--color-moved`](https://git-scm.com/docs/git-diff). Moved lines = the multiset intersection of removed and added lines. Share = `2 × moved / (added + removed)`. Own code is needed because Git documents no option that reports the count.
- **Gap:** a block moved and lightly edited counts as new. No source gives a target. A share near 0 or 1 suggests one purpose, and a middle value suggests a mix, which is my inference.

### P3. Cosmetic changes (lens, syntax)

- **Measures:** touching unrelated code, a maintainer rejection reason in [METR 2026](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/).
- **Compute:** for each item changed by the PR, compare before and after:
  - Formatting only: the token streams are equal, ignoring whitespace and comments.
  - Rename only: the token streams are equal after replacing identifiers with placeholders numbered by first appearance.

  Report the share of changed lines in these two groups.
- **Gap:** Google allows small cleanups such as a rename, per good-bad-1. So this needs an allowance above zero.

### P4. Change history measures (lens, diff and history)

- **Measures:** other change-risk factors. The model has crates, files, entropy and total lines changed. [Zeng et al.](https://zhangyuqun.github.io/publications/issta2021.pdf) found that a model using added lines alone beat two deep learning models (via good-bad-2).
- **Source:** [Kamei et al. 2013](https://sailresearch.github.io/sail-website/data/pdfs/TSE_ALarge-ScaleEmpiricalStudyOfJust-in-TimeQualityAssurance.pdf), table 1 (read directly). The definitions are theirs.
- **Compute:**
  - `LA`, `LD`: lines added and deleted, kept separate.
  - `ND`: distinct directories modified.
  - `LT`: lines in the touched files before the change.
  - `NUC`: distinct last-changing commits among the touched files. Their example: file A last changed in α, and B and C in β, gives 2.
  - `AGE`: mean time since each touched file was last modified. Their example gives 4 for 3, 5 and 4 days.
- **Gap:** C, C++ and Java projects, mostly human-era. Leave out `NDEV`, `EXP`, `REXP` and `SEXP`, for the reason the model gives about ownership and experience. `FIX` depends on unreliable labels.

### P5. Failed checks before merge (report, host)

- **Measures:** good-bad-2 reports failing CI as the strongest quantitative signal for unmerged agent PRs in [Ehsani et al. 2026](https://www.alphaxiv.org/abs/2601.15195.md). I confirmed the feature's definition through alphaXiv's text, not that ranking. The outcome there is merging, not defects.
- **Compute:** they counted failed check-runs on the last commit. In this factory the last commit is green at merge, so go further. For every commit on the PR branch, call [`GET /repos/{owner}/{repo}/commits/{ref}/check-runs`](https://docs.github.com/en/rest/checks/runs), count `conclusion == "failure"`, and report the total and the distinct check names.
- **Gap:** agents may use CI as a test loop, so a high count may reflect workflow. This needs the branch commits to still exist when the metric runs.

### P6. Patch variation during review (report, host)

- **Measures:** how much a change was reworked before merge. `PATCH_SD` is the sum of normalized standard deviations of patch churn until submission. Churn across revisions of (45, 45, 43, 49, 49) gives 2.9/46.6 ≈ .06 ([Shimagaki et al.](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf), table 2, read directly).
- **Compute:** for each commit on the PR branch, compute the lines in `git diff <base> <commit>`. The value is standard deviation divided by mean.
- **Gap:** at Sony Mobile, higher values went with less defect-proneness. That direction is the opposite of "rework is bad", and it is one study of human review. Do not charge for it.

### P7. Approval speed and discussion (report, host)

- **Measures:** whether review could have happened. Section 3.7 says an approval shows only a click. These facts partly test that.
- **Source:** `SELF_APPROVAL`, `REVIEW_WINDOW`, `HASTILY`, `DISCUSS_LENGTH` and `NO_DISCUSS` are listed in [Shimagaki et al.](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf) (read directly). The page gives no `HASTILY` threshold.
- **Compute:** from [`GET .../pulls/{pull_number}/reviews`](https://docs.github.com/en/rest/pulls/reviews):
  - Self-approved: no `APPROVED` review by an account other than the author and allowed agent accounts.
  - Approval speed: lines changed divided by minutes between the reviewed commit's time and `submitted_at`.
  - No discussion: zero review comments. This needs the review comments endpoint, which I did not open.
- **Gap:** evidence conflicts. [McIntosh et al.](https://rebels.cs.uwaterloo.ca/confpaper/2014/05/30/the-impact-of-code-review-coverage-and-code-review-participation-on-software-quality.html) link low participation to more defects. At Sony Mobile, `SELF_APPROVAL`, `HASTILY`, `DISCUSS_LENGTH` and `REVIEW_WINDOW` provided insignificant explanatory power, and `NO_DISCUSS` was redundant. A slow approval can still be unread.

### P8. Lines changed after approval (check or lens, host and diff)

- **Measures:** code that an approval did not cover. The model's unreviewed-lines metric treats a PR as approved or not.
- **Compute:** take the last `APPROVED` review by an allowed human account, and read its [`commit_id`](https://docs.github.com/en/rest/pulls/reviews). The value is the lines in `git diff <commit_id> <head>`, ignoring whitespace. Count them as unreviewed in section 3.7.
- **Gap:** a rebase changes hashes without changing content, so compare the resulting tree diff and not the commit list.

### P9. Speculative items (lens, diff and index)

- **Measures:** over-engineering. Google says a change should [solve the problem known now](https://google.github.io/eng-practices/review/reviewer/looking-for.html) (via good-bad-1). Unintended side effects and overengineering were the top group of causes of reverted agent code, at 22.33% of 500 reverting commits ([Oukay et al. 2026](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/)).
- **Compute:** for items the PR adds, count at head:
  - Items with no non-test use.
  - Traits with exactly one `impl` in the workspace.
  - `pub` items with no use outside their own module.
  - Generic parameters instantiated with only one concrete type. This one needs type inference and is the most expensive.
- **Gap:** stacked PRs add items that a later PR uses, so this should be charged only after the following PR, or reported. Single-impl traits are also used for test doubles. Oukay's category includes side effects, so 22.33% overstates over-engineering alone.

### P10. Description checks (lens, host)

- **Measures:** a vague description, such as those on [Google's list](https://google.github.io/eng-practices/review/developer/cl-descriptions.html). The model has no description lens.
- **Compute:**
  - Vague title: normalized title matches the list "fix bug", "fix build", "add patch", "phase 1", or a similar project list.
  - Short text: title under 7 words, or body under 80 words. [Pham and Ghaleb](https://arxiv.org/pdf/2601.17627) (read directly) found these lengths associated with higher similarity between PR text and commit messages.
  - False references: the share of backticked identifiers and paths in the body that appear in neither the diff nor the repository. This one is my design.
- **Gap:** length is easily padded, and their "good" label is a similarity score, not a quality judgment. I left out their embedding-based similarity because of the model's objection to run-to-run variation. Whether embeddings vary in that way is not verified.

### P11. Duplicate PR (lens, host and diff)

- **Measures:** duplicates were 23% of rejected PRs sampled in [Ehsani et al.](https://www.alphaxiv.org/abs/2601.15195.md), labeled manually. The paper describes no automated method.
- **Compute:** make a set of `(file, item)` pairs the PR changes. Compute Jaccard overlap with each open PR and each PR merged in the window. Report the maximum.
- **Gap:** my design and untested. Two PRs in a busy file overlap without being duplicates, so a threshold needs calibration.

### P12. Warnings added (lens, compiler)

- **Measures:** quality decline that lints allow. Static analysis warnings rose persistently after Cursor adoption ([He et al.](https://arxiv.org/abs/2511.04427), abstract only). The model's lint check is pass/fail for `deny` lints only.
- **Compute:** run `cargo clippy --message-format=json` with a broader lint set on base and head. Fingerprint each warning as `(lint, item path, normalized message)`, and take the set difference. Report warnings added per 100 changed lines. [Cynthia et al.](https://arxiv.org/abs/2601.20109) used the same base-against-merged comparison with SonarQube, and found that differences between agents "largely disappear after normalizing by code churn" (abstract only).
- **Gap:** broad lint groups include matters of taste. Choose the set before relying on the count.

## Codebase

### C1. Lenses over target (lens, derived)

- **Measures:** "near every limit at once" (section 2). In [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf), median changes rose from 12 with no smells to 54 with three (via good-bad-1). This also addresses the weakness in section 4.4, where the worst lens hides the others.
- **Compute:** for each piece, count lenses with a penalty above 0. Report the distribution, and the share of lines in pieces with 3 or more.
- **Gap:** correlated lenses, such as length and complexity, count separately. Group them first. Palomba's smells are not the model's lenses.

### C2. Debt trend and improving PRs (report, derived)

- **Measures:** health that improves over time. Google's standard is that a change ["definitely improves the overall code health"](https://google.github.io/eng-practices/review/reviewer/standard.html) (via good-bad-1).
- **Compute:** store each PR's debt change. Report the Theil-Sen slope of debt per 1,000 lines over the last `N` PRs, and the share of PRs with a negative debt change.
- **Gap:** both values depend on the chosen lenses. A deletion lowers debt without improving anything else.

### C3. Finding age and fix rate (report, derived)

- **Measures:** problems that stay. Palomba et al. cite Tufano et al. for "almost 80%" of smells never being removed (via good-bad-1, a second-hand claim).
- **Compute:** fingerprint each finding as `(lens, item path)`. Store the first PR that reports it. Report median age in PRs, and findings removed divided by findings added in the window.
- **Gap:** renames reset age, unless rename detection maps the item path.

### C4. Relative code churn (lens, history)

- **Measures:** good-bad-1 notes a difference from section 3.8: [Nagappan and Ball](https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/) report absolute churn as a poor predictor of defect density and relative churn as highly predictive.
- **Compute:** per crate over the window, `(added lines + deleted lines) / lines at the window's end`. `RELATIVE_CHURN` in [Shimagaki et al.](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf) is churn normalized by size (read directly).
- **Gap:** I could not open the full Nagappan paper, so its exact measures are unread. At Sony Mobile, `RELATIVE_CHURN` was redundant in the model and churn had a negative relationship with defects.

### C5. Item survival (lens, history)

- **Measures:** code that does not last. Symbols added by agents were removed after a median of 3 days, against 34 for humans, and symbol churn was 7.33% against 4.10% ([Pham and Ghaleb](https://arxiv.org/pdf/2601.17627), read directly). The model's short-term churn counts lines, so moved or reformatted lines blur it.
- **Compute:** per commit, parse and list items as `(module path, kind, name)`. An item is introduced at the first commit containing it and removed at the first commit without it. Report the share of items removed within `N` PRs, and median survival in PRs and days.
- **Gap:** they used regular expressions on patches in TypeScript, Python and Go, and name the limits. They also say documentation and test tasks may explain early removal. A rename looks like a removal here.

### C6. Co-changing clones (report, syntax and history)

- **Measures:** duplication that costs something. DORA and Metz disagree on duplication (via good-bad-1), and the model reports it only. CodeScene detects ["duplicated logic that is actually changed together"](https://codescene.io/docs/guides/technical/code-health.html). I infer that this narrower form may avoid that dispute, because the copies have already shown they are one concept.
- **Compute:** hash each function body's tokens with identifiers replaced by placeholders. For each pair of equal hashes, count PRs that changed both, and PRs that changed one only.
- **Gap:** near-duplicates are missed by exact hashing. CodeScene's method is not on the page.

### C7. Dependency weight (lens, tool)

- **Measures:** few and stable dependencies. rust-analyzer is ["very conservative"](https://rust-analyzer.github.io/book/contributing/style.html) with crates.io dependencies. Microsoft's M-SMALLER-CRATES points the other way for internal crates.
- **Compute:** from [`cargo metadata --format-version=1`](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html), walk `resolve.nodes`, following `deps` where `dep_kinds.kind` is `null`:
  - Transitive packages per workspace crate.
  - For each direct dependency, packages that would disappear if it were removed.
  - Packages with several versions, the same set as [`cargo tree -d`](https://doc.rust-lang.org/cargo/commands/cargo-tree.html).
  - PR delta of the package count.
- **Gap:** a package count ignores size and quality.

### C8. Libyear (report, tool)

- **Measures:** [the cumulative age of dependencies compared with current stable releases](https://chaoss.community/kb/metric-libyears/). CHAOSS gives no formula and lists cumulative, average and median forms.
- **Compute:** for each direct dependency in `Cargo.lock`, take `pubtime` of the latest non-yanked, non-prerelease version minus `pubtime` of the locked version, from the [registry index](https://doc.rust-lang.org/cargo/reference/registry-index.html). Sum in years.
- **Gap:** `pubtime` is optional, so older entries may need another source. Old does not mean bad for a finished crate.

### C9. Rebuild radius (lens, tool)

- **Measures:** parts that can change independently ([DORA](https://dora.dev/capabilities/loosely-coupled-teams/), via good-bad-1). The model's propagation cost is one number for the codebase and does not show one crate or one PR.
- **Compute:** from `resolve.nodes`, build the reverse graph among workspace members. Per crate, the value is the number of members reachable in reverse. Per PR, it is the union over changed crates.
- **Gap:** this measures declared dependencies, not whether a change affects them.

### C10. Build time (report, tool)

- **Measures:** compile cost, which good-bad-2 gives as one of rust-analyzer's reasons for few dependencies.
- **Compute:** time `cargo build --workspace` from clean, and again after touching one low-level file. [`cargo build --timings`](https://doc.rust-lang.org/cargo/reference/timings.html) gives per-unit detail, but the page documents only an HTML report.
- **Gap:** noisy. Apply section 5.3.

### C11. Architecture document check (check, text and index)

- **Measures:** a short overview with a code map and invariants ([matklad](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html)). Opinion. He advises naming files and types without linking them, and revisiting a couple of times a year.
- **Compute:** check that `ARCHITECTURE.md` exists. Extract backticked names, and report the share that resolve to neither a repository path nor an indexed symbol.
- **Gap:** this catches stale names, not false statements. The check is my design.

## Test code

### T1. Private access (lens, index)

- **Measures:** tests tied to implementation at merge time. Google says tests using only public APIs access the system ["in the same manner that its users would"](https://abseil.io/resources/swe-book/html/ch12.html). This approximates pinning before any history exists.
- **Compute:** take the crate's public items from `cargo public-api`. For each test function, resolve the production items it references. The value is the share not in the public list. Report it, and the share of tests in `tests/`, which can reach only public items.
- **Gap:** Rust places unit tests beside private code by convention, and a test of a pure private function may be sound. No study I found links this share to pinning.

### T2. Interaction assertions (lens, syntax)

- **Measures:** tests of calls and not of state. Google's preferred test expresses ["the state of the system under test"](https://abseil.io/resources/swe-book/html/ch12.html) after the action.
- **Compute:** per test, count matches from a configured list of mock constructs, such as `.expect_*()` and `.times(..)`. Report the count, and the share of tests with at least one.
- **Gap:** a mock of a slow or external system is legitimate. A search summary of [Spadini et al.](https://link.springer.com/article/10.1007/s10664-018-9663-0) says mocks raise coupling between test and production code. I could not open the paper.

### T3. Whole-output assertions (lens, syntax)

- **Measures:** tests that assert exact output, which section 3.8 identifies as how pinned tests kill mutants.
- **Compute:** classify an assertion as whole-output when any of these holds:
  - It is an `insta` snapshot macro. [Insta](https://insta.rs/docs/) is a snapshot testing tool; I did not read its macro list, so the list needs checking.
  - An `assert_eq!` argument contains a string literal of 40 or more characters.
  - An argument contains `format!("{:?}", ..)` or `.to_string()`.

  Report the share per test and per crate.
- **Gap:** golden files are correct for a format the spec defines, so allow them by path. The 40 is my choice. I found no study measuring how often such assertions break on refactoring.

### T4. Logic in tests (lens, syntax)

- **Measures:** Google: ["Clear tests are trivially correct upon inspection"](https://abseil.io/resources/swe-book/html/ch12.html).
- **Compute:** count `if`, `match`, `for`, `while` and `loop` in each test body.
- **Gap:** table-driven tests use one loop legitimately, so the target should allow it.

### T5. Flake rate (lens, runner)

- **Measures:** tests that fail for non-bug reasons. A flaky test has ["both a passing and failing status across multiple test runs for the same commit"](https://docs.datadoghq.com/tests/flaky_tests/). Section 5.3 asks for run-to-run noise but has no per-test lens.
- **Compute:** store each test's result keyed by `(test, tree hash)` for all CI runs. The value is the share of a test's tree hashes that have both a pass and a fail.
- **Gap:** without repeated runs on the same tree, it stays near zero. So schedule repeats on unchanged commits.

### T6. Ignored tests (check, diff)

- **Measures:** a suppression that section 3.1 does not list. rust-analyzer also says ["Do not use `#[should_panic]` tests"](https://rust-analyzer.github.io/book/contributing/style.html).
- **Compute:** in the diff, flag added `#[ignore]` and `#[should_panic]` attributes.
- **Gap:** `#[should_panic]` is one project's rule, so it can be a separate option.

### T7. Assertion downgrade (check or lens, syntax)

- **Measures:** weakening without removal, which the model's "tests are not weakened" check misses. [ImpossibleBench](https://arxiv.org/abs/2510.20270) describes a spectrum of test exploitation by agents, from test modification upward (abstract only).
- **Compute:** give each assertion a tier:
  - 3: `assert_eq!`, `assert_ne!` or `matches!` against a specific value.
  - 2: `assert!` on another condition.
  - 1: `assert!` on `is_ok`, `is_err`, `is_some`, `is_none` or `!is_empty`.

  For tests matched between base and head by name, flag a lower tier sum.
- **Gap:** refactoring a test can legitimately change tiers, and the tiers are my design. This pulls against T3, because the strongest tier also includes exact comparison.

### T8. Assertion blocks (lens, syntax)

- **Measures:** large and copy-pasted assertion blocks ([CodeScene](https://codescene.io/docs/guides/technical/code-health.html)), and Google's one test per behavior.
- **Compute:** per test, find the longest run of consecutive assertion statements. Across tests, hash normalized runs of 3 or more, and count repeats.
- **Gap:** thresholds are mine. CodeScene's page gives none.

## Lower value, considered and left out

| Idea | Why |
| --- | --- |
| Churn entropy per crate | [Kamei et al.](https://sailresearch.github.io/sail-website/data/pdfs/TSE_ALarge-ScaleEmpiricalStudyOfJust-in-TimeQualityAssurance.pdf) define the formula. In [Shimagaki et al.](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf), entropy provided insignificant explanatory power |
| Developer count, experience | The model excludes these, because one agent writes everything |
| Decoupling Level | A possible alternative to propagation cost, but I could not read [the formula](https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf), so I cannot say how to compute it |
| PR-to-commit embedding similarity | Depends on an embedding model, which is close to the model's objection to LLM judgment |

## Not verified

**Failed to open:**

- [Mo et al. 2019](https://www.cs.drexel.edu/~yc349/papers/2019/tse2019.pdf) and the [Decoupling Level paper](https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf): certificate error. So crossing and clique thresholds, and the DL formula, are unread. The revised algorithms in Mo et al. may differ from the Xiao et al. 2016 definitions I used.
- [Nagappan and Ball PDF](https://www.st.cs.uni-saarland.de/edu/recommendation-systems/papers/ICSE05Churn.pdf): connection refused. I read the abstract only.
- [Spadini et al.](https://link.springer.com/article/10.1007/s10664-018-9663-0): redirected to a login. Its claims in T2 come from a search summary.
- [Huo and Clause 2014 on brittle assertions](https://personal.utdallas.edu/~lxz144130/cs6301-readings/oracle-huo-fse14.pdf): redirected away. A search summary describes brittle assertions as depending on irrelevant values, which matches T3. I did not read it.
- [Cox et al. on dependency freshness](https://www.cs.ru.nl/masters-theses/2014/J_Cox___Measuring_dependency_freshness_in_software_systems.pdf): I did not read the formula. A search summary says systems with outdated dependencies are four times as likely to have security issues. I make no claim from that.
- [Clippy lint list](https://clippy.rust-lang.org/master/index.html): I read only parts, and did not reach the lints I looked for, so I used the [configuration page](https://doc.rust-lang.org/clippy/lint_configuration.html) instead.

**Read partly:**

- [aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code): the first 100,000 characters.
- [Microsoft Rust guidelines](https://microsoft.github.io/rust-guidelines/agents/all.txt): the first 100,000 characters.
- PDFs: only the pages named in each entry.

**Discrepancy in a source:** Pham and Ghaleb's text gives a median time to next file modification of 23 days for humans, and their table 3 gives 29.2. I do not use either number.

**Assumed from general knowledge, with no source opened for this file:**

- `syn` does not expand macros, so syntax metrics do not see code inside macro calls.
- A rust-analyzer index can resolve receiver types and field access accurately enough for F9 and S5.
- Trait, generic and macro-heavy code may limit the index in ways I did not test.
- The cost of per-commit parsing for M2 and C5, which section 6.1 would need to accept. I expect a cache keyed by file hash to make it practical, but this is untested.

**Not searched:** evidence specific to Rust for any metric here. Both input files also report finding none.
