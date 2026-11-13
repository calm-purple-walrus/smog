# Geiger research notes (fresh run, 2026-11-07)

Each entry: claim | exact quote I read | URL. Only sources read in this run.

## Term

- HN Algolia: exact phrase "metric-driven agentic coding" has 0 hits | "nbHits":0 | https://hn.algolia.com/api/v1/search?query=%22metric-driven%20agentic%20coding%22
- Nearest use: HN comment (PS) critical | "I found metric driven agentic refactors just push complexity to outside the scope of the metric." | https://news.ycombinator.com/item?id=47999904
- Same comment | "I am finding I need to actively guide the agents for the refactors to actually improve things without increasing the entropy of the codebase." | same
- Extended web search: no page uses the phrase as a defined term; results: velocity-vs-quality posts (dev.to/dmitryame), agentic code optimization, engineering metrics in agentic era, CodeScene guardrails, harness engineering.
- Harness engineering (Böckeler) guides/sensors | "Guides (feedforward controls) - anticipate the agent's behaviour and aim to steer it before it acts." ; "Sensors (feedback controls) - observe after the agent acts and help it self-correct." ; "Basically: Fitness Functions" | https://martinfowler.com/articles/harness-engineering.html
- Böckeler field report: agent raised thresholds | "AI frequently decided to increase the cyclomatic complexity threshold, but suggested good refactorings when I nudged it further." | https://martinfowler.com/articles/sensors-for-coding-agents.html
- Fitness function definition | "provides an objective integrity assessment of some architectural characteristics" | https://www.thoughtworks.com/radar/techniques/architectural-fitness-function
- Ford course | "how to define architecture rules embedded within specifications and how to use the same rules to generate deterministic guardrails" | https://nealford.com/training/agentsandarch.html
- CodeScene + loveholidays (TechDebt 2026 industry talk) | "The agents iterated on any low-CodeHealth code additions until they reached a predefined threshold, intentionally set at a high value (a perfect 10)." | https://conf.researchr.org/details/TechDebt-2026/TechDebt-2026-industry-track/1/Quality-Feedback-in-the-Agentic-Loop-Using-CodeHealth-Guardrails-to-Agentic-Code-Imp

## Catalog: structure

- Construct validity (Arif, Kuutila, Ralph, ESEM 2026): factor analysis of class-level metrics from Designite, JHawk, Understand | "24 code quality metrics that correspond to six constructs: Cohesion, In-Coupling, OutCoupling, Size, Sub-Inheritance (related to subclasses), and Sup-Inheritance (related to superclasses)" ; "Ten metrics did not correspond to any known dimension" | https://arxiv.org/pdf/2609.20411
- Size confounding (El Emam et al.) | "After controlling for size none of the metrics we studied were associated with fault-proneness anymore." | https://www.ehealthinformation.ca/web/default/files/wp-files/1062.pdf
- MI critique (van Deursen 2014) | "all underlying metrics (Halstead, Cyclomatic Complexity, Lines of Code) are directly correlated with size (lines of code)" ; "taking the average tends to mask the presence of high-risk parts" | https://avandeursen.com/2014/08/29/think-twice-before-using-the-maintainability-index/
- Cognitive complexity design (Sonar whitepaper) | "a set of simple rules for turning programmer intuition into numbers" | https://www.sonarsource.com/docs/CognitiveComplexity.pdf
- Cognitive complexity validation (Muñoz Barón et al. 2020) | "Cognitive Complexity positively correlates with comprehension time and subjective ratings of understandability. The metric showed mixed results for the correlation with the correctness of comprehension tasks and with physiological measures." | https://arxiv.org/abs/2007.12520
- Understandability (Scalabrino et al. TSE) | "none of the 121 experimented metrics is able to capture code understandability" | https://www.cs.wm.edu/~denys/pubs/TSE'19-Understandability.pdf
- LLM readability ratings (CoReEval) | "LLMs show moderate alignment with human judgments in Java (Pearson = 0.25, Spearman = 0.25), indicating some consistency in relative scoring, though far from strong agreement" | https://arxiv.org/pdf/2510.16579
- Clippy cognitive_complexity | "We used to think it measured how hard a method is to understand." ; left in restriction "so as to not mislead users into using this lint as a measurement tool" (quote spans comment lines) | https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/cognitive_complexity.rs
- rust-code-analysis metric list: ABC, BLANK, CC, CLOC, COGNITIVE, HALSTEAD, LLOC, MI, NARGS, NEXITS, NOM, NPA, NPM, PLOC, SLOC, WMC | "ABC : it measures the size of a source code by counting the number of Assignments ( A ), Branches ( B ) and Conditions ( C )." | https://mozilla.github.io/rust-code-analysis/metrics.html
- Decoupling Level (Mo, Cai, Kazman et al., ICSE 2016) | "Instead of measuring how coupled an architecture is, we measure how well the software can be decoupled into small and independently replaceable modules." ; "Despite decades of research on software metrics, we still cannot reliably measure if one design is more maintainable than another." | https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf

