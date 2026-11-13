# Existing products and the term "metric-driven agentic coding"

Research for the Geiger report, 2026-11-08. Every claim below comes from a source opened on 2026-11-08 and linked next to it, except claims marked (unverified). Star counts come from the GitHub API on 2026-11-08. Marks:

- **(unverified)**: the source could not be opened or did not contain the statement; the claim is a lead only.
- **(description only)**: taken from the GitHub repository description or a launch post; the project was not examined further.
- Quotations are exact.

Sections 1 and 2 give these fields per entry: link, what it measures, how it measures, how it reports, whether it can evaluate only the changed code of a pull request, how users add their own rules, and licence and business model. Sections 3 to 5 give one or two lines per entry. Section 6 covers the term and name collisions. Section 7 lists the limits of the search.

---

## 1. Tools built for code written by AI agents

Search method: GitHub repository search (keywords "slop", "deslop", "aislop", "slop detector", "slop linter", "slop scanner", "vibe code quality", "quality gate coding agents", "AI-generated code quality", "code health score agents", "claude code hook quality gate", "technical debt AI coding agents", "CRAP metric", topic `ai-slop`), Hacker News "Show HN" search through the Algolia API, Product Hunt through web search, and vendor documentation. Most "slop" repositories on GitHub target prose or UI design; those are left out.

### desloppify

