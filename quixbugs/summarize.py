#!/usr/bin/env python3
"""Per-task markdown table for a harbor job dir. Usage: summarize.py jobs/<name>"""
import json
import sys
from pathlib import Path

job = Path(sys.argv[1] if len(sys.argv) > 1 else "jobs")
rows, tot_in, tot_out, tot_cost, tot_sec = [], 0, 0, 0.0, 0.0
for f in sorted(job.glob("*/result.json")):
    d = json.load(f.open())
    a, v = d["agent_result"] or {}, d["verifier_result"] or {}
    reward = (v.get("rewards") or {}).get("reward")
    ex = (d.get("exception_info") or {}).get("exception_type") if d.get("exception_info") else None
    ae = d.get("agent_execution") or {}
    sec = 0.0
    if ae.get("started_at") and ae.get("finished_at"):
        from datetime import datetime
        p = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        sec = (p(ae["finished_at"]) - p(ae["started_at"])).total_seconds()
    rows.append((d["task_name"].split("/")[-1], reward, ex, a.get("n_input_tokens", 0),
                 a.get("n_output_tokens", 0), a.get("cost_usd") or 0.0, sec))
    tot_in += a.get("n_input_tokens") or 0
    tot_out += a.get("n_output_tokens") or 0
    tot_cost += a.get("cost_usd") or 0.0
    tot_sec += sec

print("| Task | Reward | In tok | Out tok | Cost | Agent time |")
print("|---|---|---|---|---|---|")
for n, r, ex, i, o, c, s in rows:
    mark = "✅ 1.0" if r == 1.0 else ("❌ 0.0" if r == 0.0 else f"⚠️ {ex or r}")
    print(f"| `{n}` | {mark} | {i:,} | {o:,} | ${c:.4f} | {s:.0f}s |")
solved = sum(1 for r in rows if r[1] == 1.0)
print(f"| **{solved}/{len(rows)} solved** | **{solved/len(rows):.0%}** | "
      f"**{tot_in:,}** | **{tot_out:,}** | **${tot_cost:.4f}** | **{tot_sec:.0f}s** |")
