"""Kontakte vor Ort: Lesen mit Vererbung (Vorgang eigene + Auftrag + Projekt), Zuordnen, Einsatz vermerken,
Anonymisieren. Die Vererbung wird beim Lesen berechnet, es gibt keine Kopien -- eine korrigierte
Telefonnummer stimmt damit sofort an allen Zielen."""
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auftrag import Auftrag
from app.models.mandant import Mandant
from app.models.projekt import Projekt
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.models.vor_ort_kontakt import VorOrtKontakt, VorOrtKontaktZuordnung
from app.schemas.kontakt import AnsprechpartnerEintrag
from app.schemas.vor_ort_kontakt import (
    VorOrtHauptkontaktKurz,
    VorOrtKontaktCreate,
    VorOrtKontaktOut,
    VorOrtKontaktZugeordnet,
    VorOrtZuordnungCreate,
)
from app.services.audit_service import log_action
from app.services.mandanten_lauf import je_mandant
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN

Z = VorOrtKontaktZuordnung
K = VorOrtKontakt

# Naechste Ebene zuerst: bei doppelt zugeordneten Kontakten gewinnt die naechste, und der Hauptkontakt
# ist der der naechsten Ebene, die einen hat.
EBENEN = ("vorgang", "auftrag", "projekt")
AUFTRAG_STATUS_OFFEN = ("offen", "in_arbeit")

_Ziel = Vorgang | Auftrag | Projekt


def offene_zuordnung_klausel():
    """Zuordnung zeigt auf ein noch offenes Ziel: Vorgang nicht geschlossen, Auftrag offen/in_arbeit, Projekt
    nicht archiviert (vereinfachend, ohne Blick auf dessen Vorgaenge). Gemeinsam fuer die Anzeige und den
    Anonymisierungs-Job."""
    return or_(
        exists().where(
            Vorgang.id == Z.vorgang_id,
            Vorgang.geloescht_am.is_(None),
            Vorgang.status.not_in(sorted(VORGANG_STATUS_GESCHLOSSEN)),
        ),
        exists().where(
            Auftrag.id == Z.auftrag_id,
            Auftrag.geloescht_am.is_(None),
            Auftrag.status.in_(AUFTRAG_STATUS_OFFEN),
        ),
        exists().where(
            Projekt.id == Z.projekt_id,
            Projekt.geloescht_am.is_(None),
            Projekt.archiviert.is_(False),
        ),
    )


# --- Ausgabemodelle -----------------------------------------------------------------------------


async def kontakte_als_out(session: AsyncSession, kontakte: list[VorOrtKontakt]) -> list[VorOrtKontaktOut]:
    """Standortbezeichnung und Zuordnungs-Zaehler im Batch (kein N+1)."""
    if not kontakte:
        return []
    ids = [k.id for k in kontakte]
    standort_ids = {k.standort_id for k in kontakte if k.standort_id}
    bezeichnungen: dict[UUID, str] = {}
    if standort_ids:
        zeilen = await session.execute(select(Standort.id, Standort.bezeichnung).where(Standort.id.in_(standort_ids)))
        bezeichnungen = {z[0]: z[1] for z in zeilen}
    zeilen = await session.execute(
        select(Z.kontakt_id, func.count(Z.id), func.count(Z.id).filter(offene_zuordnung_klausel()))
        .where(Z.kontakt_id.in_(ids))
        .group_by(Z.kontakt_id)
    )
    zaehler = {z[0]: (z[1], z[2]) for z in zeilen}
    ergebnis = []
    for kontakt in kontakte:
        out = VorOrtKontaktOut.model_validate(kontakt)
        out.standort_bezeichnung = bezeichnungen.get(kontakt.standort_id) if kontakt.standort_id else None
        out.zuordnungen_anzahl, out.offene_zuordnungen_anzahl = zaehler.get(kontakt.id, (0, 0))
        ergebnis.append(out)
    return ergebnis


