"""
Every check, and what the engineer thought of it, appended to one file.

This is the research dataset as much as an audit trail. Each line holds:
- the claim
- both readings of it, the rule parser's and Claude's
- the stamp and the numbers behind it
- the thresholds version that produced the stamp
- the sha256 of every session file

That is enough to re-run any check later, under new thresholds, against the
same data. An engineer's agree / disagree / unsure is appended as its own
line, pointing back at the check by id. Comparing stamps with the outcome of the next session
is the calibration step.

JSON Lines, append-only, never rewritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

DEFAULT = "claimcheck-checks.jsonl"


def _id(record: dict) -> str:
    h = hashlib.sha1(json.dumps([record.get("checked_at"), record.get("claim")],
                                sort_keys=True).encode()).hexdigest()
    return h[:10]


def write_check(path: str | Path, verdict, files: list, rule_spec=None, llm_spec=None,
                translator_note: str = "") -> str:
    d = verdict.to_dict()
    record = {
        "type": "check",
        "checked_at": d["checked_at"],
        "claim": verdict.spec.text,
        "spec_used": d["spec"],
        "spec_rules": rule_spec.to_dict() if rule_spec is not None else None,
        "spec_claude": llm_spec.to_dict() if llm_spec is not None else None,
        "translator_note": translator_note,
        "stamp": d["stamp"],
        "headline": d["headline"],
        "reference": d["reference"],
        "corner": d["corner"],
        "tests": d["tests"],
        "where": d["where"],
        "pointers": d["pointers"],
        "caveats": d["caveats"],
        "thresholds": d["thresholds"],
        "files": [{"name": f["name"], "sha256": f["sha256"], "drivers": f["drivers"]} for f in files],
    }
    record["id"] = _id(record)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record["id"]


def write_feedback(path: str | Path, check_id: str, judgement: str, note: str = "") -> None:
    import datetime as dt
    record = {"type": "feedback", "check_id": check_id, "engineer": judgement,
              "note": note, "at": dt.datetime.now().isoformat(timespec="seconds")}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read(path: str | Path, limit: Optional[int] = None) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[-limit:] if limit else rows
