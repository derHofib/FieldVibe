from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthContext,
    get_current_user,
    get_db,
    require_recht,
    require_roles,
)
from app.models.leistungsverzeichnis import (
    Leistungsverzeichnis,
    LeistungsverzeichnisKunde,
    LeistungsverzeichnisPosition,
    LeistungsverzeichnisVerwendung,
)
from app.models.mandant import Mandant
from app.models.material import Material
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.schemas.leistungsverzeichnis import (
    LeistungsverzeichnisPositionCreate,
    LeistungsverzeichnisPositionRead,
    LeistungsverzeichnisPositionUpdate,
    LeistungsverzeichnisVerwendungCreate,
    LeistungsverzeichnisVerwendungMitDetails,
    LeistungsverzeichnisVerwendungRead,
    MaterialPosten,
)
from app.services import papierkorb_service
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN

# Gleiche Rollen-/Rechte-Basis wie kunden.py: das Leistungsverzeichnis
# haengt fachlich am Kunden, daher dieselbe "kunden"-Rechtematrix statt
# eines eigenen Rechts.
router = APIRouter(
    prefix="/api/leistungsverzeichnis",
    tags=["leistungsverzeichnis"],
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "sehen")),
    ],
)


async def _require_position(session: AsyncSession, lv_position_id: UUID) -> LeistungsverzeichnisPosition:
    position = await session.get(LeistungsverzeichnisPosition, lv_position_id)
    if position is None or position.geloescht_am is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht im Leistungsverzeichnis gefunden"
        )
    return position


async def _require_lv(session: AsyncSession, lv_id: UUID) -> Leistungsverzeichnis:
    lv = await session.get(Leistungsverzeichnis, lv_id)
    if lv is None or lv.geloescht_am is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leistungsverzeichnis nicht gefunden")
    return lv


async def _pruefe_material_posten(session: AsyncSession, posten: list[MaterialPosten]) -> None:
    for p in posten:
        if p.material_id is not None and await session.get(Material, p.material_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Material nicht gefunden oder gehört nicht zum eigenen Mandanten",
            )


def _material_posten_zu_json(posten: list[MaterialPosten]) -> list[dict]:
    # Decimal ist nicht JSON-serialisierbar -- als str speichern, damit
    # Pydantic beim Lesen wieder verlustfrei einen Decimal daraus macht.
    return [
        {
            "bezeichnung": p.bezeichnung,
            "menge": str(p.menge),
            "einzelpreis": str(p.einzelpreis),
            "material_id": str(p.material_id) if p.material_id else None,
        }
        for p in posten
    ]


def _berechne_eigenen_preis(position: LeistungsverzeichnisPosition) -> tuple[Decimal, Decimal]:
    """(lohn_gesamt, material_gesamt) einer Position OHNE Kinder, gemaess
    ihres eigenen kalkulationsmodus -- BEREITS inklusive Gemeinkosten-
    Aufschlag (Lohn) bzw. Materialaufschlag UND der abschliessenden
    Gewinn/Wagnis-Marge auf die Zwischensumme aus beidem (proportional auf
    Lohn- und Materialanteil verteilt, damit lohn_gesamt + material_gesamt
    weiterhin exakt einzelpreis ergibt -- wichtig fuer die Summenbildung bei
    Hauptpunkten mit Unterpunkten, siehe _neu_berechnen). Fuer "festpreis"
    gibt es keinen Lohn/Material-Split -- einzelpreis ist dann der einzige,
    frei editierbare Wert, kein automatischer Aufschlag."""
    if position.kalkulationsmodus != "berechnet":
        return Decimal("0"), Decimal("0")
    lohn_basis = Decimal("0")
    if position.lohn_minuten and position.lohn_stundensatz:
        lohn_basis = (Decimal(position.lohn_minuten) / Decimal(60)) * position.lohn_stundensatz
    gemeinkosten = position.lohn_gemeinkosten_prozent or Decimal("0")
    lohn = lohn_basis * (Decimal("1") + gemeinkosten / Decimal("100"))

    material_basis = sum(
        (Decimal(str(p["menge"])) * Decimal(str(p["einzelpreis"])) for p in position.material_posten),
        Decimal("0"),
    )
    aufschlag = position.material_aufschlag_prozent or Decimal("0")
    material = material_basis * (Decimal("1") + aufschlag / Decimal("100"))

    gewinn_wagnis = position.gewinn_wagnis_prozent or Decimal("0")
    gewinn_faktor = Decimal("1") + gewinn_wagnis / Decimal("100")
    return lohn * gewinn_faktor, material * gewinn_faktor


