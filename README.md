# Smog

Smog measures Rust code and applies a policy to the results. You write the policy as a Python script that imports Smog, states its conditions and runs. The script prints an overview at the coarseness you choose, writes the full report as text and as JSON, and exits nonzero if anything blocks or data for the score is missing.

The overview lists the score, the worst pieces at the chosen level, the functions the change against the ref made worse, every block and warning, the failed checks, the slow tools asked for that did not run, and every slop finding that lowers the score. The full report, `report.txt` and `report.json` in the folder of the setting `report_folder` (default `target/smog`), adds every piece, every check with each failure, the score settings and what lowers the score most. `report.json` also holds every value of every piece and of the change.

This is the first version, in Python. `docs/design/measurement-model.md` is the design it started from, and the registry uses its section numbers. Where the two differ, this README and `--explain` state what Smog does.

## Install

You need:

- [uv](https://docs.astral.sh/uv/), which also provides Python 3.13 or later if it is missing.
- git.
- SSH access to this private repository.
- A Rust repository with at least one commit.

There is no separate install step. A policy script declares Smog as a dependency, and `uv run` installs it on first use.

## Run it

Create `scripts/smog_policy.py` in the repository you want to measure:

```python
# /// script
# requires-python = ">=3.13"
# dependencies = ["smog"]
#
# [tool.uv.sources]
# smog = { git = "ssh://git@github.com/calm-purple-walrus/smog.git" }
# ///
from smog import Policy, run

policy = Policy()
policy.function_drop("main", warn_by=0.2, block_at=0.4)
run(policy)
```

Then run it:

```sh
uv run scripts/smog_policy.py --level crate
```

The script exits with 0 if nothing blocks and with 1 if something does. If data for a measurement in the score is missing, it prints no score and exits with 2 (see "The standard selection"). The standard selection holds `codebase.mutation_score`, which needs `--full --mutants tree`; to score runs without it, add `policy.deselect("codebase.mutation_score")`. A crash also exits with 1 and prints a traceback. A ref you name, such as `main` above, must exist in the repository.

To work on Smog from a local checkout, use a path instead, relative to the script:

```python
# smog = { path = "../../smog", editable = true }
```

### Update

Each `uv run` checks GitHub for the latest commit on the default branch, so it needs network access and can pick up a new version without warning. To stay on a fixed version, add `rev = "<commit>"` to the `smog` source. To update, change the commit.

### Slow tools

`--full` runs these on the code being measured, so that code must build. Install them first:

```sh
rustup component add clippy rust-analyzer llvm-tools rustfmt
cargo install --locked cargo-llvm-cov cargo-mutants cargo-geiger cargo-semver-checks cargo-nextest
rustup toolchain install nightly
```

A tool that is missing or fails is listed as not run, and the rest still run. A measurement that needs it then has no value.

Each tool compiles with the toolchain of the repository being measured: its `rust-toolchain.toml`, else the default toolchain. A tool that needs a newer compiler than that is listed as not run with the tool's message. What was observed on 2026-11-11, with Rust 1.92.0 and 1.95.0 installed:

| Tool | Version run | Rust it needs |
| --- | --- | --- |
| cargo-semver-checks | 0.51.0 | 1.93 to install and to run: with rustc 1.92.0 it stops with `rustc version is not high enough: >=1.93.0 needed`. Version 0.49.0 declares 1.91; it was not run |
| cargo-geiger | 0.13.0 | 0.13.0 declares 1.85, was installed with 1.95.0 and ran on code built with 1.92.0 and with 1.95.0. The newest release, 0.14.0, does not install with 1.95.0; `cargo install --locked cargo-geiger@0.13.0` does |
| cargo-llvm-cov | 0.9.1 | declares 1.87; ran with 1.92.0 and 1.95.0 |
| cargo-mutants | 27.1.0 | declares 1.88; ran with 1.92.0 and 1.95.0 |
| cargo-nextest | 0.9.124 | declares 1.89; ran with 1.92.0 and 1.95.0 |
| `shuffle` | libtest | a nightly toolchain |

"Declares" is the `rust-version` of the release on crates.io. No older compiler than 1.92.0 was tried.

cargo-geiger and cargo-semver-checks report per crate. When one of them fails for some crates, such as a crate whose optional dependency cargo has not downloaded, the other crates keep their values and the tool is listed with the number of crates it reported on and the reason it failed.

The cargo tools stay off the network: Smog sets `CARGO_NET_OFFLINE` for every cargo call, also those a tool makes itself. A tool that needs a dependency cargo has not downloaded yet is listed as not run with cargo's message; run `cargo fetch` first, or let cargo download with `policy.setting("cargo_offline", False)`.

**What `--full` writes into the measured repository.** A run without `--full` writes nothing. With `--full`:

- cargo fills the repository's `target` folder: Clippy, `cargo test`, cargo-llvm-cov (`target/llvm-cov-target`), cargo-nextest, cargo-geiger, cargo-semver-checks (`target/semver-checks`) and rust-analyzer build there. The clean build, the shuffled test runs and the message probe build in a temporary folder, and cargo-mutants works on a temporary copy of the tree.
- Where the repository has no `Cargo.lock`, cargo creates one, which then shows up as an untracked file.
- An existing `Cargo.lock` is never changed. Every cargo call passes `--locked` when a lock file exists (cargo-mutants through `--cargo-arg`), also for a crate with a lock file of its own, such as a fuzz crate outside the workspace. A tool that would have to update the lock file is listed as not run with cargo's message. `cargo fmt` and cargo-semver-checks take no such option: if one of them changes a tracked `Cargo.lock`, Smog puts the file back and lists the tool as not run.
- The `reviews` tool adds what it fetches to the reviews file, when the setting `reviews_file` names one.

The environment of the Smog process is not changed: `CARGO_NET_OFFLINE` is set for the tool processes only.

Two tools run the tests again and give values that can differ between runs on the same code. `nextest` runs `cargo nextest run --retries` for `test.flaky`, `test.duration`, `codebase.flaky_tests` and `codebase.slow_tests`; the setting `flaky_test_retries` is the number of retries. `shuffle` runs the tests on one thread in the default order and in one shuffled order per seed of the setting `test_order_seeds`, for `test.order_dependent` and `codebase.order_dependent_tests`; libtest's `--shuffle-seed` is unstable, so it needs the nightly toolchain. The registry note of each of these IDs says that it is not deterministic.

Three crate and module measurements come from these tools. `geiger` runs cargo-geiger once per crate, offline, for `crate.unsafe_in_dependencies`. `semver` runs cargo-semver-checks against the policy's ref for `crate.semver_violations`. `clippy` also runs rustc's `unreachable_pub` lint, which replaces the syntax count of `module.unreachable_pub`. None of these uses the network unless the setting `cargo_offline` is off; only the `reviews` tool does, and `--full` alone does not run it (see Human review).

Mutation testing has two scopes, chosen by the setting `mutants_scope` or by `--mutants`. `diff`, the default, mutates the lines changed against the policy's ref and needs one. `tree` mutates the whole codebase, which takes one build and test run per mutant. Both give each function its missed mutants, timeouts and mutation score (`function.missed_mutants`, `function.mutant_timeouts`, `function.mutation_score`); with coverage they also give `function.pseudo_tested` and `function.coverage`. A timed-out mutant is left out of the mutation score unless the setting `mutation_timeouts_caught` is true.

`codebase.mutation_score` and `codebase.covered_mutation_score` have a value only after a `tree` run. The mutants of a `diff` run describe the change, so they give the codebase no value; with `codebase.mutation_score` in the selection, as in the standard selection, such a run has no score. A `diff` run still gives `codebase.surviving_mutants`, the values of each function and `crate.mutation_score` over the changed lines.

### History

Smog reads the last `history_window` commits (100 by default) on the first-parent line of HEAD with `git`: each commit's parents, time, author name, subject, body and trailers. The first commit of a repository is never one of the measured commits, because it has no earlier state to compare with: a window that reaches it measures one commit fewer. It asks git for no email address; one written in a commit message, such as in a `Signed-off-by` trailer, is part of the message text, which no output prints.

A fix commit is one whose subject matches the setting `fix_commit_pattern`, by default the Conventional Commits type `fix`. For each fix commit, `git blame --first-parent` on its parent names the commits that last changed the lines it removes; `function.szz_fixes`, `file.szz_fixes` and `codebase.bug_introducing_share` are built on that. `codebase.active_branches` counts the branches of the clone, so its value depends on what was fetched. `codebase.merges_per_day` and `codebase.branch_lifetime_days` read merge commits; a history of squashed changes has none.

In a shallow clone, such as the default checkout of a CI job, `git blame` names the oldest commit the clone holds for every older line. So there the three measurements built on blame and the human-review measurements do not run, the overview says so under `not run: git blame`, and the history window ends where the clone ends. Fetch the full history for them (`git fetch --unshallow`, or `fetch-depth: 0` in a GitHub workflow).

### Human review

A policy lists the GitHub logins that count as human:

```python
policy.humans("login-a", "login-b")
```

A code line is human-reviewed when the commit that last changed it (`git blame --first-parent` on the working tree) belongs to a merged pull request that a listed human signed off, by approving it (their latest review is an approval) or by merging it, or when a listed human committed it directly, without a pull request. A commit belongs to a pull request as one of its commits or as its merge or squash commit. A file with the comment `// smog: human-reviewed <commit>` on one of its first lines, such as `// smog: human-reviewed 3f2c1ab`, is human-reviewed as of that commit: the marker covers each line whose last change is that commit or an earlier one, and a line changed later is not covered. The comment line must hold the marker and the hash and nothing else; a marker without a hash covers nothing. Every other code line is unreviewed. `--explain codebase.unreviewed_lines` gives the details and the settings.

The values are `function.unreviewed_lines`, and `unreviewed_lines` and `unreviewed_line_share` for `file`, `crate` and `codebase`. `codebase.unreviewed_line_share` is in the standard selection; the others are not. Without `policy.humans` they have no value and charge nothing.

Once the policy lists humans, a selected review measurement needs review data. If no reviews file is set, the file cannot be read, it does not know a commit, the fetch fails, or the clone is shallow, the data is missing and the measurements have no value. With one of them in the selection, the run prints no score, names the measurement and why its data is missing, and exits with 2.

The review data comes from one of two places:

- `--full --tools reviews` asks the GitHub REST API which merged pull requests each of those commits belongs to and for their reviews. The repository is the `origin` remote. The token is `GITHUB_TOKEN`, else `GH_TOKEN`, else that of a signed-in `gh`; a public repository needs none, within GitHub's limit of 60 requests an hour. A run takes one request per commit and one per pull request.
- `--reviews-file PATH`, or the setting `reviews_file`, reads a JSON file. Every run, also without `--full`, asks GitHub for the commits the file does not know, such as ones made since, and writes the file back, also when the fetch stops part way. A run whose commits are all in the file stays offline and gives the same result, and a fetch cut short by the rate limit continues on the next run. With the `reviews` tool as well, the commits of `reviews_refetch` are asked for again.

The reviews file has this form. `repository` is `owner/name` on GitHub. Every commit is a full hash of 40 characters; a commit that is in no entry is unknown and is fetched or reported as missing. `state` is GitHub's review state, such as `APPROVED`, `CHANGES_REQUESTED`, `COMMENTED` or `DISMISSED`; of each login the latest review by `submitted_at` counts, without the states in `review_ignored_states`. `merged_by` is the login that merged the pull request. `commits_without_pull_request` lists the commits that were looked up and belonged to no merged pull request; `direct_commit_logins` gives the login of the author of each of them, where GitHub knows one.

```json
{
  "repository": "example/parser",
  "pull_requests": [
    {
      "number": 12,
      "merge_commit": "0123456789abcdef0123456789abcdef01234567",
      "merged_by": "login-b",
      "commits": ["89abcdef0123456789abcdef0123456789abcdef"],
      "reviews": [{"login": "login-a", "state": "APPROVED", "submitted_at": "2026-01-15T10:00:00Z"}]
    }
  ],
  "commits_without_pull_request": ["fedcba9876543210fedcba9876543210fedcba98"],
  "direct_commit_logins": {"fedcba9876543210fedcba9876543210fedcba98": "login-a"}
}
```

How the reviews file is refreshed is the setting `reviews_refetch`:

- A commit the file does not know is always fetched.
- `unmerged`, the default: each fetch also asks again for every commit the file records without a merged pull request, one request per commit. Such a record is not final: the file may have been written on a branch whose pull request was still open, or before the commit was pushed.
- `all`: each fetch asks again for every commit and for the reviews of its pull requests. Use it for one run after an approval was dismissed or a review was added: `policy.setting("reviews_refetch", "all")`. Deleting the file has the same effect.
- `none`: only unknown commits are fetched. For a repository with many commits outside pull requests and a tight rate limit.

When GitHub fails while a commit is asked for again, nothing the file holds is lost: the values are computed with the saved verdict of each commit not asked again, and the report names those commits under `not run: reviews, asked again`. A failure while a commit the file does not know is still open gives no value, as before.

A run without the `reviews` tool reads the file as it is.

Smog sends GitHub the repository's owner and name, commit hashes and pull request numbers, and nothing else. The API URL must start with `https://`, and a redirect is followed only to the same host, so the token reaches no other host. Smog keeps the login, state and time of each review and no email address. An answer of another shape than the API documents, a list of more than `reviews_max_pages` pages, an answer cut off, a rate limit or an unreachable host all list `reviews` as not run with the reason. Then the counts have no value, and a selected share is charged as described above.

### Options

| Option | Meaning |
| --- | --- |
| `--level` | `codebase`, `crate`, `module`, `file` or `function`. Lists scores at that level, worst first |
| `--comprehensive` | Prints the full report in place of the overview |
| `--files-by-crate` | Prints each crate, worst first, with every file of it, worst first: score, main problem and policy ID |
| `--report` | Which full report files to write: `both` (default), `text`, `json` or `none` |
| `--failures` | Lists only what failed in the checks. `--failures catch_all_names` limits it to one check |
| `--full` | Also runs the slow tools |
| `--tools` | With `--full`, which to run: `clippy,tests,coverage,mutants,index,build,probe,fmt,geiger,semver,nextest,shuffle`. `reviews` uses the network and runs only when named here |
| `--reviews-file` | A JSON file with pull requests and reviews for the human-review measurements. Overrides the setting `reviews_file` |
| `--mutants` | With `--full`, `diff` or `tree`: what cargo-mutants mutates. Overrides the setting `mutants_scope` |
| `--root` | The repository to analyze. By default, the one that holds the script |
| `--only` | `--only code/domain --only "*-adapter"` reports and scores only the files whose path, folder or crate name matches one of the glob patterns. Can be repeated. See "A part of the codebase" |
| `--explain` | `--explain function.length` says what a policy ID means, whether it is in the selection in force, its numbers in force, how to improve it and how to change it in the policy. A setting name such as `others_share` shows its value in force. With no ID, lists every ID. Does not analyze the repository. An unknown ID exits with 2 and prints the closest IDs |
| `--metric` | `--metric function.length` prints that metric's value for each piece it measures, worst first: the highest value first, or the lowest where the registry says a higher value is better, as for `function.coverage`. If the metric is in the selection in force, it also prints each score and the codebase score. Exits with the usual code, so CI can log it. An unknown ID exits with 2 |
| `--json` | With `--explain` or `--metric`, prints the same data as one JSON document. With `--metric` its field `result` is `passes`, `blocked` or `no score` |

A script does not have to sit in the repository it measures. Pass `root=` to `run`.

### A part of the codebase

`--only PATTERN`, or `policy.only("code/domain", "*-adapter")` in the policy, restricts a run to the files that match one of the patterns. A pattern is a shell-style glob in which `*` also matches `/`. A file matches by its path, by a folder above it or by the name of its crate.

- Smog still measures the whole codebase, because call counts, duplication and other values need all of it.
- Only the matching files and the functions, tests and types in them are listed and scored. A module, a crate and the codebase take their lines and their score from the kept files below them.
- A crate or module that is kept only in part has no values of its own, because those describe the whole of it. So a restricted run has no `codebase.*` value, apart from the median function length of the kept functions, and the overview names each selected `codebase.*` row under `No value in this run`.
- A crate or module of which every file is kept, inline modules included, keeps its values, and its score is that of the whole run.
- Gates judge the kept pieces. The checks and the comparison with a ref still read the whole codebase.
- A floor on a measurement (`policy.metric_floor`) of a piece that is kept only in part cannot be judged: a `codebase.*` measurement, or a crate or module measurement when some files of that crate or module are left out. The floor did not run, and it follows the rule under "Gates" like every other gate: if it blocks, the result is `blocked`, unless the floor has `allow_not_run=True`. A floor that fails on a kept piece fails as in a whole run. `policy.score_floor` judges the score of the kept part.
- Patterns that keep every file, such as `--only "*"`, give the run on the whole codebase.
- A run in which no file matches stops with an error.

## Develop

```sh
git clone git@github.com:calm-purple-walrus/smog.git
cd smog
uv run pytest
```

`SMOG_FULL=1 uv run pytest tests/test_full.py` also runs the slow tools on a fixture crate. `SMOG_PRIVATE_NAMES=name1,name2 uv run pytest` fails if any of those names appears in the code or tests.

## Write a policy

### Choose what is scored

Smog computes and reports every measurement in `smog.REGISTRY`. A measurement lowers the score only if it is in the selection in force. A new `Policy()` starts with the standard selection, `smog.STANDARD_SELECTION` in `src/smog/domain/selection.py`: one row per measurement ID with its target, limit, other curve numbers, group and weight.

| You want | Write |
| --- | --- |
| Add a measurement to the score | `policy.select("function.parameters", target=5, limit=7, group="complexity")` |
| Change numbers of a selected one | `policy.select("function.length", target=50, limit=160, weight=1.0)` |
| Change the curve shape | `policy.select("function.length", power=3.0, knee=2.0)`, or `base=9.0` for an exponential curve, or `low_target=1, low_limit=0` to also charge low values |
| Take one out of the score | `policy.deselect("file.duplicated_line_share")` |
| Replace the whole selection | `policy.use_selection({"function.length": {"target": 40, "limit": 160, "group": "size"}})` |
| Score nothing | `policy.use_selection({})` |

`policy.disable("type.lazy_class", "check.pr_size")` switches measurements or checks off for the repository: they appear in no output, a disabled measurement cannot be selected, and `--metric` and `--explain` say that the policy disabled it. Deselect a measurement before disabling it.

A new row needs `target`, `limit` and `group`. For a row already selected, numbers you leave out keep their value. A check, a diff value and a left-out measurement cannot be selected.

Every other number, word list and expression that decides when a measurement counts something is a named setting in `smog.SETTINGS` (`src/smog/domain/settings.py`), except what [Fixed in the code](#fixed-in-the-code) lists. This covers the scoring settings, the thresholds and word lists inside measurements and the limits of the slop rules. `policy.setting("others_share", 0.2)` overrides one and raises `ValueError` for an unknown name or a value of the wrong kind or out of range; `policy.select` raises for a curve number or weight that would give a negative penalty or switch the row off (`knee=0`, `weight=-1`). `--explain` with no ID lists them, and `--explain` on a measurement or slop rule prints the settings it reads with their values in force.

### Your own conditions

There are three kinds: blocking, warning and metric. Each is a Python function.

```python
@policy.blocking
def no_sleep_in_domain(run):
    for piece in run.functions():
        if "domain" in piece.id and "sleep" in piece.item.text:
            yield piece, "calls sleep"


@policy.warning
def large_crates(run):
    for piece in run.pieces("crate"):
        if piece.lines > 10_000:
            yield piece, f"{piece.lines} lines"


@policy.metric("function.sleep_calls", piece="function", target=0, limit=2, group="custom")
def sleep_calls(function):
    return sum(1 for call in function.calls() if call.name == "sleep")
```

A blocking or warning function takes a `Run` and yields a message, or a pair of a piece and a message. One that returns `True` has one violation, `False` none; one that returns a single string raises `TypeError`. A metric takes one code object (`Function`, `TypeDef`, `SourceFile`, `Module`, `Crate` or `Codebase`) and returns a finite number, `True` or `False` for a yes/no measurement (counted as 1 and 0), or a list of strings, one per problem: the value is their count, and the report prints them where it names the piece. Anything else raises `TypeError`. Its ID must not be that of a built-in measurement. With `target` and `limit` it joins the selection and feeds the score. Without them it is measured and reported only.

### Dependency rules

A rule names a source pattern, a target pattern, and whether it allows or forbids.

```python
policy.dependency_rule("code/adapter/*", "code/domain/*")                 # every adapter may depend on the domain
policy.dependency_rule("code/adapter/*", "code/application/ports/*")
policy.dependency_rule("code/adapter/legacy", "code/domain/*", allow=False, reason="being removed")
policy.check("layer_violations")
```

- A pattern is a shell-style glob in which `*` also matches `/`. It matches a crate by its name, its folder or the path of its `Cargo.toml`, and a file by its path or, seen from another crate, by any of these three names of its crate. A crate or file added later is covered by every rule whose pattern it matches.
- `check.layer_violations` checks each dependency of one workspace crate on another (from `Cargo.toml`, without dev-dependencies) and each `use` of one production file by another.
- The last rule that matches a dependency decides it.
- The default: a dependency between two crates that no rule matches is a violation. A dependency between two files of one crate that no rule matches is allowed, and for such a pair only the file paths are matched.
- Without any rule the check is skipped. It changes the exit code only after `policy.check("layer_violations")`.

### Product rules

Rules that hold for one product only are not built into Smog. Write them as blocking or warning conditions. A `Run` gives you these building blocks, all without test code:

| You need | Use |
| --- | --- |
| Structs and enums by name pattern | `run.types("*Record")`; each has `name`, `qualified`, `file`, `fields`, `public_fields`, `methods` |
| Where a type is named | `run.type_uses("*Record")`, pairs of file and type name |
| Production files by path pattern | `run.files("src/domain/*")`; each has `path`, `root` (the syntax tree), `types`, `functions` |
| Every folder with a tracked file | `run.folders()` |
| Crates and their manifests | `run.codebase.crates` |

```python
@policy.blocking
def no_public_fields_in_models(run):
    for type_def in run.types():
        if fnmatch.fnmatch(type_def.file.path, "src/domain/*"):
            for field in type_def.public_fields:
                yield type_def.qualified, f"field {field.name} is {field.visibility}"
```

The design's rules for attribute structs, public fields in domain models and folder structure are product rules. Smog has no check and no registry row for them; each product writes them this way.

### Built-in conditions

Every method below builds a blocking or warning condition.

| You want | Write |
| --- | --- |
| This selected metric warns at 0.95 and blocks at 0.9 | `policy.metric_floor("function.length", warn_below=0.95, block_below=0.9)` |
| The same for each piece of a kind | Add `piece="function"` |
| Score floors for a level | `policy.score_floor("crate", warn_below=0.8, block_below=0.6)` |
| Block if any function violates a concern | `policy.any_function("function.panic_points", above=0)` |
| The same with a score, or your own test | `policy.any_function("function.length", score_below=0.5)`, `policy.any_function(my_predicate)` |
| Warn at a fall of 0.2 against a ref, block at 0.4 | `policy.function_drop("main", warn_by=0.2, block_at=0.4)` |
| Block a new file below 0.9 and a file that falls from 0.8 or above to below it | `policy.file_drop("main", new_below=0.9, existing_below=0.8)` |
| Block a fall of the codebase score by more than 0.02 | `policy.score_drop("main", block_above=0.02)` |
| This dependency is not allowed | `policy.forbid_dependency("tokio", crates="*-domain")` |
| Warn when a module is added | `policy.warn_added_module("*")` |
| Warn when a struct is added | `policy.warn_added_struct("Manager")` |
| Make a design check fire | `policy.check("no_type_bounds", "block")` |

Checks from section 3.1 of the design that Smog computes are always reported. They change the exit code only if the policy calls `policy.check`.

A gate that cannot fire is an error, and a gate that was not evaluated has not passed:

- `metric_floor`, `any_function` and `score_floor` raise `ValueError` for an unknown or disabled ID, a level whose pieces never hold the measurement (`file.length` on a function), a score of a measurement outside the selection, or a call without a bound. `policy.deselect`, `policy.use_selection` and `policy.disable` raise when a gate declared before them reads what they remove. A run checks the gates again before it measures anything.
- A check made to count with `policy.check`, a floor or an `any_function` gate that did not run is listed in the overview as `did not run` with the reason: `tests_pass` without `--full`, `gate_untouched` without a ref, `layer_violations` without a rule. If the gate blocks, the result is `blocked`. `allow_not_run=True` on `policy.check`, `policy.metric_floor` or `policy.any_function` lists it without failing the result. A floor on a measurement of a piece that a run restricted with `--only` keeps only in part did not run either (see "A part of the codebase").

**Comparison with a ref.** A run compares only with `--changes`, or `--changes REF`; without it, the run measures the code as it is, and the checks on the diff and the conditions against a ref do not apply. Smog compares the working tree with the merge base of the ref and `HEAD`, so a ref that has moved on does not show up as a change. A ref with no local branch or tag of that name is read as `origin/<ref>`, as in a CI checkout of a pull request. A function at or below the block level blocks whenever it gets worse. Both sides are scored without slow tools. They are scored with review data when the run has it and it can be had for the ref too; otherwise neither side is, and the overview says why. With a selected function or test measurement that needs what is left out, such as `function.coverage`, `function_drop` did not run. `file_drop` and `score_drop` compare the two sides as scored. A file judged by `file_drop` is new unless the ref has a file at its path or it was moved or renamed: a file at a path the ref lacks is the moved version of a file gone from its path when at least half of the code lines of the longer of the two are equal (setting `file_match_min_similarity`). A deleted file is not judged.

**The policy as a gate.** The policy that judges a change is the script in the working tree, so a change can edit it. When the policy names a ref, Smog compares the policy script with the same file at the merge base:

- A policy script that differs is named in the overview (`Policy script ... differs from main`), with what the run enforces differently from the policy of the ref: gate files, gates with their numbers, rows of the selection, settings and the other lists of the policy. `check.gate_untouched` fails for it, whether or not the script matches a `policy.gate_files` pattern, and blocks after `policy.check("gate_untouched")`.
- `check.gate_untouched` takes its gate files from the policy as it is at the ref, so a change cannot take a file off the list and edit it. To read them, Smog runs the script of the ref in a process of its own, with `run` replaced so that it measures nothing.
- When the ref has no such script, or its policy cannot be loaded, the gate files are those of the policy as it is now, and the overview says so.
- The body of a function the policy defines itself (`policy.blocking`, `policy.warning`, `policy.metric`, `policy.score_function`) is not compared; the changed file is still reported. A module the policy script imports is compared only if it is a gate file.
- From Python, `smog.analyze(policy, root, policy_script="scripts/smog_policy.py")` does the same; without `policy_script` only the gate files of the policy as it is now are checked.

This reports a weakened policy; it does not stop a policy that drops its ref, because then there is no comparison at all. For a gate a change cannot open, CI must take the policy from the base ref and not from the change:

```sh
git show origin/main:scripts/smog_policy.py > "$RUNNER_TEMP/smog_policy.py"
uv run "$RUNNER_TEMP/smog_policy.py" --root .
```

Which function of the working tree is which function of the ref does not depend on its position in the file. A function is matched:

1. by its file, the modules, functions and `impl` header around it, its name and its `cfg` attributes. A second definition of the name under another `cfg`, or in another file, does not take its place.
2. by the same place with other `cfg` attributes.
3. by the same surrounding items, name and signature in another file, when there is one such function on each side: a file that was moved or renamed.
4. by its body, whatever its name and file: equal tokens, or at least 70% of the lines of the longer body equal with names and literals normalized (setting `function_match_min_similarity`).

A function without a match is new. A new function never counts as fallen, so a function rewritten under a new name passes `function_drop` at any score. `policy.function_drop("main", new_functions=True)` also blocks a new production function that scores at or below `block_at`; `policy.metric_floor` and `policy.any_function` judge every function, old or new. Two definitions of one name in one file have their own history values.

### Settings

| Setting | Write |
| --- | --- |
| Any named setting | `policy.setting("worst_items_in_file", 3)` |
| The ref for diff metrics | `policy.against("main")` |
| Names of layers, for `diff.layers_touched` | `policy.layer("domain", "code/domain/*")` |
| Files only humans may change | `policy.gate_files(".github/*")`. The policy script itself is always one, see "The policy as a gate" |
| PR size limit | `policy.pr_size(lines=1000, files=50)` |
| Allowed new suppressions | `policy.suppression_exceptions("dead_code")` |
| Dependencies the unused check skips | `policy.ignore_unused_dependencies("serde")` |
| Effective length weight | `policy.effective_length(alpha=0.5)` |
| Commits read for history | `policy.history_window(100)` |
| GitHub logins that count as human reviewers | `policy.humans("login-a", "login-b")` |
| Files to skip | `policy.exclude("code/generated/*")` |
| Report and score a part of the codebase | `policy.only("code/domain", "*-adapter")` |
| Slop rules off, or paths exempt | `policy.slop_allow("meta-seam")`, `policy.slop_exempt("docs/research/*")` |
| The severity of one slop rule | `policy.slop_severity("meta-seam", "metric")`, and for a rule that also fires at a limit `policy.slop_severity("len-words", "metric", at_limit="metric")`. A slop rule warns or only reports: slop never blocks, since no rule detects it reliably |
| The patterns, exceptions or scope of one slop rule | `policy.setting("slop_rule_meta_seam", {"exceptions": [r"\bweld seams?\b"]})` |
| A word list of the slop rules | `policy.setting("slop_list_vocab_weak", ["crucial", ("leverage", "use")])` |
| How a penalty becomes a score | `policy.score_function(lambda penalty: 1 / (1 + penalty))` |

Outside the selection, every number, word list, expression and severity that is a rule is a named setting; [Fixed in the code](#fixed-in-the-code) lists what is not. `--explain` with no ID lists the settings with their values in force; `--explain <setting>` prints one. `policy.setting` checks each value when it is set and raises `ValueError` for one that would end the run or switch a rule off without saying so:

- a value of the wrong kind, a misspelt severity, rule ID or choice, and a key a rule does not read;
- a number outside its range: a fraction where the code counts or compares for equality (a whole number is an `int`, so `3.0` is refused), a unit or `score_decay` of 0, a minimum of 0 where the run would divide by it;
- a regular expression that does not compile or that matches the empty text, an empty text in a list, and an empty marker or URL;
- an empty list where a slop rule matches with it. `policy.slop_allow` turns a rule off. A word list of a measurement, such as `debug_macros`, may be empty: the measurement then finds nothing.

The slop rules are settings generated from the rule data, in three forms:

- `slop_rule_<id>` (the rule ID with `_` for `-`) holds the parameters of one rule as a mapping: `severity`, `limit_severity` for the five rules that report each hit and fire again at a limit, `patterns` and `exceptions` with their quantifiers, and `comments_only`. A rule has only the keys its code reads, and `--explain slop_rule_<id>` names them. Give the keys to change; the others keep their value. To change a quantifier, give the pattern with the new quantifier. An exception excuses the matches it overlaps, so `weld seams?` excuses the seam of a weld seam and not a second seam in the sentence; `.*word.*` excuses the whole sentence.
- `slop_list_<name>` holds one word list. An entry is a regular expression, or a list of the expression, a replacement to suggest and a source.
- `slop_number_words`, `slop_abstract_nouns`, `slop_homonyms` and the lists the rules read in their code (`slop_coordinators`, `slop_abbreviations` and others) are plain lists. The abstract nouns and the homonyms hold regular expressions; the others hold words, matched as they are written.

### Fixed in the code

These are not settings. Each group is parsing or the structure of a formula, not a threshold or a word list of a rule, with one exception at the end.

- **The shape of the score.** A group charges its worst measurement plus a share of the others, groups add up, and a piece's score is its own score times the score of its contents. `policy.score_function` replaces the last step; the numbers are settings or selection rows.
- **The structure of published formulas.** Halstead, ABC, cyclomatic and cognitive complexity, LCOM4, TCC, PageRank, the form of the Maintainability Index, ARI and Flesch (their coefficients are settings), the factor 2 in `diff.moved_line_share`, the nesting rule of Clippy's `type_complexity` (its four scores are settings), and `function.panic_sites` as the sum of three Clippy lints.
- **How prose is found.** The expressions in `slop.py` that find code spans, links, quotes, list items, tables, directives, code-like lines, compiler output, bullets, words, sentence ends and syllables, and the fields of a slop rule that say which code runs it on which form of the text (`class`, `kind`, `scope`, `strip`, `source`).
- **Rust and Cargo.** The syntax node kinds; what `cfg(test)` means; `mod.rs`, `lib.rs` and `main.rs`; where Cargo looks for the root file of a target; the built-in names a measurement is defined by (`#[should_panic]`, `#[ignore]`, `panic!`, `catch_unwind`, `bool`, `Option`, `Self`, `Result<()>`); that an assertion is a macro with `assert` in its name, and where its message starts.
- **Formats of other tools.** The output of git, cargo, Clippy, cargo-nextest, cargo-llvm-cov, cargo-mutants, cargo-semver-checks, cargo-geiger and the GitHub API, the paths of cargo-vet, and the list of tools.
- **Not rules.** 86,400 seconds per day, 12 months per year, the 30-second HTTP timeout, the length of a printed commit hash and of a tool's error text, the hash base of the duplication search, the 2 passes of the data-flow walk.
- **One rule that is still fixed.** Folder churn leaves out files whose path ends in `tests.rs`.

### Not built

Eight measurements of the list are in the registry with the status `left out`. Smog computes no value for them, and `--explain <ID>` gives the reason.

| ID | Measurement | Why it is not built |
| --- | --- | --- |
| `codebase.balanced_coupling` | Balanced-coupling score | Needs every reference classified by strength. cargo-coupling does that in 2,660 lines and gives a score per coupling and per project, none per module. |
| `codebase.technical_debt_ratio` | Technical debt ratio | Needs a time estimate for the fix of each finding. Smog has none; its debt is a sum of penalties. |
| `test.checked_coverage` | Checked coverage | Needs a test run with dynamic slicing from each assertion. Smog has no tool for that. |
| `codebase.working_commits` | Working commits | Needs a build and a test run for every commit of the history window. |
| `codebase.imperative_subjects` | Imperative mood of commit subjects | Needs a part-of-speech tagger or a list of verbs. |
| `codebase.deployment_measures` | Time from commit to deployment, share of deployments that need a fix | The data is in a deployment system, not in the repository. |
| `codebase.message_content` | Message content | Needs a trained classifier. |
| `file.comment_code_inconsistency` | Comment–code inconsistency | Needs a trained classifier. |

Six more are left out for a reason the registry states: `check.security_advisories`, `type.memory_layout`, `codebase.dependency_age`, `test.redundant`, `test.behavior_probe` and `test.breakage_rate`.

## How scoring works

Only measurements in the selection in force are scored. Each turns its value into a penalty through its curve: `((value - target) / (limit - target))^power` above the target, times its weight, and a straight line past the knee. With the default numbers the power is 2 and the knee is 3 target-to-limit distances past the target. Measurements in a group are correlated, so a group charges its worst measurement plus a share of the others (`others_share`, default 0.1). Groups add up, and `score = exp(-score_decay * penalty)` with `score_decay` 1 by default.

| Piece | Score |
| --- | --- |
| Function, test, type | `exp(-penalty)` |
| File | Its own penalty as a score, times the mean of its worst items (`worst_items_in_file`, default 5; `worst_items_combine`, default `mean`) |
| Module, crate, codebase | Its own penalty as a score, times the line-weighted mean of what it contains (`aggregate_weight`, default `lines`). A piece without code lines, such as a comment-only file, weighs one line (`aggregate_min_lines`) |

Every step is a setting. `worst_items_combine` also takes `geometric_mean` and `min`; `aggregate_weight` also takes `equal`. A policy can replace the step from penalty to score with its own function, which must return 1 for no penalty and a number from 0 to 1 otherwise:

```python
policy.score_function(lambda penalty: 1 / (1 + penalty))
```

Still fixed, because they are the shape of the model and not a number: a group charges its worst measurement plus a share of the others, the groups of a piece add up, and a piece's score is its own score times that of what it contains. The power 2 and the knee 3 are the defaults of a selection row, and each row can state its own (`policy.select(..., power=, knee=)`).

A function, struct, enum or impl declared inside a function body, or in the block of a `const _: () = { ... };`, is a piece of its own, named after the function around it (`crate::outer::inner`). The function around it counts only its own code: its length, statements, complexity, nesting, paragraphs and every other value leave the item out, and a changed, covered, mutated or unreviewed line inside the item belongs to the item. A closure stays part of the function that holds it.

Effective length counts private one-caller helpers at half weight, so splitting a function does not hide its length. The line-weighted median is the function length at which half of all lines sit in shorter functions.

### The standard selection

| Measurement | Counted on | Target | Limit | Group | Where the numbers come from |
| --- | --- | --- | --- | --- | --- |
| `function.length` | function | 40 | 100 | size | Target: the owner's number. Limit: Clippy `too_many_lines` |
| `function.paragraph_penalty` | function | 0 | 40, straight line | size | A choice: one paragraph of 40 lines gives penalty 1 |
| `function.cognitive` | function | 15 | 35 | complexity | Target: SonarSource and PMD default. Limit: a choice |
| `function.nesting` | function | 3 | 6 | complexity | Target: PMD default. Limit: a choice |
| `type.fields` | type | 15 | 40 | size | Target: PMD `TooManyFields`, a Java rule. Limit: a choice |
| `file.length` | file | 800 | 4,000 | size | A choice |
| `file.slop_findings` | file | 0 | 20 | comments | Every slop finding in a Rust file lowers the score, as in documents. The earlier target 2, chosen so that no measured codebase had more than a quarter of its files lose more than 5%, let one or two findings per file cost nothing |
| `file.duplicated_line_share` | file | 0.03 | 1.0 | duplication | Target: SonarQube gate. Limit: the whole file is a copy |
| `module.files_per_folder` | module | 25 | 120 | layout | A choice |
| `module.subfolders_per_folder` | module | 15 | 80 | layout | A choice |
| `crate.modules` | crate | 100 | 400 | size | A choice |
| `codebase.tests_per_100_lines` | codebase | 2 to 15 | 0 and 40 | tests | A choice. Charged below 2 and above 15 |
| `codebase.doc_slop_findings` | codebase | 0 | 750 | documents | Chosen from measured distributions: the worst of five codebases, with 503 findings, gets penalty 0.45 |
| `codebase.mutation_score` | codebase | 0.8 | 0 | tests | A choice. Charged below 0.8 |
| `codebase.unreviewed_line_share` | codebase | 0 | 1.0, straight line, weight 0.1 | review | Limit: every line is unreviewed. Weight 0.1, because every uncommitted line counts as unreviewed: at weight 1, any change lowered the score until it was signed off, even one that improved the code |

Every weight is 1. No number is validated on Rust code, so none is evidence that a value is right. Treat the standard selection as a starting policy.

Churn, `function.cyclomatic` and `type.methods` are measured and reported, and are not in the standard selection.

A selected measurement without a value because there is nothing to measure, such as `type.fields` in a codebase without a type or a review measurement without `policy.humans`, charges nothing; `--comprehensive` names each one under `No value in this run`, with the reason.

A selected measurement without a value because its data is missing, such as `codebase.mutation_score` without a whole-tree mutation run or a review measurement without review data, makes any score wrong. The run then prints `No score: data for these measurements in the score is missing.` with each such measurement and the reason, and exits with 2 (result `no score`). Conditions that inspect source, completed checks or available individual metrics still run and report findings. Overall score conditions cannot run and report that explicitly. `--metric` still prints the values. To score runs without that data, deselect the measurement.

## Limits

- **Macros.** tree-sitter does not parse inside macro calls. Smog sees their tokens, so it counts names and panic methods there, but no structure. A measurement that reads the syntax of a body, such as `function.return_points`, `function.abc`, `test.cognitive` or `type.wmc`, therefore gives another value for the same code inside a macro call; each has the status `approximate` and `--explain` gives this reason. Items a macro generates are not measured, and a function written inside a macro call, such as `item! { pub fn f() { ... } }`, is no piece: no function gate sees it. To guard that route, limit the lines inside macro calls. `function.macro_lines` and `function.macro_line_share` count the code lines of a function on which a macro call or a `macro_rules!` definition stands; `file.macro_lines` and `file.macro_line_share` count them for the production code of a file, also outside every function. Neither is in the standard selection. For example `policy.any_function("function.macro_lines", above=20)`, or a rule on `piece.value("file.macro_line_share")` over `run.pieces("file")`. A one-line call such as `println!(...)` counts as one line.
- **Test code.** Only this is test code: a file below the `tests` folder of its crate; every item under `#[cfg(test)]`, or under a `cfg(all(...))` with `test` among its members (a module, function, `impl`, `use` or type); the file behind `#[cfg(test)] mod name;` with the folder of that name; and a function with a test attribute (setting `test_attributes`). It counts as test lines, not production lines; its functions are test pieces, its types are no pieces, and duplication and clone detection leave it out.
  - Code under any other `cfg` is production code: `cfg(any(test, feature = "x"))` is also built without tests, and `cfg(not(...))` and features are not evaluated.
  - A file name alone does not make test code. `src/test_support.rs` or `src/tests.rs` behind a plain `mod` declaration is built into the product, so its functions meet every gate. A repository that keeps test-only files under such names without `#[cfg(test)]` on the `mod` can name them, and so can one with a crate that only supports tests: `policy.setting("test_file_patterns", ("*/test_*.rs", "crates/test-support/*"))`, glob patterns matched against the path from the repository root.
  - Files in `benches` and `examples` are production code: they count in production lines, in the divisor of the test density and as unreviewed lines.
  - A `#[path]` attribute on a `#[cfg(test)]` module is not followed.
- **Checks against weakening.** `check.new_suppressions` reads the text of added lines: lint and test attributes in Rust files, also inside `cfg_attr`, and a lint set to `allow` in a `Cargo.toml`. It does not see a `clippy.toml`, a lint flag on the command line, or `#[cfg(any())]` on a test; `check.tests_in_build` finds the last with `--full`. `check.tests_not_weakened` counts assertion macros and `check.assertion_strength` reads their kind, so an assertion that cannot fail (`assert_eq!(x, x)`, `assert_eq!(100, 100)`) or is never reached (inside `if false`, after `return`) still counts; `test.smell.redundant_assertion` reports the first kind as a value.
- **Test smells.** tsDetect lists 19 rules for Java and JUnit. Smog has 15 `test.smell.*` measurements and `test.no_assertion`, which is tsDetect's Unknown Test. Three rules have no ID because they have no meaning in Rust: Constructor Initialization and General Fixture need a test class with a constructor or a `setUp` method, and Default Test names the files Android Studio creates.
- **Names.** `function.naming_flaws` checks the number of words in a name and capital letters. It does not check names against a dictionary: Smog ships no word list.
- **Modules.** A module is a crate root, a file module or an inline `mod` block outside test code; file modules are known by their path, whatever a `#[path]` attribute says. `check.module_path_overrides` fails once per `#[path]` attribute and once per `include!` of a `.rs` file; `policy.check("module_path_overrides")` makes it block. The module measurements on dependencies (`module.afferent`, `module.efferent`, `module.instability`, `module.cycle_size`, the centralities) read a module-use graph built from `use` paths and qualified paths, so a re-exported item counts for the module that re-exports it.
- **Exports.** Which `pub` items a crate exports is read from `pub mod` and `pub use` syntax. This feeds `module.unreachable_pub`, `crate.public_api_items`, `crate.documentation_coverage`, `crate.example_coverage` and `crate.exposed_dependencies`; a type that reaches other crates only through a signature is not seen as exported.
- **Dependency trees.** `crate.dependencies_total`, `crate.dependencies_total_dev`, `crate.duplicate_versions` and `crate.audited_dependency_share` read Cargo.lock, which lists the packages of every platform and feature. The counts are therefore upper bounds of what one build uses, and the same on every machine.
- **Name resolution.** Without `--full`, Smog resolves names by matching text. These metrics have the status `approximate`. With `--full`, the rust-analyzer index replaces this for function dependencies and effective length. The comparison with a ref always uses names, so both sides match.
- **Metric status.** Every metric in sections 3.1 to 3.10 of the design is in `smog.REGISTRY` with a status, except three rules a product writes in its own policy and six measurements of a pull request on GitHub (checks, review rounds, approval speed, lines after approval, duplicates, description), which are out of scope. The status is shown in every run: computed, approximate, full-only or left out with the reason. The registry does not say whether a metric is scored.
- **History.** One commit on the first-parent line stands for one PR, which assumes squash merges.
- **Slop rules.** The rules come from `docs/research/2026-11-08-slop-detection.md` and are a style policy. They make no claim about who wrote a text. No rule has been measured on a labeled sample, and some regexes passed through a summarizing tool before they reached the research file. Every severity is a placeholder until replayed on real history. Lists derived from Wikipedia and vale-signs-of-ai-writing are under CC BY-SA 4.0.

## Layout

| Package | Holds |
| --- | --- |
| `smog.domain` | Code models, curves, scoring, metrics, the standard selection, settings, policy, slop rules. Standard library only |
| `smog.ports` | What the application needs from outside |
| `smog.application` | The analysis use case |
| `smog.adapter` | tree-sitter, git, Cargo files, the slow tools, console output |
| `smog.infrastructure` | Wires the adapters and runs a policy script |

`tests/test_architecture.py` enforces the import directions and that domain classes have no public fields.