## Catalog: tests

- Coverage vs effectiveness (Inozemtseva & Holmes 2014) | "We found that there is a low to moderate correlation between coverage and effectiveness when the number of test cases in the suite is controlled for." | https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf
- Coverage vs post-release bugs (Kochhar et al.) | "coverage has an insignificant correlation with the number of bugs that are found after the release of the software at the project level, and no such correlation at the file level" | https://www.microsoft.com/en-us/research/publication/code-coverage-and-post-release-defects-a-large-scale-study-on-open-source-projects/
- Mutants vs real faults (Just et al. FSE 2014) | "The results show a statistically significant correlation between mutant detection and real fault detection, independently of code coverage." | https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf
- Google mutation testing | "developers at Google initially classified 85% of reported mutants as unproductive" ; "heuristics for mutant suppression that improved the ratio of productive mutants from 15% to 89%" | https://arxiv.org/pdf/2102.11378v2
- Assertions (Zhang & Mesbah FSE 2015), title | "Assertions Are Strongly Correlated with Test Suite Effectiveness" | https://people.ece.ubc.ca/amesbah/resources/papers/fse15.pdf
- Test smells (Spadini et al. ICSME 2018) | "tests with smells are more change- and defect-prone" ; "production code is more defect-prone when tested by smelly tests" | https://zenodo.org/records/1689875/files/main.pdf
- Flaky tests at Google | "we see a continual rate of about 1.5% of all test runs reporting a "flaky" result" | https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html

## Catalog: history

- Graves et al. (TSE 2000) | "process measures based on the change history are more useful in predicting fault rates than product metrics of the code" ; "the number of times code has been changed is a better indication of how many faults it will contain than is its length" | https://cs.uwaterloo.ca/~m2nagapp/courses/CS846/1171/papers/graves_tse98.pdf
- Nagappan & Ball (ICSE 2005) | "while absolute measures of code churn are poor predictors of defect density, our set of relative measures of code churn is highly predictive of defect density" | https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icse05churn.pdf
- Rahman & Devanbu (ICSE 2013) | "code metrics, despite widespread use in the defect prediction literature, are generally less useful than process metrics for prediction" | https://2013.icse-conferences.org/content/how-and-why-process-metrics-are-better.html
- Majumder et al. (700 GitHub projects) | "process metrics are better predictors for defects than product metrics" | https://arxiv.org/pdf/2008.09569v3.pdf
- Hassan (ICSE 2009), entropy of changes | "our change complexity metrics are better predictors of fault potential in comparison to other well-known historical predictors of faults, i.e., prior modifications and prior faults" | https://sailresearch.github.io/sail-website/data/pdfs/ICSE2009_PredictingFaultsUsingTheComplexityOfCodeChanges.pdf
- Logical coupling (Gall et al. ICSM 1998) | "are there some modules that are always changed together in a release?" | https://plg.uwaterloo.ca/~migod/846/papers/gall-coupling.pdf
- Ownership (Bird et al. 2011) | "measures of ownership such as the number of low-expertise developers, and the proportion of ownership for the top owner have a relationship with both pre-release faults and post-release failures" | https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf

## Catalog: duplication, rule findings, hotspots

- Juergens et al. (clones) | "about every second to third unintentional change to a clone leads to a fault" | https://arxiv.org/pdf/1701.05472
- Rahman, Bird, Devanbu (MSR 2010) | "the great majority of bugs are not significantly associated with clones. Second, we find that clones may be less defect prone than non-cloned code." | https://microsoft.com/en-us/research/wp-content/uploads/2016/02/rahman2010cws.pdf
- Lenarduzzi et al. SonarQube rules | "the fault-prediction power of the model proposed by SonarQube is extremely low" | https://arxiv.org/abs/1907.00376v2
- CodeScene hotspots | "Low code health in a development hotspot is expensive. Prioritize improvements here." | https://codescene.io/docs/guides/technical/hotspots.html
- Code Red (Tornhill & Borg, CodeScene) | "low quality code contains 15 times more defects than high quality code" ; "resolving issues in low quality code takes on average 124% more time in development" | https://arxiv.org/pdf/2203.04374

## Catalog: agent-written code

