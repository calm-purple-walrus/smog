# Code quality metrics: a catalogue

Prepared on 2026-11-08 as input for the Geiger research report. This document lists the metrics that tools compute, or that research proposes, for measuring the quality of source code. For each metric it gives a definition, its origin, a tool that computes it on Rust code, the validity evidence I found, and whether it can be computed on changed code alone. It does not evaluate the metrics against Geiger's plans.

## Summary

**Families covered:** size; function-level complexity; object-oriented coupling, cohesion and inheritance; module and architecture structure; code smells; duplication; static-analysis findings and technical-debt items; security measures; readability, understandability and naming; naturalness; comments and documentation; test quality; process and history; change-level (just-in-time) metrics and code review; dependencies and supply chain; Rust-specific measures; composite quality models and indices; AI-generated code; agent pull requests; and the outcome measures that studies use to validate all of these.

**Strongest validity evidence:**

- Process and history metrics. A review of 106 fault-prediction studies rated code churn, number of changes, module age and change-set size as the most effective metrics, and found that "Process metrics seem to be better at predicting post-release faults compared to any static code metrics" ([Radjenović et al. 2013][radj]). Two later studies agree ([Rahman & Devanbu 2013][rahman13]; [Majumder et al. 2022][majumder22], 700 GitHub projects). One review reported the opposite ranking (Hall et al., as summarised by [Radjenović][radj]).
- Change-level (just-in-time) metrics. Models built from change size, spread and history predict defect-inducing changes with moderate accuracy ([Kamei et al. 2013][kamei13]); simple models match deep-learning models ([Zeng et al. 2021][zeng21]); models lose accuracy over time ([McIntosh & Kamei 2018][mcintosh18]).
- Mutation score. Mutant detection correlates with real-fault detection independently of coverage ([Just et al. 2014][just14]); the correlation weakens once test-suite size is controlled ([Papadakis et al. 2018][papadakis18]).
- CBO, RFC and WMC, and coupling measures in general, are the best-supported object-oriented design metrics in the same review ([Radjenović et al. 2013][radj]).

**Weakest validity evidence:**

- Readability and understandability: "none of the 121 experimented metrics is able to capture code understandability" ([Scalabrino et al.][scalabrino19]); LLM readability judgments agree weakly with humans ([CoReEval][coreeval]).
- Halstead measures, inheritance depth (DIT, NOC) and lack of cohesion (LCOM) for fault prediction ([Radjenović et al. 2013][radj]).
- Static-analysis warning density and SonarQube technical-debt items: small or negligible relationships with defects ([Trautsch et al. 2023][trautsch23]; [Lenarduzzi et al. 2020][lenarduzzi20]; [Lenarduzzi et al. 2019][lenarduzzi19]).
- Metrics for AI-generated code and agent pull requests: proposed in 2025–2026, mostly single studies, mostly preprints, some by vendors.
- Rust-specific measures: unsafe code and panic sites have retrospective evidence (the share of known bugs that involve them); I found no study that relates their density to defects, and no crates.io-wide distributions for setting thresholds beyond the share of crates that use `unsafe`.

**Confounds that apply across families:** module size ("After controlling for size none of the metrics we studied were associated with fault-proneness anymore", [El Emam et al.][elemam]); test-suite size for coverage and mutation scores ([Inozemtseva & Holmes 2014][inozemtseva14]); study context ("evaluation context is king", [Chowdhury et al. 2022][chowdhury22]); and authorship by the vendor of the metric (CodeScene, SIG, Sonar, GitClear).

## How to read the tables

- **Level:** function, type, module, system, change, or test suite.
- **Definition:** precise enough to compute the metric. Where tools disagree, the variants are named.
- **Origin:** the defining paper or the tool documentation I used for the definition.
- **Rust tool:** a tool that computes the metric on Rust code; "none" if I found none. "Threshold lint" means the tool warns about each unit whose value exceeds a limit and does not output the value. RCA is [rust-code-analysis][rca]. In its source, the implementations of ABC, NPA, NPM and WMC are empty for Rust (they exist for Java only), so RCA computes for Rust only SLOC, PLOC, LLOC, CLOC, BLANK, CC, cognitive complexity, Halstead, MI, NARGS, NEXITS and NOM ([RCA source][rca-src]). RCA's last crates.io release is 0.0.25 (2023-01-13).
- **Validity evidence:** what the metric has been shown to predict or not to predict; "—" if I found nothing. Ratings written as "++", "+", "0" and "−" come from Table 5 of [Radjenović et al. 2013][radj], a review of 106 fault-prediction studies (1991–2011); the symbols mean strong positive, weak positive, no, and weak negative association with fault-proneness.
- **Changed code only:** "Yes" means the value for a changed unit can be computed from that unit's code or from the diff alone. "Partly" means it can be computed per changed unit but needs context outside the change: the dependency or call graph, version history, a test run, or a baseline. "No" means the metric is defined only for a whole module, system or time window.
- **Verification:** I opened every source I cite, either the full text or, where marked "(abstract)", only the abstract. Items I could not open are marked "(not opened)"; descriptions I could not check against a source are marked "unverified". Quotations are exact, except that double quotation marks inside a quotation are shown as single quotation marks.