async def _neu_berechnen(session: AsyncSession, position: LeistungsverzeichnisPosition) -> None:
    """Aktualisiert lohn_gesamt/material_gesamt/einzelpreis dieser Position
    und kaskadiert -- eine Ebene tief -- zu ihrem Hauptpunkt, falls sie ein
    Unterpunkt ist. Hat die Position selbst aktive Kinder, ist sie ein
    Hauptpunkt: ihr Preis ist dann immer die Summe der Kinder, unabhaengig
    vom eigenen kalkulationsmodus (der wird dann ignoriert) -- die Kinder
    tragen ihre eigene Gewinn/Wagnis-Marge bereits in ihrem lohn_gesamt/
    material_gesamt, eine erneute Anwendung auf Hauptpunkt-Ebene waere eine
    Doppelverrechnung."""
    kinder = (
        await session.execute(
            select(LeistungsverzeichnisPosition).where(
                LeistungsverzeichnisPosition.eltern_position_id == position.id,
                LeistungsverzeichnisPosition.geloescht_am.is_(None),
            )
        )
    ).scalars().all()

    if kinder:
        # einzelpreis wird bewusst NICHT als lohn+material der Kinder
        # gebildet, sondern als Summe ihrer tatsaechlichen einzelpreis-Werte:
        # ein Festpreis-Unterpunkt hat kein lohn_gesamt/material_gesamt
        # (bleibt dort immer 0, siehe _berechne_eigenen_preis), sein Preis
        # steckt ausschliesslich in einzelpreis -- eine Summe ueber
        # lohn_gesamt+material_gesamt wuerde einen Festpreis-Unterpunkt sonst
        # stillschweigend mit 0 EUR zaehlen. lohn_gesamt/material_gesamt am
        # Hauptpunkt bleiben ein rein informativer Teil-Breakdown ueber die
        # "berechnet"-Unterpunkte, muessen sich also nicht zwingend zu
        # einzelpreis aufaddieren, wenn Festpreis-Unterpunkte gemischt sind.
        lohn = sum((k.lohn_gesamt for k in kinder), Decimal("0"))
        material = sum((k.material_gesamt for k in kinder), Decimal("0"))
        position.lohn_gesamt = lohn
        position.material_gesamt = material
        position.einzelpreis = sum((k.einzelpreis for k in kinder), Decimal("0"))
    elif position.kalkulationsmodus == "berechnet":
        lohn, material = _berechne_eigenen_preis(position)
        position.lohn_gesamt = lohn
        position.material_gesamt = material
        position.einzelpreis = lohn + material
    else:
        position.lohn_gesamt = Decimal("0")
        position.material_gesamt = Decimal("0")
        # einzelpreis bleibt der frei eingetragene Wert.

    await session.flush()

    if position.eltern_position_id is not None:
        eltern = await session.get(LeistungsverzeichnisPosition, position.eltern_position_id)
        if eltern is not None and eltern.geloescht_am is None:
            await _neu_berechnen(session, eltern)


