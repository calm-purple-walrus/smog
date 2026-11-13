# More metrics for what is good and bad

Researched 2026-11-08. Inputs: `good-bad-1.md`, `good-bad-2.md`, `docs/design/measurement-model.md` (section 3).

## Answer

This file lists 64 metrics that section 3 of the model does not have, each with a computation for Rust. They are not validated for this use:

- No source I opened tested any of them on Rust code or in a code factory. Most evidence is Java, C or C++, on human-written code.
- Metrics marked **Own** are my own definitions. No study tested them. Some turn a guideline into a rule; others are new.
- A computation here says how to get a number. It does not show the number measures the property. [Scalabrino et al.](https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf) (reported in `good-bad-2.md`, not reopened) found none of 121 metrics captured understandability.

The biggest gaps these fill, in my judgment:

| Gap in the model | Metrics |
| --- | --- |
| Section 3.10 says nothing catches pinned tests at merge time | [Message-wording probe](#t1-message-wording-probe), [non-API references](#t4-references-to-non-api-items), [exact-output assertions](#t6-exact-output-assertions) |
| "Tests are not weakened" misses an edited expected value | [Changed expected values](#p8-changed-expected-values) |
| PR purpose is measured only by spread | [Disconnected change groups](#p1-disconnected-change-groups), [no-op lines](#p4-no-op-lines) |
| Over-engineering by agents is unmeasured | [Speculative additions](#p5-speculative-additions) |
| Struct invariants were called uncomputable | [Public fields with a visible invariant](#s4-public-fields-with-a-visible-invariant), [bool fields](#s1-bool-fields), [correlated `Option` fields](#s3-correlated-option-fields) |
| Function lenses miss data flow | [Data-flow edges](#f1-data-flow-edges-depdegree), [vocabulary](#f2-vocabulary) |
| History lenses ignore the dependency graph | [Unstable interface](#m2-unstable-interface), [crossing](#m3-crossing), [modularity violation](#m4-modularity-violation) |

## How to read this

**Source labels:**

- **Read:** I read the passage in the PDF page.
- **Summary:** I read it through a fetch tool that summarizes pages. Check quotes before reusing them.
- **Snippet:** seen only in a search result.
- **Earlier report:** taken from `good-bad-1.md` or `good-bad-2.md`. I did not reopen the source.
- **Own:** my definition. The linked source supports the goal, not the computation.

**Shared inputs:**

| Name | Meaning |
| --- | --- |
| AST | Each `.rs` file parsed with `syn`. Macros are not expanded. `assert!`, `assert_eq!`, `assert_ne!`, `debug_assert*`, `format!`, `panic!` and `matches!` are parsed from their tokens. Other macros are opaque |
| Test code | A function with an attribute whose last segment is `test`, and anything under `#[cfg(test)]` or `tests/`. All else is production code |
| Index | The rust-analyzer index that model section 3.2 already requires. It maps each name use to its definition |
| API | One line per public item from `cargo public-api`, or rustdoc JSON. [Both need nightly](https://github.com/cargo-public-api/cargo-public-api) (Summary) |
| Mutation results | [cargo-mutants `outcomes.json`, `caught.txt`, `missed.txt`](https://mutants.rs/mutants-out.html) (Summary) |
| PR diff | `git diff --find-renames base...head`. Each hunk is mapped to its enclosing item with the AST |
| AST hash | Hash of an item's `syn` tokens, ignoring spans and comments, so formatting does not change it. The model's section 3.8 uses the same idea |
| Item identity | Full path. If a path disappears and the same AST hash appears elsewhere in that commit, it is one item that moved |
| Window | The last N squash-merged PRs, as in section 3.8 |

All thresholds are policy unless a source is named. Generated files are excluded everywhere.

## Codebase

### C1. Lenses over target per piece

- **Wants:** "near every limit at once" (model section 2). Section 4.4 takes the worst lens, so it does not see this.
- **Compute:** for each piece, group correlated lenses (length, complexity, nesting are one group). Count groups with a value above target. Report how many pieces have a count of at least k.
- **Gap:** the grouping is a judgment.
- **Evidence:** median changes rose from 12 with no smells to 54 with three ([Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf), Earlier report). The [abstract](https://research.tudelft.nl/en/publications/on-the-diffuseness-and-the-impact-on-maintainability-of-code-smel) confirms smelly classes are more change- and fault-prone (Summary). **Own** as a count of lenses.

### C2. Lint warning density

- **Wants:** warnings building up, which the `deny` check in section 3.1 does not show for lints outside the denied set.
- **Compute:** run `cargo clippy --workspace --all-targets --message-format=json -- -W clippy::pedantic`. Keep compiler messages of level `warning`. Deduplicate by file, line and lint. Divide by production lines over 1,000. Report per lint.
- **Gap:** pedantic lints are noisy. Agents can suppress them; the "no new suppressions" check covers that.
- **Evidence:** warnings and complexity rose and stayed high after adopting an agent tool, against matched controls ([He et al.](https://arxiv.org/abs/2511.04427), Summary). The abstract does not name the tool or lint set.

### C3. Transitive and duplicated dependencies

- **Wants:** few dependencies. The model counts crate dependencies, not the whole tree.
- **Compute:** from `cargo metadata --format-version 1`, count `resolve.nodes` outside the workspace reachable by normal or build edges. Duplicates: from [`cargo tree -d -e normal,build --prefix none`](https://doc.rust-lang.org/cargo/commands/cargo-tree.html) (Summary), count names listed with more than one version.
- **Gap:** one large crate counts the same as one tiny crate.
- **Evidence:** [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) is "very conservative" with dependencies (Summary, one project). Cargo's docs say duplicates hurt build time and binary size. No defect evidence.

### C4. Unused dependencies

- **Wants:** no more code than needed.
- **Compute:** run [`cargo machete --with-metadata`](https://github.com/bnjbvr/cargo-machete). Exit 1 means at least one was found; exit 2 means an error (Summary). Count the names listed. Suitable as a check.
- **Gap:** the tool calls itself imprecise. Dependencies used only in `build.rs` output are false positives and need its `ignored` list.

### C5. Dependency age (libyear)

- **Wants:** dependencies that are maintained and rarely break the code.
- **Compute:** for each resolved external crate, get the release dates of the locked version and the newest non-yanked, non-prerelease version from the crates.io API. Sum the differences in years.
- **Gap:** an old, finished crate scores badly. Fresh does not mean stable, so this can oppose the goal.
- **Evidence:** [libyear](https://libyear.com/) defines it by example, with no formula (Summary). No evidence it predicts anything.

### C6. Admitted-debt markers

- **Wants:** problems accumulating that the author already knows about.
- **Compute:** count comments matching `\b(TODO|FIXME|HACK|XXX)\b`, plus `todo!()` and `unimplemented!()` calls. Divide by production lines over 1,000. On a PR, count those added.
- **Gap:** agents can reword them, and a marker is more honest than silence, so blocking may hide debt.
- **Evidence:** [Potdar and Shihab](https://bibtex.github.io/ICSME-2014-PotdarS.html) found this debt in 2.4% to 31% of files (Snippet; the page I opened has only the citation). The same snippet says only 26.3% to 63.5% was later removed.

### C7. Build time

- **Wants:** dependencies and crate layout that do not slow work. rust-analyzer cites compile times as a reason to limit dependencies (Earlier report).
- **Compute:** in CI, record wall-clock time of `cargo build --workspace` from a clean target directory, then again after touching one low-level file. [`cargo build --timings`](https://doc.rust-lang.org/cargo/reference/timings.html) gives a per-crate breakdown, but its page documents HTML output only (Summary).
- **Gap:** noisy across machines, so section 5.3 applies. Report only.

### C8. Architecture document freshness

- **Wants:** a short architecture document that stays true (matklad, Earlier report).
- **Compute:** check that `ARCHITECTURE.md` exists. Extract backticked paths and identifiers. Resolve paths on disk and identifiers in the Index. Report the unresolved share.
- **Gap:** catches dead references, not false statements. **Own.**

## Pull request

### P1. Disconnected change groups

- **Wants:** one self-contained change. Files touched and entropy measure spread, not purpose.
- **Compute**, following [ClusterChanges](https://blog.acolyer.org/2015/06/26/helping-developers-help-themselves-automatic-decomposition-of-code-review-changes/) (Summary):
  1. Make each diff hunk a node.
  2. Join two hunks if they are in the same function.
  3. Join them if one changes a definition and the other changes a use of it (Index).
  4. Join them if both change uses of an item defined in the changeset but not itself changed.
  5. Take connected components. A component is trivial if it sits inside one function or is a lone hunk outside any function.
  6. Report the non-trivial components, and the share of changed lines outside the largest component.
- **Gap:** unrelated edits can join through a shared type. One feature can split when the link is a trait object or macro. Formatting hunks should be removed first ([P4](#p4-no-op-lines)).
- **Evidence:** in 1,000 Microsoft Office changesets, about 42% had more than one non-trivial partition. 16 of 20 developers agreed with the partitions. [Herzig et al.](https://www.microsoft.com/en-us/research/publication/the-impact-of-tangled-code-changes-on-defect-prediction-models/) found 7% to 20% of bug fixes tangled (Summary). That study shows harm to defect data, not to code. Splitting has a narrow review benefit ([di Biase et al.](https://arxiv.org/abs/1805.10978), Earlier report).

### P2. Added lines, with deletions discounted

- **Wants:** a size that reflects risk and review load. The model's "lines changed" mixes added and deleted lines.
- **Compute:** from `git diff --numstat`, sum added lines and deleted lines separately. Count a wholly deleted file as one line. Report added lines as the size lens.
- **Gap:** a large mechanical rename still counts in full, although Google exempts output from a [fully trusted refactoring tool](https://google.github.io/eng-practices/review/developer/small-cls.html) (Summary).
- **Evidence:** the deletion rule is Google's. The added-line feature beat other traditional features, and a logistic regression on it alone outperformed two deep learning models, on over 310,370 changes ([Zeng et al. 2021](https://zhangyuqun.github.io/publications/issta2021.pdf), Read, abstract).

### P3. State of the touched files

- **Wants:** how risky the area is that a PR changes, which the model's PR lenses omit.
- **Compute**, from [Kamei et al. Table 1](https://sailresearch.github.io/sail-website/data/pdfs/TSE_ALarge-ScaleEmpiricalStudyOfJust-in-TimeQualityAssurance.pdf) (Read):
  - **LT:** mean lines per modified file before the change.
  - **AGE:** mean, over modified files, of the time since the last PR touched that file.
  - **NUC:** number of distinct earlier PRs in the Window that touched any modified file.
- **Gap:** these describe where a change lands, not whether it is good, so charging a PR for them punishes work on bad code. Report only. Kamei's author metrics (NDEV, EXP, REXP, SEXP) are left out for the reason in section 3.8.
- **Evidence:** I read the table and its rationale, not the results for each measure.

### P4. No-op lines

- **Wants:** no touching of unrelated code.
- **Compute:** for each changed item, compare its AST hash before and after. Equal hash means formatting only. Otherwise, hash again with local names replaced by their order of first appearance; equal means a local rename only. Sum changed lines in such items, and report them as a share of changed lines.
- **Gap:** a rename may be intended. Code outside any item needs a separate rule.
- **Evidence:** maintainers named touching unrelated code as a reason to reject agent PRs ([METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/), Summary). Google says to [separate refactorings](https://google.github.io/eng-practices/review/developer/small-cls.html) (Summary). **Own.**

### P5. Speculative additions

- **Wants:** solves today's problem, not over-engineered.
- **Compute:** in the head commit, using the AST and Index, count items added by the PR that match any rule:
  1. A trait with exactly one `impl`.
  2. A generic parameter that all call sites instantiate with one type.
  3. A function with no caller outside test code.
  4. An enum variant constructed only in test code, or never.
  5. A public struct field never read in the workspace.
- **Gap:** a later PR may add the second implementation, and one-impl traits can serve test doubles. Rule 2 needs type queries, which are the hardest part. Library crates have callers outside the workspace, so skip rules 3 and 5 for their public API.
- **Evidence:** unintended side effects and overengineering together were the top cause of reverted agent code, at 22.33% ([Oukay et al.](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/), Summary). The figure is not for overengineering alone. **Own.**

### P6. Public API change

- **Wants:** a stable, narrow interface. The model counts public items in a snapshot, not changes.
- **Compute:** run [`cargo public-api diff base..head`](https://github.com/cargo-public-api/cargo-public-api) per crate. Count items added, removed and changed. Run [`cargo semver-checks --baseline-rev base`](https://github.com/obi1kenobi/cargo-semver-checks); exit 100 means a violation, 101 means it could not finish (Summary).
- **Gap:** rustdoc JSON is unstable. semver-checks misses some breaking type and generics changes, by its own account. For crates used only inside the workspace, a break is usually harmless, so use the count rather than the check.
- **Evidence:** [Effective Rust](https://effective-rust.com/visibility.html) says making an item public is hard to reverse (Summary). This is guidance.

### P7. Lockfile change

- **Wants:** dependencies do not grow by accident.
- **Compute:** parse `Cargo.lock` at base and head as sets of (name, version). Count added, removed and version-changed packages.
- **Gap:** one wanted dependency can pull in many others, and that may be correct. **Own.** Support is the rust-analyzer rule under C3.

### P8. Changed expected values

- **Wants:** tests not weakened. Section 3.1 catches deleted tests and removed assertions, but not `assert_eq!(x, 3)` edited to `assert_eq!(x, 4)`.
- **Compute:** for each test function in both base and head, extract its assertion macro calls with normalized arguments. Count two kinds of change:
  - **Value changed:** same macro and first argument, different other arguments.
  - **Weakened:** `assert_eq!` or `assert_ne!` replaced by `assert!`, or a new `.is_ok()`, `.is_some()` or `.is_err()` as the asserted expression.
  
  Report each with whether the PR also changed production code the test reaches.
- **Gap:** a requirement change legitimately edits expected values. Only a person or the ticket can tell, so this is a flag for review. Matching assertions across edits is approximate.
- **Evidence:** [ImpossibleBench](https://arxiv.org/abs/2510.20270) describes agents deleting failing tests and studies "simple test modification" (Summary). **Own.**

### P9. Failed CI runs before merge

- **Wants:** how much work the agent needed to get through the gate.
- **Compute:** from the Git host API, list every check run on every commit pushed to the PR. Count failed runs per check, and the commits pushed after the first failure.
- **Gap:** this differs from the study, which counted failures on the last commit only. A merged PR in the factory ends green. Force pushes can lose history unless runs are logged by CI. Report only.
- **Evidence:** each failed check lowered merge odds by about 15% in agent PRs ([Ehsani et al.](https://www.alphaxiv.org/abs/2601.15195.md), Summary). The outcome was merging, not defects.

### P10. Review rounds and comments

- **Wants:** real review. Section 3.7 counts human approval only, and review here is often by agents.
- **Compute:** from the Git host API, count review submissions requesting changes, and review comments per 100 changed lines. At codebase level, report the share of PRs merged with no comment.
- **Gap:** counts show activity, not quality. More comments can mean a worse PR or a better reviewer. Report only.
- **Evidence:** the link between review and defects is mixed ([McIntosh et al.](https://rebels.cs.uwaterloo.ca/confpaper/2014/05/30/the-impact-of-code-review-coverage-and-code-review-participation-on-software-quality.html) against [Sony Mobile](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf), Earlier report).

### P11. Duplicate PR

- **Wants:** no second attempt at work already done.
- **Compute:** for each PR open or merged in the last D days, compute Jaccard similarity of changed-item sets, and token similarity of titles. Flag a pair if both exceed a limit. Linking to the same ticket flags it directly.
- **Gap:** a follow-up PR on the same items looks like a duplicate.
- **Evidence:** duplicates were 142 of 562 categorized rejected agent PRs, 23% ([Ehsani et al.](https://www.alphaxiv.org/abs/2601.15195.md), Summary). **Own** as a computation.

### P12. Description completeness

- **Wants:** the description says what changed and why.
- **Compute:** fail if the title matches a list of vague forms ([Google's examples](https://google.github.io/eng-practices/review/developer/cl-descriptions.html): "Fix bug", "Fix build.", "Add patch.", "Phase 1."), if the body has fewer than k words outside the template, or if no ticket is linked.
- **Gap:** an agent can write filler easily, so this tests presence only. [Tian et al.](https://arxiv.org/abs/2202.02974) studied automatic identification of good commit messages (Snippet); I did not read its accuracy. **Own.**

### P13. Item survival

- **Wants:** "code stays once merged". The model's short-term churn counts lines over a set number of PRs.
- **Compute:** for each function and type a PR adds, follow its Item identity through later commits on `main`. Record the days until it disappears, and mark items still present as censored. Report the Kaplan-Meier median per Window.
- **Gap:** deletion can be healthy. A rename with a body change loses identity and counts as a removal.
- **Evidence:** symbols from agent PRs were removed much sooner, median 3 against 34 days ([Pham and Ghaleb](https://arxiv.org/abs/2601.17627), Summary). The abstract does not say how they tracked symbols.

## Struct

No source I opened studies Rust structs. Results on classes carrying over is my inference.

### S1. Bool fields

- **Wants:** types instead of flags.
- **Compute:** count fields whose type is exactly `bool`, per struct.
- **Gap:** a config struct of independent switches is legitimate.
- **Evidence:** [Clippy's `max-struct-bools` default is 3](https://doc.rust-lang.org/clippy/lint_configuration.html) (Summary). That is a tool default, not a finding. [C-CUSTOM-TYPE](https://rust-lang.github.io/api-guidelines/type-safety.html) warns about `bool` (Summary).

### S2. Primitive field share

- **Wants:** types that carry meaning.
- **Compute:** for structs with at least 3 named fields, divide the fields whose type is an integer, float, `bool`, `char`, `String`, `&str`, or a `Vec` or `Option` of those, by all fields. One-field tuple structs are the fix, so skip them.
- **Gap:** passive data records may be correct like this.
- **Evidence:** [C-NEWTYPE](https://rust-lang.github.io/api-guidelines/type-safety.html) (Summary) is guidance. Primitive obsession has no separate measurement in what the earlier reports read. **Own.**

### S3. Correlated `Option` fields

- **Wants:** invalid states cannot be represented.
- **Compute:**
  1. For each struct with at least 2 `Option` fields, find every struct literal (Index).
  2. Record each `Option` field as `None`, `Some`, or unknown.
  3. For each pair across literals where both are known, flag it if they are always equal (candidate nested struct) or never both `Some` (candidate enum).
  4. Require at least k literals.
- **Gap:** `..Default::default()`, builders and later assignment show as unknown. Few literals gives false patterns.
- **Evidence:** [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) argues the goal (Earlier report for this point). **Own.** Untested.

### S4. Public fields with a visible invariant

- **Wants:** private fields where an invariant exists. `good-bad-2.md` says whether a field has an invariant does not look computable. This is a partial proxy.
- **Compute:** flag a `pub` or `pub(crate)` field if any holds:
  1. It appears in a guard (`if` returning `Err` or `None`, `assert!`, `ensure!`) in an associated function returning `Self`, `Result<Self, _>` or `Option<Self>`.
  2. It appears in an `assert!` or `debug_assert!` anywhere in the type's `impl` blocks.
  3. Its doc comment matches `must|always|never|invariant|at least|at most`.
- **Gap:** this misses invariants nobody wrote down, and agents can drop the guard.
- **Evidence:** rust-analyzer: ["if there is an invariant, ... make the field private"](https://rust-analyzer.github.io/book/contributing/style.html) (Summary). [C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/future-proofing.html) agrees for non-passive types (Summary). **Own.**

### S5. Empty encapsulation

- **Wants:** privacy that protects something.
- **Compute:** for each private field, find a getter (body is `self.f`, `&self.f` or `self.f.clone()`) and a setter (body is only `self.f = v`). Count fields with both.
- **Gap:** sources differ. rust-analyzer says ["Never provide setters."](https://rust-analyzer.github.io/book/contributing/style.html) C-STRUCT-PRIVATE accepts getters and setters (both Summary). Choose a side or report only. **Own.**

### S6. Data clumps

- **Wants:** values that travel together become a type.
- **Compute:** represent each struct and each function signature as a set of (name, type) pairs. Intersect all pairs of sets, using an inverted index to skip disjoint ones. Report each intersection of size at least 3 that occurs in at least 2 declarations.
- **Gap:** renamed fields escape. The size of 3 is my choice.
- **Evidence:** Data Clumps affected editing effort in a study of 6 developers on Java ([Soh et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf), Read, first page).

### S7. Feature envy (foreign access share)

- **Wants:** a method tied to another type, which `good-bad-1.md` lists with an eightfold rise in fault-proneness (Palomba et al., Earlier report).
- **Compute:** for each method of type T, count own = accesses to `self.f`, and foreign = field accesses and getter-shaped calls on values of other workspace types (Index). Report `foreign / (own + foreign)`. Flag if foreign exceeds own and comes from one or two types.
- **Gap:** getter-shaped is a guess, and coordinating methods look envious. Free functions have no owner, so they are skipped.
- **Evidence:** [PMD's God Class rule](https://pmd.github.io/pmd/pmd_rules_java_design.html) uses foreign data access (ATFD), citing Lanza and Marinescu (Summary). It gives no formula, and its metric page returned 404. The ratio is my definition. **Own.**

### S8. Type complexity (WMC)

- **Wants:** a type doing too much. The model counts methods, but not their complexity.
- **Compute:** sum the cyclomatic complexity of all methods in all `impl` blocks of the type. [rust-code-analysis lists WMC](https://mozilla.github.io/rust-code-analysis/metrics.html) (Summary), but I did not check that it merges separate `impl` blocks; summing the model's function lens does.
- **Gap:** mostly size. A wrapper with many small methods also scores high.
- **Evidence:** WMC is one of PMD's three God Class inputs (Summary, no thresholds on that page).

### S9. Memory layout size

- **Wants:** "very large" in the literal sense.
- **Compute:** build with [`-Z print-type-sizes`](https://doc.rust-lang.org/beta/unstable-book/compiler-flags/print-type-sizes.html) on nightly. Parse each type's size in bytes. Clippy defaults for reference: [enum variant 200, pass by value 256](https://doc.rust-lang.org/clippy/lint_configuration.html) (both Summary).
- **Gap:** the flag is unstable and internal. Bytes measure memory, not understanding. Low priority.

## Function

### F1. Data-flow edges (DepDegree)

- **Wants:** how much a reader must track. Length and branches do not capture this.
- **Compute**, from [Beyer and Fararooy](https://www.sosy-lab.org/research/pub/2010-ICPC.A_Simple_and_Effective_Measure_for_Complex_Low-Level_Dependencies.pdf) (Read):
  1. Build a control-flow graph of operations from the AST: `let`, assignment, condition, call, return, `?`, loop back edges.
  2. Treat each parameter as a definition. Treat a call taking `&mut x` as a definition of `x` (my choice for Rust). Treat `x.f` as `x`.
  3. Run reaching definitions to a fixed point.
  4. Add an edge from each operation to every definition reaching a variable it uses.
  5. The value is the number of edges.
  
  Test case derived from the paper's Figure 1: `a += b; b = a - b; a -= b` gives 6. `temp = a; a = b; b = temp` gives 3.
- **Gap:** closures and opaque macros lose edges. rustc MIR would be more exact, but ties the tool to compiler internals and adds temporaries.
- **Evidence:** [Peitek et al.](https://www.se.cs.uni-saarland.de/publications/docs/PAP+21.pdf) (Read), Java snippets of at most 30 lines, 19 student participants. Correlation with correct answers: LOC -.46, Halstead -.45, DepDegree -.41, McCabe -.09. DepDegree also correlates .59 with LOC, so part of this is size.

### F2. Vocabulary

- **Wants:** working-memory load. Peitek et al.: "vocabulary size burdens programmers' working memory" (Read).
- **Compute:** tokenize the function body. Operands are identifiers and literals. Operators are keywords and punctuation. The value is distinct operators plus distinct operands. [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) has a HALSTEAD suite (Summary); I did not check its token rules.
- **Gap:** correlates .32 with LOC in that study. Maintainability Index was rejected for its constants, but this is one plain count.

### F3. Branch count and loop depth

- **Wants:** simple control-flow load.
- **Compute:** branches = `if`, `else if`, `match` arms, `while`, `for`, `loop`, `?`. Loop depth = maximum nesting of `for`, `while` and `loop` only.
- **Gap:** tracks length. Small study.
- **Evidence:** Peitek et al. report that number of branching statements and maximum loop depth correlate more strongly with brain activation than McCabe (Read, Discussion). They suggest maximum loop depth as a CI check. The same passage supports the model's Parameters lens.

### F4. Flag parameters

- **Wants:** no flag argument that switches behavior. The model counts parameters, not this.
- **Compute:** for each parameter typed `bool` or `Option<_>`, flag it if its name appears in an `if` condition, `if let` scrutinee or `match` scrutinee in the body. Report the count per function.
- **Gap:** an `Option` defaulted with `unwrap_or` is not caught, and that is often fine.
- **Evidence:** rust-analyzer: ["split the function in two"](https://rust-analyzer.github.io/book/contributing/style.html) (Summary). [C-CUSTOM-TYPE](https://rust-lang.github.io/api-guidelines/type-safety.html) (Summary). Clippy's [`max-fn-params-bools` is 3](https://doc.rust-lang.org/clippy/lint_configuration.html) and counts `bool` type only (Summary). **Own** as a use-based rule.

### F5. Adjacent same-typed parameters

- **Wants:** arguments that cannot be swapped silently.
- **Compute:** for each signature, excluding `self`, find the longest run of neighboring parameters with identical type text. Report that length if it is at least 2.
- **Gap:** `fn min(a: u32, b: u32)` is fine. Exempt commutative functions by a list.
- **Evidence:** [C-NEWTYPE](https://rust-lang.github.io/api-guidelines/type-safety.html) warns against mixing up meanings (Summary). **Own.**

### F6. Local bindings

- **Wants:** few things to hold in mind.
- **Compute:** count distinct names bound by `let`, `if let`, `while let`, `for` and `match` patterns, excluding `_` and nested `fn` items.
- **Gap:** correlates with length. Long, simple functions may have many.
- **Evidence:** [Linux kernel](https://docs.kernel.org/process/coding-style.html): "They shouldn't exceed 5-10" (Summary). This is a policy. Peitek et al. also recommend minimizing variables (Read).

### F7. Pass-through functions

- **Wants:** no shallow functions.
- **Compute:** flag a function whose body is one call or method call, where the arguments are the function's parameters in any order, unchanged except for `&`, `.into()` or `?`. Exempt trait impls, which must exist.
- **Gap:** a named alias can be deliberate. A public wrapper can be the module's boundary.
- **Evidence:** [Ousterhout's notes](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) list "one method simply calls another with essentially the same arguments" as a red flag (Summary). **Own.**

### F8. One-caller helpers

- **Wants:** no entangled fragments. Section 3.10 names "functions with one caller" as a guard but defines no lens.
- **Compute:** for each private function, count call sites in the Index, excluding test code. Flag exactly one. Report the flagged count per file, and the longest chain of such functions.
- **Gap:** extracting a well-named step is often right, and [Martin and Ousterhout disagree](https://github.com/johnousterhout/aposd-vs-clean-code) on how far to go (Summary). Use this only as a guard against splitting, not as a target.

### F9. Panic points

- **Wants:** preconditions in types rather than hidden in the body.
- **Compute:** count `.unwrap()`, `.expect(..)`, `panic!`, `unreachable!`, `todo!`, `unimplemented!`, and `[..]` indexing in production code, per function and per 1,000 lines.
- **Gap:** a panic on a proven invariant is correct, and this conflicts with F11's assertions. Clippy has matching lints; I could not read them because its [lint page](https://clippy.rust-lang.org/master/index.html) was too long for the tool, so lint names are from memory.
- **Evidence:** [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) on preconditions in types (Summary). **Own.** No defect evidence opened.

### F10. Repeated guards

- **Wants:** no "shotgun parsing", which [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) describes as checks "spread across processing code" (Summary).
- **Compute:**
  1. In each production function, collect conditions from leading guard statements (`if` returning or panicking, `assert!`, `ensure!`).
  2. Normalize each condition by replacing parameter names with their type, for example `<str>.is_empty()`.
  3. Group identical conditions across functions.
  4. For each group in at least 2 functions, add size minus 1 to the type's count.
- **Gap:** different layers may check for good reason. Syntactically different checks do not match. **Own.** Untested. A high count suggests a newtype.

### F11. Assertion density

- **Wants:** invariants stated in code. This is production code; the model's assertion lens is for tests.
- **Compute:** count `assert*!` and `debug_assert*!` in production functions. Report the mean per function, and the share with at least one.
- **Gap:** evidence is thin, and counts grow with method size.
- **Evidence:** methods with asserts had significantly fewer defects, a small effect, in 100 C and C++ projects ([Casalnuovo et al.](https://www.cs.ucdavis.edu/~filkov/papers/assert-main.pdf), Read, first page). An industrial Java study found [only limited support](https://researchprofiles.herts.ac.uk/en/publications/assert-use-and-defectiveness-in-industrial-code/) (Summary). [TigerBeetle](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md) requires an average of two per function (Summary). Report only.

### F12. Name and behavior mismatch

- **Wants:** a function that can be used without reading the body.
- **Compute:** from the signature, following [the rules in IDEAL](https://ar5iv.labs.arxiv.org/html/2107.08344) (Summary):
  - A name starting `get` that returns `()`.
  - A name starting `is`, `has`, `can` or `should` whose return type is not `bool`.
  - A name starting `set` that returns a type other than `()`, `Self`, `&mut Self` or `Result`.
  - A name starting `get` with a plural last word whose return type is not a collection or iterator.
- **Gap:** this checks words against types, not meaning. The Rust exemptions in the `set` rule are mine.
- **Evidence:** over 80% of external developers rated the clearest of these poor or very poor ([Arnaoudova et al.](https://publications.polymtl.ca/34761/), Snippet; the page I opened holds only metadata). Java.

### F13. Identifier words

- **Wants:** a name that says what the item is.
- **Compute:** split names on `_` and case changes. Check each part against an English wordlist plus a project allowlist. Report the share of parameters and locals that are single letters or have no dictionary part. Exempt names in short closures.
- **Gap:** evidence conflicts, and domain terms need the allowlist.
- **Evidence:** full words gave about 19% faster comprehension in Hofmeister et al.; Scanniello et al. found no difference ([review](https://neverworkintheory.org/2021/08/09/abbreviated-vs-full-names.html), Summary).

### F14. Public documentation coverage

- **Wants:** interfaces documented. The model's comment lenses charge for comments but never credit this, a tension noted in `good-bad-2.md`.
- **Compute:** run [`rustdoc -Z unstable-options --show-coverage --output-format json`](https://doc.rust-lang.org/rustdoc/unstable-features.html) per crate, and read `with_docs / total` (Summary). Add `--document-private-items` to include private items.
- **Gap:** presence, not value. Agents will generate restating docs, so pair it with the "comments that restate the code" lens. The flag needs nightly.

### F15. Stale documentation

- **Wants:** comments that stay true.
- **Compute:** two signals:
  1. **Dead references:** in each `///` comment, extract backticked identifiers and intra-doc links, and resolve them in the Index. Count those that fail.
  2. **Unchanged docs:** in a PR, count documented functions whose signature changed while the doc comment did not.
- **Gap:** an internal change can leave a doc correct, so signal 2 uses signatures only. Neither finds a false statement that still resolves.
- **Evidence:** [Wen et al.](https://www.inf.usi.ch/faculty/lanza/PUBS/P/Wen2019a.pdf) studied this inconsistency on 1,500 Java projects (Read, first page; no rate taken). **Own** as a computation.

## Module

### M1. Interface depth

- **Wants:** much functionality behind a simple interface. The model counts public items only.
- **Compute:** implementation = logical lines in the module. Interface = tokens in the signatures of its public items from the API, including public fields and variants. Report implementation divided by interface.
- **Gap:** size is a poor stand-in for functionality. Dividing by size may not remove its influence (Chowdhury et al., Earlier report). Lines reward bloat, so never use this as a target alone.
- **Evidence:** Ousterhout: ["maximize functionality/(interface complexity)"](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) (Summary). That is opinion, and the formula is not meant as a literal computation. **Own.**

### M2. Unstable interface

- **Wants:** a widely used interface that keeps changing. Mo et al. rank this among the two largest contributors (Wilson's [summary](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html), Summary).
- **Compute**, using the rule in a [longitudinal case study](https://arxiv.org/pdf/1811.12904) (Read):
  1. Build the file dependency graph with the Index.
  2. For file f, find all files that depend on f, directly or indirectly.
  3. Count how many of those changed in the same PR as f at least 2 times in the Window.
  4. Flag f if the count is at least 5.
  
  A Rust refinement of mine: count only PRs where `cargo public-api diff` for f's module is non-empty.
- **Gap:** the thresholds were set for that project's short history. Mo et al.'s own thresholds are unverified. A squash-merged tangled PR adds false links.

### M3. Crossing

- **Wants:** a file that many depend on and that depends on many.
- **Compute**, from the [same study](https://arxiv.org/pdf/1811.12904) (Read):
  1. Compute fan-in and fan-out per file.
  2. Keep files where both are at or above the 90th percentile. That cutoff is my choice; the source says "many".
  3. Flag those that also change with their dependents and dependencies, using the co-change rule in M2.
- **Gap:** foundation files may be legitimately central.
- **Evidence:** the same Wilson summary ranks this with unstable interfaces. It is an association over 19 projects.

### M4. Modularity violation

- **Wants:** parts that can change independently. The model lists "files changed together" but does not compare it with the graph.
- **Compute**, from the [same study](https://arxiv.org/pdf/1811.12904) (Read): count file pairs that changed in the same PR at least 2 times in the Window and have no dependency in either direction. Exclude test files and PRs over the size limit.
- **Gap:** tangled PRs make false pairs, so filtering by [P1](#p1-disconnected-change-groups) helps. Shared-format changes are real links that no code edge shows, which is the point.
- **Evidence:** [Clio](https://2011.icse-conferences.org/content/detecting-software-modularity-violations.html) uses this idea; hundreds of its findings were recognized as design problems or later refactored (Summary).

### M5. Largest cyclic group

- **Wants:** how much code is tangled. Section 3.1 passes or fails on cycles, and this gives a number when a repository cannot pass yet.
- **Compute:** run Tarjan's strongly connected components on the file graph. Report the size of each component larger than 1, and the largest one's share of files. To keep measuring once modules are acyclic, run it on the type graph too.
- **Gap:** small cycles between closely related types are harmless.
- **Evidence:** the case study above defines a clique as a strongly connected component (Read). [Baldwin et al.](https://ideas.repec.org/a/eee/respol/v43y2014i8p1381-1397.html) call a large dominant cyclic group the Core and found it in 70% to 80% of releases (Snippet; full text returned HTTP 403 and 405).

### M6. Flaw counts beside averages

- **Wants:** a signal that moves when architecture changes.
- **Compute:** report the number of files in M2, M3, M4 and M5 per file and in total, alongside propagation cost.
- **Evidence:** in one company's refactoring, decoupling level went from 86% to 83% and propagation cost stayed at 6%. Over the same period cliques went from 17 to 10, and crossings from 29 to 6 ([case study](https://arxiv.org/pdf/1811.12904), Read). The authors say system-wide measures "do not reflect the changes in architecture directly". File count also fell from 1,713 to 711. This is one case. Files in more anti-patterns had more bugs and changes (Wilson's summary).

### M7. Central position

- **Wants:** which pieces need the most care.
- **Compute:** build the file graph. Compute betweenness with Brandes' algorithm, and PageRank. Report the top files and each file's rank.
- **Gap:** central files can be good foundations, so report only. The choice of betweenness and PageRank is mine; the abstract does not name its measures.
- **Evidence:** on Windows Server 2003, network measures had recall 10 percentage points above complexity metrics, and found 60% of critical binaries, twice as many ([Zimmermann and Nagappan](https://www.microsoft.com/en-us/research/publication/predicting-defects-using-network-analysis-on-dependency-graphs/), Summary).

### M8. Cross-module edge share

- **Wants:** related code grouped together.
- **Compute:** build the item dependency graph with the Index. Report the share of edges whose ends are in different modules. Alternatively compute [`Q = Σ(e_ii - a_i²)`](https://en.wikipedia.org/wiki/Modularity_(networks)) with modules as communities (Summary).
- **Gap:** one giant module scores perfectly, so pair it with module size. No study I opened links it to defects. `good-bad-1.md` reports MacCormack et al. saying modularity is hard to measure repeatably.

### M9. Over-wide visibility

- **Wants:** minimal visibility.
- **Compute:** two signals:
  1. Warnings from rustc's [`unreachable_pub`](https://doc.rust-lang.org/rustc/lints/listing/allowed-by-default.html) lint, for `pub` items other crates cannot reach (Summary).
  2. From the Index, `pub` and `pub(crate)` items used only in their defining module, or only in test code.
- **Gap:** a library's external users do not appear in the Index, so signal 2 needs an exemption for its public API.
- **Evidence:** [Effective Rust](https://effective-rust.com/visibility.html) says to expose "as little as possible" (Summary).

### M10. Foreign and duplicate API paths

- **Wants:** an interface that does not leak dependencies.
- **Compute:** from rustdoc JSON, three counts per crate:
  1. **Leaked types:** public signatures naming a type from an external crate other than `std`, `core` and `alloc`.
  2. **Foreign re-exports:** public `use` items whose target is external.
  3. **Multiple paths:** items reachable by more than one public path.
- **Gap:** Microsoft lists exceptions, and leaking a widely shared type can be right. Internal-only crates may not care.
- **Evidence:** [M-DONT-LEAK-TYPES, M-FOREIGN-REEXPORTS, M-SINGLE-ITEM-PATH](https://microsoft.github.io/rust-guidelines/agents/all.txt) (Summary). Guidance only.

### M11. Catch-all names

- **Wants:** no module that exists only because nothing else fit.
- **Compute:** match module, file and folder names against `util(s)`, `helper(s)`, `common`, `misc`, `shared`, `stuff`. Also report items per match. Suitable as a project-convention check.
- **Gap:** easy to dodge with another name. The list is mine.
- **Evidence:** [matklad](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) names a "catch-all utils folder" as a bad outcome (Summary). Opinion, about crate folders.

## Tests

These extend model section 3.5. T1 to T6 target pinned tests before they accumulate churn.

### T1. Message-wording probe

- **Wants:** tests that pin wording no spec requires. Section 3.8 says a test killing such a mutant "is a pinned test", but no lens computes it. The [cargo-mutants page](https://mutants.rs/mutants.html) lists no string-literal mutation (Summary).
- **Compute:**
  1. Find message strings in production code: first string in `format!`, `write!`, `panic!`, `anyhow!`, `bail!`, and `#[error("...")]`.
  2. Rewrite each one, keeping its placeholders: `"bad {x} at {y}"` becomes `"probe {x} probe {y}"`.
  3. Apply all rewrites at once in one build, and run the tests.
  4. Each test that newly fails is a candidate. Allowlist files whose output is a declared contract, such as CLI text.
  5. Optionally limit to messages in the diff, plus tests the PR adds.
- **Gap:** some wording is spec. Strings used as data would need excluding, and any comparison in production code against a rewritten string breaks. That breakage is a false positive. One build and one test run, so cheap. **Own.** Untested.

### T2. Behavior-preserving probe

- **Wants:** the same thing as T1, for structure: a [brittle test](https://abseil.io/resources/swe-book/html/ch12.html) "fails in the face of an unrelated change to production code that does not introduce any real bugs" (Summary).
- **Compute:** apply edits that should not change behavior. Run tests after each kind, and record compile failures and test failures separately:
  1. Rename a private function or private field.
  2. Reorder fields of structs with no derived or manual `Ord`, `PartialOrd`, `Hash` or serialization.
  3. Vary `HashMap` iteration order between runs, where the test relies on the default hasher.
- **Gap:** I found no study of this, after one search. Proving an edit preserves behavior is hard, and field reorder changes `Debug` output, which is intended here. **Own.** Untested and the most speculative item in this file.

### T3. Pseudo-tested functions

- **Wants:** tests that run a function but do not depend on it.
- **Compute:** for each production function covered by a test (cargo-llvm-cov), take its [function-body replacement mutants](https://mutants.rs/mutants.html) (FnValue). If there is at least one viable mutant and all were missed, it is pseudo-tested.
- **Gap:** overlaps surviving mutants, but isolates the worst case. Trivial functions and logging will appear.
- **Evidence:** [Niedermayr et al.](https://ar5iv.labs.arxiv.org/html/1611.07163): mean 11.41% of methods under unit tests, 35.48% under system tests, Java (Summary). [Vera-Pérez et al.](https://arxiv.org/abs/1807.05030) replicated this on over 28,000 methods, but found developers would often not pay to fix them (Summary). So do not target zero.

### T4. References to non-API items

- **Wants:** tests that use the system as its users do. Rust's in-file `mod tests` makes private access easy.
- **Compute:** for each test, list items and fields it references directly (Index). Classify each as public API or not, by the API or by module boundary. Report non-API references per test, and the share of tests with any.
- **Gap:** testing a private algorithm directly can be right, and I recall the Rust Book allowing it (not reopened). This is a signal for a target range, not a limit. Crate-internal `pub` items need a chosen boundary. An untested hypothesis for pinning; history can test it (compare with test churn, section 3.8).
- **Evidence:** ["it's more brittle to test a private method than to test a public method"](https://abseil.io/resources/swe-book/html/ch12.html) (Summary). Guidance. **Own.**

### T5. Interaction assertions

- **Wants:** tests of results, not of how the code got there.
- **Compute:** count calls to `.expect_*()`, `.times(..)`, `.with(..)` and `.withf(..)` on [mockall](https://docs.rs/mockall/latest/mockall/) mocks (Summary), and report tests with any, and the count per test. Other mock libraries and hand-written call recorders need their own patterns.
- **Gap:** a mock at a real external boundary can be correct. Hand-written fakes that assert call order are not detected.
- **Evidence:** ["Interaction testing should be avoided when possible"](https://abseil.io/resources/swe-book/html/ch13.html) (Summary). Google reports mocks that "required constant effort to maintain while rarely finding bugs". Guidance. **Own** as a computation.

### T6. Exact-output assertions

- **Wants:** tests that pin formatting. This is the [Sensitive Equality](https://testsmells.org/pages/testsmells.html) smell (Summary).
- **Compute:** count assertions where the compared expression is any of:
  - `.to_string()`, `format!(..)` or `format!("{:?}", ..)`, compared with a string literal.
  - `.contains("..")` or `.starts_with("..")` on an error's text.
  - `insta::assert_*_snapshot!` or another snapshot macro.
  - `include_str!` as the expected value.
- **Gap:** CLI output and wire formats are often the spec. Allowlist those, as in T1.
- **Evidence:** no study of this smell opened. **Own** in its Rust mapping.

### T7. Test smell rules

- **Wants:** the code-smell equivalent for tests. The model has only "without an assertion" and length.
- **Compute:** one count per test for each rule. Definitions are from [testsmells.org](https://testsmells.org/pages/testsmells.html) (Summary). The Rust mappings are **Own**.

| Smell | Rust rule |
| --- | --- |
| Assertion Roulette | More than one assertion without a message argument. Weaker in Rust, because `assert_eq!` prints both values |
| Conditional Test Logic | `if`, `match`, `for`, `while` or `loop` in the test body |
| Duplicate Assert | The same normalized assertion twice |
| Eager Test | More than k distinct production functions called directly |
| Ignored Test | `#[ignore]` |
| Magic Number | A numeric literal other than 0 and 1 in an assertion |
| Mystery Guest | A path into `std::fs`, `std::net`, `std::env` or `std::process::Command`, or a project-listed client |
| Redundant Print | `println!`, `eprintln!`, `dbg!` |
| Redundant Assertion | `assert!(true)`, or `assert_eq!` with identical arguments |
| Sleepy Test | `thread::sleep`, `tokio::time::sleep` |

- **Gap:** many are style. Eager Test's definition is contested, leading to disagreement between detectors ([search result](https://arxiv.org/pdf/2507.06354), Snippet).
- **Evidence:** in 221 releases of ten systems, smelly tests were more change- and defect-prone, and code they tested was more defect-prone. Indirect Testing, Eager Test and Assertion Roulette were most linked to change-proneness ([Spadini et al.](https://research.tudelft.nl/en/publications/on-the-relation-of-test-smells-to-software-code-quality/), Summary). Java.

### T8. Flake rate

- **Wants:** a gate that fails only for real reasons. Section 5.3 asks for noise measurement but has no lens.
- **Compute:** on an unchanged commit, run the full test suite K times. A test is flaky if it both passes and fails. Report the count and each test's failure share. Run it occasionally, and also retry failures seen in CI to log flakes.
- **Gap:** rare flakes need large K.
- **Evidence:** [Software Engineering at Google](https://abseil.io/resources/swe-book/html/ch12.html) distinguishes flaky from brittle tests (Summary). No measured effect opened here.

## No workable computation found

| Property | Why |
| --- | --- |
| A module hides a design decision (Parnas) | Needs knowledge of which decisions are hard or likely to change. M2 and M4 show effects, not the property |
| A module follows processing steps | Needs a judgment about the design. Names could hint, but I found no method |
| Tests are "correct, sensible, and useful" | Needs a spec. T1 to T6 only detect some wrong shapes |
| One source of truth for each fact | Partly reachable by S6, not in general |
| The PR "improves code health" | The debt rule approximates this by policy |

Considered and dropped:

- **Decoupling Level:** I have its idea from an [abstract page](https://researchwith.stevens.edu/en/publications/decoupling-level-a-new-metric-for-architectural-maintenance-compl/) (Snippet) and the case study, but not the formula. The [paper](https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf) failed on a certificate error, and one site offered its formula only by reference. I cannot say how to compute it. M6's case suggests it may be insensitive.
- **Checked coverage:** the share of executed statements in dynamic slices from assertions ([Schuler and Zeller](https://www.st.cs.uni-saarland.de/publications/details/schuler-icst-2011), Snippet). I found no Rust tool, and dynamic slicing would have to be built.
- **Unsafe count (cargo-geiger):** no claim in either good-and-bad report asks for it.
- **New clones in a PR:** the model already makes duplication report-only.

## Not verified

- **CLI details from memory:** `cargo clippy` flags and message format, `cargo metadata` JSON fields, `cargo mutants` mutant genres in its JSON, rustdoc JSON structure, the output format of `-Z print-type-sizes`. Check before implementing.
- **Tool coverage:** I did not run any tool, so none of the computations has been tried on real code.
- **Clippy lint groups:** the list was too long for the fetch tool at the positions I tried.
- **Earlier report items:** Palomba et al. figures, di Biase et al., McIntosh et al., Chowdhury et al., Scalabrino et al., MacCormack et al., matklad on architecture documents and rust-analyzer on compile times come from `good-bad-1.md` and `good-bad-2.md`.
- **Snippet only:** Potdar and Shihab rates, Arnaoudova perception figure, Baldwin et al. figures, Tian et al., Schuler and Zeller, Eager Test disagreement.
- **Mo et al.:** read through Wilson's summary. The operational thresholds in M2 to M4 come from a different case study, which set them for its own short history. I saw pages 3 to 5 of that study only.
- **Peitek et al.:** I read pages 1 to 3 and 5 to 8. Their results rest on short snippets chosen to vary in complexity, with a small sample.
- **Kamei et al.:** I read only the table of measures, not the per-measure results.
- **Failed to open:** [PMD metrics index](https://pmd.github.io/pmd/pmd_java_metrics_index.html) (404), [Hidden Structure](https://core.ac.uk/download/28943272.pdf) (403), [Spadini PDF](https://pure.tudelft.nl/ws/files/46651094/main.pdf) (timeout; abstract used).
