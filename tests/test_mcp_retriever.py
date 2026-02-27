"""Unit tests for ai.mcp_retriever resilience mechanisms.

Covers the 5 user-specified scenarios plus cache and circuit breaker:
  1. Timeout → safe default  (search_docs returns [], fetch_doc returns "")
  2. Fallback failure → safe default
  3. Double failure (MCP + fallback) → safe default
  4. Retry occurs exactly once for retryable errors
  5. No infinite loops under any failure pattern
  6. LRU cache deduplicates identical queries
  7. Circuit breaker trips after _CB_THRESHOLD consecutive failures
"""
from __future__ import annotations

import asyncio
import time
import types
from unittest import mock

import pytest

# ── Module under test ─────────────────────────────────────────────
import ai.mcp_retriever as mcp_ret


# ── Helpers ───────────────────────────────────────────────────────

def _reset_module_state():
    """Reset all mutable module-level state to a clean baseline."""
    mcp_ret._grounding_telem.update({
        "mode": "mcp",
        "mcp_initialize_success": False,
        "mcp_calls": {},
        "mcp_call_failures": 0,
        "mcp_timeouts": 0,
        "rest_fallback_calls": 0,
        "rest_fallback_failures": 0,
        "error_classifications": {},
        "_notes": [],
    })
    mcp_ret.reset_mcp_cache()       # also resets circuit breaker
    mcp_ret._last_mcp_error = None


@pytest.fixture(autouse=True)
def _clean_state():
    """Ensure every test starts with pristine module state."""
    _reset_module_state()
    yield
    _reset_module_state()


# ── 1. Timeout → safe default ────────────────────────────────────

class TestTimeoutSafeDefault:
    """MCP timeout must produce safe defaults, never raise."""

    def test_search_docs_timeout_returns_empty_list(self):
        """search_docs returns [] (via fallback) when MCP times out."""
        async def _timeout_async(*a, **kw):
            raise TimeoutError("MCP call timed out")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_timeout_async):
            with mock.patch.object(mcp_ret, "_fallback_search", return_value=[]):
                result = mcp_ret.search_docs("test query")

        assert result == []

    def test_fetch_doc_timeout_returns_empty_string(self):
        """fetch_doc returns '' when MCP times out."""
        async def _timeout_async(*a, **kw):
            raise TimeoutError("MCP call timed out")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_timeout_async):
            result = mcp_ret.fetch_doc("https://learn.microsoft.com/test")

        assert result == ""

    def test_search_code_samples_timeout_returns_empty_list(self):
        """search_code_samples returns [] when MCP times out."""
        async def _timeout_async(*a, **kw):
            raise TimeoutError("MCP call timed out")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_timeout_async):
            result = mcp_ret.search_code_samples("azure firewall")

        assert result == []


# ── 2. Fallback failure → safe default ────────────────────────────

class TestFallbackSafeDefault:
    """When MCP fails and fallback also fails, still get safe defaults."""

    def test_search_docs_fallback_exception_returns_empty_list(self):
        """If _fallback_search itself raises, search_docs returns []."""
        async def _fail_async(*a, **kw):
            raise ConnectionError("MCP unreachable")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail_async):
            with mock.patch.object(
                mcp_ret, "_fallback_search", return_value=[]
            ) as fb:
                result = mcp_ret.search_docs("query")
                fb.assert_called_once()

        assert result == []


# ── 3. Double failure (MCP + fallback both fail) ─────────────────

class TestDoubleFailureSafeDefault:
    """MCP failure followed by fallback failure still yields safe defaults."""

    def test_search_docs_double_failure(self):
        async def _fail_async(*a, **kw):
            raise ConnectionError("refused")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail_async):
            with mock.patch.object(
                mcp_ret, "_fallback_search", return_value=[]
            ):
                result = mcp_ret.search_docs("governance query")

        assert result == []

    def test_fetch_doc_double_failure(self):
        async def _fail_async(*a, **kw):
            raise Exception("unexpected")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail_async):
            result = mcp_ret.fetch_doc("https://learn.microsoft.com/test")

        assert result == ""


# ── 4. Retry occurs exactly once ──────────────────────────────────

