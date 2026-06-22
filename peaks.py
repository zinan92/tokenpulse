"""Single-session peak token burn — the largest one-session total, all-time.

A session = one Claude transcript FILE (NOT sessionId: subagent agent-*.jsonl
files reuse the parent's sessionId, so grouping by sessionId over-counts) / one
Codex session UUID (dedup keep-latest-file). The running max never needs a
window, but logs prune — so the value lives in the lifetime accumulator
(lifetime.py), backfilled once and refreshed from recently-touched files (the
merge is an idempotent max, so re-scanning can't double-count).

Pure stdlib.
"""
from __future__ import annotations

import glob
import json
import os

import core


def _claude_session_peaks(floor_mtime: float = 0.0) -> dict:
    """{file: {tool,id,date,total}} — one entry per transcript file."""
    out = {}
    for f in glob.glob(core.CLAUDE_GLOB, recursive=True):
        try:
            if os.path.getmtime(f) < floor_mtime:
                continue
        except OSError:
            continue
        seen: set = set()
        tot, last_dt, sid = 0, None, None
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    sid = sid or d.get("sessionId")
                    m = d.get("message")
                    if not isinstance(m, dict):
                        continue
                    u = m.get("usage")
                    if not isinstance(u, dict):
                        continue
                    mid = m.get("id")
                    key = (mid, d.get("requestId"))
                    if mid and key in seen:
                        continue
                    if mid:
                        seen.add(key)
                    tot += ((u.get("input_tokens", 0) or 0)
                            + (u.get("cache_creation_input_tokens", 0) or 0)
                            + (u.get("cache_read_input_tokens", 0) or 0)
                            + (u.get("output_tokens", 0) or 0))
                    dt = core._parse_ts(d.get("timestamp"))
                    if dt:
                        last_dt = dt
        except OSError:
            continue
        if tot > 0:
            out[f] = {"tool": "claude", "id": sid or os.path.basename(f).replace(".jsonl", ""),
                      "date": last_dt.astimezone().date().isoformat() if last_dt else None,
                      "total": tot}
    return out


def _codex_session_peaks(floor_mtime: float = 0.0) -> dict:
    """{uuid: {tool,id,date,total}} — dedup by UUID keep-latest-file."""
    chosen, mt = {}, {}
    for pat in core.CODEX_GLOBS:
        for f in glob.glob(pat, recursive=True):
            try:
                m = os.path.getmtime(f)
            except OSError:
                continue
            if m < floor_mtime:
                continue
            uid = core._codex_session_uuid(f)
            if uid not in mt or m > mt[uid]:
                mt[uid], chosen[uid] = m, f
    out = {}
    for uid, f in chosen.items():
        tot, last_dt = 0, None
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    p = d.get("payload")
                    info = p.get("info") if isinstance(p, dict) else None
                    if not isinstance(info, dict):
                        continue
                    lt = info.get("last_token_usage")
                    if not isinstance(lt, dict):
                        continue
                    tot += lt.get("total_tokens", 0) or 0
                    dt = core._parse_ts(d.get("timestamp"))
                    if dt:
                        last_dt = dt
        except OSError:
            continue
        if tot > 0:
            out[uid] = {"tool": "codex", "id": uid,
                        "date": last_dt.astimezone().date().isoformat() if last_dt else None,
                        "total": tot}
    return out


def pick_larger(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return b
    if not b:
        return a
    return a if a["total"] >= b["total"] else b


def scan_session_peak(floor_mtime: float = 0.0) -> dict | None:
    """Largest single session across both tools among files newer than floor."""
    peak = None
    for sess in _claude_session_peaks(floor_mtime).values():
        peak = pick_larger(peak, sess)
    for sess in _codex_session_peaks(floor_mtime).values():
        peak = pick_larger(peak, sess)
    return peak


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(scan_session_peak(), indent=2, default=str))
