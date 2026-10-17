"""Live API client (D-092): sign-in, auth header, expiry, retries and rate limits.

- Sign-in: ``POST /signin`` with ``X-API-Key`` (organizer README). The key comes from the
  ``DEMO_SIGNIN_API_KEY`` environment variable, else from a ``.env`` file in the working directory.
- Every call is built from the sign-in ``base_url`` and ``usage`` header fields (D-004, D-005).
- A new sign-in 30 s before ``expires_in`` runs out, and once on a 401 (D-006; the organizer README
  says to call /signin again when authentication expires, so refresh tokens are not used).
- 429 and 503 wait the advertised time (``Retry-After``, UKG ``X-CallLimit-TimeToWait``), capped
  at 60 s, up to 3 retries. Network errors are tried 3 times; a call still unanswered gets status 0.
- Every body is read with ``parse_source_json`` (exact decimals, D-025).

The token lives only in this object's header and is never part of a reply, an error or a log line.
The transport is a plain function, so tests replace the network with a fake.
"""
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..canonical.parsing import parse_source_json

SIGNIN_URL = "https://tada-demo-provider-signin.onrender.com/signin"
KEY_NAME = "DEMO_SIGNIN_API_KEY"
TENANTS = {"prism": "prismhr", "isol": "isolved", "ukg": "ukg-ready"}  # sign-in tenant -> provider
EXPIRY_MARGIN = 30.0  # seconds before expiry that a new sign-in happens
MAX_WAIT = 60.0
THROTTLE_RETRIES = 3
NETWORK_ATTEMPTS = 3
TIMEOUT = 120.0

# (method, url, headers, body, timeout) -> (status, raw bytes, response headers). Raises OSError
# (or http.client.HTTPException) when no answer arrives.
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes, dict[str, str]]]


class FetchError(Exception):
    """A failure that stops the whole fetch (no key, sign-in refused). Never carries a token."""


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})


def api_key(env_file: Path = Path(".env")) -> str:
    """The sign-in key: the environment variable, else the ``.env`` line. Raises FetchError."""
    key = os.environ.get(KEY_NAME, "").strip()
    if not key and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == KEY_NAME:
                key = value.strip().strip('"').strip("'")
    if not key:
        raise FetchError(f"no sign-in key: set {KEY_NAME} in the environment or in a .env file (never committed)")
    return key


def parse_body(raw: bytes) -> Any:
    """A response body as JSON with exact decimals; None when empty; the text when it is not JSON."""
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    try:
        return parse_source_json(text)
    except ValueError:
        return text


@dataclass(frozen=True)
class Reply:
    status: int  # 0: no answer after every attempt
    body: Any
    headers: dict[str, str] = field(default_factory=dict)  # response headers (send only: a create's Location)