# --- Lesen mit Vererbung ------------------------------------------------------------------------


async def _projekt_ids_der_auftraege(session: AsyncSession, auftrag_ids: set[UUID]) -> dict[UUID, UUID | None]:
    if not auftrag_ids:
        return {}
    zeilen = await session.execute(select(Auftrag.id, Auftrag.projekt_id).where(Auftrag.id.in_(auftrag_ids)))
    return {z[0]: z[1] for z in zeilen}


def _kette_von_vorgang(
    vorgang: Vorgang, auftrag_projekt: dict[UUID, UUID | None], *, ohne_vererbung: bool = False
) -> dict[str, UUID | None]:
    if ohne_vererbung:
        return {"vorgang": vorgang.id, "auftrag": None, "projekt": None}
    auftrag_id = vorgang.auftrag_id
    projekt_id = vorgang.projekt_id or (auftrag_projekt.get(auftrag_id) if auftrag_id else None)
    return {"vorgang": vorgang.id, "auftrag": auftrag_id, "projekt": projekt_id}


async def _zuordnungen_je_ziel(
    session: AsyncSession, ketten: list[dict[str, UUID | None]], *, nur_haupt: bool = False
) -> dict[tuple[str, UUID], list[tuple[VorOrtKontaktZuordnung, VorOrtKontakt]]]:
    """Zuordnungen samt (nicht geloeschtem) Kontakt aller Ziele der Ketten, gruppiert nach (Ebene, Ziel-Id)."""
    ids = {ebene: {k[ebene] for k in ketten if k[ebene]} for ebene in EBENEN}
    bedingungen = [getattr(Z, f"{ebene}_id").in_(ids[ebene]) for ebene in EBENEN if ids[ebene]]
    if not bedingungen:
        return {}
    stmt = (
        select(Z, K)
        .join(K, K.id == Z.kontakt_id)
        .where(K.geloescht_am.is_(None), or_(*bedingungen))
        .order_by(Z.reihenfolge, Z.created_at, Z.id)
    )
    if nur_haupt:
        stmt = stmt.where(Z.ist_hauptkontakt.is_(True))
    je_ziel: dict[tuple[str, UUID], list] = defaultdict(list)
    for zuordnung, kontakt in (await session.execute(stmt)).all():
        for ebene in EBENEN:
            ziel_id = getattr(zuordnung, f"{ebene}_id")
            if ziel_id is not None:
                je_ziel[(ebene, ziel_id)].append((zuordnung, kontakt))
    return je_ziel


def _haupt_kontakt_id(kette: dict[str, UUID | None], je_ziel: dict) -> UUID | None:
    for ebene in EBENEN:
        if kette[ebene] is None:
            continue
        for zuordnung, kontakt in je_ziel.get((ebene, kette[ebene]), []):
            if zuordnung.ist_hauptkontakt:
                return kontakt.id
    return None


async def _herkunft_titel(session: AsyncSession, ketten: list[dict[str, UUID | None]]) -> dict[tuple[str, UUID], str]:
    titel: dict[tuple[str, UUID], str] = {}
    quellen = (
        ("vorgang", Vorgang, Vorgang.vorgangsnummer),
        ("auftrag", Auftrag, Auftrag.titel),
        ("projekt", Projekt, Projekt.name),
    )
    for ebene, modell, spalte in quellen:
        ids = {k[ebene] for k in ketten if k[ebene]}
        if ids:
            zeilen = await session.execute(select(modell.id, spalte).where(modell.id.in_(ids)))
            titel.update({(ebene, z[0]): z[1] for z in zeilen})
    return titel


