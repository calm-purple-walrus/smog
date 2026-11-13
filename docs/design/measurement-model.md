# Smog measurement model

> **Status: historical.** This is the design Smog started from. It is not kept in line with the code; the README and `--explain` state what Smog does. Known differences:
>
> - Section 3.9: Smog blames with `git blame --first-parent`, not with `-w -M -C`. An approval given before later commits of the pull request still counts. The marker is a comment at the top of a file and covers that file, not "everything before this commit".
> - Section 3.11: duplication is scored (`file.duplicated_line_share` is in the standard selection), and the Maintainability Index is computed (`function.maintainability_index`).
> - Nine measurements of the list are not built; the README section "Not built" names them.

This document merges Malte's notes with the research in `docs/research/2026-11-08-geiger-research/` and `docs/research/2026-11-08-model-research/`. The second folder has the full computations and sources for layers 2 to 6. Smog was first called Geiger, and the older research documents still use that name.

The model has six layers:

1. What objects are we interested in?
2. What is good and what is bad?
3. What are the metrics that measure these things?
4. What are the methods for aggregating those measurements into scores?
5. What rules do we apply to the scores?
6. How is it implemented and integrated?

Layer 1 is locked. Layers 3 to 5 are lists of options, and each user chooses which to apply.

**Marks used in the tables:**

| Mark | Meaning |
| --- | --- |
| M | Malte's idea |
| C | Claude's idea |
| Untested | No source tests this design. A linked source supports the goal only |

**Limits of the evidence:**

- Nothing in this document has run on real code. All worked numbers are arithmetic on invented inputs, unless a source is named.
- No source tested any metric on Rust code or in a code factory. Most evidence is from Java, C or C++ code written by humans.
- Quotes from web pages came through a tool that summarizes pages. Check the wording before reusing one.
- All thresholds are placeholders until replayed on real history (section 5.8).

## Goal

Smog supports a code factory: agents take tickets, then write, review and merge them without a human. CI blocks a pull request (PR) when:

- it breaks a hard rule;
- it lowers the quality of the codebase too much;
- it lowers the quality of one piece of code too much;
- the PR itself is unacceptable, for example too large.

The main consumer of the results is an AI agent. A human reads the score and the trend.

The end goal is to know how healthy the codebase is, how much agent usage it can take, and how much poisoning it can take right now before that becomes a problem. **Poisoning** means low-quality code entering the codebase. Deliberate attacks are out of scope. Section 4.9 reports these three things as separate outputs, because each answers a different question.

