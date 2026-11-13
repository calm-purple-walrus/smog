# Measuring code by agent change cost

Date: 2026-11-08. Follow-up to `report.md`: what the existing products measure, and what Geiger could measure instead.

## What existing products measure

Almost every product measures the code as it currently stands and combines the results with weights the vendor picked (details in `products.md`):

- **Rule findings relative to code size:** lint, smell and security findings, weighted by severity. Used by aislop, SonarQube and Qlty (estimated fix time as a share of estimated writing time), Codacy, DeepSource, TIOBE and polyscan.
- **Structural metrics with thresholds:** function size, complexity, nesting, duplication, cohesion, coupling and dependency cycles. Used by CodeScene Code Health, SIG stars, rustqual, sentrux and fallow.
- **Tests:** mostly coverage. Only Uncle Bob's mutator does mutation testing; CRAP combines complexity with coverage.
- **Change history:** churn, hotspots and ownership, in CodeScene, fallow and GitClear.
- **LLM judgment:** desloppify takes 75% of its score from LLM review. Qlty SlopOne feeds an LLM's answers to reviewer questions into a model trained on human ratings.
- **AI tells:** narrative comments, TODO stubs, generic names and hallucinated imports, in aislop, sloppylint and similar tools.
- **Architecture rules:** layers, forbidden imports and cycles, in sentrux, fallow, rustqual and SIG.

Several products already reduce this to one number: desloppify, aislop, sentrux, rustqual, CodeScene and TIOBE. None of them has shown that its number predicts an outcome. In the one comparison against expert ratings, a plain line count did as well as CodeScene's Code Health (`scoring.md`, section 2).

## Proposal: measure the cost of the next change

Every number above stands in for one question: how much does the next change cost? For code that agents maintain, this can be measured directly:

- Give a fixed agent a set of hidden change tasks on the codebase.
- Record its success rate and what it spends: tokens, time, attempts.
- Report the expected cost per change, in tokens or dollars.

This differs from LLM judgment. desloppify and SlopOne ask a model what it thinks of the code; this measures what happens when an agent has to change it.

## Evidence

Research has started to measure code this way:

- **CodeThread (2026):** agents solved up to 13.1% fewer tasks when building on agent-written code than on human-written code. "many traditional software engineering maintainability metrics do not explain this difference"; the clearest signals were changes to input validation and error handling, along with code size and task difficulty ([arXiv 2606.21804](https://arxiv.org/abs/2606.21804)).
- **NITR (2026):** checks agent edits with hidden functional tests plus structural checks. 13.3% of outcomes passed every test but failed the structural check, and agents solved only 4.3% of the dependency-control probes ([arXiv 2603.27745](https://arxiv.org/abs/2603.27745)).
- **CodeScene (2026, vendor study):** Code Health was associated with whether AI refactorings preserved behavior, on 5,000 Python files from competitive programming. CodeScene uses this result to support Code Health; its product sells the proxy score ([arXiv 2601.02200](https://arxiv.org/abs/2601.02200)).

None of the products found in `products.md` measures a customer's codebase this way.

## How it could work as a product

1. **The number has units.** The per-pull-request budget becomes "a pull request may raise the cost of changing the code it touches by at most X%". If tasks are drawn from the repository's history, areas that change often count more, and a messy component nobody touches counts little.
2. **Pull requests use cheap checks.** Agent runs are slow and cost tokens. Each pull request gets fast static checks whose weights are fitted to the measured agent cost; periodic agent runs refit them. The weights then come from data instead of a vendor's choice.
3. **The fitted weights are the asset.** The data would grow with every codebase measured. This is option C in `report.md` section 4, made cheaper: agent runs produce outcome data on demand, while defect data appears only after later fixes.

## Open problems

- **Cost:** each measurement needs many agent runs.
- **Noise:** results vary between identical runs, so each task needs repeats, and the budget must be larger than that variation.
- **Model changes:** the number shifts when the agent or model changes. The agent must be pinned and the baseline reset after upgrades.
- **Tasks:** they must be realistic and checkable in any repository. One source: take a past commit, remove its feature, ask the agent to add it back, and check with that commit's tests.
- **Humans:** whether agent cost tracks human maintenance cost is unknown. It matters less if agents make most changes.

## First test

Take a few public Rust repositories and two versions of each, one known to be in better shape than the other. Replay past commits as tasks with one pinned agent. If the cost difference between versions is clearly larger than the variation between runs, the measurement works. Then check which static metrics predict that difference.
