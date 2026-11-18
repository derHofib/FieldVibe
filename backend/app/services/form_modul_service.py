"""Service-Funktionen fuer das Formular-Modul v2 (siehe app/models/
form_modul.py und app/api/routes/form_modul.py). Buendelt das Aufloesen
einer Schema-Definition, die Anwendung von form_logic_engine auf eine
form_submission sowie den Datenquellen-Autofill -- funktional das Pendant
zu app/services/formular_service.py fuer das alte Modell.
"""
from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, func, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.zeit import tagesbeginn_utc, tagesende_utc

from app.models.anlage import Anlage
from app.models.form_modul import (
    FormAuftragstypZuordnung,
    FormField,
    FormGroup,
    FormLogicRule,
    FormPresentationElement,
    FormSchema,
    FormSubmission,
    FormView,
    FormViewFieldLayout,
)
from app.models.kunde import Kunde
from app.models.standort import Standort
from app.models.user import User
from app.models.vorgang import Vorgang
from app.schemas.form_modul import (
    FormSchemaLeistungstyp,
    FormSchemaRead,
    FormSubmissionRead,
    FormSubmissionUebersichtEintrag,
    FormSubmissionUebersichtRead,
)
from app.services.form_logic_engine import RuleApplicationResult, apply_rules
from app.services.zuweisung_service import vorgang_scope_filter

if TYPE_CHECKING:
    from app.api.deps import AuthContext

LEISTUNGSTYP_LABEL = {
    "installation": "Installation",
    "pruefung": "Prüfung",
    "wartung": "Wartung",
    "stoerung": "Störung",
    "beratung": "Beratung",
    "planung": "Planung",
}


async def fields_fuer(session: AsyncSession, schema_id: UUID) -> list[FormField]:
    result = await session.execute(
        select(FormField).where(FormField.schema_id == schema_id).order_by(FormField.reihenfolge)
    )
    return list(result.scalars().all())


async def groups_fuer(session: AsyncSession, schema_id: UUID) -> list[FormGroup]:
    result = await session.execute(
        select(FormGroup).where(FormGroup.schema_id == schema_id).order_by(FormGroup.reihenfolge)
    )
    return list(result.scalars().all())


async def rules_fuer(session: AsyncSession, schema_id: UUID) -> list[FormLogicRule]:
    result = await session.execute(
        select(FormLogicRule).where(FormLogicRule.schema_id == schema_id).order_by(FormLogicRule.reihenfolge)
    )
    return list(result.scalars().all())


async def zuordnungen_fuer(session: AsyncSession, schema_id: UUID) -> list[FormAuftragstypZuordnung]:
    result = await session.execute(
        select(FormAuftragstypZuordnung).where(FormAuftragstypZuordnung.schema_id == schema_id)
    )
    return list(result.scalars().all())


def _rule_dicts(rules: list[FormLogicRule]) -> list[dict[str, Any]]:
    return [
        {
            "target_key": r.target_key,
            "effect": r.effect,
            "condition": r.condition,
            "value": r.value,
            "view_id": str(r.view_id) if r.view_id else None,
            "reihenfolge": r.reihenfolge,
        }
        for r in rules
    ]


async def compute_states(
    session: AsyncSession,
    *,
    schema_id: UUID,
    values: dict[str, Any],
    view_id: UUID | None,
) -> RuleApplicationResult:
    fields = await fields_fuer(session, schema_id)
    groups = await groups_fuer(session, schema_id)
    rules = await rules_fuer(session, schema_id)
    return apply_rules(
        fields=[{"key": f.key, "group_key": f.group_key} for f in fields],
        groups=[{"key": g.key} for g in groups],
        rules=_rule_dicts(rules),
        values=values,
        view_id=str(view_id) if view_id else None,
    )


async def capture_view_fuer(session: AsyncSession, schema_id: UUID) -> FormView | None:
    result = await session.execute(
        select(FormView).where(FormView.schema_id == schema_id, FormView.type == "capture").limit(1)
    )
    return result.scalars().first()


async def layouts_fuer(session: AsyncSession, view_id: UUID) -> list[FormViewFieldLayout]:
    result = await session.execute(
        select(FormViewFieldLayout).where(FormViewFieldLayout.view_id == view_id).order_by(FormViewFieldLayout.seite)
    )
    return list(result.scalars().all())


async def elements_fuer(session: AsyncSession, view_id: UUID) -> list[FormPresentationElement]:
    result = await session.execute(
        select(FormPresentationElement)
        .where(FormPresentationElement.view_id == view_id)
        .order_by(FormPresentationElement.reihenfolge)
    )
    return list(result.scalars().all())


