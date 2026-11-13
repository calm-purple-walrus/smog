# Code Quality Measurement for Agentic Coding

Research for Geiger, 2026-11-07. This document answers the questions in the Geiger request. All sources were read for this document. Paragraphs marked **My conclusion** are my own reading of the sources, not something a source states.

## Short answers

**Types of measurement.** Code quality is measured through size, complexity, coupling and architecture, duplication, rule violations, readability, tests, change history and the individual change. Rust adds unsafe code, panic sites, Clippy's lint categories and public API changes. Across studies, measurements of the code alone mostly track size. Measurements of tests and of change history carry more information about defects.

**More interesting than Uncle Bob.** CRAP combines cyclomatic complexity and coverage, two of the weaker signals. Uncle Bob also has a mutation-testing tool, and mutation testing is better supported than coverage. Change-history measurements (how often code changes, how widely changes spread, which files change together, who owns the code) predict defects better than measurements of the code itself. Newer ideas include an architecture metric for how well a system splits into independent modules, and benchmarks that measure how agent-written code decays over a series of tasks.

**The term.** *Metric-driven agentic coding* is not an established term. Searches found no page that uses it, except one Hacker News comment that uses a similar phrase critically. The practice exists under other names: harness engineering, fitness functions, quality gates and ratchets.

**Custom rules such as ECS rules.** Rust has rule engines for rules of different depth: Cargo's crate graph for dependencies, Clippy's lists of banned paths, ast-grep for syntax patterns, and Dylint for lints that need type information. bevy_lint is an existing collection of ECS lints for Bevy. Lints that need type information depend on a pinned nightly toolchain.

**Categories.** Existing tools separate pass/fail gates from ratings. A check that blocks must have almost no false positives. Error budgets are a precedent for allowing a limited amount of decline; ratchets allow none.

**One score.** Averages hide the bad parts, so established models count the share of code above risk thresholds, sum up remediation costs, or map each measurement to a utility value before combining them. Two of these models disagreed completely when rating the same projects, and the choice of aggregation method changes how metrics relate to defects. Equal weights predict about as well as tuned weights, but the aggregation method changes rankings.

**Scoring only the changed code.** Yes, this is possible and already done: SonarQube applies conditions to new code only, CodeScene fails a change when touched code gets worse, SIG rates only the files a pull request touches, and SIG researchers built a maintainability score for single commits. The problem that a large codebase hides decline is documented.

**The product.** Several tools already score or gate agent-written changes. SIG, an established vendor, calibrates its ratings against data from tens of thousands of systems, which takes years to collect. One vendor's founder argues that code quality depends on each organization's own standards, which supports your guess that knowing what you want could be the product.

## 1. Is *metric-driven agentic coding* an established term?

