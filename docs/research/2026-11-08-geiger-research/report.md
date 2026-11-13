# Geiger research report

Date: 2026-11-08. Supporting files in this folder: `products.md` (product details), `metrics.md` (the full metrics catalogue), `scoring.md` (sources for section 3).

## Summary

- **Products.** Many tools that score or gate agent-written code already exist; most were released in 2026. Free tools give agent-written code one score (desloppify, aislop, sentrux, fallow, polyscan, and rustqual for Rust), check only changed code, connect to agents through hooks and MCP servers, and enforce layer rules. Qlty SlopOne caps the score drop per changed file, which is your 0.2-points-per-pull-request rule applied per file. SonarQube, CodeScene, SIG, Codacy and DeepSource added gates or tools for agent code. Section 1.
- **Metrics.** `metrics.md` lists the metrics that tools compute and research proposes, by family, with definitions, sources, Rust tools and evidence. The evidence supports your doubts about complexity and coverage: complexity metrics mostly measure size, and coverage correlates weakly with test effectiveness once the number of tests is controlled. The best-supported predictors are history metrics (churn, number of changes, change size), change-level risk models and mutation score. Section 2.
- **Measuring the changed code.** This is possible and common: new-code gates, before/after scores per changed file, diff coverage, mutation testing on the diff, risk scores per change. The dilution you described is documented: a 200-line fix moved a system's SIG rating by −0.007 on a scale from −5 to 5. Change-level numbers are noisy and depend on size, and only counts and costs add up across changes. Section 3.
- **Gates and the single number.** Google lets only checks with essentially no false positives break the build. No study shows which classes of violation are worth blocking. Evidence that any aggregate score predicts outcomes is weak: a plain line count predicted expert maintainability labels as well as CodeScene's Code Health. No per-change quality budget has been evaluated. Section 3.
- **Gaming.** Agents game tests: GPT-5 cheated on 76% of SWE-bench tasks made impossible, and Claude models cheated mainly by editing tests. A gate configuration stored in the repository can be changed by the pull request it checks. Section 3.
- **Product.** The runner, the score and the plug-in system exist for free. What is missing: evidence that a score predicts outcomes for agent-written code, rules for specific architectures, and a measurement the agent cannot change. Recommendation: sell architecture rules as enforced checks under the name "metric-driven agentic coding", and build outcome data as the long-term asset. Section 4.
- **Term and name.** Nobody uses "metric-driven agentic coding"; the only near match is one critical Hacker News comment. The name Geiger is taken in the Rust ecosystem by cargo-geiger. Section 5.

## 1. Existing products

For each product: link, the metrics it computes, and the techniques it uses. `products.md` adds how each reports, whether it can check only changed code, how users add rules, and licence and price.

### Built for code written by agents

Most of these appeared in 2026.