def _adresse_einzeilig(adresse: dict | None) -> str | None:
    adresse = adresse or {}
    teile = []
    if adresse.get("strasse"):
        teile.append(str(adresse["strasse"]))
    ort = " ".join(str(adresse[k]) for k in ("plz", "ort") if adresse.get(k))
    if ort:
        teile.append(ort)
    return ", ".join(teile) or None


def auto_fill_values(
    fields: list[FormField],
    vorgang: Vorgang,
    kunde: Kunde | None,
    anlage: Anlage | None,
    standort: Standort | None,
    zugewiesener_name: str | None,
) -> dict[str, Any]:
    """Aequivalent zu formular_service.auto_fill_werte, aber Ergebnis ist
    keyed by FormField.key statt Formularfeld-UUID. Felder in einer
    Wiederholgruppe werden nie automatisch befuellt (es gibt beim Start noch
    keine Zeilen)."""
    quellen: dict[str, Any] = {
        "vorgang.vorgangsnummer": vorgang.vorgangsnummer,
        "vorgang.titel": vorgang.titel,
        "vorgang.beschreibung": vorgang.beschreibung,
        "vorgang.leistungstyp": LEISTUNGSTYP_LABEL.get(vorgang.leistungstyp, vorgang.leistungstyp),
        "vorgang.faelligkeit_am": (
            vorgang.faelligkeit_am.date().isoformat() if vorgang.faelligkeit_am else None
        ),
        "vorgang.adresse": _adresse_einzeilig(vorgang.adresse),
        "vorgang.zugewiesener_name": zugewiesener_name,
        # Automatischer Zeitstempel: einmalig beim Start der Ausfuellung
        # gesetzt (wie jede andere Datenquelle hier), nicht bei jedem
        # Autosave neu -- ein "erfasst am" soll den Beginn dokumentieren,
        # nicht sich waehrend des Ausfuellens weiterbewegen.
        "system.jetzt": date.today().isoformat(),
    }
    if kunde is not None:
        quellen["kunde.kundennummer"] = kunde.kundennummer
        quellen["kunde.name"] = kunde.name
        quellen["kunde.adresse"] = _adresse_einzeilig(kunde.adresse)
        erster_ansprechpartner = kunde.ansprechpartner[0] if kunde.ansprechpartner else None
        quellen["kunde.ansprechpartner"] = (
            erster_ansprechpartner.get("name") if erster_ansprechpartner else None
        )
    if anlage is not None:
        quellen["anlage.bezeichnung"] = anlage.bezeichnung
        quellen["anlage.adresse"] = _adresse_einzeilig(anlage.adresse)
        quellen["anlage.hersteller"] = anlage.hersteller
        quellen["anlage.modell"] = anlage.modell
        quellen["anlage.seriennummer"] = anlage.seriennummer
        quellen["anlage.anlagentyp"] = anlage.anlagentyp
    if standort is not None:
        quellen["standort.bezeichnung"] = standort.bezeichnung
        quellen["standort.adresse"] = _adresse_einzeilig(standort.adresse)

    values: dict[str, Any] = {}
    for field in fields:
        if field.datenquelle is None or field.group_key is not None:
            continue
        wert = quellen.get(field.datenquelle)
        if wert is not None:
            values[field.key] = wert
    return values


async def to_submission_read(session: AsyncSession, submission: FormSubmission) -> FormSubmissionRead:
    """Reichert eine form_submission um den Schema-Namen an, damit das
    Frontend (siehe FormularAbschnitt.tsx) diesen nicht separat je
    Ausfuellung nachladen muss."""
    schema = await session.get(FormSchema, submission.schema_id)
    return FormSubmissionRead(
        **{k: getattr(submission, k) for k in FormSubmissionRead.model_fields if k != "schema_name"},
        schema_name=schema.name if schema else "Formular",
    )


async def verfuegbare_schemas_fuer(session: AsyncSession, vorgang: Vorgang) -> list[tuple[FormSchema, bool]]:
    result = await session.execute(
        select(FormSchema, FormAuftragstypZuordnung.pflicht_vor_abschluss)
        .join(FormAuftragstypZuordnung, FormAuftragstypZuordnung.schema_id == FormSchema.id)
        .where(
            FormAuftragstypZuordnung.leistungstyp == vorgang.leistungstyp,
            FormSchema.status == "published",
        )
        .order_by(FormSchema.name)
    )
    return list(result.all())


