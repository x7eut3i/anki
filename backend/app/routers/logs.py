"""Log viewer and AI statistics API endpoints."""

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/logs", tags=["logs"])

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_RETENTION_FILE = DATA_DIR / "log_retention.json"

# ── Log file paths ───────────────────────────────────────────────────

LOG_FILES = {
    "ai": DATA_DIR / "ai_interactions.log",
    "app": DATA_DIR / "app.log",
}


def _get_retention_days() -> int:
    """Read log retention days from config file. 0 = keep forever."""
    try:
        if _RETENTION_FILE.is_file():
            data = json.loads(_RETENTION_FILE.read_text(encoding="utf-8"))
            return int(data.get("retention_days", 0))
    except Exception:
        pass
    return 0


def _set_retention_days(days: int) -> None:
    """Save log retention days to config file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _RETENTION_FILE.write_text(
        json.dumps({"retention_days": days}), encoding="utf-8"
    )


def cleanup_old_logs(retention_days: int | None = None) -> dict:
    """Remove log entries older than retention_days. Returns cleanup stats."""
    if retention_days is None:
        retention_days = _get_retention_days()
    if retention_days <= 0:
        return {"cleaned": False, "reason": "retention disabled"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    stats = {}
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")

    for name, path in LOG_FILES.items():
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        original = len(lines)
        kept = []
        for line in lines:
            m = date_re.match(line)
            if m:
                if m.group(1) >= cutoff:
                    kept.append(line)
                # else: drop old line
            else:
                # Continuation line — keep only if preceded by a kept line
                if kept:
                    kept.append(line)
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        stats[name] = {"original_lines": original, "kept_lines": len(kept), "removed": original - len(kept)}

    return {"cleaned": True, "retention_days": retention_days, "cutoff_date": cutoff, "stats": stats}


def _read_log_lines(log_type: str) -> list[str]:
    """Read all lines from a log file."""
    path = LOG_FILES.get(log_type)
    if not path or not path.is_file():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _parse_ai_log_entries(lines: list[str]) -> list[dict]:
    """Parse AI interaction log into structured entries.

    Each entry is an INFO line followed by a DEBUG JSON block.
    The DEBUG line starts with a timestamp prefix like:
      2026-02-27 14:45:37 | DEBUG | {
    """
    entries = []
    # Regex to match any timestamped log line
    _TS_PREFIX_RE = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (\w+) \| (.*)$"
    )
    i = 0
    while i < len(lines):
        line = lines[i]
        info_match = _TS_PREFIX_RE.match(line)
        if info_match:
            timestamp, level, message = info_match.groups()

            # Check if next line is a DEBUG JSON block
            json_data = None
            next_i = i + 1
            if next_i < len(lines):
                debug_match = _TS_PREFIX_RE.match(lines[next_i])
                if debug_match and debug_match.group(2) == "DEBUG":
                    # Extract JSON from this DEBUG line and continuation lines
                    first_json_part = debug_match.group(3)  # e.g. "{"
                    json_lines = [first_json_part]
                    j = next_i + 1
                    # Collect continuation lines (lines without timestamp prefix)
                    while j < len(lines):
                        next_match = _TS_PREFIX_RE.match(lines[j])
                        if next_match:
                            break
                        json_lines.append(lines[j])
                        j += 1
                    json_text = "\n".join(json_lines)
                    try:
                        json_data = json.loads(json_text)
                    except json.JSONDecodeError:
                        json_data = None
                    i = j
                    entries.append({
                        "timestamp": timestamp,
                        "level": level,
                        "message": message,
                        "data": json_data,
                    })
                    continue

            entries.append({
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "data": None,
            })
        i += 1
    return entries


def _parse_app_log_entries(lines: list[str]) -> list[dict]:
    """Parse app log into structured entries."""
    entries = []
    for line in lines:
        match = re.match(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] ([\w.]+): (.*)$",
            line,
        )
        if match:
            timestamp, level, logger_name, message = match.groups()
            entries.append({
                "timestamp": timestamp,
                "level": level,
                "logger": logger_name,
                "message": message,
            })
        elif entries:
            # Continuation line (e.g. tracebacks)
            entries[-1]["message"] += "\n" + line
    return entries


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
def list_log_files():
    """List available log files with their sizes."""
    result = []
    for name, path in LOG_FILES.items():
        if path.is_file():
            stat = path.stat()
            result.append({
                "name": name,
                "path": str(path.name),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    return result


# ── AI Statistics (must come BEFORE /{log_type} to avoid path conflict) ──

@router.get("/ai/statistics")
def get_ai_statistics():
    """Get aggregated AI interaction statistics."""
    lines = _read_log_lines("ai")
    entries = _parse_ai_log_entries(lines)

    # Only look at entries with data
    requests = [e for e in entries if e.get("data") and e["data"].get("direction") == "REQUEST"]
    responses = [e for e in entries if e.get("data") and e["data"].get("direction") == "RESPONSE"]

    # Total calls
    total_calls = len(requests)
    total_errors = sum(1 for r in responses if r.get("data", {}).get("error"))

    # By feature
    by_feature = defaultdict(lambda: {"count": 0, "errors": 0, "total_tokens": 0, "total_ms": 0})
    for req in requests:
        feature = req["data"].get("feature", "unknown")
        by_feature[feature]["count"] += 1

    for resp in responses:
        data = resp.get("data", {})
        feature = data.get("feature", "unknown")
        by_feature[feature]["total_tokens"] += data.get("tokens_used", 0)
        by_feature[feature]["total_ms"] += data.get("elapsed_ms", 0)
        if data.get("error"):
            by_feature[feature]["errors"] += 1

    # By model
    by_model = defaultdict(lambda: {"count": 0, "total_tokens": 0, "total_ms": 0})
    for req in requests:
        model = req["data"].get("model", "unknown")
        by_model[model]["count"] += 1
    for resp in responses:
        data = resp.get("data", {})
        model = data.get("model", "unknown")
        by_model[model]["total_tokens"] += data.get("tokens_used", 0)
        by_model[model]["total_ms"] += data.get("elapsed_ms", 0)

    # Daily usage
    daily = defaultdict(lambda: {"count": 0, "tokens": 0, "errors": 0})
    for req in requests:
        day = req["timestamp"][:10]
        daily[day]["count"] += 1
    for resp in responses:
        data = resp.get("data", {})
        day = resp["timestamp"][:10]
        daily[day]["tokens"] += data.get("tokens_used", 0)
        if data.get("error"):
            daily[day]["errors"] += 1

    # Latency distribution
    latencies = [r["data"].get("elapsed_ms", 0) for r in responses
                 if r.get("data") and r["data"].get("elapsed_ms")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0

    # Token usage
    total_tokens = sum(r["data"].get("tokens_used", 0) for r in responses if r.get("data"))

    return {
        "total_calls": total_calls,
        "total_errors": total_errors,
        "total_tokens": total_tokens,
        "avg_latency_ms": round(avg_latency),
        "max_latency_ms": max_latency,
        "min_latency_ms": min_latency,
        "by_feature": [
            {"feature": k, **v, "avg_ms": round(v["total_ms"] / v["count"]) if v["count"] else 0}
            for k, v in sorted(by_feature.items(), key=lambda x: -x[1]["count"])
        ],
        "by_model": [
            {"model": k, **v, "avg_ms": round(v["total_ms"] / v["count"]) if v["count"] else 0}
            for k, v in sorted(by_model.items(), key=lambda x: -x[1]["count"])
        ],
        "daily": [
            {"date": k, **v} for k, v in sorted(daily.items())
        ],
    }


# ── Log retention ────────────────────────────────────────────────────

@router.get("/settings/retention")
def get_log_retention():
    """Get log retention setting."""
    return {"retention_days": _get_retention_days()}


@router.put("/settings/retention")
def set_log_retention(data: dict):
    """Set log retention days. 0 = keep forever."""
    days = int(data.get("retention_days", 0))
    if days < 0:
        days = 0
    _set_retention_days(days)
    # Immediately clean up if retention is set
    result = {}
    if days > 0:
        result = cleanup_old_logs(days)
    return {"retention_days": days, "cleanup": result}


# ── Log entries (parameterized routes AFTER specific ones) ───────────

@router.get("/{log_type}")
def get_log_entries(
    log_type: str,
    search: str = Query(default="", description="Search filter"),
    level: str = Query(default="", description="Filter by level (INFO, DEBUG, ERROR, WARNING)"),
    date: str = Query(default="", description="Filter by date (YYYY-MM-DD)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=10, le=500),
    tail: int = Query(default=0, ge=0, description="Return last N entries (0=all)"),
):
    """Get parsed log entries with filtering and pagination."""
    lines = _read_log_lines(log_type)
    if not lines:
        return {"entries": [], "total": 0, "page": page, "page_size": page_size}

    if log_type == "ai":
        entries = _parse_ai_log_entries(lines)
    elif log_type == "app":
        entries = _parse_app_log_entries(lines)
    else:
        return {"entries": [], "total": 0, "page": page, "page_size": page_size}

    # Filter by date
    if date:
        entries = [e for e in entries if e.get("timestamp", "").startswith(date)]

    # Filter by level
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.get("level", "").upper() == level_upper]

    # Filter by search text
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries
            if search_lower in e.get("message", "").lower()
            or search_lower in json.dumps(e.get("data") or {}, ensure_ascii=False).lower()
        ]

    # Most recent first
    entries.reverse()

    total = len(entries)

    # Tail mode
    if tail > 0:
        entries = entries[:tail]
        return {"entries": entries, "total": total, "page": 1, "page_size": tail}

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]

    return {
        "entries": page_entries,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{log_type}/raw")
def get_raw_log(
    log_type: str,
    tail: int = Query(default=200, ge=10, le=5000),
):
    """Get raw log text (last N lines)."""
    lines = _read_log_lines(log_type)
    if tail > 0:
        lines = lines[-tail:]
    return {"content": "\n".join(lines), "total_lines": len(lines)}


@router.get("/{log_type}/dates")
def get_log_dates(log_type: str):
    """Get available dates in a log file."""
    lines = _read_log_lines(log_type)
    dates = set()
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")
    for line in lines:
        m = date_re.match(line)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


@router.delete("/{log_type}")
def clear_log(log_type: str):
    """Clear a log file."""
    path = LOG_FILES.get(log_type)
    if not path or not path.is_file():
        return {"ok": False, "error": "Log file not found"}
    path.write_text("", encoding="utf-8")
    return {"ok": True, "message": f"{log_type} log cleared"}
