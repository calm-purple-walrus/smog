# Layer 6: how Smog is built and runs on GitHub

Researched 2026-11-08. Scope: Rust, on every PR. Inputs: `docs/design/measurement-model.md`, `metrics-1.md`, `metrics-2.md`, `scores-rules.md`.

## Answer

**Build one Rust binary, `smog`.** It parses code itself, reads the output of existing tools, applies the policy, and publishes a verdict. No product I opened can express the model's curves, debt ledger and per-piece budgets (section 5).

**On GitHub, split the gate into an untrusted half and a trusted half:**

```
agent pushes a branch, or the merge queue creates a group
        |
        v
smog-collect   pull_request, merge_group
UNTRUSTED        read-only token, no secrets, runs the PR's code
                 clippy, tests + coverage, mutants, index; uploads raw outputs
        |  workflow_run: completed
        v
smog-judge     runs from the default branch
TRUSTED          holds the Smog App key, never runs the PR's code
                 reads git objects, evidence, policy and ledger
                 posts the check run smog/gate on the PR's head commit
        |
        v
Ruleset          required check smog/gate, expected source = Smog App
        |
        v
squash merge --> smog-record (push to main) --> smog-state repository
```

**Why the split:** the code being judged is written by the agent being judged. A normal CI job can be edited by the agent's PR, or subverted by its `build.rs`, proc macros and tests. Section 1 lists each attack and what closes it.

**Limits:**

- Nothing here has run. The Smog repository holds only documents (observed), so I have no timings for any tool on real code.
- One attack stays open: code that runs in the collector can forge that collector's outputs (section 1).
- Two choices depend on your GitHub plan, which I do not know: the merge queue and push rulesets (section 12).

**How to read sources:** every linked page came through a fetch tool that summarizes, so check quotes before reusing them. **Snippet** means seen only in a search result. **Own** means my design or inference, which no source tests.

## 1. Attacks on the gate

The attacker model is an agent that optimizes for a green check, which `scores-rules.md` section 6 shows is measured behavior. Deliberate supply-chain attacks are a larger question (section 12).

