"""
backend/utils/rate_limiter.py
------------------------------
Simple in-memory rate limiter to protect the API from abuse.

WHY RATE LIMITING?
Without limits, a single user (or bot) could:
  - Send thousands of messages per minute
  - Run up massive OpenAI API costs
  - Starve other users of resources

APPROACH — Sliding Window Counter:
For each (session_id, window), we count how many requests were made.
If count exceeds limit, we reject the request with HTTP 429.

LIMITATION:
This in-memory limiter resets when the server restarts and doesn't
share state across multiple server instances. For production scale,
replace with Redis-backed limiting (e.g. redis-py + INCR + EXPIRE).

For a single-instance Render deployment this is perfectly sufficient.

USAGE in a FastAPI endpoint:
    from backend.utils.rate_limiter import rate_limit_check
    from fastapi import Request, HTTPException

    @router.post("/chat")
    async def chat(request: Request, ...):
        rate_limit_check(request)   # raises 429 if over limit
        ...
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional
from fastapi import Request, HTTPException
from loguru import logger


# ─────────────────────────────────────────────
# Rate Limiter Class
# ─────────────────────────────────────────────

class RateLimiter:
    """
    Sliding window rate limiter.

    Tracks request timestamps in a deque (double-ended queue) per client.
    On each request, we:
      1. Remove timestamps older than `window_seconds`
      2. Count remaining timestamps
      3. If count >= max_requests → reject
      4. Otherwise append current timestamp and allow

    SLIDING WINDOW vs FIXED WINDOW:
    Fixed window: "max 20 requests per minute starting at :00"
      Problem: User can send 20 at :59 and 20 more at :00 = 40 in 2 seconds
    Sliding window: "max 20 requests in any 60-second window"
      Solves the burst problem above.

    Thread safety: Uses a Lock because multiple async requests can hit the
    limiter concurrently. The lock is very short-lived (microseconds).
    """

    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        """
        Args:
            max_requests:    Maximum requests allowed in the window
            window_seconds:  Duration of the rolling window
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        # Maps client_key → deque of request timestamps
        # defaultdict(deque) auto-creates an empty deque for new keys
        self._requests: dict = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        """
        Checks if a client is within their rate limit.

        Args:
            client_key: Unique identifier for this client (session_id or IP)

        Returns:
            Tuple of (allowed: bool, remaining: int)
            allowed   = True if request should proceed
            remaining = how many requests left in the current window
        """
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[client_key]

            # Remove timestamps outside the current window
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()

            current_count = len(timestamps)

            if current_count >= self.max_requests:
                remaining = 0
                return False, remaining

            # Record this request
            timestamps.append(now)
            remaining = self.max_requests - len(timestamps)
            return True, remaining

    def reset(self, client_key: str) -> None:
        """Clears the rate limit for a specific client. Useful for testing."""
        with self._lock:
            if client_key in self._requests:
                del self._requests[client_key]

    def get_count(self, client_key: str) -> int:
        """Returns the current request count for a client (for monitoring)."""
        now = time.time()
        window_start = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[client_key]
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()
            return len(timestamps)

    def cleanup_old_keys(self) -> int:
        """
        Removes entries for clients who haven't made requests recently.
        Call this periodically (e.g. from a background task) to prevent
        memory growth from accumulating stale session IDs.

        Returns the number of keys removed.
        """
        now = time.time()
        window_start = now - self.window_seconds
        removed = 0
        with self._lock:
            stale = [k for k, v in self._requests.items() if not v or v[-1] < window_start]
            for key in stale:
                del self._requests[key]
                removed += 1
        return removed


# ─────────────────────────────────────────────
# Singleton Limiter Instances
# ─────────────────────────────────────────────

# Chat endpoint limiter — 20 messages per minute per session
# This is generous for real users but blocks automated abuse.
chat_limiter = RateLimiter(max_requests=20, window_seconds=60)

# Admin endpoint limiter — 10 requests per minute
# Admin routes should only be called by devs/automation, not users.
admin_limiter = RateLimiter(max_requests=10, window_seconds=60)


# ─────────────────────────────────────────────
# FastAPI Dependency
# ─────────────────────────────────────────────

def _get_client_key(request: Request) -> str:
    """
    Extracts a unique identifier for this client from the HTTP request.

    Priority:
    1. X-Session-ID header (set by our Chainlit frontend)
    2. X-Forwarded-For (client's real IP behind a proxy/load balancer)
    3. request.client.host (direct connection IP)
    4. Fallback to "unknown"

    Using session_id is better than IP because:
    - Multiple users can share the same IP (NAT, offices, schools)
    - IP-based limiting unfairly penalises shared networks
    """
    # Check for session ID header first
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return f"session:{session_id}"

    # Try forwarded IP (behind proxy/Render's load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can be a comma-separated list — take the first (original client)
        ip = forwarded_for.split(",")[0].strip()
        return f"ip:{ip}"

    # Direct connection
    if request.client:
        return f"ip:{request.client.host}"

    return "unknown"


def rate_limit_check(request: Request, limiter: Optional[RateLimiter] = None) -> None:
    """
    FastAPI dependency that enforces the chat rate limit.

    Raises HTTP 429 if the client has exceeded their rate limit.

    USAGE in a router:
        @router.post("/chat")
        async def chat_endpoint(
            request: Request,
            _: None = Depends(rate_limit_check),   # ← adds rate limiting
            ...
        ):
            ...

    Or call directly:
        rate_limit_check(request)   # raises 429 if over limit

    Args:
        request: FastAPI request object
        limiter: Which limiter to use (defaults to chat_limiter)
    """
    if limiter is None:
        limiter = chat_limiter

    client_key = _get_client_key(request)
    allowed, remaining = limiter.is_allowed(client_key)

    if not allowed:
        logger.warning(f"Rate limit exceeded for client: {client_key}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Maximum {limiter.max_requests} requests per {limiter.window_seconds} seconds.",
                "retry_after": limiter.window_seconds,
            },
            headers={"Retry-After": str(limiter.window_seconds)},
        )

    # Log remaining for monitoring (only in debug to avoid log noise)
    logger.debug(f"Rate limit OK for {client_key}: {remaining} requests remaining")
