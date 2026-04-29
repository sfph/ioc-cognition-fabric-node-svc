# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Background event-loop lag sampler with stack-snapshot on wedge events.

When ``/decide`` requests pile up in uvicorn's accept queue, the underlying
cause is usually that the single event loop is blocked elsewhere.  This
module answers *who* is blocking it.

Two pieces of data:
    1. **Continuous lag samples** — a background task sleeps in 10 ms ticks
       and records (loop_time_after_sleep − loop_time_before_sleep − interval).
       That delta is event-loop block time directly attributable to whatever
       coroutine was running on the loop during the sleep window.
    2. **Stack snapshot on wedge** — when a single sample exceeds
       ``WEDGE_THRESHOLD_MS``, snapshot ``asyncio.all_tasks()`` and emit a
       structured warning with the current frame of every running (non-self)
       task.  That points the finger at the offending coroutine.

Per-request stats: the request middleware can call
``loop_lag_window_start()`` / ``loop_lag_window_stop()`` to slice the rolling
sample buffer for the lifetime of one request and stamp the slice into the
``_timing`` envelope (so the client sees ``cfn_loop_lag_*`` next to
``wire_to_middleware_ms``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# How often the sampler wakes up.  10 ms gives µs-level resolution on a
# healthy loop without measurable overhead (one sleep + one append per tick).
SAMPLE_INTERVAL_S = 0.010

# Lag value above which we emit a stack snapshot.  500 ms means we won't spam
# logs for normal scheduling jitter, but anything that can plausibly explain
# multi-second event-loop wedges will trip it many times over.
WEDGE_THRESHOLD_MS = 500.0

# Cap snapshot rate so a sustained wedge doesn't emit thousands of identical
# log lines.  One snapshot per second is plenty to identify the culprit.
SNAPSHOT_MIN_INTERVAL_S = 1.0


@dataclass
class _SamplerState:
    """Singleton holding the live sampler task and rolling samples buffer."""

    task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    # (perf_counter_at_sample, lag_ms) tuples.  We keep a bounded deque-like
    # list; older entries get popped when we exceed _MAX_SAMPLES.  A list is
    # fine here — append/pop(0) is cheap relative to the work the loop does.
    samples: list[tuple[float, float]] = field(default_factory=list)
    last_snapshot_at: float = 0.0


_state = _SamplerState()
_MAX_SAMPLES = 60_000  # ~10 minutes at 10 ms — wraps automatically


# Per-request window markers (perf_counter values).  The middleware reads
# the rolling buffer between ``start`` and ``stop`` to get a per-request
# slice without disturbing the global sampler.
_window_cv: ContextVar[float | None] = ContextVar("_loop_lag_window_start", default=None)


# ─────────────────────────── lifecycle ────────────────────────────


async def _run_sampler() -> None:
    loop = asyncio.get_running_loop()
    while not _state.stop_event.is_set():
        t0 = loop.time()
        try:
            # Race sleep vs stop signal so shutdown is prompt.
            await asyncio.wait_for(_state.stop_event.wait(), timeout=SAMPLE_INTERVAL_S)
            return  # stop_event fired
        except asyncio.TimeoutError:
            pass
        elapsed = loop.time() - t0
        lag_ms = max(0.0, (elapsed - SAMPLE_INTERVAL_S) * 1000.0)

        # Append before snapshot decision so the wedge sample is captured
        # in any in-flight per-request window.
        _state.samples.append((loop.time(), lag_ms))
        if len(_state.samples) > _MAX_SAMPLES:
            # Truncate the oldest 10% in one shot — cheaper than popping
            # one at a time on every overflow tick.
            del _state.samples[: _MAX_SAMPLES // 10]

        if lag_ms >= WEDGE_THRESHOLD_MS:
            now = loop.time()
            if now - _state.last_snapshot_at >= SNAPSHOT_MIN_INTERVAL_S:
                _state.last_snapshot_at = now
                _emit_wedge_snapshot(lag_ms)


def _emit_wedge_snapshot(lag_ms: float) -> None:
    """Log every running task with its current frame.  Called from the sampler
    coroutine itself, so we filter ourselves out of the listing."""
    self_task = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not self_task]
    snapshots: list[dict] = []
    for t in tasks:
        # ``get_coro()`` can return None for tasks created from non-coroutine
        # awaitables; ``get_stack()`` works regardless.
        stack = t.get_stack(limit=8)
        # Format the innermost frame (the current point of execution) plus
        # one or two ancestors for context.  Full traceback is overkill in
        # log lines and hard to read — keep it compact.
        if stack:
            frame_lines = traceback.format_list(traceback.extract_stack(stack[-1]))[-3:]
            top = "".join(frame_lines).strip().replace("\n", " | ")
        else:
            top = "<no stack — task awaiting>"
        snapshots.append(
            {
                "name": t.get_name(),
                "done": t.done(),
                "top_frame": top,
            }
        )
    logger.warning(
        "CFN event-loop wedge: lag=%.1fms threshold=%.0fms running_tasks=%d "
        "(snapshots follow)",
        lag_ms,
        WEDGE_THRESHOLD_MS,
        len(snapshots),
    )
    for s in snapshots:
        logger.warning("  task %s done=%s top=%s", s["name"], s["done"], s["top_frame"])


def start_sampler() -> None:
    """Kick off the background sampler.  Idempotent."""
    if _state.task is not None and not _state.task.done():
        return
    _state.stop_event = asyncio.Event()
    _state.task = asyncio.create_task(_run_sampler(), name="cfn-loop-lag-sampler")
    logger.info(
        "CFN loop-lag sampler started (interval=%.0fms wedge_threshold=%.0fms)",
        SAMPLE_INTERVAL_S * 1000,
        WEDGE_THRESHOLD_MS,
    )


async def stop_sampler() -> None:
    """Stop the sampler gracefully.  Safe to call if never started."""
    if _state.task is None:
        return
    _state.stop_event.set()
    try:
        await asyncio.wait_for(_state.task, timeout=2.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    _state.task = None


# ─────────────────────────── per-request slice ────────────────────────────


def loop_lag_window_start() -> None:
    """Mark the start of a per-request lag-sampling window.

    The middleware calls this on entry; ``loop_lag_window_stop`` returns the
    samples gathered during the window and stamps summary stats into the
    request's ``_timing`` bucket.
    """
    try:
        loop = asyncio.get_running_loop()
        _window_cv.set(loop.time())
    except RuntimeError:
        # Called outside an event-loop context — never raise from
        # instrumentation.
        _window_cv.set(None)


def loop_lag_window_stop() -> dict:
    """Return summary stats for the current request's window.

    Keys (mirrors the client-side ``_LagSampler``):
        - ``cfn_loop_lag_samples_n``
        - ``cfn_loop_lag_mean_ms``
        - ``cfn_loop_lag_p95_ms``
        - ``cfn_loop_lag_max_ms``
    """
    start = _window_cv.get()
    if start is None:
        return {}
    try:
        loop = asyncio.get_running_loop()
        end = loop.time()
    except RuntimeError:
        return {}
    # Slice samples taken during the window.  Linear scan from the tail is
    # fine — we keep ≤ 60k samples and the window is usually < 1k entries.
    in_window = [lag for ts, lag in _state.samples if start <= ts <= end]
    if not in_window:
        return {
            "cfn_loop_lag_samples_n": 0,
            "cfn_loop_lag_mean_ms": 0.0,
            "cfn_loop_lag_p95_ms": 0.0,
            "cfn_loop_lag_max_ms": 0.0,
        }
    in_window_sorted = sorted(in_window)
    p95_idx = max(0, int(round(0.95 * len(in_window_sorted))) - 1)
    return {
        "cfn_loop_lag_samples_n": len(in_window),
        "cfn_loop_lag_mean_ms": round(sum(in_window) / len(in_window), 2),
        "cfn_loop_lag_p95_ms": round(in_window_sorted[p95_idx], 2),
        "cfn_loop_lag_max_ms": round(max(in_window), 2),
    }