class RateLimit:
    """At most ``calls`` calls in any rolling ``seconds`` window (UKG documents 500 per 60 s)."""

    def __init__(self, calls: int, seconds: float, clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
        self.calls, self.seconds, self.clock, self.sleep = calls, seconds, clock, sleep
        self.sent: deque[float] = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            while True:
                now = self.clock()
                while self.sent and now - self.sent[0] >= self.seconds:
                    self.sent.popleft()
                if len(self.sent) < self.calls:
                    self.sent.append(now)
                    return
                self.sleep(self.seconds - (now - self.sent[0]))


def _wait_seconds(headers: dict[str, str], attempt: int) -> float:
    lowered = {name.lower(): value for name, value in headers.items()}
    for name in ("retry-after", "x-calllimit-timetowait"):
        try:
            return min(max(float(lowered[name]), 0.0), MAX_WAIT)
        except (KeyError, ValueError):
            continue
    return min(5.0 * 2 ** attempt, MAX_WAIT)


class Session:
    """One signed-in demo tenant. Thread safe: calls may run in parallel."""

    def __init__(
        self,
        tenant: str,
        key: str,
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rate_limit: tuple[int, float] | None = None,
        signin_url: str = SIGNIN_URL,
    ) -> None:
        if tenant not in TENANTS:
            raise FetchError(f"unknown tenant {tenant!r}; choose from {', '.join(TENANTS)}")
        self.tenant, self.provider = tenant, TENANTS[tenant]
        self._key, self._transport, self._clock, self._sleep, self._signin_url = key, transport, clock, sleep, signin_url
        self._limit = RateLimit(*rate_limit, clock, sleep) if rate_limit else None
        self._lock = threading.Lock()
        self._header: dict[str, str] = {}
        self._expires_at: float | None = None
        self._generation = 0
        self.sign_ins = 0
        self.base_url = ""
        self.tenant_id = ""
        self.companies: list[dict] = []
        self.sign_in()

    def __repr__(self) -> str:  # never shows the header
        return f"Session(tenant={self.tenant!r}, tenant_id={self.tenant_id!r}, sign_ins={self.sign_ins})"

    def sign_in(self) -> None:
        body = json.dumps({"tenant": self.tenant}).encode()
        headers = {"X-API-Key": self._key, "Content-Type": "application/json"}
        try:
            status, raw, _ = self._transport("POST", self._signin_url, headers, body, TIMEOUT)
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError(f"sign-in for {self.tenant!r} got no answer ({type(exc).__name__})") from None
        if status != 200:
            raise FetchError(f"sign-in for {self.tenant!r} failed: HTTP {status}")
        info = parse_body(raw)
        try:
            auth, usage = info["auth"], info["usage"]
            token = auth.get("access_token") or auth.get("sessionId")
            header = {str(usage["header_name"]): str(usage.get("header_prefix") or "") + str(token)}
            base_url = str(info["base_url"]).rstrip("/")
        except (KeyError, TypeError, AttributeError):
            raise FetchError(f"sign-in for {self.tenant!r} returned an unexpected body") from None
        if not token:
            raise FetchError(f"sign-in for {self.tenant!r} returned no token")
        expires_in = auth.get("expires_in")
        self._header = header
        self._expires_at = self._clock() + float(expires_in) if expires_in else None
        self._generation += 1
        self.sign_ins += 1
        self.base_url = base_url
        self.tenant_id = str(info.get("tenant_id") or "")
        self.companies = list(((info.get("context") or {}).get("companies")) or [])

    def _current(self) -> tuple[dict[str, str], int]:
        """The header to use now, signing in again first when the token is about to expire."""
        with self._lock:
            if self._expires_at is not None and self._clock() > self._expires_at - EXPIRY_MARGIN:
                self.sign_in()
            return dict(self._header), self._generation

    def _renew(self, generation: int) -> None:
        """A 401: sign in again, unless another call already did since this one started."""
        with self._lock:
            if self._generation == generation:
                self.sign_in()

    def _send(self, url: str, headers: dict[str, str]) -> tuple[int, bytes, dict[str, str]] | None:
        for attempt in range(NETWORK_ATTEMPTS):
            if self._limit:
                self._limit.wait()
            try:
                return self._transport("GET", url, headers, None, TIMEOUT)
            except (OSError, http.client.HTTPException):
                if attempt + 1 < NETWORK_ATTEMPTS:
                    self._sleep(2.0 ** attempt)
        return None

    def get(self, path: str, query: dict[str, str] | None = None, headers: dict[str, str] | None = None) -> Reply:
        """GET ``base_url + path`` with ``query``. HTTP errors are replies, not exceptions."""
        url = self.base_url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        renewed = False
        throttled = 0
        while True:
            auth, generation = self._current()
            answer = self._send(url, {"Accept": "application/json", **(headers or {}), **auth})
            if answer is None:
                return Reply(0, None)
            status, raw, response_headers = answer
            if status == 401 and not renewed:
                renewed = True
                self._renew(generation)
                continue
            if status in (429, 503) and throttled < THROTTLE_RETRIES:
                self._sleep(_wait_seconds(response_headers, throttled))
                throttled += 1
                continue
            return Reply(status, parse_body(raw))

    def send(self, method: str, path: str, body: Any = None, content_type: str = "application/json") -> Reply:
        """A write (Phase 8, D-100): ``method`` on ``base_url + path`` with a JSON ``body``. Sent
        once: a write retried after a lost answer could be applied twice, so a network failure is
        status 0 ("outcome unknown"), never retried. A 401 signs in again and a 429 or 503 waits;
        the provider processed nothing in those cases, so they are resent."""
        url = self.base_url + path
        data = json.dumps(body, default=str).encode() if body is not None else None
        renewed = False
        throttled = 0
        while True:
            auth, generation = self._current()
            if self._limit:
                self._limit.wait()
            headers = {"Accept": "application/json", "Content-Type": content_type, **auth}
            try:
                status, raw, response_headers = self._transport(method, url, headers, data, TIMEOUT)
            except (OSError, http.client.HTTPException):
                return Reply(0, None)
            if status == 401 and not renewed:
                renewed = True
                self._renew(generation)
                continue
            if status in (429, 503) and throttled < THROTTLE_RETRIES:
                self._sleep(_wait_seconds(response_headers, throttled))
                throttled += 1
                continue
            return Reply(status, parse_body(raw), dict(response_headers))