[github.com/peteromallet/desloppify](https://github.com/peteromallet/desloppify) · 4,094 stars · created 2026-02-11

- **Measures:** a 0–100 "health score" from two pools. Mechanical dimensions: File health, Code quality, Duplication, Test health, Security. Subjective dimensions: High, Mid and Low elegance, Contracts, Type safety, Design coherence, Abstraction fit, Logic clarity, Structure nav, Error consistency, Naming quality, AI generated debt ([docs/scoring.md](https://github.com/peteromallet/desloppify/blob/main/docs/scoring.md)).
- **Technique:** "mechanical detection (dead code, duplication, complexity) with subjective LLM review (naming, abstractions, module boundaries)" ([README](https://github.com/peteromallet/desloppify/blob/main/README.md)). The mechanical pool weighs 25%, the LLM pool 75%. Mechanical dimension score = ((potential − weighted_failures) / potential) × 100; issue weights by detection confidence are 1.0, 0.7 and 0.3; dimensions with fewer than 200 checks get reduced weight; test, config, generated and vendor files are excluded ([scoring.md](https://github.com/peteromallet/desloppify/blob/main/docs/scoring.md)). The Rust plugin integrates `cargo clippy`, `cargo check` and `cargo rustdoc` and uses "best-effort Rust source parsing" ([Rust plugin README](https://github.com/peteromallet/desloppify/blob/main/desloppify/languages/rust/README.md)).
- **Reports:** a lenient and a strict score (strict also counts issues marked `wontfix`), per-dimension scores, and a work queue the agent runs through: scan → score → review → triage → execute → rescan. The README calls the score "a north-star" for the agent and says "A score above 98 should correlate with a codebase a seasoned engineer would call beautiful." The scoring doc says "Scores from different codebases are not directly comparable."
- **Changed code only:** no. "True incremental or diff-only scanning is not the supported model yet; compare full-codebase results across runs or enforce a project-level threshold." ([README](https://github.com/peteromallet/desloppify/blob/main/README.md))
- **Own rules:** project-local Python plugins in `.desloppify/plugins/*.py`, loaded only when `trust_plugins` is set or `DESLOPPIFY_TRUST_PLUGINS=1` ([discovery.py](https://github.com/peteromallet/desloppify/blob/main/desloppify/languages/_framework/registry/discovery.py)).
- **Licence and business model:** Open Source Native License 0.2, source-available. Free for internal use, including by companies. A fee applies only when a company that is not open source redistributes it in a product or service: $1,000 per month from $1M funding or revenue, $5,000 from $10M revenue, $10,000 from $100M revenue ([LICENSE](https://github.com/peteromallet/desloppify/blob/main/LICENSE)).

### aislop (scanaislop)

[github.com/scanaislop/aislop](https://github.com/scanaislop/aislop) · 730 stars · v0.20.0

- **Measures:** findings from six engines: Formatting, Linting, Code Quality (function and file size limits, deep nesting, unused files and dependencies, unused declarations), AI Slop ("Narrative comments, trivial comments, dead patterns, unused imports, `as any`, `console.log` leftovers, TODO stubs, generic names"), Security (eval, innerHTML, injection, unsafe deserialization, dependency audits), Architecture (opt-in: "Custom import bans, layering rules, required patterns") ([README](https://github.com/scanaislop/aislop/blob/main/README.md)).
- **Technique:** runs existing formatters and linters (for Rust: `cargo fmt`, Clippy) plus its own pattern and syntax-tree rules. "Deterministic: no LLM in the runtime path, same code in, same score out." Each finding's severity penalty is multiplied by an engine weight and a rule impact tier, capped per rule (`maxPerRule: 40`), and the total uses "logarithmic scaling with issue-density normalization" relative to the number of files ([docs/scoring.md](https://github.com/scanaislop/aislop/blob/main/docs/scoring.md)).
- **Reports:** "Scores every change 0–100", score labels, SARIF, CI exit codes, agent hooks for Claude Code, Cursor, Gemini CLI, Codex and others, and MCP tools ([README](https://github.com/scanaislop/aislop/blob/main/README.md)). Hook "Quality-gate mode: Blocks if score regresses below baseline." CI "exits 1 when the score drops below `failBelow`, or when any error-severity diagnostic is present" (default `failBelow: 70`); with a baseline it fails only on new findings ([docs/ci.md](https://github.com/scanaislop/aislop/blob/main/docs/ci.md)).
- **Changed code only:** yes. "Both `scan` and `ci` accept `--changes` and `--base`" ([docs/ci.md](https://github.com/scanaislop/aislop/blob/main/docs/ci.md)).
- **Own rules:** `.aislop/rules.yml` with `forbid_import`, `forbid_import_from_path` and `require_pattern` ([docs/rules.md](https://github.com/scanaislop/aislop/blob/main/docs/rules.md)). The import extractor handles only `.ts/.tsx/.js/.jsx/.mjs/.cjs`, `.py` and `.go` files ([matchers.ts](https://github.com/scanaislop/aislop/blob/main/src/engines/architecture/matchers.ts)); from the code, import rules do not fire on Rust files.
- **Licence and business model:** CLI under MIT, free. Hosted layer: Solo $29 per month, Studio $99 per month, more tiers above; public repository scans free ([pricing](https://scanaislop.com/pricing)).

### Uncle Bob's crapper, dryer and mutator (and ub-mode)

[crapper](https://github.com/unclebob/crapper) (211 stars) · [dryer](https://github.com/unclebob/dryer) (88) · [mutator](https://github.com/unclebob/mutator) (111) · all created 2026-09-30 · [ub-mode](https://github.com/unclebob/ub-mode) (7,252)

- **Measures:** crapper: per-function CRAP score, "CRAP = CC² × (1 − coverage)³ + CC", where CC is cyclomatic complexity; "A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested." dryer: candidate duplicate functions, scored by "Jaccard similarity of structural fingerprints", default threshold 0.82. mutator: mutation score "killed / (killed + survived)" ([crapper README](https://github.com/unclebob/crapper), [dryer README](https://github.com/unclebob/dryer), [mutator README](https://github.com/unclebob/mutator)).
- **Technique:** all three parse code with tree-sitter (their `pyproject.toml` dependencies) for Clojure, Java, Go, TypeScript, Rust and Python. For Rust, crapper "counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`." dryer normalizes away local names, field names and literals before comparing. mutator runs `cargo test` for Rust with "the Java set (`&&`/`||`, `!`, unary `-`)" of mutations and does not run mutants on uncovered lines.
- **Reports:** per-function tables and EDN snapshots under `.metrics/` that [uml-viewer](https://github.com/unclebob/uml-viewer) reads. The READMEs describe no repository-level score. crapper `--threshold 30` exits 2 when the worst score is higher; mutator exits 3 when a mutant survives.
- **Changed code only:** yes, `--changed` ("git additions and edits") in all three.
- **Own rules:** none described; thresholds are command-line flags.
- **ub-mode:** an agent skill that pairs engineering principles with these tools: "Crapper (`CRAP < 10`), Dryer (duplication `< 0.8`), Mutator (cover the uncovered, kill the survivors, delete dead code)" ([ub-mode README](https://github.com/unclebob/ub-mode)).
- **Licence and business model:** crapper, dryer and mutator under 0BSD; ub-mode under MIT; free.

### Qlty SlopOne (and the Qlty CLI for agents)

[qlty.sh/blog/introducing-slopone](https://qlty.sh/blog/introducing-slopone) (2026-09-27) · CLI at [github.com/qltysh/qlty](https://github.com/qltysh/qlty) (3,217 stars)

- **Measures:** a per-file maintainability score. Qlty says SlopOne aims to "differentiate quality, maintainable code from slop" ([blog](https://qlty.sh/blog/introducing-slopone)).
- **Technique:** "a hybrid model that combines statistics from traditional static analysis with classifications from Typesafe AI's new Jev decision model". Jev answers reviewer-style questions per file, and the answers become features for a machine-learning model ([blog](https://qlty.sh/blog/introducing-slopone)). "We'll publish the methodology and our measurements soon." The CLI has a cap on "estimated API spend ... in USD" ([slop-one docs](https://docs.qlty.sh/cli/commands/slop-one.md)).
- **Reports:** per-file scores and an HTML trends report; the CLI "exits with code 1 when a file fails the 5.0 cutoff" ([PR #2861](https://github.com/qltysh/qlty/pull/2861)). The score range is not stated in the pages read; a 1–10 range from the earlier attempt is (unverified).
- **Changed code only:** yes. `--upstream <REF>` "Compare the files changed since the merge base with REF against their versions there"; `--max-drop` is the "Largest score drop allowed before a changed file counts as declined (default: 1)"; triggers include `agent`, `pre-commit` and `pre-push` ([slop-one docs](https://docs.qlty.sh/cli/commands/slop-one.md)).
- **Own rules:** none for SlopOne. The Qlty CLI, which agents can run as "a universal 'quality gate'" through git hooks ([coding with AI agents](https://docs.qlty.sh/cli/coding-with-ai-agents.md)), accepts plugins such as ast-grep, Semgrep and ripgrep in `.qlty/qlty.toml` ([README](https://github.com/qltysh/qlty)).
- **Licence and business model:** SlopOne is a "free research preview"; "You bring your own API key for Jev" ([blog](https://qlty.sh/blog/introducing-slopone)). The CLI is under Business Source License 1.1, converting to GPLv3 on 2028-12-10; its Additional Use Grant forbids using it "for a Code Quality Service or to produce ... an Artificial Intelligence Coding Service" ([LICENSE.md](https://github.com/qltysh/qlty/blob/main/LICENSE.md)).

### CodeScene MCP server

[github.com/codescene-oss/codescene-mcp-server](https://github.com/codescene-oss/codescene-mcp-server) · platform described in section 2

- **Measures:** Code Health per file, "one numeric score from 10.0 (optimal) to 1.0 (worst)" ([tools.md](https://github.com/codescene-oss/codescene-mcp-server/blob/main/docs/tools.md)).
- **Technique:** CodeScene's Code Health analysis (25+ code factors, section 2), run locally.
- **Reports:** per-file score and review findings; `analyze_change_set` "Returns quality gates (passed/failed) and per-file verdicts (improved, degraded, or stable)"; `code_health_refactoring_business_case` with targets "5.15 (industry average), then 9.1 (top 5%), then 10.0 (optimal)" ([tools.md](https://github.com/codescene-oss/codescene-mcp-server/blob/main/docs/tools.md)).
- **Changed code only:** yes. `analyze_change_set` reviews "all files that differ between the current HEAD and a base ref"; `pre_commit_code_health_safeguard` reviews "all modified and staged files" ([tools.md](https://github.com/codescene-oss/codescene-mcp-server/blob/main/docs/tools.md)).
- **Own rules:** `rules_config_*` tools edit the Code Health rules file (`.codescene/code-health-rules.json`), which sets rule weights and thresholds ([tools.md](https://github.com/codescene-oss/codescene-mcp-server/blob/main/docs/tools.md), [Code Health docs](https://codescene.io/docs/guides/technical/code-health.html)).
- **Licence and business model:** "includes both open-source and closed-source software components" ([LICENSE](https://github.com/codescene-oss/codescene-mcp-server/blob/main/LICENSE)). Tools marked "All Users" work with a standalone licence; "The full feature set — including hotspots, technical debt goals, and code ownership — requires a CodeScene subscription" ([README](https://github.com/codescene-oss/codescene-mcp-server)). Pricing in section 2.
- **Reported use:** CodeScene and loveholidays, TechDebt 2026 industry talk (vendor co-authored): "The agents iterated on any low-CodeHealth code additions until they reached a predefined threshold, intentionally set at a high value (a perfect 10)." ([conf.researchr.org](https://conf.researchr.org/details/TechDebt-2026/TechDebt-2026-industry-track/1/Quality-Feedback-in-the-Agentic-Loop-Using-CodeHealth-Guardrails-to-Agentic-Code-Imp))

### Sonar features for agent-written code

Closed source; platform described in section 2.

- **Measures:** the "Sonar way for agentic AI" quality gate "enforces six conditions on new code": no new Reliability or Security issues of severity Low or higher, no new Maintainability issues of Medium or higher, no new Dependency Risks of Low or higher (needs the Advanced Security add-on), coverage on new code ≥ 80%, duplication on new code ≤ 3% ([quality gate doc](https://docs.sonarsource.com/sonarqube-cloud/standards/ai-code-assurance/quality-gate-for-agentic-ai.md)). The "Sonar agentic AI" quality profile focuses rules on "Security boundaries and access control", "Error-handling depth", "Hallucinated APIs and supply-chain risks", "Code duplication and structural drift", "Concurrency correctness" and "Performance patterns", for Java, JavaScript/TypeScript and Python ([quality profile doc](https://docs.sonarsource.com/sonarqube-cloud/standards/ai-code-assurance/quality-profiles-for-agentic-ai.md)).
- **Technique:** Sonar's rule-based static analysis. Sonar Vortex runs it inside the agent's loop: "Guide" injects "code intelligence, architectural awareness, coding guidelines" into the model context, "Verify" analyzes the agent's code "with full CI-level precision", "Solve" has the model fix what it introduced ([Vortex doc](https://docs.sonarsource.com/agent-centric-development-cycle/inside-your-agent-the-agentic-loop/sonar-vortex.md)). Vortex restores dependencies, compiled artifacts and type information collected during CI ([Vortex analysis doc](https://docs.sonarsource.com/agent-centric-development-cycle/inside-your-agent-the-agentic-loop/sonar-vortex-analysis.md)). The documentation also lists a Remediation Agent, a Hunter Agent and AI CodeFix ([docs index](https://docs.sonarsource.com/llms.txt)).
- **Reports:** pass/fail gate and issues; Vortex installs for Claude Code, Codex, GitHub Copilot CLI, Cursor, Devin, Antigravity and Kiro.
- **Changed code only:** yes; gate conditions apply to new code, and Vortex "analyzes the files your agent edits". Vortex analysis languages do not include Rust ([Vortex analysis doc](https://docs.sonarsource.com/agent-centric-development-cycle/inside-your-agent-the-agentic-loop/sonar-vortex-analysis.md)).
- **Own rules and licence:** see SonarQube in section 2.

### SIG Sigrid Guardrails

[softwareimprovementgroup.com/mcp](https://www.softwareimprovementgroup.com/mcp/) · docs at [docs.sigrid-says.com](https://docs.sigrid-says.com/axis/guardrails.html) · closed source

- **Measures:** maintainability (the product page names duplication, unit size, complexity and coupling) and security findings mapped to the OWASP Top 10; a separate check for architecture drift ([MCP page](https://www.softwareimprovementgroup.com/mcp/)).
- **Technique:** Sigrid's "deterministic analysis engine" called through MCP ([MCP page](https://www.softwareimprovementgroup.com/mcp/)). "The quality gate checks each file the agent changed for maintainability and security, before it reports a task done, with the `guardrails_quality_check` MCP tool"; "The architecture drift check checks the whole change for new dependencies, cycles, and bypassed facades, before you push" ([Guardrails doc](https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/axis/guardrails.md)).
- **Reports:** findings returned to the agent; usable on demand, as a pre-commit gate or as a mandatory gate after each task ([MCP page](https://www.softwareimprovementgroup.com/mcp/)).
- **Changed code only:** yes, per changed file for the quality gate; the whole change for the drift check.
- **Own rules:** not stated in the pages read.
- **Languages:** Java, Python, C/C++, C#, JavaScript, TypeScript, Kotlin, Progress ABL, PHP ([MCP page](https://www.softwareimprovementgroup.com/mcp/)).
- **Licence and business model:** commercial; no public price ("Request a free trial").
- **Vendor experiment:** SIG built the same system 20 times with Claude Sonnet 4.6, 10 runs with and 10 without Guardrails: "High-risk security findings dropped by roughly 97%"; maintainability score up about 24%; "Every guided run scored higher on maintainability than every unguided run." ([SIG blog, 2026-07-03](https://www.softwareimprovementgroup.com/?p=49333))

### Codacy Guardrails

[docs.codacy.com/codacy-guardrails](https://docs.codacy.com/codacy-guardrails/codacy-guardrails-getting-started/) · closed source

- **Measures:** issues from bundled scanners, about 30 in the VS Code-based extension, including Opengrep, Trivy, ESLint, Ruff and Bandit ([getting started](https://docs.codacy.com/codacy-guardrails/codacy-guardrails-getting-started/)).
- **Technique:** local static analysis plus a Codacy MCP server that is "installed automatically when starting the extension"; the extension creates AI rules so the agent analyzes its generated code.
- **Reports:** findings in the IDE; the page describes "blocking insecure patterns while the code is being generated".
- **Changed code only:** analyzes code as the agent generates it; pull-request metrics are in the Codacy platform (section 2).
- **Own rules:** see Codacy in section 2.
- **Licence and business model:** "built into the free Codacy IDE Extension" for VS Code, Cursor, Windsurf and JetBrains IDEs.

### DeepSource Autofix Bot and PR Report Card

[deepsource.com](https://deepsource.com/llms.txt) · closed source · site banner: "DeepSource has joined Harness."

- **Measures:** the PR Report Card "Grades every PR across five dimensions (Security, Reliability, Complexity, Hygiene, Coverage) with an aggregate letter grade (A–D) and a single focus area" ([llms.txt](https://deepsource.com/llms.txt)).
- **Technique:** "a hybrid analysis engine that combines 5,000+ deterministic static analysis rules with an AI review agent": a code graph (data flow, control flow, import graph), a static pass, a sub-agent that filters false positives, then an AI review seeded with the static findings, plus a taint-analysis sub-agent ([llms.txt](https://deepsource.com/llms.txt)). Autofix Bot, launched 2025-12-11, is "a hybrid static analysis + AI agent purpose-built for in-the-loop use with AI coding agents" ([Show HN](https://news.ycombinator.com/item?id=46237358)).
- **Reports:** letter grade per PR; "PR Quality Gates — Define guardrails and prevent PRs from merging when quality thresholds aren't met."
- **Changed code only:** yes, per pull request.
- **Own rules:** not described in the pages read.
- **Licence and business model:** free for public repositories; Team $30 per user per month ($24 billed annually) with AI review credits; Enterprise custom ([llms.txt](https://deepsource.com/llms.txt)).

### sentrux

[github.com/sentrux/sentrux](https://github.com/sentrux/sentrux) · 3,339 stars · created 2026-03-11

- **Measures:** "5 root cause metrics, one score 0–10000: modularity, acyclicity, depth, equality, redundancy" ([README](https://github.com/sentrux/sentrux)).
- **Technique:** dependency-structure analysis; "Pure Rust. Single binary"; "52 languages via tree-sitter plugins".
- **Reports:** one score plus the weakest metric (`bottleneck`), a live visualization, and an MCP server for agents.
- **Changed code only:** no; `sentrux gate --save` stores a baseline "before agent session", and `sentrux gate` compares after it.
- **Own rules:** `.sentrux/rules.toml` with `max_coupling`, `[[layers]]` and `[[boundaries]]`; `sentrux check` exits 0 or 1.
- **Licence and business model:** MIT; no paid tier described.

### fallow

[github.com/fallow-rs/fallow](https://github.com/fallow-rs/fallow) · 5,314 stars · created 2026-03-17 · agent skills at [fallow-rs/fallow-skills](https://github.com/fallow-rs/fallow-skills) (137 stars)

- **Measures:** for TypeScript and JavaScript: "Health, complexity, duplication, architecture, styling, and unused code"; "a 0 to 100 health score" with complexity hotspots, "git churn and ownership"; boundary violations with presets `bulletproof`, `layered`, `hexagonal` and `feature-sliced`; circular dependencies ([README](https://github.com/fallow-rs/fallow)).
- **Technique:** a repository graph of "modules, exports, dependencies, functions, and styling tokens", git history, and an opt-in local model for functions "with the same intent and different syntax".
- **Reports:** health score, findings, and an audit result of pass, warn or fail.
- **Changed code only:** yes. "The gate fails (exit code 1) on findings in changed files. Findings that existed before the change are excluded."
- **Own rules:** a configuration file; boundary presets.
- **Agent setup:** "`fallow agent install` sets up the agents that it detects (Claude Code, Codex, and Cursor)" with an `AGENTS.md` task map, skills and an MCP server.
- **Licence and business model:** MIT. The exit codes mention "license" errors; the business model was not checked.

### rustqual

[github.com/SaschaOnTour/rustqual](https://github.com/SaschaOnTour/rustqual) · 17 stars · crate v1.8.3

- **Measures:** "seven dimensions (IOSP, Complexity, DRY, SRP, Coupling, Test Quality, Architecture)": function separation (integration vs operation), cognitive and cyclomatic complexity, magic numbers, nesting, function length, `unsafe`, duplication and dead code, LCOM4 cohesion, module instability and cycles, assertion density and tests without a system under test, layer rules, forbidden edges and "call parity across adapters" ([README](https://github.com/SaschaOnTour/rustqual)).
- **Technique:** parses Rust with `syn` ([Cargo.toml](https://github.com/SaschaOnTour/rustqual/blob/main/Cargo.toml)); optional LCOV coverage input.
- **Reports:** "one aggregated quality score" from configurable dimension weights, per-dimension percentages, SARIF and GitHub annotations; `--min-quality-score` gate.
- **Changed code only:** no diff option in the [CLI reference](https://github.com/SaschaOnTour/rustqual/blob/main/book/reference-cli.md); `--compare baseline.json --fail-on-regression` fails when quality regresses against a saved baseline.
- **Own rules:** architecture rules and dimension weights in its configuration file.
- **Licence and business model:** MIT.

### pyscn and polyscan

[github.com/ludo-technologies/pyscn](https://github.com/ludo-technologies/pyscn) (1,103 stars) · [polyscan](https://github.com/ludo-technologies/polyscan) (13 stars)

- **Measures:** dead code; "Type 1-4 clone detection"; "cyclomatic and cognitive complexity"; module and directory hotspots; "circular imports, layer rule violations (clean / layered / hexagonal / MVC presets)"; class design "(CBO coupling, LCOM4 cohesion)" ([README](https://github.com/ludo-technologies/pyscn)).
- **Technique:** "Built with Go + tree-sitter".
- **Reports:** "0-100 with an A-F grade" and an HTML report; an MCP server `pyscn-mcp`.
- **Changed code only:** not stated.
- **Own rules:** layer presets; custom rules not checked.
- **Licence and business model:** MIT. polyscan applies "Same five angles, same 0-100 score" to JavaScript, TypeScript, Go, Rust and C++.

### no-mistakes

[github.com/kunchenguid/no-mistakes](https://github.com/kunchenguid/no-mistakes) · 9,160 stars · created 2026-04-05 · successor of the deprecated [airlock](https://github.com/airlock-hq/airlock)

- **Measures:** no metric. It "puts a local git proxy in front of your real remote", "runs an AI-driven validation pipeline" of `review → test → docs → lint → push → PR → CI`, and forwards the branch "only after every check passes" ([README](https://github.com/kunchenguid/no-mistakes)).
- **Technique:** a coding agent (claude, codex, opencode, copilot and others) reviews and fixes the change in a disposable worktree; "Safe, mechanical fixes are applied automatically; anything that touches your intent is escalated".
- **Reports:** pass/fail gate; opens the pull request.
- **Changed code only:** works on the pushed branch.
- **Own rules:** repository configuration (not examined).
- **Licence and business model:** MIT.

### Smaller projects

One line each, from the README unless marked. Stars as of 2026-11-08.

| Project | Measures or checks | Technique | Reports and gating | Changed code only |
|---|---|---|---|---|
| [SlopCheck](https://github.com/midnightrunai/slopcheck) (0, MIT) | "duplication, verbose naming, unpinned GitHub Actions ..., bloated error handling, and a fast OWASP top-10 pass" | "analyzes PR diffs"; method not stated | "Vibe Score" 0–100, grade A–F, PR comment; CI fails above threshold 60 | yes, PR diff |
| [vibecop](https://github.com/bhvbhushan/vibecop) (57, MIT) | "35 detectors": god functions, N+1 queries, unsafe shell exec, unpinned LLM models | ast-grep (tree-sitter) rules, "No LLM required" | findings; GitHub Action PR gate; MCP server; agent hooks | yes, `--diff HEAD` |
| [KarpeSlop](https://github.com/CodeDeficient/KarpeSlop) (39, MIT) | TypeScript/JavaScript "slop index" on three axes: noise, lies, soul | each rule adds "weight × ln(1 + findings per 1,000 lines)" with weights 8, 4, 2, 1 by severity | per-axis scores; example workflow comments on PRs | not stated |
| [AI-SLOP-Detector](https://github.com/flamehaven01/AI-SLOP-Detector) (111, MIT) | "empty functions with real-looking bodies, imports of things that don't exist, copy-pasted logic, unreachable code, and docs that oversell" | "deterministic core scoring", offline | score with `measurement_state`; CLI, MCP, REST | not stated |
| [kiss](https://github.com/dsweet99/kiss) (51, MIT) | complexity statistics, code-graph metrics, duplication; test time, count and orphan gates; Python and Rust | static analysis | writes `.kissconfig` with thresholds "so that your repo *just* passes", so later increases are flagged | whole repository |
| [smixs/code-quality](https://github.com/smixs/code-quality) (20, MIT) | test tampering, secrets, skipped hooks; "one complexity bar on every changed function"; diff coverage | git hooks and agent Stop hooks; runs the tests that reach the change | "Advice, not a gate": flags only, no blocking | yes |
| [agent-slop-lint](https://github.com/JordanGunn/agent-slop-lint) (44, Apache-2.0) | 25 rules: control-flow complexity, CK class metrics, hotspots, package distance, dependency cycles, clone density, god modules, Halstead volume and difficulty, magic literals | static analysis with cited default thresholds; profiles default, lax, strict | violations and PASS/FAIL | not stated |
| [grain](https://github.com/mmartoccia/grain) (34, MIT) | AI-generated code patterns, for example `NAKED_EXCEPT` | rules | violations plus a work queue for agents to repair | not stated |
| [sloppylint](https://github.com/rsionnach/sloppylint) (91, no licence file) | Python; "100+" patterns that LLMs carry over from other languages | pattern rules | "Slop Score" in points; `--max-score 50` exits 1 | not stated |
| [Rigour](https://github.com/rigour-labs/rigour) (29, MIT) | "quality issues AI coding agents introduce": god classes, SRP violations, DRY issues | "AST extracts deterministic facts ..., an LLM interprets what the patterns mean ..., then AST verifies the LLM didn't hallucinate" ([Show HN, 2026-02-21](https://news.ycombinator.com/item?id=47102656)) | findings; quality gate | not stated |
| [LucidShark](https://lucidshark.com) | "linting, formatting, type checking, SAST/security scanning, SCA/dependency checks, IaC validation, container scanning, unit tests, coverage thresholds, code duplication" | runs existing tools from `lucidshark.yml`, locally | "QUALITY.md dashboard with health scores (e.g. 9.1/10)" ([Show HN, 2026-03-18](https://news.ycombinator.com/item?id=47424142)) (description only) | not stated |
| [gap-trap](https://github.com/pliablepixels/gap-trap) (180, MIT) | writes rules for the codebase: contracts, "Proven red" tests that must fail on the old code, ratchets on counts that "may go down, never up" | agent skill writes the rules; commit and CI gates enforce them | gate failure | ratchets on totals |
| [brooks-lint](https://github.com/hyhmrright/brooks-lint) (1,567, MIT) | LLM reviews "grounded in twelve classic engineering books" | LLM review; a deterministic parser reads the model's report | "0–100 Health Score" from finding severities; SARIF; CI gates | not stated |
| [guard-skills](https://github.com/amElnagdy/guard-skills) (1,311, MIT) | "LLM code smells, over-abstraction, broad error swallowing", test bloat, documentation accuracy | agent skills (LLM review) | "do not merge" verdicts with rule-by-rule fixes | run on the diff |
| [anti-slop](https://github.com/peakoss/anti-slop) (855, AGPL-3.0) | "34 check rules covering PR branches, size, title, description, template, commit messages" and files | GitHub Action heuristics | closes the PR when `max-failures` is reached | per PR |
| [ultimate_bug_scanner](https://github.com/Dicklesworthstone/ultimate_bug_scanner) (314) | "1000+ bug patterns" across many languages including Rust | pattern scanning; "auto-wiring into AI coding agent" setups | findings, SARIF, `--comparison=<baseline.json>` for regressions | baseline deltas |
| [TheAuditor](https://github.com/TheAuditorTool/Auditor) (549) | "Queryable code truth for AI agents": code intelligence and SAST | local fact database | CLI and MCP answers; commercial licensing on inquiry | n/a |
| [Wispbit](https://wispbit.com) (closed) | "scanning your codebase for patterns you already use, and coming up with rules", enforced in code review ([Show HN, 2025-10-14](https://news.ycombinator.com/item?id=45584017)) (description only) | rule generation from the codebase | review comments | n/a |
| Haystack Slop Detector | flags PRs "that look like they were made without reviewing them first" ([Show HN, 2025-12-22](https://news.ycombinator.com/item?id=46356360)) (description only); the page now redirects to [haystack.sh](https://haystack.sh/slop-detector) with no detector content | not stated | not stated | per PR |
| [Prodlint](https://github.com/prodlint/prodlint) (15, MIT) | "hardcoded secrets, missing auth, and hallucinated imports" (description only) | static checks | findings | not stated |
| [codeclone](https://github.com/orenlab/codeclone) (12, MPL-2.0) | "Deterministic Structural Change Controller for AI-assisted Python development" (description only) | not examined | not examined | not examined |
| [archprint](https://github.com/Tommkruix/archprint) (8, MIT) | "Infers architecture rules from your TypeScript repo's real import graph, gates each on statistical evidence" and emits them to ESLint and others (description only) | import-graph analysis | rules for other linters | not examined |
| [good-egg](https://github.com/2ndSetAI/good-egg) (53, MIT) | "Trust scoring for GitHub PR authors based on contribution history" (description only) | contribution history | author score | n/a |
| [pr-slop-stopper](https://github.com/vmazi/pr-slop-stopper) (4) | "GitHub App to combat AI-generated spam PRs using heuristic-based reputation scoring" (description only) | heuristics | not examined | n/a |

Further projects with only a repository description checked: [Ivy-Apps/deslop](https://github.com/Ivy-Apps/deslop) (import-graph architecture rules in YAML for TypeScript), [godagoo/slopcheck-deslop](https://github.com/godagoo/slopcheck-deslop) ("structural erosion in AI-written TypeScript", based on SlopCodeBench), [MrZoyo/deslop-GPT](https://github.com/MrZoyo/deslop-GPT) (agent skill that deletes test bloat), [LeonardNJU/code-humanizer](https://github.com/LeonardNJU/code-humanizer) (agent skill that removes duplicated helpers and broad excepts), [scale-venture-partners/windbag](https://github.com/scale-venture-partners/windbag) (comments that narrate change history), [cm2435/slopcop](https://github.com/cm2435/slopcop) (Python anti-patterns, tree-sitter), [raye-deng/open-code-review](https://github.com/raye-deng/open-code-review) (hallucinated packages, phantom dependencies), [lucasvtiradentes/tscanner](https://github.com/lucasvtiradentes/tscanner), [r-tatarinov/codex-harness](https://github.com/r-tatarinov/codex-harness) (quality gates for Codex CLI), [stef41/vibescore](https://github.com/stef41/vibescore) (letter grade for vibe-coded projects), [shadcn/improve](https://github.com/shadcn/improve) (9,346 stars; "Use your most capable model to audit your codebase"). Product Hunt listings found through web search (Scan AI Slop, roast-my-code, Sloppoke, Orix) were not opened (unverified).

---

## 2. Code quality platforms that compute scores or ratings

### SonarQube (Server, Cloud, Community Build)

[sonarsource.com](https://www.sonarsource.com/plans-and-pricing/) · closed source platform; analyzers source-available

- **Measures:** issues by software quality (security, reliability, maintainability) with severities; "Code cyclomatic and cognitive complexities"; "Duplicated lines and blocks"; coverage; technical debt (sum of remediation costs) and the technical debt ratio, `sqale_debt_ratio = technical debt /(cost to develop one line of code * number of lines of code)`, with 30 minutes per line by default ([metrics definition](https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition.md)).
- **Technique:** rule-based static analysis per language. For Rust: coverage import (LCOV, Cobertura), cognitive and cyclomatic complexity, and "Import of Clippy output as external rules"; "The analyzer does not run Clippy for you" ([Rust doc](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/languages/rust.md)). Architecture analysis compares "your current architecture against an intended one", for C#, Java, JavaScript, Python and TypeScript, on Team and Enterprise plans ([architecture doc](https://docs.sonarsource.com/sonarqube-cloud/architecture-analysis.md)).
- **Reports:** ratings A–E; "The maintainability rating reflects the density of technical debt relative to the size of the code", A ≤ 5% debt ratio ([metrics definition](https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition.md)); quality gates as pass/fail sets of conditions, each made of "A metric", "A comparison operator" and "An error value" ([quality gates](https://docs.sonarsource.com/sonarqube-cloud/standards/managing-quality-gates/introduction-to-quality-gates.md)).
- **Changed code only:** yes. "In case of a pull request analysis, only the quality gate conditions applying to new code are used." ([quality gates](https://docs.sonarsource.com/sonarqube-cloud/standards/managing-quality-gates/introduction-to-quality-gates.md))
- **Own rules:** "Writing a SonarQube Server plugin in Java", "Adding XPath rules directly through the SonarQube Server web interface", or importing a generic issue format from another tool ([adding coding rules](https://docs.sonarsource.com/sonarqube-server/extension-guide/adding-coding-rules.md)); quality profiles select rules.
- **Licence and business model:** priced by lines of code, "starts at $34 monthly for analysis of up to 100k LOC", with a free tier ([pricing](https://www.sonarsource.com/plans-and-pricing/)). Analyzers are under the "SONAR Source-Available License v1.0", which allows only a "Non-competitive Purpose" and excludes using outside AI technology to ingest or interact with the program's output ([sonar-java LICENSE](https://github.com/SonarSource/sonar-java/blob/master/LICENSE.txt)).

### CodeScene

[codescene.com](https://codescene.com/pricing) · closed source

- **Measures:** Code Health, 10.0 to 1.0 per file, "an aggregated metric based on 25+ factors scanned from the source code". Named factors include Low Cohesion ("calculated using the LCOM4 metric"), Brain Class, Brain Method, Bumpy Road, Nested Complexity, Complex Method (cyclomatic complexity), Large Method, Primitive Obsession, DRY violations ("duplicated logic that is actually changed together"), Lines of Code, Developer Congestion and "Complex code by former contributors" ([Code Health docs](https://codescene.io/docs/guides/technical/code-health.html)). Codebase KPIs: Hotspot Code Health and Average Code Health.
- **Technique:** syntax-level code analysis plus git history mining (hotspots, change coupling, contributor data). Rust has full support, including custom rules for tests embedded in application files ([language support](https://codescene.io/docs/usage/language-support.html)).
- **Reports:** per-file score, KPIs, PR reviews. "The weight is the number of lines of code (LoC) in each file" when scores are averaged ([Code Health docs](https://codescene.io/docs/guides/technical/code-health.html)).
- **Changed code only:** yes; PR quality gates ("Quality gates for PR/Merge requests", [pricing](https://codescene.com/pricing)) and the MCP change-set review (section 1).
- **Own rules:** `.codescene/code-health-rules.json` sets rule weights, thresholds and path scopes ([Code Health docs](https://codescene.io/docs/guides/technical/code-health.html)).
- **Licence and business model:** Standard €18 and Pro €27 per active author per month billed yearly, Enterprise custom; free for open source; the ACE auto-refactoring add-on is sold separately ([pricing](https://codescene.com/pricing)).

### Qlty Cloud (successor of Code Climate Quality)

[qlty.sh](https://qlty.sh/pricing) · CLI fair source, cloud closed source · "Qlty is the next generation of Code Climate Quality." ([migration doc](https://docs.qlty.sh/migration/overview.md))

- **Measures:** lines of code; code smells for duplication and structure (similar code, identical code, many parameters, complex boolean logic, high file complexity, high function complexity, deeply nested control flow, many return statements) ([code smells](https://docs.qlty.sh/code-smells.md)); cognitive and cyclomatic complexity; duplication percentage; remediation minutes; technical debt and the technical debt ratio ([metrics](https://docs.qlty.sh/cloud/maintainability/metrics.md)).
- **Technique:** its own smell analysis plus over "60+ linter plugins" (for Rust: Clippy, complexity, duplication, osv-scanner, rustfmt, Trivy) ([README](https://github.com/qltysh/qlty)). The debt ratio divides fix effort by a rewrite estimate from "the Basic Constructive Cost Model (COCOMO)".
- **Reports:** project maintainability grade by debt ratio: A < 5%, B 5–10%, C 10–20%, D 20–50%, F ≥ 50%; file and directory grades from "a logorithmic function based on the total Technical Debt"; a coverage grade ([metrics](https://docs.qlty.sh/cloud/maintainability/metrics.md)).
- **Changed code only:** yes. "Qlty Gate" considers new issues, vulnerabilities and file maintainability; "Qlty Coverage" can fail "if the coverage decreases compared to the base branch"; "Qlty Diff Coverage" covers "the new or changed lines" ([quality gates](https://docs.qlty.sh/cloud/gates.md)).
- **Own rules:** plugins in `.qlty/qlty.toml`, including ast-grep and Semgrep.
- **Licence and business model:** Free $0, Pro $20 and Enterprise $30 per contributor per month ([pricing](https://qlty.sh/pricing)); CLI licence as in section 1.

### Codacy

[codacy.com](https://www.codacy.com/pricing) · closed source

- **Measures:** static analysis issues in categories such as style, error-prone, performance, security and documentation; issues per thousand lines; cyclomatic complexity; duplication (clones); line coverage ([metrics FAQ](https://docs.codacy.com/faq/code-analysis/which-metrics-does-codacy-calculate/)).
- **Technique:** runs bundled third-party analyzers per language. For Rust the tools page lists Opengrep for static analysis and Opengrep and Trivy for security, plus duplication and complexity; Clippy is not listed ([supported languages and tools](https://docs.codacy.com/getting-started/supported-languages-and-tools/)).
- **Reports:** "Grades represent a weighted average of the available code quality metrics (issues, complexity, duplication, and coverage), and range from A to F", for "repository branches and to individual files"; the weights are not published ([metrics FAQ](https://docs.codacy.com/faq/code-analysis/which-metrics-does-codacy-calculate/)).
- **Changed code only:** yes. Per PR: complexity change summed over changed files, "the number of clones introduced", and diff coverage; "AI Reviewer & Merge Gates for Pull Requests" on the Team plan ([metrics FAQ](https://docs.codacy.com/faq/code-analysis/which-metrics-does-codacy-calculate/), [pricing](https://www.codacy.com/pricing)).
- **Own rules:** "Custom Rules" on the Business plan; rule configuration through local configuration files or the web UI ([pricing](https://www.codacy.com/pricing)).
- **Licence and business model:** Developer plan $0 ("Free forever"), Team $18 per developer per month billed yearly, Business custom; free for open source ([pricing](https://www.codacy.com/pricing)).

### DeepSource

See section 1 for the PR Report Card, technique, pricing and gates. The current [llms.txt](https://deepsource.com/llms.txt) says analysis covers "30+ languages". Rust support was reported by the previous attempt and not confirmed today (unverified).

### SIG Sigrid

[softwareimprovementgroup.com](https://www.softwareimprovementgroup.com/?p=40154) · docs source at [Software-Improvement-Group/sigridci](https://github.com/Software-Improvement-Group/sigridci) · closed source

- **Measures:** maintainability model with Volume, Duplication, Unit size, Unit complexity, Unit interfacing, Module coupling, Component entanglement and Component independence, mapped to ISO 25010 sub-characteristics (from the description of a table image on the [SIG page, 2025-10-16](https://www.softwareimprovementgroup.com/?p=40154)); also security, open-source health and architecture quality ([docs index](https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/llms.txt)).
- **Technique:** static analysis, with ratings calibrated against a benchmark of other systems: the documentation README says "a benchmark of 25,000 industry systems" ([README](https://github.com/Software-Improvement-Group/sigridci)); the MCP page cites 30,000+ and 40,000+.
- **Reports:** "a standardized 1 to 5 star scoring approach" ([SIG page](https://www.softwareimprovementgroup.com/?p=40154)); sub-metrics "range from 1 to 5 stars, with the range 0.5 to 5.5"; "the overall score is not an average of the submetrics" ([maintainability doc](https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/capabilities/system-maintainability.md)).
- **Changed code only:** Sigrid CI "provides feedback on your changes" and "will let you pass as long as you're moving *towards* your objective"; default target 3.5 stars ([Sigrid CI doc](https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/sigridci-integration/using-sigridci.md)). The exact scope (changed files or changed lines) is not stated in that page (unverified). Guardrails check each changed file (section 1).
- **Own rules:** objectives per system; architecture configuration ([docs index](https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/llms.txt)).
- **Licence and business model:** commercial; no public price.

### GitHub Code Quality

[docs.github.com](https://docs.github.com/en/code-security/concepts/about-code-quality) · closed source · generally available 2026-07-20

- **Measures:** Reliability and Maintainability findings from CodeQL rules ([metrics and ratings](https://docs.github.com/en/code-security/reference/code-quality/metrics-and-ratings)); line coverage from uploaded Cobertura XML.
- **Technique:** "rule-based analysis of the following languages using CodeQL: C# Go Java JavaScript Python Ruby TypeScript"; "AI-powered analysis on your repository's recently changed code, including languages beyond those supported by rule-based queries" ([about](https://docs.github.com/en/code-security/concepts/about-code-quality)).
- **Reports:** per-repository categories Excellent, Good, Fair, Poor, set by the most severe rule-based finding on the default branch ([metrics and ratings](https://docs.github.com/en/code-security/reference/code-quality/metrics-and-ratings)).
- **Changed code only:** yes. "On pull requests, Code Quality posts rules-based CodeQL findings only." Rulesets can block PRs by finding severity, by "Minimum line coverage percentage", or by "Maximum line coverage drop ... percentage points relative to the default branch" ([coverage gate](https://docs.github.com/en/code-security/how-tos/maintain-quality-code/restrict-code-coverage)). "Code Quality AI findings cannot be set as a threshold." ([thresholds](https://docs.github.com/en/code-security/how-tos/maintain-quality-code/set-pr-thresholds))
- **Own rules:** CodeQL queries (section 3); custom queries for Code Quality not checked.
- **Licence and business model:** "$10 per active committer, per month" plus metered usage ([changelog](https://github.blog/changelog/2026-07-20-github-code-quality-is-now-generally-available/)).

### Teamscale (CQSE)

[teamscale.com](https://teamscale.com/) · docs at [docs.teamscale.com](https://docs.teamscale.com/llms.txt) · closed source

- **Measures:** findings from "over 500 built-in checks"; clones, including cross-component clones; architecture conformance; test gaps; any configured metric ([docs index](https://docs.teamscale.com/llms.txt), [custom checks](https://docs.teamscale.com/reference/custom-checks.md)). Specific metric names were not verified.
- **Technique:** static analysis, clone detection, architecture analysis, Test Gap Analysis (motivated by research that "untested changes are five times more likely to contain errors", [Test Gap Analysis doc](https://docs.teamscale.com/reference/test-gap-analysis.md)), uploaded external coverage and findings; LLM "review agents" for merge requests whose "comments are verified and consolidated" ([agentic reviews](https://docs.teamscale.com/howto/performing-agentic-reviews.md)).
- **Reports:** "metric change badges" on merge requests with "yellow and red warning thresholds for any metric" ([merge request metrics](https://docs.teamscale.com/howto/tracking-metrics-in-merge-requests.md)); a customer quote on the homepage describes GitLab merge requests being blocked "if new findings are detected".
- **Changed code only:** yes; delta analysis and merge-request views ([docs index](https://docs.teamscale.com/llms.txt)).
- **Own rules:** a Custom Check Framework in which checks are implemented in code ([custom checks](https://docs.teamscale.com/reference/custom-checks.md)); adjustable analysis profiles.
- **Licence and business model:** commercial; prices not on the pages read. The homepage headline rotates through variants, one of which is "The Software Quality Platform for Agents".

### NDepend

[ndepend.com](https://www.ndepend.com/docs/code-metrics) · closed source · C# and VB.NET

- **Measures:** lines of code, comment percentage, IL instructions, afferent and efferent coupling, relational cohesion, instability, abstractness, distance from main sequence, LCOM and LCOM HS, cyclomatic complexity, IL nesting depth, parameter and variable counts, depth of inheritance, number of children, ABC, TypeRank and MethodRank, line and branch coverage, Halstead volume, Maintainability Index ([code metrics](https://www.ndepend.com/docs/code-metrics)).
- **Technique:** analysis of source and compiled IL; "smart technical-debt estimation" since 2017.1.0, as the sum of per-issue cost-to-fix estimates.
- **Reports:** dashboard; "For each metric, the dashboard shows the diff since baseline."
- **Changed code only:** baseline comparison.
- **Own rules:** CQLinq queries.
- **Licence and business model:** commercial; price not checked.

### TIOBE TICS and the TIOBE Quality Indicator (TQI)

[tiobe.com/quality-standards/tqi](https://www.tiobe.com/quality-standards/tqi/) · definition [TIOBEQualityIndicator_v5_2.pdf](https://www.tiobe.com/files/TIOBEQualityIndicator_v5_2.pdf) (version 5.2, 17 October 2025) · closed source

- **Measures:** eight metrics with fixed weights: Code Coverage 20%, Abstract Interpretation 20%, Code Security 15%, Compiler Warnings 15%, Cyclomatic Complexity 10%, Coding Standards 10%, Code Duplication 5%, Fan Out 5% ([PDF](https://www.tiobe.com/files/TIOBEQualityIndicator_v5_2.pdf)).
- **Technique:** each metric is mapped to a 0–100 score by formulas "determined empirically, based on analyzing the more than 2 billion lines of code that are checked by TIOBE Software each day"; violations are converted with a "compliance factor" per thousand lines weighted by severity; fan out is "the number of import statements". The PDF says "TIOBE has started research to correlate software defects to code quality metrics".
- **Reports:** one TQI score with categories Outstanding ≥ 90%, Good ≥ 80%, Fairly Good ≥ 70%, Moderate ≥ 50%, Weak ≥ 40%, Poor < 40%, "similar to the European Union energy labels".
- **Changed code only:** not stated in the PDF sections read.
- **Own rules:** not examined.
- **Licence and business model:** commercial; price not checked.

### CAST Highlight

[doc.casthighlight.com](https://doc.casthighlight.com/?p=8703) · closed source

- **Measures:** Software Health, "the straight average of" Software Resiliency, Software Agility and Software Elegance ([Software Health](https://doc.casthighlight.com/?p=8703)); also Cloud Maturity, Green Impact and Software Composition ([indicators](https://doc.casthighlight.com/?p=1346)).
- **Technique:** "Highlight implements hundreds of code insights across 20+ technologies to calculate health factors of a software" ([indicators](https://doc.casthighlight.com/?p=1346)).
- **Reports:** scores with colour bands: Red below 53.0, Orange 53.0–75.0, Green above 75.0 ([Software Health](https://doc.casthighlight.com/?p=8703)); portfolio dashboards.
- **Changed code only:** not stated.
- **Own rules:** a documentation page on custom indicators exists (not opened) (unverified).
- **Licence and business model:** commercial SaaS; price not checked.

### Axivion Suite (Qt Group)

[doc.qt.io/axivion](https://doc.qt.io/axivion/analyses_guide/index.html) · closed source

- **Measures and technique:** the analyses guide covers Architecture, Clones, Cycles, Dead Code, Metrics, Safety and Security, and Stylechecks ([analyses guide](https://doc.qt.io/axivion/analyses_guide/index.html)). Supported languages, delta analysis and reporting were not verified.

### Squore (Vector)

[vector.com](https://www.vector.com/int/en/products/products-a-z/software/squore/) · closed source

- **Measures and technique:** "consolidates static analysis results, test coverage, requirements traceability, and project metrics" from over 50 tools; pre-built models for ISO 26262, DO-178C, IEC 62304, ISO 9126 and SQALE; "Configurable quality and decision models"; debt metrics and generated action plans.
- **Reports:** ratings with drill-down "from global rating down to the exact line of code"; PDF and PPT reports; quality gates for CI in Squore 26 ([product page](https://www.vector.com/int/en/products/products-a-z/software/squore/)).
- **Changed code only, own rules, price:** not stated beyond configurable models.

### GitClear

[gitclear.com](https://www.gitclear.com/ai_assistant_code_quality_2025_research) · closed source

- **Measures:** classifies changed lines, including "copy/pasted" (cloned), "moved", refactoring-associated and "short-term churn" lines; its own "Diff Delta" metric (not defined on the page read).
- **Reported findings (vendor research):** over 211 million changed lines from 2020 to 2024, copy/pasted lines rose from 8.3% (2021) to 12.3% (2024), and refactoring-associated changed lines fell from 25% (2021) to under 10% (2024) ([research page](https://www.gitclear.com/ai_assistant_code_quality_2025_research)).
- **Technique:** git history analysis of changed lines.
- **Licence and business model:** commercial; prices not on the page read.

### Kiuwan, Embold, Scrutinizer

- [Kiuwan](https://www.kiuwan.com/code-analysis/) lists a "Code Quality" product with "Actionable Code Analysis Metrics" for "over 30 programming languages"; its indicators were not on the page read.
- Embold and Scrutinizer: current status not established; web search returned only aggregator pages (unverified).

---

## 3. Architecture-rule checkers and custom-rule engines

| Tool | What it checks | Technique |
|---|---|---|
| [ArchUnit](https://github.com/TNG/ArchUnit) | Java: "dependencies between packages and classes, layers and slices, check for cyclic dependencies and more" | analyzes Java bytecode; rules written as unit tests |
| [ArchUnitNET](https://github.com/TNG/ArchUnitNET) | C#: the ArchUnit checks | ArchUnit port for .NET |
| [NetArchTest](https://github.com/BenMorris/NetArchTest) | .NET: "architectural rules in unit tests" | fluent API |
| [Konsist](https://github.com/LemonAppDev/konsist) | Kotlin: "consistency of Kotlin projects by enforcing a cohesive code structure" | rules run inside JUnit or Kotest tests |
| [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) | JavaScript, TypeScript: "Validate and visualise dependencies. With your rules." | collects module dependencies and validates them against user rules |
| [eslint-plugin-boundaries](https://github.com/javierbrea/eslint-plugin-boundaries) | JavaScript, TypeScript: dependencies between declared element types | ESLint rules; "Violations are ordinary ESLint errors" |
| [Import Linter](https://github.com/seddonym/import-linter) | Python: "constraints on the imports between your Python modules" | import graph contracts |
| [Tach](https://github.com/tach-org/tach) | Python: "enforce dependencies and interfaces" | checks that "Imports only come from declared dependencies"; "written in Rust" |
| [Packwerk](https://github.com/Shopify/packwerk) | Ruby on Rails: "enforce boundaries and modularize Rails applications" with packages and constant visibility | package definitions; reports violations |
| [Deptrac](https://github.com/deptrac/deptrac) | PHP: "enforce architectural decisions" | "define your architectural layers over classes and which rules should apply to them" |
| [go-arch-lint](https://github.com/fe3dback/go-arch-lint) | Go: "validate top level architecture (code layers)" | `mayDependOn` rules per component in a config file |
| [depguard](https://github.com/OpenPeeDeeP/depguard) | Go: "package imports are in a list of acceptable packages" | allow and deny lists |
| [cargo-pup](https://github.com/DataDog/cargo-pup) (Datadog) | Rust: "assertions about your Rust project's architecture"; "Inspired by ArchUnit" | integrates with rustc; needs a pinned nightly toolchain; rules in `pup.ron` |
| [arch-lint](https://github.com/ynishi/arch-lint) | Rust: "layering, scope, and dependency rules in `arch-lint.toml`" | `syn` parsing; runs inside `cargo test` |
| [crawk](https://github.com/BartoszCiesla/crawk) | Rust: module dependency graph, layering rules, cycles, forbidden imports | crate module analysis |
| [Clippy `disallowed-methods`, `disallowed-types`, `disallowed-macros`](https://github.com/rust-lang/rust-clippy/blob/master/book/src/lint_configuration.md) | Rust: banned items "written as fully qualified paths" | compiler lint configuration |
| [Dylint](https://github.com/trailofbits/dylint) | Rust: user-written lints; "Dylint runs lints from user-specified, dynamic libraries" | rustc lint libraries |
| [cargo-deny](https://github.com/EmbarkStudios/cargo-deny) | Rust dependencies: licences, bans, advisories, sources | `Cargo.lock` and dependency graph |
| [Semgrep](https://github.com/semgrep/semgrep) | "searches code, finds bugs, and enforces secure guardrails and coding standards", 30+ languages | "semantic grep"; YAML pattern rules |
| [Opengrep](https://github.com/opengrep/opengrep) | same as Semgrep | "a fork of Semgrep, under the LGPL 2.1 license" |
| [ast-grep](https://github.com/ast-grep/ast-grep) | "code structural search, lint, and rewriting" | tree-sitter syntax patterns; YAML rules |
| [CodeQL](https://github.com/github/codeql) | security and quality queries | QL query libraries and standard checks that "power GitHub Advanced Security" |
| [GritQL](https://github.com/getgrit/gritql) | "a declarative query language for searching and modifying source code" | "any code snippet is a valid GritQL query"; auto-fix rules |
| [Comby](https://github.com/comby-tools/comby) | structural match and rewrite | templates with holes such as `if (:[condition])`, plus a language flag |
| [Danger JS](https://github.com/danger/danger-js) | "your team's conventions surrounding code review" | Dangerfile rules run in CI on the PR |
| [Betterer](https://phenomnomnominal.github.io/betterer/docs/introduction) | any measured value over time | ratchet: "If it gets better, the .betterer.results file will be updated ... If it gets worse, your test will fail" |
| [reviewdog](https://github.com/reviewdog/reviewdog) | output of any linter | filters findings "by diff" and posts review comments |

Platforms in section 2 with architecture checks: SonarQube architecture analysis, Sigrid architecture quality, Axivion architecture verification, Teamscale architecture conformance.

---

## 4. AI code review tools that accept project-specific rules

All of these review with large language models.

| Tool | Project rules | Notes |
|---|---|---|
| [CodeRabbit](https://docs.coderabbit.ai/pr-reviews/pre-merge-checks.md) | custom pre-merge checks "using natural language instructions" to "Encode architectural patterns, compliance rules, or business logic"; [path instructions](https://docs.coderabbit.ai/guides/review-instructions.md) in `.coderabbit.yaml`; AST-based instructions with ast-grep | checks run in `warning` (default) or `error` mode; `error` blocks merges only with Automatic Approvals; custom checks need the Team plan |
| [Greptile](https://www.greptile.com/docs/code-review/custom-standards) | dashboard rules at organization or team scope; `.greptile/` or `greptile.json` in the repository | documentation also covers "Training the Learning System" |
| [Cursor Bugbot](https://cursor.com/docs/bugbot) | "team rules, repository rules, and project .cursor/BUGBOT.md files" | "findings default to neutral" unless fail-on-unresolved-issues is enabled |
| [Qodo](https://www.qodo.ai/blog/introducing-qodo-rule-system/) | Rules System (Qodo 2.1, 2026-02-17): "Each rule is a versioned entity with defined scope, ownership, and lifecycle", "from architectural constraints to security and domain requirements" | rules enforced by its review agents |
| [Sourcery](https://docs.sourcery.ai/reviews/review-rules.md) | "one of your team's conventions, written in plain language and scoped to the files it applies to" | all plans |
| [Claude Code Code Review](https://code.claude.com/docs/en/code-review) | `REVIEW.md` and `CLAUDE.md` | "A review never approves or blocks the pull request" |
| [OpenAI Codex GitHub review](https://learn.chatgpt.com/docs/third-party/github) | `## Code Review Rules` sections in `AGENTS.md` | "Codex flags only P0 and P1 issues"; "Leave mechanical checks in CI" |
| [GitHub Copilot code review](https://docs.github.com/en/copilot/concepts/agents/code-review) | `.github/copilot-instructions.md`, path-specific `*.instructions.md`, `AGENTS.md`, skills | |
| [Gemini Code Assist on GitHub](https://developers.google.com/gemini-code-assist/docs/customize-gemini-behavior-github) | `.gemini/config.yaml` and `styleguide.md` | |
| [Kodus](https://github.com/kodustech/kodus-ai) (1,573 stars, AGPLv3) | "Define custom review rules in plain language" | "Open source AI code review you can self-host, with the LLM you choose" |
| [PR-Agent](https://github.com/qodo-ai/pr-agent) | prompts and review categories in `configuration.toml` | open source; the README now links to The-PR-Agent/pr-agent |
| Teamscale, DeepSource | see section 2 and section 1 | LLM review combined with static analysis |
| [CodeAnt AI](https://www.codeant.ai/) | not stated on the homepage | homepage lists "AI code reviews" within a security platform |
| Graphite Agent (Cursor) | custom rules per the previous attempt (unverified) | not re-checked |

---

## 5. Rust quality tools

Versions and downloads from crates.io on 2026-11-08.

| Tool | What it checks | Technique |
|---|---|---|
| [Clippy](https://github.com/rust-lang/rust-clippy) | "over 800 lints" in groups correctness, suspicious, style, complexity, perf (on by default), and pedantic, restriction, nursery, cargo (off by default) | compiler lints on typed code |
| [rust-code-analysis](https://github.com/mozilla/rust-code-analysis) (Mozilla; CLI v0.0.25, last release 2023-01-13) | ABC, BLANK, CC, CLOC, COGNITIVE, HALSTEAD, LLOC, MI, NARGS, NEXITS, NOM, NPA, NPM, PLOC, SLOC, WMC ([metrics](https://mozilla.github.io/rust-code-analysis/metrics.html)) | tree-sitter, many languages |
| [cargo-geiger](https://github.com/geiger-rs/cargo-geiger) (v0.14.0, 2026-10-12) | "statistics related to the usage of unsafe Rust code in a Rust crate and all its dependencies" | counts `unsafe` usage in the crate and each dependency |
| [cargo-mutants](https://github.com/sourcefrog/cargo-mutants) (v27.1.0) | "Inject bugs and see if your tests catch them" | mutation testing; [`--in-diff`](https://mutants.rs/in-diff.html) tests "only mutants generated from recently changed code" |
| [cargo-semver-checks](https://github.com/obi1kenobi/cargo-semver-checks) (v0.51.0) | "semver violations" in the public API | lints over rustdoc JSON output |
| [cargo-public-api](https://github.com/cargo-public-api/cargo-public-api) (v0.52.0) | "List and diff the public API" between releases and commits | rustdoc JSON |
| [cargo-llvm-cov](https://github.com/taiki-e/cargo-llvm-cov) (v0.9.1) | test coverage | "LLVM source-based code coverage (-C instrument-coverage)" |
| [cargo-tarpaulin](https://github.com/xd009642/tarpaulin) (v0.37.6) | "line coverage" | Ptrace tracing backend by default on Linux |
| [cargo-crap](https://github.com/minikin/cargo-crap) (432 stars, v0.9.0) | CRAP score per function; the main-branch README, marked "Since 0.10.0", adds six signals per function: "nesting depth, length, separate nested chunks ('bumps'), the most `&&`/`\|\|` in one condition, stubs (`todo!`, `dbg!`) and panic sites (`unwrap`, `expect`, `panic!`)" | `syn` parsing plus LCOV; `--fail-above`, and `--fail-regression` against a baseline; SARIF; PR comment |
| [rustqual](https://github.com/SaschaOnTour/rustqual) (v1.8.3) | seven dimensions and one score (section 1) | `syn` |
| [debtmap](https://github.com/iepathos/debtmap) (74 stars, v0.24.1) | ranks technical debt by risk: complexity, coverage gaps, git history | `syn` for Rust; "unified priority score with severity bands"; output prepared for LLMs |
| [kiss](https://github.com/dsweet99/kiss) | complexity, duplication, test gates for Python and Rust (section 1) | static analysis with ratchet-style thresholds |
| [cargo-deny](https://github.com/EmbarkStudios/cargo-deny) (v0.20.2) | dependency licences, bans, advisories, sources | dependency graph |
| [cargo-audit](https://github.com/rustsec/rustsec) (v0.22.2) | "Audit Cargo.lock for crates with security vulnerabilities" | RustSec advisory database |
| [cargo-vet](https://github.com/mozilla/cargo-vet) (v0.10.3) | "Supply-chain security for Rust" | checks that "third-party Rust dependencies have been audited by a trusted entity" |
| [cargo-udeps](https://github.com/est31/cargo-udeps), [cargo-machete](https://github.com/bnjbvr/cargo-machete) | unused dependencies | udeps "needs Rust nightly to actually run"; machete works "in a fast (yet imprecise) way" |
| [cargo-modules](https://github.com/regexident/cargo-modules) (v0.28.0) | "tree-like overview of a crate's modules" | module tree of a crate |
| [Kani](https://github.com/model-checking/kani) (v0.68.0) | "a bit-precise model checker for Rust": panics, arithmetic overflows, custom properties | model checking |
| [Dylint](https://github.com/trailofbits/dylint), [cargo-pup](https://github.com/DataDog/cargo-pup), [arch-lint](https://github.com/ynishi/arch-lint), [crawk](https://github.com/BartoszCiesla/crawk) | custom lints and architecture rules | see section 3 |

Tools in sections 1 and 2 with Rust analysis: desloppify (Rust plugin), aislop (Clippy and own rules), crapper, dryer and mutator, sentrux, polyscan, CodeScene, SonarQube (imported Clippy output), Qlty.

---

## 6. The term "metric-driven agentic coding"

### What the searches returned

| Query | Where | Result |
|---|---|---|
| "metric-driven agentic coding" | [HN Algolia](https://hn.algolia.com/api/v1/search?query=%22metric-driven%20agentic%20coding%22&tags=(story,comment)&advancedSyntax=true), stories and comments | 0 hits |
| "metrics-driven agentic coding" | HN Algolia | 0 hits |
| "metric-driven agentic", "metric driven agentic" | HN Algolia | 1 hit: the comment below |
| "metrics-driven agentic" | HN Algolia | 0 hits |
| "metric-driven coding", "metrics-driven coding" | HN Algolia | 0 hits |
| "quality gates for coding agents" | HN Algolia | 0 hits |
| "quality gates for AI coding agents" | HN Algolia | 1 hit: [Show HN: Rigour](https://news.ycombinator.com/item?id=47102656) (2026-02-21) |
| "metric-driven agentic coding" | web search, extended mode | no page uses the phrase; results were a DEV post ["Velocity is a Vanity Metric: Why Agentic Coding is Actually About Quality"](https://dev.to/dmitryame/velocity-is-a-vanity-metric-why-agentic-coding-is-actually-about-quality-3cof), [Tweag's "Introduction to Agentic Coding"](https://www.tweag.io/blog/2025-10-23-agentic-coding-intro/), and arXiv papers on agent behaviour and agent-written code |
| "metrics-driven agentic", "metric-driven agentic", "metric-driven AI coding", "metrics-driven AI coding" | web search | no page uses the phrases; results were articles on measuring coding agents (CodeRabbit, Warp, Augment, explyt, HackerNoon, [arXiv 2609.04681](https://arxiv.org/pdf/2609.04681)) |
| "metric-driven development", "metrics-driven development" with AI coding agents | web search | no method by that name for agents; results were agent KPI articles (CodeRabbit, Jellyfish, Warp, AWS, StackHawk) |
| "metric-driven", "metrics-driven" | GitHub repository names and descriptions | [EurekAgent](https://github.com/THU-Team-Eureka/EurekAgent) (88 stars): "an autonomous research system for metric-driven tasks, built with Claude Code. Define the problem and metric."; [walterfan/mdd](https://github.com/walterfan/mdd) ("metrics driven development"); the rest are unrelated (ML papers, resume tools) |

All searches ran on 2026-11-08. Reddit and X were not searched.

### The one near-match

A postscript in a Hacker News comment by aleyan, 2026-05-03, on the story "Uncle Bob: It's Over" (a link to a Reddit thread): "PS. Reacting to Uncle Bob, I found metric driven agentic refactors just push complexity to outside the scope of the metric. I am finding I need to actively guide the agents for the refactors to actually improve things without increasing the entropy of the codebase." The comment links an X post by Uncle Bob ([status 2046206145597972849](https://x.com/unclebobmartin/status/2046206145597972849), not opened) ([HN comment](https://news.ycombinator.com/item?id=47999904)).

### Older uses of "metrics-driven development"

The term exists in DevOps writing from 2012 to 2016, for runtime and business telemetry. It does not refer to code-quality measurement.

- Hacker News stories: "Metric Driven Development Fueled by StatsD and Graphite" (7digital, [2012-04-19](https://news.ycombinator.com/item?id=3862942)), "Metrics Driven Development" ([2012-05-22](https://news.ycombinator.com/item?id=4006337)), Librato posts ([2014-07-17](https://news.ycombinator.com/item?id=8049918), [2015-04-02](https://news.ycombinator.com/item?id=9312966)), Sookocheff ([2016-08-09](https://news.ycombinator.com/item?id=12256636)).
- InfoQ, Mantas Klasavičius, 2012-11-30: "I would define MDD as a practice where metrics are used to drive the entire application development. In a company which uses MDD, everything from performance and usage patterns to revenue is measured." ([InfoQ](https://www.infoq.com/articles/metrics-driven-development/))
- Kevin Sookocheff, 2016-08-09: "Metrics-Driven Development is an emerging term developing from the practices of continuous integration, continuous delivery, dev ops, and agile"; defined as "The use of real-time metrics to drive rapid, precise, and granular software iterations" ([sookocheff.com](https://sookocheff.com/post/mdd/mdd/)).

### Related practices under other names

These sources describe steering coding agents with measurements without using the phrase.

- **Quality gates.** Addy Osmani, 2026-08-08: "We call these constraints quality gates, and they take many forms." and "Software quality isn't a single metric." ([addyosmani.com](https://addyosmani.com/blog/agentic-code-quality/))
- **Harness engineering, sensors and fitness functions.** Birgitta Böckeler, Thoughtworks, 2026-04-02: "Computational sensors catch the structural stuff reliably: duplicate code, cyclomatic complexity, missing test coverage, architectural drift, style violations." On architecture checks: "Basically: Fitness Functions" ([martinfowler.com](https://martinfowler.com/articles/harness-engineering.html)).
- **Gaming observed in practice.** Böckeler, 2026-05-27: "AI frequently decided to increase the cyclomatic complexity threshold, but suggested good refactorings when I nudged it further." ([martinfowler.com](https://martinfowler.com/articles/sensors-for-coding-agents.html))
- **Agent loops against a complexity threshold.** Tweag, Wesley Fuchter, 2025-10-23: "Engineers can instruct the AI to execute Lizard against the codebase." When a function exceeds "the defined complexity threshold (typically 10)", "the AI is prompted to refactor that function"; "This method forces the AI to act on specific, measurable quality signals". The article does not use "metric-driven" ([tweag.io](https://www.tweag.io/blog/2025-10-23-agentic-coding-intro/)).
- **Agent loops against a quality score.** CodeScene and loveholidays, TechDebt 2026: agents iterated until Code Health reached 10 (section 1) ([conf.researchr.org](https://conf.researchr.org/details/TechDebt-2026/TechDebt-2026-industry-track/1/Quality-Feedback-in-the-Agentic-Loop-Using-CodeHealth-Guardrails-to-Agentic-Code-Imp)).
- **Metric-driven research agents.** EurekAgent uses "metric-driven" for research tasks with a target metric, as listed above.

### Product or method using the term

No product, company, repository, article or talk found uses "metric-driven agentic coding" or "metrics-driven agentic coding" as a name. The only use of a close phrase is the critical Hacker News comment above. This conclusion rests on missing search results; closed platforms (X, LinkedIn, Reddit) were not covered.

### Name collisions for "Geiger" among developer tools

| Name | What it is | Source |
|---|---|---|
| cargo-geiger | Rust: "A tool that lists statistics related to the usage of unsafe Rust code in a Rust crate and all its dependencies"; title "cargo-geiger ☢️"; 1,664 stars; v0.14.0 on 2026-10-12, 270,185 downloads | [GitHub](https://github.com/geiger-rs/cargo-geiger), [crates.io](https://crates.io/crates/cargo-geiger) |
| crate `geiger` | "Some library parts of cargo-geiger"; v0.5.0, 254,106 downloads | [crates.io](https://crates.io/crates/geiger) |
| go-geiger | "Find and count `unsafe` usages in Go packages and their dependencies" | [GitHub](https://github.com/jlauinger/go-geiger) |
| react-geiger | "a tool for 'audiolizing' React performance issues"; 1,104 stars | [GitHub](https://github.com/kristiandupont/react-geiger) |
| Atomburst geiger (npm `geiger-scan`) | "A Geiger counter for AI agents": inventories agents, harnesses, MCP servers and plugins on a machine; 172 stars | [GitHub](https://github.com/Atomburstofficial/geiger) |
| puck-security/geiger | "Read-only blast-radius triage for leaked credentials" | [GitHub](https://github.com/puck-security/geiger) |
| lukechampine/geiger | "A Geiger counter for allocations"; 276 stars | [GitHub](https://github.com/lukechampine/geiger) |
| alloc_geiger, malloc_geiger | allocators that make sound when allocating | [alloc_geiger](https://github.com/cuviper/alloc_geiger), [malloc_geiger](https://github.com/laserallan/malloc_geiger) |
| david-grs/geiger | "C++ micro benchmark library" | [GitHub](https://github.com/david-grs/geiger) |
| npm `geiger` | a small Flux implementation, last modified 2022-06-18 | [npm](https://registry.npmjs.org/geiger) |
| PyPI `geiger` | "A radiation detection utility package" | [PyPI](https://pypi.org/pypi/geiger/json) |
| GEIGER (EU Horizon 2020 project) | cybersecurity tool for small businesses, per the previous attempt (unverified today) | [cyber-geiger.eu](https://cyber-geiger.eu/what-is-geiger.html) |

---

## 7. Limits of this search

- GitHub repository search matches names, descriptions and READMEs by keyword. Tools that describe themselves with other words may be missing. GitHub code search was unavailable (no authentication).
- Reddit, X and LinkedIn were not searched. Product Hunt was searched only through a web search engine; its listings were not opened.
- Vendor documentation describes intended behaviour. No tool was run.
- Star counts and prices change; both are as of 2026-11-08.
- Smaller projects in the tables were read from their READMEs or descriptions only. Their accuracy claims were not tested.
