"""Login-Limiter hinter Reverse-Proxy: die echte Client-IP kommt aus
Uvicorns ProxyHeadersMiddleware (FORWARDED_ALLOW_IPS), nicht aus eigenem
Header-Parsing; zusaetzlich zaehlt ein Limiter pro Konto."""

import pytest
from httpx import ASGITransport, AsyncClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.main import app
from app.core.rate_limit import login_account_limiter, login_ip_limiter

PROXY = ("172.18.0.5", 40000)


def _client(*, trusted: str, peer: tuple[str, int]) -> AsyncClient:
    wrapped = ProxyHeadersMiddleware(app, trusted_hosts=trusted)
    return AsyncClient(transport=ASGITransport(app=wrapped, client=peer), base_url="http://test")


async def _fehlversuche(ac: AsyncClient, n: int, xff: str | None, email_prefix: str = "x") -> int:
    headers = {"X-Forwarded-For": xff} if xff else {}
    letzter = 0
    for i in range(n):
        resp = await ac.post(
            "/api/auth/login",
            json={"email": f"{email_prefix}{i}@example.de", "password": "falsch-123456"},
            headers=headers,
        )
        letzter = resp.status_code
    return letzter


@pytest.mark.asyncio
async def test_zwei_clients_hinter_vertrauenswuerdigem_proxy_getrennt_gezaehlt():
    async with _client(trusted="172.16.0.0/12", peer=PROXY) as ac:
        assert await _fehlversuche(ac, 20, "203.0.113.1") == 401
        assert await _fehlversuche(ac, 1, "203.0.113.1") == 429
        # Zweiter Client hinter demselben Proxy ist nicht mitgesperrt.
        assert await _fehlversuche(ac, 1, "203.0.113.2", "andere") == 401
    assert set(login_ip_limiter._failures) == {"203.0.113.1", "203.0.113.2"}


@pytest.mark.asyncio
async def test_gefaelschter_xff_von_nicht_vertrauenswuerdiger_quelle_wird_ignoriert():
    async with _client(trusted="172.16.0.0/12", peer=("198.51.100.7", 5555)) as ac:
        # Jede Anfrage behauptet eine andere IP -- gezaehlt wird trotzdem die echte Peer-IP.
        for i in range(20):
            await _fehlversuche(ac, 1, f"10.0.0.{i}", f"f{i}")
        resp = await ac.post(
            "/api/auth/login",
            json={"email": "neu@example.de", "password": "falsch-123456"},
            headers={"X-Forwarded-For": "10.0.0.99"},
        )
        assert resp.status_code == 429
    assert set(login_ip_limiter._failures) == {"198.51.100.7"}


@pytest.mark.asyncio
async def test_konto_sperre_greift_unabhaengig_von_der_ip(make_mandant, make_user):
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")
    async with _client(trusted="172.16.0.0/12", peer=PROXY) as ac:
        for i in range(5):
            resp = await ac.post(
                "/api/auth/login",
                json={"email": user.email, "password": "falsch"},
                headers={"X-Forwarded-For": f"203.0.113.{i + 10}"},
            )
            assert resp.status_code == 401
        # Sechster Versuch von einer frischen IP, sogar mit korrektem Passwort: gesperrt.
        resp = await ac.post(
            "/api/auth/login",
            json={"email": user.email, "password": "korrekt-123"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert resp.status_code == 429


@pytest.mark.asyncio
async def test_unbekannte_email_wird_gleich_gezaehlt_und_beantwortet(make_mandant, make_user):
    """Keine Account-Enumeration: existierendes und nicht existierendes Konto
    zeigen dieselbe Antwort und werden gleich gesperrt."""
    mandant = await make_mandant()
    user = await make_user(mandant=mandant, role="mandant_admin", password="korrekt-123")
    async with _client(trusted="172.16.0.0/12", peer=PROXY) as ac:
        antworten = []
        for email in (user.email, "gibtsnicht@example.de"):
            for i in range(5):
                resp = await ac.post(
                    "/api/auth/login",
                    json={"email": email, "password": "falsch"},
                    headers={"X-Forwarded-For": f"203.0.113.{i + 50 if email == user.email else i + 150}"},
                )
                antworten.append((resp.status_code, resp.json()["detail"]))
            resp = await ac.post(
                "/api/auth/login",
                json={"email": email, "password": "falsch"},
                headers={"X-Forwarded-For": "203.0.113.200"},
            )
            antworten.append((resp.status_code, resp.json()["detail"]))
    assert antworten[:6] == antworten[6:]
    assert len(login_account_limiter._failures) == 2


@pytest.mark.asyncio
async def test_partner_login_ist_limitiert():
    async with _client(trusted="172.16.0.0/12", peer=PROXY) as ac:
        for _ in range(5):
            resp = await ac.post(
                "/api/partnerportal/auth/login",
                json={"email": "p@example.de", "password": "falsch"},
                headers={"X-Forwarded-For": "203.0.113.5"},
            )
            assert resp.status_code == 401
        resp = await ac.post(
            "/api/partnerportal/auth/login",
            json={"email": "p@example.de", "password": "falsch"},
            headers={"X-Forwarded-For": "203.0.113.6"},
        )
        assert resp.status_code == 429