No. The Hacker News search returns no result for the exact phrase ([HN search](https://hn.algolia.com/api/v1/search?query=%22metric-driven%20agentic%20coding%22)), and web searches found no page that defines or uses it. The closest match is a postscript to a Hacker News comment about Uncle Bob: "I found metric driven agentic refactors just push complexity to outside the scope of the metric. I am finding I need to actively guide the agents for the refactors to actually improve things without increasing the entropy of the codebase." ([Hacker News](https://news.ycombinator.com/item?id=47999904)).

A search for the phrase returns related topics instead. Some posts argue that agent-assisted work should be measured by quality rather than speed, for example: "your priority shouldn't be speed. It should be the compounding quality of your output." ([DEV Community](https://dev.to/dmitryame/velocity-is-a-vanity-metric-why-agentic-coding-is-actually-about-quality-3cof)). Others describe the practices below.

**Harness engineering.** Birgitta Böckeler (Thoughtworks) describes what surrounds a coding agent as guides and sensors. Guides "anticipate the agent's behaviour and aim to steer it before it acts", and sensors "observe after the agent acts and help it self-correct". For architecture she writes: "Basically: Fitness Functions" ([martinfowler.com](https://martinfowler.com/articles/harness-engineering.html)).

**Fitness functions.** The term comes from Building Evolutionary Architectures. A fitness function "provides an objective integrity assessment of some architectural characteristics" ([Thoughtworks Technology Radar](https://www.thoughtworks.com/radar/techniques/architectural-fitness-function)). Neal Ford, one of the book's authors, now teaches "how to define architecture rules embedded within specifications and how to use the same rules to generate deterministic guardrails" for agents ([course](https://nealford.com/training/agentsandarch.html)).

**A quality score in the agent loop.** CodeScene and loveholidays fed CodeScene's CodeHealth score back to Claude Code: "The agents iterated on any low-CodeHealth code additions until they reached a predefined threshold, intentionally set at a high value (a perfect 10)." ([TechDebt 2026 talk](https://conf.researchr.org/details/TechDebt-2026/TechDebt-2026-industry-track/1/Quality-Feedback-in-the-Agentic-Loop-Using-CodeHealth-Guardrails-to-Agentic-Code-Imp)). This is an industry talk with the vendor, not a peer-reviewed study.

**Known problem.** Agents optimize the number. In Böckeler's field report, the agent was allowed to raise limits in justified cases: "AI frequently decided to increase the cyclomatic complexity threshold, but suggested good refactorings when I nudged it further." ([martinfowler.com](https://martinfowler.com/articles/sensors-for-coding-agents.html)). The Hacker News comment above describes the same problem.

Quality gates and ratchets, two older practices for controlling code changes with measurements, are described in Section 5.

**My conclusion:** The name is free. The idea of steering agents with measurements is in use under the names above, and its known weakness is that agents change the code to satisfy the measurement rather than to improve it.

## 2. Types of code quality measurements

### Size

Lines of code, statements, functions per file and arguments per function. Size explains much of what other metrics report. In a study of a large C++ framework, "After controlling for size none of the metrics we studied were associated with fault-proneness anymore." ([El Emam et al.](https://www.ehealthinformation.ca/web/default/files/wp-files/1062.pdf)).

### Complexity

Cyclomatic complexity is computed from a function's control flow. Cognitive complexity adds one for each break in the linear flow of the code and more for nested ones; its designers describe it as "a set of simple rules for turning programmer intuition into numbers" ([SonarSource](https://www.sonarsource.com/docs/CognitiveComplexity.pdf)). The Halstead suite estimates, among other things, the effort to maintain code and the difficulty of understanding it, and the ABC metric counts assignments, branches and conditions ([rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html)).

The evidence that these measure difficulty is weak. Cognitive complexity "positively correlates with comprehension time and subjective ratings of understandability", but "The metric showed mixed results for the correlation with the correctness of comprehension tasks" ([Muñoz Barón et al.](https://arxiv.org/abs/2007.12520)). A study of 121 metrics found that "none of the 121 experimented metrics is able to capture code understandability" ([Scalabrino et al.](https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf)).

### Coupling, cohesion and architecture

Class-level metrics count how many other classes a class uses or is used by, how closely its methods belong together, and how deep the inheritance goes. A 2026 study tested whether such metrics from three tools measure distinct properties. It found "24 code quality metrics that correspond to six constructs: Cohesion, In-Coupling, OutCoupling, Size, Sub-Inheritance (related to subclasses), and Sup-Inheritance (related to superclasses)", and "Ten metrics did not correspond to any known dimension" ([Arif et al., ESEM 2026](https://arxiv.org/pdf/2609.20411)).

Architecture metrics work on the dependency graph of files or modules. The Decoupling Level metric starts from the observation that "we still cannot reliably measure if one design is more maintainable than another". "Instead of measuring how coupled an architecture is, we measure how well the software can be decoupled into small and independently replaceable modules." ([Mo et al., ICSE 2016](https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf)). Layer rules, such as *the domain must not depend on infrastructure*, are checks on the same dependency graph (Section 4).

### Duplication

Clone detection finds copied or near-copied code. The evidence on harm is mixed. One study found that "about every second to third unintentional change to a clone leads to a fault" ([Juergens et al.](https://arxiv.org/pdf/1701.05472)). Another found that "the great majority of bugs are not significantly associated with clones" and that "clones may be less defect prone than non-cloned code" ([Rahman et al.](https://microsoft.com/en-us/research/wp-content/uploads/2016/02/rahman2010cws.pdf)).

### Rule violations

Linters and static analyzers report violations of coding rules. Single rules predict faults poorly: for SonarQube's rules labelled as bugs, "the fault-prediction power of the model proposed by SonarQube is extremely low" ([Lenarduzzi et al.](https://arxiv.org/abs/1907.00376v2)).

### Readability

Readability models and, more recently, LLMs rate how easy code is to read. LLM ratings agree only weakly with human ratings: for Java, "LLMs show moderate alignment with human judgments in Java (Pearson = 0.25, Spearman = 0.25), indicating some consistency in relative scoring, though far from strong agreement" ([CoReEval](https://arxiv.org/pdf/2510.16579)).

### Tests

**Coverage** is a weak measure of test quality. Once the number of tests is held constant, "there is a low to moderate correlation between coverage and effectiveness when the number of test cases in the suite is controlled for" ([Inozemtseva & Holmes](https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)). Across 100 open-source Java projects, "coverage has an insignificant correlation with the number of bugs that are found after the release of the software at the project level, and no such correlation at the file level" ([Kochhar et al.](https://www.microsoft.com/en-us/research/publication/code-coverage-and-post-release-defects-a-large-scale-study-on-open-source-projects/)).

**Mutation testing** changes the code in small ways and checks whether a test fails. "The results show a statistically significant correlation between mutant detection and real fault detection, independently of code coverage." ([Just et al.](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf)). Google runs it on changed code during review. At first, "developers at Google initially classified 85% of reported mutants as unproductive"; rules based on their feedback "improved the ratio of productive mutants from 15% to 89%" ([Petrović et al.](https://arxiv.org/pdf/2102.11378v2)).

**Assertions, test smells and flaky tests.** "Assertions Are Strongly Correlated with Test Suite Effectiveness" ([Zhang & Mesbah](https://people.ece.ubc.ca/amesbah/resources/papers/fse15.pdf)). Badly structured tests ("test smells") matter: "tests with smells are more change- and defect-prone" and "production code is more defect-prone when tested by smelly tests" ([Spadini et al.](https://zenodo.org/records/1689875/files/main.pdf)). Flaky tests make test-based measurements unstable. Google defines a flaky result as "a test that exhibits both a passing and a failing result with the same code" and sees it in about 1.5% of all test runs ([Google Testing Blog](https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html)).

### Change history

Change history is mined from version control. It predicts defects better than measurements of the code itself.

- **Change frequency and churn.** "the number of times code has been changed is a better indication of how many faults it will contain than is its length" ([Graves et al.](https://cs.uwaterloo.ca/~m2nagapp/courses/CS846/1171/papers/graves_tse98.pdf)). Churn needs normalizing: "while absolute measures of code churn are poor predictors of defect density, our set of relative measures of code churn is highly predictive of defect density" ([Nagappan & Ball](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icse05churn.pdf)).
- **How widely changes spread.** Hassan measures the entropy of changes, which is lowest when all changes touch one file and grows as changes spread across files. His "change complexity metrics are better predictors of fault potential in comparison to other well-known historical predictors of faults, i.e., prior modifications and prior faults" ([Hassan, ICSE 2009](https://sailresearch.github.io/sail-website/data/pdfs/ICSE2009_PredictingFaultsUsingTheComplexityOfCodeChanges.pdf)).
- **Files that change together.** Logical coupling asks: "are there some modules that are always changed together in a release?" ([Gall et al.](https://plg.uwaterloo.ca/~migod/846/papers/gall-coupling.pdf)).
- **Ownership.** At Microsoft, "measures of ownership such as the number of low-expertise developers, and the proportion of ownership for the top owner have a relationship with both pre-release faults and post-release failures" ([Bird et al.](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf)).
- **Hotspots.** CodeScene combines change frequency with its code score: "Low code health in a development hotspot is expensive. Prioritize improvements here." ([CodeScene](https://codescene.io/docs/guides/technical/hotspots.html)). CodeScene's own study reports that "low quality code contains 15 times more defects than high quality code" ([Tornhill & Borg](https://arxiv.org/pdf/2203.04374)); the authors work for CodeScene.

Comparisons favour history: "code metrics, despite widespread use in the defect prediction literature, are generally less useful than process metrics for prediction" ([Rahman & Devanbu](https://2013.icse-conferences.org/content/how-and-why-process-metrics-are-better.html)). A re-check on 700 GitHub projects reached the same result: "process metrics are better predictors for defects than product metrics" ([Majumder et al.](https://arxiv.org/pdf/2008.09569v3.pdf)).

### The individual change

Just-in-time defect prediction rates single commits by properties such as the size of the change and how widely it is spread across the code. The models need regular retraining, because "fluctuations in the properties of fix-inducing changes can impact the performance and interpretation of JIT models" ([McIntosh & Kamei](https://rebels.cs.uwaterloo.ca/papers/tse2017_mcintosh.pdf)).

### Composite scores

- **Maintainability Index.** Combines Halstead metrics, cyclomatic complexity and lines of code. Its inputs "are directly correlated with size (lines of code)", and because it averages over files, "taking the average tends to mask the presence of high-risk parts" ([van Deursen](https://avandeursen.com/2014/08/29/think-twice-before-using-the-maintainability-index/)).
- **CRAP.** Uncle Bob's crapper computes `CRAP = CC² × (1 − coverage)³ + CC` per function ([crapper](https://github.com/unclebob/crapper/blob/master/README.md)).
- **Technical debt (SQALE), SIG ratings, Quamoco, CodeScene Code Health.** These combine many measurements into one value; Section 6 describes how.

### Measurements for agent-written code

New research measures how agent-written code decays over a series of tasks, which is the 50-PR scenario in the request. SlopCodeBench has agents extend their own code over many checkpoints and measures "two forms of degradation: structural erosion (concentrated complexity) and verbosity (redundant code)". Its result: "Explicit quality guidance reduces initial verbosity and erosion by up to a third, without affecting degradation rates." ([Orlanski et al.](https://arxiv.org/abs/2603.24755)). In open-source projects that adopted Cursor, "Static analysis warnings increase by 30% and code complexity increases by 41% post-adoption" ([He et al.](https://arxiv.org/html/2511.04427v3)).

### Beyond Uncle Bob

crapper scores each function by cyclomatic complexity and coverage, with "A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested." ([crapper](https://github.com/unclebob/crapper/blob/master/README.md)). Both inputs are among the weaker signals above. His other two tools do "Mutation testing for Clojure, Java, Go, TypeScript, Rust, and Python." ([mutator](https://github.com/unclebob/mutator)) and find duplicates: "dryer finds candidate duplicate code in Clojure, Java, Go, TypeScript, Rust, and Python." ([dryer](https://github.com/unclebob/dryer)). Mutation testing is one of the better-supported measurements.

**My conclusion:** The more interesting measurements in this research are mutation testing, the change-history measures (change frequency, entropy of changes, files that change together, ownership, hotspots), architecture decoupling, and the decay measures from agent benchmarks (erosion and verbosity across tasks).

## 3. Rust

### Tools

- **Clippy.** Lints are grouped by how strict they are: pedantic contains "lints which are rather strict or have occasional false positives", restriction contains "lints which prevent the use of language and library features" ([Clippy README](https://github.com/rust-lang/rust-clippy/blob/master/README.md)). Limits such as function length and type complexity are configurable; for example, `too-many-lines-threshold` has a default value of 100 ([Clippy configuration](https://doc.rust-lang.org/clippy/lint_configuration.html)). The documentation of the `cognitive_complexity` lint says: "We used to think it measured how hard a method is to understand." Clippy keeps it in the restriction group so that it is not used as a measurement ([lint source](https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/cognitive_complexity.rs)).
- **rust-code-analysis** (Mozilla) computes size, complexity, Halstead, ABC, Maintainability Index and related metrics per function and file ([metrics](https://mozilla.github.io/rust-code-analysis/metrics.html)).
- **Coverage.** cargo-llvm-cov measures line, region and branch coverage; "branch coverage is currently optional and requires nightly" ([cargo-llvm-cov](https://github.com/taiki-e/cargo-llvm-cov/blob/main/README.md)).
- **Mutation testing.** cargo-mutants can limit itself to a change: "The --in-diff DIFF_FILE option tests only mutants that overlap with regions changed in the diff." ([cargo-mutants](https://github.com/sourcefrog/cargo-mutants/blob/main/book/src/in-diff.md)).
- **Flaky tests.** cargo-nextest retries failing tests and reports those that pass on retry. "By default, flaky tests are treated as ultimately successful." A flag makes them fail the run instead ([nextest](https://nexte.st/docs/features/retries/)).
- **Unsafe code.** cargo-geiger is "A tool that lists statistics related to the usage of unsafe Rust code in a Rust crate and all its dependencies." ([cargo-geiger](https://github.com/geiger-rs/cargo-geiger/blob/master/README.md)).
- **Dependencies.** cargo-deny checks advisories, banned crates, licenses and sources ([cargo-deny](https://embarkstudios.github.io/cargo-deny/checks/index.html)).
- **Public API.** cargo-semver-checks: "Lint your crate API changes for semver violations." ([cargo-semver-checks](https://github.com/obi1kenobi/cargo-semver-checks/blob/main/README.md)).
- **Dependency graph.** `cargo metadata` outputs "JSON to stdout containing information about the workspace members and resolved dependencies of the current package" ([Cargo book](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html)).

### Evidence specific to Rust

**Unsafe code.** In a study of Rust vulnerabilities, "vulnerable code has statistically significantly higher ratios of unsafe functions and unsafe blocks compared to complete code". At the same time, "95% of the affected functions are safe functions" ([Zheng et al.](https://arxiv.org/pdf/2308.15046)).

**Panic sites.** In a study of real panic bugs, "the majority of these issues (107 out of 110) are in safe code", and "27 issues are triggered by calling unwrap(), while the remaining 12 are triggered when invoking expect()" ([Qin et al.](https://songlh.github.io/paper/rust-tse.pdf)). How many `unwrap` calls in a codebase are real bugs is not known.

**Clippy as a gate.** A study of Clippy use found that "Clippy is frequently not selected as the gate-keeper in continuous integration due to the high false positives and limited automated fixes for most warnings" ([Li et al.](https://arxiv.org/pdf/2310.11738)).

**Types.** Rust moves part of the design into types, where control-flow metrics do not look. A thesis that refactored production code found: "While the typestate pattern improves faultlessness and testability significantly, it comes at the cost of more structural code that can degrade readability." ([Heuer](https://arxiv.org/abs/2607.02744)).

## 4. Custom rules: the ECS example

Rules differ in how much they need to know about the code. Rust has an engine for each depth:

1. **Dependencies between crates.** "Cargo doesn’t assume that crates in a workspace will depend on each other, so we need to be explicit about the dependency relationships." ([Rust Book](https://doc.rust-lang.org/book/ch14-03-cargo-workspaces.html)). In a workspace with one crate per layer, a layer rule therefore becomes a rule about which dependencies each crate may declare, and `cargo metadata` provides the resolved graph to check it against (Section 3).
2. **Banned functions and types.** Clippy accepts "The list of disallowed types, written as fully qualified paths." and the same for methods and macros, configured per crate ([Clippy configuration](https://doc.rust-lang.org/clippy/lint_configuration.html)). A domain crate can ban engine or framework types this way without writing a lint.
3. **Syntax patterns.** ast-grep matches code patterns from YAML rules. "ast-grep at the moment does not support the following information": scope analysis, type information, control flow and data flow ([ast-grep FAQ](https://ast-grep.github.io/advanced/faq.html)). It cannot check rules that depend on types.
4. **Lints with type information.** "Dylint runs lints from user-specified, dynamic libraries." ([Dylint](https://github.com/trailofbits/dylint)). These lints use compiler internals and the `clippy_utils` library, which "provides no stability guarantees for its APIs". Each lint library is compiled for one toolchain: its file name contains a TOOLCHAIN part, which "is the Rust toolchain for which the library is compiled", such as a dated nightly ([How Dylint works](https://github.com/trailofbits/dylint/blob/master/docs/how_dylint_works.md)).
5. **Architecture assertions.** cargo-pup (Datadog) "lets you write assertions about your Rust project's architecture" and is inspired by ArchUnit ([cargo-pup](https://github.com/DataDog/cargo-pup)). ArchUnit, the Java original, declares layers and their allowed dependencies with `layeredArchitecture()`. For existing violations it records them, so that "Consecutive runs will then only report new violations and ignore known violations." ([ArchUnit](https://www.archunit.org/userguide/html/000_Index.html)).

For ECS, an example exists. bevy_lint is "an unofficial community project, hacked upon by the Bevy CLI working group" ([bevy_lint](https://github.com/TheBevyFlock/bevy_cli/blob/main/bevy_lint/README.md)), with lints for Bevy's ECS conventions. Two of them are "useful for denying an unwanted schedule" in a whole module, for example to keep physics systems out of the per-frame schedule ([source](https://github.com/TheBevyFlock/bevy_cli/blob/main/bevy_lint/src/lints/restriction/schedule.rs)). bevy_lint "depends on a pinned nightly version of Rust", because it uses internal compiler crates.

**My conclusion:** Plugging in team rules does not need a new rule language; the engines exist and produce machine-readable output. The depth of a rule decides the cost. Crate dependencies and banned paths need configuration only. ECS rules that depend on types, such as *systems may only access these components*, need type-aware lints and therefore a pinned nightly toolchain.

## 5. Categories: blocking versus lowering the score

Existing tools already separate the two. A SonarQube quality gate is pass/fail: "Depending on the result, the code will pass or fail the quality gate", and each condition applies to new code or to all code ([SonarQube](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/)). Its ratings are built in two different ways. The security rating is set by the worst finding, "E = at least one blocker vulnerability". The maintainability rating is based on a debt ratio, "The ratio between the cost to develop the software and the cost to fix it." ([SonarQube metrics](https://docs.sonarsource.com/sonarqube-server/latest/user-guide/code-metrics/metrics-definition/)). Fitness functions are also split into kinds: atomic ones "run against a singular context and exercise one particular aspect of the architecture", holistic ones "run against a shared context" and check several characteristics together ([Ford's workshop slides](https://nealford.com/downloads/Evolutionary_Architectures_workshop_by_Neal_Ford.pdf)).

A blocking check must be almost free of false positives. At Google, analyses that break the build must meet this: "These analyses break the build when they find an issue, so the effective false positive rate must be essentially zero." Findings shown during code review may have a false-positive rate of up to 10% ([Tricorder](https://research.google.com/pubs/archive/43322.pdf)). Clippy illustrates the problem: it is often not used as a CI gate because of false positives (Section 3).

Two established mechanisms control how much a value may get worse. Google's error-budget policy allows a limited amount and lets releases continue until the budget is spent: "If the service has exceeded its error budget for the preceding four-week window, we will halt all changes and releases other than P0" issues or security fixes ([Google SRE](https://sre.google/workbook/error-budget-policy/)). A ratchet allows none and lets a value move in one direction only: "Betterer keeps track of a value as it changes over time, and makes sure that the value changes how you want it to change!" ([Betterer](https://phenomnomnominal.github.io/betterer/docs/introduction)).

**My conclusion:** Layer violations and banned dependencies fit blocking, because they can be checked without false positives. Continuous measurements such as length, complexity or coverage fit the score.

## 6. Combining measurements into one score

**Averages hide problems.** "In general, the use of averaging to aggregate measures on individual system parts tends to mask the presence of high-risk parts." ([Heitlager et al.](https://www.di.uminho.pt/~joost/publications/HeitlagerKuipersVisser-Quatic2007.pdf)). The established alternatives:

- **Risk profiles (SIG).** Each function is put into a risk level by its complexity, and the score is built from the share of code in each level, "counting for each risk level what percentage of lines of code falls within units categorized at that level" ([Heitlager et al.](https://www.di.uminho.pt/~joost/publications/HeitlagerKuipersVisser-Quatic2007.pdf)). The thresholds come from a benchmark of real systems: "we proposed the use of the 70%, 80% and 90% quantiles to derive thresholds" ([Alves et al.](https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf)).
- **Summed debt (SQALE).** "Technical Debt is the sum of remediation costs" for all rule violations ([Letouzey & Ilkiewicz](https://lists.uniroma2.it/index.html/arc/isssr/2014-01/msg00007/IEEE-SW-Managing-TD-with-SQALE-Accepted-version.pdf)). SonarQube divides this sum by the estimated cost of developing the code (Section 5).
- **Utility functions (Quamoco).** Each measurement is mapped to a utility value, and "the measurement data are interpreted according to the utility functions defined in the model and then aggregated along the model’s structure" ([Wagner et al.](https://arxiv.org/pdf/1611.09230)).
- **Weighted averages (CodeScene).** File scores are averaged, and "The weight is the number of lines of code (LoC) in each file." ([CodeScene](https://codescene.io/docs/guides/technical/code-health.html)).
- **Counts divided by size (Pylint).** The default score is `max(0, 0 if fatal else 10.0 - ((float(5 * error + warning + refactor + convention) / statement) * 10))` ([Pylint](https://pylint.readthedocs.io/en/stable/user_guide/configuration/all-options.html)).

**The choice matters.** In a study of 255 projects, "aggregation schemes can significantly alter correlations among metrics, as well as the correlations between metrics and the defect count" ([Zhang et al.](https://sail.cs.queensu.ca/data/pdfs/TSE2017_TheUseOfSummationToAggregateSoftwareMetricsHindersThePerformanceOfDefectPredictionModels.pdf)). Two established models rated the same projects without agreement: "there is no agreement between the Quamoco and SQALE models in any of the three quality characteristics" ([Griffith et al.](https://www.cs.montana.edu/izurieta/pubs/ESEM_2017.pdf)).

**User-adjustable weights.** For prediction, the exact weights matter less than expected: "unit (i.e., equal) weighting is quite robust for making such predictions" ([Dawes](https://www.cmu.edu/dietrich/sds/docs/dawes/the-robust-beauty-of-improper-linear-models-in-decision-making.pdf)). For rankings and thresholds, the construction matters: "Weights heavily influence the outcome of a composite indicator", and with the aggregation method changed, "Although in all cases we used equal weighting, rankings produced are very different." ([EU composite indicators toolkit](https://knowledge4policy.ec.europa.eu/sites/default/files/eur_21682_en_1.pdf)).

**Report of offending areas.** Risk profiles assign every function to a risk level, so the functions in the high levels are the ones to report. CodeScene ranks hotspots by change frequency and code score (Section 2). Both answer which code causes the score, not only what the score is.

**My conclusion:** The sources above do not show that any combination method measures quality reliably, so the Geiger score is a policy that a team chooses. A method that weights the worst parts heavily, such as risk profiles, fits the goal of exposing bad code better than an average does.

## 7. Scoring only the changed code

**The problem is documented.** For coverage in a project of a million lines, "a change in coverage of even 100 lines would only impact coverage by one hundredth of one percentage point" ([Hilton et al.](https://jonbell.net/publications/coverage)). For SIG's model, whole-codebase scoring leads to "small changes to large systems typically having a very minor impact on the maintainability rating", because "changes are always weighted towards the entire system’s code base" ([di Biase et al.](https://zenodo.org/records/2606632/files/deltamaintainability.pdf)).

**Existing approaches:**

- **New code only.** In SonarQube pull requests, "Only conditions defined on new code are applied.", and "new code is defined as whatever has changed relative to the target branch". For small changes, "The conditions on duplication are ignored until the number of new lines is at least 20." ([SonarQube](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/)). Sonar's argument: "By always requiring new code to be issue-free, teams gradually improve the overall codebase quality with each sprint" ([Clean as You Code](https://www.sonarsource.com/blog/clean-as-you-code/)).
- **Touched files.** CodeScene's gate "is triggered if any code declines in code health" ([CodeScene](https://docs.enterprise.codescene.io/latest/guides/delta/automated-delta-analyses.html)). SIG's Sigrid CI rates "only the files you touched during your pull request", but "we do consider the entire contents of those files, not only the lines that you personally wrote" ([Sigrid](https://docs.sigrid-says.com/capabilities/faq.html)).
- **A score for a single commit.** SIG researchers built the Delta Maintainability Model because whole-codebase models "lack the ability to determine shortcomings of smaller, fine-grained" changes. "DMM categorizes changed lines of code into low and high risk, and then uses the proportion of low risk change to calculate a delta score." Checked against experts, "In a manual inspection process for 100 commits, 67 cases matched the expert judgment." ([di Biase et al.](https://zenodo.org/records/2606632/files/deltamaintainability.pdf)).
- **Changed lines.** Google shows "results for most analyses on changed lines by default" ([Tricorder](https://research.google.com/pubs/archive/43322.pdf)), and runs mutation testing on changed code (Section 2). cargo-mutants supports the same in Rust (Section 3).

**Limits.** A change also affects code outside the diff: "Patches often impact coverage of existing (nonpatch) code" ([Hilton et al.](https://jonbell.net/publications/coverage)). Scores for small changes are unstable, which is why SonarQube waits for 20 new lines before it applies some conditions.

**My conclusion:** Measuring the changed code is possible and established. For a per-PR limit such as 0.2 points to mean the same in a small and a large codebase, the limit has to apply to something that is not divided by the size of the whole codebase: the score of the touched code, or the amount of problems the change adds.

## 8. The product question

Several tools already score or gate agent-written changes:

- **CodeScene** gives each file a score that "Returns one numeric score from 10.0 (optimal) to 1.0 (worst)", and its agent tool can "Run a branch-level Code Health review for all files that differ between the current HEAD and a base ref." ([CodeScene MCP tools](https://raw.githubusercontent.com/codescene-oss/codescene-mcp-server/main/docs/tools.md)).
- **SonarQube** has a gate for agent-written code: "The quality gate enforces six conditions on new code" ([SonarQube](https://docs.sonarsource.com/sonarqube-cloud/standards/ai-code-assurance/quality-gate-for-agentic-ai)).
- **Qlty SlopOne** uses "a hybrid model that combines statistics from traditional static analysis with classifications from Typesafe AI’s new Jev decision model", and says: "We’ll publish the methodology and our measurements soon." ([Qlty](https://qlty.sh/blog/introducing-slopone)). Each changed file may drop by a set amount: "Largest score drop allowed before a changed file counts as declined (default: 1)" ([Qlty docs](https://docs.qlty.sh/cli/commands/slop-one.md)).
- **aislop** "Scores every change 0–100. Sub-second. Deterministic: no LLM in the runtime path, same code in, same score out." Its agent hook "Blocks if score regresses below baseline." ([aislop](https://github.com/scanaislop/aislop/blob/main/README.md)). Its architecture rules read imports only from JavaScript, TypeScript, Python and Go files ([source](https://github.com/scanaislop/aislop/blob/main/src/engines/architecture/matchers.ts)).
- **desloppify** claims "A score above 98 should correlate with a codebase a seasoned engineer would call beautiful." and says "True incremental or diff-only scanning is not the supported model yet" ([desloppify](https://github.com/peteromallet/desloppify/blob/main/README.md)). Three quarters of its score comes from "AI code review assessments" ([scoring](https://github.com/peteromallet/desloppify/blob/main/docs/scoring.md)).
- **SlopCheck** "Outputs a Vibe Score (0–100) as an automated PR comment. Configurable threshold to fail CI." ([SlopCheck](https://github.com/midnightrunai/slopcheck)).

SIG, an established vendor, calibrates its ratings against other systems, and "SIG’s benchmark spans more than 30,000 systems and over 400 billion lines of code" ([SIG](https://www.softwareimprovementgroup.com/wp-content/uploads/State-of-Software-2026.pdf)).

Your guess that knowing what you want may be the product has support from a vendor. Qodo's founder Itamar Friedman says: "Quality is subjective. It depends on organizational standards, past decisions, and tribal knowledge." ([TechCrunch](https://www.techcrunch.com/2026/03/30/qodo-bets-on-code-verification-as-ai-coding-scales-raises-70m/)). This is a vendor's view, not evidence.

**My conclusion:** Measurements and gates on changed code are already available, so they are not the product. Two things none of the tools above offers: deterministic architecture and domain rules for Rust that feed a score, and a limited per-PR allowance instead of either blocking any decline (aislop, CodeScene) or allowing a fixed drop per file (Qlty). Benchmark data from many repositories is what SIG built over years, and a tool that is used on many repositories could collect such data as well.

## Sources and limits

Every quotation was checked by a script against the linked source after writing. The Squale papers on weighting bad parts more heavily could not be downloaded and are not used. Most evidence about metrics comes from Java and C++ projects; Rust-specific evidence is limited to the studies in Section 3. The working notes with all quotes are in `.local/geiger-research/notes.md`.
