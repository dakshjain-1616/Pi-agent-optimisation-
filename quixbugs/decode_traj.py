#!/usr/bin/env python3
"""Decode pi agent trajectories (pi.txt JSONL) into readable text.

Usage: decode_traj.py <job_dir> [task_glob] [max_summary_chars]
For each message_end, iterate content and print toolCall name/args, text,
thinking snippets, and toolResult text.
"""
import glob
import json
import sys

JOB = sys.argv[1]
GLOB = sys.argv[2] if len(sys.argv) > 2 else "*"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 400

paths = sorted(glob.glob(f"{JOB}/{GLOB}/agent/pi.txt"))

for p in paths:
    task = p.split("/agent/")[0].split("/")[-1]
    print(f"\n===== {task} =====")
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "message_end":
            msg = ev.get("message", {})
            role = msg.get("role", "?")
            for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(c, dict):
                    continue
                ctype = c.get("type")
                if ctype == "text" and str(c.get("text", "")).strip():
                    print(f"[{role} text] {c['text'][:LIMIT]}")
                elif ctype == "thinking" and str(c.get("thinking", "")).strip():
                    print(f"[{role} think] {c['thinking'][:LIMIT//2]}")
                elif ctype == "toolCall":
                    args = json.dumps(c.get("args", c.get("arguments", {})))[:LIMIT]
                    print(f"[{role} call:{c.get('name')}] {args}")
        elif t in ("toolResult", "tool_result"):
            content = ev.get("content") or ev.get("result") or []
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        print(f"[toolResult] {str(c.get('text'))[:LIMIT//2]}")
            else:
                print(f"[toolResult] {str(content)[:LIMIT//2]}")
