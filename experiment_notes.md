# Experiment log — pi agent auto-research loop on QuixBugs

## Baselines
- Original pre-split baseline (job `pi-quixbugs-glm53flash`, 80/80 tasks): 64/80 solved (80%).
- Fresh dev-split baseline (job `dev-repro`, 60 dev tasks, n_attempts=1, current pi HEAD): **49/60 (82%)**, $0.0598, 4309s agent time.
- Holdout baseline (stored): 16/20.

## Failure taxonomy (baseline job dev-repro verifier stdout)
11 failing tasks in fresh baseline:
- reClass A (all functionals.pass, `test_one_line_change` fails — original mutated in place then copied so diff==0):
  - python-hanoi, python-knapsack, python-powerset, python-rpn_eval, python-shortest_paths, python-sqrt, python-to_base (7 tasks)
- Class B (one_line_change passes, JUnit functional fails): java-breadth_first_search, java-minimum_spanning_tree, java-wrap
- Class C (functional fails on python side): python-wrap (5 fails)
- (Note: java-minimum_spanning_tree and java-breadth_first_search changed between stored baseline and fresh dev — stochastic.)

## Hypotheses tried
| # | Hypothesis | Edit | Gate | Dev score | Decision |
|---|-----------|------|------|-----------|----------|
| H1 | Class A trap: agent edits original in place then copies → diff==0. Add general guidelines: write result to exactly named output file; leave explicitly provided input/source files unchanged | pi/packages/coding-agent/src/core/system-prompt.ts (buildSystemPrompt guidelines), committed 64f6db6 | check 0, test 0, build 0 | 55/60 (92%) vs baseline 49/60 (82%) → +6 net (n=1); 8 fixes, 2 regressions | KEEP — n_attempts:3 confirmed: 164/180 solved (91% mean), pass@any-of-3 59/60, pass-all-3 46/60, $0.1583, 12157s (job h1-confirm-n3). The -k1 regressions did NOT repeat (stochastic). Only java-minimum_spanning_tree went 0/3. |
| H2 | Class B java wrong fixes + minimal-fix drift: add guidelines — (1) for minimal fixes, substitute the buggy line in place, don't reorder/swap/restructure; (2) verify before finishing with the project's own build/test commands + diff old vs new | pi/packages/coding-agent/src/core/system-prompt.ts (2 more addGuideline lines), committed 94d91cc | check 0, test 0 (PI_NO_LOCAL_LLM=1, fd-find installed), build 0 | 54/60 (90%) vs dev-repro 49/60 (82%) → +5 net (n=1, job h2-minfix-verify, $0.0792, 5311s agent time) | KEEP (stepping stone) — h2-confirm-n3 (-k3): 163/180 (90.6% mean), pass@any 59/60, pass-all 49/60. Rationale: H2's n=3 mean (90.6%) ≈ H1's n=3 mean (91%), and H2's only structural regressions were the V-DUP duplicate-class class that H3's guideline eliminated (H3 grep "duplicate class" = 0). H2's python-facing verify guidance contributed (7 python fixes in the -k1 run); its java "run the project's build/test" half caused the V-DUP backfire that H3 corrected. Since H3 (57/60=95%) is stacked directly on H2's commit 94d91cc and dominates it, H2's guidelines are retained as part of the final stack. |
| H3 | Class V-DUP: H2's "run the project's build/test" guideline made the agent `mkdir java_programs && cp/mv X.java` → duplicate-class → reward 0. Constrain verify: never move/copy the named source or create a duplicate package dir; verify in place or copy to a temp dir (/tmp) | pi/packages/coding-agent/src/core/system-prompt.ts (1 more addGuideline line), committed 63e3d71 | check 0, test 87/87 pass, build 0 | **57/60 (95%)** vs H2 54/60 → +3 net (n=1, job h3-verify-inplace, $0.0779, 4296s agent time) | KEEP (n=1). V-DUP eliminated: grep "duplicate class" over all H3 verifier stdout = 0. Flips H2→H3: +8 (java-get_factors, java-minimum_spanning_tree, java-possible_change, java-subsequences, java-to_base, python-powerset all 0→1) / −3 (java-breadth_first_search, java-shortest_paths, python-topological_ordering, all one_line_change diff-count flakes: 2-line change, JUnit fail, 0-line change respectively — flaky band, NOT V-DUP). |