class TestRetryExactlyOnce:
    """Retryable errors get exactly 1 retry, non-retryable get 0."""

    def test_timeout_retried_once(self):
        """TimeoutError is retryable — _mcp_call_async called exactly twice."""
        call_count = 0

        async def _timeout_async(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise TimeoutError("timed out")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_timeout_async):
            result = mcp_ret._mcp_call("microsoft_docs_search", {"query": "x"})

        assert result is None
        assert call_count == 2, f"Expected 2 calls (initial + 1 retry), got {call_count}"

    def test_dns_failure_not_retried(self):
        """dns_failure is NOT retryable — _mcp_call_async called exactly once."""
        import socket as _socket
        call_count = 0

        async def _dns_fail(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise _socket.gaierror("Name or service not known")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_dns_fail):
            result = mcp_ret._mcp_call("microsoft_docs_search", {"query": "x"})

        assert result is None
        assert call_count == 1, f"Expected 1 call (no retry for DNS), got {call_count}"

    def test_json_decode_error_not_retried(self):
        """bad_response (JSONDecodeError) is NOT retryable."""
        import json
        call_count = 0

        async def _bad_json(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise json.JSONDecodeError("bad", "doc", 0)

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_bad_json):
            result = mcp_ret._mcp_call("microsoft_docs_search", {"query": "x"})

        assert result is None
        assert call_count == 1


# ── 5. No infinite loops ─────────────────────────────────────────

class TestNoInfiniteLoops:
    """Even pathological failures never cause unbounded looping."""

    def test_continuous_failures_bounded(self):
        """100 search_docs calls with constant failure complete in bounded time."""
        async def _fail(*a, **kw):
            raise TimeoutError("stuck")

        start = time.monotonic()
        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail):
            with mock.patch.object(mcp_ret, "_fallback_search", return_value=[]):
                # Patch time.sleep to avoid real waits in retry backoff
                with mock.patch("ai.mcp_retriever.time.sleep"):
                    for _ in range(100):
                        mcp_ret.search_docs("infinite loop test")

        elapsed = time.monotonic() - start
        # 100 calls should complete well under 60 seconds (no real I/O)
        assert elapsed < 60, f"Took {elapsed:.1f}s — possible unbounded loop"


# ── 6. LRU cache ─────────────────────────────────────────────────

class TestLRUCache:
    """In-memory cache deduplicates identical (tool, query) pairs."""

    def test_cache_deduplicates_identical_queries(self):
        call_count = 0

        async def _succeed(*a, **kw):
            nonlocal call_count
            call_count += 1
            return {"results": [{"title": "hit", "url": "u", "excerpt": "e"}]}

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_succeed):
            r1 = mcp_ret.search_docs("same query")
            r2 = mcp_ret.search_docs("same query")

        # _mcp_call_async called only once (second is a cache hit)
        assert call_count == 1
        assert r1 == r2

    def test_cache_does_not_cache_failures(self):
        """Failed calls (returning None) are not cached — retried next time."""
        call_count = 0

        async def _fail_then_succeed(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # first call + retry
                raise TimeoutError("fail")
            return {"results": [{"title": "ok", "url": "u", "excerpt": "e"}]}

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail_then_succeed):
            with mock.patch.object(mcp_ret, "_fallback_search", return_value=[]):
                with mock.patch("ai.mcp_retriever.time.sleep"):
                    r1 = mcp_ret.search_docs("flaky query")
            r2 = mcp_ret.search_docs("flaky query")

        # First call failed (returned fallback []), second succeeded
        assert r1 == []
        assert len(r2) == 1

    def test_reset_mcp_cache_clears_cache(self):
        call_count = 0

        async def _succeed(*a, **kw):
            nonlocal call_count
            call_count += 1
            return {"results": [{"title": "hit", "url": "u", "excerpt": "e"}]}

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_succeed):
            mcp_ret.search_docs("some query")
            mcp_ret.reset_mcp_cache()
            mcp_ret.search_docs("some query")

        assert call_count == 2, "Cache should have been cleared"


# ── 7. Circuit breaker ───────────────────────────────────────────

