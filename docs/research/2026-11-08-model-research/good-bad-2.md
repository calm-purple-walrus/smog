# What is good and bad: codebase, PR, struct, function, module

Researched 2026-11-08.

## Answer

Sources broadly agree on these points:

- **Codebase:** it gets healthier over time, tests catch bugs, and parts can change independently. It is bad when dependencies tangle and low-quality code builds up.
- **PR:** one self-contained change, about 100 to 200 lines, with tests and a stated reason. It is bad when it is large, mixes purposes or touches unrelated code.
- **Struct:** its types rule out invalid states, and it hides fields that carry invariants. It is bad when it relies on bool flags and primitives, or does too many jobs.
- **Function:** it can be understood quickly and used without reading its body, with shallow nesting and few parameters. It is bad when it is long, deeply nested or full of flags.
- **Module:** it hides a design decision behind a small interface. It is bad when it follows processing steps, has cycles, or has an interface that keeps changing.

Three limits apply:

- **Most of this is expert opinion.** Studies mostly show associations, in Java or C, on human-written code. I found no study of these questions on Rust code.
- **No metric was shown to measure understandability.** [Scalabrino et al.](https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf) tested 121 metrics against 444 human evaluations: "none of the 121 experimented metrics is able to capture code understandability".
- **Experts disagree on two points:** how short a function should be, and how much to comment.

## How to read this

- **Opinion:** a guideline or an expert's view. It has no measured effect behind it.
- **Tool default:** a value that a tool ships with. It is not evidence that the value is right.
- **Association:** a study that links a property to an outcome. It does not show cause.

Quotes from web pages came through a fetch tool that summarizes pages. I did not compare them with the original text. I read the first pages of these PDFs directly: Scalabrino, Soh, Zeng, Kudrjavets, Shimagaki and Radjenović. Section "Not verified" lists what I could not open.

## Codebase

### Good