async def kontakte_fuer_ziel(
    session: AsyncSession,
    *,
    vorgang: Vorgang | None = None,
    auftrag: Auftrag | None = None,
    projekt: Projekt | None = None,
    ohne_vererbung: bool = False,
) -> list[VorOrtKontaktZugeordnet]:
    """Effektive Kontakte eines Ziels. Vorgang: eigene + Auftrag + Projekt (Projekt des Vorgangs, sonst das
    des Auftrags); Auftrag: eigene + Projekt; Projekt: nur eigene. Derselbe Kontakt erscheint nur einmal
    (naechste Ebene gewinnt), nur der Hauptkontakt der naechsten Ebene mit Hauptkontakt behaelt das Kennzeichen.
    ohne_vererbung: nur eigene Kontakte des Vorgangs (fuer eigenstaendig gefuehrte Vorgaenge, deren Auftrag/Projekt
    der Nutzer nicht sehen darf)."""
    if vorgang is not None:
        auftrag_projekt = await _projekt_ids_der_auftraege(session, {vorgang.auftrag_id} if vorgang.auftrag_id else set())
        kette = _kette_von_vorgang(vorgang, auftrag_projekt, ohne_vererbung=ohne_vererbung)
    elif auftrag is not None:
        kette = {"vorgang": None, "auftrag": auftrag.id, "projekt": auftrag.projekt_id}
    elif projekt is not None:
        kette = {"vorgang": None, "auftrag": None, "projekt": projekt.id}
    else:
        raise ValueError("vorgang, auftrag oder projekt angeben")

    je_ziel = await _zuordnungen_je_ziel(session, [kette])
    titel = await _herkunft_titel(session, [kette])
    haupt_id = _haupt_kontakt_id(kette, je_ziel)

    gesehen: set[UUID] = set()
    # (Rang der Ebene, Zuordnung, Kontakt, Ebene, Ziel-Id)
    eintraege: list[tuple[int, VorOrtKontaktZuordnung, VorOrtKontakt, str, UUID]] = []
    for rang, ebene in enumerate(EBENEN):
        ziel_id = kette[ebene]
        if ziel_id is None:
            continue
        for zuordnung, kontakt in je_ziel.get((ebene, ziel_id), []):
            if kontakt.id not in gesehen:
                gesehen.add(kontakt.id)
                eintraege.append((rang, zuordnung, kontakt, ebene, ziel_id))
    # Stabil: je Ebene bleibt die Reihenfolge (reihenfolge, created_at) aus der Abfrage erhalten.
    eintraege.sort(key=lambda e: (e[2].id != haupt_id, e[0]))
    outs = {o.id: o for o in await kontakte_als_out(session, [e[2] for e in eintraege])}
    return [
        VorOrtKontaktZugeordnet(
            zuordnung_id=zuordnung.id,
            kontakt=outs[kontakt.id],
            ist_hauptkontakt=kontakt.id == haupt_id,
            herkunft=ebene,
            herkunft_id=ziel_id,
            herkunft_titel=titel.get((ebene, ziel_id), ""),
        )
        for _, zuordnung, kontakt, ebene, ziel_id in eintraege
    ]


async def hauptkontakte_fuer_vorgaenge(
    session: AsyncSession, vorgaenge: list[Vorgang], *, ohne_vererbung: frozenset[UUID] = frozenset()
) -> dict[UUID, VorOrtHauptkontaktKurz | None]:
    """Hauptkontakt je Vorgang fuer Feed/Listen im Batch: zwei bis drei Abfragen unabhaengig von der Anzahl."""
    if not vorgaenge:
        return {}
    auftrag_projekt = await _projekt_ids_der_auftraege(session, {v.auftrag_id for v in vorgaenge if v.auftrag_id})
    ketten = {v.id: _kette_von_vorgang(v, auftrag_projekt, ohne_vererbung=v.id in ohne_vererbung) for v in vorgaenge}
    je_ziel = await _zuordnungen_je_ziel(session, list(ketten.values()), nur_haupt=True)
    ergebnis: dict[UUID, VorOrtHauptkontaktKurz | None] = {}
    for vorgang_id, kette in ketten.items():
        ergebnis[vorgang_id] = None
        for ebene in EBENEN:
            treffer = je_ziel.get((ebene, kette[ebene]), []) if kette[ebene] else []
            if treffer:
                kontakt = treffer[0][1]
                ergebnis[vorgang_id] = VorOrtHauptkontaktKurz(
                    name=kontakt.name, rolle=kontakt.rolle, telefon=kontakt.telefon, einheit=kontakt.einheit
                )
                break
    return ergebnis


