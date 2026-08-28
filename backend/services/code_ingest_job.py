"""Run the CMS code-set ingest as an explicit admin job.

This is intentionally not startup work. The ingest downloads CMS files and
rewrites large reference tables; doing that in init_db() would make boot depend
on cms.gov and could take the API down during normal deploys.
"""

from __future__ import annotations

import datetime
import os
import pathlib
import subprocess
import sys
import threading
import time
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ingest_code_sets.py"

_lock = threading.Lock()
_job: Optional[dict] = None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _snapshot() -> Optional[dict]:
    if not _job:
        return None
    out = dict(_job)
    out["log_tail"] = list(out.get("log_tail") or [])
    return out


def current_job() -> Optional[dict]:
    with _lock:
        return _snapshot()


def start_ingest_job(loaded_by: str = "admin UI") -> dict:
    """Start one ingest if no ingest is already running."""
    global _job
    with _lock:
        if _job and _job.get("status") == "running":
            return _snapshot()
        _job = {
            "id": int(time.time() * 1000),
            "status": "running",
            "started_at": _now(),
            "finished_at": None,
            "loaded_by": loaded_by or "admin UI",
            "returncode": None,
            "message": "CMS code-set ingest is running.",
            "log_tail": [],
        }
        thread = threading.Thread(target=_run, args=(_job["id"], _job["loaded_by"]),
                                  daemon=True)
        thread.start()
        return _snapshot()


def _append(job_id: int, line: str) -> None:
    with _lock:
        if not _job or _job.get("id") != job_id:
            return
        tail = _job.setdefault("log_tail", [])
        tail.append(line.rstrip())
        del tail[:-80]


def _finish(job_id: int, status: str, returncode: Optional[int], message: str) -> None:
    with _lock:
        if not _job or _job.get("id") != job_id:
            return
        _job.update({
            "status": status,
            "finished_at": _now(),
            "returncode": returncode,
            "message": message,
        })


def _run(job_id: int, loaded_by: str) -> None:
    env = os.environ.copy()
    if not env.get("DATABASE_URL"):
        _finish(job_id, "failed", None,
                "DATABASE_URL is not configured for this process.")
        return

    cmd = [sys.executable, str(SCRIPT), "--write", "--loaded-by", loaded_by]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        _finish(job_id, "failed", None, f"Could not start ingest: {exc}")
        return

    assert proc.stdout is not None
    for line in proc.stdout:
        _append(job_id, line)
    rc = proc.wait()
    if rc == 0:
        _finish(job_id, "completed", rc, "CMS code-set ingest completed.")
    else:
        _finish(job_id, "failed", rc, f"CMS code-set ingest failed with exit code {rc}.")
