"""In-Prozess Rate-Limiting fuer Login-/Passwort-Endpoints.

Kein Redis im Stack (siehe docker-compose.yml), Backend laeuft als einzelner
Container -- ein simpler In-Memory-Zaehler pro Prozess reicht damit aus, ohne
eine zusaetzliche Infrastruktur-Abhaengigkeit einzufuehren. Faellt bei einem
Neustart des Containers zurueck auf Null, was fuer einen Brute-Force-Schutz
akzeptabel ist (ein Angreifer muesste den Container-Neustart abpassen).
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Sperrt einen Schluessel, sobald er innerhalb von `window_seconds`
    `max_attempts` Fehlversuche gesammelt hat. Die Sperre laeuft von selbst
    wieder ab, sobald der aelteste gezaehlte Fehlversuch aus dem Fenster
    faellt -- kein separater Lockout-Timer noetig."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        bucket = self._failures[key]
        cutoff = now - self._window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if not bucket:
            del self._failures[key]
        return bucket

    def check(self, key: str) -> None:
        """Raises 429 if `key` is currently locked out."""
        now = time.monotonic()
        bucket = self._failures.get(key)
        if bucket is None:
            return
        bucket = self._prune(key, now)
        if len(bucket) >= self._max_attempts:
            retry_after = int(self._window_seconds - (now - bucket[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Zu viele Fehlversuche. Bitte später erneut versuchen.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._prune(key, now)
        if not bucket:
            bucket = self._failures[key]
        bucket.append(now)

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)


# Zwei Ebenen: pro Account (email) enger begrenzt, damit gezielte Angriffe
# auf ein einzelnes Konto frueh blockiert werden; pro IP weiter gefasst,
# damit ein Passwort-Spraying ueber viele Konten hinweg von derselben Quelle
# ebenfalls gebremst wird, ohne normale Nutzer an einem NAT/Firmennetz zu
# behindern.
login_account_limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=15 * 60)
login_ip_limiter = SlidingWindowRateLimiter(max_attempts=20, window_seconds=15 * 60)

password_reset_ip_limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=60 * 60)


def client_ip(request) -> str:  # type: ignore[no-untyped-def]
    return request.client.host if request.client else "unknown"