# --- Zuordnen -----------------------------------------------------------------------------------


def _ziel_kunde_id(ziel: _Ziel) -> UUID:
    if ziel.kunde_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Erst einen Auftraggeber setzen")
    return ziel.kunde_id


def _ziel_spalte(ziel: _Ziel) -> str:
    return {Vorgang: "vorgang_id", Auftrag: "auftrag_id", Projekt: "projekt_id"}[type(ziel)]


async def standort_pruefen(session: AsyncSession, standort_id: UUID, kunde_id: UUID) -> Standort:
    """Standort muss existieren (RLS: eigener Mandant), nicht geloescht sein und zum Kunden gehoeren -> sonst 422."""
    standort = await session.get(Standort, standort_id)
    if standort is None or standort.geloescht_am is not None or standort.kunde_id != kunde_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Standort gehört nicht zum Kunden"
        )
    return standort


async def kontakt_anlegen(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    user_id: UUID | None,
    kunde_id: UUID,
    body: VorOrtKontaktCreate,
    standort_vorgabe: UUID | None = None,
) -> VorOrtKontakt:
    standort_id = body.standort_id if "standort_id" in body.model_fields_set else standort_vorgabe
    if standort_id is not None:
        await standort_pruefen(session, standort_id, kunde_id)
    kontakt = VorOrtKontakt(
        mandant_id=mandant_id,
        kunde_id=kunde_id,
        standort_id=standort_id,
        name=body.name,
        rolle=body.rolle,
        einheit=body.einheit,
        telefon=body.telefon,
        telefon2=body.telefon2,
        email=body.email,
        erreichbarkeit=body.erreichbarkeit,
        hinweis=body.hinweis,
        quelle="buero",
        erstellt_von=user_id,
    )
    session.add(kontakt)
    await session.flush()
    await session.refresh(kontakt)
    return kontakt


async def _ziel_eintrag(session: AsyncSession, zuordnung: VorOrtKontaktZuordnung, kontakt: VorOrtKontakt) -> VorOrtKontaktZugeordnet:
    """Ausgabe einer Zuordnung auf ihrer eigenen Ebene (ohne Vererbung)."""
    for ebene in EBENEN:
        ziel_id = getattr(zuordnung, f"{ebene}_id")
        if ziel_id is not None:
            break
    kette = {e: (ziel_id if e == ebene else None) for e in EBENEN}
    titel = await _herkunft_titel(session, [kette])
    [out] = await kontakte_als_out(session, [kontakt])
    return VorOrtKontaktZugeordnet(
        zuordnung_id=zuordnung.id,
        kontakt=out,
        ist_hauptkontakt=zuordnung.ist_hauptkontakt,
        herkunft=ebene,
        herkunft_id=ziel_id,
        herkunft_titel=titel.get((ebene, ziel_id), ""),
    )


async def _hauptkontakt_freimachen(session: AsyncSession, spalte: str, ziel_id: UUID, ausser: UUID | None = None) -> None:
    stmt = select(Z).where(getattr(Z, spalte) == ziel_id, Z.ist_hauptkontakt.is_(True))
    if ausser is not None:
        stmt = stmt.where(Z.id != ausser)
    for alt in (await session.execute(stmt)).scalars():
        alt.ist_hauptkontakt = False
    # Vor dem Setzen des neuen Hauptkontakts schreiben: der partielle Unique-Index prueft je Statement.
    await session.flush()