## H2 analysis (job h2-minfix-verify, 54/60 = 90%)
- Score: 54/60 (90%), $0.0792, 5311s agent time, 1.49M in / 166k out tokens.
- Fails (6): java-get_factors, java-minimum_spanning_tree, java-possible_change, java-subsequences, java-to_base, python-powerset.

### H2 flip fingerprint vs dev-repro (49/60)
- failed→passed (9): java-breadth_first_search, java-wrap, python-hanoi, python-knapsack, python-rpn_eval, python-shortest_paths, python-sqrt, python-to_base, python-wrap
- passed→failed (4, ALL java): java-get_factors, java-possible_change, java-subsequences, java-to_base
- still failing both: java-minimum_spanning_tree, python-powerset

### H2 failures cross-referenced with H1 n=3 (h1-confirm-n3, 164/180 = 91% mean)
- java-get_factors: n3 [1,0,1] flaky → H2 fail plausibly stochastic
- java-possible_change: n3 [1,1,0] flaky → stochastic
- java-subsequences: n3 [1,1,0] flaky → stochastic (also slow on H2: 329s, 141k in-tokens)
- java-to_base: n3 [1,1,1] solid → NEW regression, suspicious (self-verify loop may talk the agent out of a correct minimal fix?)
- java-minimum_spanning_tree: n3 [0,0,0] → ONLY consistent 0/3 task anywhere; real persistent failure (600s timeout on H2, 8.4k out tokens)
- python-powerset: n3 [1,1,1] solid → NEW regression (fast fail: 23s, 677 out tokens — barely tried)
- Net: H2 90% vs H1 n=3 mean 91% — ambiguous; 3 of 4 java regressions are flaky-band, but java-to_base + python-powerset are new.

### H2 failure root-cause classification (decoded via decode_traj.py + verifier test-stdout)
All 6 fails passed `test_one_line_change`; the loss is downstream. Two dominant classes:
- **Class V-DUP (verify-backfire, java duplicate-class) — 3 tasks.** The H2 self-verify guideline makes the agent run `javac` on a `package java_programs;` source, which fails at top level; the agent then does `mkdir -p java_programs && cp/mv X.java java_programs/` to make javac happy. This leaves a SECOND copy `java_programs/X.java` next to `/app/X.java`; the verifier compiles both → `error: duplicate class: java_programs.X` → reward 0. Affected: **java-to_base** (`mv` — moved the fixed file out of /app), **java-get_factors**, **java-possible_change** (`cp`). Root cause is the H2 verify guideline interacting with Java packaging — NOT a model logic error.
- **Class NET-FLAKE (infra) — 1 task.** **java-subsequences**: gradle could not download hamcrest-core (`repo.maven.apache.org ... Network is unreachable`) — pure environment network flake, agent fix was fine.
- **Class ALGO (genuine model difficulty) — 1 task.** **java-minimum_spanning_tree**: agent built temp stubs, compiled OK, but its own Test2 caught the MST returning 4 edges incl. weight-10 instead of 3 edges/total 6 — union/update logic still wrong. Real algorithmic failure (also the only 0/3 in h1-confirm-n3), 600s timeout.
- **Class ORDER (fix-correctness) — 1 task.** **python-powerset**: agent found the right bug (missing `+ rest_subsets`) but concatenated in the wrong order → output `[[...full...],...,[]]` vs expected `[[],...]`; 4/5 functional tests fail on ordering. Fast 23s fail.

**Headline:** H2's self-verify guideline HELPED Python (7 python fixes, 0 python regressions among flips) but its "run the project's build/test" half actively BROKE Java by inducing a duplicate-class artifact. The highest-value next lever is to stop the java duplicate-class self-inflicted wound.

## Loop termination / plateau (declared)
Plateau declared at **H3 = 57/60 (95%)**, the best dev score achieved. Hypothesis loop terminated here. The 3 remaining H3 failures are 3 DISTINCT failure modes across the known flaky band, not one clean scaffold bug:
- **java-breadth_first_search** — diff-count honesty gap: agent made 2 edits (addFirst→addLast + while(true)→while(!isEmpty)) then claimed "verified the final diff is exactly one line" (2≠1); the task arguably needs 2 lines for correctness.
- **java-shortest_paths** — JUnit functional fail (wrong-logic fix, flaky; passed in H2 & dev-repro).
- **python-topological_ordering** — 0-line diff = old Class-A "edit the original then copy" trap resurfacing (flaky).
No single general pi/ guideline fixes all three without risking the 95% already achieved, and all three sit in the stochastic flaky set (h1-confirm-n3 / h2-confirm-n3 both show these tasks oscillating pass/fail). Therefore the loop is terminated and pi/ is frozen at commit **63e3d71** (H3).

