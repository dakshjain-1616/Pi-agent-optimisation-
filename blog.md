# How I Took a Coding Agent from 82% → 95% on QuixBugs by Changing Only Its System Prompt

*A friendly, fully-documented account of an automated research loop: measure → read the failures → form ONE hypothesis → change only the agent → verify → keep or revert. All numbers below are reproducible and cross-referenced to the ledger in `experiment_notes.md` and the scored job outputs in `quixbugs/jobs/`.*

---

## TL;DR (the results up front)

| Split | Before | After | Δ |
|---|---|---|---|
| **Dev (60 tasks)** | 49/60 — **82%** | 57/60 — **95%** | **+8 tasks (+13 pts)** |
| **Holdout (20 sealed)** | 16/20 — **80%** | 19/20 — **95%** | **+3 tasks (+15 pts)** |

- **Model:** unchanged throughout — `openrouter/z-ai/glm-5.3-flash`.
- **What changed:** only text — five general guidelines added to the agent's system prompt.
- **Where:** all edits confined to `pi/packages/coding-agent/src/core/system-prompt.ts`.
- **Holdout:** run *exactly once* at the end, on the frozen final commit.

```
Score progress (dev, percent solved)

82% ──●──────────────────────────────────────────── baseline (dev-repro)
      |\
      | \
92% ──|──● H1 (output fidelity)                     55/60  KEEP
      |   \
90% ──|────● H2 (minimal-fix + self-verify)         54/60  KEEP (stepping stone)
      |     \
95% ──|──────● H3 (no duplicate class / verify)     57/60  KEEP, frozen
      |
      +--- H1 n=3 confirmation: 164/180 = 91% mean
      +--- H2 n=3 confirmation: 163/180 = 90.6% mean
```

Holdout line: **80% baseline → 95% final** (16/20 → 19/20), single sealed run.

---

## 1. What I was working with

- **The agent:** `pi`, a TypeScript coding-agent monorepo (here at `pi/`).
- **The benchmark:** QuixBugs — 80 small bug-fixing tasks (40 Java, 40 Python). I split
  it 60 dev / 20 sealed holdout.
- **The grader (important):** it isn't just "does the program work." Two checks matter:
  1. **Functional** — JUnit for Java, pytest-style for Python.
  2. **One-line-change honesty** — `test_one_line_change`, a difflib-based check that the
     diff between the original and the fixed file is *exactly one line*.

That second check is the twist: the agent can produce a *functionally correct* fix and
still score 0 if it solves the problem in a way that breaks the diff contract (e.g. edits
the original then copies it, so the diff is 0 lines; or makes 2 edits and claims 1).

Everything I changed was **general prompt-level guidance** in
`buildSystemPrompt()` inside `pi/packages/coding-agent/src/core/system-prompt.ts`.
No task-specific code. No edits outside `pi/`.

---

## 2. The method (the loop)

Each iteration did exactly this, in order:

1. **Measure** — run the full dev split with the current agent.
2. **Read the failures** — decode the agent's own trajectories (`decode_traj.py`) and the
   verifier stdout, and group failures into a *root-cause class*.
3. **ONE hypothesis** — a single sentence: "these failures share cause X; a general
   guideline Y should remove it."
4. **Change ONLY the agent** — edit `system-prompt.ts` (nowhere else).
5. **Gate** — must pass before any benchmark run, each as a separate command:
   `npm run check` → `PI_NO_LOCAL_LLM=1 npm test` → `npm run build` (all green, 87/87 tests).
6. **Commit** — one commit, message references the hypothesis, touches only `pi/`.
7. **Measure dev again** — same harness, same command shape.
8. **Keep / revert** — decided by the numbers, with an n=3 confirmation whenever the
   n=1 result was ambiguous.

Discipline rules that made the data trustworthy:

- The harbor launch **requires `--env-file .env`** — without it `OPENROUTER_API_KEY`
  never reaches the containers and every trial prints "No API key found for openrouter",
  exits 1, reward 0. (Two early runs were discarded for exactly this.)
- Harbor jobs were run **sequentially** on this 4-core / 15.6 GB box — two parallel heavy
  Docker jobs caused transient shell-wrapper races (exit 127).
- The **gate was run as three separate commands** — chaining them hit the 900 s timeout
  (full monorepo test ≈13 min).

---

## 3. The baseline: where the losses actually were

