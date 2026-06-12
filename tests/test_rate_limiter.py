"""
tests/test_rate_limiter.py
---------------------------
Unit tests for the rate limiting utility.

These tests use the RateLimiter class directly (not through HTTP)
so they run fast without needing a live server.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for the sliding window rate limiter."""

    def test_allows_requests_within_limit(self):
        """Should allow up to max_requests."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        for i in range(5):
            allowed, remaining = limiter.is_allowed("test_client")
            assert allowed, f"Request {i+1} should be allowed"

    def test_blocks_after_limit_exceeded(self):
        """Should block the (max_requests + 1)th request."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("test_client")
        # 4th request should be blocked
        allowed, remaining = limiter.is_allowed("test_client")
        assert not allowed
        assert remaining == 0

    def test_remaining_decrements(self):
        """Remaining count should decrease with each request."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        _, remaining_1 = limiter.is_allowed("test_client")
        _, remaining_2 = limiter.is_allowed("test_client")
        assert remaining_2 < remaining_1

    def test_different_clients_are_independent(self):
        """One client hitting the limit should not affect other clients."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        # Exhaust client A
        limiter.is_allowed("client_a")
        limiter.is_allowed("client_a")
        allowed_a, _ = limiter.is_allowed("client_a")
        assert not allowed_a
        # Client B should be unaffected
        allowed_b, _ = limiter.is_allowed("client_b")
        assert allowed_b

    def test_reset_clears_limit(self):
        """After reset, client should be allowed again."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("test_client")
        allowed, _ = limiter.is_allowed("test_client")
        assert not allowed
        limiter.reset("test_client")
        allowed_after_reset, _ = limiter.is_allowed("test_client")
        assert allowed_after_reset

    def test_window_expiry(self):
        """Requests older than the window should not count."""
        limiter = RateLimiter(max_requests=2, window_seconds=1)  # 1 second window
        limiter.is_allowed("test_client")
        limiter.is_allowed("test_client")
        # Confirm blocked
        allowed, _ = limiter.is_allowed("test_client")
        assert not allowed
        # Wait for window to expire
        time.sleep(1.1)
        # Should be allowed again
        allowed_after_wait, _ = limiter.is_allowed("test_client")
        assert allowed_after_wait

    def test_get_count(self):
        """get_count should return the current request count."""
        limiter = RateLimiter(max_requests=10, window_seconds=60)
        assert limiter.get_count("new_client") == 0
        limiter.is_allowed("new_client")
        limiter.is_allowed("new_client")
        assert limiter.get_count("new_client") == 2

    def test_cleanup_removes_stale_entries(self):
        """cleanup_old_keys should remove clients with no recent activity."""
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        limiter.is_allowed("stale_client")
        time.sleep(1.1)
        removed = limiter.cleanup_old_keys()
        assert removed >= 1