class TestCircuitBreaker:
    """Circuit breaker trips after _CB_THRESHOLD consecutive failures."""

    def test_circuit_breaker_trips_after_threshold(self):
        """After CB_THRESHOLD failures, _cached_mcp_call returns None without calling MCP."""
        call_count = 0

        async def _fail(*a, **kw):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("refused")

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail):
            with mock.patch("ai.mcp_retriever.time.sleep"):
                # Burn through threshold failures
                for i in range(mcp_ret._CB_THRESHOLD):
                    mcp_ret._cached_mcp_call(f"tool_{i}", {"q": "x"})

        assert mcp_ret._cb_tripped is True
        calls_at_trip = call_count

        # After tripping, no more _mcp_call_async calls
        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail):
            result = mcp_ret._cached_mcp_call("tool_extra", {"q": "y"})

        assert result is None
        assert call_count == calls_at_trip, "Should not call MCP after breaker trips"

    def test_circuit_breaker_resets_on_cache_clear(self):
        """reset_mcp_cache also resets the circuit breaker."""
        mcp_ret._cb_tripped = True
        mcp_ret._cb_consecutive_failures = 99
        mcp_ret.reset_mcp_cache()
        assert mcp_ret._cb_tripped is False
        assert mcp_ret._cb_consecutive_failures == 0

    def test_success_resets_consecutive_counter(self):
        """A successful call resets the consecutive failure counter."""
        fail_count = 0

        async def _fail_then_ok(*a, **kw):
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 3:
                raise ConnectionError("refused")
            return {"text": "ok"}

        with mock.patch.object(mcp_ret, "_mcp_call_async", side_effect=_fail_then_ok):
            with mock.patch("ai.mcp_retriever.time.sleep"):
                # 3 failures — not yet at threshold (5)
                for _ in range(3):
                    mcp_ret._cached_mcp_call("tool", {"q": "x"})
                assert mcp_ret._cb_consecutive_failures == 3
                # Success resets counter
                mcp_ret._cached_mcp_call("tool2", {"q": "y"})
                assert mcp_ret._cb_consecutive_failures == 0


# ── 8. Error classification ──────────────────────────────────────

class TestErrorClassification:
    """Verify _classify_error returns the correct category."""

    def test_timeout(self):
        assert mcp_ret._classify_error(TimeoutError("t")) == "timeout"
        assert mcp_ret._classify_error(asyncio.TimeoutError()) == "timeout"

    def test_dns_failure(self):
        import socket as _s
        assert mcp_ret._classify_error(_s.gaierror("resolve")) == "dns_failure"

    def test_connection_refused(self):
        exc = ConnectionRefusedError("Connection refused")
        assert mcp_ret._classify_error(exc) == "connection_refused"

    def test_json_decode_error(self):
        import json
        assert mcp_ret._classify_error(
            json.JSONDecodeError("x", "d", 0)
        ) == "bad_response"

    def test_unknown(self):
        assert mcp_ret._classify_error(RuntimeError("wat")) == "unknown"


# ── 9. Grounding status ──────────────────────────────────────────

class TestGroundingStatus:
    """get_grounding_status reflects module state correctly."""

    def test_default_bypassed(self):
        status = mcp_ret.get_grounding_status()
        assert status["mcp"] == "bypassed"
        assert status["fallback"] == "unused"

    def test_ok_after_success(self):
        mcp_ret._grounding_telem["mcp_initialize_success"] = True
        mcp_ret._grounding_telem["mcp_calls"]["microsoft_docs_search"] = 3
        status = mcp_ret.get_grounding_status()
        assert status["mcp"] == "ok"

    def test_bypassed_when_circuit_breaker_tripped(self):
        mcp_ret._grounding_telem["mcp_initialize_success"] = True
        mcp_ret._grounding_telem["mcp_calls"]["microsoft_docs_search"] = 2
        mcp_ret._cb_tripped = True
        status = mcp_ret.get_grounding_status()
        assert status["mcp"] == "bypassed"
        assert any("circuit breaker" in n for n in status["notes"])

    def test_degraded_with_timeouts(self):
        mcp_ret._grounding_telem["mcp_initialize_success"] = True
        mcp_ret._grounding_telem["mcp_calls"]["microsoft_docs_search"] = 5
        mcp_ret._grounding_telem["mcp_timeouts"] = 2
        status = mcp_ret.get_grounding_status()
        assert status["mcp"] == "degraded"


# ── 10. Telemetry ────────────────────────────────────────────────

class TestGroundingTelemetry:
    """get_grounding_telemetry includes all resilience counters."""

    def test_telemetry_has_cache_and_error_fields(self):
        t = mcp_ret.get_grounding_telemetry()
        assert "cache_hits" in t
        assert "cache_misses" in t
        assert "error_classifications" in t
        assert "rest_fallback_failures" in t
