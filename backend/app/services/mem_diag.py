"""Memory diagnostics — opt-in via MEMORY_DIAG=1 env var.

Starts tracemalloc on init() and provides take_snapshot() for a full
memory profile (RSS, per-module breakdown, top allocations with tracebacks,
GC census, large objects, SQLAlchemy session identity maps).
"""

import gc
import os
import sys
import tracemalloc
from collections import Counter

_enabled = False


def init():
    """Call once at startup (lifespan). Starts tracemalloc if MEMORY_DIAG=1."""
    global _enabled
    if os.environ.get("MEMORY_DIAG", "0") == "1":
        tracemalloc.start(10)  # 10-frame call stacks (reduced from 25 to save memory)
        _enabled = True


def is_enabled() -> bool:
    return _enabled


def take_snapshot() -> dict:
    """Return a diagnostic dict — call from the API endpoint."""
    if not _enabled:
        return {"error": "Memory diagnostics not enabled (set MEMORY_DIAG=1)"}

    import resource  # Unix only, fine for Docker container

    snap = tracemalloc.take_snapshot()
    stats = snap.statistics("filename")

    rusage = resource.getrusage(resource.RUSAGE_SELF)
    rss_mb = rusage.ru_maxrss / 1024  # Linux: ru_maxrss is in KB

    # Also try /proc for current RSS (maxrss is peak)
    current_rss_mb = None
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    current_rss_mb = int(line.split()[1]) / 1024
                    break
    except OSError:
        pass

    return {
        "process": {
            "peak_rss_mb": round(rss_mb, 1),
            "current_rss_mb": round(current_rss_mb, 1) if current_rss_mb else None,
            "tracemalloc_traced_mb": round(
                tracemalloc.get_traced_memory()[0] / 1024 / 1024, 2
            ),
            "tracemalloc_peak_mb": round(
                tracemalloc.get_traced_memory()[1] / 1024 / 1024, 2
            ),
        },
        "by_module": _by_module(stats, top_n=30),
        "top_allocations": _top_allocs(snap, top_n=30),
        "gc_census": _gc_census(),
        "large_objects": _large_objects(min_kb=50),
        "sa_sessions": _sa_sessions(),
    }


# ── helpers ──────────────────────────────────────────────────────────

def _by_module(stats, top_n: int = 30) -> list[dict]:
    """Aggregate tracemalloc stats by filename, sorted by size desc."""
    return [
        {"file": str(s.traceback), "size_kb": round(s.size / 1024, 1), "count": s.count}
        for s in stats[:top_n]
    ]


def _top_allocs(snap, top_n: int = 30) -> list[dict]:
    """Top allocations with full tracebacks (up to 25 frames)."""
    stats = snap.statistics("traceback")
    result = []
    for s in stats[:top_n]:
        frames = []
        for frame in s.traceback:
            frames.append(f"{frame.filename}:{frame.lineno}")
        result.append({
            "size_kb": round(s.size / 1024, 1),
            "count": s.count,
            "traceback": frames,
        })
    return result


def _gc_census() -> dict:
    """Count objects by type in the GC-tracked heap."""
    counts: Counter = Counter()
    for obj in gc.get_objects():
        counts[type(obj).__name__] += 1
    top = counts.most_common(20)
    return {"total_tracked": len(gc.get_objects()), "top_types": dict(top)}


def _large_objects(min_kb: int = 50) -> list[dict]:
    """Find large objects (>min_kb) currently alive."""
    result = []
    for obj in gc.get_objects():
        try:
            size = sys.getsizeof(obj)
        except (TypeError, AttributeError):
            continue
        if size >= min_kb * 1024:
            result.append({
                "type": type(obj).__name__,
                "size_kb": round(size / 1024, 1),
                "repr": repr(obj)[:200],
            })
    result.sort(key=lambda x: x["size_kb"], reverse=True)
    return result[:50]


def _sa_sessions() -> list[dict]:
    """Report live SQLAlchemy Session identity maps."""
    try:
        from sqlalchemy.orm import Session as SASession

        result = []
        for obj in gc.get_objects():
            if isinstance(obj, SASession) and obj.identity_map:
                types: Counter = Counter()
                for v in obj.identity_map.values():
                    types[type(v).__name__] += 1
                result.append({
                    "id": id(obj),
                    "identity_map_size": len(obj.identity_map),
                    "types": dict(types),
                })
        return result
    except ImportError:
        return []