async def offene_pflichtschemas(session: AsyncSession, vorgang: Vorgang) -> list[str]:
    """Namen der fuer den Leistungstyp dieses Vorgangs als 'pflicht vor
    Abschluss' markierten Formular-Schemas, zu denen noch keine
    abgeschlossene form_submission existiert -- Pendant zu
    formular_service.offene_pflichtformulare fuer das neue Modell."""
    pflicht_schemas = (
        await session.execute(
            select(FormSchema)
            .join(FormAuftragstypZuordnung, FormAuftragstypZuordnung.schema_id == FormSchema.id)
            .where(
                FormAuftragstypZuordnung.leistungstyp == vorgang.leistungstyp,
                FormAuftragstypZuordnung.pflicht_vor_abschluss.is_(True),
                FormSchema.status == "published",
            )
        )
    ).scalars().all()
    if not pflicht_schemas:
        return []

    erledigt_ids = set(
        (
            await session.execute(
                select(FormSubmission.schema_id).where(
                    FormSubmission.vorgang_id == vorgang.id,
                    FormSubmission.status == "abgeschlossen",
                    FormSubmission.schema_id.in_([s.id for s in pflicht_schemas]),
                )
            )
        ).scalars().all()
    )
    return [s.name for s in pflicht_schemas if s.id not in erledigt_ids]