async def zuordnen(
    session: AsyncSession, *, mandant_id: UUID, user_id: UUID | None, ziel: _Ziel, body: VorOrtZuordnungCreate
) -> VorOrtKontaktZugeordnet:
    kunde_id = _ziel_kunde_id(ziel)
    spalte = _ziel_spalte(ziel)
    if body.neu is not None:
        kontakt = await kontakt_anlegen(
            session,
            mandant_id=mandant_id,
            user_id=user_id,
            kunde_id=kunde_id,
            body=body.neu,
            standort_vorgabe=getattr(ziel, "standort_id", None),
        )
    else:
        kontakt = await session.get(K, body.kontakt_id)
        if kontakt is None or kontakt.geloescht_am is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kontakt nicht gefunden")
        if kontakt.kunde_id != kunde_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Kontakt gehört zu einem anderen Auftraggeber",
            )
        if kontakt.anonymisiert_am is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Anonymisierte Kontakte können nicht zugeordnet werden"
            )
        vorhanden = await session.execute(select(Z.id).where(Z.kontakt_id == kontakt.id, getattr(Z, spalte) == ziel.id))
        if vorhanden.first() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kontakt ist bereits zugeordnet")

    if body.ist_hauptkontakt:
        await _hauptkontakt_freimachen(session, spalte, ziel.id)
    naechste = (
        await session.execute(select(func.coalesce(func.max(Z.reihenfolge), -1) + 1).where(getattr(Z, spalte) == ziel.id))
    ).scalar_one()
    zuordnung = Z(
        mandant_id=mandant_id,
        kontakt_id=kontakt.id,
        ist_hauptkontakt=body.ist_hauptkontakt,
        reihenfolge=naechste,
        erstellt_von=user_id,
        **{spalte: ziel.id},
    )
    session.add(zuordnung)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kontakt ist bereits zugeordnet") from exc
    return await _ziel_eintrag(session, zuordnung, kontakt)


async def hauptkontakt_setzen(session: AsyncSession, zuordnung: VorOrtKontaktZuordnung, ist_haupt: bool) -> VorOrtKontaktZugeordnet:
    spalte = next(s for s in ("vorgang_id", "auftrag_id", "projekt_id") if getattr(zuordnung, s) is not None)
    if ist_haupt and not zuordnung.ist_hauptkontakt:
        await _hauptkontakt_freimachen(session, spalte, getattr(zuordnung, spalte), ausser=zuordnung.id)
    zuordnung.ist_hauptkontakt = ist_haupt
    await session.flush()
    kontakt = await session.get(K, zuordnung.kontakt_id)
    return await _ziel_eintrag(session, zuordnung, kontakt)


# --- Einsatz, Anonymisierung --------------------------------------------------------------------


async def einsatz_vermerken(session: AsyncSession, vorgang: Vorgang) -> int:
    """Setzt letzter_einsatz_am fuer alle dem Vorgang effektiv zugeordneten Kontakte (eigene, Auftrag,
    Projekt). Aufgerufen beim Abschluss des Vorgangs; Grundlage der Anonymisierungsfrist."""
    auftrag_projekt = await _projekt_ids_der_auftraege(session, {vorgang.auftrag_id} if vorgang.auftrag_id else set())
    kette = _kette_von_vorgang(vorgang, auftrag_projekt)
    je_ziel = await _zuordnungen_je_ziel(session, [kette])
    jetzt = datetime.now(timezone.utc)
    kontakte = {
        kontakt.id: kontakt
        for ebene in EBENEN
        if kette[ebene]
        for _, kontakt in je_ziel.get((ebene, kette[ebene]), [])
    }
    for kontakt in kontakte.values():
        kontakt.letzter_einsatz_am = jetzt
    return len(kontakte)


def anonymisieren(kontakt: VorOrtKontakt) -> None:
    """Leert alle personenbezogenen Felder; Rolle und Einheit bleiben fuer Verlauf und Statistik.
    Der Audit-Eintrag wird vom Aufrufer geschrieben (Akteur/Grund unterscheiden sich)."""
    kontakt.name = None
    kontakt.telefon = None
    kontakt.telefon2 = None
    kontakt.email = None
    kontakt.erreichbarkeit = None
    kontakt.hinweis = None
    kontakt.anonymisiert_am = datetime.now(timezone.utc)


