# Deterministic prose slop detection

Research for Smog, 2026-11-08. Scope: Rust comments and Markdown docs, using phrase lists and sentence structure, with no LLM and no embeddings. Ticket IDs, history narration and comment hedging are already in `docs/design/measurement-model.md` sections 3.1 and 3.6; this file adds to them and does not repeat them.

## Summary

- **Phrase and pattern rules are feasible.** Published tools already do this. I found no independent evaluation of any tool, on any corpus of code comments.
- **False positives are the main risk.** One tool's own test failed 21 of 28 human English excerpts ([humanizer-lint][HUM]). Wikipedia says these signs are not proof of AI writing ([WP]). So Smog should present these rules as a style policy and make no claim about who wrote the text.
- **A long sentence is not shown to be a bad sentence.** In one small study of adult newspaper text, words per sentence did not predict readers' ratings, and more verb phrases per sentence went with higher ratings ([Pitler and Nenkova][PIT]). The sentence limits below are therefore style policy.
- **No regex finds a new metaphor.** Lists catch listed phrases only ([Claudisms][CLA] says the same). Malte's metaphor complaint can be covered only by a list that grows.
- **Lists go out of date.** "Delve" fell to 1 in 1,000 chats by July 2025 ([Washington Post via Boston Globe][WAPO]). "Load-bearing" rose from 0.5 to 12.0 hits per 10,000 words between two model versions in one user's sample ([issue 53454][ISS]). Each list entry needs a source and a review date.

## Findings

Evidence labels:

| Label | Meaning |
| --- | --- |
| Study | Published measurement or experiment |
| Press | Journalist's data analysis |
| User count | One person's counts of their own logs or threads, not controlled |
| Guidance | Published style standard from an organization |
| Community | Maintained by volunteer editors |
| Catalog | One author's list, based on judgment |
| Tool | Software with rules. Evaluation noted where one exists |
| Request | Malte's request |
| Own | My proposal, with no source behind it |

### Lists of phrases and constructions

| Source | Label | What it gives | Limits it states or that I found |
| --- | --- | --- | --- |
| [Wikipedia: Signs of AI writing][WP] | Community | Words to watch by model period; negative parallelism; rule of three; copula avoidance; superficial `-ing` analyses; vague attribution; chatbot phrases | "Not all text featuring these indicators is AI-generated". It lists perfect grammar and transition words in isolation ("Additionally", "Consequently", "Notably") as ineffective indicators. One or two vocabulary words may be coincidence; many in one edit is "one of the strongest tells". "underscore" can be literal |
| [Kobak et al.][KOB] | Study, PubMed abstracts 2010 to 2024 | 379 excess style words in 2024. Ratios: "delves" 28.0, "underscores" 13.8, "showcasing" 10.7. Common set: across, additionally, comprehensive, crucial, enhancing, exhibited, insights, notably, particularly, within | Biomedical abstracts only. Cannot separate LLM use from people adopting the words. I did not read the 291-word rare list, which is a figure |
| [Juzek and Ward][JUZ] | Study, COLING 2025 | 21 focal words: delves, delved, delving, showcasing, delve, boasts, underscores, comprehending, intricacies, surpassing, intricate, underscoring, garnered, showcases, emphasizing, underscore, realm, surpasses, groundbreaking, advancements, aligns | PubMed and ChatGPT-3.5 only. Experiments on the cause were exploratory |
| [Reinhart et al.][REI] | Study, PNAS 2025 | GPT-4o against humans: present participial clauses about 5.3 times, "that" clauses as subject 2.6, nominalizations 2.1, phrasal coordination 1.9 | "generalizability across LLMs or to different registers of text is difficult". The features come from a tagger; the paper does not say which work without one |
| [Washington Post via Boston Globe][WAPO] | Press, 328,744 GPT-4o messages | "Not just X, but Y" in 6 percent of chats in July 2025 | Shared chats only, to July 2025. A later article notes that the unit (chats or messages) varies in reports |
| [Lazovic on negative parallelism][LAZ] | Blog, collects other figures | Pangram: "not just X but Y" about 3 times more common in AI text. Barron's: fourfold rise in corporate filings | Pangram is a vendor and its method is not described. I did not open the Atlantic or Barron's originals |
| [claude-code issue 53454][ISS] | User count | "load-bearing": Opus 4.6 0.5 and Opus 4.7 12.0 hits per 10,000 words (one user); per 100,000 words, 19.5 for Opus 5, 6.4 for Opus 4.8, 2.3 for Sonnet 5 (another user). Maintainer reports the phrase in the built-in prompt text | Small samples, single users. The cause is a claim |
| [Matsuoka, The Word Problem][HYP] | User count | Mentions in Hacker News threads he read: load-bearing 83, seam(s) 36, honest/honestly 66. "worth noting/naming/knowing" openers 0.451 per 1,000 words in Opus 5, 0.042 in Fable 5. "wearing" or "dressed as" metaphor: 26 uses in Opus 5, none in other sampled output | Threads were not sampled systematically. One author's logs |
| [tropes.fyi][TRO] | Catalog | 49 tropes, including compulsive counting ("Five things we wish to discuss"), "Where it actually lives", "Not X. Not Y. Just Z.", "The X? A Y.", false ranges, preamble ("Two constraints shape the design.") | Almost no data |
| [Claudisms][CLA] | Catalog | Long banlist, including load-bearing, doing the work, the "worth" family, the whole game | Author's judgment. Many entries are common words that cannot be bare rules (section "Words rejected as bare rules") |
| [GOV.UK style guide][GOV] | Guidance | Words to avoid, with literal uses excepted: "leverage (unless in the financial sense)", "robust (unless talking about a sturdy object)", "key (unless it unlocks something)", "foster (unless it's children)". "Avoid using metaphors" because they "lead to slower comprehension" | No study cited on the page. Written for government content |
| [Microsoft Style Guide][MS] | Guidance | "Avoid idioms". "Avoid modifier stacks." "Avoid linking more than three phrases or clauses" with coordinate conjunctions | Written with localization in mind |
| [windbag][WB] | Tool, no evaluation seen | Comment rules. Reason markers ("because", "to avoid", "otherwise") veto the obvious-comment rule. Doc comments are exempt from it. `windbag: ignore[RULE_ID]`, `--new-only`. Rust, `\b` plus escaped phrase | Phrase lists are in config files I did not open. Its rules cover the checks in model section 3.1, and no mannered prose |
| [aislop rules][AIS] | Tool, no evaluation seen | `narrative-comment` flags restatement openers and step-by-step narration, and "Length alone is not flagged" | No phrase data on the page |
| [vale-signs-of-ai-writing][VAL] | Tool derived from Wikipedia | Regex tokens at three levels. CC BY-SA 4.0, which matters if lists are copied | "False positives are possible". The fetch tool did not return two files in full (NegativeParallelisms, Symbolism) |
| [WSC][WSC] | Tool, no evaluation of itself | 98 words, 83 phrases, 12 structural patterns; default long sentence is 30 words | Publishes no precision figures |
| [anti-ai-tell][AAT] | Tool, no false-positive figures | Regexes for parallelism, triads, openers, closers, attribution; uniform rhythm at sentence-length CV below 0.45 | "does not mean the text reads human" |
| [slop-guard][SG], [blog][SGB] | Tool, no error rates seen | Setup-resolution regexes; contrast pair `\b(\w+), not (\w+)\b`; pithy fragment definition | "calibrated for blog-length prose; longer texts will score lower". A contrast used once is acceptable. Agents could learn the rule boundaries |
| [deslop][DES] | Tool, no evaluation seen | Defaults: sentence CV 0.35, paragraph 120 words, 1 semicolon per paragraph, Flesch floor 40 | "This is a lint, not a classifier." "Regex-based detection is easy to evade." |
| [SlopSift rule catalog][SS], [repository][SSR] | Tool, no figures on the page | 70 rule descriptions, many needing a dependency parser. It lints comments in Rust files | "A lint is an editorial signal". Warns against comparing raw counts across files |
| [humanizer-lint][HUM] | Tool with a preliminary test | Failed 21 of 28 English human excerpts (Wilson 95% interval 56.6% to 87.3%) and flagged 3 of 3 AI samples | Author says not a full benchmark. It shows how a composite gate can fail |
| [Étincel][ETI] | Tool, self-reported | Pooled AUC: docs 0.735, memo 0.909, email 0.540 | Own corpus, not independently checked. The page gives no figure for code comments |
| DSK: `.agents/skills/deslopping/SKILL.md` in the workspace repository | Guidance, internal | "not just X, but Y", groups of three, "from X to Y", abstract metaphors, "Do not impose mechanical punctuation bans" | Team rule, with no evidence attached |

