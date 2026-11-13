# Scores and rules for Smog

Researched 2026-11-08. Inputs: `docs/design/measurement-model.md`, `metrics-1.md`, `metrics-2.md`.

## Answer

No source I opened gives a validated way to turn code metrics into "how much agent usage or poisoning can we take". That number has to be measured on your own factory (section 8). The rest of the design can be settled now:

1. **A single codebase threshold cannot gate a large codebase.** In a 1,000,000-line codebase at 0.95, it takes 55,556 lines of the worst possible code to reach 0.90. Keep your 0.9 rule, but as a trigger that freezes feature work, not as the PR gate.
2. **Gate the flow, not the stock.** PR rules use absolute debt added, which does not dilute. A ledger records each item's debt over a rolling window, so many small drops add up.
3. **Your curve idea has one serious side effect.** Any curve that hurts more and more rewards splitting: a 60-line function costs 0.25, and three 20-line functions cost 0. The curve needs a guard built into the measurement (section 5).
4. **Report where the codebase is heading, not only where it is.** The debt rate of recent PRs gives an equilibrium score, which does not dilute with size. It also gives a runway in PRs, and a sustainable PR rate.
5. **Make the score hard to game with four structural defenses:** a test suite of known exploits that the scoring must survive, sealed lenses the agent never sees, frozen reference points, and seeded bad PRs that measure what the gate misses (section 6).
6. **Sabermetrics contributes method more than formulas:** check that a metric is reliable before charging for it, shrink small samples, charge only for what the actor controls, and use a fixed replacement level (section 1).

The biggest limit is that baseball has an outcome, runs, to calibrate weights against. Code has no such outcome. So the score stays a policy, as the model says, and every threshold below is a placeholder until replayed on real history.

## How to read this

- **Read:** I read the passage in the PDF page.
- **Summary:** I read it through a fetch tool that summarizes pages. Check quotes before reusing them.
- **Snippet:** seen only in a search result.
- **Own:** my design or inference. No source tests it. The linked source supports the idea, not the design.
- **Arithmetic:** I computed it. All examples use invented inputs, unless a source is named.

The repeated curve example is the model's: `penalty = ((value - target) / (limit - target))²`, with target 20 and limit 100 lines.

## 1. What sabermetrics offers