@router.get("", response_model=list[LeistungsverzeichnisPositionRead])
async def list_positionen(
    kunde_id: UUID | None = Query(default=None),
    leistungsverzeichnis_id: UUID | None = Query(default=None),
    eltern_position_id: UUID | None = Query(default=None),
    nur_stundensaetze: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
) -> list[LeistungsverzeichnisPosition]:
    if eltern_position_id is not None:
        stmt = select(LeistungsverzeichnisPosition).where(
            LeistungsverzeichnisPosition.eltern_position_id == eltern_position_id,
            LeistungsverzeichnisPosition.geloescht_am.is_(None),
        )
    else:
        # Nur eigenstaendige Positionen (Hauptpunkte/einfache Eintraege) --
        # Unterpunkte tauchen nicht in dieser Liste auf, nur ueber den
        # eltern_position_id-Filter.
        stmt = select(LeistungsverzeichnisPosition).where(
            LeistungsverzeichnisPosition.eltern_position_id.is_(None),
            LeistungsverzeichnisPosition.geloescht_am.is_(None),
        )
        if leistungsverzeichnis_id is not None:
            # Verwaltungsseite eines konkreten LV: nur dessen eigene
            # Hauptpunkte.
            stmt = stmt.where(LeistungsverzeichnisPosition.leistungsverzeichnis_id == leistungsverzeichnis_id)
        elif kunde_id is not None:
            # Kundengefilterter Blick (Angebot/Vorgang/Zeiterfassung-Picker):
            # Positionen aus allgemeinen LVs (keine Kunden-Zuordnung) PLUS
            # aus LVs, die diesem Kunden konkret zugewiesen sind -- die
            # Kunden-Zuordnung sitzt am LV, nicht mehr an der Position
            # selbst (siehe app/models/leistungsverzeichnis.py).
            zugeordnete_lv_ids = select(LeistungsverzeichnisKunde.leistungsverzeichnis_id).where(
                LeistungsverzeichnisKunde.kunde_id == kunde_id
            )
            irgendwo_zugeordnete_lv_ids = select(LeistungsverzeichnisKunde.leistungsverzeichnis_id)
            stmt = stmt.where(
                LeistungsverzeichnisPosition.leistungsverzeichnis_id.in_(zugeordnete_lv_ids)
                | LeistungsverzeichnisPosition.leistungsverzeichnis_id.not_in(irgendwo_zugeordnete_lv_ids)
            )
        # Ohne Filter: alle eigenstaendigen Positionen des Mandanten,
        # allgemeine UND kundenspezifische zusammen (z.B. fuer den
        # Stundensatz-Katalog in LvPositionFormular).
    if nur_stundensaetze:
        stmt = stmt.where(LeistungsverzeichnisPosition.ist_stundensatz.is_(True))
    stmt = stmt.order_by(LeistungsverzeichnisPosition.bezeichnung)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/verwendungen", response_model=list[LeistungsverzeichnisVerwendungMitDetails])
async def list_lv_verwendungen(
    vorgang_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
) -> list[LeistungsverzeichnisVerwendungMitDetails]:
    stmt = (
        select(
            LeistungsverzeichnisVerwendung,
            LeistungsverzeichnisPosition.bezeichnung,
            LeistungsverzeichnisPosition.einheit,
            LeistungsverzeichnisPosition.einzelpreis,
        )
        .join(LeistungsverzeichnisPosition, LeistungsverzeichnisPosition.id == LeistungsverzeichnisVerwendung.lv_position_id)
        .where(LeistungsverzeichnisVerwendung.vorgang_id == vorgang_id)
        .order_by(LeistungsverzeichnisVerwendung.created_at.desc())
    )
    result = await session.execute(stmt)
    return [
        LeistungsverzeichnisVerwendungMitDetails(
            **LeistungsverzeichnisVerwendungRead.model_validate(verwendung).model_dump(),
            lv_bezeichnung=bezeichnung,
            lv_einheit=einheit,
            lv_einzelpreis=einzelpreis,
        )
        for verwendung, bezeichnung, einheit, einzelpreis in result.all()
    ]


@router.delete("/verwendungen/{verwendung_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lv_verwendung(
    verwendung_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    verwendung = await session.get(LeistungsverzeichnisVerwendung, verwendung_id)
    if verwendung is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verwendung nicht gefunden")
    vorgang = await session.get(Vorgang, verwendung.vorgang_id)
    if vorgang is not None and vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr bebucht werden",
        )
    await session.delete(verwendung)
    await session.flush()


@router.post(
    "",
    response_model=LeistungsverzeichnisPositionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def create_position(
    body: LeistungsverzeichnisPositionCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisPosition:
    if body.eltern_position_id is not None:
        eltern = await _require_position(session, body.eltern_position_id)
        if eltern.eltern_position_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unterpunkte können nicht verschachtelt werden"
            )
        leistungsverzeichnis_id = eltern.leistungsverzeichnis_id
    else:
        if body.leistungsverzeichnis_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="leistungsverzeichnis_id ist erforderlich"
            )
        lv = await _require_lv(session, body.leistungsverzeichnis_id)
        leistungsverzeichnis_id = lv.id

    await _pruefe_material_posten(session, body.material_posten)

    lohn_gemeinkosten_prozent = body.lohn_gemeinkosten_prozent
    gewinn_wagnis_prozent = body.gewinn_wagnis_prozent
    if lohn_gemeinkosten_prozent is None or gewinn_wagnis_prozent is None:
        mandant = await session.get(Mandant, auth.mandant_id)
        if lohn_gemeinkosten_prozent is None:
            lohn_gemeinkosten_prozent = mandant.standard_lohn_gemeinkosten_prozent
        if gewinn_wagnis_prozent is None:
            gewinn_wagnis_prozent = mandant.standard_gewinn_wagnis_prozent

    position = LeistungsverzeichnisPosition(
        mandant_id=auth.mandant_id,
        leistungsverzeichnis_id=leistungsverzeichnis_id,
        eltern_position_id=body.eltern_position_id,
        bezeichnung=body.bezeichnung,
        einheit=body.einheit,
        einzelpreis=body.einzelpreis,
        ist_stundensatz=body.ist_stundensatz,
        notiz=body.notiz,
        kalkulationsmodus=body.kalkulationsmodus,
        lohn_minuten=body.lohn_minuten,
        lohn_stundensatz=body.lohn_stundensatz,
        lohn_gemeinkosten_prozent=lohn_gemeinkosten_prozent,
        material_posten=_material_posten_zu_json(body.material_posten),
        material_aufschlag_prozent=body.material_aufschlag_prozent,
        gewinn_wagnis_prozent=gewinn_wagnis_prozent,
    )
    session.add(position)
    await session.flush()
    await _neu_berechnen(session, position)
    await session.refresh(position)
    return position