## 1. Size

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Lines (physical lines) | file, function, system | Count of all lines, including blank and comment lines. | SonarQube `lines` [Sonar metrics][sonar-metrics]; RCA `SLOC` [RCA][rca] | RCA, tokei ("Lines") [tokei] | Radjenović: LOC "+" overall, "++" in pre-release and small studies, "+" in post-release and large studies [radj] | Yes |
| Non-comment lines of code (NCLOC; RCA `PLOC`; Lizard NLOC) | file, function, system | Lines with at least one character that is neither whitespace nor comment. | SonarQube `ncloc` [sonar-metrics]; RCA [rca]; [Lizard][lizard] | RCA, tokei ("Code"), Lizard, SonarQube [sonar-rust] | As above. In a maintenance experiment, "File size and the number of changes explained almost all of the modeled variation in effort" ([Sjøberg et al. 2013][sjoberg13], abstract) | Yes |
| Logical lines / statements (LLOC, NCSS, `statements`) | function, type, file | Number of statements. PMD's NCSS follows JavaNCSS: +1 per control keyword, assignment, declaration or statement expression; comments and line breaks ignored. | RCA `LLOC` [rca]; PMD NCSS [pmd-metrics]; SonarQube [sonar-metrics] | RCA | — | Yes |
| Comment lines and blank lines (CLOC, BLANK) | file, function | Number of comment lines and of empty lines. | RCA [rca]; SonarQube `comment_lines` [sonar-metrics] | RCA, tokei | See family 11 for comment density | Yes |
| Number of functions (NOM, `functions`) | file, type | Number of functions and methods; RCA counts closures separately. | RCA `NOM` [rca]; SonarQube [sonar-metrics]; CK "Number of methods" [ck] | RCA | — | Yes |
| Number of types and files (`classes`, `files`) | system | Number of classes (or types) and files. | SonarQube [sonar-metrics] | tokei (files); none for types | — | Yes, as a delta |
| Function length (unit size) | function | Lines of code per function. SIG rates the share of code in functions longer than 15, 30 and 60 lines; the 4-star limits are 48.0%, 24.2% and 9.1%. | [SIG/TÜV criteria 2026][sig-criteria]; Clippy `too_many_lines` [clippy-conf] | RCA (per function), Lizard, Clippy `too_many_lines` (pedantic, default 100; threshold lint) | See SIG model in family 17 | Yes |
| Parameters per function (NARGS, PARAM) | function | Number of formal parameters. SIG "unit interfacing" rates the share of code in functions with ≥3, ≥5 and ≥7 parameters; 4-star limits 15.4%, 3.4%, 0.9%. | RCA `NARGS` [rca]; [Lizard][lizard]; [SIG criteria][sig-criteria] | RCA, Lizard, Clippy `too_many_arguments` (complexity, default 7; threshold lint) [clippy-conf] | — | Yes |
| Exit points (NEXITS, returns) | function | Number of possible exits (return points) of a function. | RCA `NEXITS` [rca]; Lizard exit count [lizard-ext]; CK [ck]; Qlty "many return statements" [qlty-smells] | RCA, Lizard | — | Yes |
| Token count | function | Number of lexical tokens in a function. | [Lizard][lizard] | Lizard | — | Yes |
| ABC size | function, file | Counts of assignments (A), branches (B) and conditions (C); scalar size = sqrt(A² + B² + C²). | Fitzpatrick 1997 (not opened); RCA [rca]; magnitude formula per [Wikipedia][abc-wiki] | none (RCA's ABC is Java-only) | — | Yes |
| Automated Function Points (AFP) | system | Functional size counted automatically from source code; published by ISO as ISO/IEC 19515. | [OMG AFP 1.0, 2013][omg-afp] | none | — | No |
| Automated Enhancement Points (AEP) | change | Size of the functional and technical elements added, modified or deleted between two revisions. | [OMG AEP 1.0, 2017][omg-aep] | none | — | Yes |

**Evidence for the family.** Size is a moderate defect predictor and the main confound for the other structural metrics: in El Emam et al.'s study of a C++ framework, "After controlling for size none of the metrics we studied were associated with fault-proneness anymore" ([El Emam et al.][elemam]). A study of about 730K Java methods recommends "models that account for the maintenance indicator being used and the size of the methods being analyzed" ([Chowdhury et al. 2022][chowdhury22]). In a comparison of four functionally equivalent systems, "Only system size and low cohesion were strongly associated with increased maintenance effort" ([Sjøberg et al. 2012][sjoberg12]).

## 2. Function-level complexity

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Cyclomatic complexity (CC, v(G)) | function; summed per file or type | e − n + 2p of the control-flow graph; in practice the number of decision points + 1. Variants: "extended" also counts `&&` and `\|\|`; "modified" counts a whole switch or match as one decision ([Sonargraph][sonargraph], Lizard `-m` [lizard-ext]). Tools differ in which constructs count; RCA counts `if`, `for`, `while`, `loop`, match arms, `?`, `&&` and `\|\|` for Rust [rca-src]. | [McCabe 1976][mccabe76] | RCA, Lizard, cccc [cccc], debtmap [debtmap], SonarQube [sonar-rust], CodeScene [cs-lang] | Radjenović: "+" overall; effective in large post-release OO studies, not in small or procedural ones [radj]. Correlated with SLOC (R² 0.40 for Java, 0.44 for C) but "not strong enough to conclude that CC is redundant with SLOC" ([Landman et al.][landman]). Complexity metrics explain programmers' cognition "to a limited degree" ([Peitek et al., fMRI][peitek21]) | Yes |
| Cyclomatic density | function | CC divided by non-comment LOC. | Gill & Kemerer 1991, as summarised in [NIST SP 500-235][nist500235] (original not opened) | none (derivable from RCA output) | NIST reports it was "shown to be a statistically significant single value predictor of maintenance productivity" (one study) [nist500235] | Yes |
| Essential complexity (ev(G)) | function | CC of the control-flow graph after all structured-programming primitives are removed; 1 ≤ ev(G) ≤ v(G). | McCabe; defined in [NIST SP 500-235][nist500235] | none | — | Yes |
| Module design complexity (iv(G)) and integration complexity (S1) | function; system | iv(G) = CC of the graph after "design reduction" keeps only the logic that controls calls to other modules; S1 = Σ iv(G_i) − n + 1 over n modules. | [NIST SP 500-235][nist500235] | none | — | Yes (iv); No (S1) |
| NPATH | function | Number of acyclic execution paths; sequential decisions multiply (PMD: block = product of statement values; `if` chain = branches + guard complexity; loops = 1 + body + guard). | [Nejmeh 1988][nejmeh88]; rules in [PMD][pmd-metrics] | none | — | Yes |
| Cognitive complexity | function | +1 for each break in linear flow (if, else if, else, switch, loops, catch, labelled jumps, sequences of boolean operators, recursion) plus a nesting increment for flow breaks nested inside others; shorthand constructs add nothing. | [SonarSource white paper][sonar-cc]; [Campbell 2018][campbell18] | RCA, cccc, SonarQube, Lizard `-Ecognitive`, debtmap, Clippy `cognitive_complexity` (restriction, default 25; threshold lint) | "Cognitive Complexity positively correlates with comprehension time and subjective ratings of understandability. The metric showed mixed results for the correlation with the correctness of comprehension tasks and with physiological measures" ([Muñoz Barón et al.][baron20]). Diverged from EEG-measured cognitive load ([Hao et al.][hao23]). Construct weights are "based on intuition rather than on empirical evidence" ([Feitelson][feitelson23]). Clippy's own lint text: "We used to think it measured how hard a method is to understand" [clippy-cog] | Yes |
| Halstead measures | function, file | From distinct operators n1, distinct operands n2 and totals N1, N2: vocabulary n1+n2; length N1+N2; estimated length n1·log2 n1 + n2·log2 n2; volume V = N·log2 n; difficulty D = (n1/2)·(N2/n2); effort E = D·V; time E/18 s; bugs E^(2/3)/3000. | Halstead 1977 (book, not opened); formulas as implemented in [RCA][rca-src] | RCA; Lizard `-Ehalstead` (volume, difficulty, effort) | Radjenović: "0" for n1, n2, N1, N2; "inappropriate for software fault prediction"; N1 and N2 did better than n1 and n2 [radj]. Vocabulary size "burdens programmers' working memory" ([Peitek et al.][peitek21]) | Yes |
| Nesting depth | function | Deepest level of nested control structures. Variants: average block nesting depth ([Sonargraph][sonargraph]), number of nested structures (Lizard NS), CK "Max nested blocks" [ck]. | [Lizard extensions][lizard-ext]; [Sonargraph][sonargraph] | Clippy `excessive_nesting` (fires only once `excessive-nesting-threshold` is set; threshold lint) [clippy-conf], Lizard, debtmap | — | Yes |
| Knots | function | Number of crossings between control-flow jump arcs drawn beside the program text. | [Woodward, Hennell & Hedley 1979][woodward79] (not opened) | none | — | Yes |
| Information flow complexity (IFC, Henry–Kafura) | function | (fan-in × fan-out)²; weighted IFC multiplies by procedure length; fan-in and fan-out count calls, parameters and global-data flows (tools count these differently). | [Henry & Kafura 1981][henry81] (not opened); formulas per IEEE 982.2 as given by [Aivosto][aivosto-ifc] | none | — | Partly (needs call graph) |
| Function fan-in and fan-out | function | Number of functions that call a function, and number of functions it calls. | Lizard `-Eio` [lizard-ext] | Lizard; debtmap reports call-graph coupling | — | Partly |
| System complexity (Card & Agresti) | function, system | Structural complexity SC = fan-out²; data complexity DC = I/O variables / (fan-out + 1); SYSC = Σ(SC + DC); relative RSYSC = mean(SC + DC). | Card & Agresti 1988, as given by [Aivosto][aivosto-sysc] | none | Original study of 8 old systems: 4 "poor quality" systems had RSYSC ≥ 26.5, 4 "good quality" ones ≤ 25.3 [aivosto-sysc] | Partly |
| DepDegree | function | Number of data-flow (definition–use) dependencies between statements. | [Beyer & Fararooy 2010][beyer10] (definition paraphrased from [Peitek et al.][peitek21]; original not opened) | none | Part of Peitek's fMRI comparison of more than 41 metrics, which found limited explanatory power [peitek21] | Yes |
| Boolean expression complexity | function | Number of boolean operators in conditions. | Lizard `-Eboolcount` [lizard-ext]; Qlty "complex boolean logic" [qlty-smells]; CodeScene "Complex Conditional" [cs-health] | Lizard, Qlty [qlty-rust], CodeScene | — | Yes |
| Per-function construct counts | function, type | Counts of returns, loops, comparisons, try/catch blocks, parenthesised expressions, string and number literals, math operations, variables, anonymous and inner classes, lambdas, unique words and log statements. | [CK tool][ck] | none | — | Yes |

**Evidence for the family.** Complexity metrics track size: Radjenović et al. summarise that "complexity metrics are essentially a size measurement" and that "it seems complexity metrics are not bad fault predictors, but others are better" [radj]. For comprehension, a study of 121 code, documentation and developer metrics found that "none of the 121 experimented metrics is able to capture code understandability" ([Scalabrino et al.][scalabrino19]); a re-analysis of the same data found "a small but significant correlation" for some combined features ([Trockman et al. 2018][trockman18], abstract).

## 3. Object-oriented design: coupling, cohesion and inheritance

Rust has structs, enums, `impl` blocks and traits but no class inheritance. I found no tool that computes these metrics for Rust; RCA's NPA, NPM and WMC are implemented for Java only [rca-src]. Definitions below follow the comparative tables in [Briand, Wüst, Ikonomovski & Lounis (ICSE 1999)][briand99] unless another source is named.

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| CBO, CBO′, CBO Modified | type | Number of other classes a class is coupled to (uses methods or attributes of, or is used by). CBO′ excludes inheritance-based coupling; the CK tool's CBO counts types used, and "CBO Modified" counts references in both directions. | [Chidamber & Kemerer 1994][ck94]; [Briand 1999][briand99]; [CK tool][ck] | none | Radjenović: "++"; with WMC and RFC, "the best metrics from the CK metrics suite" [radj]. Not associated with faults after controlling for size ([El Emam et al.][elemam]) | Partly |
| RFC, RFC1 | type | Size of the response set: the class's methods plus methods invoked by them, transitively (RFC) or directly only (RFC1). | [Chidamber & Kemerer 1994][ck94]; [Briand 1999][briand99] | none | Radjenović: "++" [radj] | Partly |
| WMC | type | Sum of the complexities (usually CC) of a class's methods. | [Chidamber & Kemerer 1994][ck94]; [PMD][pmd-metrics] | none | Radjenović: "++" [radj] | Partly |
| Class fan-in and fan-out | type | Number of classes that reference a class (fan-in) and number of classes it references (fan-out). | [CK tool][ck]; [DesigniteJava][designite]; PMD `CLASS_FAN_OUT` [pmd-metrics] | none | Radjenović: coupling metrics did better than inheritance and cohesion metrics, and import coupling better than export coupling [radj] | Partly |
| MPC, DAC, DAC′ | type | MPC: number of method invocations in a class. DAC: number of attributes whose type is another class. DAC′: number of distinct classes used as attribute types. | [Li & Henry 1993][lihenry93]; definitions from [Briand 1999][briand99] | none | — | Yes |
| ICP, IH-ICP, NIH-ICP | type | Method invocations in a class weighted by the number of parameters of the invoked methods; IH counts only invocations of ancestors' methods, NIH only invocations of unrelated classes. | Lee et al. 1995, as defined in [Briand 1999][briand99] | none | NIH-ICP and an ICP variant entered the best fault-proneness model for one 83-class C++ system [briand99] | Partly |
| Briand et al. coupling measures (IFCAIC … OMMEC) | type | Counts of interactions between a class and other classes, named by relationship (A ancestors, D descendants, F friends, IF inverse friends, O others), interaction type (CA class–attribute, CM class–method, MM method–method) and direction (IC import, EC export). | [Briand, Devanbu & Melo 1997][briand97]; [Briand 1999][briand99] | none | "some of these coupling measures may be useful early quality indicators" ([Briand et al. 1997][briand97], abstract); OCAIC and OCMIC entered the best model in [briand99] | Partly |
| CTA, CTM | type | Coupling through abstract data types and through message passing. | Li, as listed by [Radjenović][radj] (definitions not opened) | none | — | Partly |
| Access to foreign data (ATFD) | function, type | Number of attributes of other classes that are used, directly or through accessors. | [Lanza & Marinescu 2006][lanza06]; [PMD][pmd-metrics] | none | Used in God Class and Feature Envy detection; no outcome evidence found | Partly |
| Coupling factor (COF, MOOD) | system | Share of possible class-to-class couplings (excluding inheritance) that exist. | Brito e Abreu ([MOOD 1996][mood96]); name from [Radjenović][radj] (formula not opened) | none | MOOD metrics were "outperformed by the Martin suite"; "In the MOOD suite, the CF metric had the highest impact" [radj] | No |
| LCOM1 – LCOM5, Co, Coh | type | LCOM1: method pairs sharing no attribute. LCOM2: that number minus the pairs that share one, floored at 0. LCOM3: connected components of the graph of methods linked by shared attributes. LCOM4: LCOM3 plus edges for method calls. Co = 2(E − (V − 1)) / ((V − 1)(V − 2)) on the LCOM4 graph. LCOM5 = ((1/a)·Σ_j p(A_j) − m) / (1 − m), where p(A_j) is the number of methods using attribute j. Coh = Σ_j p(A_j) / (m·a). | [Briand 1999][briand99]; CK 1991/1994, Hitz & Montazeri 1995, Henderson-Sellers 1996 as cited there | none. CodeScene computes LCOM4 for its "Low Cohesion" smell and lists Rust as supported, but does not document how it maps Rust `impl` blocks [cs-health] | Radjenović: LCOM "0"; "not very successful in finding faults" [radj]. In [Briand 1999][briand99], LCOM3 was significant and LCOM4 was not, although they correlate at Spearman 0.93 | Partly |
| TCC, LCC | type | Share of pairs of public methods that are connected through directly (TCC) or also indirectly (LCC) shared attribute use. | [Bieman & Kang 1995][bieman95]; [PMD][pmd-metrics]; [CK tool][ck] | none | Radjenović: predictive performance "modest"; LCC slightly better than TCC [radj]. LCC significant and TCC not, at Spearman 0.90 between them [briand99] | Partly |
| ICH | type | Invocations of the class's own methods, weighted by the number of parameters. | Lee et al. 1995, as defined in [Briand 1999][briand99] | none | Entered the best fault model, though the authors judge it "unlikely to measure cohesion" [briand99] | Yes |
| C3 (conceptual cohesion of classes) | type | Textual similarity, via latent semantic indexing, between the comments and identifiers of a class's methods. | [Marcus, Poshyvanyk & Ferenc 2008][marcus08] (abstract) | none | "combining C3 with existing structural cohesion metrics proves to be a better predictor of faulty classes" (abstract) | Yes |
| LSCC, SCC | type | LSCC: cohesion from the degree to which each pair of methods shares attribute references. SCC: similarity-based class cohesion. | [Al Dallal & Briand 2012][aldallal12] (abstract); SCC name from [Radjenović][radj] (definition not opened) | none | In two studies by Al Dallal, CAM and the proposed metric "performed well" [radj] | Yes |
| DIT, NOC | type | DIT: depth of the class in the inheritance tree. NOC: number of immediate subclasses. | [Chidamber & Kemerer 1994][ck94]; [CK tool][ck] | none (no class inheritance in Rust) | Radjenović: "DIT and NOC were reported as untrustworthy"; NOC was "occasionally inverse significant" [radj] | Partly |
| Other inheritance and polymorphism measures | type, system | NOP (parents), NOD (descendants), NOA (ancestors), AID (average inheritance depth), CLD (class-to-leaf depth), NMO, NMI, NMA (methods overridden, inherited, added), SIX (specialization index), NOH (hierarchies), ANA, MFA, MIF, AIF, POF. | Lorenz & Kidd 1994, Henderson-Sellers 1996, Tegarden et al., MOOD and QMOOD, as listed by [Radjenović][radj] (formulas not opened) | none | Radjenović: MOOD and QMOOD "were only validated in a few studies"; in one study QMOOD metrics were suitable for fault prediction and MOOD metrics were not [radj] | Partly |
| Encapsulation measures (MHF, AHF, DAM, NOPA, NOAM, WOC) | type, system | Share of hidden methods (MHF) and attributes (AHF); share of private or protected attributes (DAM); number of public attributes (NOPA) and accessor methods (NOAM); share of public methods that are "functional" (WOC). | MOOD and QMOOD names per [Radjenović][radj]; NOPA, NOAM, WOC per [PMD][pmd-metrics] | none | — | Partly |
| QMOOD design metrics (DSC, NOH, ANA, DAM, DCC, CAM, MOA, MFA, NOP, CIS, NOM) | type, system | Design size, hierarchies, ancestors, data access, direct class coupling, cohesion among methods, aggregation, functional abstraction, polymorphic methods, class interface size, number of methods; combined into quality attributes (family 17). | [Bansiya & Davis 2002][qmood02] (abstract); names from [Radjenović][radj] | none | Among QMOOD metrics, "CIS and NOM metrics performed better than others" [radj] | Partly |

**Evidence for the family.** The review of 106 studies found that "The CBO, WMC and RFC were reported to be the best from the CK metrics suite. The coupling metrics were reported to be better than inheritance and cohesion metrics" ([Radjenović et al. 2013][radj]). Size explains much of this: El Emam et al. found no association with fault-proneness for CK and Lorenz–Kidd metrics once class size was controlled ([El Emam et al.][elemam]). Near-identical variants can give opposite significance results on the same data (LCOM3 versus LCOM4, LCC versus TCC in [Briand 1999][briand99]).

## 4. Module and architecture structure

In Rust, `cargo metadata` outputs the crate dependency graph as JSON ([Cargo book][cargo-metadata]) and cargo-modules outputs the module graph and fails with `--acyclic` when it contains a cycle ([cargo-modules][cargo-modules]). Most metrics below can be computed from these graphs, but I found no Rust tool that computes them directly.

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Afferent and efferent coupling (Ca, Ce) | module | Ca: number of other packages that depend on classes in the package. Ce: number of other packages its classes depend on. | Martin 1994 (not opened); definitions from [JDepend][jdepend] | none (derivable from `cargo metadata` or cargo-modules graphs) | — | Partly |
| Instability (I) | module | I = Ce / (Ce + Ca), from 0 (stable) to 1 (unstable). | [JDepend][jdepend]; [Sonargraph][sonargraph] | none | Used by Arcan's Unstable Dependency smell ([Sas et al. 2022][sas22]). In one study the Martin suite outperformed MOOD [radj] | Partly |
| Abstractness (A) and distance from the main sequence (D) | module | A: abstract types / all types in the package. D: distance from the line A + I = 1; JDepend reports it from 0 to 1, Sonargraph as A + I − 1 from −1 to 1. | [JDepend][jdepend]; [Sonargraph][sonargraph] | none | — | Partly |
| Dependency cycles and cyclicity | module, system | Number of cycle groups, number of elements in cycles, size of the biggest cycle group, cyclicity (Sonargraph: summed over cycle groups; formula not given on the page), relative cyclicity, and relative entanglement = 60% × average relative cyclicity of components and top-level elements + 40% × that of packages or namespaces. | [JDepend][jdepend]; [Sonargraph][sonargraph] | cargo-modules `--acyclic` (pass/fail for module cycles) [cargo-modules] | See architectural smells below | Partly |
| Dependencies to remove; Structural Debt Index | module, system | Number of component dependencies to remove to break up all cycles; Sonargraph's cumulative structural debt index of the cycles (formula not given on the page). | [Sonargraph][sonargraph] | none | — | No |
| CCD, ACD, NCCD | system | CCD: sum over components of the number of components each depends on, directly or indirectly. ACD = CCD / number of components. NCCD = CCD divided by the CCD of a balanced binary tree of the same size (above 1 means a deep, vertical structure). | Lakos 1996 (book, not opened); definitions from [Sonargraph][sonargraph] | none | — | No |
| Propagation cost | system | Share of file pairs connected directly or indirectly: the density of the transitive closure ("visibility") of the file dependency matrix. | [MacCormack, Rusnak & Baldwin 2006][maccormack06]; [Sonargraph][sonargraph] | none | Positively correlated with the maintenance-difficulty measures of Mo et al.; its correlations with the measures of how independently developers can make changes "are much lower" ([Mo et al. 2016][mo16]) | No |
| Core size (core–periphery) | system | Size of the largest group of files that depend on each other directly or indirectly, with the other files classified by their position relative to it (description unverified). | [Baldwin, MacCormack & Rusnak 2014][baldwin14] (not opened) | none | — | No |
| Decoupling Level (DL) | system | How well a system can be decoupled into small, independently replaceable modules, computed from the design rule hierarchy of the file dependency graph. | [Mo et al. 2016][mo16] | none | Authors' evaluation on 108 open-source and 21 industrial projects: "the larger the DL, the better the architecture", where better means that bugs and changes are more likely to be localized and developers more likely to make changes independently; 60% of the measured projects had DL between 46% and 75% [mo16] | No |
| Independence Level (IL) | system | Share of files in the last layer of the design rule hierarchy. | Earlier work by the same group, described in [Mo et al. 2016][mo16] | none | Correlated with maintenance measures in the same direction as DL, "but the correlation was much weaker" [mo16] | No |
| Modularity violations | module pair | Discrepancies between how components should change together according to the modular structure and how they actually change together in the version history. | [Wong et al. 2011 (Clio)][wong11] (abstract) | none | In Hadoop and Eclipse JDT, "hundreds of violations identified using Clio were indeed recognized as design problems or refactored by the developers in later versions" (abstract) | No |
| Hotspot patterns (architecture smells from structure and history) | file group | Recurring structures such as Unstable Interface and Implicit Cross-module Dependency, detected from dependencies and co-change history. | [Mo et al. 2015][mo15] (abstract) | none | "the more hotspot patterns a file is involved in, the more error- and change-prone it is" (authors' evaluation, abstract) | No |
| Design rule spaces (DRSpace) | file group | Overlapping file clusters formed by structural or co-change relations and ordered by the design rule hierarchy. | [Xiao, Cai & Kazman 2014][xiao14] (abstract) | none | "error-prone files can be captured by just a few design rule sub-spaces" (three open-source projects, abstract) | No |
| Modularization Quality (MQ) | system | Score of a module partition that rewards dependencies inside modules and penalises dependencies between them; used as the objective of automatic clustering (description unverified). | [Mancoridis et al. 1998][mancoridis98] (abstract does not define MQ; definition not opened) | none | — | No |
| API-based and information-theoretic modularization metrics | system | Metrics for non-object-oriented systems based on module APIs, layering and the similarity of purpose of module services. | [Sarkar, Rama & Kak 2007][sarkar07] (abstract) | none | — | No |
| Component Balance | system | Combines the number of top-level components with how evenly code is distributed over them. | [Bouwers et al. 2011][bouwers11cb] (abstract; formula not opened) | none | "strongly correlated with ratings for analyzability as given by experts" (authors' study, abstract) | No |
| Dependency profiles | system | System-level metric "aimed at quantifying the level of encapsulation and independence within a system", which groups code by its dependencies across components. | [Bouwers, van Deursen & Visser 2011][bouwers11dp] (abstract; categories not opened) | none | Of twelve architecture metrics tested against the ratio of local change in ten systems, "one of the suitable architecture metrics can be considered a valid indicator for the degree of encapsulation" ([Bouwers et al. 2014][bouwers14], abstract) | No |
| Component independence (SIG) | system | Share of code in modules with no incoming dependencies from other components; 4-star limit ≥ 94.5%. | [SIG/TÜV criteria 2026][sig-criteria] | none | See SIG model, family 17 | No |
| Component entanglement (SIG) | system | Based on the number and weight (dependency count) of communication lines between components and on prohibited patterns among them. | [SIG/TÜV criteria 2026][sig-criteria] | none | See SIG model, family 17 | No |
| Module coupling (SIG) | module | Share of code in modules with more than 10, 20 and 50 incoming dependencies; 4-star limits 9.7%, 5.3%, 1.8%. | [SIG/TÜV criteria 2026][sig-criteria] | none | See SIG model, family 17 | Partly |
| Network measures on the dependency graph | module | Network-analysis measures, such as centrality, computed on the dependency graph between binaries. | [Zimmermann & Nagappan 2008][zimmermann08] (abstract) | none | On Windows Server 2003, "the recall for models built from network measures is by 10% points higher than for models built from complexity metrics" (abstract) | Partly |
| Component Rank | module | PageRank of components in the dependency graph, scaled to sum to 100. | [Sonargraph][sonargraph] | none | — | No |
| Relational cohesion; logical and physical cohesion and coupling | module | Internal dependencies divided by the number of top-level elements in a namespace (Larman); counts of dependencies inside versus across namespaces or modules. | [Sonargraph][sonargraph] | none | — | Partly |
| Architecture conformance violations | module, system | Number of dependencies that break declared layer or access rules; Sonargraph also reports violations per 1,000 LOC. | [Sonargraph][sonargraph] | cargo-deny `bans` for crate edges [deny]; Clippy `disallowed-methods` and `disallowed-types` lists [clippy-conf]; cargo-modules `--acyclic` | — (rule violations are defined by the team; no outcome studies found) | Yes |
| Architectural smells: Cyclic Dependency, Hub-Like Dependency, Unstable Dependency, God Component | module | CD: a cycle among components. HL: incoming and outgoing dependencies both above the system median, with abs(in − out) below a quarter of the total. UD: a component depending on more than 30% (Arcan's threshold) of components less stable than itself. GC: a component "considerably larger in size (i.e. lines of code) than other components", with a variable threshold in Arcan. | Arcan ([Arcelli Fontana et al. 2017][arcan17]); definitions from [Sas, Avgeriou & Uyumaz 2022][sas22] | none | Industrial study of 9 C/C++ projects: smells grow over time, and practitioners "recognise that the presence of smells correlates with frequently changed components, increased change propagation, the presence of severe bugs" (interviews) [sas22] | Partly |
| Architectural Technical Debt Index (ATDI) | system | Index built from detected architectural smells, their criticality and their history. | [Roveda et al. 2018][atdi18] (abstract) | none | — | No |

**Evidence for the family.** Most architecture metrics were validated only by the groups that proposed them (DL, hotspot patterns, DRSpace, Component Balance, the SIG measures); for the Sonargraph metrics I found no validation study. The independent evidence I found is Zimmermann & Nagappan's network measures on Windows ([abstract][zimmermann08]) and the qualitative industrial study of architectural smells ([Sas et al. 2022][sas22]). Bouwers et al. note that "over 40 different architecture-level metrics are available to quantify the encapsulation, but empirical validation of these metrics against changes in a system is not available" ([Bouwers et al. 2014][bouwers14], abstract).

## 5. Code smells and anti-patterns

Smell counts are produced by detection rules, usually thresholds on the metrics in families 1 to 4. Many smell names come from Fowler and Beck's catalogue in Refactoring (1999), which I did not open (unverified).

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Code smell count and density | file, system | Number of smell findings, optionally per KLOC. | SonarQube `code_smells`, `new_code_smells` [sonar-metrics] | SonarQube (imports Clippy findings for Rust) [sonar-rust] | In 395 releases of 30 projects, "smelly classes have a higher change- and fault-proneness than smell-free classes" ([Palomba et al. 2018][palomba18], abstract). In a controlled maintenance study, "None of the 12 investigated smells was significantly associated with increased effort after we adjusted for file size and the number of changes" ([Sjøberg et al. 2013][sjoberg13], abstract) | Yes |
| God Class and Data Class (detection strategies) | type | God Class: high WMC, high ATFD and low TCC. Data Class: high NOPA + NOAM, low WOC and low WMC. Other strategies in the same book (Feature Envy, Shotgun Surgery, and others) were not opened. | [Lanza & Marinescu 2006][lanza06]; [Marinescu 2004][marinescu04]; rules as implemented in [PMD][pmd-design] | none | — | Partly |
| Designite design smells | type, module | Imperative, Multifaceted, Unnecessary and Unutilized Abstraction; Deficient and Unexploited Encapsulation; Broken, Cyclic-Dependent, Insufficient and Hub-like Modularization; Broken, Cyclic, Deep, Missing, Multipath, Rebellious and Wide Hierarchy. | [DesigniteJava][designite] | none | — | Partly |
| Designite implementation smells | function | Abstract Function Call From Constructor, Complex Conditional, Complex Method, Empty catch clause, Long Identifier, Long Method, Long Parameter List, Long Statement, Magic Number, Missing default. | [DesigniteJava][designite] | none | — | Yes |
| CodeScene Code Health smells | function, file | Low Cohesion (LCOM4), Brain Class (large module with many functions and at least one Brain Method), Developer Congestion, complex code by former contributors, Lines of Code, Brain Method, DRY violations that change together, Complex Method (CC), Primitive Obsession, Large Method, Nested Complexity, Bumpy Road (several separate chunks of logic in one function), Complex Conditional, and the test smells Large Assertion Blocks and Duplicated Assertion Blocks. | [CodeScene docs][cs-health] | CodeScene (lists Rust as supported) [cs-lang] | See Code Health, family 17 | Partly |
| Qlty structure checks | function, file | Similar code, identical code, many function parameters, complex boolean logic, high file complexity, high function complexity (cognitive), deeply nested control flow, many return statements. | [Qlty docs][qlty-smells] | Qlty [qlty-rust] | — | Yes |
| Exception-handling anti-patterns and exception flow | function | Counts of 17 exception-handling anti-patterns and characteristics of exception flow. | [de Pádua & Shang 2018][depadua18] (abstract) | none | Exception flow characteristics in Java projects "have a significant relationship with post-release defects"; most anti-patterns were not significant (abstract) | Yes |
| Dead code | function, file | Number of unused, unexported items. | [Romano et al. 2020][romano20] (abstract) | rustc `dead_code` lint warnings [rustc-lints]; warnalyzer (unused code across crates, last release 2021) [warnalyzer] | Experiments and interviews suggest "dead code is harmful" in maintenance and evolution (abstract) | Partly |

**Evidence for the family.** The two strongest studies point in different directions: a large mining study links smells to change- and fault-proneness ([Palomba et al. 2018][palomba18]); a controlled experiment with professional developers found no effect on maintenance effort once file size and number of changes were controlled ([Sjøberg et al. 2013][sjoberg13]). Many smell detectors are thresholds on size and complexity metrics, so they share the size confound.

## 6. Duplication

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Duplicated lines density, duplicated blocks, duplicated files | file, system | Duplicated lines / lines × 100; number of duplicated blocks; number of files involved. SIG measures "redundant lines" (4-star limit 5.8%); Sonargraph counts duplicate occurrences excluding the largest one; Lizard reports a duplicate rate. | SonarQube [sonar-metrics]; [SIG criteria][sig-criteria]; [Sonargraph][sonargraph]; [Lizard][lizard-ext] | SonarQube (Rust duplication) [sonar-rust], PMD CPD (Rust since PMD 7.9.0) [pmd-rust], jscpd [jscpd], Qlty, CodeScene, dryer [dryer] | See family summary | Partly (needs the rest of the code base to find the other copy) |
| Clone type (Type-1 to Type-4) | clone pair | Type-1: identical apart from layout and comments. Type-2: identical apart from names or literal values. Type-3: copies with some edited lines. Type-4: same behaviour with different code. | [Roy, Cordy & Koschke 2009][roy09] (not opened); the four types as named by [jscpd][jscpd] | jscpd (Type-2 and Type-3 opt-in), dryer | — | Partly |
| Inconsistent changes to clones | clone group | Number of changes applied to some but not all copies of a clone group. | [Juergens et al. 2009][juergens09] | none | "nearly every second unintentionally inconsistent change to a clone leads to a fault" (commercial and open-source systems) [juergens09] | Partly |
| Co-changing duplicates (DRY violations) | function | Duplicated logic that is changed together in the version history. | [CodeScene][cs-health] | CodeScene | — | Partly |
| Duplicated parameter lists | function | Functions with identical or very similar parameter lists. | Lizard `-Eduplicated_param_list` [lizard-ext] | Lizard | — | Partly |

**Evidence for the family.** The evidence is mixed. Juergens et al. found that inconsistent clone changes often cause faults [juergens09]; Rahman, Bird & Devanbu found "the great majority of bugs are not significantly associated with clones" and that "clones may be less defect prone than non-cloned code" [rahman10]. The title of Kapser & Godfrey's paper argues against treating all cloning as harmful ([Kapser & Godfrey 2008][kapser08], not opened). Duplication measures for AI-generated code are in families 18 and 19.

## 7. Static-analysis findings and technical-debt items

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Warning or issue count and density | file, system | Number of findings from a linter or analyzer, optionally per KLOC. | SonarQube `violations` [sonar-metrics] | Clippy (JSON output), SonarQube (imports Clippy), Qlty | In Apache Java projects, the PMD warning density of bug-inducing changes differed from that of other changes, and "the effect size is negligible in all cases" ([Trautsch et al. 2023][trautsch23], abstract). Three static bug detectors applied to 594 known Java bugs "miss the large majority of the studied bugs" ([Habib & Pradel 2018][habib18], abstract) | Yes (for findings in changed lines) |
| Issues by type and severity | file, system | Counts split by type (bug, vulnerability, code smell; or reliability, security, maintainability) and by severity (blocker to info). | SonarQube [sonar-metrics] | SonarQube | "violations considered as 'bugs' by SonarQube were generally not fault-prone and, consequently, the fault-prediction power of the model proposed by SonarQube is extremely low" (21 Java projects, [Lenarduzzi et al. 2020][lenarduzzi20], abstract) | Yes |
| Issues on new code | change | Issues first raised on new code, i.e. code changed since a configurable baseline. | SonarQube `new_violations` [sonar-metrics] | SonarQube | See agent pull requests, family 19 | Yes |
| Technical debt (remediation effort) and debt ratio | file, system | Sum of per-rule remediation estimates in minutes (`sqale_index`); ratio = debt / (cost to develop one line × lines of code). | SonarQube [sonar-metrics]; SQALE ([Letouzey 2012][sqale12]) | SonarQube, Qlty | In 33 Apache projects, "Clean classes (classes not affected by TD items) are less change-prone than dirty ones, but the difference between the groups is small"; "As for fault-proneness, there is no difference between clean and dirty classes" ([Lenarduzzi et al. 2019][lenarduzzi19]) | Yes |
| Relative warning density | file, change | Warnings per line of a file relative to the project's warning density at the same point in time. | [Trautsch, Herbold & Grabowski 2023][trautsch23] (abstract) | none | As above: negligible effect size | Partly |
| Effective false-positive rate | analyzer | Share of reports on which "a user chooses not to take action to resolve the report"; Tricorder keeps this rate below 10% for analyzers shown in code review. | [Sadowski et al. 2015 (Tricorder)][tricorder]; [Sadowski et al. 2018][sadowski18] | none (a deployment measure) | — | Yes |
| Fix rate of findings | analyzer | Share of reported findings that developers fix. | [Distefano et al. 2019][infer] | none | At Facebook the same analysis had a fix rate of over 70% when reported on the diff at review time; in an earlier batch deployment that presented bug lists, the fix rate was "near zero" [infer] | Yes |
| Suppression count | file, change | Number of lint suppressions (for example `#[allow(...)]`), with or without a stated reason. | Clippy `allow_attributes`, `allow_attributes_without_reason` (restriction) [clippy-lints] | Clippy | No outcome study found. In a practitioner report, a coding agent allowed to raise thresholds "frequently decided to increase the cyclomatic complexity threshold" ([Böckeler][boeckeler]) | Yes |
| Rule-level fault-proneness | rule | For each rule, the association between its violations and later fault-inducing commits. | [Lenarduzzi et al. 2020][lenarduzzi20] | none | "Among the 202 rules defined for Java by SonarQube, only 25 can be considered to have relatively low fault-proneness" (abstract) | No |

**Evidence for the family.** Warning counts relate weakly or not at all to defects ([Trautsch et al. 2023][trautsch23]; [Lenarduzzi et al. 2019][lenarduzzi19]), and analyzers miss most known bugs ([Habib & Pradel 2018][habib18]). Deployment studies show that whether developers act on findings depends on delivery: findings shown on the diff during review were fixed far more often than batch reports ([Distefano et al. 2019][infer]), and Google keeps only analyzers with a low effective false-positive rate ([Sadowski et al. 2018][sadowski18]).

## 8. Security measures

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| SAST finding counts | file, system | Number of security findings from a static application security testing tool, by severity or CWE. | Tool documentation | CodeQL (Rust GA since 2025-10-14) [codeql-rust]; Semgrep (Rust GA) [semgrep-langs] | Six Rust SAST tools on 320 real vulnerabilities: average false-positive rate 80.3%, and every tool's false-negative rate above 90% ([Zhang et al. 2026][zhang-sast]) | Yes |
| CWE weakness counts (ASCQM, ISO/IEC 5055) | system | Counts of occurrences of selected CWE weaknesses for four characteristics: reliability, security, performance efficiency and maintainability. | [OMG ASCQM 1.1, 2022][omg-ascqm] | none | The specification itself states: "The Automated Source Code Quality Measures are correlated measures rather than absolute measures" [omg-ascqm] | Yes |
| Security hotspots reviewed | system | Share of security hotspots marked as reviewed; rated A (≥ 80%) to E (< 30%). The documentation states that "Security Hotspots are being phased out". | SonarQube [sonar-metrics] | SonarQube | — | Yes (new-code variant) |
| Vulnerability prediction metrics | file | Complexity, code churn and developer-activity metrics used to predict vulnerable files. | [Shin et al. 2011][shin11] (abstract) | none | Firefox and the RHEL kernel: "24 of the 28 metrics collected are discriminative of vulnerabilities"; models found over 80% of known vulnerable files with less than 25% false positives (abstract) | Partly |
| Attack surface metric | system | Weighted count of entry and exit points, channels and untrusted data items, weighted by their damage potential and attacker effort. | [Manadhata & Wing 2011][manadhata11] (abstract; weighting not opened) | none | Validated in three exploratory studies and used at SAP (abstract) | No |

SonarQube's security rating is in family 17, dependency vulnerabilities in family 15, unsafe Rust in family 16 and security smells in agent pull requests in family 19.

**Evidence for the family.** The security metrics with outcome evidence are the vulnerability-prediction models of [Shin et al. 2011][shin11]. Tool-finding counts depend on tool recall, which is low for Rust SAST tools ([Zhang et al. 2026][zhang-sast]).

## 9. Readability, understandability and naming

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Buse–Weimer readability | function, snippet | Logistic model over local features such as line length, identifiers per line, indentation, keywords, comments, periods, parentheses and blank lines, trained on ratings of 100 snippets by 120 annotators. | [Buse & Weimer 2010][buse10] | none | Predicts readability judgments "80% effective"; "correlates strongly with three measures of software quality: code changes, automated defect reports, and defect log messages" [buse10] | Yes |
| Posnett–Hindle–Devanbu readability | function, snippet | Sparse model of the Buse–Weimer ratings using size, Halstead volume and token entropy. | [Posnett, Hindle & Devanbu 2011][posnett11] (abstract; coefficients not opened) | none | "a much sparser, yet statistically significant, model of the mean readability scores produced in Buse's studies" (abstract) | Yes |
| Dorn readability | function, snippet | Logistic regression over structural, visual, alignment and natural-language features of code; seven features in the final model. Trained on 360 snippets in Java, Python and C++ with CUDA, rated by more than 5,000 participants. | Dorn (not opened), as described by [Sergeyuk et al. 2024][sergeyuk24] | none | Spearman 0.72 with human judgments and 5% higher F-measure than a retrained Buse–Weimer model [sergeyuk24] | Yes |
| Scalabrino readability | function, snippet | Classifier combining the structural and visual features of earlier models with textual features of identifiers and comments, 104 features in total. | [Scalabrino et al. 2018][scalabrino18] (abstract); feature count per [Sergeyuk et al.][sergeyuk24] | none | Higher accuracy than earlier models on more than 600 snippets rated by more than 5,000 people (abstract). In CoReEval it "aligns slightly better with human scores (Pearson = 0.31, Spearman = 0.27)" than LLMs for Java [coreeval] | Yes |
| Mi deep-learning readability | function, snippet | Neural classifier over visual, semantic and structural representations of code. | [Mi et al. 2022][mi22]; described by [Sergeyuk et al.][sergeyuk24] | none | 3.5% to 13.8% improvement over earlier models, as reported by [Sergeyuk et al.][sergeyuk24] | Yes |
| LLM-judged readability | function, snippet | Readability rating produced by a large language model. | [CoReEval][coreeval] | any LLM | "LLMs show moderate alignment with human judgments in Java (Pearson = 0.25, Spearman = 0.25), indicating some consistency in relative scoring, though far from strong agreement"; correlations drop for Python and CUDA [coreeval]. For AI-generated Java code, readability models and 390 developers showed "a limited correlation" [sergeyuk24] | Yes |
| Understandability metric sets | function, snippet | 121 code, documentation and developer metrics (including readability and complexity metrics) tested against measured understanding. | [Scalabrino et al. 2019][scalabrino19] | — | "none of the 121 experimented metrics is able to capture code understandability" [scalabrino19]; a re-analysis found "a small but significant correlation" for combined features ([Trockman et al. 2018][trockman18], abstract) | Yes |
| Identifier form (single letters, abbreviations, full words) | identifier | Share of identifiers that are full words, abbreviations or single letters; minimum identifier length. | [Lawrie et al. 2006][lawrie06] (abstract) | Clippy `min_ident_chars` and `many_single_char_names` (thresholds: `min-ident-chars-threshold`, default 1; `single-char-binding-names-threshold`, default 4) [clippy-conf] | Over 100 programmers: "full word identifiers lead to the best comprehension; however, in many cases, there is no statistical difference between full words and abbreviations" (abstract) | Yes |
| Identifier naming flaws | identifier, function | Count of identifiers with naming flaws, judged against naming conventions. | [Butler et al. 2010][butler10] (abstract) | none | "flawed identifiers in Java classes were associated with source code found to be of low quality by static analysis" (abstract) | Yes |
| Linguistic antipatterns | function, attribute | Inconsistencies between method signatures, documentation and behaviour, or between attribute names, types and comments. | [Arnaoudova et al. 2013][arnaoudova13] (abstract) | none | — | Yes |

**Evidence for the family.** Readability models predict human ratings of short snippets; Buse & Weimer's model also correlated with change and defect data [buse10]. Understandability, measured by how well developers answer questions about code, is not captured by any single metric ([Scalabrino et al. 2019][scalabrino19]). LLM ratings agree weakly with humans ([CoReEval][coreeval]). Buse & Weimer's model was trained on 100 snippets.

## 10. Naturalness

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Cross-entropy (naturalness) under a code language model | line, file | Average negative log-probability of the code's tokens under an n-gram model trained on the project or corpus. | [Hindle et al. 2012][hindle12] | none | Code is "repetitive, and in fact even more so than natural languages" [hindle12] | Yes (model trained on the rest of the code) |
| Line entropy ranking | line, file | Lines or files ordered by their entropy under a statistical language model. | [Ray et al. 2016][ray16] (abstract) | none | In about 7,139 bug-fix commits from 10 Java projects, "code with bugs tends to be more entropic"; ordering by entropy gave cost-effectiveness "comparable to popular defect prediction methods" and, at line level, similar to PMD and FindBugs (abstract) | Partly |

**Evidence for the family.** One line of work by overlapping authors supports entropy as a defect predictor at file and line level ([Ray et al. 2016][ray16]). I found no replication, and no study of language-model entropy as a quality measure for Rust.

## 11. Comments and documentation

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Comment density | file, system | SonarQube: comment_lines / (lines + comment_lines) × 100, where comment lines include commented-out code. RCA uses the comment share inside the SEI Maintainability Index. | SonarQube `comment_lines_density` [sonar-metrics]; RCA [rca-src] | RCA, tokei, SonarQube | Buse & Weimer: "comments, in of themselves, are less important than simple blank lines to local judgments of readability" [buse10] | Yes |
| Documented items (documentation coverage) | crate, file | Share of items with documentation, and share with code examples; JSON output available. | rustdoc `--show-coverage` (unstable, `-Z unstable-options`) [rustdoc-cov]; rustc `missing_docs` lint (allow-by-default) [rustc-allowed]; CK "Has Javadoc" [ck] | rustdoc, rustc `missing_docs` | — | Yes |
| Missing sections in API docs | function | Public functions without an `# Errors`, `# Panics` or `# Safety` section where they return errors, can panic or are `unsafe`; private items without docs. | Clippy `missing_errors_doc`, `missing_panics_doc` (pedantic), `missing_safety_doc` (style), `missing_docs_in_private_items` (restriction) [clippy-lints] | Clippy | — | Yes |
| Comment quality model | comment | Comments classified by machine learning into categories, with category-specific quality metrics. | [Steidl, Hummel & Juergens 2013][steidl13] (abstract) | none | Validated by a survey of 16 experts (abstract) | Yes |
| Self-admitted technical debt (SATD) | file, comment | Number of source-code comments in which developers admit technical debt: code that is incomplete, needs rework, produces errors or is a temporary workaround. | [Potdar & Shihab 2014][potdar14] (abstract) | Clippy `todo` counts `todo!()` macros (restriction) [clippy-lints]; no comment-based SATD tool found for Rust | SATD exists in "2.4%-31% of the files" of four projects [potdar14]. In five projects, "there is no clear trend when it comes to defects and self-admitted technical debt", SATD changes "induce less future defects", but "self-admitted technical debt changes are more difficult to perform" ([Wehaibi et al. 2016][wehaibi16], abstract) | Yes |
| Spelling errors in doc comments | comment | Number of misspelt words in documentation comments. | cargo-spellcheck [spellcheck] | cargo-spellcheck | — | Yes |

**Evidence for the family.** I found outcome evidence only for SATD, and it does not show a link to defects ([Wehaibi et al. 2016][wehaibi16]). Documentation coverage and comment density are widely computed, but I found no study relating them to defects or maintenance effort.

## 12. Test quality

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Line (statement) coverage | file, test suite | Executed executable lines / executable lines. | SonarQube `line_coverage` [sonar-metrics] | cargo-llvm-cov [llvm-cov], cargo-tarpaulin [tarpaulin], grcov [grcov] | "there is a low to moderate correlation between coverage and effectiveness when the number of test cases in the suite is controlled for" (mutation-based effectiveness, [Inozemtseva & Holmes 2014][inozemtseva14]). Across 100 Java projects, "coverage has an insignificant correlation with the number of bugs that are found after the release of the software at the project level, and no such correlation at the file level" ([Kochhar et al. 2017][kochhar17], abstract). Across hundreds of open-source Java projects, "statement (not block, branch, or path) coverage predicts mutation kills best" ([Gopinath et al. 2014][gopinath14]) | Partly (needs a test run) |
| Branch and condition coverage | file, test suite | SonarQube condition coverage = (conditions evaluated true + conditions evaluated false) / (2 × conditions); combined coverage = (true conditions + covered lines) / (conditions + executable lines). | SonarQube `branch_coverage`, `coverage` [sonar-metrics] | cargo-llvm-cov `--branch` (unstable, nightly); tarpaulin's branch option is "NOT IMPLEMENTED" [tarpaulin] | "stronger forms of coverage do not provide greater insight into the effectiveness of the suite" [inozemtseva14] | Partly |
| Region and function coverage | file, test suite | Share of LLVM source regions, or of functions, executed by tests. | cargo-llvm-cov (`--fail-under-regions`, `--fail-under-functions`) [llvm-cov] | cargo-llvm-cov | — | Partly |
| MC/DC coverage | function | Share of conditions shown to independently affect their decision's outcome. | cargo-llvm-cov `--mcdc` (unstable) [llvm-cov] | cargo-llvm-cov (nightly) | — | Partly |
| Patch (diff, new-code) coverage | change | Coverage of the lines added or changed by a change. | SonarQube `new_coverage` [sonar-metrics]; changelist coverage at Google ([Ivanković et al. 2019][ivankovic19]) | SonarQube with LCOV or Cobertura from cargo-llvm-cov [sonar-rust] | In 7,816 builds of 47 projects, patch coverage did not correlate with overall coverage (Kendall tau −0.01); in a 1-million-line project, a 100-line coverage change moves overall coverage by "one hundredth of one percentage point" ([Hilton et al. 2018][hilton18]) | Yes (needs a test run) |
| Mutation score | function, test suite | Killed mutants as a percentage of non-equivalent mutants. cargo-mutants reports caught, missed, timeout and unviable mutants. | Definition as stated by [Zhang & Mesbah 2015][zhangmesbah15]; [cargo-mutants][mutants] | cargo-mutants, mutator [mutator] | "a statistically significant correlation between mutant detection and real fault detection, independently of code coverage" ([Just et al. 2014][just14]); correlations "are weak when controlling for test suite size" ([Papadakis et al. 2018][papadakis18]); for test suites generated by LLMs, "the usefulness of coverage and mutation is highly context-dependent" ([Zhao et al. 2026][zhao26]) | Partly |
| Diff-scoped mutation testing | change | Mutation testing restricted to changed lines, with suppression of unproductive mutants. | [Petrović et al. 2021 (Google)][petrovic21]; cargo-mutants `--in-diff` [mutants-diff] | cargo-mutants `--in-diff` | At Google, "developers at Google initially classified 85% of reported mutants as unproductive"; suppression heuristics "improved the ratio of productive mutants from 15% to 89%" [petrovic21]. The cargo-mutants documentation warns that edits in one region can leave code in another region less well tested, so `--in-diff` is "not a substitute for a full test run" [mutants-diff] | Yes |
| Pseudo-tested methods | function | Methods covered by tests where no test fails when the whole method body is removed (extreme mutation). | [Niedermayr, Juergens & Wagner 2016][niedermayr16] | none named for Rust; cargo-mutants generates body-replacement mutants that can serve this purpose (my inference, not documented as this metric) | Coverage "is only a valid effectiveness indicator for unit tests" [niedermayr16]; a replication found pseudo-tested methods "exist in all our subjects" ([Vera-Pérez et al. 2018][verape18]) | Partly |
| Checked coverage | test suite | Share of statements in the dynamic slice of covered statements that influence an oracle (an assertion). | [Schuler & Zeller 2013][schuler13] (abstract) | none | "a sure indicator for oracle quality and even more sensitive than mutation testing" (seven projects, abstract) | Partly |
| Assertion count and assertion coverage | test suite | Number of assertions; assertion coverage, the share of statements executed via the dynamic backward slice of the assertions (the authors' name for checked coverage). | [Zhang & Mesbah 2015][zhangmesbah15] | none | "assertion coverage is strongly correlated with effectiveness"; the number of assertions "directly influences the relationship between test suite size and effectiveness" (effectiveness measured by mutants) [zhangmesbah15] | Yes |
| Assertion density in production code | file | Number of assertions relative to code size in a file. | [Kudrjavets, Nagappan & Ball 2006][kudrjavets06] (abstract) | none (could count `assert!` and `debug_assert!`; no tool found) | Two Microsoft components: "with an increase in the assertion density in a file there is a statistically significant decrease in fault density" (abstract) | Yes |
| Test smells | test | Counts of 19 test smells: Assertion Roulette, Conditional Test Logic, Constructor Initialization, Default Test, Duplicate Assert, Eager Test, Empty Test, Exception Handling, General Fixture, Ignored Test, Lazy Test, Magic Number Test, Mystery Guest, Redundant Print, Redundant Assertion, Resource Optimism, Sensitive Equality, Sleepy Test, Unknown Test. CodeScene adds Large and Duplicated Assertion Blocks. | [tsDetect catalogue][tsdetect]; [CodeScene][cs-health] | CodeScene (applies test rules to tests embedded in Rust files) [cs-lang] | "tests with smells are more change- and defect-prone" and "production code is more defect-prone when tested by smelly tests" (221 releases of ten systems, [Spadini et al. 2018][spadini18], abstract) | Yes |
| Flaky test rate | test, test suite | Share of tests, or of runs, that both pass and fail on the same code. | [Google Testing Blog 2016][google-flaky] | cargo-nextest retries: a test that fails and then passes on retry is reported as flaky; "By default, flaky tests are treated as ultimately successful" [nextest] | Google: "about 1.5% of all test runs reporting a 'flaky' result"; "Almost 16% of our tests have some level of flakiness" [google-flaky] | Partly |
| Test counts, failures, skips, duration | test suite | Number of tests, errors, failures, skipped tests, execution time, success density. | SonarQube [sonar-metrics] | cargo test, cargo-nextest (JUnit output) | — | Partly |
| Test gaps | change | Changed methods that no test executed. | [Eder et al. 2013][eder13] (abstract) | none (derivable from coverage plus the diff) | Industrial case study over 14 months: the approach produced "meaningful data" (abstract) | Yes |
| Test code quality model | test suite | Ratings of test completeness, effectiveness and maintainability built from test-code metrics in the style of the SIG model. | [Athanasiou et al. 2014][athanasiou14] (abstract) | none | 18 systems: "significant positive correlation between test code quality and two out of the three issue handling metrics (throughput and productivity)" (abstract) | No |
| Test set diameter | test suite | Diversity of a test set as the normalized compression distance of the multiset of test inputs (or traces). | [Feldt et al. 2016][feldt16] (abstract) | none | — | No |

**Evidence for the family.** Mutation score has the most direct evidence of a link to real-fault detection ([Just et al. 2014][just14]), though suite size weakens it ([Papadakis et al. 2018][papadakis18]) and results differ for test suites written by LLMs ([Zhao et al. 2026][zhao26]). Coverage has a low to moderate correlation with effectiveness once suite size is controlled, and an insignificant correlation or none with post-release bugs in Kochhar et al.'s 100 projects. Most effectiveness studies measure effectiveness with mutants, which makes coverage and mutation evidence partly circular. Test metrics for agent pull requests are in family 19.

## 13. Process and history metrics

These metrics are mined from version control, issue trackers and review systems. They describe files or modules over a time window. For a change, they can be read for the files the change touches ("Partly" below), but they say nothing about the new code itself.

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Number of changes (revisions, change frequency) | file, module | Number of commits or modification requests that touched the file in a window. | [Graves et al. 2000][graves00]; [Sonargraph][sonargraph] | language-independent git tools; CodeScene [cs-hotspots]; debtmap (optional git history) [debtmap] | Radjenović: "++" [radj]. "the number of times code has been changed is a better indication of how many faults it will contain than is its length" (one large telecom system, [Graves et al. 2000][graves00]) | Partly |
| Code churn (absolute) | file, module | Lines added, changed and deleted in a window; Sonargraph reports lines added or removed over the last 30 days, 1, 2 and 5 years. | [Sonargraph][sonargraph]; Munson & Elbaum, as listed by [Radjenović][radj] | git-based tools; debtmap | Radjenović: "++" [radj]. On Windows Server 2003, "absolute measures of code churn are poor predictors of defect density" ([Nagappan & Ball 2005][nagappan05]) | Partly |
| Relative code churn (M1–M8) | module | M1 churned LOC / total LOC; M2 deleted LOC / total LOC; M3 files churned / file count; M4 churn count / files churned; M5 weeks of churn / file count; M6 lines worked on / weeks of churn; M7 churned LOC / deleted LOC; M8 lines worked on / churn count. | [Nagappan & Ball 2005][nagappan05] | none | "our set of relative measures of code churn is highly predictive of defect density"; discriminated fault-prone binaries "with an accuracy of 89.0 percent" [nagappan05] | Partly |
| Code age and weighted age | file, module | Time since the file was created or last changed; Graves's weighted time-damp model sums all past changes with more weight on large and recent ones. | [Graves et al. 2000][graves00] | git-based tools | Radjenović: "++" [radj] | Partly |
| Change-set size | file | Number of modules changed together with the module. | Graves et al., as listed by [Radjenović][radj] | git-based tools | Radjenović: "++" [radj] | Partly |
| Code delta | file, module | Difference in a metric value between two versions. | Munson & Elbaum, as listed by [Radjenović][radj] | none | Radjenović: "+"; "Code churn metrics were found to be more appropriate than delta metrics" [radj] | Partly |
| Number of past faults (bug-fix commits) | file, module | Number of faults fixed in the file in earlier releases. | Graves et al., as listed by [Radjenović][radj] | git-based tools; debtmap ("bug fix rate") | Radjenović: "+"; "there seems to be a weak connection" [radj] | Partly |
| Number of developers | file, module | Number of distinct authors in a window (variants: new developers, cumulative developers). | Weyuker et al., as described by [Radjenović][radj]; [Sonargraph][sonargraph] | git-based tools; debtmap ("author count") | Radjenović: "+"; the developer metric "showed only moderate correlation with faults" and seemed to depend on the environment [radj]. Graves et al. found "no evidence that a large number of developers working on a module caused it to be more faulty" [graves00] | Partly |
| Entropy of changes (history complexity) | system, file | Shannon entropy of how the changes in a period are spread over files; Hassan's history complexity metrics accumulate it per file. | [Hassan 2009][hassan09] | none | In six open-source projects, "our change complexity metrics are better predictors of fault potential in comparison to other well-known historical predictors of faults, i.e., prior modifications and prior faults" [hassan09] | Partly |
| Moser change metrics | file | Per-file counts over a release, such as revisions, refactorings, bug fixes, authors, lines added and deleted, churn, change-set size and age (list unverified). | [Moser, Pedrycz & Succi 2008][moser08] (abstract; full text not opened) | git-based tools | On Eclipse, "process metrics are more efficient defect predictors than code metrics" (abstract) | Partly |
| Logical (change) coupling | file pair, module | How often two artifacts change together in the history (co-change support and confidence). | [Gall, Hajek & Jazayeri 1998][gall98] (abstract); [Zimmermann et al. 2005][zimmermann05] (not opened); [D'Ambros et al. 2009][dambros09] (abstract) | CodeScene; git-based tools | In one large telecom system, connectivity "as measured by the typical number of other modules changed together with the module" did not appear important for fault prediction ([Graves et al. 2000][graves00]). D'Ambros et al. tested the link to defects in three systems; their abstract does not state the result | Partly |
| Hotspots | file | Files with high change frequency and low Code Health, raised further when they change together with many modules or are touched by many developers or teams. | [CodeScene docs][cs-hotspots] | CodeScene | In 39 proprietary codebases, code with low Code Health had 15 times more defects than code with high Code Health (vendor study; see Code Health in family 17) | Partly |
| Code ownership (Bird et al.) | module | Minor: contributors with less than 5% of the commits to a component. Major: contributors with at least 5%. Total: all contributors. Ownership: the top contributor's share. | [Bird et al. 2011][bird11] | git-based tools | Windows Vista and 7: "the number of low-expertise developers, and the proportion of ownership for the top owner have a relationship with both pre-release faults and post-release failures" [bird11]. On four Microsoft products, "The results confirm the original findings" ([Greiler et al. 2015][greiler15]). Not replicated at one company: "we found no strong correlation between minor contributors and bug numbers" ([Koana et al. 2024][koana24], abstract) | Partly |
| Organizational metrics | module | NOE engineers who touched the binary; NOEE engineers who left; EF edit frequency; DMO depth of master ownership; PO share of the organisation contributing; OCO organisational code ownership; OOW overall organisation ownership; OIF number of organisations contributing more than 10% of edits. | [Nagappan, Murphy & Basili 2008][nagappan08] | none | Windows Vista: average precision 0.87 over 50 random splits for predicting failure-prone binaries [nagappan08] | Partly |
| Socio-technical congruence | system, team | Match between the coordination that technical dependencies require and the coordination developers actually do. | [Cataldo, Herbsleb & Carley 2008][cataldo08] (abstract) | none | When coordination matched coordination needs, "the resolution time of modification requests was significantly reduced" (abstract) | No |
| Truck factor | system | "the minimal number of developers that have to be hit by a truck (or quit) before a project is incapacitated". | [Avelino et al. 2016][avelino16] (abstract) | none | 65% of 133 popular GitHub projects have a truck factor of at most 2; developers gave "a positive or partially positive answer regarding our estimated truck factors" in 53% of answers (abstract) | No |
| Knowledge awareness and team stability (SIG) | component | Knowledge awareness: how evenly ownership of a component is spread over developers, with recent contributions weighted more than older ones. Team stability: whether those owners keep contributing over time. | [SIG 2026 model changes][sig-2026] | none | — | No |
| Code review coverage and participation | module | Coverage: "the proportion of changes that have been code reviewed". Participation: "the degree of reviewer involvement in the code review process". | [McIntosh et al. 2014][mcintosh14] (abstract) | none (review-system data) | Qt, VTK and ITK: "Low code review coverage and participation are estimated to produce components with up to two and five additional post-release defects respectively" (abstract) | Partly |

**Evidence for the family.** This family has the strongest defect-prediction evidence. Radjenović et al. found that "the best process metrics are code churn, the number of changes, the age of a module and the change set size" [radj]. Rahman & Devanbu: "code metrics, despite widespread use in the defect prediction literature, are generally less useful than process metrics for prediction" ([2013][rahman13]). Majumder et al., on 700 GitHub projects: "process metrics are better predictors for defects than product metrics (best process/product-based learners respectively achieve recalls of 98%/44% and AUCs of 95%/54%, median values)" ([2022][majumder22]). The predictions attach to files with a history; new files and single changes have little history.

## 14. Change-level (just-in-time) metrics

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Kamei change metrics | change | Diffusion: NS (subsystems touched), ND (directories), NF (files), Entropy (Shannon entropy of how the modified code is spread over the files). Size: LA (lines added), LD (lines deleted), LT (lines in touched files before the change). Purpose: FIX (change fixes a defect). History: NDEV (developers who changed the touched files), AGE (average time since the last change of those files), NUC (number of unique last changes to those files). Experience: EXP, REXP (recency-weighted), SEXP (in the touched subsystems). | [Kamei et al. 2013][kamei13] | none (git-based scripts) | 6 open-source and 5 commercial projects: 68% accuracy and 64% recall; "using only 20 percent of the effort it would take to inspect all changes, we can identify 35 percent of all defect-inducing changes". In open-source projects NF, relative churn (LA/LT, LT/NF) and FIX were "the most important, risk-increasing factors" and AGE decreased risk [kamei13] | Yes (history and experience features need repository history) |
| Mockus–Weiss change measures | change | Size (lines added, deleted and unmodified), diffusion (files, modules and subsystems touched), developer experience, and change type (fault fix or new code). | [Mockus & Weiss 2000][mockus00] (abstract) | none | On 5ESS switch software, "change diffusion and developer experience are essential to predicting failures" (abstract) | Yes |
| Lines added only (LApredict) | change | Logistic regression on the number of added lines. | [Zeng et al. 2021][zeng21] | none | Deep models (CC2Vec, DeepJIT) did not consistently outperform traditional JIT models; this one-feature model "can outperform CC2Vec and all other existing approaches for most cases" (310,370 changes from 6 projects) [zeng21] | Yes |
| Token-based and line-level JIT (JITLine) | change, line | Commit-level defect prediction that also ranks the lines of a commit by risk (model details not opened). | [Pornprasit & Tantithamthavorn 2021][jitline21] (abstract) | none | On 37,524 commits, "at least 26%-38% more accurate (F-measure)" than CC2Vec and DeepJIT, and line-level predictions "133%-150% more accurate (Top-10 Accuracy)" than an NLP baseline (abstract) | Yes |
| Review properties of a change | change | Properties of the change's code review (for example participation), used as a feature family in JIT models. | [McIntosh & Kamei 2018][mcintosh18] | none | JIT models "drop considerably one year after being trained"; the "Size family of code change properties is a consistent contributor of large importance"; the Review family was overvalued in OpenStack in most periods [mcintosh18] | Partly |
| Diff risk score (DRS) | change | Model-predicted probability that a diff causes a severe production incident (SEV). | [Abreu et al. 2024 (Meta)][meta-drs] (abstract) | none | Meta's baseline logistic regression "captures 18.7%, 27.9%, and 84.6% of SEVs while respectively gating the top 5% (weekend), 10% (yellow), and 50% (red) of risky diffs"; a BERT model captured fewer [meta-drs] | Yes |
| DRS-OSS | change | Open-source diff risk scorer using commit messages, diffs and change metrics with a fine-tuned Llama 3.1 8B classifier. | [Sayedsalehi, Rigby & Mockus 2025][drs-oss] (abstract) | none | ROC-AUC 0.895 on ApacheJIT (authors' evaluation, abstract) | Yes |

**Evidence for the family.** JIT models predict defect-inducing changes moderately well, and size features are the most stable predictors ([McIntosh & Kamei 2018][mcintosh18]). A survey of 67 JIT studies found that "the predictive performance correlates with change defect ratio" ([Zhao, Damevski & Chen 2023][zhao23], abstract). Labels come from SZZ, which marks a change as defect-inducing only after a later fix ([Śliwerski et al. 2005][sliwerski05]), so labels arrive late and contain errors. Experience features describe the human author and lose their meaning when an agent writes the change (my inference).

## 15. Dependencies and supply chain

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Dependency count (direct and transitive) | crate, system | Number of direct and transitive dependencies in the resolved graph. | [`cargo metadata`][cargo-metadata] | cargo metadata | — | Yes, as a delta |
| Duplicate and banned crates | system | Number of crates present in several versions, and of explicitly banned crates. | cargo-deny `bans` [deny] | cargo-deny | — | Yes, as a delta |
| Vulnerable, unmaintained and yanked dependencies | system | Number of dependencies matching security advisories, marked unmaintained, or yanked from the registry. | cargo-deny `advisories` [deny]; cargo-audit [audit] | cargo-deny, cargo-audit | Systems with outdated dependencies were "four times as likely to have security issues as opposed to systems that are up-to-date" ([Cox et al. 2015][cox15], abstract) | Yes, as a delta |
| License and source violations | system | Dependencies with disallowed licenses or from disallowed sources. | cargo-deny `licenses`, `sources` [deny] | cargo-deny | — | Yes, as a delta |
| Dependency freshness and libyear | system | Freshness: a system-level measure of how up to date the dependencies are, rated against an industry benchmark (formula not opened). libyear: total time between the release of each used version and the newest release. | [Cox et al. 2015][cox15] (abstract); [libyear][libyear] | cargo-libyear [libyear-crate]; cargo-outdated lists outdated dependencies [outdated] | As above (Cox et al.) | Yes, as a delta |
| Technical lag | system | How far a deployed set of components is from the ideal (for example latest) versions, in time or versions, for direct and transitive dependencies. | [Zerouali et al. 2019][zerouali19] (abstract); [Gonzalez-Barahona et al. 2017][gonzalez17] | cargo-outdated, cargo-libyear | — | Yes, as a delta |
| Unused and misplaced dependencies | crate | Declared dependencies that the code does not use, or that sit in the wrong section (dev/build). | cargo-udeps (needs nightly) [udeps]; cargo-machete ("fast (yet imprecise)") [machete]; cargo-shear (also misplaced dependencies) [shear] | cargo-udeps, cargo-machete, cargo-shear | In Maven Central, "75.1% of the analyzed dependency relationships are bloated" ([Soto-Valero et al. 2021][sotovalero21], abstract) | Yes |
| Unused feature flags | crate | Enabled Cargo features that are not needed. | cargo-unused-features [unused-features] | cargo-unused-features | — | Yes |
| Dependency audit coverage | system | Dependencies without a recorded human audit or review. | cargo-vet [vet]; cargo-crev [crev] | cargo-vet, cargo-crev | — | Yes, as a delta |
| OpenSSF Scorecard checks | repository | 0–10 scores for Binary-Artifacts, Branch-Protection, CI-Tests, CII-Best-Practices, Code-Review, Contributors, Dangerous-Workflow, Dependency-Update-Tool, Fuzzing, License, Maintained, Packaging, Pinned-Dependencies, SAST, SBOM, Security-Policy, Signed-Releases, Token-Permissions, Vulnerabilities and Webhooks, plus an aggregate. | [Scorecard checks][scorecard] | Scorecard (language-independent; repository level) | npm and PyPI: Maintained, Code Review, Branch Protection and Security Policy were the most important practices, but models predicting vulnerability counts had "low R^2 (ranging from 9% to 12%)" ([Zahan et al. 2022][zahan23], abstract) | No |

Unsafe code in dependencies is in family 16; hallucinated packages in AI-generated code are in family 18.

**Evidence for the family.** Outdated dependencies relate to security issues in one industry benchmark ([Cox et al. 2015][cox15]), and Scorecard practice scores explain little of the variance in reported vulnerabilities ([Zahan et al.][zahan23]). The other measures are policy checks whose relation to outcomes I found no study of.

## 16. Rust-specific measures

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Unsafe usage counts | crate, function | Numbers of `unsafe` functions, expressions, `impl`s, traits and methods, each split into used and unused code, plus whether the crate forbids `unsafe`. | cargo-geiger report types [geiger-serde]; [cargo-geiger][geiger] | cargo-geiger (also for all dependencies) | "vulnerable code has statistically significantly higher ratios of unsafe functions and unsafe blocks" than the rest of the same packages, yet "95% of the affected functions are safe functions" ([Zheng et al. 2023][zheng23]). "All memory-safety bugs of Rust except compiler bugs require unsafe code" ([Xu et al. 2021][xu21]). "all memory-safety bugs involve unsafe code", while "all blocking bugs we studied are in safe code" ([Qin et al. 2020][qin20]) | Yes |
| Share of crates using `unsafe` (ecosystem baseline) | ecosystem | Share of crates that contain the `unsafe` keyword or call crates that do. | [Evans et al. 2020][evans20]; [Rust Foundation 2024][rustfdn24]; [Astrauskas et al. 2020][astrauskas20] | cargo-geiger | Under 30% of crates use `unsafe` directly, but more than half cannot be fully checked statically because of `unsafe` in dependencies [evans20]. May 2024: 19.11% of about 127,000 crates use `unsafe`; 34.35% call into a crate that does [rustfdn24] | No |
| Undocumented `unsafe` blocks and blocks with several unsafe operations | function | `unsafe` blocks without a `// SAFETY:` comment; blocks containing several unsafe operations; public `unsafe` functions without a `# Safety` doc section. | Clippy `undocumented_unsafe_blocks`, `multiple_unsafe_ops_per_block` (restriction), `missing_safety_doc` (style) [clippy-lints] | Clippy | — | Yes |
| Panic sites | function | Counts of `unwrap()`, `expect()`, indexing and slicing, `panic!`, `todo!`, `unimplemented!`, `unreachable!` and unchecked arithmetic. | Clippy `unwrap_used`, `expect_used`, `indexing_slicing`, `panic`, `todo`, `unimplemented`, `unreachable`, `arithmetic_side_effects` (all restriction) [clippy-lints] | Clippy | Of 110 real panic bugs, "the majority of these issues (107 out of 110) are in safe code"; 27 were triggered by `unwrap()` and 12 by `expect()` ([Qin et al., TSE][qin-tse]). I found no study relating panic-site density to defects | Yes |
| Clippy warnings by lint group | crate, file | Number or density of warnings per group: correctness (deny by default), suspicious, style, complexity, perf (warn), pedantic, restriction, nursery, cargo (allow). | [Clippy README][clippy-readme] | Clippy | crates.io projects average 21 warnings per KLOC; "a lot of (42%) participants complained that Clippy produce relatively many and frequent false positives" ([Li et al. 2023][li23]). The README says the restriction group "should, *emphatically*, not be enabled as a whole" [clippy-readme]. No defect outcome studied | Yes |
| Lint suppressions | file, change | Number of `#[allow(...)]` attributes, and of those without a `reason`. | Clippy `allow_attributes`, `allow_attributes_without_reason` (restriction) [clippy-lints] | Clippy | — | Yes |
| Type complexity score | type expression | Score of a type expression: paths, slices, tuples and arrays add 10 × nesting level; Rust-ABI function pointers add 50 × nesting level; trait objects add 20 × nesting level, or 50 × when their bounds have lifetime parameters; references, raw pointers and inferred types (`_`) add 1. Default limit 250. | Clippy `type_complexity` source [clippy-tc]; [clippy-conf] | Clippy (complexity group; threshold lint) | — | Yes |
| Size limits on functions and types | function, type | Bool parameters (`fn_params_excessive_bools`, default 3) and bool fields (`struct_excessive_bools`, default 3); enum variant size (`large_enum_variant`, 200 bytes); `Err` variant size (`result_large_err`, 128 bytes); stack frame size (`large_stack_frames`, 512,000 bytes). | [Clippy lint configuration][clippy-conf] | Clippy (threshold lints) | — | Yes |
| Clone and shared-mutability patterns | function | Counts of redundant `.clone()` calls and of `Rc<Mutex<_>>`. | Clippy `redundant_clone` (nursery), `rc_mutex` (restriction) [clippy-lints] | Clippy | — | Yes |
| Compiler warnings | crate | Number of rustc warnings, for example `dead_code` and `missing_docs`. | [rustc lint listing][rustc-lints] | rustc | — | Yes |
| Public API size and semver violations | crate | Number of public API items and their diff between versions; number of changes that violate semantic versioning. | cargo-public-api [public-api]; cargo-semver-checks [semver-checks] | cargo-public-api (nightly rustdoc JSON), cargo-semver-checks | "More than 1 in 6 crates violated semver at least once" (172 of the 1000 most-downloaded library crates, more than 14,000 releases scanned; [Nowak & Gruevski 2023][semver-study], blog post by the tool's authors) | Yes |
| Build cost | crate, function | LLVM IR lines per generic function across instantiations; build time per crate; binary size per function or crate. | cargo-llvm-lines [llvm-lines]; `cargo build --timings` [timings]; cargo-bloat [bloat] | same | — | Partly |
| Feature-combination failures | crate | Number of feature combinations that fail to build or test. | cargo-hack `--each-feature`, `--feature-powerset` [cargo-hack] | cargo-hack | — | Partly |
| Undefined-behaviour and proof results | function, crate | Pass or fail results from running tests under Miri, and from Kani proof harnesses. | [Miri][miri]; [Kani][kani] | Miri, Kani | These are verdicts, not graded metrics | Partly |
| Classic metrics on Rust code | function | CC, cognitive complexity, Halstead, LOC and MI computed with RCA. | [Ardito et al. 2021][ardito21] | RCA | Nine code artifacts per language; "the results cannot be generalized to all software written with one of the analyzed programming languages" [ardito21] | Yes |

**Evidence for the family.** The Rust measures with outcome evidence are `unsafe` code (memory-safety bugs and vulnerabilities) and panic sites (panic bugs). That evidence reports the share of known bugs involving the construct; I found no study of whether a higher density predicts more defects. In C-to-Rust translations of seven GNU coreutils programs, Clippy reported zero findings in categories such as runtime panic risk and thread safety; the authors found that Clippy "either (i) reported the underlying problems under different labels or (ii) did not emit any lint at all" ([Tadesse et al. 2026][tadesse26]). A thesis on typestate and newtype refactorings found that "the typestate pattern improves faultlessness and testability significantly" at the cost of "more structural code that can degrade readability" ([Heuer 2026][heuer26]).

## 17. Composite quality models and indices

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Maintainability Index (MI) and variants | function, file | Original: 171 − 5.2·ln(Halstead volume) − 0.23·CC − 16.2·ln(SLOC). SEI variant: log2 terms plus 50·sin(sqrt(2.4·comment ratio)). Visual Studio variant: max(0, original × 100 / 171). | [Oman & Hagemeister 1992][oman92]; [Coleman et al. 1994][coleman94]; formulas as implemented in [RCA][rca-src] | RCA (all three variants) | Its inputs "are directly correlated with size (lines of code)"; "taking the average tends to mask the presence of high-risk parts"; "The set of programs used to derive the metric and evaluate it was small, and contained small programs only" ([van Deursen 2014][vandeursen14]). In a comparison of four equivalent systems, "The metrics were not mutually consistent" ([Sjøberg et al. 2012][sjoberg12]) | Yes |
| SIG maintainability model | system | Risk profiles: the share of code in units or modules above thresholds for unit size, unit complexity, unit interfacing and module coupling, plus duplication, component independence and component entanglement; mapped to 1–5 star ratings calibrated yearly on the SIG benchmark ("30,000 systems" in 2026). The 2026 model removed Volume and changed the aggregation of properties from the arithmetic mean to a power mean. | [Heitlager, Kuipers & Visser 2007][heitlager07]; [Alves et al. 2010][alves10] (thresholds; not opened); [SIG/TÜV criteria 2026][sig-criteria]; [SIG 2026 changes][sig-2026] | none (SIG's service is language-independent; I did not check its Rust support) | SIG authors found that "all but one of the metrics of the SIG quality model show a significant positive correlation" with defect resolution speed ([Luijten & Visser 2010][luijten10]). A replication with the 2018 model found "The overall maintainability correlation with defect resolution time decreased significantly" ([Wijnmaalen et al. 2019][wijnmaalen19]) | No |
| Delta Maintainability Model (DMM) | change | Classifies each changed line as low- or high-risk, adapting the SIG maintainability model; the delta score is the proportion of low-risk change. | [di Biase et al. 2019][dmm19] (abstract) | none | In a manual inspection of 100 commits, "67 cases matched the expert judgment" (authors' study, abstract) | Yes |
| SQALE technical debt and SonarQube maintainability rating | file, system | Debt = sum of remediation-effort estimates of rule violations; debt ratio = debt / (cost to develop one line × lines of code); rating A ≤ 5%, B < 10%, C < 20%, D < 50%, E ≥ 50%. New-code variants exist. | [Letouzey 2012][sqale12]; [SonarQube][sonar-metrics] | SonarQube | See technical-debt items in family 7 ([Lenarduzzi et al. 2019][lenarduzzi19]) | Yes (new-code variant) |
| SonarQube reliability and security ratings | system | Letter grade set by the most severe open issue of that quality: A when there are at most info-level issues, E when there is at least one blocker; a worst-case grade. | [SonarQube][sonar-metrics] | SonarQube | — | Yes (new-code variant) |
| Qlty technical debt ratio and grades | file, directory, system | Technical debt (estimated time to fix all code smells) divided by the effort to rewrite the code from scratch, estimated with Basic COCOMO; project grade A < 5%, B 5–10%, C 10–20%, D 20–50%, F ≥ 50%; file and directory grades use a logarithmic function of total debt. | [Qlty docs][qlty-metrics] | Qlty [qlty-rust] | — | Partly |
| CodeScene Code Health | file; system KPIs | Per-file score (examples in the docs range from 2.0 to 10.0; green, yellow and red bands) aggregated from "25+ factors"; system KPIs are LOC-weighted averages over hotspots ("Hotspot Code Health") and over all files ("Average Code Health"). | [CodeScene docs][cs-health] | CodeScene [cs-lang] | Vendor study of 39 proprietary codebases: "low quality code contains 15 times more defects than high quality code", and issue resolution "takes on average 124% more time" ([Tornhill & Borg 2022][codered22]). A follow-up by the same group reports "strong non-linearities at the extremes of the code quality spectrum" and "amplified returns on investment in the upper end" ([Borg et al. 2024][borg24]) | Partly |
| GitHub Code Quality scores | repository | Reliability and maintainability scores (Excellent, Good, Fair, Poor) set by the most severe CodeQL quality finding (none, note, warning, error). | [GitHub docs][gh-cq] | GitHub Code Quality (CodeQL languages) | — | No |
| Quamoco | system | Normalised measurement results mapped to utility values by utility functions, then aggregated with a weighted sum along the quality-model hierarchy. | [Wagner et al. 2015][quamoco15] | none | — | No |
| QMOOD quality attributes | system | High-level quality attributes "such as reusability, flexibility, and complexity", computed from design properties (encapsulation, modularity, coupling, cohesion) measured by the QMOOD design metrics (family 3), with weighted links. | [Bansiya & Davis 2002][qmood02] (abstract; attribute list and weights not opened) | none | "validated by using empirical and expert opinion" on commercial systems (abstract) | No |
| ColumbusQM (probabilistic quality model) | system | Probabilistic model that computes maintainability from metric values using "goodness" functions, "continuous generalizations of threshold based approaches", and integrates expert knowledge. | [Bakota et al. 2011][bakota11] (abstract) | none | On two systems, model values were "in a good correlation with the experts' expectations" (authors' study, abstract) | No |
| Squale marks | function to system | Individual marks per element (3 is the best mark), combined per practice by a weighted average with weighting function λ^(−mark), where λ sets hard, medium or soft tolerance of bad marks. | [Mordal-Manet et al. 2009 (research report)][squale09] | none | — | Partly |
| ISO/IEC 25010 and 25023 measures | system | Quality characteristics (for example maintainability, reliability, security) with measurement functions; "Most quality measures use a measurement function, which normalizes the result value within a range of 0,0 to 1,0". | [ISO/IEC 25023:2016 (preview sample)][iso25023] | none | — | No |
| CISQ measures (ASCQM, ISO/IEC 5055) and Automated Technical Debt Measure (ATDM) | system | Counts of CWE-based weaknesses for reliability, security, performance efficiency and maintainability; ATDM converts them into remediation effort. | [OMG ASCQM][omg-ascqm]; [OMG ATDM][omg-atdm] | none | "correlated measures rather than absolute measures" (the specification) [omg-ascqm] | Yes |
| CAST technical debt principal | system | Principal estimated by a formula with adjustable parameters from structural-quality violations. | [Curtis, Sappidi & Szynkarski 2012][curtis12] (abstract) | none | Characterised on 700 business applications (357 MLOC) against more than 1,200 rules (abstract) | No |
| CRAP (Change Risk Anti-Patterns) | function | CRAP(m) = comp(m)² × (1 − cov(m)/100)³ + comp(m), where comp is cyclomatic complexity and cov is test coverage in percent. | [Savoia 2007][savoia07] | crapper (Rust supported) [crapper] | — | Partly (needs coverage) |
| debtmap priority score | function | Unified score from cyclomatic and cognitive complexity, nesting, optional coverage, optional git history (change frequency, bug-fix rate, authors), coupling, purity and pattern entropy. | [debtmap][debtmap] | debtmap (Rust) | — | Partly |
| Sonargraph Maintainability Level | system | Percentage estimate (100 best) derived from the component dependency structure; lowered by cycles and by low-level classes with many incoming dependencies. Formula not given. | [Sonargraph][sonargraph] | none | — | No |

**Evidence for the family.** Composite scores inherit the evidence of their inputs and add aggregation choices. The validation studies I found were run by the vendors or groups that built the models (SIG, CodeScene), and the one independent replication of the SIG result found a weaker correlation with the newer model ([Wijnmaalen et al. 2019][wijnmaalen19]). Averages hide extreme parts ([van Deursen 2014][vandeursen14]); SIG changed its 2026 aggregation to a power mean because "a single high rating for a single system property would have disproportionate impact on the overall rating" ([SIG 2026 changes][sig-2026]).

## 18. AI-generated code

These metrics come from benchmarks and repository studies published since 2020, most since 2023.

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| pass@k | task | Share of problems for which at least one of k generated samples passes the problem's unit tests; Chen et al. estimate it from n ≥ k samples with c passing as 1 − C(n−c, k) / C(n, k), averaged over problems. | Kulal et al. 2019, as described by [Chen et al. 2021][chen21] | any test runner | See the next row: passing tests overstates correctness | Yes |
| Resolved rate on repository tasks (SWE-bench style) | task | Share of issues whose generated patch passes the task's tests. | [Jimenez et al. 2023 (SWE-bench)][swebench] (abstract); critique in [Wang, Pradel & Liu 2025][patchdiff] | any test runner | "7.8% of all patches" counted as correct "while failing the developer-written test suite", and "29.6%" of plausible patches "induce different behavior than the ground truth patches" ([PatchDiff][patchdiff], abstract). "roughly half of test-passing SWE-bench Verified PRs ... would not be merged into main by repo maintainers"; maintainer merge decisions are "about 24 percentage points lower" than grader scores ([METR 2026][metr-merge]) | Yes |
| CodeBLEU | snippet | BLEU n-gram match combined with syntax (AST) match and data-flow match against a reference solution. | [Ren et al. 2020][codebleu] (abstract) | none | "better correlation with programmer assigned scores" than BLEU and accuracy (authors' study, abstract) | Yes |
| CodeBERTScore | snippet | BERTScore-style similarity between generated and reference code that also encodes the natural-language input. | [Zhou et al. 2023][codebertscore] (abstract) | none | "higher correlation with human preference and with functional correctness than all existing metrics" (authors' study, abstract) | Yes |
| LLM-as-judge code scores (ICE-Score) | snippet | Quality score assigned by a large language model following an evaluation instruction. | [Zhuo 2023][icescore] (abstract) | any LLM | "superior correlations with functional correctness and human preferences" (author's study, abstract). For readability, LLM ratings agree weakly with humans ([CoReEval][coreeval]) | Yes |
| Multi-dimensional benchmark scores (RACE, NoFunEval) | task | Pass rates on tasks with readability, maintainability, efficiency or security requirements in addition to correctness. | [RACE][race]; [NoFunEval][nofuneval] (abstracts) | none | "current correctness-centric benchmarks fail to capture the multifaceted requirements of code" ([RACE][race]); "LMs generally falter" on non-functional requirements ([NoFunEval][nofuneval]) | Yes |
| Efficiency of generated code (EffiBench, Mercury "Beyond") | task | Execution time and memory relative to a canonical human solution; Mercury's Beyond weights the pass score by the runtime percentile. | [EffiBench][effibench]; [Mercury][mercury] (abstracts) | none | GPT-4's code took on average 3.12 times the execution time of human-written canonical solutions ([EffiBench][effibench]) | Yes |
| Vulnerability rate of generated code | task | Share of generated programs, in scenarios built around high-risk CWEs (for example MITRE's Top 25), that contain the targeted weakness. | [Pearce et al. 2022][pearce22] (abstract) | CodeQL (Rust GA) [codeql-rust] | Of 1,689 Copilot programs in 89 scenarios, "approximately 40% to be vulnerable" (abstract) | Yes |
| Package hallucination rate | task | Share of package references in generated code that name packages that do not exist. | [Spracklen et al. 2025][spracklen25] (abstract) | none (could be checked against crates.io) | "at least 5.2% for commercial models and 21.7% for open-source models" over 576,000 samples (abstract) | Yes |
| Static-analysis issues in generated code | task | Code smells, bugs and security smells found by linters (for example Pylint and Bandit) in generated code. | [Siddiq et al. 2022][siddiq22]; [Liu et al. 2024][liu24] (abstracts) | Clippy, SonarQube | A fine-tuned GPT-Neo model "leaked the smells and non-standard practices to the generated source code", and Copilot suggestions contained 18 types of code smells (Siddiq et al.); 4,066 ChatGPT programs analysed for correctness and quality issues (Liu et al.) | Yes |
| Structural erosion and verbosity across iterations | trajectory | Erosion: concentration of complexity; verbosity: share of redundant code; both tracked as an agent extends its own code over checkpoints. | [SlopCodeBench][slopcode] (abstract) | none | Erosion rose in 77% and verbosity in 75.5% of trajectories; agent code was 2.3 times more verbose and 2.0 times more eroded than 473 human Python repositories; "Explicit quality guidance reduces initial verbosity and erosion by up to a third, without affecting degradation rates" (abstract) | Partly |
| Codebase redundancy across rounds | trajectory | Messiness and redundancy of a codebase that agents edit over many tournament rounds (measurement method not opened). | [CodeClash][codeclash] (abstract) | none | "repositories become progressively messy and redundant" (abstract) | Partly |
| Downstream resolve rate on agent-written code | trajectory | Rate at which agents resolve later tasks when building on agent-written versus human-written code. | [CodeThread][codethread] (abstract) | none | Resolve-rate drops of "up to 13.1%"; "many traditional software engineering maintainability metrics do not explain this difference"; the factors that best explained it were "changes to input validation and error handling", together with downstream code size and task difficulty (abstract) | No |
| Structural-oracle pass rate | task | Share of maintainability probes where the edit passes both functional tests and a structural oracle (for example dependency control or responsibility decomposition). | [NITR][nitr] (abstract) | none | Configurations solved 36.2% on average; dependency control 4.3%; "64/483 outcomes (13.3%) pass all functional tests yet fail the structural oracle" (abstract) | Yes |
| GitClear repository metrics | repository | Short-term (two-week) churn, moved lines (reuse), copy/pasted lines, duplicated blocks, error-masking constructs; exact definitions are in gated reports. | [GitClear 2024][gitclear24]; [2025][gitclear25]; [2026][gitclear26] (landing pages) | none | Vendor trend reports: 2026 page reports rises in "within-commit copy/paste ( +41% ), code block duplication ( +81% ), error-masking constructs ( +47% ), and two-week code churn ( +15% )" [gitclear26]; I found no statement on the 2026 landing page of how AI-written code is identified | Partly |
| Issue introduction and survival rate | commit | Share of AI-authored commits that introduce at least one static-analysis issue, and share of introduced issues still present at the latest revision. | [Liu et al. 2026][liu26] (abstract) | none | 302.6k verified AI-authored commits: 7.5%–14.8% introduce an issue; code smells are 89.3% of issues; "22.7% of tracked AI-introduced issues still survive at the latest version" (abstract) | Partly |

**Evidence for the family.** Repository-level studies apply existing metrics to AI adoption: after Cursor adoption, "Static analysis warnings increase by 30% and code complexity increases by 41% post-adoption" ([He et al.][cursor-did]); after coding-agent adoption, warnings and cognitive complexity rose "by roughly 18% and 39%" ([Agarwal et al. 2026][agarwal26], abstract). Test-based correctness metrics overstate quality relative to maintainer judgement ([METR 2026][metr-merge]; [PatchDiff][patchdiff]). Nearly all metrics in this family are proposed and evaluated by their own authors in a single study.

## 19. Agent pull requests

These studies mostly use the AIDev dataset of agent-authored pull requests ([Li, Zhang & Hassan 2025][aidev]).

| Metric | Level | Definition | Origin | Rust tool | Validity evidence | Changed code only |
|---|---|---|---|---|---|---|
| Acceptance (merge) rate and review latency | PR | Share of PRs merged; time to first human review. | [AIDev][aidev]; [Kraishan 2026][kraishan26] (abstracts) | GitHub API | Agent PRs "are accepted less frequently" than human PRs [aidev]; Claude Code PRs waited longest for a first human review (median 12.6 hours) [kraishan26] | Yes |
| Revert rate | PR | Share of merged PRs later reverted. | [Kraishan 2026][kraishan26] (abstract) | git | Codex 6.1%, human 11.5%, Devin 14.5% [kraishan26] | Partly (needs later history) |
| Follow-up fix rate | PR | Share of merged PRs that receive a verified later fix. | [Takerngsaksiri et al. 2026][followup26] (abstract) | git | Merged agent PRs "attract verified fixes at 1.62 times the odds of merged human PRs"; 69.6% of the fixes come from the same agent (abstract) | Partly |
| New static-analysis issues per changed KLOC | PR | Issues present after merge and absent before, divided by churn. | [Cynthia, Muttakin & Roy 2026][cynthia26] (abstract) | SonarQube, Clippy | "apparent differences in raw issue counts across agents largely disappear after normalizing by code churn" (1,210 merged bug-fix PRs, abstract) | Yes |
| Test inclusion and changed-line coverage | PR | Whether the PR changes tests; share of changed executable lines executed by existing or added tests. | [Dipongkor et al. 2026][dipongkor26] (abstract) | cargo-llvm-cov with a diff | Tests included in 49.6% of eligible PRs; existing tests covered 61.5% (Java) and 27.0% (Python) of changed lines; error-handling code was "the most consistently under-tested" (abstract) | Yes |
| Test oracle strength | PR | Share of test-file patches with strong, weak or no explicit oracle (assertion) signals, from an eight-category taxonomy. | [Banik et al. 2026][banik26] (abstract) | none | "80.2% of test patches contain weak or no explicit oracle signals"; strong oracles raised merge odds (OR = 1.28) after adjustment (abstract) | Yes |
| Test addition, modification and deletion rates | PR | Odds that a PR adds, modifies or deletes tests, compared within repositories. | [Milanese et al. 2026][milanese26] (abstract) | git | Within 391 Java repositories, agent-supported PRs add tests more often and modify or delete them less often than human PRs; "its relationship with test quality remains uncertain" (abstract) | Yes |
| Redundancy and missed reuse | PR | How much new code in a PR duplicates code that could have been reused (measurement method not opened). | [Huang et al. 2026][huang26] (abstract) | none | Agent PRs "frequently disregard code reuse opportunities, resulting in higher levels of redundancy compared to human developers"; reviewers expressed "more neutral or positive emotions" towards them (abstract) | Partly |
| Security smells in added code | PR | Presence of patterns such as hard-coded credentials or eval-style constructs in added lines. | [Kraishan 2026][kraishan26] (abstract) | none | Agent code was less likely than human code to contain a security smell (odds ratio 0.63) (abstract) | Yes |
| Reviewer approval and comment volume over time | reviewer | Change in a reviewer's approval rate and inline comments across repeated reviews of agent PRs. | [Yu et al. 2026][yu26] (abstract) | GitHub API | Approval rose from 30.1% to 36.8% while inline comments fell 22%, "most consistent with reflexive habituation" (abstract) | No |
| Metric change in readability-motivated agent commits | commit | Before–after change in MI, CC and LOC for commits labelled as readability improvements. | [Horikawa et al. 2026][horikawa26] (abstract) | RCA (MI, CC) | "the Maintainability Index decreased in 56.1% of commits, while Cyclomatic Complexity increased in 42.7%" (403 commits, abstract) | Yes |
| Cheating rate | task | Pass rate on tasks whose tests contradict the specification, so any pass requires a shortcut such as editing tests. | [ImpossibleBench][impossible] (abstract) | none | Defined as a measure of "propensity to exploit test cases" (abstract) | Yes |

**Evidence for the family.** Results depend on normalisation: per-churn issue rates remove most differences between agents ([Cynthia et al.][cynthia26]), and per-vendor revert rates differ in both directions from humans ([Kraishan][kraishan26]). Follow-up fixes ([Takerngsaksiri et al.][followup26]) and reviewer habituation ([Yu et al.][yu26]) are outcome measures specific to agent workflows. All studies are 2025–2026 preprints or new conference papers; I found no replications.

## 20. Outcome measures used to validate metrics

These are the dependent variables in the studies above. They are listed because "validity" in the tables means association with one of them.

| Outcome | Level | Definition | Used in |
|---|---|---|---|
| Fault-proneness, fault count, fault density | type, file, module | Whether, or how many, faults were later traced to the unit; density divides by size. Relating size metrics to fault density "may be misleading, as there will always be a negative correlation between size metrics and fault density" ([Radjenović][radj]) | [Radjenović][radj]; [El Emam][elemam]; [Briand 1999][briand99] |
| Defect-inducing change | change | A change later implicated by a bug fix, identified with the SZZ algorithm | [Śliwerski et al. 2005][sliwerski05]; [Kamei et al.][kamei13] |
| Change-proneness | file, method | Number of later changes | [Palomba et al.][palomba18]; [Chowdhury et al.][chowdhury22] |
| Maintenance effort | file, task | Developer time spent on maintenance tasks | [Sjøberg et al. 2013][sjoberg13] |
| Issue or defect resolution time | system | Time to resolve issues in the tracker | [Luijten & Visser][luijten10]; [Tornhill & Borg][codered22] |
| Comprehension | snippet | Time, correctness and subjective difficulty of understanding code; physiological measures (fMRI, EEG, eye tracking) | [Muñoz Barón et al.][baron20]; [Scalabrino et al.][scalabrino19]; [Peitek et al.][peitek21]; [Hao et al.][hao23] |
| Vulnerabilities | function, package | Known vulnerabilities (CVE, RustSec) traced to code | [Zheng et al.][zheng23]; [Shin et al.][shin11] |
| Production incidents | change | Severe faults affecting users (Meta's SEVs) | [Abreu et al.][meta-drs] |
| Delivery performance (DORA) | team | Change lead time, deployment frequency, failed deployment recovery time, change fail rate, deployment rework rate | [DORA][dora] |
| Maintainer merge decision | PR | Whether maintainers would merge a patch | [METR 2026][metr-merge] |
| Mutant detection | test suite | Share of seeded faults detected; used as a proxy for real-fault detection | [Inozemtseva & Holmes][inozemtseva14]; [Just et al.][just14] |

## Gaps and unverified items

- **Catalogue papers.** I could not open the full text or an abstract of Nuñez-Varela et al. 2017 ([DOI][nunez]), so this catalogue does not use it. Of Ardito et al. 2020 I could open only the abstract, which reports 174 metrics, a set of 15 most commonly mentioned ones, 19 metric tools, and "minimal coverage of metrics for newer or less popular programming languages" ([Ardito et al. 2020][ardito20]). I used [Radjenović et al. 2013][radj] and tool documentation as the main sources for the metric list instead.
- **SciTools Understand.** Its metric documentation returned HTTP 403, so I could not check which metrics it computes or whether it computes them for Rust. Search results that I could not verify say that version 8.0 added Rust.
- **Definitions not opened or unverified:** Lorenz & Kidd inheritance formulas (for example SIX); CTA and CTM; the COF formula; the SCC definition; Halstead's book; the Fowler–Beck smell catalogue; Lanza–Marinescu detection strategies other than God Class and Data Class; Garcia et al.'s architectural smell catalogue ([DOI][garcia09]); Designite's architecture smells (the documentation page rendered empty); Moser's metric list; MQ; core size; Sarkar et al.'s metric list; the Component Balance and ATDI formulas; GitClear's metric definitions (gated reports).
- **Results not opened:** D'Ambros et al. 2009 on change coupling and defects; Khomh et al. 2012 on antipatterns ([DOI][khomh12]); Kapser & Godfrey 2008 ([DOI][kapser08]); Gil & Lalouche 2017 on size and metric validity ([DOI][gil17]; no abstract available to me); Alves et al. 2010 on threshold derivation ([DOI][alves10]).
- **Rust.** I found no catalogue of Rust-specific code smells with validity data, no study relating the density of `unsafe` code, panic sites, `.clone()` calls or Clippy warnings to defects, and no crates.io-wide distribution of per-function metrics that could be used to set thresholds.
- **Not covered:** functional size measured from requirements (IFPUG and COSMIC function points); energy-consumption metrics; metrics defined only in commercial products whose documentation I did not open.
## Sources

Link targets for the references above, in alphabetical order of their keys. DOI links resolve to the publisher; I checked their titles against Crossref.

[abc-wiki]: https://en.wikipedia.org/wiki/ABC_Software_Metric
[agarwal26]: https://arxiv.org/abs/2601.13597
[aidev]: https://arxiv.org/abs/2507.15003
[aivosto-ifc]: https://www.aivosto.com/project/help/pm-proc-infoflow.html
[aivosto-sysc]: https://www.aivosto.com/project/help/pm-syscomplexity.html
[aldallal12]: https://doi.org/10.1145/2089116.2089118
[alves10]: https://doi.org/10.1109/ICSM.2010.5609747
[arcan17]: https://doi.org/10.1109/ICSAW.2017.16
[ardito20]: https://doi.org/10.1155/2020/8840389
[ardito21]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7959618/
[arnaoudova13]: https://doi.org/10.1109/CSMR.2013.28
[astrauskas20]: https://doi.org/10.1145/3428204
[atdi18]: https://doi.org/10.1109/SEAA.2018.00073
[athanasiou14]: https://doi.org/10.1109/TSE.2014.2342227
[audit]: https://github.com/rustsec/rustsec/tree/main/cargo-audit
[avelino16]: https://arxiv.org/abs/1604.06766
[bakota11]: https://doi.org/10.1109/ICSM.2011.6080791
[baldwin14]: https://doi.org/10.1016/j.respol.2014.05.004
[banik26]: https://arxiv.org/abs/2606.18168
[baron20]: https://arxiv.org/abs/2007.12520
[beyer10]: https://doi.org/10.1109/icpc.2010.49
[bieman95]: https://doi.org/10.1145/211782.211856
[bird11]: https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf
[bloat]: https://github.com/RazrFalcon/cargo-bloat
[boeckeler]: https://martinfowler.com/articles/sensors-for-coding-agents.html
[borg24]: https://arxiv.org/abs/2401.13407
[bouwers11cb]: https://doi.org/10.1109/WICSA.2011.20
[bouwers11dp]: https://doi.org/10.1109/icsm.2011.6080827
[bouwers14]: https://doi.org/10.1109/icsme.2014.43
[briand97]: https://doi.org/10.1145/253228.253367
[briand99]: https://www.cs.colostate.edu/~cs514dl/2019fa/more_discussions/briandICSE99.pdf
[buse10]: https://web.eecs.umich.edu/~weimerw/p/weimer-tse2010-readability-preprint.pdf
[butler10]: https://doi.org/10.1109/CSMR.2010.27
[campbell18]: https://doi.org/10.1145/3194164.3194186
[cargo-hack]: https://crates.io/crates/cargo-hack
[cargo-metadata]: https://doc.rust-lang.org/cargo/commands/cargo-metadata.html
[cargo-modules]: https://github.com/regexident/cargo-modules
[cataldo08]: https://doi.org/10.1145/1414004.1414008
[cccc]: https://github.com/moznion/cccc
[chen21]: https://arxiv.org/abs/2107.03374
[chowdhury22]: https://research.tudelft.nl/en/publications/revisiting-the-debate-are-code-metrics-useful-for-measuring-maint
[ck]: https://github.com/mauricioaniche/ck
[ck94]: https://doi.org/10.1109/32.295895
[clippy-cog]: https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/cognitive_complexity.rs
[clippy-conf]: https://doc.rust-lang.org/clippy/lint_configuration.html
[clippy-lints]: https://rust-lang.github.io/rust-clippy/stable/index.html
[clippy-readme]: https://github.com/rust-lang/rust-clippy/blob/master/README.md
[clippy-tc]: https://github.com/rust-lang/rust-clippy/blob/master/clippy_lints/src/types/type_complexity.rs
[codebertscore]: https://arxiv.org/abs/2302.05527
[codebleu]: https://arxiv.org/abs/2009.10297
[codeclash]: https://arxiv.org/abs/2511.00839
[codeql-rust]: https://github.blog/changelog/2025-10-14-codeql-scanning-rust-and-c-c-without-builds-is-now-generally-available
[codered22]: https://arxiv.org/abs/2203.04374
[codethread]: https://arxiv.org/abs/2606.21804
[coleman94]: https://doi.org/10.1109/2.303623
[coreeval]: https://arxiv.org/abs/2510.16579
[cox15]: https://doi.org/10.1109/ICSE.2015.140
[crapper]: https://github.com/unclebob/crapper
[crev]: https://crates.io/crates/cargo-crev
[cs-health]: https://codescene.io/docs/guides/technical/code-health.html
[cs-hotspots]: https://codescene.io/docs/guides/technical/hotspots.html
[cs-lang]: https://codescene.io/docs/usage/language-support.html
[cursor-did]: https://arxiv.org/abs/2511.04427
[curtis12]: https://doi.org/10.1109/MS.2012.156
[cynthia26]: https://arxiv.org/abs/2601.20109
[dambros09]: https://doi.org/10.1109/WCRE.2009.19
[debtmap]: https://github.com/iepathos/debtmap
[deny]: https://embarkstudios.github.io/cargo-deny/checks/index.html
[depadua18]: https://doi.org/10.1145/3196398.3196435
[designite]: https://github.com/tushartushar/DesigniteJava
[dipongkor26]: https://arxiv.org/abs/2607.18057
[dmm19]: https://doi.org/10.1109/TechDebt.2019.00030
[dora]: https://dora.dev/guides/dora-metrics/
[drs-oss]: https://arxiv.org/abs/2511.21964
[dryer]: https://github.com/unclebob/dryer
[eder13]: https://doi.org/10.1109/IWAST.2013.6595800
[effibench]: https://arxiv.org/abs/2402.02037
[elemam]: https://www.ehealthinformation.ca/web/default/files/wp-files/1062.pdf
[evans20]: https://arxiv.org/abs/2007.00752
[feitelson23]: https://www.cse.huji.ac.il/~feit/papers/Comp23CACM.pdf
[feldt16]: https://arxiv.org/abs/1506.03482
[followup26]: https://arxiv.org/abs/2609.26847
[gall98]: https://doi.org/10.1109/ICSM.1998.738508
[garcia09]: https://doi.org/10.1007/978-3-642-02351-4_10
[geiger]: https://github.com/geiger-rs/cargo-geiger
[geiger-serde]: https://github.com/geiger-rs/cargo-geiger/blob/master/cargo-geiger-serde/src/report.rs
[gh-cq]: https://docs.github.com/en/code-security/reference/code-quality/metrics-and-ratings
[gil17]: https://doi.org/10.1007/s10664-017-9513-5
[gitclear24]: https://www.gitclear.com/coding_on_copilot_data_shows_ais_downward_pressure_on_code_quality
[gitclear25]: https://www.gitclear.com/ai_assistant_code_quality_2025_research
[gitclear26]: https://www.gitclear.com/write_only_mode_ai_research
[gonzalez17]: https://doi.org/10.1007/978-3-319-57735-7_17
[google-flaky]: https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html
[gopinath14]: https://www.cefns.nau.edu/~adg326/icse14.pdf
[graves00]: https://cs.uwaterloo.ca/~m2nagapp/courses/CS846/1171/papers/graves_tse98.pdf
[grcov]: https://github.com/mozilla/grcov
[greiler15]: https://microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf
[habib18]: https://doi.org/10.1145/3238147.3238213
[hao23]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9942489/
[hassan09]: https://sailresearch.github.io/sail-website/data/pdfs/ICSE2009_PredictingFaultsUsingTheComplexityOfCodeChanges.pdf
[heitlager07]: https://doi.org/10.1109/QUATIC.2007.8
[henry81]: https://doi.org/10.1109/TSE.1981.231113
[heuer26]: https://arxiv.org/abs/2607.02744
[hilton18]: https://mir.cs.illinois.edu/marinov/publications/HiltonETAL18TestCoverageEvolution.pdf
[hindle12]: https://www.cs.ucdavis.edu/~devanbu/natural.pdf
[horikawa26]: https://arxiv.org/abs/2603.13723
[huang26]: https://arxiv.org/abs/2601.21276
[icescore]: https://arxiv.org/abs/2304.14317
[impossible]: https://arxiv.org/abs/2510.20270
[infer]: https://discovery.ucl.ac.uk/10084236/1/O%27Hearn%20AAM%20scaling-static-analysis-at-facebook.pdf
[inozemtseva14]: https://cs.ubc.ca/~rtholmes/papers/icse_2014_inozemtseva.pdf
[iso25023]: https://cdn.standards.iteh.ai/samples/35747/34b91bc957f647ce8bbb2093907d7bc0/ISO-IEC-25023-2016.pdf
[ivankovic19]: https://homes.cs.washington.edu/~rjust/publ/google_coverage_fse_2019.pdf
[jdepend]: https://github.com/clarkware/jdepend/blob/master/docs/JDepend.html
[jitline21]: https://arxiv.org/abs/2103.07068
[jscpd]: https://github.com/kucherenko/jscpd
[juergens09]: https://arxiv.org/pdf/1701.05472
[just14]: https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf
[kamei13]: https://doi.org/10.1109/TSE.2012.70
[kani]: https://github.com/model-checking/kani
[kapser08]: https://doi.org/10.1007/s10664-008-9076-6
[khomh12]: https://doi.org/10.1007/s10664-011-9171-y
[koana24]: https://arxiv.org/abs/2405.15665
[kochhar17]: https://doi.org/10.1109/TR.2017.2727062
[kraishan26]: https://arxiv.org/abs/2609.17598
[kudrjavets06]: https://doi.org/10.1109/issre.2006.14
[landman]: https://homepages.cwi.nl/~jurgenv/papers/JSEP-2015.pdf
[lanza06]: https://doi.org/10.1007/3-540-39538-5
[lawrie06]: https://doi.org/10.1109/ICPC.2006.51
[lenarduzzi19]: https://arxiv.org/abs/1908.11590
[lenarduzzi20]: https://arxiv.org/abs/1907.00376
[li23]: https://arxiv.org/abs/2310.11738
[libyear]: https://libyear.com/
[libyear-crate]: https://crates.io/crates/cargo-libyear
[lihenry93]: <https://doi.org/10.1016/0164-1212(93)90077-B>
[liu24]: https://doi.org/10.1145/3643674
[liu26]: https://arxiv.org/abs/2603.28592
[lizard]: https://github.com/terryyin/lizard
[lizard-ext]: https://github.com/terryyin/lizard/blob/master/lizard_ext/README.md
[llvm-cov]: https://github.com/taiki-e/cargo-llvm-cov
[llvm-lines]: https://github.com/dtolnay/cargo-llvm-lines
[luijten10]: https://webarchive.di.uminho.pt/wiki.di.uminho.pt/twiki/pub/Personal/Joost/PublicationList/SQM2010-FasterDefectResolution.pdf
[maccormack06]: https://doi.org/10.1287/mnsc.1060.0552
[machete]: https://github.com/bnjbvr/cargo-machete
[majumder22]: https://arxiv.org/abs/2008.09569
[manadhata11]: https://doi.org/10.1109/TSE.2010.60
[mancoridis98]: https://doi.org/10.1109/WPC.1998.693283
[marcus08]: https://doi.org/10.1109/TSE.2007.70768
[marinescu04]: https://doi.org/10.1109/ICSM.2004.1357820
[mccabe76]: https://doi.org/10.1109/TSE.1976.233837
[mcintosh14]: https://doi.org/10.1145/2597073.2597076
[mcintosh18]: https://rebels.cs.uwaterloo.ca/papers/tse2017_mcintosh.pdf
[mercury]: https://arxiv.org/abs/2402.07844
[meta-drs]: https://arxiv.org/abs/2410.06351
[metr-merge]: https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/
[mi22]: https://doi.org/10.1016/j.jss.2022.111454
[milanese26]: https://arxiv.org/abs/2610.35297
[miri]: https://github.com/rust-lang/miri
[mo15]: https://doi.org/10.1109/WICSA.2015.12
[mo16]: https://www.cs.drexel.edu/~yc349/papers/2016/icse2016-DL.pdf
[mockus00]: https://doi.org/10.1002/bltj.2229
[mood96]: https://doi.org/10.1109/METRIC.1996.492446
[moser08]: https://doi.org/10.1145/1368088.1368114
[mutants]: https://github.com/sourcefrog/cargo-mutants
[mutants-diff]: https://github.com/sourcefrog/cargo-mutants/blob/main/book/src/in-diff.md
[mutator]: https://github.com/unclebob/mutator
[nagappan05]: https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icse05churn.pdf
[nagappan08]: https://www.cs.umd.edu/users/basili/publications/proceedings/P125.pdf
[nejmeh88]: https://doi.org/10.1145/42372.42379
[nextest]: https://nexte.st/docs/features/retries/
[niedermayr16]: https://arxiv.org/abs/1611.07163
[nist500235]: https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication500-235.pdf
[nitr]: https://arxiv.org/abs/2603.27745
[nofuneval]: https://arxiv.org/abs/2401.15963
[nunez]: https://doi.org/10.1016/j.jss.2017.03.044
[oman92]: https://doi.org/10.1109/ICSM.1992.242525
[omg-aep]: https://www.omg.org/spec/AEP/
[omg-afp]: https://www.omg.org/spec/AFP/
[omg-ascqm]: https://www.omg.org/spec/ASCQM/
[omg-atdm]: https://www.omg.org/spec/ATDM/
[outdated]: https://crates.io/crates/cargo-outdated
[palomba18]: https://doi.org/10.1007/s10664-017-9535-z
[papadakis18]: https://mpapad.github.io/publications/pdfs/ICSE2018.pdf
[patchdiff]: https://arxiv.org/abs/2503.15223
[pearce22]: https://arxiv.org/abs/2108.09293
[peitek21]: https://www.se.cs.uni-saarland.de/publications/docs/PAP+21.pdf
[petrovic21]: https://arxiv.org/abs/2102.11378
[pmd-design]: https://docs.pmd-code.org/latest/pmd_rules_java_design.html
[pmd-metrics]: https://docs.pmd-code.org/pmd-doc-6.55.0/pmd_java_metrics_index.html
[pmd-rust]: https://docs.pmd-code.org/latest/pmd_languages_rust.html
[posnett11]: https://doi.org/10.1145/1985441.1985454
[potdar14]: https://doi.org/10.1109/ICSME.2014.31
[public-api]: https://github.com/cargo-public-api/cargo-public-api
[qin-tse]: https://songlh.github.io/paper/rust-tse.pdf
[qin20]: https://songlh.github.io/paper/rust-study.pdf
[qlty-metrics]: https://docs.qlty.sh/cloud/maintainability/metrics
[qlty-rust]: https://docs.qlty.sh/languages/rust
[qlty-smells]: https://docs.qlty.sh/code-smells
[qmood02]: https://doi.org/10.1109/32.979986
[quamoco15]: https://arxiv.org/abs/1611.09230
[race]: https://arxiv.org/abs/2407.11470
[radj]: https://gup.ub.gu.se/file/127150
[rahman10]: https://microsoft.com/en-us/research/wp-content/uploads/2016/02/rahman2010cws.pdf
[rahman13]: https://2013.icse-conferences.org/content/how-and-why-process-metrics-are-better.html
[ray16]: https://doi.org/10.1145/2884781.2884848
[rca]: https://mozilla.github.io/rust-code-analysis/metrics.html
[rca-src]: https://github.com/mozilla/rust-code-analysis/tree/master/src/metrics
[romano20]: https://doi.org/10.1109/TSE.2018.2842781
[roy09]: https://doi.org/10.1016/j.scico.2009.02.007
[rustc-allowed]: https://doc.rust-lang.org/rustc/lints/listing/allowed-by-default.html
[rustc-lints]: https://doc.rust-lang.org/rustc/lints/listing/warn-by-default.html
[rustdoc-cov]: https://doc.rust-lang.org/rustdoc/unstable-features.html#--show-coverage-calculate-the-percentage-of-items-with-documentation
[rustfdn24]: https://web.archive.org/web/2024/https://foundation.rust-lang.org/news/unsafe-rust-in-the-wild-notes-on-the-current-state-of-unsafe-rust/
[sadowski18]: https://doi.org/10.1145/3188720
[sarkar07]: https://doi.org/10.1109/TSE.2007.256942
[sas22]: https://arxiv.org/abs/2203.08702
[savoia07]: https://www.artima.com/weblogs/viewpost.jsp?thread=210575
[scalabrino18]: https://doi.org/10.1002/smr.1958
[scalabrino19]: https://www.cs.wm.edu/~denys/pubs/TSE%2719-Understandability.pdf
[schuler13]: https://doi.org/10.1002/stvr.1497
[scorecard]: https://github.com/ossf/scorecard/blob/main/docs/checks.md
[semgrep-langs]: https://docs.semgrep.dev/supported-languages
[semver-checks]: https://github.com/obi1kenobi/cargo-semver-checks
[semver-study]: https://predr.ag/blog/semver-violations-are-common-better-tooling-is-the-answer/
[sergeyuk24]: https://arxiv.org/abs/2401.14936
[shear]: https://github.com/Boshen/cargo-shear
[shin11]: https://doi.org/10.1109/TSE.2010.81
[siddiq22]: https://doi.org/10.1109/SCAM55253.2022.00014
[sig-2026]: https://github.com/Software-Improvement-Group/sigridci/blob/main/docs/reference/quality-model-documents/2026-model-changes.md
[sig-criteria]: https://www.softwareimprovementgroup.com/wp-content/uploads/SIG-TUViT-Evaluation-Criteria-Trusted-Product-Maintainability.pdf
[sjoberg12]: https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.anda.mockus.esem.2012.pdf
[sjoberg13]: https://doi.org/10.1109/TSE.2012.89
[sliwerski05]: https://doi.org/10.1145/1083142.1083147
[slopcode]: https://arxiv.org/abs/2603.24755
[sonar-cc]: https://www.sonarsource.com/docs/CognitiveComplexity.pdf
[sonar-metrics]: https://docs.sonarsource.com/sonarqube-server/latest/user-guide/code-metrics/metrics-definition/
[sonar-rust]: https://docs.sonarsource.com/sonarqube-server/latest/analyzing-source-code/languages/rust/
[sonargraph]: https://eclipse.hello2morrow.com/doc/standalone/content/core_metrics.html
[sotovalero21]: https://arxiv.org/abs/2001.07808
[spadini18]: https://doi.org/10.1109/ICSME.2018.00010
[spellcheck]: https://crates.io/crates/cargo-spellcheck
[spracklen25]: https://arxiv.org/abs/2406.10279
[sqale12]: https://doi.org/10.1109/MTD.2012.6225997
[squale09]: https://inria.hal.science/inria-00637363v1/file/Mord09b-TechReport-Squale.pdf
[steidl13]: https://doi.org/10.1109/ICPC.2013.6613836
[swebench]: https://arxiv.org/abs/2310.06770
[tadesse26]: https://arxiv.org/abs/2602.00840
[tarpaulin]: https://github.com/xd009642/tarpaulin
[timings]: https://doc.rust-lang.org/cargo/reference/timings.html
[tokei]: https://github.com/XAMPPRocky/tokei
[trautsch23]: https://doi.org/10.1007/s10664-023-10301-2
[tricorder]: https://research.google.com/pubs/archive/43322.pdf
[trockman18]: https://doi.org/10.1145/3196398.3196441
[tsdetect]: https://testsmells.org/pages/testsmells.html
[udeps]: https://github.com/est31/cargo-udeps
[unused-features]: https://crates.io/crates/cargo-unused-features
[vandeursen14]: https://avandeursen.com/2014/08/29/think-twice-before-using-the-maintainability-index/
[verape18]: https://arxiv.org/abs/1807.05030
[vet]: https://crates.io/crates/cargo-vet
[warnalyzer]: https://crates.io/crates/warnalyzer
[wehaibi16]: https://doi.org/10.1109/SANER.2016.72
[wijnmaalen19]: https://ceur-ws.org/Vol-2510/sattose2019_paper_11.pdf
[wong11]: https://doi.org/10.1145/1985793.1985850
[woodward79]: https://doi.org/10.1109/TSE.1979.226497
[xiao14]: https://doi.org/10.1145/2568225.2568241
[xu21]: https://arxiv.org/abs/2003.03296
[yu26]: https://arxiv.org/abs/2606.22721
[zahan23]: https://arxiv.org/abs/2210.14884
[zeng21]: https://zhangyuqun.github.io/publications/issta2021.pdf
[zerouali19]: https://doi.org/10.1002/smr.2157
[zhang-sast]: https://arxiv.org/abs/2610.21373
[zhangmesbah15]: https://people.ece.ubc.ca/amesbah/resources/papers/fse15.pdf
[zhao23]: https://doi.org/10.1145/3567550
[zhao26]: https://arxiv.org/abs/2607.22880
[zheng23]: https://arxiv.org/abs/2308.15046
[zimmermann05]: https://doi.org/10.1109/TSE.2005.72
[zimmermann08]: https://doi.org/10.1145/1368088.1368161