The score is a policy: it states what this codebase charges for. It does not claim to predict defects or cost. The closest counterexample is [Tornhill and Borg](https://arxiv.org/abs/2203.04374), who tie a vendor's composite score to defects and development time in 39 codebases. That result is a correlation, and the authors raise reverse causation themselves.

## 1. Objects

| Object | Examples |
| --- | --- |
| Codebase | The whole repository |
| PR | One change |
| Piece of code | Function, struct or type, file, folder or module, crate |
| History | The sequence of commits on `main`; with squash merges, one commit is one PR |

Test code is a piece of code with its own definition of good, so it gets its own lenses (section 3.8).

The codebase is measured mostly from its pieces. It also has properties no single piece has, such as the dependency graph, security advisories and unreviewed lines.

History differs from the other objects: it can reveal problems a snapshot of the code cannot, but only after they have had time to show.

## 2. What is good and bad

Sources agree on the direction and disagree on the numbers. Three limits apply to this whole section:

- **Most of it is expert opinion.** Studies mostly show associations.
- **No limit is established.** No source shows that a specific limit, such as a maximum number of lines, is correct. Linux, Clippy and TigerBeetle set different limits or none.
- **Nothing was shown to measure understandability.** [Scalabrino et al.](https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf) tested 121 metrics against 444 human evaluations and report that "none of the 121 experimented metrics is able to capture code understandability".

Strength labels: **Study** is a measurement or experiment. **Guidance** is a published standard from an organization or project. **Opinion** is one author's argument.

### 2.1 Codebase

| | Property | Source | Strength |
| --- | --- | --- | --- |
| Good | Health improves over time, and perfection is not the standard | [Google review standard](https://google.github.io/eng-practices/review/reviewer/standard.html) | Guidance |
| Good | No more code than needed: "code itself is a liability" | [Software Engineering at Google, ch. 9](https://abseil.io/resources/swe-book/html/ch09.html) | Guidance |
| Good | Parts can be tested and deployed without coordinating with other parts | [DORA](https://dora.dev/capabilities/loosely-coupled-teams/) | Guidance, no figures on the page |
| Good | Tests detect real faults. Mutant detection correlates with real fault detection, independently of coverage | [Just et al.](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html) | Study, 357 real faults |
| Good | Tests use the system as its users do, and "the ideal test is unchanging" unless requirements change | [Software Engineering at Google, ch. 12](https://abseil.io/resources/swe-book/html/ch12.html) | Guidance |
| Good | Few, stable external dependencies | [DORA](https://dora.dev/capabilities/code-maintainability/), [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) | Guidance |
| Good | A flat crate layout, for 10,000 to 1,000,000 lines | [matklad](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) | Opinion |
| Good | Most code sits well inside the targets. Humans have reviewed a known share of it | Malte | Policy |
| Bad | Low-quality code: 15 times more defects, and issues took 124% longer | [Tornhill and Borg](https://arxiv.org/abs/2203.04374) | Study, 39 codebases, correlation, vendor's metric |
| Bad | Smells that accumulate: median changes rose from 12 with no smells to 54 with three | [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) | Study, 395 releases of 30 projects |
| Bad | Architecture anti-patterns. Files in more of them had more bugs and changes | [Wilson on Mo et al.](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html) | Study, 19 projects, read through a summary |
| Bad | Central position in the dependency graph: recall about 10 points above complexity metrics | [Zimmermann and Nagappan](https://www.microsoft.com/en-us/research/publication/predicting-defects-using-network-analysis-on-dependency-graphs/) | Study, Windows Server 2003 |
| Bad | Tight coupling, which makes components "harder to kill" and "harder to maintain" | [MacCormack et al.](https://swizec.com/pdfs/impact-of-modularity.pdf) | Study, one product |
| Bad | High churn relative to size. Absolute churn did not predict defect density well | [Nagappan and Ball](https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/) | Study, Windows Server 2003 |
| Bad | Brittle tests, which fail on changes that are not bugs | [Software Engineering at Google, ch. 12](https://abseil.io/resources/swe-book/html/ch12.html) | Guidance |
| Bad | Persistent rises in warnings and complexity after adopting an AI tool | [He et al.](https://arxiv.org/abs/2511.04427) | Study, against matched controls |
| Bad | Agent code that does not last: functions and classes removed after a median of 3 days, against 34 for humans | [Pham and Ghaleb](https://arxiv.org/abs/2601.17627) | Study, 33,596 agent PRs |
| Bad | Unreviewed code growing without anyone knowing where it is | Malte. The link between review and defects is mixed: [McIntosh et al.](https://rebels.cs.uwaterloo.ca/confpaper/2014/05/30/the-impact-of-code-review-coverage-and-code-review-participation-on-software-quality.html) found one, [Sony Mobile](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf) did not | Mixed |

**Disputes:**

- **Which metrics matter.** [Radjenović et al.](https://gup.ub.gu.se/file/127150) found that object-oriented and process metrics did better than size and complexity metrics. [El Emam et al.](https://neverworkintheory.org/2011/07/07/the-confounding-effect-of-class-size-on-the-validity-of-object-oriented-metrics.html) found that class size accounted for the significant variation.
- **Duplication.** [DORA](https://dora.dev/capabilities/code-maintainability/) treats it as worth measuring. [Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction) argues that "duplication is far cheaper than the wrong abstraction".
- **Coverage.** It is a [poor predictor of test effectiveness](https://neverworkintheory.org/2021/09/24/coverage-is-not-strongly-correlated-with-test-suite-effectiveness.html) once suite size is controlled.

### 2.2 Pull request

| | Property | Source | Strength |
| --- | --- | --- | --- |
| Good | One self-contained change that addresses one thing | [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Guidance |
| Good | About 100 lines is reasonable and 1,000 is usually too large. Another Google source says about 200 | Same; [Software Engineering at Google, ch. 9](https://abseil.io/resources/swe-book/html/ch09.html) | Guidance |
| Good | Includes related tests, and leaves the gate alone | Same; Malte | Guidance |
| Good | Refactoring is separate from features and fixes, apart from small cleanups | [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Guidance |
| Good | Definitely improves code health, even if imperfect | [Google review standard](https://google.github.io/eng-practices/review/reviewer/standard.html) | Guidance |
| Good | Solves today's problem, not a future one | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Guidance |
| Good | The description says what changed and why | [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) | Guidance |
| Bad | Many added lines. This count alone beat two deep learning models at defect prediction | [Zeng et al.](https://zhangyuqun.github.io/publications/issta2021.pdf) | Study, 310,370 changes |
| Bad | Spread out: 200 lines across 50 files is usually too large | [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Guidance |
| Bad | Tangled purposes. 7% to 20% of bug fixes mix changes | [Herzig et al.](https://www.microsoft.com/en-us/research/publication/the-impact-of-tangled-code-changes-on-defect-prediction-models/) | Study. It shows harm to defect data, not to the code |
| Bad | Overengineering and side effects, the top group of causes of reverted agent code at 22.33% | [Oukay et al.](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/) | Manual analysis of 500 reverting commits |
| Bad | Touching unrelated code, verbose code, and code that ignores standards | [METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/) | 296 agent PRs, 4 maintainers |
| Bad | Duplicates of other work: 23% of the rejected agent PRs sampled | [Ehsani et al.](https://www.alphaxiv.org/abs/2601.15195.md) | Manual labeling |
| Bad | Deleting or editing a failing test instead of fixing the bug | [ImpossibleBench](https://arxiv.org/abs/2510.20270) | Study of test exploitation by agents |
| Bad | Vague description, such as "Fix bug" | [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) | Guidance |

**Passing tests does not make a PR good.** Maintainers would have merged only about half of the agent PRs that [passed the automated grader](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/). [Cynthia et al.](https://arxiv.org/abs/2601.20109) report that "merge success does not reliably reflect post-merge code quality".

**Disputes:**

- **Smaller is not always better.** [Rahman et al.](https://arxiv.org/abs/2609.22610), one preprint with 330,343 PRs, report the lowest risk at about ten files, with elevated rates for very small and very large PRs.
- **The size finding may be partly an artifact.** [Morita et al.](https://posl.ait.kyushu-u.ac.jp/~kamei/publications/Morita_SANER2024.pdf) note that larger changes give later fixes more surface to implicate them.
- **Splitting has a narrower benefit than often claimed.** In [di Biase et al.](https://arxiv.org/abs/1805.10978), with 28 developers, it changed neither understanding nor defects found, and reduced wrongly reported issues.
- **Small does not mean fast.** In [Kudrjavets et al.](https://arxiv.org/pdf/2203.05045), size did not relate to time-to-merge. The case for small PRs therefore rests on risk.

### 2.3 Struct

No source studies Rust structs. Results on Java classes carrying over is an inference, and those about inheritance do not carry over.

| | Property | Source | Strength |
| --- | --- | --- | --- |
| Good | Invalid states cannot be expressed in the type | [Effective Rust, item 1](https://effective-rust.com/use-types.html); [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) | Opinion |
| Good | The result of validation is kept in the type. One source of truth for each fact | [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) | Opinion |
| Good | Enums or custom types instead of `bool` and `Option`; newtypes for different meanings | [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/type-safety.html) | Guidance |
| Good | Private fields where an invariant exists | [C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/future-proofing.html), [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) | Guidance |
| Good | A builder for many optional inputs; no unnecessary bounds on the definition | [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/print.html) | Guidance |
| Bad | God class: median changes 46 with the smell, against 12 without | [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) | Study |
| Bad | God class and data clumps raised effort | [Soh et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf) | Experiment, 6 developers |
| Bad | Feature envy: fault-proneness rose by a factor of 8, with no rise in change-proneness | [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) | Study |
| Bad | Many `bool` fields. Clippy's limit is 3 | [Clippy](https://doc.rust-lang.org/clippy/lint_configuration.html) | Tool default |
| Bad | An exposed detail that later has to change | [Hyrum's Law](https://www.hyrumslaw.com/) | Practitioner observation |
| Bad | Public fields in domain models | Malte | Policy, hard rule (section 3.1) |

**Disputes:**

- **Public fields.** The API Guidelines prefer private fields for public APIs. [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) makes a field public if any value is valid. So the answer depends on whether the type has an invariant and outside users. Malte's rule settles it for domain models.
- **Data-only structs.** [Fowler](https://martinfowler.com/bliki/CodeSmell.html) calls them a smell, as a prompt to look further. Rust sources accept passive data with public fields.
- **Do smells matter beyond size?** [Sjøberg et al., as described by Soh et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf), found no smell remained significant after adjusting for size. Soh et al. reanalyzed the same 6 developers: smells outweighed size for editing and navigating, and size outweighed smells for reading and searching.

### 2.4 Function

| | Property | Source | Strength |
| --- | --- | --- | --- |
| Good | Understood quickly by readers | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Guidance |
| Good | Usable without reading the body | [Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Good | Short and single-purpose. Allowed length falls as complexity and indentation rise | [Linux kernel](https://docs.kernel.org/process/coding-style.html) | Guidance |
| Good | Under 24 lines, in Java | [Chowdhury et al.](https://arxiv.org/abs/2205.01842) | Study, about 785,000 methods |
| Good | Preconditions in types, early returns, control flow visible at the caller | [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html), [TigerBeetle](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md) | One project each |
| Good | A name long enough to say what it does | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Guidance |
| Bad | Long method | [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) | Study. A long, simple function can be fine, as [Fowler](https://martinfowler.com/bliki/CodeSmell.html) and the kernel guide say |
| Bad | Deep nesting, or more than 5 to 10 local variables | [Linux kernel](https://docs.kernel.org/process/coding-style.html) | Guidance |
| Bad | Flag arguments that switch between two behaviors | [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html) | One project |
| Bad | Fragments that must be read together | [Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Bad | Input checks scattered through processing ("shotgun parsing") | [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) | Opinion |
| Bad | Comments that narrate what the code is doing | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Guidance |

| Published limit | Source |
| --- | --- |
| 70 lines, and two assertions per function on average | [TigerBeetle](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md) |
| 100 lines, 7 arguments, 3 `bool` parameters, cognitive complexity 25 | [Clippy defaults](https://doc.rust-lang.org/clippy/lint_configuration.html) |
| No line limit, 5 to 10 local variables | [Linux kernel](https://docs.kernel.org/process/coding-style.html) |

**Disputes:**

- **How far to split.** Martin would rather err toward decomposition. Ousterhout says extra methods spread out what you must know ([their discussion](https://github.com/johnousterhout/aposd-vs-clean-code)). [Chowdhury et al.](https://arxiv.org/abs/2205.01842) report that decomposition lowers maintenance effort, in one Java study.
- **Complexity against size.** [Landman et al.](https://ir.cwi.nl/pub/23938/), on 17.6 million Java methods and 6.3 million C functions, found only a moderate correlation for single functions. Aggregation raises it, which explains earlier reports of a strong link.
- **Cognitive complexity.** Clippy keeps its lint in `restriction`: ["We used to think it measured how hard a method is to understand."](https://clippy.rust-lang.org/master/index.html)
- **Comments.** Ousterhout, the kernel guide and [Microsoft](https://microsoft.github.io/rust-guidelines/guidelines/ai/) support documenting what an interface does. Google, the kernel guide and Martin oppose comments that narrate or add nothing. So narration is bad, and interface documentation is good even when the code could show the same fact.

### 2.5 Module

| | Property | Source | Strength |
| --- | --- | --- | --- |
| Good | Hides a difficult or likely-to-change design decision | [Parnas](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html) | Design argument |
| Good | Much functionality behind a simple interface | [Ousterhout](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) | Opinion |
| Good | The implementation can change without affecting other modules | Same; Parnas | Opinion |
| Good | Groups related functionality and keeps details private | [Rust Book, ch. 7](https://doc.rust-lang.org/book/ch07-00-managing-growing-projects-with-packages-crates-and-modules.html) | Guidance |
| Good | Minimal visibility; one public path per item | [Effective Rust, item 22](https://effective-rust.com/visibility.html), [Microsoft](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Opinion |
| Good | Dependencies form a hierarchy; no layer violations; correct folder structure | Parnas; Malte | Argument, policy |
| Bad | Modules that follow processing steps | [Parnas](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html) | Design argument |
| Bad | Thin modules that hide little | [Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Bad | Unstable interfaces and crossings, which "contribute the most by far"; cliques and package cycles | [Wilson on Mo et al.](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html) | Study, read through a summary |
| Bad | A casual `pub use`; re-exports of other crates' items | [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html), [Microsoft](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Guidance |
| Bad | Catch-all folders such as `utils` | [matklad](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) | Opinion |
| Bad | A change in one place forcing many changes elsewhere | [Refactoring Guru](https://refactoring.guru/refactoring/smells) | Catalog |

The strongest module sources are design arguments. [MacCormack et al.](https://swizec.com/pdfs/impact-of-modularity.pdf) say empirical work linking modularity and evolution "has had limited success". No study shows a best module or interface size.

### 2.6 Tests and history

| Object | Good | Bad |
| --- | --- | --- |
| Tests | They catch injected bugs, use public behavior, and change when requirements change | They assert nothing, pin output the spec does not require, or break whenever the code around them changes |
| History | Code stays once merged. Change flows from interfaces to their dependents | Code is rewritten or reverted soon after merging. Files keep changing together with no structural link |

### 2.7 What sources agree on

1. Bad traits come in groups, and a piece with several is much worse than a piece with one.
2. Size is the most consistent warning sign, and it does not explain everything.
3. Limits are policy.
4. Coupling and hidden design decisions are widely valued, and harder to measure than size.
5. Passing CI or being merged does not show quality.

## 3. Metrics

### 3.0 What we want to know and what we measure

These are usually different things. The thing we want to know often cannot be computed, so we measure something else and accept the gap. Each metric should state both, so that nobody treats the number as the property itself.

| What we want to know | What we measure | The gap |
| --- | --- | --- |
| Do tests pin behavior the spec does not require? | Test churn | Churn also comes from real requirement changes. A pinned test around stable code never churns |
| Would tests notice a real bug? | Surviving mutants | Injected changes are not real bugs, and pinned tests catch them too |
| Is this function hard to understand and change? | Length, complexity, nesting, data flow | No metric was shown to capture understandability. These correlate with size, moderately for single functions and strongly once aggregated |
| Are tests piling up without adding anything? | Tests per 100 lines | A high count can be legitimate; a low count can still be pinned tests |
| Has a human actually examined this code? | Lines without human approval | An approval shows a click, not reading |
| Is this comment noise? | Phrase and overlap matches | Heuristic; can be reworded around |
| Does this field carry an invariant? | Guards on the field in constructors, and doc comment wording | Misses invariants nobody wrote down |

**Kinds of metric:**

- **Check:** pass or fail. Never part of the score.
- **Lens:** a number on a scale. It feeds aggregation (section 4).
- **Report:** shown beside the score and not charged. Weak or unclear evidence puts a metric here.

**Shared inputs for the computations below:**

| Input | Meaning |
| --- | --- |
| Syntax | `syn` parse. Macros are not expanded, so code inside macro calls is not seen |
| Index | The rust-analyzer index, mapping each name use to its definition (section 6.6) |
| API | Public items from `cargo public-api` or rustdoc JSON. Both need nightly |
| Item identity | Full path. If a path disappears and the same syntax-tree hash appears elsewhere in that commit, it is one item that moved |
| Window | The last N squash-merged PRs |

Most metrics marked C below are untested designs. Where a study defined the metric, the link says so. Generated files are excluded everywhere.

### 3.1 Pass/fail checks

| Rule | Check | From |
| --- | --- | --- |
| Tests pass | Test runner | M |
| Lints pass | Clippy with `deny` | M |
| No security advisories added | cargo-deny on the PR's lockfile. A new advisory on an unchanged lockfile opens a ticket, because the PR cannot clear it (section 6.9) | M |
| No layer violations | Allowed-edge list on the crate and module graphs. Check resolved definitions, because a re-export through a permitted module dodges a check on `use` paths. Every crate and module must have a layer, or the check fails. Moving code to a low "common" crate needs a human | M |
| Correct use of attribute structs | Not built into Smog; written in the product's policy. Project-specific rule: the struct is used only in certain contexts and has certain methods. The check takes both lists from project configuration: use sites of the struct must fall in an allowed context, and its `impl` blocks may define only the allowed methods. Use sites come from the Index, because a type alias, wrapper or macro dodges a name match. Where possible, encode it as a type error with a private constructor | M |
| No public fields in domain models | Not built into Smog; written in the product's policy. Flag `pub`, `pub(crate)`, `pub(super)` and `pub` tuple fields on types in the domain layer. Also ban `Deref` to an inner struct with public fields, `fn x_mut(&mut self) -> &mut T`, and getter-plus-setter pairs. Scope by the layer map, because moving a type out of the domain folder dodges a path check. A compiler-backed lint sees macro-generated fields, and `syn` does not | M |
| Correct folder structure | Not built into Smog; written in the product's policy. Allowlist of paths and name patterns; anything unlisted fails. Ban `#[path]` and `include!`. Only humans change the list | M |
| No dependency cycles | Cargo for crates, `cargo-modules --acyclic` for modules | C |
| Project conventions | Syntax rules, file-layout checks | C |
| No high-precision slop comments | Own comment checker: ticket IDs, history narration ("used to", "no longer"), hedging ("should work") | M |
| No new suppressions | New `allow` or `expect` attributes, `#[mutants::skip]`, `#[mutants::exclude_re]`, `ast-grep-ignore` comments, `#[ignore]`, and optionally `#[should_panic]`. Exceptions go in a human-owned list with a reason | C |
| Gate is untouched | The diff changes none of the files in section 6.3 | C |
| Tests are not weakened | The diff deletes no tests and removes no assertions | C |
| Tests stay in the build | Tests found by `syn` match tests in the runner's report, because `#[cfg(any())]` compiles a test out | C |
| Assertions keep their strength | For tests matched by name, the assertion tier does not fall. Tier 3: `assert_eq!`, `assert_ne!` or `matches!` on a value. Tier 2: `assert!` on another condition. Tier 1: `assert!` on `is_ok`, `is_err`, `is_some`, `is_none` or `!is_empty`. This pulls against exact-output assertions in section 3.8 | C |
| PR size limit | Lines changed and files touched per PR | M |
| No bounds on type definitions | `struct` and `enum` generics name no `Clone`, `Copy`, `Debug`, `Default`, `Hash`, `PartialEq`, `Eq`, `PartialOrd` or `Ord` ([C-STRUCT-BOUNDS](https://rust-lang.github.io/api-guidelines/future-proofing.html)) | C |
| Unused dependencies | [cargo-machete](https://github.com/bnjbvr/cargo-machete), with its ignore list for false positives | C |
| Catch-all names | Module, file and folder names do not match `util(s)`, `helper(s)`, `common`, `misc`, `shared`. A rename dodges it | C |

**What makes a rule hard (C).** A rule is hard only if a violation is never acceptable, the check is deterministic with no false positives, and the PR can clear it. Otherwise it belongs on a curve. If a hard rule often needs exceptions, it should move to a curve.

**How strong an encoding is (C), strongest first:** a compile error, then a compiler-backed lint, then a syntax rule. A private field cannot be gamed. A syntax rule can.

### 3.2 Function lenses

| Lens | How to compute | From | Evidence or gap |
| --- | --- | --- | --- |
| Length | Lines without comments and blanks | M | Size is the strongest simple predictor in the research, and the main confound for the other lenses |
| Effective length | `own_length + α × Σ effective_length(c)` over private functions `c` whose only caller is this one | C | Untested. Closes the splitting exploit (section 4.3). α = 1 ignores splitting entirely; α = 0.5 still rewards it |
| Largest paragraph | Lines in a run with no blank line. Merge a paragraph of fewer than 3 statements into the next. A comment is not a separator. Sum the penalty over all paragraphs in the function | M | No study found. A blank line dodges it at no cost, so it is weak alone (section 4.3) |
| Cyclomatic complexity | rust-code-analysis or own `syn` visitor | M | Moderate correlation with length for single functions ([Landman et al.](https://ir.cwi.nl/pub/23938/)) |
| Cognitive complexity | rust-code-analysis | C | Clippy warns against using its version as a measurement |
| Nesting depth | Own `syn` visitor | C | |
| Parameters | `syn` | C | |
| Return points | rust-code-analysis (`NEXITS`) | C | |
| Outgoing dependencies | Distinct items used, from the Index; report items across modules separately | C | Coupling has the best evidence among design metrics |
| Incoming dependencies | Distinct use sites, same Index | C | High values can be legitimate for foundation items, so this may be report-only |
| Generic parameters | `syn` | C | |
| Data-flow edges (DepDegree) | Build a control-flow graph, run reaching definitions, and add an edge from each operation to every definition reaching a variable it uses. Treat `&mut x` in a call as a definition of `x` | C | [Beyer and Fararooy](https://www.sosy-lab.org/research/pub/2010-ICPC.A_Simple_and_Effective_Measure_for_Complex_Low-Level_Dependencies.pdf). [Peitek et al.](https://www.se.cs.uni-saarland.de/publications/docs/PAP+21.pdf): correlation with correct answers LOC -.46, DepDegree -.41, McCabe -.09, with 19 students on short Java snippets. Closures and opaque macros lose edges |
| Vocabulary | Distinct operators plus distinct operands in the body | C | Peitek et al.: "vocabulary size burdens programmers' working memory" |
| Branch count, loop depth | Count `if`, `else if`, match arms, `while`, `for`, `loop`, `?`. Maximum nesting of loops only | C | Peitek et al. link these to brain activation more strongly than McCabe, and suggest loop depth as a CI check |
| Local bindings | Distinct names bound by `let`, `if let`, `while let`, `for`, `match`; excluding `_` | C | Kernel limit of 5 to 10 is policy. Shadowing counts as new |
| Flag parameters | `bool` or `Option` parameters whose name appears in an `if` or `match` condition in the body | C | [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html): "split the function in two". Clippy counts `bool` type only |
| Literal flag calls | For each `bool` position, the share of call sites passing a literal. Flag at 100%, and report the call-site count | C | A function with one caller reaches 100% trivially |
| Adjacent same-typed parameters | Longest run of neighboring parameters with the same type | C | `fn min(a: u32, b: u32)` is fine, so exempt commutative functions by a list |
| Pass-through functions | Body is one call whose arguments are the function's own parameters, unchanged except for `&`, `.into()` or `?`. Exempt trait impls | C | Ousterhout's red flag. A public wrapper can be a module's boundary |
| One-caller helpers and chains | Private, exactly one non-test caller, in the same module. Report the count per module and the longest chain | C | A guard against splitting. Do not use as a target, because Martin and Ousterhout disagree |
| Panic points | `.unwrap()`, `.expect()`, `panic!`, `unreachable!`, `todo!`, `unimplemented!`, `[..]` indexing | C | No defect evidence opened. A panic on a proven invariant is correct |
| Repeated guards | Normalize leading guard conditions by replacing parameter names with their type, then group identical ones across functions | C | A high count suggests a newtype |
| Validation-only functions | Returns `Result<(), _>` or `bool`, takes no `&mut`, and its name starts with `validate`, `check`, `verify`, `ensure` or `is_valid` | C | [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) treats these with suspicion. A rename dodges it |
| Late input checks (report) | `if <parameter> { return Err }` after the first visible effect | C | Heuristic. Measure false positives first |
| Assertion density (report) | `assert*!` and `debug_assert*!` per production function | C | [Casalnuovo et al.](https://www.cs.ucdavis.edu/~filkov/papers/assert-main.pdf): small effect on defects in 100 C and C++ projects. Counts grow with size |
| Name and behavior mismatch | `get*` returning `()`; `is*`, `has*`, `can*` or `should*` not returning `bool`; `set*` returning another type | C | Rules from [IDEAL](https://ar5iv.labs.arxiv.org/html/2107.08344). Checks words against types, not meaning |
| Identifier words, short names | Share of parameters and locals that are one letter or have no dictionary part | C | [Evidence conflicts](https://neverworkintheory.org/2021/08/09/abbreviated-vs-full-names.html). Domain terms need an allowlist |
| Indentation sum | On rustfmt output, leading spaces divided by 4, summed per line. Also works on diff hunks that do not parse | C | [Hindle et al.](https://plg.uwaterloo.ca/~migod/papers/2008/icpc08-abram.pdf) call it a cheap proxy. Rust match arms indent more, so targets need local data |
| Bumpy road | Runs of consecutive top-level statements with control flow nested at least 2 levels. Flag at 2 or more | C | Concept from [CodeScene](https://codescene.io/docs/guides/technical/code-health.html), which gives no algorithm |
| Complex conditional | Most `&&` and `\|\|` nodes in any one condition | C | A helper function hides the count |
| Halstead, ABC (report) | rust-code-analysis | C | Expect little new information |

### 3.3 Struct and type lenses

| Lens | How to compute | From | Evidence or gap |
| --- | --- | --- | --- |
| Fields | `syn` | M | |
| Methods | `syn`, all `impl` blocks | M | |
| Enum variants | `syn` | C | |
| Cohesion (LCOM4) | Own `syn` code | C | Weak evidence |
| On/off fields | `bool` fields plus `Option` fields, `n`. Up to `2^n` states | C | Clippy's limit is 3 for `bool`. Config types can be legitimate |
| Primitive share | For structs with at least 3 fields, the share typed as primitive, `String`, `&str`, or a `Vec` or `Option` of those | C | Passive records may be correct. Low-level crates need different targets |
| Correlated `Option` fields | Across struct literals, flag pairs always equal (nested struct) or never both `Some` (enum). Require at least k literals | C | `..Default::default()` and builders show as unknown |
| Public fields with a visible invariant | `pub` or `pub(crate)` field that appears in a guard in a constructor or an `assert!` in the `impl`, or whose doc comment matches `must\|always\|never\|invariant\|only if`. Variant: all public fields on a struct whose constructor contains `if`, `match`, `?` or an assertion | C | Partial proxy. Agents can drop the guard |
| Foreign field access | Field reads and writes outside the struct's own module | C | A public field nobody uses costs little; this shows that. Passive data scores high |
| Plain setters, empty encapsulation | `set_*` whose body is one assignment; private fields with both a trivial getter and setter | C | Sources differ, so report unless a project takes a side |
| Data clumps | Intersect sets of `(name, type)` across structs and signatures; report overlaps of 3 or more in at least 2 places | C | [Soh et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf). Renames escape |
| Feature envy | `ATFD` foreign fields used, `LAA = own / (own + ATFD)`, `FDP` foreign types | C | Rule from [Lanza and Marinescu](https://homepages.dcc.ufmg.br/~figueiredo/disciplinas/lectures/detection-strategy_v01.pdf); "few" has no number. Getters hide access unless counted |
| Type complexity, god type | `WMC` sum of cyclomatic complexity over methods; `TCC` method pairs sharing a field over all pairs; rule `ATFD > few`, `WMC` very high, `TCC < 1/3` | C | Same source. Size is a confound, and one unopened study may contradict the god class finding after controlling for size |
| Missing common traits | `missing_debug_implementations`, `missing_copy_implementations` warnings | C | Library guidance. Not every type should be `Copy` |
| Memory layout size (report) | `-Z print-type-sizes`, nightly | C | Measures memory, not understanding |

### 3.4 File, folder, module and crate lenses

| Lens | Object | How to compute | From | Evidence or gap |
| --- | --- | --- | --- | --- |
| Length | File | Lines | M | |
| Items per file | File | `syn` | C | |
| Files per folder | Folder | Git tree | M | |
| Subfolders per folder | Folder | Git tree | M | |
| Folder depth | Folder | Git tree | C | |
| Modules | Crate, codebase | `syn` | M | |
| Public items | Module, crate | `syn` or API | C | |
| Lines | Crate | Line count | C | |
| Crate dependencies, internal and external | Crate | `Cargo.toml` | C | |
| Instability, distance from the main sequence | Crate | Martin's formulas on the crate graph | C | Empirical support not verified |
| Propagation cost | Codebase | Share of code reachable from an average item | C | Barely moved in the case study under "flaw counts" |
| Interface depth | Module | `implementation_lines / interface_tokens`, counting tokens in public signatures and public fields | C | Ousterhout's formula is not meant literally. Padding raises it, so never a target alone |
| Over-wide visibility | Module, crate | `unreachable_pub` warnings; `pub` items used only in their module or in tests | C | New API not yet used counts as over-visible |
| Leaked external types | Crate | [`cargo check-external-types`](https://lib.rs/crates/cargo-check-external-types), or public signatures naming an external type | C | Library guidance. Internal crates may share a dependency on purpose |
| Re-exports | Crate | `pub use` items, split by foreign and internal | C | A crate root using `pub use` is common |
| Multiple public paths | Crate | Walk rustdoc JSON; items reachable by 2 or more paths | C | The walk is untested |
| Largest cyclic group | Module, codebase | Tarjan's strongly connected components on the file graph, and on the type graph once modules are acyclic | C | Gives a number when a repository cannot pass the cycle check yet |
| Crossing | File | `min(fan_in, fan_out)` over distinct files | C | Mo et al.'s thresholds were not read |
| Central position (report) | File, module | PageRank, or `ego_size`, `effective_size` and eigenvector centrality on a lifted module graph | C | [Zimmermann and Nagappan](https://thomas-zimmermann.com/publications/files/zimmermann-icse-2008.pdf): closeness found 60% of critical binaries, against 30% for complexity metrics. Central files can be good foundations |
| Internal edge share (report) | Module | Item edges inside over inside plus crossing | C | One giant module scores perfectly |
| Rebuild radius | Crate, PR | Workspace members reachable in the reverse dependency graph | C | Declared dependencies, not actual effects |

### 3.5 Codebase lenses

| Lens | How to compute | From | Evidence or gap |
| --- | --- | --- | --- |
| Lenses over target | Per piece, count groups of correlated lenses above target. Report the share of lines in pieces with 3 or more | C | Median changes rose from 12 to 54 with three smells ([Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf)). The worst-lens rule in 4.4 does not see this |
| Lint warning density | `clippy::pedantic` warnings per 1,000 lines | C | [He et al.](https://arxiv.org/abs/2511.04427). Pedantic lints are noisy |
| Flaw counts beside averages | Files in each of crossing, unstable interface, modularity violation and cyclic group | C | [One refactoring](https://arxiv.org/pdf/1811.12904): propagation cost stayed at 6% while cliques went from 17 to 10 and crossings from 29 to 6. File count also fell |
| Dependency weight | Transitive packages per crate, packages each direct dependency brings, packages with several versions | C | A count ignores size and quality |
| Dependency age (report) | Libyear, from the registry index | C | An old, finished crate scores badly, so this can oppose the goal |
| Admitted-debt markers | `TODO`, `FIXME`, `HACK`, `XXX`, `todo!()`, `unimplemented!()` per 1,000 lines | C | A marker is more honest than silence, so blocking may hide debt |
| Build time (report) | Clean build, then rebuild after touching a low-level file | C | Noisy across machines |
| Debt trend (report) | Theil-Sen slope of debt per 1,000 lines; share of PRs that lowered debt | C | Depends on the chosen lenses |
| Finding age (report) | Median age of findings in PRs; findings removed over findings added | C | Palomba et al. cite "almost 80%" of smells never being removed |
| Equilibrium score | Section 4.9 | C | Untested |

### 3.6 Comment lenses

The check in 3.1 catches patterns that are almost always wrong. These lenses score the rest.

| Lens | How to compute | From | Evidence or gap |
| --- | --- | --- | --- |
| Slop findings | Phrase lists on extracted comments | M | |
| Comments that restate the code | Word overlap between a comment and the line below it | C | |
| Section-header and decorative comments | Pattern match | C | |
| Comment density (report) | Comment lines per code line, per file | C | Report only, because a penalty would charge for interface documentation (2.4) |
| Interface documentation | Undocumented public items; public modules with no `//!`; first sentences over 15 words; docs whose words overlap the signature by 0.8 or more | C | Credits what density would charge. Agents can generate text that passes |
| Stale documentation | Backticked identifiers in `///` that do not resolve; documented functions whose signature changed while the doc did not | C | [Wen et al.](https://www.inf.usi.ch/faculty/lanza/PUBS/P/Wen2019a.pdf) studied this on Java. A false statement that still resolves is missed |

All of these are heuristics, so their false-positive rate must be measured before any rule relies on them. `syn` drops ordinary comments, so they need a lexer (section 6.6).

### 3.7 PR lenses

| Lens | How to compute | From | Evidence or gap |
| --- | --- | --- | --- |
| Lines changed, excluding generated files | Diff | M | |
| Added lines | `git diff --numstat`, added and deleted kept apart. A wholly deleted file counts as one line | C | [Zeng et al.](https://zhangyuqun.github.io/publications/issta2021.pdf); deletion rule from Google |
| Files touched | Diff | M | |
| Crates and layers touched | Diff and the layer map | C | |
| Entropy of the change over files | Diff | C | Insignificant in [Shimagaki et al.](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf) |
| Debt added to code the PR did not touch | Compare lenses before and after | C | |
| Disconnected change groups | Link hunks in one function, a definition and its use, or uses of one item defined in the change. Report components and the share of lines outside the largest | C | [ClusterChanges](https://blog.acolyer.org/2015/06/26/helping-developers-help-themselves-automatic-decomposition-of-code-review-changes/): about 42% of 1,000 Office changesets had more than one partition, and 16 of 20 developers agreed. It over-partitions on common attributes |
| Moved-line share | Multiset intersection of removed and added lines with at least 20 alphanumeric characters | C | A block moved and lightly edited counts as new. No target from any source |
| Cosmetic lines | Items whose token stream is unchanged, or unchanged after numbering identifiers by first appearance. Share of changed lines | C | [METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/). Google allows small cleanups, so the allowance stays above zero |
| State of the touched files (report) | `LT`, `ND`, `NUC`, `AGE` from [Kamei et al.](https://sailresearch.github.io/sail-website/data/pdfs/TSE_ALarge-ScaleEmpiricalStudyOfJust-in-TimeQualityAssurance.pdf) | C | Charging for these punishes work on bad code |
| Speculative additions | Added items with no non-test use; traits with one `impl`; `pub` items with no use outside their module; generics with one instantiation | C | [Oukay et al.](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/). Stacked PRs add items a later PR uses, and one-impl traits serve test doubles |
| Public API change | `cargo public-api diff`; `cargo semver-checks --baseline-rev` | C | Rustdoc JSON is unstable. A break in an internal crate is usually harmless, so use the count |
| Lockfile change | Packages added, removed, version-changed | C | |
| Changed expected values | Same assertion macro and first argument, different other arguments; reported with whether production code the test reaches changed | C | A requirement change edits these legitimately, so this is a flag |
| Warnings added | Broader Clippy lint set on base and head, fingerprinted by lint, item and message; added per 100 changed lines | C | [Cynthia et al.](https://arxiv.org/abs/2601.20109) used the same comparison. Choose the lint set first |
| Failed checks before merge (report) | Failed check runs on every commit of the PR | C | Each failed check lowered merge odds by about 15% in [Ehsani et al.](https://www.alphaxiv.org/abs/2601.15195.md), on the last commit, with merging as the outcome |
| Review rounds and comments (report) | Reviews requesting changes; comments per 100 lines; share of PRs merged with no comment | C | Activity, not quality |
| Patch variation (report) | Standard deviation over mean of the diff size across a PR's commits | C | [Sony Mobile](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf): higher values went with fewer defects, so do not charge |
| Approval speed and discussion (report) | Self-approved; lines per minute between the reviewed commit and approval; no comments | C | A partial test of rubber stamps. Insignificant at Sony Mobile |
| Lines changed after approval | `git diff <approved commit_id> <head>` ignoring whitespace; these count as unreviewed in 3.9 | C | Compare trees, because a rebase changes hashes |
| Duplicate PR | Jaccard overlap of `(file, item)` sets with open and recently merged PRs | C | Two PRs in a busy file overlap without being duplicates |
| Description checks | Vague title from a list; title under 7 words or body under 80 words; backticked names that appear in neither the diff nor the repository | C | [Pham and Ghaleb](https://arxiv.org/pdf/2601.17627) for the lengths. Length is easily padded |

### 3.8 Test lenses

| Lens | Object | How to compute | From | Evidence or gap |
| --- | --- | --- | --- | --- |
| Surviving mutants | Piece, PR | `cargo mutants --in-diff`; a count | M | Best-supported test metric. Tests that pin current output can still pass it |
| Pseudo-tested functions | Function | Covered, with at least one viable body-replacement mutant, and all missed | C | [Niedermayr et al.](https://ar5iv.labs.arxiv.org/html/1611.07163): mean 11.41% of methods under unit tests. [Vera-Pérez et al.](https://arxiv.org/abs/1807.05030) found developers often would not pay to fix them, so do not target zero |
| Uncovered lines | Piece, PR | cargo-llvm-cov and the diff; a count | M | Weak alone; catches code no test even runs |
| Tests per 100 lines | Crate, codebase | Test functions and production lines | M | No evidence either way. Too many and too few are both bad, so it needs a target range |
| Test lines per production line | Crate, PR | Line counts | C | Same |
| Tests without an assertion | Test | Syntax rule | C | |
| Test length | Test | Lines | C | |
| Test run time | Crate | Test runner | C | |
| Redundant tests | Test | A test is redundant if it catches no mutant that another test misses | C | Expensive; run occasionally |
| Message-wording probe | Test | Rewrite every message string in production code, keeping placeholders, and run the tests. A test that newly fails is a candidate pin. Allowlist files whose output is a contract | C | Untested. Cargo-mutants has no string mutation, so this needs its own rewriting. One build and one test run |
| Behavior-preserving probe | Test | Rename private items, reorder fields, vary `HashMap` order; record failures | C | The most speculative item in this document |
| Non-API references | Test | Share of items a test references that are outside the API | C | [Google](https://abseil.io/resources/swe-book/html/ch12.html) calls private-method tests more brittle. Rust places unit tests beside private code by convention. Target range only |
| Interaction assertions | Test | `.expect_*()`, `.times()`, `.with()` on mocks, per test | C | [Google, ch. 13](https://abseil.io/resources/swe-book/html/ch13.html). A mock at a real external boundary is correct |
| Exact-output assertions | Test | Compared against a string literal of 40 or more characters, `format!("{:?}")`, `.to_string()`, snapshot macros, `include_str!` | C | Sensitive Equality smell. Wire formats are often the spec, so allowlist those |
| Test smell rules | Test | One count per rule: conditional logic, duplicate assert, eager test, ignored test, magic number, mystery guest, print, redundant assertion, sleep | C | [Spadini et al.](https://research.tudelft.nl/en/publications/on-the-relation-of-test-smells-to-software-code-quality/): smelly tests were more change- and defect-prone, in Java. Many are style |
| Assertion blocks | Test | Longest run of consecutive assertions; repeated normalized runs | C | Concept from CodeScene, thresholds own |
| Flake rate | Test | A test with both pass and fail on the same tree | C | Run on unchanged commits, otherwise this stays near zero. Mutants read a flake as a kill (section 6.8) |

### 3.9 Unreviewed lines

Lines written without human review: lines in `HEAD` whose PR was written, committed and merged by agents with no human approval, and which no later review marker covers.

- **Why it is separate:** it measures exposure. Good code can be unreviewed. It should be reported beside the score, per module, as a count and a share.
- **Computing it:** `git blame -w -M -C` maps each line to a commit, and the commit to its PR. Author, trailers and approvals come from the Git host. Lines changed after the approval count as unreviewed.
- **Review marker (Malte's proposal):** a comment saying "Smog, I reviewed this; everything before this commit counts as reviewed."
- **Forgery risk:** an agent could write that marker. It must come from an allowed human account, or be a signed commit or tag.
- **Rubber stamps:** an approval shows that someone clicked. Approval speed in 3.7 partly tests this.
- **Refactors:** an agent moving or rewriting reviewed code makes it unreviewed again, apart from what `-M -C` recognizes as moved. This seems correct for rewrites and wrong for mechanical changes.

### 3.10 History lenses

These assume squash merges, so one commit on `main` is one PR.

**Test churn (Malte's idea).** Target: tests that pin behavior the spec does not require. Measure: how often a test changes. The reasoning is that a test tied to the current implementation must be edited whenever that implementation changes, even when the required behavior did not. A test tied to the spec changes only when the spec does.

Counting per line is unreliable, because lines move and get reformatted. Count per test function instead: parse each commit and compare a hash of the test's normalized syntax tree, so formatting does not count.

| Lens | Object | How to compute | From | Evidence or gap |
| --- | --- | --- | --- | --- |
| Test churn | Test | PRs that changed the test, per test | M | The raw form; high in any busy area |
| Relative test churn | Test | PRs that changed the test, divided by PRs that changed the code it tests | C | Corrects for busy areas. Needs a map from test to code |
| Test breakage rate | Test | Run the base commit's tests against each PR's production code; count the PRs that broke each test | C | An agent cannot hide it by rewriting the test in the same PR. A test that breaks in many PRs is the signal. Inline `mod tests` needs syntax-tree splicing, so do it after the rest |
| Assertion churn | Test | Edits that change an assertion, separate from setup | C | Setup edits are less suspicious |
| Code churn | Function, file | PRs that changed the item in a window | M | Common predictor on human code |
| Relative code churn | Crate | `(added + deleted) / lines at the window's end` | C | [Nagappan and Ball](https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/) favor it over absolute churn. Redundant, with a negative relationship to defects, at Sony Mobile |
| Short-term churn | PR | Added lines rewritten or deleted within a set number of later PRs | C | |
| Item survival | PR, codebase | Follow each added item by identity; median survival and share removed within N PRs | C | [Pham and Ghaleb](https://arxiv.org/pdf/2601.17627): 3 days against 34. A rename with a body change looks like a removal |
| Reverts | PR | Commits on `main` that revert a PR | C | |
| Follow-up fixes | PR | Later fix PRs touching the same lines | C | Needs reliable fix labels |
| Files changed together | File pair | How often two files change in the same PR | C | |
| Modularity violation | File pair | `HCP[x,y]` = PRs changing both over PRs changing x. Flag pairs with no dependency either way where the larger HCP is at least t, with at least n shared PRs | C | [Xiao et al.](https://personal.stevens.edu/~lxiao6/papers/ICSE-16-Debt.pdf). Tangled PRs make false pairs, so filter with disconnected change groups |
| Unstable interface | File, module | Dependents that changed with the file at least 2 times in the window, flagged at 5 or more, using PRs where the public API changed. Also PRs that added, changed or removed public items per module, and breaking changes per PR | C | [Case study](https://arxiv.org/pdf/1811.12904) for the rule, whose thresholds were set for its own short history. A young API churns legitimately |
| Anchor patterns | File | For a file and its dependents, count whether dependents dominate it or it dominates them, by HCP | C | Xiao et al. equations 8 and 9. An interface should change its dependents, and not the reverse |
| Co-changing clones (report) | Function pair | Equal body hashes with identifiers numbered; PRs changing both, and PRs changing one only | C | A narrower form of duplication that may avoid the dispute in 2.1, because the copies have shown they are one concept |
| Hotspots | File, function | Change frequency combined with a high penalty | C | Keeps a simple `lib.rs` that changes often off the list |

**Limits of history:**

- It says nothing about new code, so a pinned test is invisible until the code around it changes.
- High churn does not prove pinning, because requirements do change. Low churn does not prove quality, because the code may simply not have changed.
- A young repository has too little history. No published minimum exists, so use the local stabilization test in 4.2.
- Ownership and author experience are left out, because they mean little when one agent writes everything.
- No study tests whether test churn identifies pinned tests. Your own history can test it: read the highest-churn tests and see how many are pinned.

**Mutation testing and pinned tests pull in opposite directions.** Pinned tests are good at killing mutants, because they assert exact output, so a mutation target on its own rewards pinning. Two consequences:

- Zero surviving mutants is the wrong target. A mutant in something the spec does not require, such as an error message's wording, should survive, and a test that kills it is a pinned test. The allowance for surviving mutants must stay above zero.
- History charges for what mutation testing rewards: a pinned test earns credit at once and pays in churn and breakage later. A pinned test around code that never changes is never charged.

History lenses use a rolling window of recent PRs, so a penalty clears once the test stops changing.

### 3.11 Considered and left out

| Idea | Why |
| --- | --- |
| LLM judgment | Rubber-stamping, and scores vary between runs |
| Duplication as a penalty | Duplication is a trade-off, and removing it adds dependencies. Report only |
| Agent token cost | Depends on the model and instructions |
| Poisoning dose test: inject bad code and measure agent success | Uses agents to measure what agents cannot be trusted to judge, and depends on the model and instructions. The owner decides how much low-quality code is acceptable |
| Maintainability Index, CRAP | Composites of lenses already listed, with unexplained constants |
| Embedding similarity between a PR and its commits | Depends on an embedding model, close to the objection to LLM judgment |
| Developer count and experience | One agent writes everything |
| Decoupling Level | Its formula could not be read, so its computation is unknown |
| Checked coverage | No Rust tool, and dynamic slicing would have to be built |
| Churn entropy per crate | Insignificant in Shimagaki et al. |

**No workable computation was found for these:**

- A module hides a design decision. Unstable interface and modularity violation show effects, not the property.
- A module follows processing steps.
- Tests are correct, sensible and useful. That needs a spec.
- One source of truth for each fact. Data clumps reach it partly.
- The PR improves code health. The debt rule approximates this by policy.

### 3.12 Keeping lenses honest

Agents optimize what is measured, and the research has direct evidence of them gaming tests. Every lens needs another that catches its obvious exploit:

| Exploit | Caught by |
| --- | --- |
| Split functions into fragments to shorten them | Effective length, pass-through functions, one-caller chains |
| Split a type's fields into nested structs | Nested structs used by one owner count toward the owner's fields |
| Spread code over many small files | Files per folder, modules |
| Insert blank lines to break paragraphs | Merge short paragraphs, function length, blank-line density |
| Tests that run code but assert nothing | Surviving mutants, tests without an assertion |
| Tests that pin current output | At merge time, as untested candidates: message-wording probe, non-API references, exact-output assertions. Later: test churn and test breakage |
| Edit an expected value or weaken an assertion | Changed expected values, assertion tiers |
| Add tests to raise a count | Tests per 100 lines upper range, redundant tests |
| Lower the penalty by editing thresholds | Check: gate is untouched; policy lives outside the repository |
| Silence a lint or skip a test | Check: no new suppressions |
| Reword a slop comment to dodge the phrase list | Nothing reliable |

## 4. Aggregation

### 4.1 Pipeline

1. **Raw value:** one number per lens per piece.
2. **Penalty per lens:** a curve turns the value into points.
3. **Penalty per piece:** combine the piece's lens penalties.
4. **Debt:** add up the pieces into a total.
5. **Score:** turn the total into a number. Piece scores use `score = exp(-penalty)`, which keeps falling and never reaches 0.

Scores run from 0 to 1. The codebase score is the line-weighted mean of piece scores, or `1 - debt per 1,000 lines / 100`. The two behave alike at scale (4.7), and only the second adds up across PRs.

### 4.2 What sabermetrics offers

Sabermetrics contributes method more than formulas. Baseball has an outcome, runs, to fit weights against. Code has no such outcome, so the score stays a policy.

| Baseball idea | What it is | Use in Smog (all C, untested) |
| --- | --- | --- |
| Three tests for a metric | [Descriptiveness, reliability, predictiveness](https://baseballprospectus.com/news/article/41748/prospectus-feature-the-expected-contribution) | A lens must pass before it is charged. Reliability: do two disjoint samples of PRs rate a piece alike? Predictiveness: does it predict later reverts or short-term churn? Independence: does it add anything beyond length? |
| Stabilization | [Correlation of .7 between samples](https://library.fangraphs.com/principles/sample-size/). Strikeout rate needs 60 PA, batting average 910 AB | Compute each history lens's window from your own history. A lens that never reaches .7 is noise for that object |
| Regression to the mean | [Add league-average sample to the observed sample](https://blogs.fangraphs.com/fangraphs-prep-regression-towards-the-mean) | Shrink rates with few events. A test changed in 3 of 3 PRs, with crate mean 0.1 and k = 20, becomes (3 + 2) / 23 = 0.22. One changed in 30 of 100 becomes 0.27. The raw rates, 1.0 and 0.3, rank them the wrong way round |
| FIP | [Counts only what the pitcher controls](https://library.fangraphs.com/pitching/fip/) | Charge a PR only for debt it added. Measure run-to-run variation separately |
| Linear weights | [wOBA weighs each event by run value](https://library.fangraphs.com/offense/woba/) | Lens weights could be fitted once there are enough reverts and failures. Until then they are policy. Do not refit often, because fitted weights can be exploited |
| Replacement level | [A fixed .294 winning percentage](https://library.fangraphs.com/misc/war/) | Fix a reference: debt per line from a template you consider good |
| Relative scale | [wRC+: league average is 100](https://library.fangraphs.com/offense/wrc/) | Do not use this for gating. A scale relative to your own recent code hides decline |
| Park and position adjustment | [Context-neutral WAR](https://library.fangraphs.com/misc/war/) | Different targets for parsers, glue code and tests. Humans assign each area, because an agent could move code to a lenient one |
| Humility about precision | ["a guide for separating groups of players"](https://library.fangraphs.com/misc/war/) | Report bands. 0.899 and 0.901 do not differ without a noise margin |

### 4.3 Curves

A lint says 100 lines is fine and 101 is wrong, which gives permission to write 100-line functions. A curve charges every line above a target, and charges more the further out it is:

```
penalty = ((value - target) / (limit - target))²    when value > target, otherwise 0
```

Curve shapes, all with target 20 and limit 100. The exponential form is `(b^x - 1) / (b - 1)`, with `x = (value - target) / (limit - target)` and b = 9:

| Lines | Linear | Quadratic | Cubic | Exponential |
| --- | --- | --- | --- | --- |
| 30 | 0.125 | 0.016 | 0.002 | 0.04 |
| 60 | 0.50 | 0.25 | 0.125 | 0.25 |
| 100 | 1.00 | 1.00 | 1.00 | 1.00 |
| 120 | 1.25 | 1.56 | 1.95 | 1.82 |
| 150 | 1.63 | 2.64 | 4.29 | 4.32 |

Higher powers are softer near the target and harsher past the limit. Quadratic is the default, because it is easy to explain. No evidence favors any power for code.

**Mapping to a score.** With `score = exp(-penalty)` and the quadratic curve above:

| Score | Penalty | Function length |
| --- | --- | --- |
| 0.90 | 0.105 | 46 lines |
| 0.70 | 0.357 | 68 lines |
| 0.37 | 1.000 | 100 lines |

If 46 lines looks wrong for a floor of 0.9, change the target and limit, and leave the mapping alone.

**Curves that hurt more and more reward splitting.** Any curve that starts at 0 and steepens charges one big thing more than its parts:

| Same code as | Penalty |
| --- | --- |
| One function of 60 lines | 0.25 |
| Two of 30 | 0.03 |
| Three of 20 | 0 |
| One function of 100 lines | 1.00 |
| Four of 25 | 0.02 |
| Five of 20 | 0 |

The guard must compete with that discount, so it belongs in the measure: effective length (3.2). With α = 1, splitting into one-caller helpers saves nothing. With α = 0.5, 60 lines split into three functions count as 40 and cost 0.06. α must stay below 1 if decomposition is to pay at all, since [Chowdhury et al.](https://arxiv.org/abs/2205.01842) report that it lowers maintenance effort. The same applies to types: nested structs used by one owner count toward the owner's fields.

**Tail form.** With unbounded curves, one enormous legacy item can dominate the score. Use a knee: quadratic to a far limit, then a straight line at the same slope. The cost of a further line stays positive, and the total stays readable. A cap would make further decline free. For the same reason, the `max(0, ...)` form of a score is not used.

**Malte's paragraph rule.** "10 is allowed, 15 is tolerable, then every line costs serious points" needs two slopes:

```
paragraph penalty = 0                         n ≤ 10
                  = 0.02 × (n - 10)           10 < n ≤ 15
                  = 0.10 + 0.10 × (n - 15)²   n > 15
```

| Paragraph lines | 10 | 11 | 15 | 16 | 17 | 18 | 20 | 25 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Penalty | 0 | 0.02 | 0.10 | 0.20 | 0.50 | 1.00 | 2.60 | 10.10 |

So 18 lines costs as much as a function at its limit. Sum over all paragraphs in a function; otherwise a function with one 18-line paragraph can add others for free.

**The exploit is a blank line.** It costs nothing, and rustfmt allows it. An agent that inserts one every 10 lines still passes, which may be acceptable if the groups make sense. This lens starts with a low weight.

**Where targets come from.** Targets and limits are policy. To avoid inventing them, take them from a frozen template you consider good, using the percentiles of its own distribution, as [SIG does](https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf) at 70%, 80% and 90% of code, weighted by lines. Rolling percentiles from your own code fall as quality falls, so do not use them.

### 4.4 Other measurements

| Measure | Answers | Evidence | Weakness |
| --- | --- | --- | --- |
| Line-weighted median | Where does typical code sit? | SIG's thresholds use the same weighting | |
| p90, maximum | How far out is the tail? | | A percentile says nothing about what lies beyond it |
| Share of lines per band | How much code is risky? | [SIG](https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf) | Band edges are cliffs |
| Mean of the worst K lines, K fixed | How bad is the tail? | [Expected shortfall](https://en.wikipedia.org/wiki/Expected_shortfall), from finance | Untested on code |
| Squale mark | One number stressing bad pieces: [`-log_w(average(w^-mark_i))`](https://www.squale.org/quality-models-site/research-deliverables/WP1.3_ICSM-2009_ShortPaper.pdf) | With 1,000 pieces at mark 3 and 10 at mark 0, the mean is 2.97, and Squale with w = 9 gives 2.04 | A ratio, so it cannot be summed across PRs |
| Theil index (report) | Is debt concentrated, and in what? | [Decomposes by group](https://ercim-news.ercim.eu/en88/special/seeing-the-forest-for-the-trees-with-new-econometric-aggregation-techniques) | Report only |
| Geometric mean of groups | A non-compensating score across unrelated groups | [HDI uses it](https://www.englishschool.ac.cy/udata/contents/files/docs/Departments/Economics/as_a2_resources/New-HDI-2010.pdf). Structure, tests and PR hygiene at 0.1, 1, 1 give 0.46, against an arithmetic mean of 0.70 | A zero anywhere gives zero, so it needs the `exp` mapping |
| Debt slope | Is it getting worse? | | Depends on the chosen lenses |
| Equilibrium score | Where is it heading? | Section 4.9 | Noisy with few PRs |
| Hotspot score | Is the code we change healthy? | [CodeScene](https://codescene.io/docs/guides/technical/code-health.html), a vendor | Rewards not touching bad code |

**Median creep (Malte's example).** You want a median near 20 lines, and slippage should cost points. The curve charges only above its target, so a median moving from 8 to 19 lines costs nothing with a target of 20. Track the line-weighted median as its own lens, the function length at which half of all lines sit in shorter functions. A plain median can be gamed by adding many tiny functions. Give no credit below the target, because agents could farm it with tiny functions.

### 4.5 Combining lenses within a piece

| Method | Strength | Weakness |
| --- | --- | --- |
| Worst lens (Malte) | Suits the data, because length, complexity and nesting are correlated and a sum would charge the same problem several times. Tells the agent which lens to fix | A piece already bad on length can get worse on complexity for free |
| Worst lens plus a small share of the others | Further decline still costs | One more constant |
| Groups of correlated lenses: worst within a group, plus a small share of the others, summed across groups (C) | Length and complexity are not charged twice, and tests or coupling are not free | The grouping is a judgment |
| Per-lens PR gate alongside the worst lens | Simple | Many findings |

### 4.6 Combining pieces

| Method | Strength | Weakness |
| --- | --- | --- |
| Mean | Simple | Hides bad code; many small good files raise it |
| Line-weighted mean | Size counts | Still hides bad code |
| Minimum across all pieces | No hiding | One old function fixes the score forever, and flags that cannot be cleared get ignored |
| Risk profile: share of lines per band (SIG) | Readable, traceable | Band edges are cliffs |
| Power mean, or Squale's weighting | Low marks count more | Hard to read; a ratio, so it cannot be summed across PRs |
| Sum of penalties (debt) | Adds up across PRs, and a PR's change is not diluted by codebase size | Grows as the code grows, so it needs a reference |
| Mean of the worst K lines | A fixed window cannot be diluted by padding | Untested on code |

Only counts and costs add up across changes, so a per-PR budget (section 5) needs a sum. Taking the worst lens within a piece and summing across pieces is one combination that provides this.

**A file's score** should be its worst item, or the mean of its worst items. A line-weighted file score lets 400 good lines hide a 150-line function, and moving a bad function into a large good file improves that file.

### 4.7 Why a single codebase score is insensitive

With a line-weighted score starting at 0.95:

| Codebase | Lines of score-0 code to reach 0.90 | Lines of score-0.5 code to reach 0.90 |
| --- | --- | --- |
| 10,000 lines | 556 | 1,250 |
| 1,000,000 lines | 55,556 | 125,000 |

- **Concentrated damage hides.** A 5,000-line module falling from 0.95 to 0 moves that 1,000,000-line codebase from 0.950 to 0.945.
- **Padding helps.** Adding 100,000 lines of trivial code at 1.0 raises it from 0.950 to 0.955.

The density form, `100 - debt per 1,000 lines`, behaves the same way at scale.

### 4.8 What stays sensitive on a large codebase

| Mechanism | Why size does not matter |
| --- | --- |
| Absolute debt per PR | No division by codebase size |
| Equilibrium score | Uses recent PRs only |
| Floors per module and crate | Each is judged at its own size |
| Mean of the worst K lines | The 5,000-line module above: if the worst 10,000 lines averaged 0.6, they now average about 0.3 |
| Change detection on the PR stream | Sees a sustained shift even when each PR passes |
| Funnel plot across modules | [Limits narrow with size](https://rdrr.io/cran/FunnelPlotR/man/funnel_plot.html), so small crates can vary without alarm and large crates cannot hide |
| Hotspot-weighted score | Weighted to code being changed |

**Change detection.** PR debt can drift upward while every PR passes. [NIST](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm) says a CUSUM detects small shifts better than a Shewhart chart. PRs taken to notice a shift, with k = 0.5 and h = 5:

| Sustained shift in PR debt | Per-PR limit at 3 sigma | CUSUM |
| --- | --- | --- |
| None (false alarm interval) | 741 | 929 |
| 0.5 sigma | 161 | 38 |
| 1 sigma | 44 | 10.5 |

Both columns assume independent, normally distributed values. The per-PR column is computed and the CUSUM column simulated. Real PR debt will be skewed with many zeros, so calibrate on your own history. An [EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm) with λ of 0.2 to 0.3 does similar work. An alarm prompts investigation and does not block a PR, because no single PR caused it.

**Few events.** With 10 requests an hour, [one failure produces a 1,000x burn rate](https://sre.google/workbook/alerting-on-slos/). The same applies to small crates, so group them or lengthen their windows.

### 4.9 The three outputs

One number cannot answer three different questions, so Smog reports three lines. The numbers are examples:

```
HEALTH    0.95, worst 10k lines 0.58, hotspots 0.81, slope -0.002 per 100 PRs
CAPACITY  equilibrium 0.90, freeze 0.92, runway 3,000 PRs (150 days), sustainable 20 PRs/day
POISON    margin to limits 0.03; exposure 12% of PRs; contagion +0.3 debt/100 lines; gate caught 37/40 seeded PRs
```

All of this is untested. No source gives a validated way to turn code metrics into capacity or tolerance. So both are computed by programs, from the limits the owner sets and the recent PR stream.

**Health.** The codebase score, with worst-K lines, hotspot score and slope beside it. A human reads this.

**Agent capacity.** With `L` lines and `D` debt, recent PRs adding `d` debt and `l` net lines each, and a freeze line at density `f`:

```
equilibrium density = d / l
runway in PRs       = (f × L - D) / (d - f × l)        when d > f × l
excess per PR       = d - f × l
sustainable PRs/day = cleanup debt removed per day / excess per PR
```

Current density always moves toward the density of what is being added, so a large codebase at 95 with PRs at equilibrium 90 is heading to 90, however large it is. Equilibrium is the number that does not dilute. Example with `d = 5`, `l = 500`, so equilibrium 90, and a freeze at 92 (`f = 0.008`):

| Codebase | Density now | Score now | Runway | At 20 PRs/day |
| --- | --- | --- | --- | --- |
| 10,000 lines | 5 per 1,000 | 95 | 30 PRs | 1.5 days |
| 1,000,000 lines | 5 per 1,000 | 95 | 3,000 PRs | 150 days |

Same score, same PR quality, and 100 times the runway. Excess per PR is 1, so cleanup removing 20 debt per day supports 20 PRs per day indefinitely. If `d ≤ f × l`, this measure sets no limit. These formulas use density, so `score = 100 - density` here; on the 0 to 1 scale, divide by 100.

**Poisoning tolerance.** What the evidence says:

| Source | Finding | Limit |
| --- | --- | --- |
| [Comment Traps](https://arxiv.org/abs/2512.20334) | Defective commented-out code in context raised generated defects by up to 58.17%. Telling the tool to ignore it reduced them by at most 21.84% | Copilot and Cursor, abstract only |
| [Sourcery](https://sourcery.ai/blog/does-bad-code-make-agents-worse) | Success 81.9% with maximum cognitive complexity of 9 or less, 56.2% above. Average complexity and smell counts did not correlate | 9 tasks, a blog, no statistical tests |
| [Borg et al.](https://arxiv.org/html/2601.02200v1) | Refactoring break rates lower on healthy code for five medium models, such as 39.9% against 50.0%. Not significant for Sonnet and Claude. AUC 0.54 to 0.57 | Competitive-programming Python, authors include CodeScene staff |
| [Sonar](https://www.sonarsource.com/blog/your-ai-agent-doesnt-know-your-codebases-context-or-constraints/) | About 540 Claude Code runs. Clean repositories used 7.2% fewer input and 8.5% fewer output tokens; pass rate changed by -0.9 points | Vendor, setup not on the page |
| [He et al.](https://arxiv.org/abs/2511.04427) | Transient velocity, persistent complexity and warnings, which drive later slowdown | Abstract only, observational |
| [CodeThread](https://arxiv.org/abs/2606.21804) | Agents solved up to 13.1% fewer tasks building on agent-written code | Traditional metrics did not explain the difference |

Bad code raises cost, and lowers success for some agents and tasks. Whether strong current agents lose much success is unclear. One small study suggests the worst piece matters more than the average, which would support floors and tail measures. That is not enough to derive a number, so the amount of low-quality code the codebase may take is the owner's decision, expressed as floors, budgets and the freeze line. **Tolerance is the remaining distance to those limits.** These measures sit beside it:

| Measure | How | Gap |
| --- | --- | --- |
| Exposure | Share of agent PRs in the window that touched a piece under the floor | A count, available from the start |
| Contagion | Debt per added line against the penalty of the code touched, controlling for crate. A positive slope means bad code begets bad code | Observational; agents may be sent to hard areas |
| Gate leak rate | Share of seeded bad PRs the gate catches, per exploit class (section 5.6) | Covers only the classes seeded |

The gate leak rate shows how fast low-quality code can grow unnoticed.

## 5. Rules

### 5.1 Malte's rules

| Rule | Result of the analysis | Fix |
| --- | --- | --- |
| Whole codebase at 0.9 or better, otherwise no merge | Cannot detect one PR on a large codebase (4.7). Once below 0.9, every PR blocks, including PRs that did nothing wrong, and the model requires that every finding be clearable by the PR | Below 0.9, only PRs that lower debt, or human-approved exceptions, can merge. This is a freeze, in the form of [Google's error budget policy](https://sre.google/workbook/error-budget-policy/). PR rules below do the per-PR gating |
| New code at 0.9 or better | Fits a large codebase, because the new code is the denominator. [SonarQube's default gate](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/) works this way. An agent can pick the softer regime by growing an existing function | The same curve applies to new and modified code, and only the allowance differs. No exemption for small changes: Sonar's 20-line exemption can be stayed under indefinitely. Score by effective length |
| Budget for modified code | Works well with a convex curve, which tightens by itself (table below). Its hole is repetition: a function reaches 100 lines in 20 PRs of 0.05 each | A second limit over a rolling window, read from a ledger keyed by item identity, so a rename does not reset it |
| No file below 0.7 | Sound. Old code would block every PR that touches it. Moving code to an excluded path dodges it | Strict for new pieces. Existing pieces under the floor are frozen: they may not get worse, and their count may only go down. Exclusions are a human-owned, fail-closed list. Use the floor at every level: function, file, module, crate |
| Paying for paragraph size | Section 4.3 | A curve with a low weight |

**Budget of 0.05 per PR:**

| Function length now | Lines it may grow |
| --- | --- |
| 20 | 17.9 |
| 60 | 3.8 |
| 80 | 2.6 |
| 100 | 2.0 |

This gives agents room on healthy code and almost none on bad code, so no separate "must fix what you touch" rule is needed for it. Radiation protection uses the same two-limit form: ["20 mSv per year, averaged over defined periods of 5 years, with no single year exceeding 50 mSv"](https://icrpaedia.org/Dose_limits).

### 5.2 Available rules

| Rule | Check | Purpose | Block? |
| --- | --- | --- | --- |
| Pass/fail | Any failure in 3.1 | Hard requirements | Blocks |
| PR debt | Debt added ≤ base + rate × non-cosmetic added lines | Decline in the whole codebase, with no dilution | Blocks |
| New piece floor | Score ≥ 0.9, by effective length | New code | Blocks |
| Piece budget per PR | Penalty increase of any one piece ≤ limit, such as 0.05 | A local decline cannot hide in a good PR | Blocks |
| Piece budget over a window | Increase over the last 50 PRs ≤ limit, such as 0.15 | Many small drops add up | Blocks |
| Piece floor | Function and file ≥ 0.7. Existing offenders frozen, and their count may not rise | Local catastrophe | Blocks |
| Ratchet | A count may only fall, [as in Betterer](https://phenomnomnominal.github.io/betterer/docs/introduction) | Hard counts, such as files over the floor | Blocks |
| PR size | Lines and files ≤ limit | The PR itself | Blocks |
| Crate floor | Crate ≥ 0.8 | What a codebase score cannot show | Freezes that crate |
| Codebase floor | Score ≥ 0.9 | Overall health | Freezes feature work |
| Stream detection | CUSUM on PR debt, with [fast and slow burn windows](https://sre.google/workbook/alerting-on-slos/) | Drift no single PR causes | Opens a ticket; stops the factory on a fast burn |
| Sealed lenses | Divergence, seeded PRs, random audit (5.6) | Gaming | Alerts humans |
| Report | Health, capacity, poison outputs | Trend | Never |

Coverage and mutation results enter as counts added by the PR (uncovered lines, surviving mutants), because a repository-wide percentage does not move for one PR.

History lenses count toward the codebase score. They stay out of the PR debt rule, because one PR should not fail for churn that earlier PRs caused.

### 5.3 Holes in the PR debt rule

- **An allowance per changed line can be farmed.** Reformatting code would buy room for debt. So count only added lines that are not cosmetic, and add a small base so a one-line PR can still add a small amount.
- **Credit can be laundered.** "Removing debt earns credit" lets an agent split or delete easy things to pay for hard debt elsewhere. So cap credit, keep it inside the same crate, and give none for code that moved or split.

### 5.4 Choices within the rules

| Choice | Options |
| --- | --- |
| Existing debt | A PR pays only for debt it adds, or it must also fix bad code it touches |
| Over a limit | The PR blocks, or the piece keeps paying on the curve |
| Unreviewed lines | Report only, or block above a limit per module. The mixed evidence on review and defects fits reporting better |
| Weakened tests | Deleted tests and removed assertions block, or cost points |
| Codebase below 0.9 | Features stop fully, or a small allowance remains |
| Effective length | α between 0.5 and 1 |
| Sealed lenses | Used, or all findings stay open |

### 5.5 Noise

A rule tighter than the run-to-run noise of its input fails at random. Syntax-based lenses are deterministic. Coverage and mutation results are not: measure the variation on unchanged commits, and allow for it.

### 5.6 Gaming resistance

[Manheim and Garrabrant](https://ar5iv.arxiv.org/html/1803.04585) name four ways a proxy fails, and each needs a different defense:

| Type | Meaning | Defense |
| --- | --- | --- |
| Regressional | Selecting on the proxy also selects its noise | Margins, shrinkage |
| Extremal | The link fails at extreme values | No reward beyond a target, and no credit for tiny functions |
| Causal | Changing the proxy does not change the goal | Test predictiveness, and do not gate on weak proxies |
| Adversarial | Another actor responds to the metric | The defenses below |

Gaming by agents is measured. In [ImpossibleBench](https://arxiv.org/html/2510.20270v1), tasks are impossible, so any pass is a cheat: GPT-5 reached 54%, o3 49% and Claude Opus 4.1 50% on one benchmark. Results vary a lot by benchmark and prompt.

Defenses, strongest first. All are C and untested in this application:

1. **Exploit suite.** Write each known exploit as a test of Smog itself: a code pair where the transformed version must not score better. Examples: split into one-caller helpers, add blank lines, rename, move a function to another file, nest fields in a struct, add trivial code. Each new exploit becomes a test.
2. **Sealed lenses.** Keep some lenses out of the agent's view and do not gate on them, because section 6.10 requires a finding to be clearable. If open lenses improve and sealed lenses do not, that points to gaming. Support is mixed: in ImpossibleBench, hiding tests cut cheating to near zero and also degraded performance. [StrongDM](https://simonwillison.net/2026/Feb/7/software-factory/) keeps scenarios outside the codebase, like a holdout set.
3. **Frozen references.** Targets come from a frozen template or benchmark (4.3). They change only by human decision.
4. **Ledger keyed by identity.** Debt follows the item through renames and moves, and the ledger lives outside the agent's reach.
5. **Seeded bad PRs.** Regularly run known-bad PRs through the gate without merging, and report the share caught per exploit class.
6. **Red-team agent.** Ask an agent to raise the score without improving the code, or to land named harm while passing every gate. The agent only proposes code pairs. A pair counts when a human confirms the code got worse and the program confirms it scored better, and it then goes in the exploit suite.
7. **Make the real fix cheaper than the fake.** [Kleinberg and Raghavan](https://arxiv.org/abs/1807.05307) characterize when agents can be led to intended effort. Rate each lens by what a fake costs against a fix: blank lines cost nothing, and layer violations are expensive to hide.
8. **Mute weak proxies.** [Holmström and Milgrom](https://edegan.com/wiki/Holmstrom_Milgrom_(1991)_-_Multitask_Principal_Agent_Analyses) show that paying on measured tasks moves effort from unmeasured ones. Comment density and test counts stay report-only until they pass the three tests in 4.2.
9. **Limit what retries reveal.** [The Ladder](https://proceedings.mlr.press/v37/blum15.html) shows that repeated evaluation lets participants overfit a holdout. In ImpossibleBench, multiple submissions raised cheating from 33% to 38%. Do not report sealed lenses per PR.
10. **Random audit.** Pick a random share of merged PRs for human or sealed review.

**Exploits against the rules:**

| Rule | Exploit | Defense |
| --- | --- | --- |
| Codebase ≥ 0.9 | Add trivial code | PR size limit, worst-K lines, the exploit suite |
| New code ≥ 0.9 | Grow an existing function instead | Same curve for new and modified |
| Modified budget | Many small PRs | Rolling window in the ledger |
| Modified budget | Rename to reset | Item identity |
| File ≥ 0.7 | Dilute within a file, or split | File score from worst items, effective length |
| Curve | Split | Effective length |
| Paragraph | Blank lines | Section 4.3 |
| PR size | Stack many PRs | Piece budget over a window, stream detection, disconnected change groups |
| Debt credit | Launder | Cap, same crate, none for moves |
| Excluded paths | Move code there | Human-owned list, fail closed |

### 5.7 A starting policy

The table in 5.2 is the starting policy, with all numbers as placeholders.

### 5.8 Backtest before enabling

Replay the rules over the squash-merged history and record what each would have blocked. Read a sample of those PRs. Then set limits where the blocks look right. A rule blocking 40% of PRs would stop the factory, and one blocking none does nothing. Each history lens also gets the stabilization test from 4.2 first.

## 6. Implementation and integration

**The first version is a Python package using tree-sitter, run from a policy script, with no GitHub integration yet. The design below is the target: one Rust binary, `smog`.** It parses code itself, reads the output of existing tools, applies the policy, and publishes a verdict. No product examined can express the curves, debt ledger and per-piece budgets. The binary runs on GitHub in two halves, because the code being judged is written by the agent being judged. A normal CI job can be edited by the agent's PR, or subverted by its `build.rs`, proc macros and tests.

```
agent pushes a branch, or the merge queue creates a group
        |
        v
smog-collect   pull_request, merge_group
UNTRUSTED        read-only token, no secrets, runs the PR's code
                 clippy, tests + coverage, mutants, index; uploads raw outputs
        |  workflow_run: completed
        v
smog-judge     runs from the default branch
TRUSTED          holds the Smog App key, never runs the PR's code
                 reads git objects, evidence, policy and ledger
                 posts the check run smog/gate on the PR's head commit
        |
        v
Ruleset          required check smog/gate, expected source = Smog App
        |
        v
squash merge --> smog-record (push to main) --> smog-state repository
```

Everything in this section comes from documentation, and no part of it has run. Workflow sketches are in `docs/research/2026-11-08-model-research/layer-6.md`.

### 6.1 Attacks on the gate

The attacker is an agent optimizing for a green check.

| Attack | What closes it |
| --- | --- |
| Edit the workflow in the PR | The agent's App has no Workflows permission. The verdict comes only from the judge, whose file [must be on the default branch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) |
| Post a fake check called `smog/gate` | [Select the App as expected source](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) |
| Read the App key from a PR workflow | Keep the key in an [environment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) whose deployment branches allow only `main` |
| Skip the collector | A required check that never reports [leaves the PR blocked](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks) |
| Run code inside the trusted job through [`.cargo/config.toml`](https://doc.rust-lang.org/cargo/reference/config.html), build scripts or proc macros | The judge never calls `cargo`, `rustc` or rust-analyzer on PR content. It reads git objects and data files only |
| Loosen a tool through its config in the tree | Section 6.3, and fixed config on the command line |
| Suppress in the source | "No new suppressions" in 3.1 |
| Hide tests from the build | "Tests stay in the build" in 3.1 |
| Poison the cache | The judge restores no cache |
| Merge around the gate | The agent's App is on no bypass list |
| **Forge tool outputs:** tests, build scripts and proc macros run in the same VM as the tools, and could rewrite the report files | **Not closed.** Partial: validate the schema, flag diffs that add `build.rs` or a proc-macro crate, flag file writes in test code, and rerun a random sample of merged PRs on `main` and alert on differences |

The agent must not push with `GITHUB_TOKEN`, because [events from that token do not create workflow runs](https://docs.github.com/en/actions/concepts/security/github_token). An App token avoids this.

Deliberate attacks on the factory are out of scope.

### 6.2 GitHub setup

**Two Apps:**

| | Agent App | Smog App |
| --- | --- | --- |
| Used by | The factory's agents | The judge and record jobs only |
| Permissions | Contents write, pull requests write | [Checks write](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps), contents write |
| Must not have | Workflows, administration, access to `smog-state`, any bypass | Any bypass, or use outside those jobs |

Only a GitHub App [can create a check run](https://docs.github.com/en/rest/checks/runs), so a dedicated App is required. Limit each job's token with [`create-github-app-token`](https://github.com/actions/create-github-app-token).

**Rules on `main`:**

| Setting | Value | Note |
| --- | --- | --- |
| [Require a pull request](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) | On | It need not be approved, so the factory can merge without a human |
| Required status check | `smog/gate`, expected source Smog App | `smog/report` stays optional |
| Allowed merge methods | Squash only | History needs one commit per PR |
| Bypass | Named humans only | [Admins are exempt by default](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) on branch protection unless "Do not allow bypassing" is on |
| Merge queue, or "up to date" | See below | Two PRs can each pass against a base the other then changes |
| [Push ruleset: restrict file paths](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Section 6.3's list, humans bypass | Private and internal repositories only |
| [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) review | Section 6.3's list | Whether it works with zero required approvals is unverified |

**What each GitHub plan allows.** On a private repository on GitHub Free, CI can report a result and cannot block a merge, so an agent with write access can merge or push to `main` regardless. A gate that blocks needs a public repository, or GitHub Pro or Team.

| Feature | Free, private | Free, public | Pro or Team, private |
| --- | --- | --- | --- |
| [Protected branches](https://docs.github.com/en/get-started/learning-about-github/githubs-plans), including required checks | Not listed, so read as unavailable | Likely, under Free's "full feature set" for public repositories | Listed |
| [Environment secrets, deployment branches](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | No | Yes | Yes |
| [Code owners](https://docs.github.com/en/get-started/learning-about-github/githubs-plans) | Not listed | Not stated | Listed |
| [Rulesets, including push rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Not listed | Not listed | Team only |
| [Merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Not stated | Not stated | Not stated |

On Pro or Team, a protected branch replaces the ruleset: it requires `smog/gate` and branches that are up to date. Push rules are not needed, because policy lives in `smog-state` (6.7) and the "gate is untouched" check covers the files in 6.3. The merge queue is not assumed.

**On Free with private repositories,** the gate is a rule that is audited, on the assumption that agents are benign:

- **Rule:** agents merge only through `smog merge <pr>`. It merges only if `smog/gate` succeeded on the PR's current head and the branch contains the latest `main`, and it squash-merges. No GitHub setting enforces this.
- **Audit:** `smog-record` checks every new commit on `main`. A commit with no PR, or whose PR head has no successful `smog/gate`, alerts a human.
- **Limit:** a violation is found after it lands, and must then be reverted.
- **Limit:** private repositories on Free have limited Actions minutes, and mutation testing on every PR uses many. If the minutes run out, no gate result exists and nothing can merge. Measure the use in build step 2.
- **Upgrade condition:** move to Pro or Team if the audit finds violations, or if the minutes run out.

**Merge queue.** Debt depends on the base: two PRs that each fit a piece's budget can exceed it together, so the second must be judged against the first.

| Option | Cost | Availability |
| --- | --- | --- |
| [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Must add `merge_group` | [Enterprise Cloud and public organization repositories](https://github.blog/changelog/2023-07-12-pull-request-merge-queue-is-now-generally-available/), as of 2023 |
| [Require branches to be up to date](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | Every merge invalidates all other PRs, which gets expensive with mutation testing at factory rates | Any plan with protection |
| [Mergify](https://docs.mergify.com/migrate/github-merge-queue) or similar | A third party holds merge rights | Vendor |

Use the merge queue if the plan has it, with squash and a maximum group size of 1 to start. Otherwise use "up to date", and measure how often agents have to rerun. In the queue, reuse the PR's mutation and coverage counts when the patch is unchanged, keyed by `git patch-id`. This assumes other PRs in front rarely change a mutant's result, so backtest it.

**Workflow details that matter:**

- **No checkout in the judge.** It fetches objects by SHA and reads them through git.
- **Collect on the PR head.** [`pull_request` defaults to the merge result](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), and required checks attach to the latest commit, whose line numbers findings need.
- **Conflicts.** `pull_request` does not run on a conflicting PR, which leaves it blocked. Agents treat that state as "rebase".
- **Verify the run.** The judge checks that the triggering run came from `.github/workflows/smog-collect.yml` and that its head SHA is the PR's current head. It treats artifacts as hostile: size limits, schema validation, no extraction to paths.
- **Branch names are attacker text.** Never put `workflow_run.head_branch` in a `${{ }}` in a script.
- **No path filters on the collector.** A filtered workflow [stays pending and blocks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks).
- **No `pull_request_target`.** GitHub says to [avoid it unless necessary](https://docs.github.com/en/actions/reference/security/secure-use), and `workflow_run` gives what is needed.
- **Pin every action** to a full commit SHA.

### 6.3 Files the agent may not change

| File | What it can do |
| --- | --- |
| `.github/**`, `CODEOWNERS` | Change CI and approval rules |
| `.cargo/config.toml`, also in parent folders of a crate | [`rustc-wrapper`, `runner`, `rustc`](https://doc.rust-lang.org/cargo/reference/config.html) replace or wrap what runs |
| `.cargo/mutants.toml` | [Exclude files and mutants](https://mutants.rs/print.html). Also pass `--no-config` |
| `.config/nextest.toml` | Profiles, retries, and a [`default-filter`](https://nexte.st/docs/selecting/) that excludes tests. Also pass `--config-file` and `--ignore-default-filter` |
| `clippy.toml`, `.clippy.toml`, `deny.toml`, `rustfmt.toml`, `sgconfig.yml` | Loosen a tool |
| `rust-toolchain.toml`, `rust-toolchain` | Choose the compiler. Smog names the toolchain explicitly |
| `[lints]` and `[profile.*]` in any `Cargo.toml` | Silence lints or change how tests build. Agents must edit this file, so check the sections and not the path |
| `build.rs`, proc-macro crates | Not blocked, because they are legitimate. A change is flagged for the audit sample |

### 6.4 The binary

On 2026-11-08, `smog` was free on PyPI and taken on crates.io. A private binary called `smog` works, and publishing a Rust version would need another crate name.

| Command | Runs in | Does |
| --- | --- | --- |
| `smog check-static` | Collector | Fast verdict on the syntax-only rules, to skip the slow jobs. Advisory |
| `smog collect <tool>` | Collector | Runs a tool with fixed arguments, stores raw output and versions |
| `smog judge-run` | Judge | Fetches objects, evidence, policy and ledger, then calls `judge` and `publish` |
| `smog judge` | Judge, local | Pure function: base facts, head facts, evidence, policy and ledger in; verdict out |
| `smog publish` | Judge | Posts check runs and annotations |
| `smog merge <pr>` | Agent | Checks the gate result and that the branch contains the latest `main`, then squash-merges |
| `smog record <sha>` | Push to `main` | Writes one PR's entry to the ledger, and audits the merge. Safe to rerun |
| `smog replay <range>` | Local, scheduled | Backtest over history (5.8) |

```
smog-facts    versioned serde types: facts, evidence, findings, verdict
smog-scan     syn + lexer --> per-item facts, AST hash, item identity
smog-ingest   parsers for clippy, nextest, lcov, cargo-mutants, SCIP
smog-judge    lenses, curves, aggregation, rules. No I/O
smog-github   check runs, artifacts, REST
smog          the binary
```

- `smog-judge` has no I/O, so the exploit suite can be plain unit tests.
- `policy.toml` selects lenses, curves and rules, and a lens is one implementation of a small trait.
- Base and head facts are both computed at judge time, because syntax facts are deterministic. No baseline file is needed for them, which removes one thing an agent could edit.
- Each tool version is pinned in the binary, with a fixture test per version, because [cargo-mutants' output](https://mutants.rs/mutants-out.html) and [rustdoc JSON](https://github.com/obi1kenobi/cargo-semver-checks) can change.

### 6.5 Tools

**Off-the-shelf products are not the gate.** [SonarQube](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/languages/rust) and [CodeScene](https://codescene.io/docs/usage/language-support.html) show no curves, ledger or item-level budgets for Rust on the pages read. CodeScene's score is its own, which could serve as a sealed second opinion. [CodeQL](https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/about-the-codeql-cli) is a possible later source for type-resolved queries.

**What feeds each lens.** Static means no PR code runs, so the judge can compute it. Executes means it runs PR code, so it belongs in the collector and is only evidence.

| Lens or check | Tool | Tier | Notes |
| --- | --- | --- | --- |
| Length, nesting, parameters, fields, methods, variants, generics, LCOM4, return points, cyclomatic | Own `syn` visitors | Static | |
| Cognitive complexity | Own visitor, or [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) | Static | |
| Comment lenses, slop check, blank lines, paragraphs | Own, over a lexer | Static | |
| Suppressions, weakened tests, changed expected values, assertion tiers | Own, comparing base and head trees | Static | |
| Gate untouched, PR size, entropy, files touched | Git diff | Static | |
| File, folder and module counts | Git tree | Static | |
| Crate dependencies, layer edges, instability, lockfile change | Parse `Cargo.toml` and `Cargo.lock` as data | Static | Not `cargo metadata` in the judge. The collector may run it as evidence |
| Project conventions | [ast-grep](https://ast-grep.github.io/reference/cli/scan.html) `scan --json` plus own rules | Static | Rules come from `smog-state` |
| Unused dependencies | [cargo-machete](https://github.com/bnjbvr/cargo-machete) | Static (assumed) | Check that it runs nothing |
| Item identity, AST hash, test churn input | Own | Static | Foundation for the ledger |
| Lints | [`cargo clippy --message-format=json`](https://doc.rust-lang.org/cargo/reference/external-tools.html) | Executes | Parse only lines starting with `{`, because proc macros can print to stdout |
| Tests, test time, uncovered lines | [`cargo llvm-cov nextest`](https://github.com/taiki-e/cargo-llvm-cov) with `--lcov` | Executes | [JUnit](https://nexte.st/docs/machine-readable/junit/) gives times and flakes |
| Doctests | Separate step | Executes | [Nextest does not run them](https://mutants.rs/nextest.html) |
| Surviving mutants | [cargo-mutants](https://mutants.rs/pr-diff.html) `--in-diff`, sharded | Executes | Section 6.8 |
| Advisories | [cargo-deny](https://github.com/EmbarkStudios/cargo-deny) `check advisories` | Reads the lockfile (assumed) | Covers cargo-audit's job, so run one |
| Dependency lenses, propagation cost, module lenses, disconnected change groups | rust-analyzer SCIP | Executes | Section 6.6 |
| Module cycles | [`cargo modules dependencies --acyclic`](https://github.com/regexident/cargo-modules), later strongly connected components over the index | Executes (assumed) | |
| Public API change | [cargo-public-api](https://github.com/cargo-public-api/cargo-public-api), [cargo-semver-checks](https://github.com/obi1kenobi/cargo-semver-checks) | Executes | Run only if the diff touches a `pub` item. The first needs nightly |
| Unreviewed lines | `git blame -w -M -C`, [`GET /commits/{sha}/pulls`](https://docs.github.com/en/rest/commits/commits), [reviews API](https://docs.github.com/en/rest/pulls/reviews) | Static, push job | Report only, so not on the PR path |
| Failed checks, review lenses | [Checks](https://docs.github.com/en/rest/checks/runs) and reviews REST | Host | Read by the judge or record job |
| Custom type-aware rules | [Dylint](https://trailofbits.com/tools/dylint/), [cargo-pup](https://github.com/DataDog/cargo-pup) | Executes, pinned nightly | Later, only for rules `syn` cannot do. cargo-pup has `restrict_imports` for layers |
| Banned named items | [Clippy `disallowed-types`, `disallowed-methods`](https://doc.rust-lang.org/clippy/lint_configuration.html) | Executes | No per-folder option seen |

**Installing and caching:**

- [`taiki-e/install-action`](https://github.com/taiki-e/install-action) installs pinned versions and verifies SHA-256.
- The `smog` binary must be fetchable without a secret, because the collector has none.
- [`Swatinem/rust-cache`](https://github.com/Swatinem/rust-cache) caches dependencies and sets `CARGO_INCREMENTAL=0`. Cargo-mutants [spends its time in incremental builds](https://mutants.rs/performance.html), so measure the mutants job with `CARGO_INCREMENTAL=1`.
- The [cache limit is 10 GB per repository](https://docs.github.com/en/actions/reference/limits).

### 6.6 Foundation choices

**Parser: `syn` for trees, a lexer for text.** [Non-doc comments are whitespace](https://doc.rust-lang.org/reference/comments.html) to `syn`, so comment lenses and paragraph length need a lexer. [`ra_ap_rustc_lexer`](https://docs.rs/ra_ap_rustc_lexer/latest/ra_ap_rustc_lexer/) is a candidate. [`ra_ap_syntax`](https://docs.rs/ra_ap_syntax/latest/ra_ap_syntax/) is the alternative, with one full-fidelity tree. Try both on one lens first. A parse failure must not pass.

**rust-code-analysis** has useful metrics, but its [newest crates.io release is from January 2023](https://crates.io/api/v1/crates/rust-code-analysis), so it may not know later syntax. Simple lenses are written in `syn`, with this tool as a cross-check.

**Index: rust-analyzer's SCIP output.**

| Option | For | Against |
| --- | --- | --- |
| **`rust-analyzer scip`**, chosen | A defined command, with a [Protobuf schema and Rust bindings](https://github.com/scip-code/scip). Links no compiler internals | Whole-workspace analysis per run, timing unknown |
| `ra_ap_*` crates | Types, trait solving | [The `ide` API is "explicitly unstable"](https://rust-analyzer.github.io/book/contributing/architecture.html) |
| Rustc driver or MIR | Exact | Pinned nightly, compiler internals |
| Own name resolution over `syn` | Static and fast | Wrong for traits, macros and re-exports |

From [the source](https://docs.rs/crate/ra_ap_rust-analyzer/latest/source/src/cli/scip.rs), version 0.0.336:

- It executes PR code, so it belongs in the collector and has the same forgery limit as tests.
- Reads and writes are not separated, so field reads and writes must come from the syntax tree at each occurrence.
- Trait calls probably resolve to the trait method, so a one-impl check needs `impl` blocks from `syn`.

If it takes too long per PR, compute the index on `main` only, and restrict PR-time findings to syntax lenses plus the changed files.

### 6.7 Where state lives

Two things decide whether a PR passes. The **policy** is the settings file: which lenses and rules apply, plus targets, limits, curves, the layer map and allowlists. The **debt ledger** records how much each merged PR changed each piece's penalty, which the rolling-window budget in 5.2 reads.

Both live in a separate private repository, `smog-state`, which the agent's App cannot access. If they sat in the product repository, an agent with write access could edit them to loosen its own gate. Keeping them apart stops that on any plan. A branch in the product repository can be reached by the agent's token. The [Actions cache](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) is not verified and gets evicted. An external database is one more service.

```
policy.toml                  human-edited; lenses, curves, limits, layer map, allowlists
sealed/                      lenses the agent never sees
ledger/<merge-sha>.json      one file per merged PR
pending/<patch-id>.json      PR-stage counts reused in the queue
reports/                     generated trend reports
```

- One file per merge SHA means no write conflicts, and rerunning `record` writes the same file.
- Syntax entries can be rebuilt from git history. Mutation and coverage counts cannot, so they are backed up with the repository.
- Humans change policy by PR in this repository. Each verdict records the policy commit.

### 6.8 Mutation testing on every PR

The factory waits for this step, on every PR, limited to the diff.

```sh
git diff "$MERGE_BASE".."$HEAD" > git.diff
cargo mutants --no-config --no-shuffle --in-diff git.diff \
  --shard "$K/$N" --baseline=skip --timeout 300 --in-place --test-tool=nextest
```

- **Tests must already pass.** With `--baseline=skip`, results are otherwise "meaningless", so this runs after the test job.
- **Shards do not coordinate.** All must [see the same diff and arguments](https://mutants.rs/shards.html), and `smog-ingest` merges each shard's `outcomes.json`.
- **Shard count comes from the mutant count.** `--list` gives the count, and a first job sets the matrix up to [256 jobs](https://docs.github.com/en/actions/reference/limits).
- **Runner limits.** [Standard runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) have 2 CPUs on private repositories and 4 on public ones. `--in-place` cannot combine with `--jobs`, so a shard handles one mutant at a time per VM.
- **Time.** [One incremental build and test run per viable mutant](https://mutants.rs/performance.html). The PR size limit is also the real limit on this job, so the two are set together.
- **Flaky tests corrupt results.** A mutant counts as [caught if any test failed](https://mutants.rs/print.html), so a flake reads as a kill.
- **Doctests.** Under nextest, behavior tested only by doctests [shows as missed](https://mutants.rs/nextest.html), which counts against the PR.
- **Exit codes.** [0, 2 and 3 are results; 1, 4, 5, 6 and 70 are failures of the run](https://mutants.rs/exit-codes.html). Counts come from `outcomes.json`.
- **Full runs** go on the nightly job, because [the diff approach can miss what a whole-tree run catches](https://mutants.rs/pr-diff.html).

### 6.9 When something fails

The judge never passes on missing data, and never charges the agent for something the PR cannot clear.

| Event | Gate result | Finding tells the agent |
| --- | --- | --- |
| Collector did not run | No check, so blocked | Nothing. The factory treats a stale missing check as an error |
| Build or test failure | Fail | The failure |
| Tool crash, or mutants exit 1, 5, 6 or 70 | Fail, labelled `tool_error`, not debt | Retry. Repeats alert a human |
| Mutants exit 4 (baseline fails) | Fail | Tests are failing |
| Evidence missing or invalid | Fail, labelled `evidence_invalid` | Alerts a human, because this may be forgery |
| File does not parse in `syn` | Fail, labelled `tool_error` | Alerts a human |
| Flaky test | Smog's nextest config sets [`retries = 2`](https://nexte.st/docs/features/retries/), and a per-test override sets `flaky-result = "fail"` for tests the PR adds or changes. Flakes go in the ledger | The new flaky test |
| Mutant timeout | Report. Not charged until noise is measured | Nothing |
| New advisory on an unchanged lockfile | PR passes, and the nightly job opens a ticket | Nothing |
| Advisory added by the PR's lockfile change | Fail | The package |

### 6.10 Output for agents and humans

**Check runs.** `smog/gate` is required, with `success` or `failure` and only blocking findings. `smog/report` is optional and [`neutral`](https://docs.github.com/en/rest/checks/runs), for report-only lenses.

[Limits](https://docs.github.com/en/rest/checks/runs): `output.summary` and `output.text` are 65,535 characters each, and annotations are 50 per request.

| Place | Content |
| --- | --- |
| `output.summary` | Count, worst findings, policy commit, in Markdown for people |
| `output.text` | One JSON block, worst first, cut off at the limit with `truncated: true` |
| Annotations | One per finding on the changed code |
| Artifact | The full `findings.json`, from the judge run |

One score tells the agent that it failed; it needs the detail to know why. Each finding gives:

```json
{
  "schema_version": 1,
  "id": "function_length:src/foo/mod.rs::parse_header",
  "head_sha": "...",
  "gate": "piece_debt",
  "path": "src/foo/mod.rs",
  "line": 120,
  "item": "parse_header",
  "lens": "function_length",
  "value": 85,
  "target": 20,
  "limit": 100,
  "penalty_before": 0.20,
  "penalty_after": 0.66
}
```

- Sort findings by penalty, worst first.
- Show findings on the changed code first. At Facebook, the same analysis had a fix rate near zero as a nightly report and over 70% on the diff.
- Every finding must be clearable. Google's bug-prediction flags were ignored because developers could not clear them.
- An agent reads this with `gh api repos/{owner}/{repo}/commits/{sha}/check-runs`. A local `smog judge` gives the same static findings before pushing. Sealed lenses are excluded.

**Code scanning is not the main channel.** [PR alerts appear only on added or edited lines](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning), and debt added to untouched code would not show. Only the top 5,000 of 25,000 results per run are kept.

**Humans.** The record job writes a Markdown trend report to `smog-state/reports/` and to the job summary. No dashboard yet.

### 6.11 Jobs outside the PR

| Trigger | Job | Does |
| --- | --- | --- |
| Push to `main` | `smog-record` | Facts delta, AST hashes for the changed files, debt, blame for changed files, PR metadata. Writes the ledger, with no PR code |
| Nightly | `smog-nightly` | Full mutation run; K test runs on one commit for flakes and noise; advisories; redundant tests; API lenses; audit rerun of a random merged PR; seeded PRs. Fills any ledger gap by comparing `main` with the ledger |
| On demand | `smog replay` | Backtest before enabling a rule |

Use the App token for REST calls, because [`GITHUB_TOKEN` gets 1,000 API requests per hour per repository](https://docs.github.com/en/actions/reference/limits).

### 6.12 Behavior to test before relying on this design

- `workflow_run` for a `pull_request` run reports the PR head as `head_sha`, and does so for merge groups too.
- An App's check run on a merge group's head SHA satisfies the queue's required check.
- A deployment-branch policy of `main` allows a `workflow_run` job and refuses a `pull_request` job, on the plan in use.
- An App without the Workflows permission cannot push workflow files.
- Code owner review works with zero required approvals.
- Annotations appear on files outside the diff.
- A merge by the queue starts the push job.
- A protected branch can require `smog/gate` from the Smog App specifically, on the plan in use. The source for this expected-source setting describes rulesets.

### 6.13 Build order

1. **Skeleton.** Two Apps, ruleset, `smog-collect`, `smog-judge`, a stub verdict. Prove with real PRs on a scratch repository that each attack in 6.1 fails, and that the behavior in 6.12 holds. This comes first because it carries the most unverified behavior and needs no lenses.
2. **Measure.** Run each tool in 6.5 on a real repository, for time, disk and determinism. Decide whether SCIP runs per PR.
3. **Scan.** Item identity, AST hash, syntax lenses, static checks, in report mode.
4. **Ledger.** `smog-state`, `record` and `replay`.
5. **Judge.** Curves, debt, budgets, exploit suite, in report mode.
6. **Evidence.** Clippy, tests and coverage, mutants.
7. **Index.** SCIP lenses.
8. **Enable.** Turn on blocking one rule at a time, after replay, starting with the hard checks.
9. **Gaming.** Seeded PRs, sealed lenses.