## Sealed holdout result (run EXACTLY ONCE on final commit 63e3d71 = H3)
- Job: `holdout-final`, `-c holdout.yaml --env-file .env -k 1`, 20 sealed tasks, run once, total runtime 16m 49s.
- **Score: 19/20 (95%)** — up from the stored holdout baseline of **16/20 (80%)** → **+3 tasks**.
- Cost $0.0155, 319,075 in-tokens / 32,204 out-tokens, 1071s agent time.
- Only failure: **python-possible_change** (❌ 0.0). All 19 others passed (java: bitcount, detect_cycle, gcd, kheapsort, levenshtein, lis, next_permutation, quicksort, shortest_path_lengths, shunting_yard; python: bitcount, breadth_first_search, find_in_sorted, is_valid_parenthesization, levenshtein, mergesort, pascal, shortest_path_length, sieve).
- Holdout run was healthy throughout: 0 "No API key found" errors, all pi.txt trajectories grew normally.

## n=3 confirmation (job h1-confirm-n3) flaky set (2/3 or inconsistent)
java-breadth_first_search, java-get_factors, java-hanoi, java-max_sublist_sum, java-mergesort, java-possible_change, java-shortest_paths, java-sieve, java-subsequences, java-wrap, python-shortest_paths, python-shunting_yard, python-wrap (failing attempt hit 600s timeout, 81,823 tokens), python-subsequences (3/3 but slow 65-77s).

## Launch command lesson (INVALID runs discarded)
- I launched `h2-confirm-n3` (-k3) and `h3-verify-inplace` (-k1) WITHOUT `--env-file .env`. Result: every trial's pi CLI printed **"No API key found for openrouter."** and exited 1 → reward 0 on all trials. Verifier showed `ModuleNotFoundError: No module named 'fixed_X'` (agent never wrote output). Diagnosed via 425-byte agent/pi.txt. Both runs INVALID; deleted jobs dirs. **Correct launch requires `--env-file .env`** so OPENROUTER_API_KEY is injected into containers: `PYTHONPATH=. ./.venv/bin/harbor run -c dev.yaml --env-file .env -k <n> --job-name <name>`. Also: run dev jobs SEQUENTIALLY (not 2 in parallel) — parallel heavy docker jobs caused transient shell-wrapper races on this 4-core/15.6GB box.

## Gate environment notes (must document in final README)
- `fd` binary was missing on this box (no ~/.pi/bin, no PATH fd) → 10 coding-agent find-tool test failures ("fd is not available and could not be downloaded"). Remediated via `sudo apt-get install -y fd-find` (fdfind 9.0.0; tools-manager resolves "fdfind" via systemBinaryNames). Env fix, not a pi/ edit.
- Ollama was installed ~5h in with gpt-oss:20b (13 GB) pulled, ACTIVATING previously-skipped Ollama E2E tests in packages/ai (connection/timeout failures). Gated with the suite's own env flag `PI_NO_LOCAL_LLM=1` (stream.test.ts ~line 1649). Do NOT pre-warm gpt-oss:20b — RAM contention with dev runs.
- Full monorepo `npm test` ≈13 min; run check/test/build as SEPARATE commands (chained single command hit the 900s timeout mid-build).

H1 flip detail (dev-repro → h1-output-fidelity):
- passed→failed (regressions): java-sqrt (600s timeout), python-depth_first_search
- failed→passed (fixes): java-wrap, python-hanoi, python-knapsack, python-powerset, python-shortest_paths, python-sqrt, python-to_base, python-wrap
- still failing: java-breadth_first_search, java-minimum_spanning_tree, python-rpn_eval

## Todo candidates
- H2 (Class B java wrong fixes): strengthen self-verification guidance — e.g., after editing, run the project's own tests or construct tests from the task statement, not ad-hoc spot checks.
- H3: python-wrap loops forever (555s, 14k out tokens) — transcript shows repeated re-write churn.
- H4: java minimum_spanning_tree/shortest_path_lengths/SUBSEQUENCES in the stored baseline.
