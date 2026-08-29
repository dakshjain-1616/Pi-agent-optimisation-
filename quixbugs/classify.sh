#!/bin/bash
# Classify each failing baseline task by verifier stdout.
cd /home/azureuser/piEvalLoop/quixbugs
FAILED_TASKS=(
  quixbugs-java-lis
  quixbugs-java-max_sublist_sum
  quixbugs-java-minimum_spanning_tree
  quixbugs-java-rpn_eval
  quixbugs-java-shortest_path_lengths
  quixbugs-java-sqrt
  quixbugs-java-subsequences
  quixbugs-python-bitcount
  quixbugs-python-hanoi
  quixbugs-python-possible_change
  quixbugs-python-rpn_eval
  quixbugs-python-topological_ordering
  quixbugs-python-wrap
)
JOB=jobs/pi-quixbugs-glm53flash
for t in "${FAILED_TASKS[@]}"; do
  d=$(ls -d "$JOB/${t}__"* 2>/dev/null | head -1)
  if [ -z "$d" ]; then echo "$t : no task dir"; continue; fi
  verdir="$d/verifier"
  if [ ! -f "$verdir/reward.txt" ]; then echo "$t : no reward.txt"; continue; fi
  rw=$(cat "$verdir/reward.txt")
  stdout="$verdir/test-stdout.txt"
  one_line_failed=$(grep -cE "FAILED test_outputs.py::test_one_line_change" "$stdout")
  func_failed=$(grep -cE "FAILED test_outputs.py::test_" "$stdout" | head -1)
  func_failed=$((func_failed - one_line_failed))
  passed=$(grep -cE "PASSED test_outputs.py::test_" "$stdout")
  echo "$t reward=$rw one_line_change_failed=$one_line_failed other_failed=$func_failed passed=$passed"
done