| Baseball idea | What it is | Use in Smog (**Own**) |
| --- | --- | --- |
| Three tests for a metric | Baseball Prospectus tests [descriptiveness, reliability and predictiveness](https://baseballprospectus.com/news/article/41748/prospectus-feature-the-expected-contribution) (Summary). It warns that a metric can be consistent and still useless | Every lens must pass before it is charged. **Reliability:** do two disjoint samples of PRs rate a piece alike? **Predictiveness:** does it predict later reverts, short-term churn or agent failure? **Independence:** does it add anything beyond length? |
| Stabilization | FanGraphs gives a common cut point: [correlation of .7 between samples of the same size](https://library.fangraphs.com/principles/sample-size/). Strikeout rate needs 60 PA, batting average 910 AB (Summary). It also says "there is no one point" | Compute each history lens's window from your own history. The model says no minimum commit count is published; this replaces that number with a local test. A lens that never reaches .7 is noise for that object |
| Regression to the mean | [Add league-average sample to the observed sample](https://blogs.fangraphs.com/fangraphs-prep-regression-towards-the-mean): (.375 × 250 + .335 × 450) / 700 ≈ .349 (Summary). The 450 is specific to that statistic | Shrink rates with few events. A test changed in 3 of 3 PRs, with crate mean 0.1 and k = 20, becomes (3 + 2) / 23 = 0.22. A test changed in 30 of 100 becomes (30 + 2) / 120 = 0.27. The raw rates (1.0 and 0.3) rank them the wrong way round |
| FIP | [Counts only results the pitcher controls](https://library.fangraphs.com/pitching/fip/), because hits on balls in play correlate poorly across seasons (Summary) | Charge a PR only for debt it added. Separate what the agent controls from noise. Measure run-to-run variation of mutation and coverage results as the model's 5.3 asks |
| Linear weights | [wOBA weighs each event by its run value](https://library.fangraphs.com/offense/woba/), and recomputes yearly (Summary) | Lens weights could be fitted to an outcome once you have enough reverts and failures. Until then they are policy. Do not refit often, because fitted weights can be exploited |
| Replacement level | WAR measures value above [a .294 winning percentage](https://library.fangraphs.com/misc/war/) (Summary), a fixed reference | Fix a reference: debt per line from a baseline agent on benchmark tickets, or from a template you consider good |
| Relative scale | [wRC+: league average is 100](https://library.fangraphs.com/offense/wrc/) (Summary) | **Do not copy this for gating.** A scale relative to your own recent code hides decline, because when everything worsens the average stays at 100 |
| Park and position adjustment | WAR is ["context, league, and park neutral"](https://library.fangraphs.com/misc/war/) (Summary) | Set different targets for parsers, glue code and tests. Humans assign each area, because an agent could otherwise move code to a lenient one |
| Humility about precision | ["WAR should be used as a guide for separating groups of players"](https://library.fangraphs.com/misc/war/) (Summary) | Report bands. Do not treat 0.899 and 0.901 as different without a noise margin |

A warning from baseball: FiveThirtyEight and other critics argue that managers optimize saves over wins. [Bill James disputes that the save rule drove this](https://www.billjamesonline.com/article805/?F_All=y) (Snippet; the FiveThirtyEight page no longer opens). So even that familiar case of a metric distorting behavior is contested.

## 2. Your proposals, tested

### 2.1 Whole codebase at 0.9 or better

**What goes wrong:** with a line-weighted score (Arithmetic):

| Codebase | Starts at | Lines of score-0 code to reach 0.90 | Lines of score-0.5 code to reach 0.90 |
| --- | --- | --- | --- |
| 10,000 lines | 0.95 | 556 | 1,250 |
| 1,000,000 lines | 0.95 | 55,556 | 125,000 |

- **Concentrated damage hides.** A 5,000-line module at 0.95 falling to 0 moves that 1,000,000-line codebase from 0.950 to 0.945.
- **Padding helps.** Adding 100,000 lines of trivial code at 1.0 raises it from 0.950 to 0.955.
- **Blame is wrong.** Once the score is below 0.9, every PR blocks, including PRs that did nothing wrong. The model requires that every finding be clearable by the PR.

**Keep it as a freeze trigger.** Google's SRE policy is the template. An error budget is ["1 minus the SLO"](https://sre.google/workbook/error-budget-policy/) over a rolling four weeks. When it is spent, they ["halt all changes and releases other than P0 issues or security fixes"](https://sre.google/workbook/error-budget-policy/) (Summary). In Smog (**Own**): above 0.9, normal gates apply. Below 0.9, only PRs with net negative debt, or a human-approved exception, can merge.

### 2.2 New code at 0.9 or better

SonarQube's default gate works this way. It is [conditioned only on new code](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/): no new issues, 80% coverage, 3% duplication (Summary). This fits a large codebase, because the new code's size is the denominator.

Three exploits (**Own**):

- **Choose the softer regime.** If modified code has a budget and new code has a floor, the agent adds logic to an existing function rather than creating a new one. So the same curve must apply to both, and only the allowance may differ.
- **Stay under an exemption.** Sonar ignores coverage and duplication [under 20 new lines](https://docs.sonarsource.com/sonarqube-server/latest/quality-standards-administration/managing-quality-gates/introduction-to-quality-gates/) (Summary). A factory that splits work into small PRs could stay under such a rule indefinitely. Do not exempt small changes. Use the ledger's cumulative numbers instead, so a small PR has enough data.
- **Split to pass.** See section 5.

To make it concrete, 0.9 needs a mapping from penalty to score. With `score = exp(-penalty)`, which never reaches 0, the model's curve gives (Arithmetic):

| Score | Penalty | Function length |
| --- | --- | --- |
| 0.90 | 0.105 | 46 lines |
| 0.70 | 0.357 | 68 lines |
| 0.37 | 1.000 | 100 lines |

If 46 lines looks wrong for your floor of 0.9, change the target and limit, not the mapping.

### 2.3 Budget for modified code

Your budget works well with a convex curve, because a fixed penalty budget tightens by itself as a piece gets worse. With a budget of 0.05 per PR (Arithmetic):

| Function length now | Lines it may grow |
| --- | --- |
| 20 | 17.9 |
| 60 | 3.8 |
| 80 | 2.6 |
| 100 | 2.0 |

This gives agents room on healthy code, and almost none on bad code. No separate "must fix what you touch" rule is needed for it.

**The hole is repetition.** The model's rule 5.1 checks one PR at a time, so a function can reach 100 lines in 20 PRs of 0.05 each. Add a second limit over a rolling window.

Radiation protection uses this exact form: ["20 mSv per year, averaged over defined periods of 5 years, with no single year exceeding 50 mSv"](https://icrpaedia.org/Dose_limits) (Summary). It is only an analogy. For a piece (**Own**):

- No single PR adds more than 0.05.
- The last 50 PRs on `main` together add no more than 0.15 to it, read from the ledger.

A [Betterer-style ratchet](https://phenomnomnominal.github.io/betterer/docs/introduction) stores a baseline and fails when a result gets worse (Summary). That is a zero-budget version. It suits hard counts, such as the number of files over the floor.

### 2.4 No file below 0.7

Sound, but with three traps (**Own**):

- **Old code.** Model 4.5 notes that with a minimum across all pieces, "one old function fixes the score forever". Apply the floor strictly to new pieces. Existing pieces under the floor are frozen: they may not get worse, and their count may only go down.
- **Averaging inside the file.** A line-weighted file score lets 400 good lines hide a 150-line function, and moving a bad function into a large good file improves its file. A file's score should be its worst item, or the mean of its worst items.
- **Escaping the floor.** Moving code to an excluded path, or reclassifying it as generated, avoids the floor. Excluded paths must be human-owned configuration, as model 6.1 says, and the exclusion list must be fail-closed.

Use the floor at every level: function, file, module, crate. A crate at 0.8 in a codebase at 0.95 is what a whole-codebase score cannot show.

### 2.5 Three holes in the model's current rules

- **Allowance per changed line can be farmed.** Rule 5.1 grows the allowance with lines changed, so reformatting code buys room for debt. Count only added lines that are not cosmetic (`metrics-1` P2, P4; `metrics-2` P3). Add a small base allowance so a one-line PR can still add a small amount.
- **Credit can be laundered.** "Removing debt earns credit" lets an agent split or delete easy things to pay for hard debt elsewhere. Cap credit, keep it inside the same crate, and give none for code that moved or split. Move detection should use `metrics-1` Item identity.
- **A clamp removes the marginal cost.** `max(0, ...)` in model 4.6, or any floor at 0, makes further damage free once reached. Use a form that keeps falling.

## 3. Keeping a large codebase sensitive

Each ratio scales badly. These do not (**Own**, combining the sources named):

| Mechanism | Why size does not matter | Source of the idea |
| --- | --- | --- |
| Absolute debt per PR | No division by codebase size | Model 5.1 |
| Equilibrium score | Uses recent PRs only (section 8) | Own |
| Floors per module and crate | Each is judged at its own size | Own |
| Mean of the worst K lines, with K fixed | A fixed window cannot be diluted by padding | [Expected shortfall](https://en.wikipedia.org/wiki/Expected_shortfall) (Summary) |
| Change detection on the PR stream | Sees a sustained shift even when each PR passes | [CUSUM, EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm) (Summary) |
| Funnel plot across modules | Limits narrow with size | [Spiegelhalter](https://rdrr.io/cran/FunnelPlotR/man/funnel_plot.html) (Summary) |
| Hotspot-weighted score | Weighted to code that is being changed | [CodeScene](https://codescene.io/docs/guides/technical/code-health.html) (Summary) |

**Worst K lines, example (Arithmetic).** The 5,000-line module from 2.1 moves the whole-codebase score by 0.005. If the worst 10,000 lines averaged 0.6, they now average about 0.3. A percentage window would grow as the codebase grows and take in better code, so a fixed K is harder to pad.

**Change detection, example.** PR debt can drift upward while every PR passes its gate. NIST says a CUSUM is ["more efficient in detecting small shifts"](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm) than a Shewhart chart for shifts of 2 sigma or less, and suggests k as half the shift and h of 4 or 5 (Summary). An EWMA with λ of 0.2 to 0.3 [does similar work](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm) (Summary). My numbers for how many PRs each takes to notice, with k = 0.5 and h = 5:

| Sustained shift in PR debt | Per-PR limit at 3 sigma | CUSUM |
| --- | --- | --- |
| None (false alarm interval) | 741 | 929 |
| 0.5 sigma | 161 | 38 |
| 1 sigma | 44 | 10.5 |

The per-PR column is computed for a one-sided limit. The CUSUM column is simulated, with 4,000 runs per row. Both assume independent, normally distributed values. NIST states the same assumption for the EWMA. Real PR debt will be skewed with many zeros, so calibrate on your own history before trusting these numbers. An alarm should prompt investigation and not block a PR, because no single PR caused it.

**Funnel plots.** A league table ranks noise when units differ in size. A funnel plot draws limits around a target, with [95% and 99.8% limits](https://rdrr.io/cran/FunnelPlotR/man/funnel_plot.html), and can widen them for overdispersion (Summary). Plot each crate's debt per line against its lines: small crates can vary widely without alarm, and large crates cannot hide.

**Few events.** SRE notes that with 10 requests an hour, [one failure produces a 1,000x burn rate](https://sre.google/workbook/alerting-on-slos/) (Summary). Its remedies include grouping services and lengthening windows. The same applies to small crates: group them, or use longer windows.

## 4. Other measurements

The model already has line-weighted median, p90 and maximum. These add to them:

| Measure | Answers | Evidence | Weakness |
| --- | --- | --- | --- |
| Share of lines per band | How much code is risky? | SIG's thresholds are the values at [70%, 80% and 90% of code](https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf), weighted by lines, across 100 systems. McCabe gives 6, 8 and 14 (15 in the paper's other passage) (Read) | Band edges are cliffs. Java and C# |
| Mean of the worst K lines | How bad is the tail? | Expected shortfall [accounts for severity beyond the cutoff](https://en.wikipedia.org/wiki/Expected_shortfall) (Summary). Basel moved [from VaR to it](https://www.bis.org/bcbs/publ/d352.htm) (Summary). A percentile says nothing about what lies beyond it | Finance, not code |
| Squale mark | One number that stresses bad pieces | [`mark = -log_w(average(w^-mark_i))`](https://www.squale.org/quality-models-site/research-deliverables/WP1.3_ICSM-2009_ShortPaper.pdf), marks 0 to 3. "stresses bad quality instead of averaging" (Read) | A ratio, so it cannot be summed across PRs. A [related paper warns](https://hal.archives-ouvertes.fr/inria-00637367) some weightings make overall quality fall when a component improves (Snippet) |
| Theil index | Is debt concentrated, and by what? | [Decomposes by group](https://ercim-news.ercim.eu/en88/special/seeing-the-forest-for-the-trees-with-new-econometric-aggregation-techniques): on Debian, package explained file-size inequality better than language (Summary) | [Inequality indices correlate highly with each other](https://www.slideshare.net/slideshow/icsm-2011-12654311/12654311) (Snippet), so pick one. Report only |
| Geometric mean of groups | Non-compensating score across unrelated groups | The HDI uses it: ["a low achievement in one dimension is not anymore linearly compensated for by high achievement in another"](https://www.englishschool.ac.cy/udata/contents/files/docs/Departments/Economics/as_a2_resources/New-HDI-2010.pdf) (Read, in a school's copy of what appears to be UNDP's FAQ) | A zero anywhere gives zero. Needs the exp mapping or a floor |
| Debt slope | Is it getting worse? | Own; `metrics-2` C2 | Depends on the chosen lenses |
| Equilibrium score | Where is it heading? | Section 8, Own | Noisy with few PRs |
| Hotspot score | Is the code we change healthy? | CodeScene reports [hotspot, average and worst performer](https://helpcenter.codescene.com/articles/8038123-what-are-the-different-code-health-scores) (Snippet), and calls hotspots most critical. It is a vendor | Rewards not touching bad code |

**Why these beat a mean (Arithmetic).** Take 1,000 pieces with mark 3, and 10 with mark 0. The mean is 2.97. A Squale mark with w = 9 is 2.04. The value 9 is my choice: the short paper does not state its weights.

**Combining unrelated parts.** Say structure, tests and PR hygiene score 0.1, 1 and 1. The arithmetic mean is 0.70 and the geometric mean is 0.46. So use the geometric mean, or a minimum, across unrelated groups.

**Fix for model 4.4 (Own).** Taking the worst lens leaves everything else free. Group correlated lenses (`metrics-1` C1): take the worst within a group, plus a small share of the others, and sum across groups. Length and complexity are then not charged twice, and tests or coupling are not free.

**Median creep below the target is invisible.** Model 4.3 says the curve already charges for creep. It charges only above the target: the median moving from 8 to 19 lines costs nothing with a target of 20. Track the line-weighted median as its own lens, and do not move the target down to catch it. Do not give credit below the target, because agents could farm it with tiny functions.

## 5. Curves

**Shape (Arithmetic).** All use target 20, limit 100. The exponential form is `(b^x - 1) / (b - 1)`, with `x = (value - target) / (limit - target)`, and b = 9 is my choice.

| Lines | Linear | Quadratic | Cubic | Exponential |
| --- | --- | --- | --- | --- |
| 30 | 0.125 | 0.016 | 0.002 | 0.04 |
| 60 | 0.50 | 0.25 | 0.125 | 0.25 |
| 100 | 1.00 | 1.00 | 1.00 | 1.00 |
| 120 | 1.25 | 1.56 | 1.95 | 1.82 |
| 150 | 1.63 | 2.64 | 4.29 | 4.32 |

Higher powers are softer near the target and harsher past the limit. Quadratic is a sensible default, because it is easy to explain. I found no evidence favoring any power for code.

**The side effect: convex curves reward splitting.** Any curve that starts at 0 and hurts more and more charges one big thing more than its parts. "Hurts more and more" and "does not reward splitting" conflict, mathematically (Arithmetic):

| Same code as | Penalty |
| --- | --- |
| One function of 60 lines | 0.25 |
| Two of 30 | 0.03 |
| Three of 20 | 0 |
| One function of 100 lines | 1.00 |
| Four of 25 | 0.02 |
| Five of 20 | 0 |

Model 3.10 names guards, but they must be priced to compete with a 100% discount. Build the guard into the measure (**Own**, untested):

```
effective_length(f) = own_length(f) + α × Σ effective_length(c)
                      for each private function c whose only caller is f
```

With α = 1, splitting into one-caller helpers saves nothing. With α = 0.5, the 60 lines split into three functions count as 40, costing 0.06. α below 1 is needed, because `metrics-2` reports evidence that decomposition lowers maintenance effort. `metrics-2` F8 gives the call-graph data. Do the same for types: nested structs used by one owner count toward the owner's fields.

**Tail form.** With unbounded curves, one enormous legacy item can dominate the stock score. Use a knee: quadratic to a far limit, then a straight line at the same slope. The cost of a further line stays positive, and the total stays readable. Do not cap it, or worsening becomes free.

**Your paragraph rule.** "10 is the target, 15 is tolerable, then serious points" needs two slopes (**Own**; I found no study of paragraph length):

```
paragraph penalty = 0                         n ≤ 10
                  = 0.02 × (n - 10)           10 < n ≤ 15
                  = 0.10 + 0.10 × (n - 15)²   n > 15
```

| Paragraph lines | 10 | 11 | 15 | 16 | 17 | 18 | 20 | 25 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Penalty | 0 | 0.02 | 0.10 | 0.20 | 0.50 | 1.00 | 2.60 | 10.10 |

So 18 lines costs as much as a function at its limit. Rather than the largest paragraph only, sum over all paragraphs in a function, or a function with one 18-line paragraph can add others for free.

**The exploit is a blank line.** It costs nothing and rustfmt allows it: [`blank_lines_upper_bound` defaults to 1, `blank_lines_lower_bound` to 0](https://raw.githubusercontent.com/rust-lang/rustfmt/main/Configurations.md) (Summary). Partial guards:

- Merge a paragraph of fewer than 3 statements into the next.
- Do not count a comment as a separator.
- Report blank-line density.
- Keep function length charged independently.

An agent that inserts a blank line every 10 lines still passes. That may be acceptable if the groups make sense, but this lens is weak on its own, and I would start it with a low weight.

## 6. Gaming resistance

**What kind of gaming?** Manheim and Garrabrant name [four ways a proxy fails](https://ar5iv.arxiv.org/html/1803.04585) (Summary). Each needs a different defense (**Own**):

| Type | Meaning | Defense |
| --- | --- | --- |
| Regressional | Selecting on the proxy also selects its noise | Margins, shrinkage |
| Extremal | The link fails at extreme values | Do not reward beyond a target. No credit for tiny functions |
| Causal | Changing the proxy does not change the goal | Test predictiveness. Do not gate on weak proxies |
| Adversarial | Another actor responds to the metric | Everything below |

Gaming by agents is measured. In [ImpossibleBench](https://arxiv.org/html/2510.20270v1), tasks are impossible, so any pass is a cheat: GPT-5 reached 54%, o3 49% and Claude Opus 4.1 50% on one benchmark. Claude models mainly modified tests (Summary). Results vary a lot by benchmark and prompt.

**Defenses, strongest first (all Own in this application):**

1. **Exploit suite.** Write each known exploit as a test of Smog itself: a code pair where the transformed version must not score better. Examples: split into one-caller helpers, add blank lines, rename, move a function to another file, nest fields in a struct, add trivial code. Each new exploit found becomes a test. This keeps the scoring honest and is the cheapest defense here.

2. **Sealed lenses.** Keep some lenses out of the agent's view: not in its findings, not in its repository. Do not gate on them, because model 6.2 requires a finding to be clearable. Instead, watch for divergence: if open lenses improve and sealed lenses do not, that points to gaming.
   - The support is mixed. In ImpossibleBench, hiding tests [cut cheating to near zero, but also degraded performance](https://arxiv.org/html/2510.20270v1), while read-only tests were a middle ground that does not stop special-casing (Summary).
   - StrongDM says its scenarios are ["often stored outside the codebase"](https://simonwillison.net/2026/Feb/7/software-factory/), and compares them to a holdout set (Summary).
   - This limits model 6.2, so state plainly which lenses are open.

3. **Frozen references.** Set targets from a frozen template or benchmark, not from recent code. Thresholds from your own rolling percentiles fall as quality falls. [SIG's benchmark method](https://list.inf.unibe.ch/hyperkitty/list/moose-dev@list.inf.unibe.ch/message/5JKRBNHFQI3AFFUZJELPGASSYK4HWQPO/attachment/4/Alves101.pdf) gives the procedure (Read). Change the references only by human decision.

4. **Ledger keyed by identity.** Debt follows the item through renames and moves, so these do not reset a budget. It lives outside the agent's reach.

5. **Seeded bad PRs.** Regularly run known-bad PRs through the gate without merging. Report what share is caught, per exploit class. This resembles [Mills' error seeding](https://www.geeksforgeeks.org/?p=232962) (Snippet), though a [1999 paper finds no gain from seeding for defect estimates](https://repository.hku.hk/bitstream/10722/43501/1/49240.pdf) under thorough testing (Snippet). My use differs: it tests the gate, not the defect count.

6. **Red-team agent.** Ask an agent to raise the score without improving the code, or to land named harm while passing every gate. Each success goes in the exploit suite. Hardt et al. model this as [a game with a cost of changing the input](https://arxiv.org/abs/1506.06980), and note that classifier performance "may deteriorate sharply" (Summary). Their results concern classifiers, not code.

7. **Make the real fix cheaper than the fake.** Kleinberg and Raghavan characterize [when agents can be led to the intended effort instead of gaming](https://arxiv.org/abs/1807.05307), and say a simple linear mechanism suffices if any reasonable one does (Summary). Practically, rate each lens by how much a fake costs against a fix. Blank lines cost nothing, so that lens is weak. Layer violations are expensive to hide, so that rule is strong.

8. **Mute weak proxies.** Holmström and Milgrom show that [paying on measured tasks moves effort away from unmeasured ones](https://edegan.com/wiki/Holmstrom_Milgrom_(1991)_-_Multitask_Principal_Agent_Analyses) (Snippet), so muted incentives can be optimal. So comment density and test counts should stay report-only until they pass the three tests.

9. **Limit what retries reveal.** The Ladder shows that [repeated evaluation lets participants overfit a holdout](https://proceedings.mlr.press/v37/blum15.html), and reveals a new score only when it beats the best by a margin (Summary, with the margin from Snippet). In ImpossibleBench, multiple submissions raised cheating [from 33% to 38%](https://arxiv.org/html/2510.20270v1) on average (Summary). Do not report sealed lenses per PR. Track failed CI runs (`metrics-1` P9).

10. **Random audit.** Pick a random share of merged PRs for human or sealed review. The agent cannot tell which. This also validates the score itself. I did not look for evidence on audit rates.

**Exploits against your rules:**

| Rule | Exploit | Defense |
| --- | --- | --- |
| Codebase ≥ 0.9 | Add trivial code | PR size limit, fixed worst-K lines, tests for trivial code in the suite |
| New code ≥ 0.9 | Grow an existing function instead | Same curve for new and modified |
| Modified budget | Many small PRs | Rolling window in the ledger |
| Modified budget | Rename to reset | Item identity |
| File ≥ 0.7 | Dilute within a file, or split | File score from worst items, effective length |
| Curve | Split | Effective length |
| Paragraph | Blank lines | Section 5 |
| PR size | Stack many PRs | Budget per ticket as well as per PR. Disconnected-group check (`metrics-1` P1) |
| Debt credit | Launder | Cap, same crate, none for moves |
| Excluded paths | Move code there | Human-owned list, fail closed |

## 7. Hard rules

**Test for "hard" (Own).** A rule is hard only if all hold. Otherwise use a curve:

- A violation is never acceptable.
- It is deterministic, with no false positives.
- The PR can clear it.

Paragraph length fails the first, as you said. The file floor is a hard floor on a soft scale, so it needs the old-code handling in 2.4.

**Strength, in order (Own):** make the violation a compile error, then a compiler-backed lint, then a syntax rule. A private field cannot be gamed. A syntax rule can.

**Tools:**

| Tool | Good for | Limits |
| --- | --- | --- |
| Rust visibility, sealed traits, separate crates | Domain invariants, layers | Crate splits have a cost |
| [Clippy `disallowed-types`, `disallowed-methods`](https://doc.rust-lang.org/clippy/lint_configuration.html) | Banning named items, with a reason and replacement (Summary) | Applies across its configuration scope. I saw no per-folder option |
| [ast-grep](https://ast-grep.github.io/guide/project/lint-rule.html) | Syntax rules in YAML, with per-rule `files` and `ignores` globs (Summary) | Syntax only, as far as the page shows. Has an `ast-grep-ignore` comment |
| [Dylint](https://blog.trailofbits.com/2021/11/09/write-rust-lints-without-forking-clippy/) | Your own lints from libraries, with compiler knowledge (Snippet) | [Pinned nightly](https://trailofbits.com/tools/dylint/) (Snippet) |
| [cargo-pup](https://github.com/DataDog/cargo-pup) | Architecture assertions, such as `restrict_imports` on modules, and trait rules (Summary) | Nightly, pinned to `nightly-2026-01-22` on that page. No mention of struct fields |
| Own `syn` check | Whatever is left | No macro expansion |

**Your rules (Own, except tools named):**

| Rule | Check | How it gets dodged | Close it with |
| --- | --- | --- | --- |
| No layer violations | Allowed-edge list on crate and module graphs (model 3.1), or cargo-pup's `restrict_imports` | Re-export through a permitted module. New crate or module with no layer. Moving code to a low "common" crate | Check resolved definitions, not `use` paths. Every crate and module needs a layer, or the check fails |
| Correct use of attribute structs | **I do not know this rule's exact content.** Please read it to me. Best encoded by making misuse a type error, with a private constructor. Otherwise a Dylint | Type alias, wrapper, macro | Resolve types via the compiler, not by name |
| No public fields in domain models | Flag `pub`, `pub(crate)`, `pub(super)` and `pub` tuple fields on types in the domain layer | Moving the type out of the domain folder. `Deref` to an inner struct with public fields. A `fn x_mut(&mut self) -> &mut T`. Getter plus setter (`metrics-1` S5). Macro-generated fields | Scope by layer map, not only by path. Also ban those forms. A compiler-backed lint sees expanded code, `syn` does not |
| Correct folder structure | Allowlist of paths and name patterns. Fail on anything unlisted | `#[path = ".."]`, `include!`. New catch-all folder (`metrics-2` M12) | Ban both. Only humans can change the allowlist |

**Suppressions.** Model 3.1 lists new `allow` attributes and `#[mutants::skip]`. Add `#[expect(..)]`, `ast-grep-ignore` comments, and changes to any tool's config. Exceptions go in a human-owned list with a reason.

**A hard rule has no budget.** If a rule often needs exceptions, it is a soft rule and should move to a curve.

## 8. The end goal: health, agent capacity, poisoning

"Poisoning" appears nowhere in the model or the Smog notes I searched. I take it to mean low-quality code entering the codebase that also makes later agent work worse. Please correct this if you meant something else, such as deliberate attacks.

One number cannot carry three different questions, so I propose three outputs (**Own**):

```
HEALTH    0.95, worst 10k lines 0.58, hotspots 0.81, slope -0.002 per 100 PRs
CAPACITY  equilibrium 0.90, freeze 0.92, runway 3,000 PRs (150 days), sustainable 20 PRs/day
POISON    gate caught 37/40 seeded PRs; contagion +0.3 debt/100 lines; dose test: success -10% at dose 3
```

The numbers are examples.

### Health

The model's score, with worst-K lines, hotspot score and slope beside it. A human reads this.

### Agent capacity

This uses the model's formula, `score = 100 - debt per 1,000 lines`, with `L` lines and `D` debt. Recent PRs add `d` debt and `l` net lines each. The freeze line is at density `f` (Arithmetic):

```
equilibrium density = d / l
runway in PRs       = (f × L - D) / (d - f × l)        when d > f × l
excess per PR       = d - f × l
sustainable PRs/day = cleanup debt removed per day / excess per PR
```

**Why equilibrium matters.** Current density always moves toward the density of what is being added. So a large codebase at 95 with PRs at equilibrium 90 is heading to 90, however large it is. Equilibrium is the number that does not dilute.

Example with `d = 5`, `l = 500`, so equilibrium 90, and a freeze at 92 (`f = 0.008`):

| Codebase | Density now | Score now | Runway | At 20 PRs/day |
| --- | --- | --- | --- | --- |
| 10,000 lines | 5 per 1,000 | 95 | 30 PRs | 1.5 days |
| 1,000,000 lines | 5 per 1,000 | 95 | 3,000 PRs | 150 days |

Same score, same PR quality, and 100 times the runway. Excess per PR is 5 - 4 = 1. So a cleanup process removing 20 debt per day supports 20 PRs per day indefinitely. If `d ≤ f × l`, this measure sets no limit, and review or test capacity will limit you first.

Google's multi-window alerting is the model for reacting to this: [burn rate is how fast the budget is consumed](https://sre.google/workbook/alerting-on-slos/), and an alert fires only when both a long and a short window exceed the threshold (Summary). Their values (14.4, 6 and 1) are for 99.9% availability, so they do not transfer. The structure does: a fast burn stops the factory, a slow burn opens a cleanup ticket.

### Poisoning tolerance

**What the evidence says:**

| Source | Finding | Limit |
| --- | --- | --- |
| [Comment Traps](https://arxiv.org/abs/2512.20334) (Summary) | Defective commented-out code in context raised generated defects by up to 58.17%. Telling the tool to ignore it reduced defects by at most 21.84% | Copilot and Cursor. Abstract only |
| [Sourcery](https://sourcery.ai/blog/does-bad-code-make-agents-worse) (Summary) | Success was 81.9% with maximum cognitive complexity of 9 or less, and 56.2% above. Average complexity and smell counts did not correlate | 9 tasks, a blog, no statistical tests. The agent and task mattered more |
| [Borg et al.](https://arxiv.org/html/2601.02200v1) (Summary) | Refactoring break rates were lower on healthy code for five medium models, such as 39.9% against 50.0%. For Sonnet and Claude the difference was not significant. AUC was only 0.54 to 0.57 | Competitive-programming Python. Authors include CodeScene staff |
| [Sonar](https://www.sonarsource.com/blog/your-ai-agent-doesnt-know-your-codebases-context-or-constraints/) (Summary) | About 540 Claude Code runs. Clean repositories used 7.2% fewer input and 8.5% fewer output tokens, and pass rate changed by -0.9 points | Vendor. Setup not on the page |
| [He et al.](https://arxiv.org/abs/2511.04427) (Summary) | Cursor adoption gave transient velocity and persistent complexity and warnings, and these drive later slowdown | Abstract only. Observational |
| [Zhu et al.](https://arxiv.org/html/2605.02741v1) (Summary) | In one multi-agent framework, code volume correlated ρ = 0.94 with architectural smells | Small sample, preprint, may just show size |

**My reading:** bad code raises cost, and lowers success for some agents and tasks. Whether strong current agents lose much success is unclear. One small study suggests the worst piece matters more than the average, which would support floors and tail measures over averages. That is not enough to set a number. [CodeScene's article](https://codescene.com/blog/code-health-a-prerequisite-for-successful-agent-deployment) sets no numeric threshold either (Summary).

**So measure it directly:**

1. **Exposure.** The share of agent PRs in the window that touched or read a piece under the floor. This is a count you can have now.
2. **Contagion.** For recent PRs, compare debt per added line against the penalty of the code they touched, controlling for crate. A positive slope means bad code begets bad code. It is observational, and agents may be sent to hard areas, so treat it as a signal.
3. **Gate leak rate.** The seeded PR catch rate from section 6.
4. **Dose-response test.** This is the only one that answers your question directly:
   - Copy the repository at a fixed commit.
   - Inject increasing doses of a poison class, and use the model's lenses to measure each dose. Sourcery degraded code with an LLM in a similar way.
   - Run the same K tickets on each dose with several attempts.
   - Measure hidden-test pass rate, tokens, loops, and debt added.
   - The result is a curve, and tolerance is the dose at which success falls by an amount you choose.

The dose test costs agent runs and needs repeats because agents vary, so run it occasionally. Results apply to that agent and those tickets. Repeat when the model changes. Different poison classes will have different curves, and I would test long functions, misleading comments, dead code and layer violations first.

**Tolerance** then is the remaining distance between the current dose and that point, with the gate leak rate showing how fast the dose can grow unnoticed.

## 9. A starting policy

All numbers are placeholders. Replay on history before use (see below).

| Layer | Rule | Block? |
| --- | --- | --- |
| Hard | Section 7 rules, plus model 3.1 | Blocks |
| Piece, new | Score ≥ 0.9 by effective length | Blocks |
| Piece, existing | Increase ≤ 0.05 per PR and ≤ 0.15 per 50 PRs | Blocks |
| Piece, floor | Function and file ≥ 0.7. Existing offenders frozen, and their count may not rise | Blocks |
| PR | Debt added ≤ base + rate × non-cosmetic added lines. Size limit. Budget per ticket | Blocks |
| Module | Crate ≥ 0.8, as a freeze for that crate | Freezes the crate |
| Codebase | Score ≥ 0.9 | Freezes feature work |
| Stream | CUSUM on PR debt, fast and slow burn | Opens a ticket, or stops the factory on fast burn |
| Sealed | Divergence, seeded PRs, random audit | Alerts humans |
| Report | Health, capacity, poison outputs | Never |

**Backtest before enabling.** Replay the rules over your squash-merged history and record what each would have blocked. Read a sample of those PRs. Then set limits where the blocks look right and tell the block rate to the humans. A rule blocking 40% of PRs would stop the factory, and one blocking none does nothing. Each history lens also gets the stabilization test from section 1 first.

**Build order:**

1. Item identity and the debt ledger. Most rules depend on them.
2. Exploit suite, alongside the first lenses.
3. Curves and flow gates, in report-only mode first.
4. Stock floors and freeze rules.
5. Seeded PRs, sealed lenses.
6. Dose test.

## 10. Decisions for Malte

1. What does the attribute struct rule say exactly?
2. Does "poisoning" mean low-quality code generally, or also deliberate attacks? I covered only the first.
3. Should a freeze stop features fully, or leave a small allowance? Who may override it? Google's policy [escalates disputes to the CTO](https://sre.google/workbook/error-budget-policy/) (Summary).
4. Do you accept sealed lenses, given that they limit the model's rule that agents see every finding?
5. Which α for effective length? 1 ignores splitting entirely, and 0.5 still rewards it.
6. Is a score on 0 to 1 the one you want shown? The model's 4.6 uses 100 minus density, while your 0.9 examples imply piece scores. I used both above. They behave alike at scale, but they should be unified.

## Not verified

- **None of this has run on real code.** The rules, examples and curves are untested. The only computed figures are arithmetic and one simulation.
- **Own designs with no test:** effective length, equilibrium score, runway, contagion, dose test, exploit suite, sealed-lens divergence, worst-K lines for code, and the paragraph curve.
- **Failed or partial:**
  - [qntm on ratchets](https://qntm.org/ratchet) (403).
  - [Mordal et al. CSMR 2011](https://hal.archives-ouvertes.fr/inria-00637367) blocked by a bot check, and its [PDF](https://core.ac.uk/download/49949578.pdf) gave 403, so the anomaly claim is a snippet and Squale's weight values are unread. Its [journal version](https://research.tue.nl/en/publications/software-quality-metrics-aggregation-in-industry/) showed only an abstract, so I do not know how Squale compared with the mean, Gini and Theil.
  - [UNDP technical notes](https://hdr.undp.org/sites/default/files/2021-22_technical_notes.pdf) (404), so the HDI passage comes from a copy hosted by a school, not from UNDP's site.
  - [OECD/JRC composite indicator handbook](https://one.oecd.org/document/STD/DOC(2005)3/en/pdf): not opened. My compensability point rests on the HDI material, not the handbook.
  - [FiveThirtyEight on the save](https://fivethirtyeight.com/features/goose-egg-new-save-stat-relief-pitchers) redirects away.
  - ImpossibleBench: first 100,000 of 113,373 characters.
- **Secondary only:** Holmström and Milgrom (excerpts and a wiki), Ladder's margin rule, Mills' seeding, Dylint details, Vasilescu et al. on index correlation, and the tail-risk motive for Basel's change (the BIS page names the change, not that reason). Regression and stabilization values are for baseball statistics and do not carry over.
- **Assumed from general knowledge, no source opened:** `#[path]` and `include!` can bypass a folder rule; compiler lints see macro-expanded code; `#[expect]` is a suppression form; `Deref` and `_mut` accessors act as field access.
- **Not searched:** evidence on audit rates, on paragraph length, or on any of this applied to Rust. I did not check Smog's ADRs, because this file changes nothing in the repository.
