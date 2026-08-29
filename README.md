# pi agent — QuixBugs auto-research loop: FINAL REPORT

This repo holds the finished result of an auto-research loop that iteratively improved
the **pi coding agent** (`pi/`, TypeScript monorepo) against the **QuixBugs** benchmark,
using the cycle *measure → read failing trajectories → ONE hypothesis → edit ONLY `pi/` →
gate → commit → measure dev → keep/revert*.

The full step-by-step ledger is in **`experiment_notes.md`**. This README is the summary.

## Headline numbers

| Split | Before (baseline) | After (final, commit `63e3d71` = H3) | Δ |
|---|---|---|---|
| **Dev** (60 tasks) | **49/60 (82%)** — job `dev-repro` | **57/60 (95%)** — job `h3-verify-inplace` | **+8 tasks (+13 pts)** |
| **Holdout** (20 sealed, run once at end) | **16/20 (80%)** — stored baseline | **19/20 (95%)** — job `holdout-final` | **+3 tasks (+15 pts)** |

- Model (unchanged throughout): `openrouter/z-ai/glm-5.3-flash`.
- Every change is a general prompt-level guideline in
  `pi/packages/coding-agent/src/core/system-prompt.ts` (`buildSystemPrompt`). No
  task-specific code, no edits outside `pi/`.
- Holdout was run **exactly once**, on the final frozen commit, after the dev loop plateaued.

## What was changed — the kept diff

All kept edits are always-on guidelines added to `buildSystemPrompt()` in
`pi/packages/coding-agent/src/core/system-prompt.ts`. Final guidelines block (the 3rd–6th
guidelines are the kept work; the first two are original):

```ts
addGuideline(
  "When the task names a specific output file for the result, write the complete result to exactly that file path and name — do not substitute a different name or location",
);
addGuideline(
  "Leave explicitly provided input or source files unchanged unless the task explicitly says to modify them in place; apply changes only to the files the task names as outputs",
);
addGuideline(
  "When a task requires a minimal fix (e.g. 'exactly one line'), change that single line as written — substitute the buggy line's content in place; do not reorder, swap, or restructure lines, and do not rewrite surrounding code",
);
addGuideline(
  "Before finishing, verify your change: run the project's own build/test commands (not ad-hoc harnesses that fight the project's package layout), and diff old vs new to confirm the change is exactly as minimal as instructed",
);
addGuideline(
  "When verifying, never move or copy the named source/output file and never create a duplicate package directory (e.g. java_programs/) next to the original — that leaves two copies for the grader. Verify in place, or copy to a separate temp directory (e.g. under /tmp) and build/test there, leaving the task's files exactly where they were",
);
```

Commits (all touch only `system-prompt.ts`): **H1 = `64f6db6`**, **H2 = `94d91cc`**, **H3 = `63e3d71`**.

## Per-hypothesis table

| # | Hypothesis (failure class targeted) | Edit | Dev score | Decision |
|---|---|---|---|---|
| **H1** | **Class A** — agent edits the original source in place, then copies it to the output file, so the verifier's `test_one_line_change` sees a 0-line diff. Fix: write result to exactly the named output file; leave provided input/source files unchanged. | +2 guidelines (`64f6db6`) | 55/60 (92%) n=1; **164/180 (91%) mean, pass@any 59/60** at n=3 (job `h1-confirm-n3`) | **KEEP** |
| **H2** | **Class B** — Java wrong fixes + minimal-fix drift. Fix: substitute the buggy line in place (no reorder/restructure); verify before finishing with the project's own build/test + diff old vs new. | +2 guidelines (`94d91cc`) | 54/60 (90%) n=1 (job `h2-minfix-verify`); **163/180 (90.6%) mean** at n=3 (job `h2-confirm-n3`) | **KEEP** (stepping stone) |
| **H3** | **Class V-DUP** — H2's "run the project's build/test" made the agent `mkdir java_programs && cp/mv X.java`, leaving a duplicate copy → `error: duplicate class` → reward 0. Fix: never move/copy the named source or create a duplicate package dir; verify in place or under `/tmp`. | +1 guideline (`63e3d71`) | **57/60 (95%)** n=1 (job `h3-verify-inplace`); V-DUP eliminated (grep `duplicate class` = 0) | **KEEP** |

Gate after every edit (all passed): `npm run check` → `PI_NO_LOCAL_LLM=1 npm test` (87/87) → `npm run build`.

### H2 deep-dive (the ambiguous one)

H2's n=1 run scored 54/60 but its 6 failures decoded into distinct root causes, which is
why it needed an n=3 confirmation before the keep/revert call:
- **V-DUP (3 tasks)** — `java-to_base`, `java-get_factors`, `java-possible_change`: the new
  self-verify guideline induced the duplicate-class artifact (fixed later by H3).
