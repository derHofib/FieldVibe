from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_roles
from app.core.zeit import in_lokal
from app.models.angebot import ANGEBOT_STATUS, Angebot, AngebotPosition
from app.models.anlage import Anlage
from app.models.auftrag import Auftrag
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.projekt import Projekt
from app.models.rechnung import RECHNUNG_STATUS, Rechnung
from app.models.standort import Standort
from app.models.tag import Tag
from app.models.telefonat import Telefonat
from app.models.user import User
from app.models.vor_ort_kontakt import VorOrtKontakt
from app.models.vorgang import Vorgang
from app.schemas.search import SearchHit, SearchKategorie, SearchResponse
from app.services import berechtigung_service
from app.services.angebot_service import summen as angebot_summen
from app.services.rechnung_service import brutto_sql
from app.services.telefonat_service import sichtbar_query as telefonat_sichtbar_query
from app.services.vorgang_completion_service import VORGANG_STATUS_GESCHLOSSEN
from app.services.zuweisung_service import erlaubte_kunde_ids, vorgang_scope_filter

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_roles("mandant_admin", "custom"))],
)

HITS_PER_KATEGORIE = 8
# Die Zaehler sind nur ein Hinweis ("100+"), kein exakter Wert -- so bleibt
# die Zaehl-Abfrage auch bei grossen Mandanten billig.
ANZAHL_DECKEL = 100
NOTIZ_KURZ = 80

# Aus den Status-Katalogen der Modelle abgeleitet: alles ausser den
# Endzustaenden gilt als offen (auch Entwuerfe).
_RECHNUNG_OFFEN = [s for s in RECHNUNG_STATUS if s not in ("bezahlt", "storniert")]
_ANGEBOT_OFFEN = [s for s in ANGEBOT_STATUS if s not in ("angenommen", "abgelehnt", "widerrufen")]