| Property | Source | Strength |
| --- | --- | --- |
| Health improves over time. Perfection is not the standard: "there is no such thing as "perfect" code—there is only better code" | [Google, standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html) | Opinion |
| No more code than needed: "code itself is a liability" | [Software Engineering at Google, ch. 9](https://abseil.io/resources/swe-book/html/ch09.html) | Opinion |
| Parts can be tested and deployed without coordinating with other parts | [DORA, loosely coupled teams](https://dora.dev/capabilities/loosely-coupled-teams/) | DORA expects deployment frequency to rise as coupling falls. I saw no statistics on this page |
| Tests detect real faults. Mutant detection correlates with real fault detection, independently of coverage | [Just et al. 2014, abstract](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html) | Association, 357 real faults |
| Coverage is treated as a weak signal: it is "a poor predictor" of test effectiveness once suite size is controlled | [Wilson on Inozemtseva and Holmes](https://neverworkintheory.org/2021/09/24/coverage-is-not-strongly-correlated-with-test-suite-effectiveness.html) | Association, read through a summary |
| Tests cover observable behavior, so agents can refactor with little supervision | [Microsoft Rust Guidelines, M-DESIGN-FOR-AI](https://microsoft.github.io/rust-guidelines/guidelines/ai/) | Opinion |
| A flat crate layout for 10,000 to 1,000,000 lines | [matklad, Large Rust Workspaces](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) | Opinion |
| Few external dependencies: "very conservative" use of crates.io, partly to keep compile times low | [rust-analyzer style guide](https://rust-analyzer.github.io/book/contributing/style.html) | One project's opinion |

### Bad

| Property | Source | Strength |
| --- | --- | --- |
| Low-quality code. "Alert" code had 15 times more defects than "Healthy" code, and issues took 124% longer | [Tornhill and Borg 2022](https://ar5iv.labs.arxiv.org/html/2203.04374) | Association, 39 codebases. Uses a proprietary metric from the first author's company. The authors raise reverse causation and confounders |
| Architecture anti-patterns: unstable interfaces, modularity violations, unhealthy inheritance, crossings, cliques and package cycles. Files in more anti-patterns had more bugs and changes | [Wilson on Mo et al.](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html) | Association, 19 projects, read through a summary |
| Central position in the dependency graph. Network measures had about 10 points higher recall than complexity metrics | [Zimmermann and Nagappan 2008](https://www.microsoft.com/en-us/research/publication/predicting-defects-using-network-analysis-on-dependency-graphs/) | Association, Windows Server 2003 |
| Rising warnings and complexity after adopting an AI tool: "a substantial and persistent increase" | [He et al., Speed at the Cost of Quality](https://arxiv.org/abs/2511.04427) | Difference-in-differences against matched controls |
| Poorly reviewed code | [McIntosh et al. 2014](https://rebels.cs.uwaterloo.ca/confpaper/2014/05/30/the-impact-of-code-review-coverage-and-code-review-participation-on-software-quality.html) | Mixed. Linked to defects in Qt, VTK and ITK, but [not at Sony Mobile](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf) |

### Conflict: which metrics matter

- [Radjenović et al. 2013](https://gup.ub.gu.se/file/127150) reviewed 106 papers. Object-oriented and process metrics did better than size and complexity metrics, and process metrics seemed better than static code metrics for post-release faults.
- [El Emam et al. 2001](https://neverworkintheory.org/2011/07/07/the-confounding-effect-of-class-size-on-the-validity-of-object-oriented-metrics.html), as summarized by Wilson, found that class size "accounted for all of the significant variation". Size may therefore explain part of the object-oriented result.

## Pull request

### Good

| Property | Source | Strength |
| --- | --- | --- |
| "one self-contained change" | [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Opinion |
| About 100 lines is usually reasonable and 1000 is usually too large | Same | Opinion |
| "limited to about 200 lines of code" | [Software Engineering at Google, ch. 9](https://abseil.io/resources/swe-book/html/ch09.html) | Opinion |
| Few files: 200 lines "spread across 50 files" would usually be too large | [Google, small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) | Opinion |
| Definitely improves code health, even if imperfect | [Google, standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html) | Opinion |
| Good design, working behavior, and tests that are "correct, sensible, and useful" | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Opinion |
| Solves today's problem, not a future one | Same | Opinion |
| The description says what changed, why, and what the shortcomings are | [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) | Opinion |
| Small batches: "predicts software delivery performance" | [DORA, small batches](https://dora.dev/capabilities/working-in-small-batches/) | DORA claim; this page gives no statistics |

Google accepts two exceptions to the size limit: [deleting a whole file, and a large change from a fully trusted refactoring tool](https://google.github.io/eng-practices/review/developer/small-cls.html).

### Bad

| Property | Source | Strength |
| --- | --- | --- |
| Many added lines. The added-line count outperformed other traditional features in defect prediction, and a model using it alone beat two deep learning models | [Zeng et al. 2021](https://zhangyuqun.github.io/publications/issta2021.pdf) | Association, 310,370 changes, mostly human-era data |
| Tangled purposes. 7% to 20% of bug fixes mix several changes | [Herzig et al.](https://www.microsoft.com/en-us/research/publication/the-impact-of-tangled-code-changes-on-defect-prediction-models/) | Association. This study shows tangling corrupts defect data, not that tangling causes defects |
| Failing CI, which was the strongest quantitative signal. Unmerged agent PRs also changed more lines and files | [Ehsani et al. 2026](https://www.alphaxiv.org/abs/2601.15195.md) | Association, 33,596 agent PRs. The outcome is merging, not defects |
| Duplicates of other work: 23% of the rejected PRs sampled | Same | Manual labeling of 600 rejected PRs |
| Touching unrelated code and causing breakages; verbose code; code that does not follow standards | [METR 2026](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/) | 296 agent PRs reviewed by 4 maintainers, under unrealistic review conditions |
| Overengineering and side effects. These were the top cause of reverted agent commits (22.33%), with incorrect behavior close behind (22.13%). Agents "struggle primarily with scope management and contextual understanding" | [Oukay et al. 2026](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/) | Manual analysis of 500 reverting commits. 2.66% of agent PRs contained a revert |
| A vague description, such as "Fix bug" | [Google, CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) | Opinion |

Passing tests does not make a PR good. In the METR study, maintainers would have merged only about half of the agent PRs that [passed the automated grader](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/). Human baseline patches were merged only about 68% of the time, so maintainer judgment is noisy too.

### Conflict: does small mean fast?

Google says small changes are [reviewed more quickly](https://google.github.io/eng-practices/review/developer/small-cls.html). [Kudrjavets et al. 2022](https://arxiv.org/pdf/2203.05045) studied 845,316 pull requests and found that size and composition "do not relate to time-to-merge". That study measures speed only. It does not address defects or review quality, so the case for small PRs rests on risk rather than speed.

## Struct

I found no study of Rust structs. The empirical results below are for Java classes, and applying them to Rust is my inference. The Rust sources are guidelines.

### Good

| Property | Source | Strength |
| --- | --- | --- |
| Invalid states cannot be expressed in the type | [Effective Rust, item 1](https://effective-rust.com/use-types.html); [King, Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) | Opinion |
| One source of truth for each fact | [King](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) | Opinion |
| Enums or custom types instead of `bool` and `Option` to carry meaning | [Rust API Guidelines, C-CUSTOM-TYPE](https://rust-lang.github.io/api-guidelines/type-safety.html) | Opinion |
| Newtypes that separate different meanings of one underlying type | [C-NEWTYPE](https://rust-lang.github.io/api-guidelines/type-safety.html); [Microsoft, M-DESIGN-FOR-AI](https://microsoft.github.io/rust-guidelines/guidelines/ai/) | Opinion |
| Private fields, except on plain passive data. "Making a field public is a strong commitment" | [C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/future-proofing.html) | Opinion |
| Public fields when any value is valid; private fields with a getter and no setter when an invariant exists | [rust-analyzer style guide](https://rust-analyzer.github.io/book/contributing/style.html) | One project's opinion |
| A separate builder type for incremental configuration | [C-BUILDER](https://rust-lang.github.io/api-guidelines/type-safety.html) | Opinion |

### Bad

| Property | Source | Strength |
| --- | --- | --- |
| Many bool fields. Clippy's limit is 3 | [Clippy configuration](https://doc.rust-lang.org/clippy/lint_configuration.html) | Tool default |
| A bool plus a comment stating a rule that the type could enforce | [Effective Rust, item 1](https://effective-rust.com/use-types.html) | Opinion |
| A public field or exposed detail that later has to change, because "all observable behaviors of your system will be depended on by somebody" | [Hyrum's Law](https://www.hyrumslaw.com/) | Observation by a practitioner |
| Too many responsibilities (God Class). This raised editing, navigating and reading effort | [Soh et al. 2016](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf) | Experiment, 6 developers, Java |
| Data Clumps. These raised editing effort | Same | Same |
| Smelly classes in general, which had higher change- and fault-proneness | [Palomba et al. 2018](https://research.tudelft.nl/en/publications/on-the-diffuseness-and-the-impact-on-maintainability-of-code-smel) | Association, 30 projects. The abstract does not show that removing smells helps |

### Conflict: are data-only structs bad?

- [Fowler](https://martinfowler.com/bliki/CodeSmell.html) calls "classes with all data and no behavior" a smell, but only as a prompt to look further: smells are "often an indicator of a problem rather than the problem themselves".
- The Rust sources accept passive data with public fields. See [C-STRUCT-PRIVATE](https://rust-lang.github.io/api-guidelines/future-proofing.html) and [rust-analyzer](https://rust-analyzer.github.io/book/contributing/style.html).

### Conflict: do smells matter beyond size?

- [Sjøberg et al.](https://ir.cwi.nl/pub/25393/Soh-SANER16_Smells-Effort.pdf), as described by Soh et al., found that no smell remained a significant driver of effort after adjusting for file size and changes.
- Soh et al. reanalyzed the same data by activity. Smells outweighed file size for editing and navigating, and file size outweighed smells for reading and searching. Both studies use the same 6 developers, so neither settles the question.

## Function

### Good

| Property | Source | Strength |
| --- | --- | --- |
| Quick to understand. Too complex means "can't be understood quickly by code readers" | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Opinion |
| Usable without reading the body: "It should be possible to use a method without reading its code" | [Ousterhout, in aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Short and single-purpose: one or two screens of 80x24 text | [Linux kernel coding style](https://docs.kernel.org/process/coding-style.html) | Opinion |
| Under 24 lines, in Java | [Chowdhury et al. 2022](https://arxiv.org/abs/2205.01842) | Association, about 785,000 methods. Java only |
| Allowed length falls as complexity and indentation rise | [Linux kernel coding style](https://docs.kernel.org/process/coding-style.html) | Opinion |
| Preconditions expressed in types, early returns, and control flow pushed to the caller | [rust-analyzer style guide](https://rust-analyzer.github.io/book/contributing/style.html) | One project's opinion |
| A name "long enough to fully communicate what the item is or does" | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Opinion |

### Bad

| Property | Source | Strength |
| --- | --- | --- |
| Over 100 lines | [Clippy configuration](https://doc.rust-lang.org/clippy/lint_configuration.html) | Tool default |
| Over 7 arguments | Same | Tool default |
| Over 3 bool parameters | Same | Tool default |
| Many optional or boolean parameters. rust-analyzer suggests a `Config` struct | [rust-analyzer style guide](https://rust-analyzer.github.io/book/contributing/style.html) | One project's opinion |
| More than 3 levels of indentation, or more than 5 to 10 local variables | [Linux kernel coding style](https://docs.kernel.org/process/coding-style.html) | Opinion |
| Fragments that must be read together. "Entangled methods are hard to read" | [Ousterhout, in aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Comments that narrate what the code is doing | [Google, what to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html) | Opinion |

A long function is not automatically bad: ["Some long methods are just fine"](https://martinfowler.com/bliki/CodeSmell.html).

### Conflict: how short?

- **Martin:** ["if I must err, I'd rather err on the side of decomposition."](https://github.com/johnousterhout/aposd-vs-clean-code)
- **Ousterhout:** extra methods don't reduce what you must know: ["It just spreads it out"](https://github.com/johnousterhout/aposd-vs-clean-code).
- **Their summary:** ["we disagree on the relative weighting of those two values."](https://github.com/johnousterhout/aposd-vs-clean-code) Those values are decomposition and avoiding entanglement.
- **Evidence:** [Chowdhury et al.](https://arxiv.org/abs/2205.01842) support decomposition, reporting that it "decreases overall maintenance efforts". This is one Java study, and I read only the abstract.

### Conflict: what does a complexity number mean?

- **Cyclomatic complexity:** [Landman et al. 2016](https://ir.cwi.nl/pub/23938/) studied 17.6 million Java methods and 6.3 million C functions. Correlation with lines was "only moderate", so they conclude it is not redundant with lines. Aggregation raised the correlation, which explains earlier reports of a strong link.
- **Size as a proxy:** [Chowdhury et al.](https://arxiv.org/abs/2205.01842) say "size correlates with many other common metrics".
- **Cognitive complexity:** Clippy's documentation says ["We used to think it measured how hard a method is to understand."](https://clippy.rust-lang.org/master/index.html) The lint is left in `restriction` "so as to not mislead users into using this lint as a measurement tool".

### Conflict: comments

- **Google:** comments should [explain why, not what the code is doing](https://google.github.io/eng-practices/review/reviewer/looking-for.html).
- **Linux kernel:** comments should [tell what the code does, not how](https://docs.kernel.org/process/coding-style.html). It puts them at the head of the function.
- **Ousterhout:** comments are ["crucially important"](https://github.com/johnousterhout/aposd-vs-clean-code), and he believes interfaces cannot be defined without many of them.
- **Martin:** ["In every case a comment is a failure of our ability to use our languages to express our intent."](https://github.com/johnousterhout/aposd-vs-clean-code) He also says he is hostile only to gratuitous comments.
- **Microsoft:** for agents, ["Agents love good detailed docs."](https://microsoft.github.io/rust-guidelines/guidelines/ai/)

My reading: Google and the kernel guide oppose comments that narrate the implementation, and Martin opposes gratuitous ones. Ousterhout, the kernel guide and Microsoft support documenting what a function or interface does. The real dispute is whether comments are a failure at all.

## Module

### Good

| Property | Source | Strength |
| --- | --- | --- |
| Hides a decision. Start from "difficult design decisions or design decisions which are likely to change", then "hide such a decision from the others" | [Parnas 1972](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html) | Design argument from a worked example |
| Can be changed and studied alone: "drastic changes to one module without a need to change others" | Same | Same |
| Deep, the opposite of the shallow interface listed under "Bad". The joint document applies this to methods; applying it to modules follows the title of his book chapter ["General-Purpose Modules are Deeper"](https://web.stanford.edu/~ouster/cgi-bin/aposd.php) | [Ousterhout, in aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Groups related functionality and separates distinct features | [The Rust Book, ch. 7](https://doc.rust-lang.org/book/ch07-00-managing-growing-projects-with-packages-crates-and-modules.html) | Opinion |
| Minimal visibility. Making an item public is hard to undo | [Effective Rust, item 22](https://effective-rust.com/visibility.html) | Opinion |
| One public path per item | [Microsoft, M-SINGLE-ITEM-PATH](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Opinion |
| A separate crate for anything usable on its own | [Microsoft, M-SMALLER-CRATES](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Opinion |
| `std` types in public APIs where possible, rather than types from other crates | [Microsoft, M-DONT-LEAK-TYPES](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Opinion |

### Bad

| Property | Source | Strength |
| --- | --- | --- |
| Modules that follow processing steps: "almost always incorrect to begin the decomposition" from a flowchart | [Parnas 1972](https://www.cs.lafayette.edu/~gexia/cs301/resources/parnas.html) | Design argument |
| Shallow interfaces, which "don't help much in terms of reducing what the programmer needs to know" | [Ousterhout, in aposd-vs-clean-code](https://github.com/johnousterhout/aposd-vs-clean-code) | Opinion |
| Unstable interfaces and crossings (high fan-in and high fan-out), which "contribute the most by far" | [Wilson on Mo et al.](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html) | Association, 19 projects, read through a summary |
| Cliques and package cycles | Same | Same |
| Catch-all folders, such as `utils` | [matklad](https://matklad.github.io/2021/08/22/large-rust-workspaces.html) | Opinion, about crate folders |
| Re-exporting items from other crates | [Microsoft, M-FOREIGN-REEXPORTS](https://microsoft.github.io/rust-guidelines/agents/all.txt) | Opinion |

## Where this differs from the measurement model

These are my inferences from the sources above. No source addresses the design. The statements come from its sections 2 and 3.

| Design statement | What the sources add |
| --- | --- |
| Good pieces are "small" | How small is disputed. Entanglement is the named cost of going too far, and nothing in the good and bad table covers it |
| Length and complexity "mostly measure size" | This holds better for aggregated code than for single functions, per [Landman et al.](https://ir.cwi.nl/pub/23938/) |
| Cognitive complexity is a lens | Clippy's documentation [warns against using it as a measurement](https://clippy.rust-lang.org/master/index.html) |
| Comments "explain only what the code cannot" | [Ousterhout](https://github.com/johnousterhout/aposd-vs-clean-code) and [Microsoft](https://microsoft.github.io/rust-guidelines/guidelines/ai/) value interface documentation even when the code could show the same fact. A comment density lens could charge for this documentation |
| Types are judged on size and coupling | The Rust sources care most about invariants: invalid states, bools, primitives and public fields. Only bool count and public-field count look computable. Whether a field has an invariant does not |
| Modules are judged on public items and dependencies | [Mo et al.](https://neverworkintheory.org/2022/03/14/architecture-anti-patterns.html), via Wilson, rank unstable interfaces highest. The history lenses do not measure this |
| Good PRs are small and in one area | Agent evidence supports this. [Oukay et al.](https://2026.msrconf.org/details/msr-2026-mining-challenge/27/) and [METR](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/) point to scope problems. [Duplicate PRs](https://www.alphaxiv.org/abs/2601.15195.md) are not covered |
| Humans have reviewed a known share | The link to defects is [mixed](https://rebels.cs.uwaterloo.ca/papers/icse2016_shimagaki.pdf). This fits reporting the share more than gating on it |

## Not verified

**Read through a summary, not the original:**

- El Emam et al. 2001
- Inozemtseva and Holmes 2014 (the PDF failed with a connection reset)
- Mo et al. (the PDF failed on a certificate error)
- Sjøberg et al. 2013, read only as described by Soh et al.

**Seen only in search snippets, so not used as findings:**

- Johnson et al. 2019, on nesting and comprehension
- Chowdhury et al., "Revisiting the debate" (access blocked)
- He et al.'s percentages for warnings and complexity
- The 73% mutant coupling figure in Just et al.
- Kamei et al. 2013
- Baum et al. and dos Santos and Nunes, on review effectiveness
- The Cisco and SmartBear figure of about 400 lines
- Sadowski et al. 2018, on Google's review data

**Could not open or not researched:**

- Hatton 1997, on small components: I could not read the abstract, so I make no claim about whether very small units are worse.
- MacCormack et al. on propagation cost: no findings retrieved.
- Martin's instability and main-sequence metrics: not researched.
- The books *A Philosophy of Software Design* and *Clean Code*: not read. Their views come from the authors' joint document, and I did not read its final 24,851 characters, including the closing remarks.

**Single-source figures to check before relying on them:**

- Ehsani et al.'s percentages and odds came through alphaXiv's text of the paper.
- Reviewed studies mix dates and languages. Zeng et al.'s data predates agents. I infer this from the 2021 publication date.
