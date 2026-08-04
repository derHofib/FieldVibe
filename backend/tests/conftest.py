import os
import uuid

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://fieldvibe:fieldvibe@localhost:5432/fieldvibe_test",
)
os.environ.setdefault(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://fieldvibe:fieldvibe@localhost:5432/fieldvibe_test",
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-do-not-use-in-prod")
# Fixed port (not dynamically chosen) because app.services.storage_service
# builds its boto3 clients at import time -- these env vars must exist
# before `from app.main import app` pulls that module in below, so the
# ThreadedMotoServer fixture further down just has to bind the same port
# rather than discover and propagate one after the fact.
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9199")
os.environ.setdefault("S3_PUBLIC_URL_BASE", "http://localhost:9199")
os.environ.setdefault("S3_BUCKET_FOTOS", "fieldvibe-fotos-test")

import pytest
import pytest_asyncio
import sqlalchemy
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from moto.moto_server.threaded_moto_server import ThreadedMotoServer
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.rate_limit import (
    login_account_limiter,
    login_ip_limiter,
    password_reset_ip_limiter,
)
from app.core.security import hash_password
from app.db.session import engine, system_session
from app.main import app
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.kunde_zuweisung import KundeZuweisung
from app.models.mandant import Mandant
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.services import storage_service

_settings = get_settings()
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_test_database_exists() -> None:
    sync_url = sqlalchemy.engine.make_url(_settings.database_url_sync)
    admin_url = sync_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": sync_url.database},
        ).scalar_one_or_none()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{sync_url.database}"'))
    admin_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_per_test():
    """Disposes the app's async engine pool before every test.

    asyncpg connections are bound to the event loop that created them, and
    pytest-asyncio opens a new loop per test function by default. Without
    this, a connection pooled during one test gets handed to a query
    running on the next test's (different) loop and asyncpg raises
    "attached to a different loop". Disposing invalidates the pool so the
    next checkout opens a fresh connection on the loop actually running.
    """
    await engine.dispose()
    yield


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    _ensure_test_database_exists()
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session", autouse=True)
def _s3_test_server():
    """Stands in for MinIO: a real local S3-compatible HTTP server (moto's
    server mode, not its request-mocking decorator -- the latter only
    intercepts calls to actual AWS hostnames, not a custom endpoint_url like
    ours). storage_service's module-level boto3 clients were already built
    against S3_ENDPOINT_URL/S3_PUBLIC_URL_BASE at import time, so this just
    has to listen on that same fixed port.
    """
    server = ThreadedMotoServer(port=9199)
    server.start()
    try:
        storage_service._internal_client.create_bucket(Bucket=storage_service.BUCKET)
        yield
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    # Alle Test-Requests laufen ueber httpx' ASGITransport mit derselben
    # festen Client-IP (127.0.0.1) -- ohne Reset wuerden sich Fehlversuche
    # aus verschiedenen, voneinander unabhaengigen Tests im selben
    # In-Memory-Rate-Limiter aufsummieren und irgendwann faelschlich einen
    # spaeteren Test mit 429 blockieren.
    login_account_limiter._failures.clear()
    login_ip_limiter._failures.clear()
    password_reset_ip_limiter._failures.clear()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE audit_log, notifications, tag_assignments, tags, zeiterfassung, "
                "termine, pruefzyklen, pruefmittel, maengel, angebot_positionen, angebote, "
                "rechnung_positionen, rechnungen, highlights, "
                "bestellung_positionen, material_bedarfe, bestellungen, lieferanten, "
                "material_verwendungen, material, "
                "kundenportal_zugaenge, kunde_zuweisungen, "
                "vorgang_events, vorgaenge, vertraege, "
                "anlagen, kunden, mandant_integrationen, users, mandanten "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def make_mandant():
    async def _make(name: str = "Testbetrieb", status: str = "aktiv") -> Mandant:
        async with system_session() as session:
            mandant = Mandant(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}", status=status)
            session.add(mandant)
            await session.flush()
            # Spiegelt app/api/routes/mandanten.py:create_mandant -- jeder
            # Mandant bekommt sofort einen Lagerort fuer die Materialwirtschaft.
            session.add(
                Anlage(
                    mandant_id=mandant.id,
                    kunde_id=None,
                    objekttyp="lager",
                    bezeichnung="Zentrallager",
                    adresse={},
                    stammdaten={},
                )
            )
            await session.flush()
            await session.refresh(mandant)
            return mandant

    return _make