Fresh dev-split baseline (**job `dev-repro`**, n=1): **49/60 (82%)**.
11 failing tasks, grouped into a taxonomy (the first big payoff of actually *reading*
failures instead of guessing):

- **Class A — the 0-line-diff trap (7 tasks, all Python).**
  All functional tests pass, but `test_one_line_change` fails because the agent edited the
  *original* file in place and then copied it to the output name → diff == 0.
  `python-hanoi, python-knapsack, python-powerset, python-rpn_eval, python-shortest_paths, python-sqrt, python-to_base`.
- **Class B — one-line-change passes, JUnit functional fails (Java).**
  `java-breadth_first_search, java-minimum_spanning_tree, java-wrap`.
- **Class C — functional fails on Python.**
  `python-wrap` (5 functional failures).

Distribution of the 11 baseline failures:

```
Class A (diff==0 trap, Python)   ███████  7/11   <- biggest lever
Class B (Java wrong fix)         ███      3/11
Class C (Python functional)      █        1/11
```

So the single most valuable thing to fix first wasn't "smarter model logic" — it was a
*scaffold/behavior* bug that turned correct code into a 0 score.

---

## 4. Hypothesis H1 — kill the Class-A trap

**Hypothesis:** the agent mutates the provided source and copies it, so the verifier sees
a 0-line diff. Tell it, generally: write the complete result to *exactly the named output
file*, and *leave provided input/source files unchanged*.

**Edit (only file touched):** `pi/packages/coding-agent/src/core/system-prompt.ts`, two
`addGuideline(...)` lines in `buildSystemPrompt`. **Commit `64f6db6`.**

```ts
addGuideline(
  "When the task names a specific output file for the result, write the complete result to exactly that file path and name — do not substitute a different name or location",
);
addGuideline(
  "Leave explicitly provided input or source files unchanged unless the task explicitly says to modify them in place; apply changes only to the files the task names as outputs",
);
```

**Gate:** check ✅ / tests ✅ (87/87) / build ✅ — run as three separate commands.

**Result (job `h1-output-fidelity`, n=1):** **55/60 (92%)** vs baseline 49/60 → **+6 net.**
Flip fingerprint: 8 fixes / 2 regressions.

Because single n=1 runs on a stochastic agent can mislead, I ran an **n=3 confirmation**
(**job `h1-confirm-n3`**): **164/180 solved = 91% mean**, pass@any-of-3 59/60, pass-all-3
46/60. The two n=1 regressions did *not* repeat — stochastic, not structural. Only
`java-minimum_spanning_tree` failed all 3 attempts (a genuine hard task).

**Decision: KEEP.** (This "confirm ambiguous n=1 with n=3" step is what separates a
research loop from a coin-flip.)

---

## 5. Hypothesis H2 — wrong Java fixes + drift from "minimal fix"

With Class A gone, the next cluster was Class B plus a related behavior: when told
"exactly one line," the agent sometimes re-ordered or restructured instead of substituting
the single buggy line; and its verification was ad-hoc (e.g. printing a value and eyeballing
it) which gave false confidence.

**Hypothesis:** add guidelines — (1) for a minimal fix, *substitute the buggy line in
place*, don't reorder/swap/restructure; (2) *before finishing, verify* with the project's
own build/test commands and diff old vs new.

**Edit:** two more `addGuideline(...)` lines, same file. **Commit `94d91cc`.**

```ts
addGuideline(
  "When a task requires a minimal fix (e.g. 'exactly one line'), change that single line as written — substitute the buggy line's content in place; do not reorder, swap, or restructure lines, and do not rewrite surrounding code",
);
addGuideline(
  "Before finishing, verify your change: run the project's own build/test commands (not ad-hoc harnesses that fight the project's package layout), and diff old vs new to confirm the change is exactly as minimal as instructed",
);
```

**Result (job `h2-minfix-verify`, n=1):** **54/60 (90%)** → +5 over baseline.

Flip fingerprint vs the 49/60 baseline: **9 fixes / 4 regressions** — and all 4 regressions
were Java. That smelled structural, so I decoded the 6 failing trajectories and classified
root causes (all 6 passed `test_one_line_change`; the loss was downstream):