| Attack | Why it works | What closes it |
| --- | --- | --- |
| Edit the workflow in the PR so it passes | A run [uses "the version of the workflow that is present in the associated commit SHA or Git ref of the event"](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflows), so a `pull_request` run uses the PR's version | Agent's App has no [Workflows permission](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app). The verdict comes only from the judge, whose file [must be on the default branch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) |
| Post a fake check or status called `smog/gate` | Anyone with a write token can post one | [Select the App as expected source](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets): "If another person or integration sets the status, merging isn't allowed" (fetch tool's wording) |
| Read the App key from a PR workflow | GitHub [withholds secrets from fork PRs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets). A branch in the same repository has no such limit (inference) | Keep the key in an [environment](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) whose deployment branches allow only `main`. Jobs get its secrets only after the rules pass |
| Skip the collector | If it does not run, nothing is reported | Fails closed: a required check that never reports leaves the PR [blocked](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks) |
| Run code inside the trusted job | [`build.rustc`, `build.rustc-wrapper`](https://doc.rust-lang.org/cargo/reference/config.html) in `.cargo/config.toml` name executables. Build scripts and proc macros run at build time | The judge never calls `cargo`, `rustc` or rust-analyzer on PR content. It reads git objects and data files only. **Own.** The [`cargo metadata` page](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html) does not say whether it runs `rustc`, so I treat it as unsafe here |
| Loosen a tool through its config in the tree | Section 3 lists these files. `exclude_re` in [`.cargo/mutants.toml`](https://mutants.rs/print.html) removes mutants. A nextest [`default-filter`](https://nexte.st/docs/selecting/) can exclude tests | Add them to the "gate is untouched" list, and pass fixed config on the command line |
| Suppress in the source | `#[mutants::skip]` is in model 3.1. [`#[mutants::exclude_re("...")]`](https://mutants.rs/print.html) is not, and `mutants::skip` inside `cfg_attr` always applies | Extend "no new suppressions" to these forms |
| Hide tests from the build | `#[cfg(any())]` on a test compiles it out (general knowledge) | Compare tests found by `syn` with tests in the nextest report. A test in one and not the other is a finding. **Own** |
| Poison the cache | A PR run's cache [cannot be restored by the base branch or other PRs](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching). `workflow_run` gets read-only access to the default branch's cache | The judge restores no cache |
| Merge around the gate | Bypass lists | The agent's App is on no bypass list |
| **Forge tool outputs** | Tests, build scripts and proc macros run in the same VM as cargo-mutants and llvm-cov. They could rewrite the report files | **Not closed.** Partial: validate the schema, flag diffs that add `build.rs` or a proc-macro crate, flag file writes in test code (`metrics-1` T7 Mystery Guest), and rerun a random sample of merged PRs on `main` and alert on differences. **Own** |

The agent must also not push with `GITHUB_TOKEN`. Events from that token [do not create workflow runs](https://docs.github.com/en/actions/concepts/security/github_token), except that some `pull_request` runs are created in an [approval-required state](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow). The same page says an App token avoids both.

## 2. GitHub setup

### Two Apps

| | Agent App | Smog App |
| --- | --- | --- |
| Used by | The factory's agents | The judge and record jobs only |
| Permissions | Contents write, pull requests write | [Checks write](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps), contents write |
| Must not have | Workflows, administration, access to `smog-state` (section 7), any bypass | Any bypass, or use outside those jobs |

An App's permissions are not set per repository (general knowledge), so the Smog App holds contents write everywhere it is installed. Limit each job's token instead: [`create-github-app-token`](https://github.com/actions/create-github-app-token) takes `repositories` and `permission-*`. Use one token for checks and reads on the product repository, and one for writes to `smog-state`. The ruleset on `main` still applies to this App, because it has no bypass.

Only a GitHub App [can create a check run](https://docs.github.com/en/rest/checks/runs), so a dedicated App is required for the expected-source defense as well as for check output.

### Rules on `main`

| Setting | Value | Note |
| --- | --- | --- |
| [Require a pull request](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) | On | It need not be approved, so the factory can merge without a human |
| Required status check | `smog/gate`, expected source Smog App | `smog/report` stays optional |
| Allowed merge methods | Squash only | Model 3.8 needs one commit per PR |
| Bypass | Named humans only | [Admins are exempt by default](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) on branch protection unless "Do not allow bypassing" is on |
| Merge queue, or "up to date" | See below | Two PRs can each pass against a base that the other then changes |
| [Push ruleset: restrict file paths](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Section 3's list, humans bypass | The push fails outright. [Private and internal repositories only](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) |
| [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners) review | Section 3's list, including CODEOWNERS | Read from the base branch. Whether it works with zero required approvals is unverified. Test it |

Rulesets need [GitHub Team or Enterprise](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets). Organization-wide rulesets need Enterprise.

### Merge queue

Debt depends on the base. Two PRs that each fit a piece's budget can exceed it together, so the second must be judged against the first.

| Option | Cost | Availability |
| --- | --- | --- |
| [GitHub merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Must add `merge_group`, or "the required status check will not be reported" | [Enterprise Cloud repositories and public organization repositories](https://github.blog/changelog/2023-07-12-pull-request-merge-queue-is-now-generally-available/), as of 2023. The current docs page did not state this |
| [Require branches to be up to date](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) | Every merge invalidates all other PRs, and "more builds may be required". With mutation testing on each rebuild this gets expensive at factory rates (inference) | Any plan with protection |
| [Mergify](https://docs.mergify.com/migrate/github-merge-queue) or a similar vendor | A third party holds merge rights. It needs the `merge_queue` rule removed, or a bypass for itself, so section 1's "no bypass" gets one exception | Vendor claims a free tier for up to 5 users on private repositories (Snippet) |

**Recommendation:** use the GitHub merge queue if your plan has it, otherwise "up to date". In the queue, set the [merge method](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) to squash and start with a maximum group size of 1. Agents call [`gh pr merge`](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue), which enables auto-merge if checks have not passed yet.

**In the queue, do not rerun mutants (Own).** The queue run repeats the static checks and tests. It reuses the PR's mutation and coverage counts when the patch is unchanged, using a `git patch-id` key the judge stored in the ledger. This assumes other PRs in front rarely change a mutant's result. Backtest it.

### Workflows

Sketch, not run. Pin every action to a full [commit SHA](https://docs.github.com/en/actions/reference/security/secure-use) in the real files. I show tags for reading.

```yaml
# .github/workflows/smog-collect.yml
name: smog-collect
on: [pull_request, merge_group]
permissions: { contents: read }
jobs:
  static:        # saves money only. The judge recomputes this result.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
          fetch-depth: 0
          persist-credentials: false
      - run: smog check-static     # install step omitted
  evidence:
    needs: static
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7    # same inputs as above
      - uses: Swatinem/rust-cache@v2
        with: { save-if: false }
      - uses: taiki-e/install-action@v2
        with: { tool: "cargo-nextest@X,cargo-llvm-cov@X" }
      - run: smog collect clippy tests index --out evidence/
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: evidence, path: evidence/ }
  mutants:
    needs: static
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix: { shard: [0, 1, 2, 3] }
    steps:
      - uses: actions/checkout@v7    # same inputs as above
      - run: smog collect mutants --shard ${{ matrix.shard }}/4 --out evidence/
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: "mutants-${{ matrix.shard }}", path: evidence/ }
```

```yaml
# .github/workflows/smog-judge.yml
name: smog-judge
on:
  workflow_run:
    workflows: [smog-collect]
    types: [completed]
permissions: { actions: read, contents: read }
jobs:
  judge:
    runs-on: ubuntu-latest
    environment: smog-judge        # App key, deployment branch main only
    steps:
      - uses: actions/create-github-app-token@v3
        id: app
        with:
          client-id: ${{ vars.SMOG_APP_ID }}
          private-key: ${{ secrets.SMOG_APP_KEY }}
          permission-checks: write
          permission-contents: read
      # second token for smog-state omitted
      - run: smog judge-run --run-id "$RUN_ID"    # install step omitted
        env:
          RUN_ID: ${{ github.event.workflow_run.id }}
          GH_TOKEN: ${{ steps.app.outputs.token }}
```

Details that matter:

- **No checkout in the judge.** It fetches objects by SHA and reads them through git. **Own.**
- **Collect on the PR head, not the merge commit.** [`pull_request` defaults to the merge result](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), but required checks attach to [the latest commit](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks), and findings need that commit's line numbers. [`actions/checkout`](https://github.com/actions/checkout) supports this. Staleness is then handled by the queue. **Own.**
- **Conflicts.** `pull_request` [does not run on a conflicting PR](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), which leaves the PR blocked. Agents need to treat that state as "rebase".
- **Verify the run.** The judge checks that the triggering run came from `.github/workflows/smog-collect.yml` and that its head SHA is the PR's current head. It treats artifacts as hostile: size limits, schema validation, no extraction to paths. **Own.**
- **Branch names are attacker text.** Never put `workflow_run.head_branch` in a `${{ }}` in a script. The [docs](https://docs.github.com/en/actions/reference/security/secure-use) prefer passing such values as arguments or environment variables.
- **Artifacts from another run** need [`run-id` and a token with `actions:read`](https://github.com/actions/download-artifact).
- **Merge groups.** The docs say to [check and report on the group's head SHA](https://docs.github.com/en/webhooks/webhook-events-and-payloads). Third-party CI [runs on `gh-readonly-queue/{base_branch}` pushes](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue). I did not confirm the `workflow_run` path through a queue, or how to find one PR's share of a group. Test this first.
- **Never use path filters on the collector.** A filtered workflow [stays pending and blocks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks).
- **Do not use `pull_request_target` here.** GitHub says to [avoid it unless necessary](https://docs.github.com/en/actions/reference/security/secure-use), and `workflow_run` gives what is needed. It also does not fire for merge groups, as far as the page shows.

**Required workflows from another repository** are the other way to keep a gate out of the agent's reach. [Ruleset workflows](https://docs.github.com/en/enterprise-server@3.20/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules) support `pull_request`, `pull_request_target` and `merge_group`. GitHub's [2023 changelog](https://github.blog/changelog/2023-10-11-requiring-workflows-with-repository-rules-is-generally-available/) names Enterprise Cloud, and a third-party blog says Team too (Snippet). I would not depend on it until the plan is known. It still runs PR code on the same VM, so it does not remove the need for a judge.

**A hosted webhook service** instead of `workflow_run` would [receive `merge_group` directly](https://docs.github.com/en/webhooks/webhook-events-and-payloads) and need no key in Actions. It adds a server to run. Consider it later. **Own.**

## 3. Files the agent may not change

Model 3.1 says rules, thresholds, baselines and CI files. For Rust, the list must also include (**Own**, with sources for what each does):

| File | What it can do |
| --- | --- |
| `.github/**`, `CODEOWNERS` | Change CI and approval rules |
| `.cargo/config.toml`, also in parent folders of a crate | [`rustc-wrapper`, `runner`, `rustc`](https://doc.rust-lang.org/cargo/reference/config.html) replace or wrap what runs |
| `.cargo/mutants.toml` | [Exclude files and mutants](https://mutants.rs/print.html). Also pass [`--no-config`](https://mutants.rs/print.html) |
| `.config/nextest.toml` | [Profiles and retries](https://nexte.st/docs/configuration/), and a [`default-filter`](https://nexte.st/docs/selecting/) that excludes tests. Also pass [`--config-file`](https://nexte.st/docs/configuration/) with Smog's own file, and [`--ignore-default-filter`](https://nexte.st/docs/selecting/) |
| `clippy.toml`, `.clippy.toml`, `deny.toml`, `rustfmt.toml`, `sgconfig.yml` | Loosen a tool (general knowledge; only partly checked) |
| `rust-toolchain.toml`, `rust-toolchain` | Choose the compiler. Smog should name the toolchain explicitly |
| `[lints]` and `[profile.*]` in any `Cargo.toml` | Silence lints or change how tests build. These sit in a file agents must edit, so check the sections and not the path |
| `build.rs`, proc-macro crates | Not blocked, because they are legitimate. A change is flagged for the audit sample |

Policy and baselines do not appear here, because they live outside the repository (section 7).

## 4. The binary

**Name.** `cargo-geiger` is [an existing crate that detects `unsafe`](https://crates.io/api/v1/crates/cargo-geiger), and [`geiger` is its library](https://crates.io/api/v1/crates/geiger). That collision is why this project is now called Smog. A private binary works under that name.

**Commands (Own):**

| Command | Runs in | Does |
| --- | --- | --- |
| `smog check-static` | Collector | Fast verdict on the syntax-only rules, to skip the slow jobs. Its result is advisory |
| `smog collect <tool>` | Collector | Runs a tool with fixed arguments, stores raw output and versions. Keeps the workflows short and the arguments in the binary |
| `smog judge-run` | Judge | Fetches objects, evidence, policy and ledger, then calls `judge` and `publish` |
| `smog judge` | Judge, local | Pure function: base facts, head facts, evidence, policy and ledger in; verdict out. No network |
| `smog publish` | Judge | Posts check runs and annotations |
| `smog record <sha>` | Push to `main` | Writes one PR's entry to the ledger. Safe to rerun |
| `smog replay <range>` | Local, scheduled | Backtest over history, as `scores-rules.md` section 9 requires |

**Crates (Own):**

```
smog-facts    versioned serde types: facts, evidence, findings, verdict
smog-scan     syn + lexer --> per-item facts, AST hash, item identity
smog-ingest   parsers for clippy, nextest, lcov, cargo-mutants, SCIP
smog-judge    lenses, curves, aggregation, rules. No I/O
smog-github   check runs, artifacts, REST
smog          the binary
```

- `smog-judge` has no I/O so that the exploit suite in `scores-rules.md` section 6 can be plain unit tests: the transformed code must not score better.
- Layers 3 to 5 are options per user, so `policy.toml` selects lenses, curves and rules. A lens is one implementation of a small trait.
- Base and head facts are both computed at judge time, because syntax facts are deterministic. No baseline file is needed for them, which removes one thing an agent could edit.
- `cargo-mutants` says its output format is [subject to change](https://mutants.rs/mutants-out.html), and [rustdoc JSON is unstable](https://github.com/obi1kenobi/cargo-semver-checks). So pin each tool version in the binary, and keep a fixture test per tool version.

## 5. Tools

### Off-the-shelf products

| Product | What the page shows for Rust | Use |
| --- | --- | --- |
| [SonarQube](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/languages/rust) | Cognitive and cyclomatic complexity, imported Clippy findings. No custom Rust rules on the page. Coverage import and duplication (Snippet) | Not the gate. Nothing on the page offers curves, a ledger or item-level budgets |
| [CodeScene](https://codescene.io/docs/usage/language-support.html) | "Full support" and method-level X-Ray, with [custom rules applied in PR checks](https://codescene.io/docs/usage/language-support.html) | Not the gate, because its score is its own. Possibly a sealed second opinion (`scores-rules.md` section 6). **Own** |
| [Qlty](https://docs.qlty.sh/languages) | Rust under "Full support", with no per-feature breakdown on that page | Not evaluated further |
| [CodeQL](https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/about-the-codeql-cli) | Rust listed. Free on public repositories. Private needs a Code Security license | Not first. A possible later source for type-resolved queries |

### What feeds each lens

**Static** means no PR code runs, so the judge can compute it. **Executes** means it runs PR code, so it belongs in the collector and is only evidence.

| Model lens or check | Tool | Tier | Notes |
| --- | --- | --- | --- |
| Length, nesting, parameters, fields, methods, variants, generics, LCOM4, return points, cyclomatic | Own `syn` visitors | Static | Section 6 |
| Cognitive complexity | Own visitor, or [rust-code-analysis](https://mozilla.github.io/rust-code-analysis/metrics.html) | Static | Section 6 |
| Comment lenses, slop check, blank lines | Own, over a lexer | Static | `syn` loses comments (section 6) |
| Suppressions, weakened tests, `metrics-1` P8, `metrics-2` T7 | Own, comparing base and head trees | Static | |
| Gate untouched, PR size, entropy, files touched | Git diff | Static | |
| File, folder and module counts | Git tree | Static | |
| Crate dependencies, layer edges, instability, `Cargo.lock` change | Parse `Cargo.toml`, `Cargo.lock` as data | Static | Not `cargo metadata` in the judge. The collector may run [`cargo metadata --format-version=1`](https://doc.rust-lang.org/cargo/commands/cargo-metadata.html) as evidence |
| Project conventions | [ast-grep](https://ast-grep.github.io/reference/cli/scan.html) `scan --json` plus own rules | Static | Exit 1 on an error-level match. Rules come from `smog-state` |
| Unused dependencies | [cargo-machete](https://github.com/bnjbvr/cargo-machete) (via `metrics-1` C4) | Static (assumed) | Check that it runs nothing |
| Item identity, AST hash, test churn input | Own | Static | Foundation for the ledger |
| Lints | [`cargo clippy --message-format=json`](https://doc.rust-lang.org/cargo/reference/external-tools.html) | Executes | `build.rs` and proc macros run. Pass the denied set as flags. Parse only lines that start with `{`, because [proc macros can print to stdout](https://doc.rust-lang.org/cargo/reference/external-tools.html) |
| Tests, test time, uncovered lines | [`cargo llvm-cov nextest`](https://github.com/taiki-e/cargo-llvm-cov) with `--lcov` | Executes | One run gives tests and coverage. Smog intersects LCOV with the diff. [JUnit](https://nexte.st/docs/machine-readable/junit/) gives times and flakes |
| Doctests | Separate step | Executes | [Nextest does not run them](https://mutants.rs/nextest.html). [llvm-cov needs nightly](https://github.com/taiki-e/cargo-llvm-cov) for them |
| Surviving mutants | [cargo-mutants](https://mutants.rs/pr-diff.html) `--in-diff`, sharded | Executes | Section 8 |
| Advisories | [cargo-deny](https://github.com/EmbarkStudios/cargo-deny) `check advisories` | Reads the lockfile (assumed) | Covers cargo-audit's job, so run one. Block only on packages the PR's lockfile adds (section 9) |
| Outgoing and incoming dependencies, propagation cost, `metrics-*` M and P1 entries | [rust-analyzer SCIP](https://docs.rs/crate/ra_ap_rust-analyzer/latest/source/src/cli/flags.rs) | Executes | Section 6 |
| Module cycles | [`cargo modules dependencies --acyclic`](https://github.com/regexident/cargo-modules), later SCC over the index | Executes (assumed) | The page does not say what it runs |
| Public API change, `metrics-1` P6 | [cargo-public-api](https://github.com/cargo-public-api/cargo-public-api), [cargo-semver-checks](https://github.com/obi1kenobi/cargo-semver-checks) | Executes | Run only if the diff touches a `pub` item. `cargo-public-api` needs a nightly, and each version fits a nightly range. `cargo-semver-checks` supports current stable and beta. Its exit codes: 0, 100 violation, 101 could not finish. It works on unpublished crates with `--baseline-rev` |
| Unreviewed lines | `git blame -w -M -C`, [`GET /commits/{sha}/pulls`](https://docs.github.com/en/rest/commits/commits), [reviews API](https://docs.github.com/en/rest/pulls/reviews) (via `metrics-2` P7) | Static, push job | Report only, so not on the PR path |
| `metrics-1` P9, P10, `metrics-2` P5 to P8 | [Checks](https://docs.github.com/en/rest/checks/runs) and reviews REST | Host | Read by the judge or record job |
| Custom type-aware rules | [Dylint or cargo-pup](https://github.com/DataDog/cargo-pup) (`scores-rules.md` section 7) | Executes, pinned nightly | Later. Only for rules `syn` cannot do |

### Installing and caching

- [`taiki-e/install-action`](https://github.com/taiki-e/install-action) installs pinned versions (`tool@1.2.3`) and verifies SHA-256 for tools it covers. Its tool list is on a page I did not open. [cargo-mutants' docs](https://mutants.rs/pr-diff.html) use it for cargo-mutants.
- The `smog` binary must be fetchable without a secret in the collector, which has none. Public release assets, or a checksum-pinned download from a public location. **Own.**
- [`Swatinem/rust-cache`](https://github.com/Swatinem/rust-cache) caches dependencies, not workspace crates, and sets `CARGO_INCREMENTAL=0`. Cargo-mutants [spends its time in incremental builds](https://mutants.rs/performance.html), although its own example workflow uses this action. So measure the mutants job with `CARGO_INCREMENTAL=1`. This is my inference.
- [Cache limit is 10 GB per repository](https://docs.github.com/en/actions/reference/limits), and the action says [older caches are evicted](https://github.com/Swatinem/rust-cache).

## 6. Two foundation choices

### Parser: `syn` for trees, a lexer for text

- The model and both metric reports assume `syn`. [`syn::parse_file`](https://docs.rs/syn/latest/syn/) parses a file, and [`proc-macro2`'s `span-locations`](https://docs.rs/proc-macro2/latest/proc_macro2/struct.Span.html) gives line numbers on any toolchain outside a macro.
- **`syn` cannot do the comment lenses alone.** [Non-doc comments are whitespace](https://doc.rust-lang.org/reference/comments.html), and doc comments become attributes. So ordinary comments and blank lines are not in its tokens (inference from that page; I did not test it). Length "without comments and blanks", the slop check and the paragraph rule need a lexer. [`ra_ap_rustc_lexer`](https://docs.rs/ra_ap_rustc_lexer/latest/ra_ap_rustc_lexer/) is a candidate. The page did not list its token kinds, so check that it emits comments.
- **Alternative:** [`ra_ap_syntax`](https://docs.rs/ra_ap_syntax/latest/ra_ap_syntax/) gives one full-fidelity tree with error tolerance, at version 0.0.360. It may break on upgrade, but a pinned version only costs upgrade work. Try both on one lens before committing. **Own.**
- **A parse failure must not pass.** If `syn` lacks new syntax the compiler accepts, block and name it as a tool failure (section 9).

**rust-code-analysis.** Model 3.2 names it for complexity. It [offers COGNITIVE, CC, NEXITS and NARGS](https://mozilla.github.io/rust-code-analysis/metrics.html), but [crates.io's newest release is 0.0.25 from January 2023](https://crates.io/api/v1/crates/rust-code-analysis). The [newest commits I saw](https://github.com/mozilla/rust-code-analysis/commits/master) are from 20 January 2026. A January 2023 grammar may not know later Rust syntax (inference). So I would write the simple lenses in `syn`, which the exploit suite needs anyway, and use this tool as a cross-check on a sample.

### Index: rust-analyzer's SCIP output

| Option | For | Against |
| --- | --- | --- |
| **`rust-analyzer scip <path> --output ...`** | [A defined command](https://docs.rs/crate/ra_ap_rust-analyzer/latest/source/src/cli/flags.rs). [SCIP has a Protobuf schema and Rust bindings](https://github.com/scip-code/scip), so Smog reads a file and links no compiler internals | Whole-workspace analysis per run, timing unknown |
| `ra_ap_*` crates directly | Richer: types, trait solving | rust-analyzer says [the `ide` API is "explicitly unstable"](https://rust-analyzer.github.io/book/contributing/architecture.html) and the `hir-*` crates "will never be" an API boundary |
| Rustc driver or MIR | Exact | Pinned nightly, compiler internals |
| Own name resolution over `syn` | Static and fast | Wrong in the cases that matter: traits, macros, re-exports |

**Recommendation:** SCIP. What the [source](https://docs.rs/crate/ra_ap_rust-analyzer/latest/source/src/cli/scip.rs) shows, for version 0.0.336:

- **It executes PR code.** It sets `load_out_dirs_from_check: true` and starts a proc-macro server, so it belongs in the collector. So anything the judge concludes from it is evidence, with the same forgery limit as tests.
- **Reads and writes are not separated.** Only the Definition role is set. `metrics-1` S7 and `metrics-2` F9 need field reads and writes, so Smog must get those from the syntax tree at the occurrence's position.
- **Enclosing ranges** are present only when the definition body is in the same file. Smog can use them to assign a reference to its containing function.
- **Trait calls** probably resolve to the trait method, not the implementation (general knowledge). A one-impl check needs `impl` blocks from `syn`.

Run one real repository through it before building on it. If it takes too long per PR, compute the index on `main` only, and restrict PR-time findings to syntax lenses plus the changed files.

## 7. Where state lives

| Option | Problem |
| --- | --- |
| Branch or git notes in the product repository | The agent's Contents write token can reach them unless a ruleset covers them. Mixed with product history |
| [Actions cache](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) | "Not signed or verified", and evicted at the [10 GB limit](https://docs.github.com/en/actions/reference/limits) |
| Artifacts | [Storage by plan is 500 MB to 50 GB](https://docs.github.com/en/actions/reference/limits). Retention not confirmed from the pages I read |
| External database | One more service and credential |
| **Separate private repository** | Recommended. **Own** |

**Layout of `smog-state` (Own):**

```
policy.toml                  human-edited; lenses, curves, limits, layer map, allowlists
sealed/                      lenses the agent never sees
ledger/<merge-sha>.json      one file per merged PR
pending/<patch-id>.json      PR-stage counts reused in the queue
reports/                     generated trend reports
```

- The agent's App has no access, so policy needs no protection in the product repository. This also works on any plan, unlike push rulesets.
- One file per merge SHA means no write conflicts, and rerunning `record` writes the same file.
- Syntax entries can be rebuilt from git history. Mutation and coverage counts cannot, so back them up with the repository.
- Humans change policy by PR in this repository. The judge reads `main` of it, and each verdict records the policy commit.
- Whether this scales to a large window is unmeasured. If reading the last N files is slow, a generated index file fixes it.

## 8. Mutation testing on every PR

Commands, combining [the PR page](https://mutants.rs/pr-diff.html), [shards](https://mutants.rs/shards.html), [nextest](https://mutants.rs/nextest.html) and [config](https://mutants.rs/print.html):

```sh
git diff "$MERGE_BASE".."$HEAD" > git.diff
cargo mutants --no-config --no-shuffle --in-diff git.diff \
  --shard "$K/$N" --baseline=skip --timeout 300 --in-place --test-tool=nextest
```

- **Tests must already pass.** With `--baseline=skip`, the docs say results are otherwise "meaningless". So run this after the test job, and skip it if tests fail. Without a baseline the default timeout is 300 seconds.
- **Shards do not coordinate.** All must [see the same diff and arguments](https://mutants.rs/shards.html). CI collects results, so `smog-ingest` merges each shard's `outcomes.json`.
- **Choose the shard count from the mutant count.** `--list` with the same diff gives the count, and a first job can set the matrix up to [256 jobs](https://docs.github.com/en/actions/reference/limits). **Own.** Zero mutants skips the job. I did not check what `--in-diff` does with a diff that has no Rust changes.
- **Runner limits.** [Standard runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) are 2 CPU, 8 GB and 14 GB disk on private repositories, and 4 CPU, 16 GB and 14 GB on public ones. `--in-place` [cannot combine with `--jobs`](https://mutants.rs/print.html), so a shard is one mutant at a time per VM. Each hosted VM is new per job, so `--in-place` leaves nothing behind.
- **Time.** [Run time is one incremental build and test run per viable mutant](https://mutants.rs/performance.html). [A job may run 6 hours](https://docs.github.com/en/actions/reference/limits). The PR size limit is also the real limit on this job, so the two must be set together.
- **Flaky tests corrupt results.** A mutant counts as [caught if any test failed](https://mutants.rs/print.html), so a flake reads as a kill, and the docs make non-flaky tests a prerequisite.
- **Doctests.** Under nextest, behavior tested only by doctests [shows as missed](https://mutants.rs/nextest.html). Decide whether to accept this. It would count against the PR.
- **Pinned tests.** Cargo-mutants [has no string-literal mutation](https://mutants.rs/mutants.html), so `metrics-1` T1 needs Smog's own rewriting in the collector.

**Exit codes** ([source](https://mutants.rs/exit-codes.html)): 0, 2 and 3 are results (all caught, some missed, some timed out). 1, 4, 5, 6 and 70 are failures of the run. Smog should read the counts from `outcomes.json`, and use the exit code only to tell these apart.

**Full runs** go on the nightly job. The docs say [the diff approach can miss what a whole-tree run catches](https://mutants.rs/pr-diff.html).

## 9. When something fails

The judge must never pass on missing data. It should also not charge the agent for something the PR cannot clear (model 6.2). **Own:**

| Event | Gate result | Finding tells the agent |
| --- | --- | --- |
| Collector did not run | No check, so [blocked](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks) | Nothing. Factory treats a stale missing check as an error |
| Build or test failure | Fail | The failure |
| Tool crash, or mutants exit 1, 5, 6 or 70 | Fail, labelled `tool_error`, not debt | Retry. Repeats alert a human |
| Mutants exit 4 (baseline fails) | Fail | Tests are failing |
| Evidence missing or invalid | Fail, labelled `evidence_invalid` | Alerts a human, because this may be forgery |
| File does not parse in `syn` | Fail, labelled `tool_error` | Alerts a human |
| Flaky test | Smog's nextest config sets [`retries = 2`](https://nexte.st/docs/features/retries/) so old flakes do not block, and a per-test override sets `flaky-result = "fail"` for tests the PR adds or changes. Use config, because [command-line retry options disable per-test overrides](https://nexte.st/docs/features/retries/). Record all flakes in the ledger for `metrics-1` T8 | The new flaky test |
| Mutant timeout | Report. Not charged until noise is measured (model 5.3) | Nothing |
| New advisory on an unchanged lockfile | PR passes. Nightly job opens a ticket | Nothing, because the PR cannot clear it |
| Advisory added by the PR's lockfile change | Fail | The package |

Model 3.1 has advisories as a plain pass or fail. That breaks model 6.2: a new advisory would block every PR until someone fixes it. So this table narrows that check.

## 10. Output for agents and humans

**Check runs (Own):**

- `smog/gate`: required. `success` or `failure`. Only blocking findings.
- `smog/report`: optional, [`neutral`](https://docs.github.com/en/rest/checks/runs). Report-only lenses.

**[Limits](https://docs.github.com/en/rest/checks/runs):** `output.summary` and `output.text` are 65,535 characters each. Annotations are 50 per request, so send more through update calls. Levels are `notice`, `warning` and `failure`. Check runs may have three action buttons.

**Where the model's finding JSON goes (Own):**

- `output.summary`: count, worst findings, policy commit, in Markdown for people.
- `output.text`: one JSON block, worst first, cut off at the limit with a `truncated: true` field.
- Annotations: one per finding on the changed code.
- Artifact: the full `findings.json`, from the judge run.
- Add to the model's example: `schema_version`, a stable `id` of `(lens, item path)`, and `head_sha`.

An agent reads this with `gh api repos/{owner}/{repo}/commits/{sha}/check-runs`. A local `smog judge` on the syntax lenses, with policy supplied, gives the same static findings before pushing. That saves CI, and it does not weaken the gate because the judge recomputes everything. Sealed lenses are excluded, per `scores-rules.md` section 6.

**Why not code scanning as the main channel:**

- PR alerts appear only if [all flagged lines are in the diff, and on added or edited lines](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning). Model 3.6 charges for debt added to code the PR did not touch, such as methods added to a widely used type. Those would not appear.
- Only the [top 5,000 of 25,000 results per run](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning) are kept, and files are limited to 10 MB compressed.
- [CodeQL on private repositories needs a Code Security license](https://docs.github.com/en/code-security/codeql-cli/getting-started-with-the-codeql-cli/about-the-codeql-cli). I did not confirm whether uploading third-party SARIF needs one as well, but I expect so.

`ast-grep` offers [`--format github` and `--format sarif`](https://ast-grep.github.io/reference/cli/scan.html) if you want this later. I did not investigate GitHub's ["require code quality results" rule](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).

**Humans:** the record job writes a Markdown trend report to `smog-state/reports/` and to the [job summary](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands), which allows 1 MiB per step. Start there and build no dashboard yet.

## 11. Jobs outside the PR

| Trigger | Job | Does |
| --- | --- | --- |
| Push to `main` | `smog-record` | Facts delta, AST hashes for the changed files, debt, blame for changed files, PR metadata. Writes the ledger. Runs from the default branch's file, with no PR code |
| Nightly | `smog-nightly` | Full mutation run; K test runs on one commit for flakes and noise (model 5.3); advisories; redundant tests (model 3.5); API lenses; audit rerun of a random merged PR (section 1); seeded PRs (`scores-rules.md` section 6) |
| On demand | `smog replay` | Backtest before enabling a rule |

- **Merges made with `GITHUB_TOKEN` would not start the push job**, for the [reason in section 1](https://docs.github.com/en/actions/concepts/security/github_token). I did not confirm how a merge by the queue behaves. Test it, and have the nightly job fill any ledger gap by comparing `main` with the ledger.
- **Test breakage rate** (model 3.8) needs base tests compiled against head code. For tests in `tests/` that is a file overlay. For inline `mod tests` it means splicing syntax trees and is harder. Do it after the rest.
- Token limits: [`GITHUB_TOKEN` gets 1,000 API requests per hour per repository](https://docs.github.com/en/actions/reference/limits). Use the App token for REST calls.

## 12. Decisions for Malte

1. **Which GitHub plan, and are product repositories private?** This decides the merge queue and push rulesets. If private and not Enterprise Cloud, I recommend "up to date" first, and measuring how often agents have to rerun.
2. **Is the threat an agent gaming the gate, or also a deliberate attack on the factory?** Same as `scores-rules.md` decision 2. For gaming, the audit rerun is enough for the forgery gap. For attacks, the collector needs no network, a separate VM for each tool, and a trusted rerun before merge, at a much higher cost.
3. **Accept a second private repository for policy and ledger?** The alternative is `.smog/` in each product repository, protected by push ruleset and CODEOWNERS. That only works on private repositories with Team or Enterprise.
4. **Who holds bypass, and on which accounts?** Human exceptions must exist, so they need owners. A human using an account that agents also use defeats this.
5. **Can agents ever change `Cargo.toml` `[lints]`?** I propose not.
6. **Should doctest-only behavior count as covered?** With nextest it reads as missed.

## 13. Build order

This puts the GitHub skeleton before `scores-rules.md`'s first step, because it carries the most unverified behavior and needs no lenses. **Own.**

1. **Skeleton.** Two Apps, ruleset, `smog-collect`, `smog-judge`, a stub verdict. Prove with real PRs on a scratch repository that each attack in section 1 fails, and that merge groups and the push job work. Keep these as a script.
2. **Measure.** Run each tool in section 5 on a real repository, for time, disk and determinism. Decide on the SCIP-per-PR question here.
3. **Scan.** Item identity, AST hash, syntax lenses, static checks, in report mode.
4. **Ledger.** `smog-state`, `record`, and `replay`.
5. **Judge.** Curves, debt, budgets, exploit suite. In report mode.
6. **Evidence.** Clippy, tests and coverage, mutants.
7. **Index.** SCIP lenses.
8. **Enable.** Turn on blocking one rule at a time, after replay, starting with the hard checks.

## Not verified

**Nothing has run.** The workflows are sketches. All tool behavior comes from documentation.

**Test first, because the design depends on it:**

- `workflow_run` for a `pull_request` run reports the PR head as `head_sha`, and does so for merge groups too.
- An App's check run on a merge group's head SHA satisfies the queue's required check.
- A deployment-branch policy of `main` allows a `workflow_run` job and refuses a `pull_request` job. The [environments page](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) says environments work on Team and Pro for private repositories, and the [plans page](https://docs.github.com/en/get-started/learning-about-github/githubs-plans) lists deployment protection rules on private repositories under Enterprise. Check this for your plan.
- An App without the Workflows permission cannot push workflow files. The [changelog](https://github.blog/changelog/2020-04-07-github-apps-workflow-permission) implies this, and the error text is from [community threads](https://github.community/t/control-permissions-does-not-allow-adding-workflow-files/175725) (Snippet).
- Code owner review with zero required approvals. Needed so that only gate-file PRs need a human.
- Annotations on files outside the diff, for findings on untouched code.

**Plan availability is uncertain.** The current GitHub docs pages I opened did not state merge queue or ruleset-workflow plans. The merge queue statement is from 2023. Ruleset workflow sources conflict.

**From general knowledge, no page opened:** `#[cfg(any())]` compiling out a test; trait calls in SCIP; `clippy.toml`, `rustfmt.toml` and `sgconfig.yml` effects; `git patch-id`; `cargo-deny`'s behavior regarding builds; `cargo mutants --list` with `--in-diff`; App permissions applying across repositories; the `actions/upload-artifact` version in the sketch.

**Read partly:** [GitHub webhooks](https://docs.github.com/en/webhooks/webhook-events-and-payloads) (first 100,000 of 193,812 characters), [App permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps) (100,000 of 104,048), [cargo-mutants book](https://mutants.rs/print.html) (100,000 of 154,284). The rust-analyzer source is from `ra_ap_rust-analyzer` 0.0.336, which may not match the `rust-analyzer` you install.

**Failed to open:** [`mutants.rs/config.html`](https://mutants.rs/config.html) (404), so config details come from the print view. A `docs.github.com` troubleshooting URL under `managing-protected-branches` (404), replaced by the one linked above. Two GitHub pages on artifacts did not give retention, one [by 404](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manage-workflow-artifacts). Ruleset workflow text comes from the [Enterprise Server 3.20 page](https://docs.github.com/en/enterprise-server@3.20/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules), not github.com.

**Not searched:** per-minute pricing, larger runner costs, Trunk or Aviator in any depth, reviewdog, SARIF conversion tools, any study of how long these tools take on a Rust codebase. Smog has no ADRs (observed), so none apply. This file changes nothing in the repository.