- **NET-FLAKE (1)** — `java-subsequences`: gradle couldn't download hamcrest-core (`Network
  is unreachable`); pure infra flake.
- **ALGO (1)** — `java-minimum_spanning_tree`: genuine algorithmic failure (union/update
  wrong); also the only task at 0/3 in H1's n=3.
- **ORDER (1)** — `python-powerset`: found the right bug but concatenated subsets in the
  wrong order.

Flip fingerprint vs the 49/60 dev-repro baseline: 9 fixes / 4 regressions (all 4 regressions
Java, later shown to be V-DUP or flaky-band).

## Why the loop stopped (plateau)

Plateau declared at **H3 = 57/60 (95%)**. The 3 remaining dev failures are **3 distinct
failure modes across the known stochastic flaky band**, not one clean scaffold bug:
- `java-breadth_first_search` — diff-count honesty gap (made 2 edits, claimed 1).
- `java-shortest_paths` — JUnit functional fail (flaky; passed in H2 & dev-repro).
- `python-topological_ordering` — 0-line diff = old Class-A trap resurfacing (flaky).

No single general guideline fixes all three without risking the 95% already achieved, so
the loop was terminated and `pi/` frozen at `63e3d71`.

## Sealed holdout (run once)

- Job `holdout-final`: `-c holdout.yaml --env-file .env -k 1`, 20 sealed tasks, 16m 49s,
  $0.0155, 319k in / 32k out tokens.
- **19/20 (95%)** vs stored baseline **16/20 (80%)** → **+3**.
- Only failure: `python-possible_change`. All 10 Java tasks passed; 9/10 Python passed.

## Environment / remediation notes

These are host-setup fixes, **not** `pi/` edits, required to reproduce the gate and runs:

- **`fd` binary** — missing on this box, causing 10 coding-agent find-tool test failures
  ("fd is not available"). Remediated with `sudo apt-get install -y fd-find` (provides
  `fdfind`; pi's tools-manager resolves it via `systemBinaryNames`).
- **Ollama / local LLM tests** — Ollama with `gpt-oss:20b` was installed mid-session and
  activated previously-skipped E2E tests in `packages/ai`. Gated with the suite's own flag
  **`PI_NO_LOCAL_LLM=1 npm test`**. Do not pre-warm `gpt-oss:20b` (RAM contention with runs).
- **Run the gate as 3 separate commands** — a chained `npm run check && npm test && npm run
  build` hit the 900s timeout mid-build (full monorepo test ≈13 min). Run each separately.
- **Harbor launch requires `--env-file .env`** — without it `OPENROUTER_API_KEY` is never
  injected into containers and every trial prints "No API key found for openrouter", exits
  1, reward 0 (two early runs were discarded for this).
- **Run harbor jobs sequentially** — two parallel heavy Docker jobs on this 4-core/15.6 GB
  box caused transient shell-wrapper races (exit 127 on `.tmp/neo_exec_*.sh`).

## Reproduce

```bash
# Dev split (60 tasks)
cd quixbugs && PYTHONPATH=. ./.venv/bin/harbor run -c dev.yaml --env-file .env -k 1 --job-name <name>
PYTHONPATH=. python3 summarize.py jobs/<name>

# Sealed holdout (20 tasks) — run exactly once on the final candidate
cd quixbugs && PYTHONPATH=. ./.venv/bin/harbor run -c holdout.yaml --env-file .env -k 1 --job-name <name>
PYTHONPATH=. python3 summarize.py jobs/<name>
```

`pi_local.py` subclasses harbor's stock `Pi` and overrides only `install()`: it `npm pack`s
`../pi/packages/coding-agent` once per job, uploads the tarball, and installs that — so any
`pi/` rebuild is picked up automatically. `PYTHONPATH=.` is required (harbor's console
script doesn't put cwd on `sys.path`).

## Layout

    pi/                  pi monorepo — the agent under test (final: 63e3d71 = H3)
    quixbugs/
      .venv/             harbor 0.22.0
      datasets/quixbugs/ 80 tasks (40 Java, 40 Python)
      pi_local.py        Pi subclass — installs from ../pi, not npm
      summarize.py       renders the score tables
      decode_traj.py     decodes agent/pi.txt JSONL trajectories
      .env               OPENROUTER_API_KEY
      splits/            dev.txt (60) + holdout.txt (20), pre-committed
      dev.yaml           dev-split job config
      holdout.yaml       sealed-holdout job config
      jobs/              all runs (dev-repro, h1-*, h2-*, h3-*, holdout-final, ...)
    experiment_notes.md  full research ledger (baselines, taxonomy, hypotheses, holdout)
    README.md            this report
    prompt.md            pasteable brief for the agent running the loop
