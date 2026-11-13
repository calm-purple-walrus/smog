# What is good and bad: codebase, pull request, struct, function, module

## Answer

Sources agree on the direction and disagree on the numbers.

- **Codebase:** good means easy to change without new defects. Bad means problems accumulate, tests break for reasons other than bugs, and parts are tightly coupled.
- **Pull request (PR):** good means one self-contained change with its tests, leaving code health better. Bad means large, mixed-purpose, or weakening tests.
- **Struct:** good means its type protects its meaning and invariants. Bad means very large, exposing a representation it may need to change, or using `bool` and bare primitives for domain meaning.
- **Function:** good means short relative to its complexity, doing one thing, with preconditions in its types. Bad means long and deeply nested, or controlled by flag arguments.
- **Module:** good means it hides a design decision behind an interface much simpler than its implementation. Bad means a thin wrapper, leaked internals, or tight coupling.

No source I opened establishes a specific limit, such as a maximum number of lines, as correct. The limits below are policies chosen by each project.

## How to read this

Evidence labels:

- **Study:** a measurement or experiment. Most study a correlation, and most used human-written Java, C or object-oriented code.
- **Guidance:** a published standard from an organization or project.
- **Opinion:** the argument of one author.

How sources were read:

- "Read directly" means I read that passage in the PDF page.
- All other quotes came through a fetch tool that summarizes pages, so check the wording against the source before reusing it.
- Studies marked "abstract" were read only as far as their abstract.
- Claims I could not check are listed under [Not verified](#not-verified).

## Codebase

| Good | Evidence |
| --- | --- |
| Improving over time, not perfect: "there is no such thing as 'perfect' code—there is only better code" | Guidance: [Google review standard](https://google.github.io/eng-practices/review/reviewer/standard.html) |
| Components are loosely coupled, with "well-defined interfaces" | Guidance: [DORA, loosely coupled teams](https://dora.dev/capabilities/loosely-coupled-teams/). That page gives no figures |
| Tests call the system the way its users do, and "the ideal test is unchanging" unless requirements change | Guidance: [Software Engineering at Google, ch. 12](https://abseil.io/resources/swe-book/html/ch12.html) |
| Work ships in small batches: "any batch of code that takes longer than a week to complete and check is too big" | Guidance: [DORA, small batches](https://dora.dev/capabilities/working-in-small-batches/) |
| Dependencies are stable and rarely break the code | Guidance: [DORA, code maintainability](https://dora.dev/capabilities/code-maintainability/) |
| A short architecture document gives an overview, a code map, invariants and boundaries | Opinion: [matklad, ARCHITECTURE.md](https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html) |

| Bad | Evidence |
| --- | --- |
| Low code quality. In 39 proprietary codebases, low quality code had 15 times more defects, and issues took on average 124% more development time | Study, abstract: [Tornhill and Borg 2022](https://arxiv.org/abs/2203.04374). The authors' metric comes from CodeScene, the tool they used. [Inference] Correlation; it does not prove the cause |
| Code smells. Classes with more smells changed and failed more: median changes rose from 12 with no smells to 54 with three | Study, read directly: [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf), 395 releases of 30 projects |
| Smells that stay. The same paper cites Tufano et al. for "almost 80%" of smells never being removed, and for most code being smelly from creation | Palomba et al. describing another study, read directly. I did not open the original |
| Brittle tests, which fail on changes that are not bugs | Guidance: [Software Engineering at Google, ch. 12](https://abseil.io/resources/swe-book/html/ch12.html) |
| Tight coupling. Tightly coupled components are "harder to kill", "harder to maintain" and "harder to augment" | Study of one commercial product over six releases, read directly: [MacCormack et al. 2007](https://swizec.com/pdfs/impact-of-modularity.pdf) (working paper, annotated copy) |
| High churn relative to size. Relative churn predicted defect density well; absolute churn did not | Study, abstract: [Nagappan and Ball 2005](https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/), on Windows Server 2003 |

Disputed or weak for codebases:

- **Duplication.** DORA treats the share of duplicate code as worth measuring ([code maintainability](https://dora.dev/capabilities/code-maintainability/)). Sandi Metz argues "duplication is far cheaper than the wrong abstraction" ([The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)).
- **Coverage.** A review of Inozemtseva and Holmes reports that "the correlation between coverage and effectiveness drops when suite size is controlled for" ([review](https://neverworkintheory.org/2021/09/24/coverage-is-not-strongly-correlated-with-test-suite-effectiveness.html)). I read the review, not the paper.
- **Mutation score.** Just et al. found "a statistically significant correlation between mutant detection and real fault detection" ([abstract](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html)). That is stronger support than coverage has, but not proof that a high score means good tests.

Agent-written code:

- 33,596 agent PRs compared with 6,618 human PRs: agent-added functions and classes were removed sooner, "median time to removal 3 vs. 34 days" ([Pham and Ghaleb, abstract](https://arxiv.org/abs/2601.17627)).
- In 1,210 merged agent bug-fix PRs, "merge success does not reliably reflect post-merge code quality" ([Cynthia et al., abstract](https://arxiv.org/abs/2601.20109)).
- DORA 2024: rising AI adoption came with an estimated 1.5% drop in delivery throughput and a 7.2% drop in stability. DORA names small batches and robust testing as basics that still apply ([Google Cloud summary](https://cloud.google.com/blog/products/devops-sre/announcing-the-2024-dora-report)). This is an association from a survey-based report; the page does not attribute the drop to a cause.

## Pull request

| Good | Evidence |
| --- | --- |
| "One self-contained change" that "addresses just one thing" | Guidance: [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) |
| Small: "100 lines is usually a reasonable size for a CL, and 1000 lines is usually too large" | Same. Google leaves the final call to the reviewer |
| Includes tests: "CLs should include related test code" | Same |
| Refactoring is separate from features and bug fixes. Small cleanups, such as a variable rename, may stay in | Same |
| "Definitely improves the overall code health", even if not perfect | Guidance: [Google review standard](https://google.github.io/eng-practices/review/reviewer/standard.html) |
| Solves the problem known now | Guidance: [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| The description says what changed and why | Guidance: [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) |

| Bad | Evidence |
| --- | --- |
| Degrades code health | Guidance: [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| Spread out: "A 200-line change in one file might be okay, but spread across 50 files it would usually be too large" | Guidance: [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) |
| Large. Each extra file lowered the odds of any review comment by about 8.7% | Study, abstract: [Rahman et al. 2026](https://arxiv.org/abs/2609.22610), preprint, 330,343 PRs |
| Large. Most predictive power in change-level defect models comes from change size | Study, read directly: [Morita et al. 2024](https://posl.ait.kyushu-u.ac.jp/~kamei/publications/Morita_SANER2024.pdf) |
| Tangled. 7% to 20% of bug fixes held several tangled changes, and this mislabeled at least 16.6% of source files in defect data | Study, abstract: [Herzig et al.](https://www.microsoft.com/en-us/research/publication/the-impact-of-tangled-code-changes-on-defect-prediction-models/), five Java projects. This shows harm to defect data, not to the code |
| Deletes or edits a failing test instead of fixing the bug | Study, abstract: [ImpossibleBench](https://arxiv.org/abs/2510.20270) describes this as an agent risk and measures test exploitation |
| Over-engineered | Guidance: [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| Vague description, such as "Fix bug" | Guidance: [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) |

Disputed or weak for PRs:

- **Smaller is not always better.** Rahman et al. report that "pull requests of about ten files have the lowest risk, while very small and very large ones have elevated rates" ([abstract](https://arxiv.org/abs/2609.22610)). This is one preprint.
- **Size may partly be an artifact.** Morita et al. call the size finding "somewhat superficial", because larger changes create more "surface area" for later fixes to implicate them. They add that a one-line change can also cause defects ([read directly](https://posl.ait.kyushu-u.ac.jp/~kamei/publications/Morita_SANER2024.pdf)).
- **Splitting has a narrower effect than often claimed.** In a controlled experiment with 28 developers, decomposition "impacts neither understanding the change rationale nor the number of found defects", but it "leads to fewer wrongly reported issues" ([di Biase et al., abstract](https://arxiv.org/abs/1805.10978)).
- **Raw issue counts mostly reflect size.** Differences between agents "largely disappear after normalizing by code churn" ([Cynthia et al., abstract](https://arxiv.org/abs/2601.20109)).

Size exceptions in Google's guidance: deleting a whole file counts as about one line, and output from a fully trusted refactoring tool may be large ([small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html)).

## Struct

Most research studies classes, not Rust structs. [Inference] Findings about size and coupling may carry over, but those about inheritance do not. I found no empirical study of Rust structs; my searches did not target one.

| Good | Evidence |
| --- | --- |
| Private fields unless it is a passive data record: a public field "pins down a representation choice" | Guidance: [Rust API Guidelines, C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/print.html) |
| Newtypes separate meanings, such as miles and kilometers | Guidance: same, C-NEWTYPE |
| Domain types instead of `bool` or `Option` arguments: "Use a deliberate type" | Guidance: same, C-CUSTOM-TYPE |
| Invalid states cannot be represented: "makes illegal states unrepresentable" | Opinion: [Alexis King, Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) |
| Validation result is kept in the type, not discarded | Same |
| A builder for values with many inputs or optional settings | Guidance: [Rust API Guidelines, C-BUILDER](https://rust-lang.github.io/api-guidelines/print.html) |
| No unnecessary trait bounds on the struct definition | Guidance: same, C-STRUCT-BOUNDS |
| In libraries, common traits implemented, because other crates cannot add them | Guidance: same, C-COMMON-TRAITS |

| Bad | Evidence |
| --- | --- |
| God class: while classes had this smell, their median changes were 46, against 12 while they did not | Study, read directly: [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf) |
| Complex class: median changes 55 with the smell, against 34 without | Same |
| Feature envy (a method too tied to another type): fault-proneness rose by a factor of 8 | Same. Change-proneness did not rise for this smell |
| Too many `bool` fields: Clippy's `max-struct-bools` defaults to 3 | Guidance: [Clippy configuration](https://doc.rust-lang.org/clippy/lint_configuration.html). A limit, not a finding |
| Primitive obsession, data clumps, large class | Catalog only: [Refactoring Guru smell list](https://refactoring.guru/refactoring/smells). I found no measurement of these as separate problems in what I read |

Disputed or weak for structs:

- **Public fields.** The Rust API Guidelines prefer private fields for public APIs. rust-analyzer says "If a field can have any value without breaking invariants, make the field public", because it has no public API ([style guide](https://raw.githubusercontent.com/rust-lang/rust-analyzer/master/docs/book/src/contributing/style.md)). [Inference] The rule depends on whether the type has an invariant and outside users. Palomba et al. also found no rise in change-proneness for *Class Data Should Be Private* (read directly).
- **Size against other metrics.** Tahir et al. found that class size consistently mediated only the link between Coupling Between Objects and defects, out of seven metrics ([abstract](https://arxiv.org/abs/2106.04687)). They recommend checking each dataset rather than assuming.
- **Data classes.** The smell catalog lists Data Class as dispensable. The Rust API Guidelines accept passive data structures with public fields. I read no direct evidence either way.

## Function

| Good | Evidence |
| --- | --- |
| "Short and sweet, and do just one thing" | Guidance: [Linux kernel style](https://www.kernel.org/doc/html/latest/process/coding-style.html) |
| Length falls as complexity rises: maximum length is "inversely proportional to the complexity and indentation level" | Same. A long, simple case statement is acceptable |
| Preconditions are in the types, supplied by the caller | Guidance: [rust-analyzer style](https://raw.githubusercontent.com/rust-lang/rust-analyzer/master/docs/book/src/contributing/style.md); [Rust API Guidelines, C-VALIDATE](https://rust-lang.github.io/api-guidelines/print.html) |
| Separate functions rather than a flag that switches between two cases | Guidance: rust-analyzer style, above |
| Control flow is visible at the caller: "push `if`s up and `for`s down", with leaf functions pure | Guidance: [TigerBeetle style](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md). rust-analyzer agrees on control flow |
| Early returns reduce what a reader must hold in mind | Guidance: rust-analyzer style, above |
| Understood quickly by readers: "too complex" usually means it "can't be understood quickly" | Guidance: [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) |
| Comments explain why the code exists, or what it does rather than how | Guidance: [Google](https://google.github.io/eng-practices/review/reviewer/looking-for.html), [Linux kernel](https://www.kernel.org/doc/html/latest/process/coding-style.html). The two emphasize different things |

| Bad | Evidence |
| --- | --- |
| Long method: median change-proneness was higher while a class had this smell | Study, read directly: Figure 8 of [Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf). I read the figure and did not take an exact number from it |
| Too many local variables: "They shouldn't exceed 5-10" | Guidance: [Linux kernel style](https://www.kernel.org/doc/html/latest/process/coding-style.html) |
| Many optional or boolean parameters | Guidance: [rust-analyzer style](https://raw.githubusercontent.com/rust-lang/rust-analyzer/master/docs/book/src/contributing/style.md) |
| Scattered input checks during processing ("shotgun parsing"), which can leave work half done on bad data | Opinion: [Alexis King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) |

Published limits differ, and all are policies:

| Source | Limit |
| --- | --- |
| [TigerBeetle](https://raw.githubusercontent.com/tigerbeetle/tigerbeetle/main/docs/TIGER_STYLE.md) | Hard limit of 70 lines. At least two assertions per function on average |
| [Clippy defaults](https://doc.rust-lang.org/clippy/lint_configuration.html) | 100 lines; 7 arguments; 3 `bool` parameters; cognitive complexity 25 |
| [Linux kernel](https://www.kernel.org/doc/html/latest/process/coding-style.html) | No line limit; 5 to 10 local variables |

Disputed or weak for functions:

- **How far to split.** Ousterhout argues over-splitting creates "shallow" interfaces, and that "Entangled methods can usually be improved by combining them". Martin says "if I must err, I'd rather err on the side of decomposition" ([their discussion](https://github.com/johnousterhout/aposd-vs-clean-code)).
- **Complexity against size.** Critics argue that no metric except size is valid, as [Chowdhury et al.](https://www.cs.ubc.ca/~rtholmes/papers/emse_2022_chowdhury_preprint.pdf) summarize (read directly). Landman et al. studied 17.6 million Java methods and 6.3 million C functions (counts from a search result, not the page I opened) and conclude the correlation "is not strong enough to conclude that CC is redundant with SLOC" ([authors' summary](https://www.rascal-mpl.org/blog/2016/01/01/empirical-analysis-of-the-relationship-between-CC-and-SLOC/)).
- **Do complexity metrics add anything?** Chowdhury et al., on about 730,000 Java methods, conclude that metrics can help estimate maintenance effort "even when the confounding influence of size is eliminated". They also show that dividing a metric by size does not remove the influence of size, and that results depend on context: nesting depth predicts less well for large methods than for small ones ([read directly, pages 1 to 3](https://www.cs.ubc.ca/~rtholmes/papers/emse_2022_chowdhury_preprint.pdf)).
- **Cognitive complexity.** Clippy keeps its lint in the `restriction` group: "We used to think it measured how hard a method is to understand" ([Clippy lint list](https://clippy.rust-lang.org/master/index.html)).
- **Comments.** Ousterhout: "missing comments are a much greater cause of lost productivity than erroneous or unhelpful comments". Martin: "In every case a comment is a failure of our ability to use our languages to express our intent", though he says he objects to gratuitous comments, not all comments ([their discussion](https://github.com/johnousterhout/aposd-vs-clean-code)).

## Module

| Good | Evidence |
| --- | --- |
| Hides a difficult or likely-to-change design decision. "Each module is then designed to hide such a decision from the others" | Argument from worked examples, read directly: [Parnas 1972](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf) |
| Much functionality behind a simple interface: "maximize functionality/(interface complexity)" | Opinion: [Ousterhout, lecture notes](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) |
| The implementation can change without affecting other modules | Same |
| Groups related functionality and keeps implementation details private | Guidance: [The Rust Book, ch. 7](https://doc.rust-lang.org/book/ch07-00-managing-growing-projects-with-packages-crates-and-modules.html) |
| Dependencies form a hierarchy, so upper levels can be removed and lower levels reused | Argument, read directly: [Parnas 1972](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf). Parnas calls hierarchy and clean decomposition "independent" properties |
| Dependencies point toward more stable modules, measured by instability `Ce / (Ce + Ca)` | Definition only: [Wikipedia, package metrics](https://en.wikipedia.org/wiki/Software_package_metrics). I did not verify empirical support |

| Bad | Evidence |
| --- | --- |
| Modules that follow processing steps: "it is almost always incorrect to begin the decomposition" from a flowchart | Argument, read directly: [Parnas 1972](https://wstomv.win.tue.nl/edu/2ip30/references/criteria_for_modularization.pdf) |
| Thin modules that hide little, and "too many classes" | Opinion: [Ousterhout, lecture notes](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) |
| Tight coupling, as under Codebase | Study: [MacCormack et al. 2007](https://swizec.com/pdfs/impact-of-modularity.pdf). The authors note that "modularity is a property of individual components, not systems" |
| Wide observable behavior. "All observable behaviors of your system will be depended on by somebody" | Observation by a practitioner: [Hyrum's Law](https://www.hyrumslaw.com/) |
| A casual `pub use`, which "is a very simple way to break encapsulation" | Guidance: [rust-analyzer style](https://raw.githubusercontent.com/rust-lang/rust-analyzer/master/docs/book/src/contributing/style.md) |
| Small helper crates that add compile time and things that can break | Same. This is one project's rule |
| A change in one place forcing many changes elsewhere (shotgun surgery, divergent change) | Catalog: [Refactoring Guru](https://refactoring.guru/refactoring/smells) |

Disputed or weak for modules:

- MacCormack et al. say empirical work linking modularity and evolution "has had limited success", partly because modularity is hard to measure repeatably ([read directly](https://swizec.com/pdfs/impact-of-modularity.pdf)).
- The strongest module sources are design arguments, not measurements. I found no study showing that a given module size or interface size is best.

## What most sources agree on

[Inference, from the above.]

1. Bad traits come in groups. A class with three smells changed and failed far more than one with one smell ([Palomba et al.](https://fpalomba.github.io/pdf/Journals/J9.pdf)).
2. Size is the most consistent warning sign, but it is not the whole explanation.
3. Limits are policy. Kernel, Clippy and TigerBeetle set different limits or none.
4. Coupling and hidden design decisions are widely valued, but harder to measure than size.
5. Passing CI or being merged does not show quality ([Cynthia et al.](https://arxiv.org/abs/2601.20109)).

## Where this differs from the measurement model

[Inference.] These compare the findings with `docs/design/measurement-model.md`.

| Model says | Finding |
| --- | --- |
| Section 2 treats struct and function together as "piece of code" | Struct guidance is mainly about representation and invariants, not size. Public fields and `bool` counts could be read from syntax, but they need a check on whether an invariant exists |
| 3.0: length and complexity "mostly measure size" | Contested: Landman et al. and Chowdhury et al. find complexity metrics are not redundant with size |
| 3.2 lists cognitive complexity | Clippy keeps its cognitive complexity lint in `restriction` because it doubts the lint's meaning. Clippy's implementation may differ from rust-code-analysis; I did not compare them |
| 3.8: raw code churn is the "best defect predictor" | Nagappan and Ball found relative churn predicts defect density, and absolute churn does not. They studied one product, and defect density rather than defect count |
| Section 2: a good PR is "small" | Rahman et al. report higher risk for very small PRs as well. One preprint |
| Goal: no composite score has good evidence of predicting defects or cost | Tornhill and Borg are a possible counterexample: a composite tied to defects and time. It is correlational and I read only the abstract. A search summary says the authors work with the tool's vendor; I did not confirm this |
| Section 2: comments explain only what the code cannot | Ousterhout's position is broader: comments are required for abstraction. A penalty on comment density takes one side of that dispute |

## Not verified

- **SmartBear/Cisco 200 to 400 line review limits:** seen only in search summaries.
- **SIG thresholds (15 lines per unit, 4 parameters):** the chapter returned HTTP 403 and search results did not confirm them.
- **Propagation cost formula:** not read. I read only the abstract of MacCormack et al. 2007.
- **Google 90% of reviews under 10 files, and Sadowski et al. details:** a blog claim. The abstract I opened does not mention size.
- **ImpossibleBench rates, such as 93% for GPT-5:** seen only in search summaries. The abstract gives no rates.
- **DORA 2025 PR-size figures (for example, 154% larger PRs):** seen only on secondary sites.
- **Conflict on God Classes:** a search summary says a study of three systems found Brain and God Classes less change- and fault-prone after controlling for size. I did not open it. This could weaken the Palomba finding. I also did not see whether Palomba et al. control for size in the pages I read.
- **Empirical support for Martin's instability and distance metrics:** a University of Waterloo thesis looks relevant, but I did not open it.
- **Evidence on Rust:** I found no study of these questions on Rust code, and did not search specifically for one.

## Sources that failed to open

- [PeerJ version of di Biase et al.](https://peerj.com/articles/cs-193): HTTP 403. I used the arXiv abstract.
- [Tahir et al. PDF](https://www.massey.ac.nz/~wwseag/files/EMSE21_sizeMatter_Tahir.pdf): HTTP 504. I used the arXiv abstract.
- [Nagappan and Ball PDF](https://www.st.cs.uni-saarland.de/edu/recommendation-systems/papers/ICSE05Churn.pdf): connection refused. I used the Microsoft Research abstract.
- [Sturtevant slides on technical debt](https://incose.org/docs/default-source/enchantment/130612_dansturtevant_techdebtlgsystems.pdf?sfvrsn=2): HTTP 403. Not used.
- [MacCormack et al. Harvard copy](https://dash.harvard.edu/bitstream/handle/1/34403525/maccormack,baldwin,rusnak_exploring-the-duality.pdf): HTTP 429. Not used; it is a different paper from the one cited above.