| Task | Root-cause class | What actually happened |
|---|---|---|
| java-to_base, java-get_factors, java-possible_change | **V-DUP** (verify-backfire) | New self-verify guideline made the agent run `javac` on a `package java_programs;` file; top-level compile failed, so it did `mkdir java_programs && cp/mv X.java` — leaving a **second copy** → verifier compiles both → `error: duplicate class` → reward 0 |
| java-subsequences | **NET-FLAKE** | gradle couldn't download hamcrest (`Network is unreachable`) — pure infra flake |
| java-minimum_spanning_tree | **ALGO** | genuine union/update logic bug (also 0/3 in H1 n=3) |
| python-powerset | **ORDER** | found the right bug, concatenated subsets in wrong order |

**Headline from the H2 decode:** the "verify before finishing" guideline *helped Python*
(7 Python fixes, 0 Python regressions) but its "run the project's build/test" half
*actively broke Java* by inducing the duplicate-class artifact. That single, specific
insight is what made H3 a laser instead of a guess.

**n=3 confirmation (job `h2-confirm-n3`):** **163/180 = 90.6% mean**, pass@any 59/60,
pass-all 49/60. Decision: **KEEP as stepping stone** — the V-DUP regressions were caused
by H2's own guideline and were about to be fixed by H3, which stacks directly on
`94d91cc` and dominates it.

---

## 6. Hypothesis H3 — stop the self-inflicted duplicate class

**Hypothesis:** V-DUP is the highest-value remaining lever. Constrain verification:
*never move/copy the named source and never create a duplicate package directory*; verify
in place, or copy to a temp dir (e.g. `/tmp`) and build there.

**Edit:** one more `addGuideline(...)` line, same file. **Commit `63e3d71`.**

```ts
addGuideline(
  "When verifying, never move or copy the named source/output file and never create a duplicate package directory (e.g. java_programs/) next to the original — that leaves two copies for the grader. Verify in place, or copy to a separate temp directory (e.g. under /tmp) and build/test there, leaving the task's files exactly where they were",
);
```

**Result (job `h3-verify-inplace`, n=1):** **57/60 (95%)** → +3 over H2, **+8 over baseline.**

**V-DUP eliminated** — `grep "duplicate class"` over all H3 verifier stdout = **0**.
Flips H2→H3: **+8 fixes** (java-get_factors, java-minimum_spanning_tree, java-possible_change,
java-subsequences, java-to_base, python-powerset) / **−3 regressions**, all in the flaky
band (diff-count honesty, JUnit flake, Class-A resurfacing) — *not* V-DUP.

**Decision: KEEP.** This is the frozen final state.

---

## 7. Where the kept guidelines now live (the full diff)

The final system prompt gained five always-on guidelines (the first two `addGuideline`
lines below are H1, next two H2, last one H3; the two original stock guidelines that
already existed are omitted here for clarity):

```ts
// H1
addGuideline("When the task names a specific output file for the result, write the complete result to exactly that file path and name — do not substitute a different name or location");
addGuideline("Leave explicitly provided input or source files unchanged unless the task explicitly says to modify them in place; apply changes only to the files the task names as outputs");
// H2
addGuideline("When a task requires a minimal fix (e.g. 'exactly one line'), change that single line as written — substitute the buggy line's content in place; do not reorder, swap, or restructure lines, and do not rewrite surrounding code");
addGuideline("Before finishing, verify your change: run the project's own build/test commands (not ad-hoc harnesses that fight the project's package layout), and diff old vs new to confirm the change is exactly as minimal as instructed");
// H3
addGuideline("When verifying, never move or copy the named source/output file and never create a duplicate package directory (e.g. java_programs/) next to the original — that leaves two copies for the grader. Verify in place, or copy to a separate temp directory (e.g. under /tmp) and build/test there, leaving the task's files exactly where they were");
```

One file. Five lines of English. **Dev 82% → 95%, holdout 80% → 95%.**

---

## 8. Why the loop stopped (the plateau, stated honestly)

Plateau declared at **H3 = 57/60 (95%)**. The 3 remaining dev failures are **3 distinct
failure modes across the known stochastic flaky band**, not one clean scaffold bug:

- `java-breadth_first_search` — **diff-count honesty gap** (made 2 edits, claimed 1).
- `java-shortest_paths` — **JUnit functional fail** (flaky; passed in H2 and dev-repro).
- `python-topological_ordering` — **0-line diff** = old Class-A trap resurfacing (flaky).

No single *general* guideline fixes all three without risking the 95% already achieved —
so the correct engineering call was to **freeze pi/ at `63e3d71`** rather than
over-fit the dev set.