async def anonymisieren_mit_protokoll(
    session: AsyncSession, kontakt: VorOrtKontakt, *, actor_user_id: UUID | None, grund: str
) -> None:
    anonymisieren(kontakt)
    await session.flush()
    # Kein Name/Telefon im Protokoll: das Audit-Log ist append-only und wuerde die Daten sonst behalten.
    await log_action(
        session,
        aktion="vor_ort_kontakt_anonymisiert",
        mandant_id=kontakt.mandant_id,
        actor_user_id=actor_user_id,
        entity_type="vor_ort_kontakt",
        entity_id=kontakt.id,
        payload={"grund": grund},
    )


async def anonymisiere_faellige(session: AsyncSession, mandant_id: UUID, monate: int) -> int:
    """Job-Logik fuer einen Mandanten (Session mit RLS): Kontakte mit letztem Einsatz (sonst Anlage) vor mehr
    als `monate` Monaten und ohne Zuordnung zu einem offenen Ziel werden anonymisiert."""
    grenze = func.now() - func.make_interval(0, monate)
    stmt = (
        select(K)
        .where(
            K.mandant_id == mandant_id,
            K.anonymisiert_am.is_(None),
            K.geloescht_am.is_(None),
            func.coalesce(K.letzter_einsatz_am, K.created_at) < grenze,
            ~exists().where(Z.kontakt_id == K.id, offene_zuordnung_klausel()),
        )
        .with_for_update(skip_locked=True)
    )
    kontakte = list((await session.execute(stmt)).scalars())
    for kontakt in kontakte:
        await anonymisieren_mit_protokoll(session, kontakt, actor_user_id=None, grund="frist")
    return len(kontakte)


async def _anonymisierung_fuer_mandant(session: AsyncSession, mandant_id: UUID) -> dict:
    mandant = await session.get(Mandant, mandant_id)
    if mandant is None:
        return {"kontakte_anonymisiert": 0}
    return {
        "kontakte_anonymisiert": await anonymisiere_faellige(
            session, mandant_id, mandant.vor_ort_kontakte_anonymisieren_monate
        )
    }


async def run_vor_ort_kontakte_anonymisierung(mandant_ids: list[UUID] | None = None) -> dict:
    return await je_mandant(mandant_ids, _anonymisierung_fuer_mandant)


async def kundenwechsel_pruefen(session: AsyncSession, spalte: str, ziel_id: UUID, neuer_kunde_id: UUID | None) -> None:
    """Ein Ziel darf nur Kontakte seines Auftraggebers haben: wechselt der Kunde, muessen fremde Kontakte
    vorher entfernt werden (409), statt dass die Zuordnung still inkonsistent wird."""
    fremd = await session.execute(
        select(Z.id)
        .join(K, K.id == Z.kontakt_id)
        .where(getattr(Z, spalte) == ziel_id, K.geloescht_am.is_(None))
        .where(K.kunde_id != neuer_kunde_id if neuer_kunde_id is not None else K.id.is_not(None))
        .limit(1)
    )
    if fremd.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Kontakte vor Ort des bisherigen Auftraggebers zuerst entfernen",
        )


def ansprechpartner_aufloesen(eintraege: list | None, ansprechpartner_id: UUID | None) -> AnsprechpartnerEintrag | None:
    """Sachbearbeitung aus der JSONB-Liste kunden.ansprechpartner; nicht (mehr) vorhanden -> None."""
    if ansprechpartner_id is None:
        return None
    for eintrag in eintraege or []:
        if isinstance(eintrag, dict) and str(eintrag.get("id")) == str(ansprechpartner_id):
            return AnsprechpartnerEintrag.model_validate(eintrag)
    return None
