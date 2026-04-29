# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""Per-request timing accumulator.

Lets the FastAPI middleware, dependency factories, and route handlers
cooperate on a single per-request ``dict[str, float]`` of stage timings
so the route handler can attach the whole envelope to its response (next
to ``pipeline_ms`` / ``to_dict_ms`` stamped inside the route).

Why a contextvar instead of ``request.state``:
    - dependency factories don't always have ``request`` in scope without
      adding a parameter, which would change their public signature
    - ``contextvars`` is the canonical asyncio-safe per-task store and
      starlette runs each request in its own task

Usage:
    # in middleware
    timing_reset()
    timing_stamp("request_started_perf", time.perf_counter())

    # in a Depends factory
    with timing_stage("check_workspace_and_mas_ms"):
        ...do work...

    # in the route handler
    envelope = result.setdefault("_timing", {})
    envelope.update(timing_snapshot())
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

# A fresh dict per request — middleware swaps in a new one, deps and the
# handler mutate it.  Default is None so misuse outside a request is loud.
_timing_cv: ContextVar[dict | None] = ContextVar("_request_timing", default=None)


def timing_reset() -> dict:
    """Install a fresh timing dict for this request and return it."""
    new: dict = {}
    _timing_cv.set(new)
    return new


def timing_stamp(key: str, value: float) -> None:
    """Record an absolute marker (e.g. ``request_started_perf``)."""
    bucket = _timing_cv.get()
    if bucket is None:  # outside a request, never raise — instrumentation
        return  # must never break the call
    bucket[key] = value


@contextmanager
def timing_stage(key: str) -> Iterator[None]:
    """Time the wrapped block and add ``key`` (in ms) to the request dict.

    Stages are additive; if the same key is measured twice, the values
    accumulate so multi-call deps (e.g. ``check_workspace_and_mas`` does
    two HTTP requests) report total time spent.
    """
    bucket = _timing_cv.get()
    if bucket is None:
        # Outside a request context — just run the block silently.
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        bucket[key] = round(bucket.get(key, 0.0) + elapsed_ms, 2)


def timing_snapshot() -> dict:
    """Return a shallow copy of the current request's timing dict (or {})."""
    bucket = _timing_cv.get()
    return dict(bucket) if bucket is not None else {}
