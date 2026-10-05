"""Synchronisierung Altpfad (users.role/account_typ_id) -> Organigramm.

Uebergangszeit: solange die Nutzerverwaltung noch role/account_typ_id setzt, muss
jeder Nutzer eine passende Besetzung haben, sonst haette er unter der Engine
(berechtigung_service) keine Rechte. Angefasst werden ausschliesslich
automatisch angelegte Besetzungen:
  - "Wurzel": die Position ohne Eltern (je Mandant, "Geschäftsführung") fuer mandant_admin
  - "Typ-Position": Position mit account_typ_id = Typ, titel = Typname und
    parent = Wurzel (siehe Migration 0102) fuer role='custom'
Alle anderen Positionen/Besetzungen (manuell im Organigramm gepflegt) bleiben
unberuehrt; beendet wird nur beim tatsaechlichen Wechsel die alte regulaere
Besetzung auf der bisherigen Typ-Position bzw. Wurzel. Bewusst keine
Markierungsspalte (keine Migration): wird eine Typ-Position umbenannt oder
umgehaengt, erkennt der Sync sie nicht mehr und legt bei Bedarf eine neue unter
der Wurzel an.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rechte_registry import scopes_fuer_bereich, alle_bereich_keys
from app.models.account_typ import AccountTyp, AccountTypRecht
from app.models.organigramm import Position, PositionBesetzung
from app.models.user import User
from app.services.audit_service import log_aenderung
from app.services.berechtigung_service import cache_leeren

WURZEL_TITEL = "Geschäftsführung"


async def wurzel_position(session: AsyncSession, mandant_id: UUID) -> Position:
    """Wurzel des Mandanten, wird angelegt falls nicht vorhanden. Bei mehreren
    (nicht vorgesehen) gilt die aelteste."""
    wurzel = (
        await session.execute(
            select(Position)
            .where(
                Position.mandant_id == mandant_id,
                Position.parent_id.is_(None),
                Position.archiviert_am.is_(None),
            )
            .order_by(Position.created_at, Position.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if wurzel is None:
        wurzel = Position(mandant_id=mandant_id, typ="linie", titel=WURZEL_TITEL, reihenfolge=0)
        session.add(wurzel)
        await session.flush()
    return wurzel


async def _typ_position(session: AsyncSession, typ: AccountTyp, *, anlegen: bool) -> Position | None:
    wurzel = await wurzel_position(session, typ.mandant_id)
    position = (
        await session.execute(
            select(Position)
            .where(
                Position.mandant_id == typ.mandant_id,
                Position.account_typ_id == typ.id,
                Position.titel == typ.name,
                Position.parent_id == wurzel.id,
                Position.archiviert_am.is_(None),
            )
            .order_by(Position.created_at, Position.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if position is None and anlegen:
        position = Position(
            mandant_id=typ.mandant_id,
            parent_id=wurzel.id,
            typ="linie",
            titel=typ.name,
            account_typ_id=typ.id,
            reihenfolge=typ.reihenfolge or 0,
        )
        session.add(position)
        await session.flush()
    return position


async def position_fuer_account_typ_anlegen(session: AsyncSession, typ: AccountTyp) -> Position:
    position = await _typ_position(session, typ, anlegen=True)
    assert position is not None
    return position


async def typ_position_umbenennen(
    session: AsyncSession, typ: AccountTyp, *, alter_name: str
) -> None:
    """Nach Umbenennung des Account-Typs, damit die Typ-Position erkennbar bleibt."""
    if alter_name == typ.name:
        return
    wurzel = await wurzel_position(session, typ.mandant_id)
    await session.execute(
        update(Position)
        .where(
            Position.mandant_id == typ.mandant_id,
            Position.account_typ_id == typ.id,
            Position.titel == alter_name,
            Position.parent_id == wurzel.id,
        )
        .values(titel=typ.name)
    )


async def wurzel_fuer_mandant_anlegen(session: AsyncSession, mandant_id: UUID) -> Position:
    return await wurzel_position(session, mandant_id)


async def _aktive_besetzung(
    session: AsyncSession, *, position_id: UUID, user_id: UUID
) -> PositionBesetzung | None:
    return (
        await session.execute(
            select(PositionBesetzung).where(
                PositionBesetzung.position_id == position_id,
                PositionBesetzung.user_id == user_id,
                PositionBesetzung.gueltig_bis.is_(None),
            )
        )
    ).scalar_one_or_none()


def _besetzung_audit(b: PositionBesetzung) -> dict:
    return {
        "id": b.id,
        "position_id": b.position_id,
        "user_id": b.user_id,
        "art": b.art,
        "gueltig_von": b.gueltig_von,
        "gueltig_bis": b.gueltig_bis,
    }


async def _besetzen(
    session: AsyncSession, *, position: Position, user: User, actor_user_id: UUID | None = None
) -> None:
    if await _aktive_besetzung(session, position_id=position.id, user_id=user.id) is not None:
        return
    besetzung = PositionBesetzung(
        mandant_id=position.mandant_id, position_id=position.id, user_id=user.id, art="regulaer"
    )
    session.add(besetzung)
    await session.flush()
    await session.refresh(besetzung)
    await log_aenderung(
        session,
        aktion="besetzung_angelegt",
        mandant_id=position.mandant_id,
        actor_user_id=actor_user_id,
        entity_type="besetzung",
        entity_id=besetzung.id,
        vorher=None,
        nachher={**_besetzung_audit(besetzung), "quelle": "nutzerverwaltung"},
    )


async def _aktive_beenden(
    session: AsyncSession, *bedingungen, actor_user_id: UUID | None = None
) -> None:
    # DB-Zeit statt Python-Zeit (kein Uhren-Versatz zwischen App und DB). Der Check
    # gueltig_bis > gueltig_von verbietet ein Ende zur Beginn-Zeit: im selben
    # Request angelegte Besetzungen (gleiche Transaktionszeit) wurden nie wirksam
    # und werden geloescht statt beendet.
    aktiv = PositionBesetzung.gueltig_bis.is_(None)
    betroffen = (await session.execute(select(PositionBesetzung).where(aktiv, *bedingungen))).scalars().all()
    # Vor dem UPDATE sichern: der Audit-Eintrag braucht den Stand "vorher".
    vorher = [_besetzung_audit(b) for b in betroffen]
    mandanten = {b.id: b.mandant_id for b in betroffen}
    await session.execute(
        update(PositionBesetzung)
        .where(aktiv, PositionBesetzung.gueltig_von < func.now(), *bedingungen)
        .values(gueltig_bis=func.now())
    )
    await session.execute(PositionBesetzung.__table__.delete().where(aktiv, *bedingungen))
    for eintrag in vorher:
        await log_aenderung(
            session,
            aktion="besetzung_beendet",
            mandant_id=mandanten[eintrag["id"]],
            actor_user_id=actor_user_id,
            entity_type="besetzung",
            entity_id=eintrag["id"],
            vorher=eintrag,
            nachher={**eintrag, "gueltig_bis": datetime.now(timezone.utc), "quelle": "nutzerverwaltung"},
        )
    cache_leeren(session)


async def _regulaer_beenden(
    session: AsyncSession, *, position_id: UUID, user_id: UUID, actor_user_id: UUID | None = None
) -> None:
    await _aktive_beenden(
        session,
        PositionBesetzung.position_id == position_id,
        PositionBesetzung.user_id == user_id,
        PositionBesetzung.art == "regulaer",
        actor_user_id=actor_user_id,
    )


async def alle_besetzungen_beenden(
    session: AsyncSession, user_id: UUID, actor_user_id: UUID | None = None
) -> None:
    """Deaktivieren/Anonymisieren: jede aktive Besetzung (auch manuelle, auch
    Vertretungen) endet."""
    await _aktive_beenden(session, PositionBesetzung.user_id == user_id, actor_user_id=actor_user_id)


async def _ziel_position(
    session: AsyncSession, *, mandant_id: UUID | None, role: str, account_typ_id: UUID | None, anlegen: bool
) -> Position | None:
    if mandant_id is None:
        return None
    if role == "mandant_admin":
        return await wurzel_position(session, mandant_id)
    if role == "custom" and account_typ_id is not None:
        typ = await session.get(AccountTyp, account_typ_id)
        if typ is None:
            return None
        return await _typ_position(session, typ, anlegen=anlegen)
    return None


async def besetzung_pflegen(
    session: AsyncSession,
    user: User,
    *,
    neu: bool = False,
    alte_rolle: str | None = None,
    alter_account_typ_id: UUID | None = None,
    war_aktiv: bool = True,
    actor_user_id: UUID | None = None,
) -> None:
    """Gleicht die automatische Besetzung eines Nutzers an role/account_typ_id/aktiv an.

    neu: Nutzer gerade angelegt (Besetzung auf Ziel-Position anlegen).
    alte_rolle/alter_account_typ_id: Stand vor einer Aenderung; unterscheidet sich die
    Ziel-Position, endet die regulaere Besetzung auf der alten.
    war_aktiv: Stand vor einer Aenderung; Reaktivierung legt die Besetzung neu an.
    """
    if not user.aktiv:
        await alle_besetzungen_beenden(session, user.id, actor_user_id)
        return

    ziel = await _ziel_position(
        session, mandant_id=user.mandant_id, role=user.role, account_typ_id=user.account_typ_id, anlegen=True
    )
    if alte_rolle is not None and not neu:
        alt = await _ziel_position(
            session,
            mandant_id=user.mandant_id,
            role=alte_rolle,
            account_typ_id=alter_account_typ_id,
            anlegen=False,
        )
        if alt is not None and (ziel is None or alt.id != ziel.id):
            await _regulaer_beenden(
                session, position_id=alt.id, user_id=user.id, actor_user_id=actor_user_id
            )
            cache_leeren(session)
        wechsel = (alt.id if alt else None) != (ziel.id if ziel else None)
    else:
        wechsel = False

    if ziel is not None and (neu or wechsel or not war_aktiv):
        await _besetzen(session, position=ziel, user=user, actor_user_id=actor_user_id)
        cache_leeren(session)


async def account_typ_flag_in_scope_uebersetzen(
    session: AsyncSession, typ: AccountTyp, *, nur_zugewiesene_kunden: bool
) -> None:
    """Flag account_typen.nur_zugewiesene_kunden -> Scope der account_typ_rechte:
    true setzt alle Rechte in Bereichen, die den Scope "eigene" kennen, auf
    "eigene"; false auf "mandant". Nur bei tatsaechlichem Wechsel aufrufen, sonst
    wuerden fein eingestellte Scopes ueberschrieben."""
    bereiche = [b for b in alle_bereich_keys() if "eigene" in scopes_fuer_bereich(b)]
    await session.execute(
        update(AccountTypRecht)
        .where(AccountTypRecht.account_typ_id == typ.id, AccountTypRecht.bereich.in_(bereiche))
        .values(scope="eigene" if nur_zugewiesene_kunden else "mandant")
    )
    cache_leeren(session)


def scope_fuer_neues_recht(typ: AccountTyp, bereich: str) -> str:
    return "eigene" if typ.nur_zugewiesene_kunden and "eigene" in scopes_fuer_bereich(bereich) else "mandant"