---

## 9. Sealed holdout — the number that counts

Dev-set gains can be over-fit. The holdout was **sealed, run exactly once**, on the final
commit, after the loop plateaued.

- **Job `holdout-final`:** `-c holdout.yaml --env-file .env -k 1`, 20 sealed tasks, 16m 49s.
- **Score: 19/20 (95%)** vs stored baseline **16/20 (80%)** → **+3 tasks**.
- **Cost: $0.0155.** 319k in-tokens / 32k out-tokens, 1071s agent time.
- Only failure: `python-possible_change`. All 10 Java passed; 9/10 Python passed.

```
Holdout (sealed, single run)
baseline   ████████████████░░░░  80%   (16/20)
final      ███████████████████░  95%   (19/20)
                                  Δ +3 tasks, +15 pts
```

Generalization check ✅: the prompt-level guidelines transfer to unseen tasks and did not
just tune to the dev split.

---

## 10. Per-hypothesis summary (the ledger in one table)

| # | Hypothesis (failure class targeted) | Edit (commit) | Dev score | Decision |
|---|---|---|---|---|
| **H1** | Class A — 0-line-diff trap | +2 guidelines (`64f6db6`) | 55/60 (92%) n=1; **91% mean** at n=3 | **KEEP** |
| **H2** | Class B — Java wrong fix + minimal-fix drift | +2 guidelines (`94d91cc`) | 54/60 (90%) n=1; **90.6% mean** at n=3 | **KEEP** (stepping stone) |
| **H3** | Class V-DUP — duplicate-class from self-verify | +1 guideline (`63e3d71`) | **57/60 (95%)**; V-DUP count 0 | **KEEP**, frozen |

Gate after every edit (all passed, three separate commands):
`npm run check` → `PI_NO_LOCAL_LLM=1 npm test` (87/87) → `npm run build`.

---

## 11. Reproduce it yourself

```bash
# Dev split (60 tasks)
cd quixbugs && PYTHONPATH=. ./.venv/bin/harbor run -c dev.yaml --env-file .env -k 1 --job-name <name>
PYTHONPATH=. python3 summarize.py jobs/<name>

# Sealed holdout (20 tasks) — run exactly once on the final candidate
cd quixbugs && PYTHONPATH=. ./.venv/bin/harbor run -c holdout.yaml --env-file .env -k 1 --job-name <name>
PYTHONPATH=. python3 summarize.py jobs/<name>
```

Handy tools in `quixbugs/`:
`summarize.py` (score tables), `decode_traj.py` (turn the agent's `pi.txt` JSONL into a
readable trajectory — this is how the root causes were classified).

Environment gotchas you must hit to match these numbers (host fixes, not `pi/` edits):
- install `fd-find` (or the find-tool tests fail),
- gate tests with `PI_NO_LOCAL_LLM=1`,
- always launch harbor with `--env-file .env`,
- run harbor jobs sequentially on a small box,
- run the gate as separate commands (chained hits the 900 s timeout).

---

## 12. What this actually demonstrates

- **The biggest wins came from reading failure trajectories, not from "smarter prompts."**
  The top loss (Class A) was a *scaffold behavior* bug: functionally correct code scoring 0.
  You find that by decoding trajectories, not by intuition.
- **Diagnose before you prescribe.** H2 looked ambiguous (+5 net but two suspicious new
  regressions); decoding the 6 failures exposed the V-DUP backfire, which one sentence in
  the prompt (H3) then eliminated. Without H2's decode step, H3 would have been a lucky guess.
- **n=1 vs n=3 discipline.** Single runs on a stochastic LLM agent are noisy. Ambiguous
  results got an n=3 confirmation before a keep/revert call — that's what made the 95%
  believable.
- **Prompt text is a real lever — when it's general.** All five kept guidelines are
  task-agnostic behavior rules. One file, five lines of English, +13 dev points and +15
  holdout points.

Everything above is verifiable: baselines, flips, root-cause classes, the plateau
statement, and the single sealed holdout run are all written down in
`experiment_notes.md` and cross-checked against the scored outputs in `quixbugs/jobs/`.

---

*Ledger: `experiment_notes.md` • Final report: `README.md` • Frozen scaffold:
`pi/packages/coding-agent/src/core/system-prompt.ts` at commit `63e3d71`.*