The windbag project I found covers comments only, and no project of that name covers Markdown prose.

Not found: any source naming "dial" or "knob" as a tell. "earns its keep" appeared only in a search snippet of a [DAIR.AI tutorial][DAI], and the opened page, which is gated, says only "figurative phrases may replace literal statements". So these entries rest on Malte's request. "Seam" has a count ([Matsuoka][HYP]) and a documented literal meaning ([Feathers via Fowler][SEAM]).

Wikipedia check: I did not find "false range" or "elegant variation" in the text I read. About 45,000 characters of the rendered page remained unread. The false-range rules are sourced from WSC, tropes.fyi and the deslopping skill.

### Measures of winding sentences

| Source | Label | Finding |
| --- | --- | --- |
| [Pitler and Nenkova][PIT] | Study, 30 Wall Street Journal articles, each rated by at least 3 college students | Against ratings: average words per sentence r = .16 (p = .39), maximum words per sentence r = .09 (p = .65), characters per word r = -.09 (p = .65). Average verb phrases per sentence r = +.42 (p = .02). Subordinate clauses r = +.34 (p = .07). Parse tree height r = -.06 (p = .74). Small sample of competent adult readers |
| [Frontiers in Psychology 2017][FRO] | Study, 64 students, German | Sentences with three nested dependencies "are judged as only marginally acceptable". Supports nesting as a cost. Other work cited in search results disputes the mechanism |
| [GOV.UK][GOV] | Guidance | "Check sentences with more than 25 words to see if you can split them". "Long sentences using semicolons should be broken up" |
| [Microsoft][MS] | Guidance | "more than a few commas" usually indicates a complex sentence. At most three linked phrases or clauses, preferably two |
| [textlint max-comma][TL] | Tool | Default maximum is 4 commas, so 5 or more is reported |
| [WSC][WSC] | Tool | 30 words default |
| [Flesch-Kincaid][FK] | Formula | FRE = 206.835 − 1.015(words/sentences) − 84.6(syllables/words). FKGL = 0.39(words/sentences) + 11.8(syllables/words) − 15.59. "They neglect between-reader differences and effects of content, layout and retrieval aids." |
| [ARI][ARI] | Formula | 4.71(characters/words) + 0.5(words/sentences) − 21.43. Needs no syllable count. The page gives no validation data |
| [Vale readability][VD] | Tool | Scoping below a paragraph gives no meaningful result. So formulas do not suit single comments |

Could not verify:

- American Press Institute comprehension figures (8 words near 100%, 14 words 90%, 43 words under 10%): second-hand only, in [blogs such as this one][APIB]. I found no original study. Do not cite these as evidence.
- Australian Style Manual "average of 15 words and no more than 25": seen in a search snippet; [the page][AUS] timed out twice.
- High correlation among readability formulas (minimum 0.94) in a [TensorFlow documentation study][TF]: seen in a search snippet; the PDF did not parse.
- Hemingway Editor thresholds: not stated in anything I opened.
- "meticulous" up 34.7-fold in [Liang et al.][LIA]: reported by anti-ai-tell. The abstract I opened does not state it.

Regexes from WSC, anti-ai-tell, slop-guard and Vale came through a summarizing fetch tool. Compare each with the source file before shipping.

## Preprocessing

All rules run after these steps. A rule's `strip` column says which text was removed.

1. **Extract prose.**
   - Rust: use a lexer, because `syn` drops ordinary comments (model section 3.6). Join consecutive line comments into one block. Remove `//`, `///`, `//!`, `/* */`. Remove fenced code in doc comments, SPDX and license headers, tool directives, and commented-out code.
   - Markdown: use a CommonMark parser. Keep text in paragraphs, list items and headings. Remove code blocks, HTML, front matter and link destinations. Treat each table cell as one unit, and skip sentence measures on tables.
2. **Strip `C` (code).** Replace inline code, intra-doc links and URLs with the one-word token `CODE`, so sentence shape and word counts stay usable.
3. **Strip `Q` (quoted).** Replace double-quoted spans of up to 200 characters, block quotes and single-word italics (a common way to mention a word) with `QUOTE`. A file that discusses slop still needs a path exemption, for example `docs/research/**`.
4. **Normalize.** Curly quotes and apostrophes to straight. No-break spaces to spaces. Runs of whitespace to one space. Windbag's approach of escaped phrases and `\b` carries over.
5. **Split sentences.** Boundaries: `[.!?]+["')\]]*\s+` when the next character is not lowercase and the preceding word is not in the abbreviation list (`e.g`, `i.e`, `vs`, `etc`, `cf`, `al`, `approx`, `No`, `Fig`); also paragraph breaks, list items, headings and table cells. Colons and semicolons are not boundaries. [deslop][DES] warns that simple splitters miscount, so sentence rules should stay at warn or metric until tested.

Regex notes:

- All patterns use Rust `regex` syntax: no lookaround and no backreferences. Where a context condition is needed, the rule has a second `except` pattern, tested on the same sentence.
- Patterns compile with `(?i)` unless they start with `(?-i)`.
- **In table cells, `\|` is the Markdown escape for `|`. Replace it before compiling.** No rule matches a literal pipe.
- `{N}`, `{ABS}` and `{list:name}` expand from the blocks in section "Macros and lists". A list expands to `\b(?:entry|entry)\b`.

## Rule table

Scope: `S` sentence, `P` paragraph, `F` file. Strip: `R` raw, `C` code stripped, `CQ` code and quoted text stripped. Every severity is a suggestion. I assigned block only where a rewrite is always possible and the phrase has almost no literal use in this kind of repository. All rules need a replay on real history before any block takes effect (model section 5.8). Sources marked own have nothing behind them.