- SlopCodeBench | "We measure two forms of degradation: structural erosion (concentrated complexity) and verbosity (redundant code)." ; "Explicit quality guidance reduces initial verbosity and erosion by up to a third, without affecting degradation rates." | https://arxiv.org/abs/2603.24755
- Cursor DiD (He et al.) | "Static analysis warnings increase by 30% and code complexity increases by 41% post-adoption" | https://arxiv.org/html/2511.04427v3
- 2609.04208 (Coppola et al.) is a registered report with "Expected Results" only: no findings. Do not cite as evidence.

## Rust

- Clippy groups | "clippy::pedantic | lints which are rather strict or have occasional false positives | allow" ; "clippy::restriction | lints which prevent the use of language and library features" | https://github.com/rust-lang/rust-clippy/blob/master/README.md
- Clippy thresholds | "too-many-lines-threshold The maximum number of lines a function or method can have Default Value: 100" ; "type-complexity-threshold The maximum complexity a type can have Default Value: 250" | https://doc.rust-lang.org/clippy/lint_configuration.html
- cargo-llvm-cov | "line, region, and branch coverage. branch coverage is currently optional and requires nightly" | https://github.com/taiki-e/cargo-llvm-cov/blob/main/README.md
- cargo-mutants | "The --in-diff DIFF_FILE option tests only mutants that overlap with regions changed in the diff." | https://github.com/sourcefrog/cargo-mutants/blob/main/book/src/in-diff.md
- nextest | "By default, flaky tests are treated as ultimately successful." ; "To fail a test run on flaky tests, pass in --flaky-result fail" | https://nexte.st/docs/features/retries/
- cargo-geiger | "A tool that lists statistics related to the usage of unsafe Rust code in a Rust crate and all its dependencies." | https://github.com/geiger-rs/cargo-geiger/blob/master/README.md
- cargo-deny checks: advisories, bans, licenses, sources | https://embarkstudios.github.io/cargo-deny/checks/index.html
- cargo-semver-checks | "Lint your crate API changes for semver violations." | https://github.com/obi1kenobi/cargo-semver-checks/blob/main/README.md
- Unsafe (Zheng et al.) | "vulnerable code has statistically significantly higher ratios of unsafe functions and unsafe blocks compared to complete code" ; "95% of the affected functions are safe functions" | https://arxiv.org/pdf/2308.15046
- Panics (Qin et al. TSE) | "the majority of these issues (107 out of 110) are in safe code" ; "27 issues are triggered by calling unwrap(), while the remaining 12 are triggered when invoking expect()" | https://songlh.github.io/paper/rust-tse.pdf
- Clippy study (Li et al.) | "Clippy is frequently not selected as the gate-keeper in continuous integration due to the high false positives and limited automated fixes for most warnings" | https://arxiv.org/pdf/2310.11738
- Typestate (Heuer thesis) | "While the typestate pattern improves faultlessness and testability significantly, it comes at the cost of more structural code that can degrade readability." | https://arxiv.org/abs/2607.02744

## Custom rules

- Dylint | "Dylint runs lints from user-specified, dynamic libraries. Thus, Dylint allows developers to maintain their own personal lint collections." ; "clippy_utils provides no stability guarantees for its APIs" (backticks in source) | https://github.com/trailofbits/dylint
- Clippy bans | "The list of disallowed methods, written as fully qualified paths." ; "The list of disallowed types, written as fully qualified paths." | https://doc.rust-lang.org/clippy/lint_configuration.html
- ast-grep limits | "ast-grep at the moment does not support the following information: scope analysis type information control flow analysis data flow analysis" | https://ast-grep.github.io/advanced/faq.html
- bevy_lint | "This is an unofficial community project, hacked upon by the Bevy CLI working group" ; "bevy_lint depends on a pinned nightly version of Rust with the rustc-dev Rustup component" (backticks) | https://github.com/TheBevyFlock/bevy_cli/blob/main/bevy_lint/README.md
- bevy_lint schedule lints | "useful for denying an unwanted schedule" | https://github.com/TheBevyFlock/bevy_cli/blob/main/bevy_lint/src/lints/restriction/schedule.rs
- cargo metadata | "Output JSON to stdout containing information about the workspace members and resolved dependencies of the current package." | https://doc.rust-lang.org/cargo/commands/cargo-metadata.html
- Rust Book workspaces | "Cargo doesn’t assume that crates in a workspace will depend on each other, so we need to be explicit about the dependency relationships." | https://doc.rust-lang.org/book/ch14-03-cargo-workspaces.html
- cargo-pup (Datadog) | "lets you write assertions about your Rust project's architecture" ; "Inspired by ArchUnit" | https://github.com/DataDog/cargo-pup
- ArchUnit layers: layeredArchitecture() ; frozen rules | "Consecutive runs will then only report new violations and ignore known violations. If violations are fixed, FreezingArchRule will automatically reduce the known stored violations to prevent any regression." | https://www.archunit.org/userguide/html/000_Index.html