@pytest_asyncio.fixture
async def make_user():
    async def _make(
        *,
        mandant: Mandant | None,
        role: str,
        email: str | None = None,
        password: str = "hunter2!!",
        name: str = "Test User",
        aktiv: bool = True,
    ) -> User:
        async with system_session() as session:
            user = User(
                mandant_id=mandant.id if mandant else None,
                email=email or f"{uuid.uuid4().hex[:10]}@example.de",
                password_hash=hash_password(password),
                role=role,
                name=name,
                aktiv=aktiv,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
            user._plaintext_password = password  # convenience for tests
            return user

    return _make


@pytest_asyncio.fixture
async def make_kunde():
    async def _make(*, mandant: Mandant, name: str = "Testkunde", **kwargs) -> Kunde:
        async with system_session() as session:
            kunde = Kunde(
                mandant_id=mandant.id,
                kundennummer=kwargs.pop("kundennummer", f"K-{uuid.uuid4().hex[:6]}"),
                name=name,
                portal_slug=kwargs.pop("portal_slug", uuid.uuid4().hex),
                **kwargs,
            )
            session.add(kunde)
            await session.flush()
            await session.refresh(kunde)
            return kunde

    return _make


@pytest_asyncio.fixture
async def make_anlage():
    async def _make(
        *, mandant: Mandant, kunde: Kunde | None = None, bezeichnung: str = "Hauptverteilung", **kwargs
    ) -> Anlage:
        async with system_session() as session:
            anlage = Anlage(
                mandant_id=mandant.id,
                kunde_id=kunde.id if kunde is not None else None,
                bezeichnung=bezeichnung,
                adresse=kwargs.pop("adresse", {"strasse": "Teststr. 1", "ort": "Musterstadt"} if kunde else {}),
                **kwargs,
            )
            session.add(anlage)
            await session.flush()
            await session.refresh(anlage)
            return anlage

    return _make


@pytest_asyncio.fixture
async def make_vertrag():
    async def _make(
        *, mandant: Mandant, kunde: Kunde, abrechnungsart: str = "wartungsvertrag", **kwargs
    ) -> Vertrag:
        async with system_session() as session:
            vertrag = Vertrag(
                mandant_id=mandant.id,
                kunde_id=kunde.id,
                bezeichnung=kwargs.pop("bezeichnung", "Wartungsvertrag"),
                abrechnungsart=abrechnungsart,
                **kwargs,
            )
            session.add(vertrag)
            await session.flush()
            await session.refresh(vertrag)
            return vertrag

    return _make


@pytest_asyncio.fixture
async def make_vorgang():
    async def _make(
        *,
        mandant: Mandant,
        kunde: Kunde,
        titel: str = "Testvorgang",
        abrechnungsart: str = "aufwand",
        leistungstyp: str = "stoerung",
        **kwargs,
    ) -> Vorgang:
        async with system_session() as session:
            vorgang = Vorgang(
                mandant_id=mandant.id,
                vorgangsnummer=kwargs.pop("vorgangsnummer", f"V-{uuid.uuid4().hex[:6]}"),
                kunde_id=kunde.id,
                titel=titel,
                abrechnungsart=abrechnungsart,
                leistungstyp=leistungstyp,
                **kwargs,
            )
            session.add(vorgang)
            await session.flush()
            await session.refresh(vorgang)
            return vorgang

    return _make


@pytest_asyncio.fixture
async def make_kunde_zuweisung():
    async def _make(*, mandant: Mandant, kunde: Kunde, techniker: User) -> KundeZuweisung:
        async with system_session() as session:
            zuweisung = KundeZuweisung(
                mandant_id=mandant.id, kunde_id=kunde.id, user_id=techniker.id
            )
            session.add(zuweisung)
            await session.flush()
            await session.refresh(zuweisung)
            return zuweisung

    return _make


async def login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