def _like_muster(q: str) -> str:
    """%, _ und \\ in der Eingabe sind Literale -- sonst findet "%" alles."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _kurz(text_: str | None) -> str | None:
    if not text_:
        return None
    text_ = " ".join(text_.split())
    return text_ if len(text_) <= NOTIZ_KURZ else text_[: NOTIZ_KURZ - 1] + "…"


def _exakt_zuerst(spalte, q: str):
    return case((func.lower(spalte) == q.lower(), 0), else_=1)


def _seit_grenze(seit: date | None) -> datetime | None:
    # asyncpg bindet kein date gegen timestamp; updated_at ist ohne Zeitzone.
    return datetime.combine(seit, time.min) if seit else None


async def _anzahl(session: AsyncSession, stmt, id_spalte) -> int:
    sub = stmt.with_only_columns(id_spalte).order_by(None).limit(ANZAHL_DECKEL).subquery()
    return (await session.execute(select(func.count()).select_from(sub))).scalar_one()


async def _darf_rechnungen_sehen(session: AsyncSession, auth: AuthContext) -> bool:
    """Rechnungstreffer sind nur fuer Accounts sichtbar, die auch
    /api/rechnungen aufrufen duerften. Dieser Router hat NUR require_roles,
    kein require_recht/require_module -- ohne dieses Gate wuerde jeder
    Mitarbeiter Rechnungsnummern, Kundennamen und Betraege sehen. Dieselben
    zwei Bedingungen wie dort: das Modul 'abrechnung' und das Recht
    abrechnung:sehen (aufgeloest von der Rechte-Engine, siehe
    require_recht in app/api/deps.py). Gilt ebenso fuer Angebote."""
    if auth.mandant_id is not None:
        mandant = await session.get(Mandant, auth.mandant_id)
        if mandant is not None and "abrechnung" in mandant.deaktivierte_module:
            return False
    return await berechtigung_service.hat_recht(session, auth, "abrechnung", "sehen")


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1),
    kategorie: SearchKategorie | None = Query(default=None),
    nur_offen: bool = Query(default=False),
    seit: date | None = Query(default=None),
    mir_zugewiesen: bool = Query(default=False),
    limit: int = Query(default=HITS_PER_KATEGORIE, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> SearchResponse:
    kunde_ids = await erlaubte_kunde_ids(session, auth)
    vorgang_klausel = await vorgang_scope_filter(session, auth)
    seit_ab = _seit_grenze(seit)

    # Welche Kategorien duerfen ueberhaupt durchsucht werden? Jede nur mit dem
    # Gate ihres Listen-Endpoints; was hier fehlt, taucht weder in treffer noch
    # in anzahl auf.
    erlaubt: set[str] = {"kunde", "anlage", "vorgang", "tag"}
    if await _darf_rechnungen_sehen(session, auth):
        erlaubt |= {"rechnung", "angebot"}
    if await berechtigung_service.hat_recht(session, auth, "projekte", "sehen"):
        erlaubt |= {"auftrag", "projekt"}
    erlaubt.add("telefonat")  # Rechte je Bezug in telefonat_sichtbar_query
    # Kontakte vor Ort folgen dem Kunden: gleiches Gate wie die Kundenliste.
    if await berechtigung_service.hat_recht(session, auth, "kunden", "sehen"):
        erlaubt.add("vor_ort_kontakt")
    # Projekt/Auftrag haben kein Zustaendigkeitsfeld, Telefonate nur "erfasst von".
    if mir_zugewiesen:
        erlaubt &= {"vorgang"}
    # Ein fuehrendes '#' durchsucht ausschliesslich Tags (Abschnitt 5.3).
    nur_tags = q.startswith("#")
    if nur_tags:
        erlaubt &= {"tag"}
    if kategorie is not None:
        erlaubt &= {kategorie}

    muster = _like_muster(q[1:].strip().lower() if nur_tags else q)
    treffer: list[SearchHit] = []
    anzahl: dict[str, int] = {}

    if "kunde" in erlaubt:
        standort_treffer = select(Standort.kunde_id).where(
            Standort.geloescht_am.is_(None),
            or_(
                Standort.bezeichnung.ilike(muster, escape="\\"),
                Standort.adresse["ort"].astext.ilike(muster, escape="\\"),
            ),
        )
        stmt = select(Kunde).where(
            or_(
                Kunde.name.ilike(muster, escape="\\"),
                Kunde.kundennummer.ilike(muster, escape="\\"),
                Kunde.id.in_(standort_treffer),
            ),
            Kunde.geloescht_am.is_(None),
        )
        if kunde_ids is not None:
            stmt = stmt.where(Kunde.id.in_(kunde_ids))
        anzahl["kunde"] = await _anzahl(session, stmt, Kunde.id)
        stmt = stmt.order_by(
            _exakt_zuerst(Kunde.kundennummer, q), func.similarity(Kunde.name, q).desc(), Kunde.id
        ).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="kunde", id=k.id, titel=k.name, subtitel=k.kundennummer, nummer=k.kundennummer
            )
            for k in (await session.execute(stmt)).scalars()
        ]

    if "anlage" in erlaubt:
        stmt = (
            select(Anlage, Standort.bezeichnung, Kunde.name)
            .select_from(Anlage)
            .outerjoin(Standort, Standort.id == Anlage.standort_id)
            .outerjoin(Kunde, Kunde.id == Anlage.kunde_id)
            .where(Anlage.bezeichnung.ilike(muster, escape="\\"), Anlage.geloescht_am.is_(None))
        )
        if kunde_ids is not None:
            stmt = stmt.where(Anlage.kunde_id.in_(kunde_ids))
        anzahl["anlage"] = await _anzahl(session, stmt, Anlage.id)
        stmt = stmt.order_by(func.similarity(Anlage.bezeichnung, q).desc(), Anlage.id).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="anlage",
                id=a.id,
                titel=a.bezeichnung,
                subtitel=a.anlagentyp,
                kunde_name=kunde_name,
                zusatz=standort or kunde_name,
            )
            for a, standort, kunde_name in (await session.execute(stmt)).all()
        ]

    if "vorgang" in erlaubt:
        # Volltextsuche (Titel/Beschreibung/Kommentare) ODER Trigram-Treffer
        # auf die Vorgangsnummer, damit "V-1002" genauso funktioniert wie ein
        # Stichwort aus dem Chat.
        stmt = (
            select(Vorgang, Kunde.name, User.name)
            .select_from(Vorgang)
            .outerjoin(Kunde, Kunde.id == Vorgang.kunde_id)
            .outerjoin(User, User.id == Vorgang.zugewiesener_user_id)
            .where(
                or_(
                    text("search_vector @@ websearch_to_tsquery('german', :q)"),
                    Vorgang.vorgangsnummer.ilike(muster, escape="\\"),
                ),
                Vorgang.geloescht_am.is_(None),
            )
            .params(q=q)
        )
        if vorgang_klausel is not None:
            stmt = stmt.where(vorgang_klausel)
        if nur_offen:
            stmt = stmt.where(Vorgang.status.not_in(sorted(VORGANG_STATUS_GESCHLOSSEN)))
        if mir_zugewiesen:
            stmt = stmt.where(Vorgang.zugewiesener_user_id == auth.user_id)
        if seit_ab:
            stmt = stmt.where(Vorgang.updated_at >= seit_ab)
        anzahl["vorgang"] = await _anzahl(session, stmt, Vorgang.id)
        stmt = stmt.order_by(
            _exakt_zuerst(Vorgang.vorgangsnummer, q), Vorgang.last_activity_at.desc(), Vorgang.id
        ).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="vorgang",
                id=v.id,
                titel=f"{v.vorgangsnummer}: {v.titel}",
                subtitel=v.status,
                nummer=v.vorgangsnummer,
                status=v.status,
                kunde_name=kunde_name,
                zusatz=user_name,
            )
            for v, kunde_name, user_name in (await session.execute(stmt)).all()
        ]

    if "rechnung" in erlaubt:
        # "R-00042" muss auffindbar sein, das war fuer die Buchhaltung die
        # spuerbarste Luecke; zusaetzlich ueber den Kundennamen.
        stmt = (
            select(Rechnung, Kunde.name, brutto_sql(Rechnung))
            .select_from(Rechnung)
            .join(Kunde, Kunde.id == Rechnung.kunde_id)
            .where(
                or_(
                    Rechnung.rechnungsnummer.ilike(muster, escape="\\"),
                    Kunde.name.ilike(muster, escape="\\"),
                ),
                Rechnung.geloescht_am.is_(None),
            )
        )
        if kunde_ids is not None:
            stmt = stmt.where(Rechnung.kunde_id.in_(kunde_ids))
        if nur_offen:
            stmt = stmt.where(Rechnung.status.in_(_RECHNUNG_OFFEN))
        if seit_ab:
            stmt = stmt.where(Rechnung.updated_at >= seit_ab)
        anzahl["rechnung"] = await _anzahl(session, stmt, Rechnung.id)
        stmt = stmt.order_by(
            _exakt_zuerst(Rechnung.rechnungsnummer, q),
            func.similarity(Rechnung.rechnungsnummer, q).desc(),
            Rechnung.id,
        ).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="rechnung",
                id=r.id,
                titel=r.rechnungsnummer,
                subtitel=f"{kunde_name or ''} · {r.status}",
                nummer=r.rechnungsnummer,
                status=r.status,
                kunde_name=kunde_name,
                betrag=brutto,
                datum=r.faellig_am or r.created_at.date(),
            )
            for r, kunde_name, brutto in (await session.execute(stmt)).all()
        ]

    if "angebot" in erlaubt:
        stmt = (
            select(Angebot, Kunde.name)
            .select_from(Angebot)
            .join(Kunde, Kunde.id == Angebot.kunde_id)
            .where(
                or_(
                    Angebot.angebotsnummer.ilike(muster, escape="\\"),
                    Kunde.name.ilike(muster, escape="\\"),
                ),
                Angebot.geloescht_am.is_(None),
            )
        )
        if kunde_ids is not None:
            stmt = stmt.where(Angebot.kunde_id.in_(kunde_ids))
        if nur_offen:
            heute = in_lokal(datetime.now(UTC)).date()
            stmt = stmt.where(
                Angebot.status.in_(_ANGEBOT_OFFEN),
                # Abgelaufen ist kein Status, sondern aus gueltig_bis abgeleitet.
                ~((Angebot.status == "versendet") & (Angebot.gueltig_bis < heute)),
            )
        if seit_ab:
            stmt = stmt.where(Angebot.updated_at >= seit_ab)
        anzahl["angebot"] = await _anzahl(session, stmt, Angebot.id)
        stmt = stmt.order_by(
            _exakt_zuerst(Angebot.angebotsnummer, q),
            func.similarity(Angebot.angebotsnummer, q).desc(),
            Angebot.id,
        ).limit(limit).offset(offset)
        angebote = (await session.execute(stmt)).all()
        # Der Bruttobetrag steht nicht am Angebot, sondern ergibt sich aus den
        # Positionen -- eine Abfrage fuer die ganze Seite statt je Treffer.
        positionen: dict = {}
        if angebote:
            pos_result = await session.execute(
                select(AngebotPosition).where(AngebotPosition.angebot_id.in_([a.id for a, _ in angebote]))
            )
            for p in pos_result.scalars():
                positionen.setdefault(p.angebot_id, []).append(p)
        treffer += [
            SearchHit(
                kategorie="angebot",
                id=a.id,
                titel=a.angebotsnummer,
                subtitel=f"{kunde_name or ''} · {a.status}",
                nummer=a.angebotsnummer,
                status=a.status,
                kunde_name=kunde_name,
                betrag=angebot_summen(positionen.get(a.id, []), a.mwst_satz)[1],
                datum=a.gueltig_bis,
            )
            for a, kunde_name in angebote
        ]

    if "auftrag" in erlaubt:
        stmt = (
            select(Auftrag, Kunde.name)
            .select_from(Auftrag)
            .outerjoin(Kunde, Kunde.id == Auftrag.kunde_id)
            .where(Auftrag.titel.ilike(muster, escape="\\"), Auftrag.geloescht_am.is_(None))
        )
        if kunde_ids is not None:
            # Auftraege ohne Kunde bleiben fuer Eingeschraenkte sichtbar, wie in der Liste.
            stmt = stmt.where(or_(Auftrag.kunde_id.is_(None), Auftrag.kunde_id.in_(kunde_ids)))
        if nur_offen:
            stmt = stmt.where(Auftrag.status.not_in(["abgeschlossen", "storniert"]))
        if seit_ab:
            stmt = stmt.where(Auftrag.updated_at >= seit_ab)
        anzahl["auftrag"] = await _anzahl(session, stmt, Auftrag.id)
        stmt = stmt.order_by(func.similarity(Auftrag.titel, q).desc(), Auftrag.id).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="auftrag",
                id=a.id,
                titel=a.titel,
                subtitel=a.status,
                status=a.status,
                kunde_name=kunde_name,
            )
            for a, kunde_name in (await session.execute(stmt)).all()
        ]

    if "projekt" in erlaubt:
        stmt = select(Projekt).where(Projekt.name.ilike(muster, escape="\\"), Projekt.geloescht_am.is_(None))
        if nur_offen:
            stmt = stmt.where(Projekt.archiviert.is_(False))
        if seit_ab:
            stmt = stmt.where(Projekt.updated_at >= seit_ab)
        anzahl["projekt"] = await _anzahl(session, stmt, Projekt.id)
        stmt = stmt.order_by(func.similarity(Projekt.name, q).desc(), Projekt.id).limit(limit).offset(offset)
        treffer += [
            SearchHit(kategorie="projekt", id=p.id, titel=p.name)
            for p in (await session.execute(stmt)).scalars()
        ]

    if "telefonat" in erlaubt:
        stmt = (await telefonat_sichtbar_query(session, auth)).add_columns(Kunde.name).where(
            or_(
                Telefonat.partner_name.ilike(muster, escape="\\"),
                Telefonat.partner_nummer.ilike(muster, escape="\\"),
                Telefonat.notiz.ilike(muster, escape="\\"),
            )
        )
        if seit_ab:
            stmt = stmt.where(Telefonat.updated_at >= seit_ab)
        anzahl["telefonat"] = await _anzahl(session, stmt, Telefonat.id)
        stmt = stmt.order_by(Telefonat.beginn.desc(), Telefonat.id).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="telefonat",
                id=t.id,
                titel=t.partner_name,
                subtitel=f"{t.richtung} · {t.ergebnis}",
                kunde_name=kunde_name,
                datum=in_lokal(t.beginn).date(),
                zusatz=_kurz(t.notiz),
            )
            for t, kunde_name in (await session.execute(stmt)).all()
        ]

    if "vor_ort_kontakt" in erlaubt:
        stmt = (
            select(VorOrtKontakt, Kunde.name)
            .select_from(VorOrtKontakt)
            .join(Kunde, Kunde.id == VorOrtKontakt.kunde_id)
            .where(
                or_(
                    VorOrtKontakt.name.ilike(muster, escape="\\"),
                    VorOrtKontakt.telefon.ilike(muster, escape="\\"),
                    VorOrtKontakt.telefon2.ilike(muster, escape="\\"),
                    VorOrtKontakt.einheit.ilike(muster, escape="\\"),
                ),
                VorOrtKontakt.geloescht_am.is_(None),
                Kunde.geloescht_am.is_(None),
            )
        )
        if kunde_ids is not None:
            stmt = stmt.where(VorOrtKontakt.kunde_id.in_(kunde_ids))
        if seit_ab:
            stmt = stmt.where(VorOrtKontakt.updated_at >= seit_ab)
        anzahl["vor_ort_kontakt"] = await _anzahl(session, stmt, VorOrtKontakt.id)
        stmt = stmt.order_by(
            func.similarity(func.coalesce(VorOrtKontakt.name, VorOrtKontakt.telefon, ""), q).desc(), VorOrtKontakt.id
        ).limit(limit).offset(offset)
        treffer += [
            SearchHit(
                kategorie="vor_ort_kontakt",
                id=k.id,
                titel=k.name or k.telefon or k.rolle,
                subtitel=" · ".join(t for t in (k.rolle, k.einheit) if t),
                kunde_name=kunde_name,
                kunde_id=k.kunde_id,
                zusatz=k.telefon if k.name else None,
            )
            for k, kunde_name in (await session.execute(stmt)).all()
        ]

    if "tag" in erlaubt:
        stmt = select(Tag).where(Tag.label.ilike(muster, escape="\\"), Tag.geloescht_am.is_(None))
        anzahl["tag"] = await _anzahl(session, stmt, Tag.id)
        label = q[1:].strip().lower() if nur_tags else q
        stmt = stmt.order_by(func.similarity(Tag.label, label).desc(), Tag.id).limit(limit).offset(offset)
        treffer += [
            SearchHit(kategorie="tag", id=t.id, titel=f"#{t.label}")
            for t in (await session.execute(stmt)).scalars()
        ]

    return SearchResponse(treffer=treffer, anzahl=anzahl)