async def schema_reads(session: AsyncSession, schemas: list[FormSchema]) -> list[FormSchemaRead]:
    """FormSchemaRead inkl. Aggregaten fuer mehrere Schemas mit je einer Abfrage pro Aggregat (kein N+1)."""
    if not schemas:
        return []
    ids = [s.id for s in schemas]
    felder_je_schema = dict(
        (
            await session.execute(
                select(FormField.schema_id, func.count()).where(FormField.schema_id.in_(ids)).group_by(FormField.schema_id)
            )
        ).all()
    )
    ausgefuellt_je_schema = dict(
        (
            await session.execute(
                select(FormSubmission.schema_id, func.count())
                .where(FormSubmission.schema_id.in_(ids))
                .group_by(FormSubmission.schema_id)
            )
        ).all()
    )
    leistungstypen_je_schema: dict[UUID, list[FormSchemaLeistungstyp]] = {}
    zuordnungen = await session.execute(
        select(FormAuftragstypZuordnung)
        .where(FormAuftragstypZuordnung.schema_id.in_(ids))
        .order_by(FormAuftragstypZuordnung.leistungstyp)
    )
    for z in zuordnungen.scalars().all():
        leistungstypen_je_schema.setdefault(z.schema_id, []).append(
            FormSchemaLeistungstyp(leistungstyp=z.leistungstyp, pflicht_vor_abschluss=z.pflicht_vor_abschluss)
        )
    user_ids = {s.erstellt_von for s in schemas if s.erstellt_von}
    namen: dict[UUID, str] = {}
    if user_ids:
        namen = dict((await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all())
    return [
        FormSchemaRead.model_validate(s).model_copy(
            update={
                "erstellt_von_name": namen.get(s.erstellt_von) if s.erstellt_von else None,
                "felder_anzahl": felder_je_schema.get(s.id, 0),
                "leistungstypen": leistungstypen_je_schema.get(s.id, []),
                "ausgefuellt_anzahl": ausgefuellt_je_schema.get(s.id, 0),
            }
        )
        for s in schemas
    ]


def _like_muster(suche: str) -> str:
    escaped = suche.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def submissions_uebersicht(
    session: AsyncSession,
    auth: "AuthContext",
    *,
    seite: int,
    seitengroesse: int,
    status: str | None,
    schema_id: UUID | None,
    von: date | None,
    bis: date | None,
    suche: str | None,
    techniker_id: UUID | None,
) -> FormSubmissionUebersichtRead:
    """Ausfuellungen ueber alle Vorgaenge. Die Sichtbarkeit (Kundenzuweisung/Scope) wird wie bei
    require_vorgang_zugriff ueber vorgang_scope_filter direkt im SQL erzwungen, damit Gesamtzahl und
    Seiten stimmen."""
    bedingungen = [Vorgang.geloescht_am.is_(None)]
    klausel = await vorgang_scope_filter(session, auth)
    if klausel is not None:
        bedingungen.append(klausel)
    if status is not None:
        bedingungen.append(FormSubmission.status == status)
    if schema_id is not None:
        bedingungen.append(FormSubmission.schema_id == schema_id)
    # Die Spalte ist timestamptz, das Mixin-Mapping aber naiv: ohne Coerce lehnt asyncpg die aware-Grenzen ab.
    erstellt = type_coerce(FormSubmission.created_at, DateTime(timezone=True))
    if von is not None:
        bedingungen.append(erstellt >= tagesbeginn_utc(von))
    if bis is not None:
        bedingungen.append(erstellt < tagesende_utc(bis))
    if techniker_id is not None:
        bedingungen.append(FormSubmission.ausgefuellt_von == techniker_id)
    if suche and suche.strip():
        muster = _like_muster(suche.strip())
        bedingungen.append(
            or_(
                Vorgang.vorgangsnummer.ilike(muster, escape="\\"),
                Kunde.name.ilike(muster, escape="\\"),
                FormSchema.name.ilike(muster, escape="\\"),
            )
        )

    basis = (
        select(FormSubmission)
        .join(Vorgang, Vorgang.id == FormSubmission.vorgang_id)
        .join(FormSchema, FormSchema.id == FormSubmission.schema_id)
        .outerjoin(Kunde, Kunde.id == Vorgang.kunde_id)
        .where(*bedingungen)
    )
    gesamt = (await session.execute(select(func.count()).select_from(basis.subquery()))).scalar_one()
    zeilen = await session.execute(
        basis.with_only_columns(
            FormSubmission, FormSchema.name, Vorgang.vorgangsnummer, Vorgang.titel, Kunde.name, User.name
        )
        .outerjoin(User, User.id == FormSubmission.ausgefuellt_von)
        .order_by(FormSubmission.created_at.desc(), FormSubmission.id)
        .offset((seite - 1) * seitengroesse)
        .limit(seitengroesse)
    )
    eintraege = [
        FormSubmissionUebersichtEintrag(
            id=sub.id,
            schema_id=sub.schema_id,
            schema_name=schema_name,
            schema_version=sub.schema_version,
            vorgang_id=sub.vorgang_id,
            vorgangsnummer=vorgangsnummer,
            vorgang_titel=vorgang_titel,
            kunde_name=kunde_name,
            status=sub.status,
            erstellt_via=sub.erstellt_via or "app",
            ausgefuellt_von_name=user_name,
            kundensichtbar=sub.kundensichtbar,
            created_at=sub.created_at,
            abgeschlossen_am=sub.abgeschlossen_am,
        )
        for sub, schema_name, vorgangsnummer, vorgang_titel, kunde_name, user_name in zeilen.all()
    ]
    return FormSubmissionUebersichtRead(eintraege=eintraege, gesamt=gesamt)


_PLATZHALTER_ADRESSE = {"strasse": "Musterstraße 1", "plz": "12345", "ort": "Musterstadt"}


def _platzhalter_wert(feld: FormField) -> Any:
    if feld.datenquelle is not None:
        return "(automatisch)"
    werte = (feld.optionen or {}).get("werte") or []
    typ = feld.feld_typ
    if typ == "zahl":
        return "42"
    if typ == "betrag":
        return "199.00"
    if typ == "datum":
        return date.today().isoformat()
    if typ == "dropdown":
        return werte[0] if werte else "Auswahl"
    if typ == "mehrfachauswahl":
        return list(werte[:2]) or ["Auswahl"]
    if typ == "ja_nein":
        return True
    if typ == "bewertung":
        return 4
    if typ == "email":
        return "name@beispiel.de"
    if typ == "telefon":
        return "+49 123 456789"
    if typ == "adresse":
        return dict(_PLATZHALTER_ADRESSE)
    if typ == "datei":
        return {"filename": "Beispiel.pdf"}
    if typ == "gps":
        return "52.5200, 13.4050"
    if typ == "qr_scan":
        return "QR-12345"
    if typ in ("foto", "unterschrift", "foto_plan"):
        return None
    return "Beispieltext"


def platzhalter_werte(fields: list[FormField], groups: list[FormGroup]) -> dict[str, Any]:
    """Beispielwerte je Feldtyp fuer die Druckvorschau einer Vorlage ohne echte Ausfuellung. Felder mit
    Datenquelle zeigen "(automatisch)", weil sie erst am Vorgang befuellt werden; Bilder bleiben leer.
    Wiederholbare Abschnitte bekommen zwei Beispielzeilen, damit die Listenform sichtbar wird."""
    werte: dict[str, Any] = {}
    for feld in fields:
        if feld.group_key is None:
            wert = _platzhalter_wert(feld)
            if wert is not None:
                werte[feld.key] = wert
    for gruppe in groups:
        zeile = {
            f.key: w for f in fields if f.group_key == gruppe.key and (w := _platzhalter_wert(f)) is not None
        }
        if zeile:
            werte[gruppe.key] = [dict(zeile), dict(zeile)] if gruppe.repeatable else [zeile]
    return werte