## Categories (gates vs score)

- SonarQube quality gate | "Depending on the result, the code will pass or fail the quality gate" ; "A condition is defined on either new code or overall code." | https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/
- SonarQube ratings: security rating set by worst issue | "E = at least one blocker vulnerability" ; debt ratio | "The ratio between the cost to develop the software and the cost to fix it." | https://docs.sonarsource.com/sonarqube-server/latest/user-guide/code-metrics/metrics-definition/
- Tricorder | "These analyses break the build when they find an issue, so the effective false positive rate must be essentially zero." ; "We still enforce a very low effective false positive rate here (< 10%)." ; "we only display results for most analyses on changed lines by default" | https://research.google.com/pubs/archive/43322.pdf
- Error budget policy | "If the service has exceeded its error budget for the preceding four-week window, we will halt all changes and releases other than P0" | https://sre.google/workbook/error-budget-policy/
- Fitness function categories (Ford slides) | "atomic run against a singular context and exercise one particular aspect of the architecture" ; holistic "run against a shared context and exercise a combination of arch[itectural characteristics]" | https://nealford.com/downloads/Evolutionary_Architectures_workshop_by_Neal_Ford.pdf
- Betterer ratchet | "Betterer keeps track of a value as it changes over time, and makes sure that the value changes how you want it to change!" | https://phenomnomnominal.github.io/betterer/docs/introduction

## Aggregation

- SIG (Heitlager et al. 2007) | "In general, the use of averaging to aggregate measures on individual system parts tends to mask the presence of high-risk parts." ; risk levels by CC 1-10/11-20/21-50/>50, "counting for each risk level what percentage of lines of code falls within units categorized at that level" | https://www.di.uminho.pt/~joost/publications/HeitlagerKuipersVisser-Quatic2007.pdf
- Alves et al. 2010 | "we proposed the use of the 70%, 80% and 90% quantiles to derive thresholds" | https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf
- SQALE | "Technical Debt is the sum of remediation costs for all noncompliances." (PDF hyphenation: quote "Technical Debt is the sum of remediation costs") | https://lists.uniroma2.it/index.html/arc/isssr/2014-01/msg00007/IEEE-SW-Managing-TD-with-SQALE-Accepted-version.pdf
- Quamoco | "the measurement data are interpreted according to the utility functions defined in the model and then aggregated along the model’s structure" | https://arxiv.org/pdf/1611.09230
- Pylint | "Default: max(0, 0 if fatal else 10.0 - ((float(5 * error + warning + refactor + convention) / statement) * 10))" | https://pylint.readthedocs.io/en/stable/user_guide/configuration/all-options.html
- CodeScene Average Code Health | "The weight is the number of lines of code (LoC) in each file." | https://codescene.io/docs/guides/technical/code-health.html
- Zhang et al. TSE 2017 (255 projects, 11 schemes) | "aggregation schemes can significantly alter correlations among metrics, as well as the correlations between metrics and the defect count" | https://sail.cs.queensu.ca/data/pdfs/TSE2017_TheUseOfSummationToAggregateSoftwareMetricsHindersThePerformanceOfDefectPredictionModels.pdf
- Griffith et al. ESEM 2017 | "there is no agreement between the Quamoco and SQALE models in any of the three quality characteristics" | https://www.cs.montana.edu/izurieta/pubs/ESEM_2017.pdf
- Dawes 1979 | "unit (i.e., equal) weighting is quite robust for making such predictions" | https://www.cmu.edu/dietrich/sds/docs/dawes/the-robust-beauty-of-improper-linear-models-in-decision-making.pdf
- JRC composite indicators | "Weights heavily influence the outcome of a composite indicator and countries ranking in a benchmarking exercise." ; "Although in all cases we used equal weighting, rankings produced are very different." | https://knowledge4policy.ec.europa.eu/sites/default/files/eur_21682_en_1.pdf
- Squale: primary sources blocked for download; not used.

## Changed code only

