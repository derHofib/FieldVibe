"""Lesen des KI-Journals (ki_aktionen) fuer die App (/api/ki/aktionen) und das MCP-Tool lesen/auflisten.

Sichtbarkeit: Mandant-Admins sehen alle Aktionen des Mandanten, alle anderen nur eigene. Mandantentrennung
sichert die RLS der tenant_session; hier nur die Nutzer-Ebene."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ki_aktion import KiAktion
from app.models.ki_verbindung import KiVerbindung
from app.models.user import User
from app.schemas.ki import KiAenderungRead, KiAktionRead, KiRefRead

_BERLIN = ZoneInfo("Europe/Berlin")


def rueckgaengig_moeglich(aktion: KiAktion, jetzt: datetime | None = None) -> bool:
    jetzt = jetzt or datetime.now(timezone.utc)
    return (
        aktion.status == "ausgefuehrt"
        and bool(aktion.rueckweg)
        and aktion.rueckgaengig_bis is not None
        and jetzt < aktion.rueckgaengig_bis
    )


def _anzeige(eintrag: Any) -> str | None:
    if isinstance(eintrag, dict):
        wert = eintrag.get("anzeige")
        return None if wert is None else str(wert)
    return None if eintrag is None else str(eintrag)


def als_read(
    aktion: KiAktion,
    *,
    user_name: str | None,
    client_name: str | None,
    rueckgaengig_von_name: str | None,
    jetzt: datetime | None = None,
) -> KiAktionRead:
    return KiAktionRead(
        id=aktion.id,
        user_id=aktion.user_id,
        user_name=user_name or "Unbekannt",
        ki_verbindung_id=aktion.ki_verbindung_id,
        client_name=client_name,
        tool=aktion.tool,
        aktionsart=aktion.aktionsart,
        stufe=aktion.stufe,
        status=aktion.status,  # type: ignore[arg-type]
        zusammenfassung=aktion.zusammenfassung,
        ziele=[KiRefRead(**z) for z in aktion.ziele],
        erzeugt=[KiRefRead(**z) for z in aktion.erzeugt],
        aenderungen=[
            KiAenderungRead(
                typ=a["typ"],
                id=a["id"],
                label=a["label"],
                feld=a["feld"],
                feld_label=a.get("feld_label") or a["feld"],
                vorher=_anzeige(a.get("vorher")),
                nachher=_anzeige(a.get("nachher")),
            )
            for a in aktion.aenderungen
        ],
        rueckgaengig_moeglich=rueckgaengig_moeglich(aktion, jetzt),
        rueckgaengig_bis=aktion.rueckgaengig_bis,
        rueckgaengig_am=aktion.rueckgaengig_am,
        rueckgaengig_von_name=rueckgaengig_von_name,
        fehler=aktion.fehler,
        erstellt_am=aktion.erstellt_am,
    )


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def _lesbar_machen(session: AsyncSession, zeilen: list[KiAktion]) -> list[KiAktionRead]:
    user_ids = {z.user_id for z in zeilen} | {z.rueckgaengig_von for z in zeilen if z.rueckgaengig_von}
    verbindungen = {z.ki_verbindung_id for z in zeilen if z.ki_verbindung_id}
    namen = (
        {u.id: u.name for u in (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars()}
        if user_ids
        else {}
    )
    clients = (
        {
            v.id: v.client_name
            for v in (await session.execute(select(KiVerbindung).where(KiVerbindung.id.in_(verbindungen)))).scalars()
        }
        if verbindungen
        else {}
    )
    jetzt = datetime.now(timezone.utc)
    return [
        als_read(
            z,
            user_name=namen.get(z.user_id),
            client_name=clients.get(z.ki_verbindung_id) if z.ki_verbindung_id else None,
            rueckgaengig_von_name=namen.get(z.rueckgaengig_von) if z.rueckgaengig_von else None,
            jetzt=jetzt,
        )
        for z in zeilen
    ]


async def auflisten(
    session: AsyncSession,
    *,
    user_id: UUID,
    ist_admin: bool,
    status: str | None = None,
    filter_user_id: UUID | None = None,
    von: date | None = None,
    bis: date | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[KiAktionRead], int]:
    bedingungen = []
    if not ist_admin:
        bedingungen.append(KiAktion.user_id == user_id)
    elif filter_user_id is not None:
        bedingungen.append(KiAktion.user_id == filter_user_id)
    if status:
        bedingungen.append(KiAktion.status == status)
    if von:
        bedingungen.append(KiAktion.erstellt_am >= datetime.combine(von, time.min, tzinfo=_BERLIN))
    if bis:
        bedingungen.append(KiAktion.erstellt_am < datetime.combine(bis + timedelta(days=1), time.min, tzinfo=_BERLIN))
    if q and q.strip():
        bedingungen.append(KiAktion.zusammenfassung.ilike(_like(q.strip()), escape="\\"))
    gesamt = (await session.execute(select(func.count()).select_from(KiAktion).where(*bedingungen))).scalar_one()
    zeilen = list(
        (
            await session.execute(
                select(KiAktion)
                .where(*bedingungen)
                .order_by(KiAktion.erstellt_am.desc(), KiAktion.id)
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )
    return await _lesbar_machen(session, zeilen), gesamt


async def lesen(session: AsyncSession, *, user_id: UUID, ist_admin: bool, aktion_id: UUID) -> KiAktionRead | None:
    zeile = await session.get(KiAktion, aktion_id)
    if zeile is None or (zeile.user_id != user_id and not ist_admin):
        return None
    return (await _lesbar_machen(session, [zeile]))[0]
