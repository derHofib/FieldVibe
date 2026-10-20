"""Datenimport-Assistent (CSV/XLSX): Analyse, Probelauf, Import, Fehlerbericht, Rueckgaengig.

Bewusst nur fuer mandant_admin (loesch_operativ hat ueberall dieselben Rechte, siehe
require_roles): ein Import legt in einem Zug viele Stammdaten an und greift deshalb nicht auf
die feinen Rechte-Bereiche zurueck. Ablauf und Grenzen: docs/konzepte/DATENIMPORT.md."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.config import get_settings
from app.models.import_lauf import ImportLauf
from app.models.mandant import Mandant
from app.schemas.datenimport import (
    ImportAnalyse,
    ImportDublettenArt,
    ImportEntitaet,
    ImportErgebnis,
    ImportFeld,
    ImportKonfiguration,
    ImportLaufRead,
    ImportSpalte,
    ImportVorschlag,
    ImportZeile,
    ImportZusammenfassung,
)
from app.services import csv_service
from app.services.datenimport import lauf as lauf_service
from app.services.datenimport import rueckgaengig as rueckgaengig_service
from app.services.datenimport.basis import Konfiguration, ZeilenErgebnis
from app.services.datenimport.felder import ENTITAETEN, schlage_zuordnung_vor
from app.services.datenimport.lauf import ImportFehler

router = APIRouter(
    prefix="/api/import",
    tags=["datenimport"],
    dependencies=[Depends(require_roles("mandant_admin"))],
)

_ARTEN_ERLAUBT = {"fehler", "dublette", "warnung"}


def _http(exc: ImportFehler) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.meldung)


async def _modul_pruefen(session: AsyncSession, auth: AuthContext, entitaet: str) -> None:
    definition = lauf_service.definition_von(entitaet)
    mandant = await session.get(Mandant, auth.mandant_id)
    if mandant is not None and not lauf_service.modul_aktiv(mandant, definition):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Diese Funktion ist für Ihren Account nicht freigeschaltet"
        )


async def _lauf(session: AsyncSession, lauf_id: UUID) -> ImportLauf:
    # RLS begrenzt auf den eigenen Mandanten: fremde Laeufe sind schlicht "nicht gefunden".
    lauf = await session.get(ImportLauf, lauf_id)
    if lauf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importlauf nicht gefunden")
    return lauf


def _konfig(body: ImportKonfiguration) -> Konfiguration:
    return Konfiguration(
        mapping=dict(body.mapping),
        modus=body.modus,
        chargengroesse=body.chargengroesse,
        dubletten_aktionen=dict(body.dubletten_aktionen),
    )


def _zeile(e: ZeilenErgebnis) -> ImportZeile:
    return ImportZeile(
        zeile=e.nr, status=e.status, aktion=e.aktion, meldungen=e.meldungen, vorschau=e.vorschau,
        dublette_art=e.dublette_art, dublette_von=e.dublette_von,
    )


def _ergebnis(lauf: ImportLauf, ergebnisse: list[ZeilenErgebnis], zusammenfassung: dict, abbruch: str | None = None) -> ImportErgebnis:
    auswahl, gekuerzt = lauf_service.antwort_zeilen(ergebnisse)
    return ImportErgebnis(
        import_lauf_id=lauf.id,
        status=lauf.status,
        zusammenfassung=ImportZusammenfassung(**zusammenfassung),
        zeilen=[_zeile(e) for e in auswahl],
        zeilen_gekuerzt=gekuerzt,
        abbruch=abbruch,
        fehlerbericht_verfuegbar=bool(lauf.fehlerbericht_key) or (zusammenfassung["fehler"] > 0 and lauf.object_key is not None),
    )


def _lauf_read(lauf: ImportLauf) -> ImportLaufRead:
    daten = ImportLaufRead.model_validate(lauf)
    daten.kann_rueckgaengig = lauf.status == "abgeschlossen" and lauf.zeilen_neu > 0
    daten.fehlerbericht_verfuegbar = bool(lauf.fehlerbericht_key)
    daten.quelle_verfuegbar = lauf.object_key is not None
    return daten


@router.get("", response_model=list[ImportLaufRead])
async def list_import_laeufe(
    limit: int = Query(default=50, ge=1, le=200), session: AsyncSession = Depends(get_db)
) -> list[ImportLaufRead]:
    laeufe = (await session.execute(select(ImportLauf).order_by(ImportLauf.created_at.desc()).limit(limit))).scalars().all()
    return [_lauf_read(lauf) for lauf in laeufe]


@router.get("/vorlagen/{dateiname}")
async def import_vorlage(dateiname: str) -> Response:
    schluessel = dateiname.removesuffix(".csv")
    definition = ENTITAETEN.get(schluessel)
    if definition is None or not dateiname.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vorlage nicht gefunden")
    return Response(
        content=lauf_service.vorlage_bytes(definition),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-vorlage-{definition.key}.csv"'},
    )


@router.post("/analyse", response_model=ImportAnalyse, status_code=status.HTTP_201_CREATED)
async def analysiere_import(
    datei: UploadFile = File(...),
    entitaet: ImportEntitaet = Form(...),
    blatt: str | None = Form(default=None),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ImportAnalyse:
    await _modul_pruefen(session, auth, entitaet)
    grenze = get_settings().import_max_bytes
    daten = await datei.read(grenze + 1)
    if len(daten) > grenze:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Die Datei ist größer als {grenze // (1024 * 1024)} MB.",
        )
    try:
        lauf, tabelle = await lauf_service.analysiere(
            session, mandant_id=auth.mandant_id, user_id=auth.user_id, entitaet=entitaet,
            dateiname=datei.filename or "", daten=daten, blatt=blatt or None,
        )
    except ImportFehler as exc:
        raise _http(exc) from None
    definition = lauf_service.definition_von(entitaet)
    return ImportAnalyse(
        import_lauf_id=lauf.id,
        entitaet=entitaet,
        dateiname=lauf.dateiname,
        format=lauf.format,
        trennzeichen=lauf.trennzeichen,
        kodierung=lauf.kodierung,
        blatt=lauf.blatt,
        blaetter=tabelle.blaetter,
        zeilen_gesamt=lauf.zeilen_gesamt,
        spalten=[ImportSpalte(**s) for s in lauf_service.spalten_info(tabelle)],
        felder=[
            ImportFeld(key=f.key, label=f.label, pflicht=f.pflicht, gruppe=f.gruppe, hinweis=f.hinweis)
            for f in definition.felder
        ],
        vorschlag=[
            ImportVorschlag(feld=v.feld, spalte=v.spalte, sicherheit=v.sicherheit)
            for v in schlage_zuordnung_vor(definition, tabelle.kopf)
        ],
        dubletten_arten=[
            ImportDublettenArt(key=a.key, label=a.label, aktionen=list(a.aktionen), standard=a.standard)
            for a in definition.dubletten_arten
        ],
        pflicht_hinweis=definition.pflicht_hinweis,
    )


@router.get("/{lauf_id}", response_model=ImportLaufRead)
async def get_import_lauf(lauf_id: UUID, session: AsyncSession = Depends(get_db)) -> ImportLaufRead:
    return _lauf_read(await _lauf(session, lauf_id))


@router.post("/{lauf_id}/probelauf", response_model=ImportErgebnis)
async def import_probelauf(
    lauf_id: UUID,
    body: ImportKonfiguration,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ImportErgebnis:
    lauf = await _lauf(session, lauf_id)
    await _modul_pruefen(session, auth, lauf.entitaet)
    try:
        ergebnisse, zusammenfassung = await lauf_service.probelauf(session, lauf, _konfig(body), auth.user_id)
    except ImportFehler as exc:
        raise _http(exc) from None
    return _ergebnis(lauf, ergebnisse, zusammenfassung)


@router.post("/{lauf_id}/ausfuehren", response_model=ImportErgebnis)
async def import_ausfuehren(
    lauf_id: UUID,
    body: ImportKonfiguration,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ImportErgebnis:
    # Zeilensperre: ein zweiter paralleler Aufruf wartet und sieht danach den neuen Status (409).
    lauf = (
        await session.execute(select(ImportLauf).where(ImportLauf.id == lauf_id).with_for_update())
    ).scalar_one_or_none()
    if lauf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importlauf nicht gefunden")
    await _modul_pruefen(session, auth, lauf.entitaet)
    try:
        ergebnisse, zusammenfassung, _ = await lauf_service.ausfuehren(session, lauf, _konfig(body), auth.user_id)
    except ImportFehler as exc:
        raise _http(exc) from None
    abbruch = (lauf.ergebnis or {}).get("abbruch")
    return _ergebnis(lauf, ergebnisse, zusammenfassung, abbruch)


@router.get("/{lauf_id}/fehlerbericht.csv")
async def import_fehlerbericht(
    lauf_id: UUID,
    arten: str = Query(default="fehler", description="Komma-getrennt: fehler, dublette, warnung"),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    gewaehlt = tuple(a for a in dict.fromkeys(t.strip() for t in arten.split(",")) if a)
    if not gewaehlt or not set(gewaehlt) <= _ARTEN_ERLAUBT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unbekannte Berichtsart")
    lauf = await _lauf(session, lauf_id)
    try:
        inhalt = await lauf_service.fehlerbericht_fuer(session, lauf, auth.user_id, gewaehlt)
    except ImportFehler as exc:
        raise _http(exc) from None
    return Response(
        content=inhalt,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-fehlerbericht-{str(lauf.id)[:8]}.csv"'},
    )


@router.post("/{lauf_id}/rueckgaengig", response_model=ImportLaufRead)
async def import_rueckgaengig(
    lauf_id: UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ImportLaufRead:
    lauf = (
        await session.execute(select(ImportLauf).where(ImportLauf.id == lauf_id).with_for_update())
    ).scalar_one_or_none()
    if lauf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Importlauf nicht gefunden")
    try:
        await rueckgaengig_service.rueckgaengig(session, lauf, auth.user_id)
    except ImportFehler as exc:
        raise _http(exc) from None
    return _lauf_read(lauf)


@router.delete("/{lauf_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwerfe_import_lauf(lauf_id: UUID, session: AsyncSession = Depends(get_db)) -> None:
    lauf = await _lauf(session, lauf_id)
    try:
        await lauf_service.verwerfen(session, lauf)
    except ImportFehler as exc:
        raise _http(exc) from None