- DMM (di Biase et al. 2019) | "Targeting entire codebases, such models lack the ability to determine shortcomings of smaller, fine-grained ch[anges]" ; "DMM categorizes changed lines of code into low and high risk, and then uses the proportion of low risk change to calculate a delta score." ; "small changes to large systems typically having a very minor impact on the maintainability rating" ; "changes are always weighted towards the entire system’s code base" ; "In a manual inspection process for 100 commits, 67 cases matched the expert judgment." | https://zenodo.org/records/2606632/files/deltamaintainability.pdf
- Hilton et al. coverage evolution | "a change in coverage of even 100 lines would only impact coverage by one hundredth of one percentage point" ; "Patches often impact coverage of existing (nonpatch) code" | https://jonbell.net/publications/coverage
- SonarQube PRs | "Only conditions defined on new code are applied." ; "new code is defined as whatever has changed relative to the target branch" ; "The conditions on duplication are ignored until the number of new lines is at least 20." | https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/
- Clean as You Code | "By always requiring new code to be issue-free, teams gradually improve the overall codebase quality with each sprint" | https://www.sonarsource.com/blog/clean-as-you-code/
- CodeScene delta | "This quality gate is triggered if any code declines in code health." | https://docs.enterprise.codescene.io/latest/guides/delta/automated-delta-analyses.html
- CodeScene MCP | "Returns one numeric score from 10.0 (optimal) to 1.0 (worst)." ; "Run a branch-level Code Health review for all files that differ between the current HEAD and a base ref." | https://raw.githubusercontent.com/codescene-oss/codescene-mcp-server/main/docs/tools.md
- Sigrid CI | "the feedback is based on only the files you touched during your pull request, not the whole system. However, we do consider the entire contents of those files, not only the lines that you personally wrote." | https://docs.sigrid-says.com/capabilities/faq.html
- JIT drift (McIntosh & Kamei) | "fluctuations in the properties of fix-inducing changes can impact the performance and interpretation of JIT models" | https://rebels.cs.uwaterloo.ca/papers/tse2017_mcintosh.pdf

## Product

- Qlty SlopOne | "Largest score drop allowed before a changed file counts as declined (default: 1)" | https://docs.qlty.sh/cli/commands/slop-one.md ; "a hybrid model that combines statistics from traditional static analysis with classifications from Typesafe AI’s new Jev decision model" ; "We’ll publish the methodology and our measurements soon." | https://qlty.sh/blog/introducing-slopone
- aislop | "Scores every change 0–100. Sub-second. Deterministic: no LLM in the runtime path, same code in, same score out." ; "Quality-gate mode: Blocks if score regresses below baseline." | https://github.com/scanaislop/aislop/blob/main/README.md ; import extraction only for .ts/.tsx/.js/.jsx/.mjs/.cjs, .py, (go) | https://github.com/scanaislop/aislop/blob/main/src/engines/architecture/matchers.ts
- desloppify | "A score above 98 should correlate with a codebase a seasoned engineer would call beautiful." ; "True incremental or diff-only scanning is not the supported model yet" | https://github.com/peteromallet/desloppify/blob/main/README.md ; Mechanical 25% / Subjective 75% "AI code review assessments" | https://github.com/peteromallet/desloppify/blob/main/docs/scoring.md
- SlopCheck | "Outputs a Vibe Score (0–100) as an automated PR comment. Configurable threshold to fail CI." | https://github.com/midnightrunai/slopcheck
- Sonar agentic AI gate | "The quality gate enforces six conditions on new code" ; "Coverage on new code is greater or equal to 80%." | https://docs.sonarsource.com/sonarqube-cloud/standards/ai-code-assurance/quality-gate-for-agentic-ai
- SIG benchmark | "SIG’s benchmark spans more than 30,000 systems and over 400 billion lines of code" | https://www.softwareimprovementgroup.com/wp-content/uploads/State-of-Software-2026.pdf
- Qodo founder Itamar Friedman | "Quality is subjective. It depends on organizational standards, past decisions, and tribal knowledge." | https://www.techcrunch.com/2026/03/30/qodo-bets-on-code-verification-as-ai-coding-scales-raises-70m/

## Uncle Bob

- crapper | "CRAP = CC² × (1 − coverage)³ + CC" (code block) ; "A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested." | https://github.com/unclebob/crapper/blob/master/README.md
- mutator | "Mutation testing for Clojure, Java, Go, TypeScript, Rust, and Python." | https://github.com/unclebob/mutator
- dryer | "dryer finds candidate duplicate code in Clojure, Java, Go, TypeScript, Rust, and Python." | https://github.com/unclebob/dryer
- Search result for term: dev.to post | "your priority shouldn't be speed. It should be the compounding quality of your output." | https://dev.to/dmitryame/velocity-is-a-vanity-metric-why-agentic-coding-is-actually-about-quality-3cof

<!-- end -->