| id | class | exact regex or computation | scope | strip | severity | source | false-positive note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| art-chatbot | artifact | `{list:chatbot}` | S | CQ | block | [WP], [VAL], [TRO] | "Would you like", "let me know" could be real text in a CLI's messages. Those are strings, which extraction excludes |
| art-cutoff | artifact | `\b(?:as of\|up to) my last (?:knowledge\|training) (?:update\|cut-?off)\b` | S | CQ | block | [WP] | Almost none |
| art-citation | artifact | `\b(?:oaicite\|turn0search\d+)\b\|utm_source=chatgpt\.com` | F | R | block | [SS], [WP] | Raw scan, as these sit in URLs. A doc about these artifacts needs an exemption. The exact UTM value is from memory; WP names ChatGPT UTM parameters, and I did not read the value there |
| art-placeholder | artifact | `(?-i)\bINSERT_[A-Z_]+\b\|\b\d{4}-XX-XX\b\|\[(?:Describe\|Insert\|Add\|Your) [^\]]{0,80}\]` | S | C | block | [WP] | Template files. Exempt by path |
| meta-load-bearing | mannered | `\bload[- ]bearing\b` | S | CQ | block | [ISS], [HYP], [TRO], [CLA], Malte | A literal building or structural-simulation text. Allow per repository. A search summary of an unopened [Hacker News thread](https://news.ycombinator.com/item?id=49774665) says some commenters defend the word |
| meta-seam | mannered | match `\bseams?\b`; except `\b(?:uv\|texture\|mesh\|weld\|welded\|sewing\|test\|testing\|link\|object\|preprocessor)\s+seams?\b` | S | CQ | warn | [HYP], Malte; literal sense [SEAM]; except list own | Feathers defines a seam as "a place where you can alter behavior in your program without editing in that place". A repository that uses that term adds `seam` to its glossary allow list. Needs a context condition |
| meta-seam-phrase | mannered | `\b(?:clean\|natural\|right\|real\|narrow\|thin\|sharp\|hard\|soft\|obvious\|load[- ]bearing)\s+seams?\b` | S | CQ | block | Malte; own | Modifiers show the word is used as a figure. "hard seam" could be a graphics term |
| meta-earns-keep | mannered | `\bearn(?:s\|ed\|ing)?\s+(?:its\|their\|your\|our\|his\|her)\s+(?:keep\|place\|spot\|seat\|stripes)\b` | S | CQ | block | Malte; [DAI] snippet only | Almost none in technical text |
| meta-dial | mannered | `\b(?:dial\|knob\|lever)s?\s+(?:worth\|to)\s+(?:turn\|turning\|pull\|pulling\|twist\|twisting)\b\|\b(?:turn\|turning\|pull\|pulling)\s+(?:the\|this\|that\|a\|these\|those)\s+(?:dial\|knob\|lever)s?\b` | S | CQ | block | Malte; family extension own | Literal UI or game controls: turn the dial on a control panel. Needs a path or glossary exemption there |
| meta-worth | mannered | `\bworth\s+(?:noting\|naming\|knowing\|mentioning\|calling out\|flagging\|pointing out\|sitting with\|asking\|examining\|considering\|exploring\|drawing\|making\|talking about)\b` | S | CQ | warn | [HYP], [CLA], [TRO] | "worth considering" can be a real recommendation. Bare `worth` is excluded because of "worth 3 points" |
| meta-stock | mannered | `{list:meta_stock}` | S | CQ | warn | see list | See per-entry notes in the list |
| meta-lives | mannered | `\bwhere\s+(?:the\s+)?[\w-]+(?:\s+[\w-]+)?\s+(?:actually\|really\|truly)\s+(?:lives?\|sits?)\b` | S | CQ | warn | [TRO] (regex own) | "where the file actually lives" is literal enough. Bare "lives" is excluded because of Rust lifetimes |
| meta-wearing | mannered | `\bdressed\s+(?:up\s+)?as\b\|\bwearing\s+(?:a\|an\|the)\s+[\w-]+\s+(?:costume\|hat\|mask\|disguise)\b` | S | CQ | warn | [HYP] (regex own) | Bare "wearing" is excluded for wear leveling and game characters |
| meta-think-of | mannered | `\bthink of (?:it\|this\|that\|them) (?:as\|like)\b\|\bimagine a world\b` | S | CQ | warn | [TRO] | A deliberate analogy in tutorials |
| meta-adverb | mannered | `\b(?:quietly\|genuinely)\b` | S | CQ | warn | [WP], [TRO], [SS], [ISS] | "quietly" for a process with no output: use "silently" or say what happens |
| meta-adverb-weak | mannered | `\b(?:truly\|really\|honestly\|essentially\|precisely\|actually)\b` per 1,000 words | F | CQ | metric | [SS], [HYP], [ISS], [TRO] | Common English. "precisely" can be a claim about accuracy |
| meta-candor | mannered | `\b(?:to be (?:transparent\|honest\|clear)\|i'?ll be honest\|the honest (?:version\|answer) is)\b` | S | CQ | warn | [SS], [CLA] | Almost none in docs |
| meta-question-frag | mannered | `(?:^\|[.!?]\s)the\s+[\w-]+(?:\s+[\w-]+)?\?\s+\w` | P | CQ | warn | [TRO] (regex own) | A real question in FAQ docs |
| meta-pithy | mannered | sentence has at most 6 words and matches `,\s+(?:but\|yet\|and\|not\|or)\b` | S | CQ | warn | [SGB] | Short factual sentences: "Reads, not writes." |
| meta-agency | mannered | `\b(?:the\|this\|that)\s+(?:approach\|design\|change\|pattern\|code\|function\|module\|type\|system)\s+(?:knows\|wants\|cares\|refuses\|insists\|understands\|believes\|hopes)\b` | S | CQ | warn | [SS] describes it; regex own | "The type knows its length" is a common shorthand |
| meta-concrete-verb | mannered | `\b(?:earn\|carry\|bear\|wear\|ride\|anchor\|stitch\|weave\|sharpen\|unlock\|untangle)\w*\s+(?:the\|its\|this\|that\|their\|a)\s+(?:weight\|keep\|load\|complexity\|tension\|argument\|insight\|idea\|burden\|value)\b` | S | CQ | metric | own | "carry the value" is literal in code. Replay before raising severity |
| meta-label | mannered | `\bthe\s+[\w-]+\s+(?:paradox\|trap\|fallacy\|illusion)\b` | S | CQ | metric | [TRO] (regex own) | Established names such as "the Monty Hall paradox" |
| neg-not-only | contrast | `\bnot\s+(?:just\|only\|merely\|simply)\b[^.!?]{1,80}?\bbut\b` | S | CQ | block | [WP], [AAT], [WSC], [WAPO], Malte | "This not only returns X but also sets Y" is factual, and "returns X and sets Y" says the same. Report once if `neg-bare` also matches |
| neg-setup-flip | contrast | A: `\b(?:this\|that\|these\|those\|it\|they\|we)\s+(?:isn't\|aren't\|wasn't\|weren't\|doesn't\|don't\|didn't\|hasn't\|haven't\|won't\|can't\|couldn't\|shouldn't\|is\s+not\|are\s+not\|was\s+not\|were\s+not\|does\s+not\|do\s+not\|did\s+not\|has\s+not\|have\s+not\|will\s+not\|cannot\|could\s+not\|should\s+not)\b.{0,80}[.;:,]\s*(?:it's\|they're\|that's\|he's\|she's\|we're\|it\s+is\|they\s+are\|that\s+is\|this\s+is\|these\s+are\|those\s+are\|he\s+is\|she\s+is\|we\s+are\|what's\|what\s+is\|the\s+real\|the\s+actual\|instead\|rather)`. B: `\b(?:it's\|that's\|this\s+is\|they're\|he's\|she's\|we're)\s+not\b.{0,80}[.;:,]\s*(?:it's\|they're\|that's\|he's\|she's\|we're\|it\s+is\|they\s+are\|that\s+is\|this\s+is\|these\s+are\|those\s+are\|what's\|what\s+is\|the\s+real\|the\s+actual\|instead\|rather)` | P | CQ | block | [SG], [WP], [TRO], Malte | Spans sentences, so paragraph scope. Matches factual text: "It does not allocate. That is why it can run in a signal handler." and diagnoses such as "This is not a race, it is a stale read." Likely the noisiest block rule. Lower to warn if replay shows that |
| neg-not-about | contrast | `\bn(?:ot\|'t)\s+(?:just\|only\|merely\|simply\|about)\s+[^.!?]{1,80}?[,;.:—–-]\s*(?:it's\|it\s+is\|this\s+is\|that's\|they're\|but\s+rather)\b` | P | CQ | warn | [WSC] | Partly overlaps `neg-setup-flip`. Report once |
| neg-bare | contrast | `\bnot\s+(?:a\s+\|an\s+\|the\s+)?[\w-]+(?:\s+[\w-]+){0,4},?\s+but\s+` | S | CQ | warn | [WP], Malte (regex own) | "does not panic but returns an error" is literal. Rewrite is "returns an error" |
| neg-x-not-y | contrast | `\b(\w+), not (\w+)\b` counted; fire when at least 2 in a paragraph or 3 per 1,000 words | P, F | CQ | metric, warn at limit | [SGB], [SS] | "Returns bytes, not characters." is precise API documentation, so a single use must not fire. [SGB] also treats one use as acceptable |
| neg-no-no-just | contrast | `\bno\s+[\w-]+(?:\s+[\w-]+){0,3}[,.;]\s*no\s+[\w-]+(?:\s+[\w-]+){0,3}[,.;]\s*(?:just\|only\|simply)\b` | P | CQ | warn | [WP], [VAL], [CLA] | Feature lists: "no allocation, no locks, only atomics." is factual |
| neg-not-not | contrast | `(?:^\|[.!?]\s)not\s+[^.!?]{1,40}\.\s+not\s+[^.!?]{1,40}\.\s+\w` | P | CQ | warn | [TRO] | Rare in docs |
| neg-list | contrast | `\b(?:does\|do\|is\|are)(?:\s+not\|n't)\b[^.!?]{0,60}[.!?]\s+(?:it\|they\|this)\s+(?:does\|do\|is\|are)(?:\s+not\|n't)\b` | P | CQ | metric | [SS] (regex own) | API docs list non-guarantees on purpose. Stay at metric in `///` |
| neg-rather-than | contrast | `\brather\s+than\b` per 1,000 words; warn above 3 | F | CQ | metric, warn at limit | [WP] | Often the precise phrase for a chosen alternative. Never per occurrence |
| neg-confused | contrast | `\bshould\s+not\s+be\s+confused\b` | S | CQ | metric | [WP], which calls it less reliable | "should not be confused with `Foo`" is valid disambiguation |
| neg-seesaw | contrast | `(?:^\|[.!?]\s)while\b[^.!?]{5,120}[.!?]\s+however\b` | P | CQ | metric | [SS] (regex own) | Weak. Real trade-offs read this way |
| but-adj | contrast | `\b(?:simple\|small\|subtle\|modest\|quiet\|boring\|unglamorous\|narrow\|minor\|easy\|ugly\|plain)\s+but\s+(?:powerful\|effective\|important\|crucial\|real\|useful\|essential\|necessary\|meaningful\|significant\|critical\|vital\|elegant)\b` | S | CQ | warn | Malte; own | "easy but useful" could be literal, rewrite is short |
| but-balanced | contrast | sentence has at most 14 words and exactly one `, but `, and word counts of both sides differ by at most 2 | S | CQ | warn | Malte; own | Balanced factual sentences: "It reads the file, but it does not parse it." Replay before relying on it |
| but-density | contrast | `,\s+but\b` per 100 sentences | F | CQ | metric | Malte; own | Bare "but" is core English, so no per-occurrence rule. Compare with the repository's baseline only |
| range-double | range | `\bfrom [^,.;!?]{2,40} to [^,.;!?]{2,40}, (?:and )?from [^,.;!?]{2,40} to\b` | S | CQ | warn | [WSC], [TRO] | Double conversions described in prose |
| range-triple | range | `\bfrom\s+[\w-]+(?:\s+[\w-]+){0,2}\s+to\s+[\w-]+(?:\s+[\w-]+){0,2}\s+to\s+[\w-]+` | S | CQ | warn | [TRO] (regex own) | Paths: "from A to B to C" in a routing description |
| range-abstract | range | `\bfrom\s+(?:[a-z]+\s+){0,2}[a-z]+(?:ion\|ment\|ity\|ness\|ance\|ence\|ship\|ism)\s+to\s+(?:[a-z]+\s+){0,2}[a-z]+(?:ion\|ment\|ity\|ness\|ance\|ence\|ship\|ism)\b` | S | CQ | metric | [DSK]; own | Bare "from X to Y" is excluded because of "from 1 to 10" and "from `u32` to `u64`". Abstract-noun endings are a proxy. "from development to production" still fires |
| triad-doc | triad | `\b\w+(?:\s\w+){0,2},\s+\w+(?:\s\w+){0,2},\s+and\s+\w+` counted; fire when count ≥ 3 and count/paragraphs > 0.5; ignore a match containing `CODE` | F | CQ | metric, warn at limit | [AAT], [WP] | Real enumerations are common in docs. Never per occurrence. Ignoring `CODE` matches is own |
| triad-puffery | triad | `\b{list:puffery},\s+{list:puffery},\s+(?:and\|or)\s+{list:puffery}` | S | CQ | warn | [WP] (list own) | "fast, safe, and portable" may be a true list of properties. Ask for evidence |
| count-noun | counting | match `\b{N}\s+(?:(?:key\|main\|core\|big\|important\|major\|distinct\|separate\|different\|specific\|critical\|quick\|simple\|primary\|central)\s+)?{ABS}\b`; except `\b(?:exactly\|at most\|at least\|up to\|only\|every\|per)\s+{N}\b` | S | CQ | warn | [TRO], [CLA], Malte | "three layers" can name a real architecture. The noun list excludes concrete counts: threads, retries, bytes, fields. "exactly two" states a fact, hence the except |
| count-found | counting | `\b(?:we\|i)\s+(?:found\|identified\|saw\|noticed\|spotted\|counted\|uncovered\|discovered)\s+(?:[\w-]+\s+){0,2}?(?:\d+\|two\|three\|four\|five\|six\|seven\|eight\|nine\|ten\|several\|many)\s+[\w-]+` | S | CQ | warn | Malte (regex own) | Research reports with real tallies: a number that a reader needs is fine, so this may need a docs exemption |
| count-there-are | counting | `\bthere\s+(?:are\|were)\s+(?:only\s+)?(?:{N}\|\d+)\s+{ABS}\b` | S | CQ | warn | [TRO]; regex own | "There are two cases" is not matched, as "cases" is outside `{ABS}` |
| count-announce | counting | sentence has at most 8 words and matches `^(?:the\s+)?{N}\s+(?:[\w-]+\s+){0,5}[\w-]+[.:]$` | S | CQ | warn | [TRO] | Introductions to a real list: "Two modes exist:". This rule fires on that too. Pairs with `count-mismatch` |
| count-ordinal | counting | `\bthe\s+(?:first\|second\|third\|fourth\|fifth)\s+(?:wall\|thing\|point\|reason\|problem\|issue\|lesson\|takeaway\|trap\|mistake)\b`, at least 2 in a paragraph | P | CQ | warn | [TRO] | Procedures use "first" and "second" with "step", which is not in the list |
| count-mismatch | counting | a sentence with a `{N}` number ends in `:` and the next block is a list with a different item count | P | C | warn | own | A correctness check. Nested lists need a top-level count |
| count-density | counting | matches of `count-noun`, `count-found`, `count-there-are`, `count-announce` per 1,000 words | F | CQ | metric | Malte; own | Reference data documents will rank high |
| count-tally | counting | `\b\d+\s+(?:findings?\|issues?\|items?\|problems?\|things?\|points?)\b` | S | CQ | metric | Malte; own | "3 items" in a queue or an API doc is a fact |
| stock-throat | stock phrase | `{list:throat}` | S | CQ | warn | [AAT], [VAL], [CLA], [SG], [WP] | "it is important to note" before a real safety warning: delete the phrase and keep the warning |
| stock-opener | stock phrase | at sentence start, `^(?:in today's\s+[\w\s-]*(?:world\|landscape\|era\|age)\|in the (?:ever-)?evolving\|at its core\|when it comes to\|from the moment (?:you\|it\|they\|we)\|this is where\b.{0,40}\bcomes in)` | S | CQ | warn | [AAT], [CLA] | "At its core" may be literal for a CPU core or a core module. Rare |
| stock-closer | stock phrase | at paragraph start, `^(?:in conclusion\|in summary\|to sum up\|all in all\|at the end of the day\|in closing\|wrapping up\|to conclude)\b` | P | CQ | warn | [AAT], [TRO] | A real summary section. Exempt headings |
| stock-transition | stock phrase | `^(?:moreover\|furthermore\|additionally\|notably\|crucially\|ultimately)\b` per 100 sentences | F | CQ | metric | [AAT], [SS] | [WP] lists these in isolation as ineffective. [VAL]'s "however" and "therefore" are excluded: those state real logic |
| stock-scaffold | stock phrase | `\bhere'?s\s+(?:the\s+(?:thing\|kicker\|catch\|twist\|deal)\|where\s+it\s+gets\|what\s+(?:makes\|matters))\b\|\blet'?s\s+(?:dive\|delve\|break\s+(?:this\|it)\s+down\|unpack\|explore)\b\|\bthe\s+key\s+is\b\|\bkey\s+takeaways?\b\|\bin\s+this\s+(?:section\|article\|post\|guide),?\s+(?:we'?ll\|we\s+will)\b` | S | CQ | warn | [TRO], [CLA], [SS] | Tutorials may use "let's" in a plain sense. Only the listed verbs fire |
| stock-signpost | stock phrase | `\b(?:this\|the)\s+(?:page\|section\|guide\|article\|note)\s+(?:explains\|lists\|covers\|describes\|shows\|says\|outlines\|walks\s+you\s+through)\b\|\bthis\s+(?:article\|blog\s+post\|post\|essay\|guide)\s+(?:aims\|seeks)\s+to\b` | S | CQ | metric | [VAL], [WSC] | "This section lists the flags" is normal documentation and may be needed |
| stock-significance | stock phrase | `{list:significance}` | S | CQ | warn | [WP], [VAL], [CLA] | Low in technical text. "focal point" is literal in graphics |
| stock-copula | stock phrase | `\b(?:serves?\|stands?)\s+as\s+(?:a\|an\|the)\b` | S | CQ | warn | [WP], [SS], [AAT] | "serves as a proxy" is near-literal. The rest of the WP list ("represents a", "maintains a", "features", "offers", "marks", "functions as", "operates as") is rejected because type docs use them literally |
| stock-participle | stock phrase | `,\s+(?:further\s+\|thereby\s+\|ultimately\s+)?(?:highlighting\|underscoring\|showcasing\|reflecting\|emphasi[sz]ing\|demonstrating\|signall?ing\|illustrating\|cementing\|solidifying\|reinforcing\|exemplifying\|epitomizing\|symbolizing\|embodying\|heralding\|fostering\|cultivating)\b` | S | CQ | warn | [WSC], [WP], [REI] | "signaling" and "reflecting" are literal in code: ", signaling the waiting thread". Add `except` `\bsignall?ing\s+(?:the\|a)\s+(?:thread\|task\|waiter\|process\|condvar)\b` (own). `ensuring` and `contributing to` are metric only |
| stock-tail-rate | stock phrase | `,\s+[a-z]{3,}ing\b` per 100 sentences; ignore `including`, `using`, `following`, `according`, `assuming`, `depending`, `given` | F | CQ | metric | [REI]; computation own | A proxy with no tagger. [REI] measured with a tagger, on other registers |
| stock-attribution | stock phrase | `\b(?:studies\s+(?:show\|suggest\|indicate)\|experts\s+(?:say\|agree\|believe\|argue)\|research\s+(?:shows\|suggests\|indicates)\|many\s+(?:critics\|observers\|analysts)\s+(?:argue\|believe\|note)\|industry\s+reports\s+suggest\|it\s+is\s+widely\s+(?:believed\|acknowledged\|recognized)\|observers\s+have\s+cited)\b` | S | CQ | warn | [AAT], [WP], [DSK] | Fine when followed by a citation. Add `except` for a Markdown link in the same sentence (own) |
| stock-promo | stock phrase | `\b(?:seamless(?:ly)?\|cutting[- ]edge\|game[- ]changing\|groundbreaking\|all[- ]in[- ]one\|world[- ]class\|best[- ]in[- ]class\|unprecedented\|blazing(?:ly)?\s+fast)\b` | S | CQ | warn | [WP], [TRO], [CLA], [ETI]; "world-class", "best-in-class", "blazingly fast" own | "seamless" is literal for texture tiling and looped audio. Add per-repo allow |
| stock-challenge | stock phrase | `\bdespite\s+(?:these\|its\|the\|this)\s+(?:challenges?\|limitations?)\b\|\bfuture\s+outlook\b` | S | CQ | warn | [WP], [TRO] | WP: the issue is the rigid formula, "not simply the mention of challenges" |
| stock-disclaimer | stock phrase | `\bwhile\s+specific\s+details\s+are\s+(?:limited\|scarce)\b\|\bnot\s+widely\s+(?:available\|documented\|disclosed)\b\|\bbased\s+on\s+available\s+information\b` | S | CQ | warn | [WP] | "based on available information" can describe an estimator. Comment hedging is otherwise in model section 3.1 |
| stock-matters | stock phrase | `\b(?:and\s+)?(?:this\|that\|it)\s+matters[.!]\|\bbecause\s+it\s+matters\b\|\bwhy\s+this\s+matters\b` | S | CQ | warn | [CLA], [WP] | Bare "matters" is rejected: "still matters" is Malte's own literal replacement for "earns its keep" |
| stock-totalizing | stock phrase | `\bthat'?s\s+the\s+(?:whole\|entire)\s+(?:game\|point\|ballgame)\b\|\bthe\s+only\s+thing\s+that\s+matter(?:s\|ed)\b` | S | CQ | warn | [CLA] | "the whole game" alone is not matched, as it can be literal in game code |
| stock-reflective | stock phrase | `{list:reflective}` | S | CQ | warn | [CLA] | First-person discovery has little place in comments. Almost none |
| stock-stakes | stock phrase | `\bthe\s+(?:gap\|line\|difference)\s+will\s+(?:be\|become)\s+(?:harder\|more\|clearer)\b\|\bthe\s+reckoning\s+will\s+come\b` | S | CQ | metric | [CLA] | Rare |
| vocab-strong | vocabulary | `{list:vocab_strong}` | S | CQ | warn | [KOB], [JUZ], [WP], [VAL] | Dated entries: "delve" declined by 2025. No code meaning, except Apache Tapestry as a product name |
| vocab-context | vocabulary | each row of the `homonyms` list: match, then except | S | CQ | warn | [GOV], [WP], [DSK], [CLA]; regexes own | Needs a context condition. See the list |
| vocab-density | vocabulary | at least 3 distinct `vocab_weak` words in one paragraph, or at least 3 occurrences per 200 words | P, F | CQ | metric, warn at limit | [WP], [DES], [KOB] | WP: one or two may be coincidence. Limit is [DES]'s `overused_word_threshold = 3` with `min_words_for_density = 200` |
| vocab-gov | vocabulary | `{list:gov_avoid}` | S | CQ | metric | [GOV] | Government guidance. "deliver", "progress", "focus", "impact" and "transform" are left out because they are literal in code |
| fmt-emdash | format | `—` per 500 words; fire at 14 or more, with at least 6 in the file | F | C | metric | [DES], [WAPO] | [DSK]: "Do not impose mechanical punctuation bans." [CLA] bans them outright. Density only |
| fmt-emoji-bullet | format | a list item or heading starts with a character in `\p{Extended_Pictographic}` | P | C | warn | [WP], [DES] | Status tables in reports. The workspace's own implementation rule uses a stop sign for blockers |
| fmt-bold-bullets | format | at least 3 consecutive list items start with a strong span followed by `:` or `.` | P | C | metric | [WP], [TRO], [SG] | A common and useful format for definitions |
| fmt-title-case | format | heading of 4 or more words in which at least 80% of words of 4 or more letters start uppercase, ignoring `CODE` | P | C | metric | [WP], [TRO] | Proper names. Some projects use title case by policy |
| fmt-mixed-quotes | format | straight and curly double quotes both occur in the file (run before normalizing) | F | C | metric | [SS], [WP] | Pasted quotations |
| fmt-hrule | format | at least 3 `---` thematic breaks per 1,000 words | F | R | metric | [SG], [CLA] | Front matter is removed first |
| len-words | sentence | words in the sentence; `CODE` counts as 1 | S | CQ | metric above W1, warn above W2 | [GOV], [WSC], [TL] | Literal lists in prose. [PIT] found no link to reader ratings. Skip tables and headings |
| len-mean | sentence | mean words per sentence, at least 5 sentences | F | CQ | metric | [AUS] unverified | Short comments have too few sentences |
| len-chars | sentence | characters in the sentence | S | CQ | metric | [TL] snippet | Redundant with `len-words`. The default of 100 characters was seen in a search snippet only |
| clause-commas | sentence | count `,` | S | CQ | warn at C1 | [TL], [MS] | Lists of items. Number groups (`1,000`) are removed first |
| clause-coord | sentence | count `\b(?:and\|or\|but\|nor\|yet)\b`; subtract 1 for each `triad-doc` match | S | CQ | warn at D1 | [MS] | The count mixes noun lists with clause links. Microsoft's limit covers phrases and clauses, so this still fits |
| clause-markers | sentence | count `{list:clause_markers}` | S | CQ | metric | own; [PIT] found the opposite direction for adults | Technical conditions often need `if` and `because`. Never block. [WB] treats `because` and `so that` as signs of a useful comment |
| clause-tails | sentence | count `,\s+(?:which\|where\|whose\|whereby)\b` plus `stock-tail-rate` matches | S | CQ | warn at T1 | [REI]; own | One tail is normal |
| clause-semicolons | sentence | count `;` | S | C | warn at 2 | [GOV], [DES] | Rust code is already stripped |
| nest-depth | sentence | maximum depth of `(`, `[`, `{` after stripping | S | C | warn at 2 | [FRO] supports nesting cost; computation own | Math and citations |
| nest-asides | sentence | count of parenthetical spans plus pairs of dashes | S | CQ | warn at A1 | [SS] describes it; limit own | Abbreviations in parentheses. Ignore spans of 1 or 2 words (own) |
| nest-relative | sentence | `\b(?:that\|which\|who)\s+[\w-]+(?:\s+[\w-]+){0,3}\s+(?:that\|which\|who)\b` | S | CQ | metric | [FRO]; regex own | Rough proxy for center embedding. Misses most real cases and matches some non-nested ones. A parser is needed for accuracy |
| nest-late-subject | sentence | sentence starts with `^(?:while\|although\|though\|because\|since\|given\|despite\|if\|when\|whereas\|assuming\|in order to)\b`, and first comma comes after more than L1 words, or there is no comma | S | CQ | warn | [FRO] by analogy; [SS] describes subject far from verb; own | Short leading conditions in `# Panics` sections are excluded by the word limit |
| nest-prep-chain | sentence | `(?:\b(?:of\|in\|on\|for\|to\|with\|by\|from\|at\|about\|over\|under\|between\|through)\s+(?:[\w-]+\s+){1,3}){4,}` | S | CQ | warn | own; [MS] on stacks is related | Long titles and place names |
| wind-composite | sentence | words > W1 and at least 2 of: commas ≥ 3; `clause-coord` ≥ 3; `clause-markers` ≥ 3; `nest-depth` ≥ 1; `clause-tails` ≥ 2 | S | CQ | warn; candidate for block after replay | own, combining [GOV], [MS], [TL] | This is the rule that targets "winding", and length alone does not trigger it. Untested |
| read-ari | readability | 4.71(characters/words) + 0.5(words/sentences) − 21.43, on at least 100 words | F | CQ | metric | [ARI], [VD] | No syllable count, which suits text with identifiers. `CODE` must be excluded from the character count. Not for single comments |
| read-flesch | readability | FRE formula above, on at least 100 words; syllables by vowel-group count | F | CQ | metric | [FK], [DES] (floor 40) | Technical terms lower the score |
| para-words | paragraph | words per paragraph | P | CQ | warn above 120 | [DES] | Long Markdown explanation may be fine |
| rhythm-cv | rhythm | population stdev / mean of words per sentence, for sentences over 2 words, in a file with at least 8 such sentences | F | CQ | metric | [DES] (0.35), [AAT] (0.45, at least 6) | These tools disagree. [HUM] saw high failure on human text with rhythm rules included. [WP] says one recent model (GPT-6) uses "shorter sentences around a strict 8–20 word limit", which a `len-words` limit will not catch |
| rhythm-adjacent | rhythm | 3 adjacent sentences whose lengths differ by at most 3 words | P | CQ | metric | [HUM] | Common in short procedures |
| rhythm-starters | rhythm | at least 3 sentences in a paragraph start with the same word; ignore `The`, `A`, `CODE` | P | CQ | warn | [HUM], [TRO]; ignore list own | Parameter lists. `# Errors` sections repeat "Returns" on purpose |
| rhythm-staccato | rhythm | at least 4 consecutive sentences of at most 6 words | P | CQ | warn | [CLA], [HUM] threshold | Procedures and terse comments |
| rhythm-ngram | rhythm | the same 6-word sequence occurs at least 3 times in a file | F | CQ | metric | [SG], [HUM]; numbers own | Boilerplate docs such as "Returns an error if the" |
| cluster-paragraph | composite | at least 3 distinct warn rules fire in one paragraph | P | CQ | warn | [SS], [HUM], [WP] | A better signal than a single word, according to WP. Limit from [HUM]. Unmeasured for code comments |

## Default limits for sentence measures

**All values are placeholders.** None has been replayed on real code. Replace them after a replay on the repository's history, using the percentile that the team accepts.

| Limit | Meaning | Placeholder | Basis |
| --- | --- | --- | --- |
| W1 | words per sentence, metric and `wind-composite` | 25 | [GOV]: check above 25 |
| W2 | words per sentence, warn | 30 | [WSC] default |
| none | block on words per sentence | none | [PIT]: no link to ratings |
| C1 | commas per sentence, warn | 5 | [TL] reports 5 or more |
| D1 | coordinating conjunctions per sentence, warn | 4 | [MS]: no more than three links |
| T1 | trailing clauses per sentence, warn | 2 | own |
| A1 | asides per sentence, warn | 2 | own |
| L1 | words before the first comma after a leading subordinator | 12 | own |
| first sentence | words in the first sentence of a doc comment | 15 | already in model section 3.6 |
| CV | sentence-length CV in a file, metric | below 0.35 | [DES]; [AAT] uses 0.45 |
| min sample | sentences for file-level rhythm | 8 | [DES], [HUM] |
| min words | words for file-level density and readability | 100, or 200 for vocabulary density | [DES]; 100 own |
| ARI | metric only, no limit | none | No evidence for a limit |
| FRE | metric only, floor if wanted | 40 | [DES] |

Report density per 1,000 words of prose, because long files otherwise score worse ([SG] blog). Check added prose only, as [windbag][WB]'s `--new-only` does, so a new rule does not fail on old text.

## Context conditions and stripping

Every rule except the raw scans runs after code stripping. Words in code spans, paths and identifiers must never fire.

| Class | Code stripped | Quotes stripped | Context condition |
| --- | --- | --- | --- |
| Artifacts | Except `art-citation`, which is raw | Yes, except placeholders | Path exemption for templates and docs about slop |
| Mannered | Yes | Yes, because a text may discuss a phrase | Glossary allow list for `seam`, `dial`, `knob`, `lever`, `seamless` |
| Contrast | Yes | Yes | Use paragraph scope across sentences. `neg-x-not-y` and `neg-rather-than` count density only |
| Range | Yes | Yes | Exclude numbers and `CODE` |
| Triad | Yes | Yes | Exclude matches that contain `CODE`. Density only for `triad-doc` |
| Counting | Yes | Yes | Abstract nouns only. Except "exactly", "at most" and similar |
| Stock phrases | Yes | Yes | Exempt headings for closers. Except a linked citation in `stock-attribution` |
| Vocabulary | Yes | Yes | Homonyms need a match and an except |
| Format | Yes | No | None |
| Sentence, rhythm | Yes | Yes | Skip tables, headings and lists of fewer than 2 sentences |

### Words rejected as bare rules

Do not match these alone. Each has a literal meaning in code, or the source says it fails in isolation. Listed by source:

- **[Claudisms][CLA]:** hold, carry, moves, points, turns, lives, shape, surface, names, real, engine, compounds, useful, honest, mature, settled, navigate, harness, unpack, landscape.
- **[WP]:** additionally, consequently, notably (WP calls these ineffective); key, challenge, clearer, practical, steady, matters, represents, maintains, features, offers, marks, enhance, valuable; causal, empirical, correlate (WP lists them for Grok; they are common in technical writing).
- **[KOB] common set:** across, within, particularly, insights, comprehensive, exhibited. Too common alone. Use in `vocab_weak` only.
- **[JUZ]:** aligns (memory alignment, UI), comprehending.
- **[GOV]:** deliver, deploy, focus, impact, land, progress, promote, transform, counter, commit, agenda, advance, initiate. These are often literal in software.
- **Own:** thread, bridge, pipeline, anchor, gate, guardrail, source of truth, first-class, footgun, orchestrate, bottleneck, hook. Software terms, some used in the Smog model itself.

## Macros and lists

Format in the list blocks: `pattern ;; replacement or action ;; source`. The pattern is a regex fragment. `{list:name}` expands to `\b(?:pattern|pattern)\b`. All entries need a review date when imported. Copied Wikipedia-derived text falls under CC BY-SA.

```text
{N}   = (?:two|three|four|five|six|seven|eight|nine|ten)
{ABS} = (?:things?|ways?|reasons?|points?|takeaways?|lessons?|items?|issues?|problems?|findings?|questions?|factors?|limits?|constraints?|pillars?|principles?|themes?|areas?|aspects?|concerns?|walls?|ideas?|insights?|mistakes?|layers?|parts?|traps?|gaps?)
```

`chatbot`:

```text
i hope this helps ;; delete ;; WP, VAL
of course! ;; delete ;; WP, VAL (builder must not append \b after !)
certainly! ;; delete ;; WP, VAL (same)
you're absolutely right ;; delete ;; WP, VAL
would you like (?:me to|it expanded) ;; delete ;; WP, VAL
is there anything else ;; delete ;; WP, VAL
let me know if you ;; delete ;; WP, VAL
more detailed breakdown ;; delete ;; WP, VAL
here is a (?:draft|detailed) article ;; delete ;; VAL
as an ai(?: language)? model ;; delete ;; VAL, WSC
i'm sorry, i can't ;; delete ;; VAL
feel free to ask ;; delete ;; VAL
great question ;; delete ;; WSC, CLA
i love that you asked ;; delete ;; CLA
if you want, i can ;; delete ;; SG
so,? to answer your question ;; delete ;; TRO
```

`meta_stock`:

```text
heavy lifting ;; name the operation ;; CLA
(?:is |are )?doing (?:all |most of )?the (?:work|lifting) here ;; name the actor and the action ;; CLA
carr(?:y|ies|ying) the (?:argument|weight) ;; supports the argument, or name the effect ;; CLA
hold(?:s|ing)? the [\w-]+ up ;; name the dependency ;; CLA
(?:rich )?tapestry ;; delete, or say what is combined ;; WP, VAL. Product name Apache Tapestry
testament to ;; shows ;; WP, VAL, CLA
(?:intricate|delicate|complex|careful) dance ;; name the interaction ;; WSC
indelible mark ;; state the effect ;; WP
deeply rooted ;; old, or established since ;; WP
set(?:s|ting)? the stage for ;; prepares ;; WP
pav(?:e|es|ing) the way ;; allows ;; CLA
shed(?:s|ding)? light on ;; explains ;; CLA
lean(?:s|ing)? into ;; uses more ;; CLA
double[- ]click(?:ing)? on ;; examine. Literal in GUI docs ;; CLA
hit(?:s|ting)? hardest|lands? hardest|strikes? hardest ;; affects most ;; CLA
hit a nerve|struck a (?:nerve|chord) ;; delete ;; CLA
stuck with me|stayed with me ;; delete ;; CLA
rides? along ;; is passed with ;; CLA
hands? it back ;; returns it ;; CLA
different physics ;; different rules. Literal in physics engines ;; CLA
throughline ;; main point ;; CLA
pressure[- ]test(?:s|ed|ing)? ;; test. Literal in hardware docs ;; CLA
right[- ]siz(?:e|ed|ing) ;; resize ;; CLA
north star|true north ;; goal ;; CLA
strategic imperative ;; requirement ;; CLA
paradigm shift ;; change ;; CLA
game[- ]chang(?:er|ing) ;; state the effect ;; TRO, CLA
table stakes ;; required ;; LAZ
at the end of the day ;; delete ;; CLA, AAT
the tell ;; the sign ;; CLA
navigat(?:e|es|ing) the (?:complexities|challenges|landscape|world) ;; handle ;; CLA, DES
moving parts ;; components ;; own
under the hood ;; internally ;; own
sharp edges? ;; state the hazard. No source found ;; own
paper(?:s|ed|ing)? over ;; hides ;; own
low[- ]hanging fruit ;; easy changes ;; own
silver bullet ;; complete solution ;; own
mov(?:e|es|ing) the needle ;; changes the result ;; own
boil(?:s|ing)? the ocean ;; do too much ;; own
elephant in the room ;; state the problem ;; own
bright line ;; clear rule ;; own
bridg(?:e|es|ing) the gap ;; connects ;; own
clos(?:e|es|ing) the loop ;; finishes ;; own
```

`throat`:

```text
it'?s worth (?:noting|mentioning) ;; delete ;; AAT, CLA, TRO
it (?:is|'s) (?:important|crucial|essential|vital|critical|necessary) to (?:note|understand|recognize|remember|examine) ;; delete ;; VAL, WP, AAT
one (?:must|should) (?:consider|note) ;; delete ;; VAL
we (?:must|should) (?:acknowledge|recognize) ;; delete ;; VAL
it cannot be overstated ;; delete ;; CLA
needless to say ;; delete ;; own
it goes without saying ;; delete ;; own
```

`significance`:

```text
(?:stands?|serves?) as a (?:testament|reminder) ;; shows ;; WP
is a (?:testament|reminder) ;; shows ;; WP
(?:crucial|pivotal|vital|significant|key) (?:role|moment) ;; state the effect ;; WP
plays? an? [\w-]+ role ;; state the effect ;; SS, CLA
underscor(?:es|ing) the (?:importance|significance) ;; delete ;; WP, CLA
highlight(?:s|ing) (?:its|the) (?:importance|significance) ;; delete ;; WP
reflect(?:s|ing) (?:a )?broader ;; delete ;; WP, CLA
setting the stage for ;; prepares ;; WP
key turning point ;; state the event ;; WP
evolving landscape ;; delete ;; WP
focal point ;; center. Literal in graphics ;; WP
distinction (?:matters|is important) because ;; state the difference ;; WP
valuable insights ;; findings ;; WP
```

`reflective`:

```text
worth sitting with|sit with (?:that|this|it) ;; delete ;; CLA
keeps? (?:coming back to|arriving at|running into|noticing) ;; delete ;; CLA
where i (?:landed|keep landing|come down) ;; state the decision ;; CLA
brings? (?:me|us) back to ;; delete ;; CLA
the (?:one|thing) that surprised me ;; delete ;; CLA
what i didn't expect to find ;; delete ;; CLA
```

`puffery` (own, for `triad-puffery`; drop the `;;` fields):

```text
fast|safe|clean|simple|robust|reliable|scalable|maintainable|flexible|elegant|powerful|efficient|modern|secure|intuitive|comprehensive|seamless|consistent|composable
```

`vocab_strong`:

```text
delv(?:e|es|ed|ing) ;; examine ;; KOB, JUZ, WP
tapestr(?:y|ies) ;; delete ;; WP, WSC
meticulous(?:ly)? ;; careful ;; WP, VAL
multifaceted ;; state the aspects ;; WP, VAL
myriad ;; many ;; VAL
plethora of|multitude of ;; many ;; VAL
showcas(?:e|es|ed|ing) ;; shows ;; KOB, JUZ, WP
boast(?:s|ed|ing)? ;; has ;; JUZ, WP
garner(?:s|ed|ing)? ;; gets ;; JUZ, WP
intricac(?:y|ies) ;; details ;; JUZ, WP
pivotal ;; important, with the reason ;; WP, CLA
cornerstone ;; basis ;; VAL
realm ;; area ;; JUZ, CLA
surpass(?:es|ed|ing) ;; exceeds ;; JUZ
vibrant ;; delete ;; WP
holistic ;; complete ;; CLA
```

`vocab_weak` (metric, density only):

```text
crucial, intricate, enhance(?:s|d)?, enhancing, comprehensive, insights?, notably, particularly, additionally, underscor(?:e|es|ing), emphasi[sz]ing, highlighting, enduring, valuable, interplay, bolster(?:s|ed), dependable, echoed, universally, prioriti[sz]e
```

Sources: [KOB], [JUZ], [WP].

`homonyms` (`vocab-context`, all regex own, literal uses from the named sources):

| word | match | except | literal use that must not fire |
| --- | --- | --- | --- |
| leverage | `\bleverag(?:e\|es\|ed\|ing)\s+(?:the\|this\|that\|these\|those\|its\|our\|their\|existing\|[a-z]+'s)\b` | | Finance, per [GOV]. The noun is not matched |
| robust | `\brobust(?:ly)?\b` | `\brobust(?:ly)?\s+(?:to\|against\|statistics?\|estimators?\|regression\|mean\|median)\b` | Statistics, "robust against X" is a claim that can be tested. Also the `robustness` feature in graphics APIs (not matched, as the word differs) |
| surface | `\bsurfac(?:e\|es\|ed\|ing)\s+(?:the\s+\|a\s+\|an\s+)?(?:issues?\|problems?\|insights?\|risks?\|concerns?\|findings?\|questions?\|tensions?\|gaps?)\b` | | Render surface, API surface, attack surface, geometry. "surface errors to the user" is not matched |
| harness | `\bharness(?:es\|ed\|ing)?\s+the\s+(?:power\|potential\|capabilit\w+)\b` | | Test harness, Cargo `harness = false` |
| key | `\bkey\s+(?:takeaways?\|insights?\|ideas?\|concepts?\|factors?\|roles?\|aspects?\|benefits?\|moments?\|features?)\b` | | Hash map key, crypto key, input key. "key point" is left out as a keypoint is a graphics term |
| landscape | `\b(?:evolving\|changing\|complex\|dynamic\|competitive\|current\|broader\|tooling\|threat\|security)\s+landscape\b` | | Screen orientation, terrain |
| underscore | `\bunderscor(?:e\|es\|ed\|ing)\s+(?:the\|that\|how\|why\|its)\b` | | The `_` character, per [WP]'s warning |
| foster | `\bfoster(?:s\|ed\|ing)?\s+(?:a\|an\|the\|greater\|better\|collaboration\|innovation\|trust)\b` | | [GOV] excepts children. Fostering trees are rare |
| align | `\balign(?:s\|ed\|ing)?\s+with\s+(?:the\s+)?(?:best\|business\|goals?\|values?\|expectations?\|needs?\|vision\|strategy)\b` | | Memory alignment, UI layout |
| streamline | `\bstreamlin(?:e\|es\|ed\|ing)\b` | | [GOV] has no literal exception. Fluid dynamics is the one literal use |
| utilize | `\butili[sz](?:e\|es\|ed\|ing\|ation)\b` | `\b(?:cpu\|gpu\|memory\|core\|disk)\s+utili[sz]ation\b` | Resource utilization metrics |
| facilitate | `\bfacilitat(?:e\|es\|ed\|ing)\b` | | None seen |
| empower | `\bempower(?:s\|ed\|ing)?\b` | | None seen |

`gov_avoid` (metric, from [GOV]): collaborate, disincentivise, empower, facilitate, incentivise, liaise, overarching, slim down, tackle, utilise.

`clause_markers` (own):

```text
because, since, although, though, while, whereas, unless, until, if, when, whenever, where, after, before, that, which, who, whom, whose, so that, in order to, as long as, as soon as, even if, even though
```

## Severity rationale

- **Block.** The `art-*` rules are almost never valid in docs. The mannered and contrast block rules follow Malte's request, and a false positive costs one rewrite by an agent. `neg-setup-flip` matches factual sentences, so it may need lowering to warn.
- **Warn.** Precision is unmeasured, or a literal meaning exists.
- **Metric.** Common words, density rules and readability. These inform the report only.

The main reader of these findings is an agent, so each finding should print the replacement from the list, plus the matched text. [WSC] and [Étincel][ETI] also flag specific edits.

Known limits:

- Nothing here has run on real prose. See "Regex check" below for what was compiled.
- No source tests any rule on Rust comments.
- Rules can be evaded by rewording ([DES], [SGB]). Agents see each failure message and can adjust. A replay should check whether fixes improve the text or only replace the phrase, for example by looking for synonyms of listed metaphors in the fixes.
- Malte's "X but Y" complaint has weak coverage by design: `but` is required English, so only narrow forms fire (`but-adj`, `but-balanced`) plus a metric.

### Regex check

I ran these through `rg`, which uses the Rust `regex` engine, on this file only: `neg-not-only`, `range-double`, `neg-no-no-just`, a shortened `neg-setup-flip` B, `nest-prep-chain`, a shortened `count-noun`, and `\p{Extended_Pictographic}`. All compiled. No other pattern was compiled, and no pattern was tested on a labeled sample. A rule import should compile every pattern and test it against the examples in this table.

[WP]: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
[KOB]: https://arxiv.org/html/2406.07016v5
[JUZ]: https://arxiv.org/html/2412.11385v1
[REI]: https://arxiv.org/html/2410.16107
[WAPO]: https://www.bostonglobe.com/2025/11/13/business/chatgpt-writing-style-clues/
[LAZ]: https://brandonlazovic.dev/articles/llm-negative-parallelism-tic/
[ISS]: https://github.com/anthropics/claude-code/issues/53454
[HYP]: https://hyperdev.matsuoka.com/p/the-word-problem-why-developers-cant
[TRO]: https://tropes.fyi/directory
[CLA]: https://claudisms.ai/
[GOV]: https://guidance.publishing.service.gov.uk/writing-to-gov-uk-standards/style-guides/a-to-z-style-guide/
[MS]: https://learn.microsoft.com/en-us/style-guide/global-communications/writing-tips
[WB]: https://github.com/scale-venture-partners/windbag
[AIS]: https://raw.githubusercontent.com/scanaislop/aislop/main/docs/rules.md
[VAL]: https://github.com/ammil-industries/vale-signs-of-ai-writing
[WSC]: https://github.com/theserverlessdev/wsc
[AAT]: https://github.com/MikkoParkkola/anti-ai-tell
[SG]: https://eric-tramel.github.io/slop-guard/docs/dev/rules/
[SGB]: https://eric-tramel.github.io/blog/2026-02-18-slop-guard
[DES]: https://github.com/adamcharnock/deslop
[SS]: https://slopsift.dev/rules/index.json
[HUM]: https://github.com/yanstd888/humanizer-lint
[ETI]: https://github.com/AIStoryHub/etincel
[DAI]: https://academy.dair.ai/resources/write-better-with-claude-fable-5-1
[SEAM]: https://martinfowler.com/bliki/LegacySeam.html
[PIT]: https://aclanthology.org/D08-1020.pdf
[FRO]: https://www.frontiersin.org/articles/10.3389/fpsyg.2017.02268/full
[TL]: https://github.com/textlint-rule/textlint-rule-max-comma
[FK]: https://en.wikipedia.org/wiki/Flesch%E2%80%93Kincaid_readability_tests
[ARI]: https://en.wikipedia.org/wiki/Automated_readability_index
[VD]: https://docs.vale.sh/checks/readability
[APIB]: https://clcomms.com.au/writing/is-there-an-ideal-sentence-length/
[AUS]: https://www.stylemanual.gov.au/style-manual-resources/government-writing-handbook/editors-tips/sentence-length
[TF]: https://arxiv.org/pdf/2505.01939
[LIA]: https://arxiv.org/abs/2403.07183
[SSR]: https://github.com/NikhilVerma/writinglint