@router.patch(
    "/{lv_position_id}",
    response_model=LeistungsverzeichnisPositionRead,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom")),
        Depends(require_recht("kunden", "bearbeiten")),
    ],
)
async def update_position(
    lv_position_id: UUID,
    body: LeistungsverzeichnisPositionUpdate,
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisPosition:
    position = await _require_position(session, lv_position_id)
    changes = body.model_dump(exclude_unset=True)

    if "material_posten" in changes and changes["material_posten"] is not None:
        await _pruefe_material_posten(session, body.material_posten)
        changes["material_posten"] = _material_posten_zu_json(body.material_posten)

    for feld, wert in changes.items():
        setattr(position, feld, wert)
    await session.flush()
    await _neu_berechnen(session, position)

    await session.refresh(position)
    return position


@router.delete(
    "/{lv_position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_roles("mandant_admin", "custom", "loesch_operativ")),
        Depends(require_recht("kunden", "loeschen")),
    ],
)
async def delete_position(
    lv_position_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    position = await _require_position(session, lv_position_id)
    eltern_id = position.eltern_position_id
    geloescht = await papierkorb_service.soft_delete(
        session, entity_typ="leistungsverzeichnis_position", entity_id=lv_position_id, actor_user_id=auth.user_id
    )
    if geloescht is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden")
    if eltern_id is not None:
        eltern = await session.get(LeistungsverzeichnisPosition, eltern_id)
        if eltern is not None and eltern.geloescht_am is None:
            await _neu_berechnen(session, eltern)


@router.post(
    "/{lv_position_id}/verwendung",
    response_model=LeistungsverzeichnisVerwendungRead,
    status_code=status.HTTP_201_CREATED,
)
async def verwendung_erfassen(
    lv_position_id: UUID,
    body: LeistungsverzeichnisVerwendungCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LeistungsverzeichnisVerwendung:
    position = await _require_position(session, lv_position_id)
    vorgang = await session.get(Vorgang, body.vorgang_id)
    if vorgang is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vorgang nicht gefunden oder gehört nicht zum eigenen Mandanten",
        )
    zugeordnete_kunden = (
        await session.execute(
            select(LeistungsverzeichnisKunde.kunde_id).where(
                LeistungsverzeichnisKunde.leistungsverzeichnis_id == position.leistungsverzeichnis_id
            )
        )
    ).scalars().all()
    if zugeordnete_kunden and vorgang.kunde_id not in zugeordnete_kunden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Position ist keinem der Kunden dieses Vorgangs zugeordnet",
        )
    if vorgang.status in VORGANG_STATUS_GESCHLOSSEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vorgang ist abgeschlossen und kann nicht mehr bebucht werden",
        )

    verwendung = LeistungsverzeichnisVerwendung(
        mandant_id=auth.mandant_id,
        lv_position_id=lv_position_id,
        vorgang_id=body.vorgang_id,
        menge=body.menge,
        verwendet_von=auth.user_id,
    )
    session.add(verwendung)

    session.add(
        VorgangEvent(
            mandant_id=auth.mandant_id,
            vorgang_id=body.vorgang_id,
            event_type="leistung",
            author_user_id=auth.user_id,
            body=f"{body.menge:g} {position.einheit} {position.bezeichnung} verwendet",
            payload={"lv_position_id": str(lv_position_id), "menge": str(body.menge)},
        )
    )

    await session.flush()
    await session.refresh(verwendung)
    return verwendung