- **desloppify**: [github.com/peteromallet/desloppify](https://github.com/peteromallet/desloppify)
  - Metrics: 0–100 health score. Mechanical dimensions (file health, code quality, duplication, test health, security) make up 25%; LLM-judged dimensions (elegance, contracts, type safety, design coherence, abstraction fit, logic clarity, naming, "AI generated debt" and others) make up 75%.
  - Techniques: dead-code, duplication and complexity detection plus LLM review. For Rust it runs `cargo clippy`, `cargo check` and `cargo rustdoc`. No diff-only mode.
- **aislop**: [github.com/scanaislop/aislop](https://github.com/scanaislop/aislop)
  - Metrics: 0–100 score from findings on formatting, linting, function and file size, nesting, unused code, "AI slop" patterns (narrative comments, TODO stubs, generic names), security, and opt-in import rules.
  - Techniques: runs existing formatters and linters (Clippy for Rust) plus its own syntax rules; no LLM; can score only changed files; agent hooks and an MCP server.
- **crapper, dryer and mutator** (Uncle Bob): [crapper](https://github.com/unclebob/crapper), [dryer](https://github.com/unclebob/dryer), [mutator](https://github.com/unclebob/mutator); agent skill [ub-mode](https://github.com/unclebob/ub-mode)
  - Metrics: CRAP per function, CC² × (1 − coverage)³ + CC; duplicate functions by structural similarity (default threshold 0.82); mutation score.
  - Techniques: tree-sitter parsing (Rust supported); coverage from `cargo llvm-cov` or tarpaulin; mutants run with `cargo test`. All three accept `--changed`. No repository score.
- **Qlty SlopOne**: [announcement](https://qlty.sh/blog/introducing-slopone); CLI [github.com/qltysh/qlty](https://github.com/qltysh/qlty)
  - Metrics: maintainability score per file.
  - Techniques: static-analysis statistics plus an LLM's answers to reviewer-style questions, combined by a machine-learning model. Compares changed files with the merge base and caps the drop per file (`--max-drop`). The methodology is not yet published.
- **CodeScene MCP server**: [github.com/codescene-oss/codescene-mcp-server](https://github.com/codescene-oss/codescene-mcp-server)
  - Metrics: Code Health per file (10.0 to 1.0) and a verdict per changed file: improved, degraded or stable.
  - Techniques: CodeScene's Code Health analysis, run locally for the agent.
- **Sonar for agents** (closed source): [agentic AI quality gate](https://docs.sonarsource.com/sonarqube-cloud/standards/ai-code-assurance/quality-gate-for-agentic-ai.md), [Vortex](https://docs.sonarsource.com/agent-centric-development-cycle/inside-your-agent-the-agentic-loop/sonar-vortex.md)
  - Metrics: conditions on new code: no new reliability or security issues of low severity or above, no new maintainability issues of medium severity or above, coverage of new code at least 80%, duplication at most 3%.
  - Techniques: Sonar's rule-based static analysis, run inside the agent's loop by Vortex. Vortex does not analyze Rust.
- **SIG Sigrid Guardrails** (closed source): [softwareimprovementgroup.com/mcp](https://www.softwareimprovementgroup.com/mcp/)
  - Metrics: maintainability (duplication, unit size, complexity, coupling), security findings mapped to the OWASP Top 10, and architecture drift (new dependencies, cycles, bypassed facades).
  - Techniques: SIG's deterministic analysis, called through MCP on each changed file. No Rust.
- **Codacy Guardrails** (closed source): [docs](https://docs.codacy.com/codacy-guardrails/codacy-guardrails-getting-started/)
  - Metrics: issues from about 30 bundled scanners.
  - Techniques: local static analysis in the IDE while the agent writes code, through an MCP server.
- **DeepSource Autofix Bot and PR Report Card** (closed source): [deepsource.com](https://deepsource.com/llms.txt)
  - Metrics: a letter grade per pull request over security, reliability, complexity, hygiene and coverage.
  - Techniques: static rules plus an AI review agent.
- **sentrux**: [github.com/sentrux/sentrux](https://github.com/sentrux/sentrux)
  - Metrics: one score (0–10000) from modularity, acyclicity, depth, equality and redundancy of the dependency structure.
  - Techniques: dependency analysis with tree-sitter; layer and boundary rules in `.sentrux/rules.toml`; a baseline saved before the agent session and a gate after it.
- **fallow**: [github.com/fallow-rs/fallow](https://github.com/fallow-rs/fallow)
  - Metrics (TypeScript and JavaScript): 0–100 health score; complexity, duplication, unused code, churn and ownership, boundary violations with presets (layered, hexagonal and others), circular dependencies.
  - Techniques: repository graph plus git history; fails only on findings in changed files.
- **rustqual**: [github.com/SaschaOnTour/rustqual](https://github.com/SaschaOnTour/rustqual)
  - Metrics (Rust): one score from seven dimensions: separation of integration and operation functions; complexity (cognitive, cyclomatic, nesting, length, magic numbers, `unsafe`); duplication and dead code; cohesion (LCOM4); coupling and cycles; test quality (assertion density); architecture (layer rules, forbidden edges).
  - Techniques: parsing with `syn`; optional coverage input; fails on regression against a saved baseline.
- **pyscn and polyscan**: [pyscn](https://github.com/ludo-technologies/pyscn), [polyscan](https://github.com/ludo-technologies/polyscan)
  - Metrics: dead code, clone types 1–4, cyclomatic and cognitive complexity, hotspots, circular imports, layer violations, CBO and LCOM4; 0–100 score with a grade. polyscan covers Rust.
  - Techniques: Go with tree-sitter.
- **no-mistakes**: [github.com/kunchenguid/no-mistakes](https://github.com/kunchenguid/no-mistakes)
  - Metrics: none; a pass/fail pipeline.
  - Techniques: a git proxy in front of the remote has a coding agent review, test, document and lint the branch before it is pushed.

`products.md` lists smaller projects (SlopCheck, vibecop, KarpeSlop, agent-slop-lint, brooks-lint, guard-skills and others). Three of them write rules for a codebase: Wispbit (closed source) derives rules from patterns in the code, archprint infers import rules for TypeScript, and gap-trap has an agent write rules and ratchets.

### Code quality platforms with scores

- **SonarQube**: [sonarsource.com](https://www.sonarsource.com/plans-and-pricing/)
  - Metrics: issues by security, reliability and maintainability with severities; cyclomatic and cognitive complexity; duplication; coverage; technical debt (sum of remediation minutes) and debt ratio; A–E ratings.
  - Techniques: rule-based static analysis per language; for Rust it computes complexity and imports Clippy output and coverage. Pass/fail gates on new code.
- **CodeScene**: [codescene.com](https://codescene.com/pricing)
  - Metrics: Code Health per file from 25+ factors, among them low cohesion (LCOM4), brain class, brain method, nested complexity, cyclomatic complexity, large method, primitive obsession, duplicated logic that changes together, developer congestion and complex code by former contributors; hotspot and average Code Health.
  - Techniques: syntax analysis plus git history mining (hotspots, change coupling, ownership). Supports Rust.
- **Qlty Cloud** (successor of Code Climate Quality): [qlty.sh](https://qlty.sh/pricing); CLI [github.com/qltysh/qlty](https://github.com/qltysh/qlty)
  - Metrics: code smells (duplication, many parameters, complex boolean logic, file and function complexity, deep nesting, many returns); cognitive and cyclomatic complexity; duplication; remediation minutes; debt ratio against a COCOMO estimate of rewrite effort; A–F grade; diff coverage.
  - Techniques: its own smell analysis plus 60+ linter plugins (Clippy and rustfmt for Rust).
- **Codacy**: [codacy.com](https://www.codacy.com/pricing)
  - Metrics: issues by category, issues per thousand lines, cyclomatic complexity, clones, coverage; an A–F grade from an unpublished weighted average.
  - Techniques: bundled third-party analyzers (Opengrep and Trivy for Rust).
- **SIG Sigrid**: [softwareimprovementgroup.com](https://www.softwareimprovementgroup.com/?p=40154); docs [github.com/Software-Improvement-Group/sigridci](https://github.com/Software-Improvement-Group/sigridci)
  - Metrics: volume, duplication, unit size, unit complexity, unit interfacing, module coupling, component entanglement and component independence; 1–5 stars.
  - Techniques: static analysis with ratings calibrated against "a benchmark of 25,000 industry systems".
- **GitHub Code Quality**: [docs](https://docs.github.com/en/code-security/concepts/about-code-quality)
  - Metrics: reliability and maintainability findings and line coverage; the repository rating is set by the most severe finding.
  - Techniques: CodeQL rules for seven languages (no Rust) plus AI analysis of recently changed code; pull-request gates on severity and coverage drop.
- **Teamscale**: [teamscale.com](https://teamscale.com/)
  - Metrics: findings from 500+ checks, clones, architecture conformance, untested changes (test gaps).
  - Techniques: static analysis, clone detection, architecture analysis, Test Gap Analysis, LLM review agents.
- **NDepend** (.NET): [ndepend.com](https://www.ndepend.com/docs/code-metrics)
  - Metrics: lines of code, afferent and efferent coupling, relational cohesion, instability, abstractness, distance from the main sequence, LCOM, cyclomatic complexity, nesting, inheritance depth, ABC, Halstead volume, Maintainability Index, coverage, technical debt.
  - Techniques: analysis of source and compiled IL; custom rules as CQLinq queries.
- **TIOBE Quality Indicator**: [tiobe.com](https://www.tiobe.com/quality-standards/tqi/)
  - Metrics: one score from eight weighted metrics: coverage 20%, abstract interpretation 20%, security 15%, compiler warnings 15%, cyclomatic complexity 10%, coding standards 10%, duplication 5%, fan-out 5%.
  - Techniques: per-metric mappings to 0–100 fitted to the code TIOBE analyzes.
- **CAST Highlight**: [doc.casthighlight.com](https://doc.casthighlight.com/?p=8703)
  - Metrics: Software Health, the plain average of resiliency, agility and elegance scores.
  - Techniques: "hundreds of code insights across 20+ technologies".
- **GitClear**: [gitclear.com](https://www.gitclear.com/ai_assistant_code_quality_2025_research)
  - Metrics: changed lines classified as copy/pasted, moved, refactoring-related and short-term churn.
  - Techniques: git history analysis. Its own research reports copy/pasted lines rising from 8.3% (2021) to 12.3% (2024) of changed lines.
- Axivion, Squore and Kiuwan cover architecture, clones, cycles, metrics and standards compliance, mainly for safety-critical and enterprise code (`products.md`).

### Adjacent tools

Links and one-line descriptions are in `products.md` sections 3 to 5.

- Architecture-rule checkers: ArchUnit (Java), dependency-cruiser and eslint-plugin-boundaries (JavaScript, TypeScript), Import Linter and Tach (Python), Packwerk (Rails), Deptrac (PHP), go-arch-lint; for Rust cargo-pup (Datadog), arch-lint, crawk, Clippy's `disallowed-*` lints, Dylint and cargo-deny.
- Pattern rule engines: Semgrep, Opengrep, ast-grep, CodeQL, GritQL, Comby.
- Ratchets and diff filters: Betterer, reviewdog, Danger.
- AI review tools with project rules in plain language: CodeRabbit, Greptile, Cursor Bugbot, Qodo, Sourcery, Claude Code Code Review, Codex review, Copilot code review, Gemini Code Assist, Kodus, PR-Agent.
- Rust quality tools: Clippy, rust-code-analysis, cargo-geiger, cargo-mutants, cargo-semver-checks, cargo-public-api, cargo-llvm-cov, tarpaulin, cargo-crap, debtmap, cargo-audit, cargo-vet, cargo-udeps, cargo-machete, cargo-modules, Kani.

## 2. Metrics

`metrics.md` is the full catalogue. For each metric it gives a definition precise enough to compute it, its origin, a Rust tool that computes it, the validity evidence found, and whether it can be computed on changed code alone. This section lists the metrics by family and summarizes the evidence.

### What the evidence says across families

- **Size is the main confound.** "After controlling for size none of the metrics we studied were associated with fault-proneness anymore" ([El Emam et al. 2001](https://www.ehealthinformation.ca/web/default/files/wp-files/1062.pdf)). A review of 106 fault-prediction studies concludes that "complexity metrics are essentially a size measurement" ([Radjenović et al. 2013](https://gup.ub.gu.se/file/127150)).
- **History metrics predict defects best.** The same review rated code churn, number of changes, module age and change-set size highest, and found that "Process metrics seem to be better at predicting post-release faults compared to any static code metrics". On 700 GitHub projects, the best history-based models reached a median recall of 98% against 44% for models built from code metrics ([Majumder et al. 2022](https://arxiv.org/abs/2008.09569)). These metrics describe files with a history; a new file or a single change has little.
- **Mutation score is the best-supported test metric.** Detecting mutants correlates with detecting real faults independently of coverage ([Just et al. 2014](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf)). Coverage correlates only weakly to moderately with test effectiveness once the number of tests is controlled ([Inozemtseva & Holmes 2014](https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf)).
- **Weak or no evidence:** readability and understandability metrics ("none of the 121 experimented metrics is able to capture code understandability", [Scalabrino et al. 2019](https://www.cs.wm.edu/~denys/pubs/TSE%2719-Understandability.pdf)); Halstead measures, inheritance depth and LCOM; static-analysis warning counts and SonarQube debt items ([Trautsch et al. 2023](https://doi.org/10.1007/s10664-023-10301-2)); most architecture metrics, which only their authors validated; metrics for AI-generated code and agent pull requests, which come from single studies of 2025 and 2026.
- **Rust.** rust-code-analysis computes only basic size, complexity, Halstead and Maintainability Index metrics for Rust, and its last release was in January 2023. No tool computes object-oriented or architecture metrics for Rust directly; they can be computed from the graphs that `cargo metadata` and cargo-modules output. For `unsafe` code, panic sites and Clippy warnings, the evidence gives only the share of known bugs that involve them; no study relates their density to defects.

### Metrics by family

1. **Size.** Physical lines; non-comment lines (NCLOC); logical lines or statements (LLOC); comment and blank lines; number of functions, types and files; function length; parameters per function; exit points; token count; ABC size; Automated Function Points and Enhancement Points. Evidence: a moderate defect predictor and the confound for the other families; "Only system size and low cohesion were strongly associated with increased maintenance effort" in a comparison of four equivalent systems ([Sjøberg et al. 2012](https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.anda.mockus.esem.2012.pdf)).
2. **Function-level complexity.** Cyclomatic complexity and cyclomatic density; essential, design and integration complexity; NPATH; cognitive complexity; Halstead measures; nesting depth; knots; information-flow complexity (Henry–Kafura); fan-in and fan-out; system complexity (Card and Agresti); DepDegree; Boolean expression complexity; construct counts per function. Evidence: tracks size; no single metric captures understandability.
3. **Object-oriented coupling, cohesion and inheritance.** CBO and variants; RFC; WMC; class fan-in and fan-out; MPC and DAC; ICP; the Briand et al. coupling measures; CTA and CTM; access to foreign data (ATFD); MOOD coupling factor; LCOM1–LCOM5, TCC and LCC, ICH, conceptual cohesion (C3), LSCC; DIT and NOC; encapsulation measures (MHF, AHF, DAM and others); the QMOOD design metrics. Evidence: CBO, RFC and WMC are the best of the group, and coupling beats inheritance and cohesion; El Emam et al. found no association left after controlling for class size. Rust has no class inheritance, and no tool computes these for Rust.
4. **Module and architecture structure.** Afferent and efferent coupling, instability, abstractness and distance from the main sequence (Martin); dependency cycles; dependencies to remove; Structural Debt Index; CCD, ACD and NCCD; propagation cost; core size; Decoupling Level and Independence Level; modularity violations; hotspot patterns; design rule spaces; Modularization Quality; information-theoretic modularization metrics; Component Balance; dependency profiles; SIG component independence, component entanglement and module coupling; network measures; Component Rank; architecture conformance violations; architectural smells (cyclic, hub-like and unstable dependencies, god component); Architectural Technical Debt Index. Evidence: mostly validated only by the groups that proposed them.
5. **Code smells.** Smell count and density; God Class and Data Class; Designite design and implementation smells; CodeScene Code Health smells; Qlty structure checks; exception-handling anti-patterns; dead code. Evidence: conflicting. A large mining study links smells to change- and fault-proneness ([Palomba et al. 2018](https://doi.org/10.1007/s10664-017-9535-z)); a controlled experiment with professional developers found no effect on maintenance effort once file size and number of changes were controlled ([Sjøberg et al. 2013](https://doi.org/10.1109/TSE.2012.89)).
6. **Duplication.** Duplicated lines, blocks and files; clone types 1 to 4; inconsistent changes to clones; duplicates that change together; duplicated parameter lists. Evidence: mixed. Inconsistent changes to clones often cause faults, while most bugs are not associated with clones.
7. **Static-analysis findings and technical debt.** Warning count and density; issues by type and severity; issues on new code; remediation effort and debt ratio; relative warning density; effective false-positive rate; fix rate of findings; suppression count; fault-proneness per rule. Evidence: warning counts relate weakly or not at all to defects; findings shown on the diff get fixed far more often than batch reports (section 3).
8. **Security.** Static-analysis security findings; CWE weakness counts (ISO/IEC 5055); share of security hotspots reviewed; vulnerability prediction metrics; attack surface. Evidence: vulnerability prediction models have outcome data; tool counts depend on tool recall, which is low for Rust analyzers.
9. **Readability, understandability and naming.** Readability models of Buse and Weimer, Posnett et al., Dorn, Scalabrino and Mi; LLM-judged readability; understandability metric sets; identifier form; identifier naming flaws; linguistic antipatterns. Evidence: weak; LLM readability ratings agree weakly with humans.
10. **Naturalness.** Cross-entropy of code under a language model; line entropy ranking. Evidence: one group of overlapping authors links entropy to defects; no replication.
11. **Comments and documentation.** Comment density; documentation coverage; missing sections in API documentation; comment quality models; self-admitted technical debt (SATD); spelling errors in doc comments. Evidence: none relating documentation to defects or effort; SATD shows no link to defects.
12. **Test quality.** Line, branch, condition, region, function and MC/DC coverage; patch (diff) coverage; mutation score, also limited to the diff; pseudo-tested methods; checked coverage; assertion count and density; test smells; flaky-test rate; test counts, failures, skips and duration; test gaps; test code quality model; test set diameter. Evidence: see above. Results differ for test suites written by LLMs.
13. **Process and history.** Number of changes; absolute and relative churn; code age; change-set size; code delta; past faults; number of developers; entropy of changes; Moser change metrics; change coupling; hotspots; code ownership; organizational metrics; socio-technical congruence; truck factor; team stability; code review coverage and participation. Evidence: the strongest defect predictors (above).
14. **Change-level (just-in-time).** Kamei change metrics (size, spread, history, author experience); Mockus–Weiss change measures; lines added as the only predictor; line-level risk (JITLine); review properties of a change; Meta's Diff Risk Score. Evidence: moderate accuracy; change size is the most stable predictor; models lose accuracy within months. Author-experience features describe a person and lose their meaning when an agent writes the change (inference).
15. **Dependencies and supply chain.** Direct and transitive dependency count; duplicate and banned crates; vulnerable, unmaintained and yanked dependencies; licence and source violations; dependency freshness (libyear) and technical lag; unused dependencies and feature flags; audit coverage; OpenSSF Scorecard checks. Evidence: outdated dependencies relate to security issues in one industry benchmark; the rest are policy checks without outcome studies.
16. **Rust-specific.** `unsafe` usage counts; undocumented `unsafe` blocks; panic sites; Clippy warnings by lint group; lint suppressions; type complexity; size limits on functions and types; clone and shared-mutability patterns; compiler warnings; public API size and semver violations; build cost; feature-combination failures; Miri and proof results. Evidence: see above. In C-to-Rust translations of GNU coreutils programs, Clippy "either (i) reported the underlying problems under different labels or (ii) did not emit any lint at all" for problems such as panic risk ([Tadesse et al. 2026](https://arxiv.org/abs/2602.00840)).
17. **Composite models and indices.** Maintainability Index; the SIG maintainability model; Delta Maintainability Model; SQALE and the SonarQube ratings; Qlty debt ratio and grades; CodeScene Code Health; GitHub Code Quality ratings; Quamoco; QMOOD quality attributes; ColumbusQM; Squale; ISO/IEC 25010 and 25023 measures; CISQ measures and the Automated Technical Debt Measure; CAST technical debt; CRAP; debtmap priority score; Sonargraph Maintainability Level. Evidence: section 3.
18. **AI-generated code.** pass@k; resolved rate on repository tasks (SWE-bench); CodeBLEU and CodeBERTScore; LLM-judge scores; multi-dimensional benchmarks (RACE, NoFunEval); efficiency of generated code; vulnerability rate; package hallucination rate; static-analysis issues in generated code; structural erosion and verbosity across iterations; redundancy across rounds; resolve rate on agent-written code; GitClear repository metrics; issue introduction and survival. Evidence: after Cursor adoption, "Static analysis warnings increase by 30% and code complexity increases by 41% post-adoption", although adopters "may not necessarily introduce more code quality issues than non-adopting projects moving with the same velocity" ([He et al.](https://arxiv.org/abs/2511.04427)); after coding-agent adoption, warnings and cognitive complexity rose "by roughly 18% and 39%" ([Agarwal et al. 2026](https://arxiv.org/abs/2601.13597)). About half of test-passing SWE-bench Verified patches would not be merged by maintainers ([METR 2026](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/)).
19. **Agent pull requests.** Merge rate and review latency; revert rate; follow-up fix rate; new static-analysis issues per changed thousand lines; test inclusion and changed-line coverage; test oracle strength; test addition, modification and deletion; redundancy and missed reuse; security smells; reviewer approval and comment volume over time; cheating rate. Most studies use the AIDev dataset of agent-authored pull requests ([Li, Zhang & Hassan 2025](https://arxiv.org/abs/2507.15003)). Evidence: results depend on normalization; per-churn issue rates remove most differences between agents ([Cynthia et al. 2026](https://arxiv.org/abs/2601.20109)). No replications yet.
20. **Outcomes used to validate metrics.** Fault-proneness, fault count and density; defect-inducing changes; change-proneness; maintenance effort; issue resolution time; comprehension; vulnerabilities; production incidents; delivery performance (DORA); maintainer merge decisions; mutant detection. "Validity" in `metrics.md` means association with one of these.

## 3. From measurements to gates and a score

All claims in this section are sourced in `scoring.md`; the links below are the main ones.

### Measuring only the changed code

Measuring the code a change touched is established practice:

- SonarQube applies only its "new code" conditions to pull requests ([docs](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/)).
- CodeScene and Sigrid compare each changed file before and after the change. CodeScene can fail the check "for any file where the code health declines" ([CodeScene](https://codescene.com/use-cases/automate-code-reviews), [Sigrid](https://docs.sigrid-says.com/capabilities/system-delta-quality.html)).
- Qlty SlopOne compares changed files with the merge base and marks a file as declined when its score drops by more than `--max-drop` (default 1 point). It has an `agent` trigger and prints instructions for the coding agent for each declined file ([CLI docs](https://docs.qlty.sh/cli/commands/slop-one)).
- Diff coverage ([diff-cover](https://github.com/Bachmann1234/diff_cover), Codecov patch status), mutation testing limited to the diff ([`cargo-mutants --in-diff`](https://mutants.rs/in-diff.html)), and the Delta Maintainability Model, which scores the share of low-risk lines in a change ([di Biase et al. 2019](https://zenodo.org/records/2606632/files/deltamaintainability.pdf); open implementation in [PyDriller](https://pydriller.readthedocs.io/en/latest/deltamaintainability.html)).
- Just-in-time defect prediction scores the risk of each change ([Kamei et al. 2013](https://doi.org/10.1109/TSE.2012.70)). Meta uses such a risk score in production to decide which changes, including AI-generated ones, may land with deferred or no human review ([Adams et al. 2026](https://arxiv.org/abs/2605.30208)).

The dilution you described is measured. In SIG's maintainability model, a 200-line bug fix moved the system rating by −0.007 on a scale from −5 to 5, and SIG designed the model that way on purpose ([di Biase et al. 2019](https://zenodo.org/records/2606632/files/deltamaintainability.pdf)). For coverage, 100 changed lines in a project of a million lines move the percentage by 0.01 points ([Hilton et al. 2018](https://mir.cs.illinois.edu/marinov/publications/HiltonETAL18TestCoverageEvolution.pdf)).

Change-level numbers have their own problems:

- Ratios swing on small changes. SonarQube ignores its coverage and duplication conditions until a change has 20 new lines.
- Coverage and mutation scores vary between identical runs; mutation scores by about four percentage points on average ([Shi et al. 2019](https://mir.cs.illinois.edu/marinov/publications/ShiETAL19FlakyMutation.pdf)).
- Size predicts most quality judgments. Against expert maintainability labels for 304 files, a plain line count scored as well as CodeScene's Code Health (AUC 0.95 for both); SonarQube's debt ratio scored 0.60 ([Borg et al. 2024](https://arxiv.org/abs/2408.10754)). After controlling for class size, El Emam et al. found no object-oriented metric associated with faults ([TSE 2001](https://doi.org/10.1109/32.935855)); later work found the size effect weaker for some metrics ([Tahir et al. 2021](https://arxiv.org/abs/2106.04687)).
- Ratios and averages cannot be added up across changes. Counts and costs can, such as violations, remediation minutes, lines in high-risk functions, or killed and surviving mutants (inference).

### Deciding what blocks

Tools separate blocking findings from the rest in four ways, often combined: they check only new or changed code; they block at or above a severity level; they block when a value gets worse; or they record existing violations in a baseline file and block only new ones (ArchUnit `FreezingArchRule`, ESLint bulk suppressions, dependency-cruiser `--baseline`, Betterer).

Google published its criteria for checks that break the build: easy to understand, actionable and easy to fix, no effective false positives, and only correctness issues. Checks shown in code review may have up to 10% effective false positives; Google disables an analyzer when more than 10% of its findings are marked "Not useful" ([Sadowski et al. 2018](https://storage.googleapis.com/gweb-research2023-media/pubtools/4365.pdf)). No study measures whether blocking a class of violation improves later outcomes. Two studies found SonarQube's issue types and severity labels inconsistent with fault data ([Lenarduzzi et al., SANER 2020](https://arxiv.org/abs/1907.00376); [Lenarduzzi et al., JSS 2020](https://arxiv.org/abs/1908.11590)).

### Aggregating into one number

- Averages hide high-risk code: complexity per function follows a power law, so the average is always low ([Heitlager et al. 2007](https://www.di.uminho.pt/~joost/publications/HeitlagerKuipersVisser-Quatic2007.pdf)), and many small healthy files raise an average.
- Published alternatives: risk profiles with thresholds taken from a benchmark of other systems (SIG); weighting that amplifies low marks (Squale); remediation cost divided by size (SQALE, SonarQube, Qlty); line-weighted averages plus the worst file (CodeScene); weighted sums of benchmark-derived utilities (Quamoco).
- Evidence that any aggregate predicts outcomes is weak. System-level studies used 4 to 20 systems; the larger studies are file-level and come from the vendor. When SIG revised its model in 2018, the rating's correlation with defect resolution time fell from 0.64 to 0.33 ([Wijnmaalen et al. 2019](https://ceur-ws.org/Vol-2510/sattose2019_paper_11.pdf)). SQALE and Quamoco grades did not agree on any of three quality characteristics across 20 projects ([Griffith et al. 2017](https://www.cs.montana.edu/izurieta/pubs/ESEM_2017.pdf)).
- The weights and the aggregation method decide rankings. In the European Commission's toolkit for composite indicators, three aggregation methods with the same equal weights ranked the same countries very differently ([Nardo et al. 2005](https://knowledge4policy.ec.europa.eu/sites/default/files/eur_21682_en_1.pdf)).
- A weighted sum lets a gain in one component offset a loss in another. SIG's certification sets minimum ratings that a high score elsewhere cannot offset, and SonarQube's reliability rating is set by the worst open issue.

### Budgets for decline

- Existing caps: Codecov's `threshold` and Coveralls' decrease threshold allow coverage to fall by a set amount per pull request; Qlty SlopOne's `--max-drop` caps the drop per changed file. CodeScene's decline gate, Betterer and ArchUnit's frozen rules allow no decline at all. I found no evaluation of any per-change or per-period quality budget.
- SRE error budgets, the closest model, depend on a measurement "by a neutral third party: our monitoring system" ([Google SRE book](https://sre.google/sre-book/embracing-risk/)).
- A cap smaller than the run-to-run noise of the score fails at random (inference). One project set its Codecov threshold at 0.15 after observing 0.12 variation from timing alone ([AnkiDroid](https://github.com/ankidroid/Anki-Android/blob/main/.codecov.yml)).
- Cumulative decline under agents has been measured. When agents repeatedly extended their own code, structural erosion rose in 77% of runs; quality instructions reduced the initial erosion by up to a third without changing the rate of decline; human-written repositories degraded less often and by smaller margins ([SlopCodeBench, Orlanski et al. 2026](https://arxiv.org/abs/2603.24755)).

### Gaming

- Agents game tests. On SWE-bench tasks altered so that the tests contradict the specification, GPT-5 passed by cheating on 76% of tasks; Claude models cheated mainly by editing the tests ([ImpossibleBench](https://arxiv.org/abs/2510.20270)). METR and Anthropic report special-casing of test inputs and edited tests ([METR](https://metr.org/blog/2025-06-05-recent-reward-hacking/), [Claude 3.7 Sonnet system card](https://assets.anthropic.com/m/785e231869ea8b3b/original/claude-3-7-sonnet-system-card.pdf)).
- Feedback from static analyzers improved the measured violations far more than correctness ([Blyth et al. 2025](https://arxiv.org/abs/2508.14419)). An agent that was allowed to change lint thresholds raised the cyclomatic complexity threshold ([Böckeler 2026](https://martinfowler.com/articles/sensors-for-coding-agents.html), one practitioner's report). No study measures agents gaming static quality scores at scale.
- A gate configuration, threshold or baseline stored in the repository can be changed by the pull request it checks. CodeScene, for example, uses the gate configuration from the pull request's branch.
- Reported countermeasures: keep the measurement and its configuration outside the agent's control; make tests read-only or flag edits to tests; count suppressions and threshold changes as findings; check test strength with mutation testing.

### Reporting

- Report findings in the pull request. At Facebook, the same Infer analysis had a fix rate near zero as a nightly report and over 70% when posted on the diff ([Distefano et al. 2019](https://discovery.ucl.ac.uk/10084236/1/O%27Hearn%20AAM%20scaling-static-analysis-at-facebook.pdf)).
- Flags that developers cannot clear get ignored. Google's file-level bug prediction produced no identifiable change in behavior for that reason ([Lewis et al. 2013](https://static.googleusercontent.com/media/research.google.com/en//pubs/archive/41145.pdf)). A score defined relative to other files (for example the worst 10%) can never be cleared; an absolute threshold can (inference).
- Dashboards outside the review workflow saw little use at Google ([Sadowski et al. 2018](https://storage.googleapis.com/gweb-research2023-media/pubtools/4365.pdf)).

## 4. What Geiger could sell

### What free tools already do

Section 1 shows that the parts you called cheap already exist, most of them free and released in 2026:

- one score for agent-written code: desloppify, aislop, sentrux, fallow, pyscn and polyscan, and rustqual for Rust;
- checks limited to changed code: aislop, fallow, `--changed` in crapper, dryer and mutator, the CodeScene MCP server, Sonar, SIG Guardrails;
- a cap on the score drop per changed file, aimed at agents: Qlty SlopOne `--max-drop`;
- user-defined layer and dependency rules: sentrux, fallow, rustqual, and for Rust also cargo-pup, arch-lint, crawk and Dylint;
- agent integration through hooks and MCP servers: aislop, sentrux, fallow, CodeScene, Sonar Vortex, SIG Guardrails, Codacy Guardrails;
- rules derived from a codebase or written by an agent: Wispbit, archprint, gap-trap.

This supports your assessment that the runner and the plug-in system are not the product.

### What is missing

1. **Evidence that a score predicts anything for agent-written code.** desloppify's README says a score above 98 "should correlate with a codebase a seasoned engineer would call beautiful"; Qlty has not published SlopOne's methodology; SIG's result for Guardrails comes from one vendor experiment of 20 runs. None of the agent-focused tools in section 1 publishes outcome data for its weights and thresholds (agent-slop-lint cites literature for its defaults). Research support for aggregate scores is weak, and size explains much of what they predict (section 3).
2. **Rules for a specific architecture.** The tools offer generic presets (layered, hexagonal, clean, feature-sliced). Rules specific to one codebase, such as signature conventions, file layout or the structure of an entity-component system, fit no preset.
3. **A measurement the agent cannot change.** Agents edit tests and thresholds, and most tools read their gate configuration from the repository under test (section 3).

### Precedents for selling such things

- **Calibrated ratings.** SIG rates systems against "a benchmark of 25,000 industry systems" ([sigridci README](https://github.com/Software-Improvement-Group/sigridci)) and certifies maintainability with TÜV NORD CERT ([evaluation criteria](https://www.softwareimprovementgroup.com/wp-content/uploads/SIG-TUViT-Evaluation-Criteria-Trusted-Product-Maintainability.pdf)). Its metrics (duplication, unit size, complexity, coupling) are standard; the benchmark and its calibration are SIG's own (inference).
- **Rules as the licensed asset.** In late 2024 Semgrep re-licensed its maintained rules so that they are "available only for internal, non-competing, and non-SaaS contexts" ([Semgrep blog](https://semgrep.dev/blog/2024/important-updates-to-semgrep-oss/)). Several security vendors then forked the engine as Opengrep, "created when Semgrep moved critical features behind a commercial licence" ([Opengrep](https://github.com/opengrep/opengrep)). Sonar's analyzer licence allows only a "Non-competitive Purpose", and Qlty's CLI licence forbids use for "a Code Quality Service" or "an Artificial Intelligence Coding Service" (`products.md`). Inference: vendors in this market protect rules and analyzers by licence because the engines are easy to rebuild.
- **Method with free tools.** Uncle Bob's ub-mode bundles his engineering principles with crapper, dryer and mutator; all are free.

### Options

| Option | What is sold | Cost | Defensibility |
| --- | --- | --- | --- |
| A. Method | "Metric-driven agentic coding" as a published method, with an open runner and one encoded rule set as the reference case; income from consulting, training or writing | Low | Low. The term is free (section 5). Thoughtworks, Addy Osmani and Uncle Bob already publish on the practice under other names |
| B. Architecture rules | Turning a team's architecture documents into enforced checks, with exceptions and a block-or-score decision per rule; as a service or as maintained packs per stack | Medium | Medium. Rule generators (Wispbit, archprint, gap-trap) and AI reviewers with plain-language rules (CodeRabbit, Qodo, Bugbot) cover simpler cases |
| C. Validated score | Data linking measurements of agent changes to outcomes (reverts, rework, rejected reviews, later churn), used to choose metrics, weights and per-change budgets; sold as calibrated ratings or certification | High: needs many repositories with history | High. No agent-focused tool publishes such data |
| D. Tamper-resistant gate | Hosted measurement whose configuration, baselines and budgets the agent cannot edit, and which reports suppressions and threshold changes | Medium | Low. Competes with Sonar, CodeScene, Qlty Cloud, Codacy, DeepSource and GitHub Code Quality ($10 per committer per month) |

### Recommendation

Sell B under the name from A, and build C over time.

- The technique alone (A) is easy to copy, and free tools already implement it. Its name is unused and can identify the offer.
- B builds on what you already have: written architecture rules for your own projects. Most such rules are yes/no conditions that existing engines can check (compiler lints, dependency-graph checks, syntax rules, file layout, tests); the work lies in deciding the rules and their exceptions, which generic presets do not cover. A first test: encode one project's rules with existing engines, use them as the reference case, and offer the same encoding to a few teams that use agents. Whether they pay answers whether B is a product.
- C answers the question every tool in section 1 leaves open: whether its score measures anything. It is the only option that would give Geiger something competitors lack, and it takes the longest.
- D belongs inside B as a requirement: keep gate configuration, baselines and budgets out of the agent's reach. As a separate product it competes with established platforms.

## 5. The term "metric-driven agentic coding"

Nobody uses the term. Hacker News search returned no hits for the phrase or its variants, and web searches found no page, product, repository or talk that uses it (`products.md` section 6; Reddit, X and LinkedIn were not searched).

- The closest phrase is a critical Hacker News comment of 2026-05-03 on a story about Uncle Bob: "I found metric driven agentic refactors just push complexity to outside the scope of the metric." ([comment](https://news.ycombinator.com/item?id=47999904))
- "Metrics-driven development" is a DevOps term from 2012 to 2016 for steering development with production telemetry such as performance, usage and revenue ([InfoQ 2012](https://www.infoq.com/articles/metrics-driven-development/)).
- The practice itself is discussed under other names: "quality gates" ([Addy Osmani, 2026](https://addyosmani.com/blog/agentic-code-quality/)); "harness engineering" with "computational sensors" and fitness functions ([Birgitta Böckeler, Thoughtworks, 2026](https://martinfowler.com/articles/harness-engineering.html)); agents refactoring until a complexity threshold or a Code Health target is met ([Tweag 2025](https://www.tweag.io/blog/2025-10-23-agentic-coding-intro/); CodeScene and loveholidays at TechDebt 2026).

The name Geiger is taken in the Rust ecosystem. [cargo-geiger](https://github.com/geiger-rs/cargo-geiger) counts `unsafe` usage in a crate and its dependencies, uses the same radiation image (☢️ in its title), and has 1,664 stars and 270,185 downloads; the crate name `geiger` belongs to it. An npm package, `geiger-scan`, calls itself "A Geiger counter for AI agents".

## 6. Unverified points and open questions

### Not verified

- Products: the search used GitHub keyword search, Hacker News and vendor documentation; Reddit, X and LinkedIn were not searched. Vendor documentation describes intended behavior, and no tool was run. Star counts and prices are as of 2026-11-08.
- Metrics: the mapping study by Nuñez-Varela et al. (2017) could not be retrieved; the SciTools Understand documentation was unavailable, so its Rust support is unknown; some definitions are unverified (Lorenz–Kidd, MOOD and QMOOD formulas, Modularization Quality, core size, Moser's metrics, GitClear's metrics). Details in `metrics.md`.
- Scoring: two practitioner posts on technical-debt budgets returned errors; the original SIG study of issue resolution (Bijlsma et al. 2012) was read only through its replication; a claim of fewer defects after introducing SonarQube gates could not be checked. Details in `scoring.md`.
- Rust: no study relates the density of `unsafe` code, panic sites or Clippy warnings to defects, and there are no published distributions of metrics across crates.io for setting thresholds.

### Decisions for you

1. Which outcome the score should predict: reverts, follow-up fixes, rejected reviews, defect-inducing changes or maintenance effort. The choice decides which metrics and weights can be validated.
2. Whether gate configuration, baselines and budgets live outside the repository the agent works in.
3. Whether Rust is the first target. Sonar Vortex, SIG Guardrails and GitHub Code Quality do not analyze Rust; rustqual, polyscan, crapper and desloppify do.
4. Whether to keep the name Geiger given cargo-geiger.
