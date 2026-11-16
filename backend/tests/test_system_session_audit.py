"""system_session(): Pflicht-Grund und Audit-Eintrag je Oeffnung."""
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as session_modul
from app.db.session import system_session
from app.models.audit_log import AuditLog


@pytest.fixture(autouse=True)
def _audit_an(monkeypatch):
    monkeypatch.setattr(get_settings(), "system_session_audit", True)
    session_modul._audit_zuletzt.clear()
    yield
    session_modul._audit_zuletzt.clear()


async def _eintraege(grund: str | None = None) -> list[AuditLog]:
    async with system_session(grund="test-lesen") as session:
        zeilen = (
            await session.execute(select(AuditLog).where(AuditLog.aktion == "system_session"))
        ).scalars().all()
    return [z for z in zeilen if grund is None or z.payload.get("grund") == grund]


async def test_ohne_grund_wird_abgelehnt():
    with pytest.raises(TypeError):
        async with system_session():  # type: ignore[call-arg]
            pass
    for leer in ("", "   "):
        with pytest.raises(ValueError):
            async with system_session(grund=leer):
                pass


async def test_eintrag_mit_grund_und_aufrufer():
    async with system_session(grund="test-eintrag") as session:
        assert session is not None
    (eintrag,) = await _eintraege("test-eintrag")
    assert eintrag.mandant_id is None
    assert eintrag.akteur_typ == "system"
    assert eintrag.payload["aufrufer"] == f"{__name__}:test_eintrag_mit_grund_und_aufrufer"


async def test_eintrag_bleibt_bei_exception_im_body():
    with pytest.raises(RuntimeError):
        async with system_session(grund="test-rollback"):
            raise RuntimeError("boom")
    assert len(await _eintraege("test-rollback")) == 1


async def test_drosselung_je_grund():
    for _ in range(3):
        async with system_session(grund="test-drossel", drosselung_s=300):
            pass
    assert len(await _eintraege("test-drossel")) == 1
    async with system_session(grund="test-drossel-anders", drosselung_s=300):
        pass
    assert len(await _eintraege("test-drossel-anders")) == 1
    for _ in range(2):
        async with system_session(grund="test-ungedrosselt"):
            pass
    assert len(await _eintraege("test-ungedrosselt")) == 2


async def test_schalter_aus_schreibt_nichts(monkeypatch):
    monkeypatch.setattr(get_settings(), "system_session_audit", False)
    async with system_session(grund="test-aus"):
        pass
    assert await _eintraege("test-aus") == []
