"""Seeds two example Mandanten with users, Kunden/Anlagen/Vertraege/Vorgaenge
in every Status, and the standard System-Tags.

Idempotent: safe to run multiple times, existing rows (matched by unique
email / slug / kundennummer / vorgangsnummer / label) are left untouched.
Run with:

    docker compose run --rm backend python -m app.seed
"""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.tag import Tag, TagAssignment
from app.models.user import User
from app.models.vertrag import Vertrag
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent

SUPER_ADMIN_EMAIL = os.environ.get("SEED_SUPER_ADMIN_EMAIL", "superadmin@fieldvibe.example.de")
SUPER_ADMIN_PASSWORD = os.environ.get("SEED_SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
DEFAULT_PASSWORD = os.environ.get("SEED_USER_PASSWORD", "Handwerk123!")

SYSTEM_TAGS = ["wiederkehrend", "nachbestellen", "ueberfaellig", "gewaehrleistung"]

MANDANTEN = [
    {
        "name": "Elektro Müller GmbH",
        "slug": "mueller",
        "branche": "elektro",
        "users": [
            ("admin@mueller.example.de", "mandant_admin", "Sabine Müller"),
            ("dispo@mueller.example.de", "disponent", "Jens Krause"),
            ("technik1@mueller.example.de", "techniker", "Ali Yildiz"),
            ("technik2@mueller.example.de", "techniker", "Petra Wagner"),
        ],
        "kunden": [
            {
                "kundennummer": "K-1001",
                "name": "Hausverwaltung Rheinblick GmbH",
                "typ": "hausverwaltung",
                "anlagen": [
                    {
                        "bezeichnung": "Hauptverteilung Wohnanlage Rheinblick",
                        "anlagentyp": "niederspannung",
                        "qr_code": "QR-MUELLER-001",
                    },
                    {
                        "bezeichnung": "PV-Anlage Dach Block C",
                        "anlagentyp": "pv",
                        "qr_code": "QR-MUELLER-002",
                    },
                ],
                "vertraege": [
                    {
                        "bezeichnung": "Wartungsvertrag Rheinblick",
                        "abrechnungsart": "wartungsvertrag",
                        "anlage_bezeichnung": "Hauptverteilung Wohnanlage Rheinblick",
                        "konditionen": {"stundensatz": 89.0, "anfahrtspauschale": 25.0},
                    },
                ],
            },
            {
                "kundennummer": "K-1002",
                "name": "Café Sonnenschein",
                "typ": "gewerbe",
                "anlagen": [
                    {"bezeichnung": "Hauptverteilung Café Sonnenschein", "anlagentyp": "niederspannung"},
                ],
                "vertraege": [],
            },
            {
                "kundennummer": "K-1003",
                "name": "Familie Schneider",
                "typ": "privat",
                "anlagen": [
                    {"bezeichnung": "Zählerschrank EFH Schneider", "anlagentyp": "niederspannung"},
                ],
                "vertraege": [],
            },
        ],
        "vorgaenge": [
            {
                "vorgangsnummer": "V-1001",
                "kundennummer": "K-1003",
                "titel": "Sicherung fällt ständig aus",
                "beschreibung": "Kunde berichtet wiederholten Ausfall im Obergeschoss.",
                "leistungstyp": "stoerung",
                "abrechnungsart": "aufwand",
                "status": "neu",
                "prioritaet": 2,
            },
            {
                "vorgangsnummer": "V-1002",
                "kundennummer": "K-1001",
                "anlage_bezeichnung": "Hauptverteilung Wohnanlage Rheinblick",
                "vertrag_bezeichnung": "Wartungsvertrag Rheinblick",
                "titel": "Jährliche DGUV V3 Prüfung",
                "leistungstyp": "pruefung",
                "abrechnungsart": "wartungsvertrag",
                "status": "geplant",
                "tags": ["wiederkehrend"],
            },
            {
                "vorgangsnummer": "V-1003",
                "kundennummer": "K-1002",
                "titel": "Neue Beleuchtung Gastraum",
                "leistungstyp": "installation",
                "abrechnungsart": "festpreis",
                "status": "in_arbeit",
                "kommentar": "Material geliefert, Montage läuft.",
            },
            {
                "vorgangsnummer": "V-1004",
                "kundennummer": "K-1003",
                "titel": "Angebot Wallbox erstellt",
                "beschreibung": "Rückmeldung des Kunden zum Angebot steht noch aus.",
                "leistungstyp": "beratung",
                "abrechnungsart": "aufwand",
                "status": "wartet_kunde",
            },
            {
                "vorgangsnummer": "V-1005",
                "kundennummer": "K-1001",
                "anlage_bezeichnung": "PV-Anlage Dach Block C",
                "titel": "PV-Wartung Frühjahr",
                "leistungstyp": "wartung",
                "abrechnungsart": "wartungsvertrag",
                "status": "abgeschlossen",
            },
            {
                "vorgangsnummer": "V-1006",
                "kundennummer": "K-1002",
                "titel": "E-Check Gastraum",
                "leistungstyp": "pruefung",
                "abrechnungsart": "pauschale",
                "status": "abgerechnet",
            },
            {
                "vorgangsnummer": "V-1007",
                "kundennummer": "K-1003",
                "titel": "Planung PV-Anlage",
                "beschreibung": "Kunde hat den Auftrag zurückgezogen.",
                "leistungstyp": "planung",
                "abrechnungsart": "aufwand",
                "status": "storniert",
            },
        ],
    },
    {
        "name": "Blitz Elektrotechnik e.K.",
        "slug": "blitz",
        "branche": "elektro",
        "users": [
            ("admin@blitz.example.de", "mandant_admin", "Markus Blitz"),
            ("dispo@blitz.example.de", "disponent", "Nadine Roth"),
            ("technik1@blitz.example.de", "techniker", "Tom Schuster"),
            ("technik2@blitz.example.de", "techniker", "Lena Fischer"),
        ],
        "kunden": [
            {
                "kundennummer": "K-2001",
                "name": "Autohaus Nordlicht GmbH",
                "typ": "gewerbe",
                "anlagen": [
                    {
                        "bezeichnung": "Ladeinfrastruktur Kundenparkplatz",
                        "anlagentyp": "ladeinfrastruktur",
                        "qr_code": "QR-BLITZ-001",
                    },
                ],
                "vertraege": [
                    {
                        "bezeichnung": "Wartungsvertrag Ladeinfrastruktur",
                        "abrechnungsart": "wartungsvertrag",
                        "anlage_bezeichnung": "Ladeinfrastruktur Kundenparkplatz",
                        "konditionen": {"stundensatz": 95.0, "anfahrtspauschale": 30.0},
                    },
                ],
            },
            {
                "kundennummer": "K-2002",
                "name": "Stadtverwaltung Musterhausen",
                "typ": "oeffentlich",
                "anlagen": [
                    {"bezeichnung": "BMA Rathaus", "anlagentyp": "niederspannung"},
                ],
                "vertraege": [],
            },
            {
                "kundennummer": "K-2003",
                "name": "Herr und Frau Kaiser",
                "typ": "privat",
                "anlagen": [
                    {"bezeichnung": "Zählerschrank EFH Kaiser", "anlagentyp": "niederspannung"},
                ],
                "vertraege": [],
            },
        ],
        "vorgaenge": [
            {
                "vorgangsnummer": "V-2001",
                "kundennummer": "K-2003",
                "titel": "FI-Schalter löst sporadisch aus",
                "leistungstyp": "stoerung",
                "abrechnungsart": "aufwand",
                "status": "neu",
                "prioritaet": 2,
            },
            {
                "vorgangsnummer": "V-2002",
                "kundennummer": "K-2001",
                "anlage_bezeichnung": "Ladeinfrastruktur Kundenparkplatz",
                "vertrag_bezeichnung": "Wartungsvertrag Ladeinfrastruktur",
                "titel": "Halbjährliche Wartung Ladesäulen",
                "leistungstyp": "wartung",
                "abrechnungsart": "wartungsvertrag",
                "status": "geplant",
                "tags": ["wiederkehrend"],
            },
            {
                "vorgangsnummer": "V-2003",
                "kundennummer": "K-2002",
                "anlage_bezeichnung": "BMA Rathaus",
                "titel": "Erweiterung Brandmeldeanlage 2. OG",
                "leistungstyp": "installation",
                "abrechnungsart": "festpreis",
                "status": "in_arbeit",
                "kommentar": "Kabelwege verlegt, Melder folgen morgen.",
            },
            {
                "vorgangsnummer": "V-2004",
                "kundennummer": "K-2003",
                "titel": "Angebot Wallbox erstellt",
                "beschreibung": "Rückmeldung des Kunden steht noch aus.",
                "leistungstyp": "beratung",
                "abrechnungsart": "aufwand",
                "status": "wartet_kunde",
            },
            {
                "vorgangsnummer": "V-2005",
                "kundennummer": "K-2001",
                "anlage_bezeichnung": "Ladeinfrastruktur Kundenparkplatz",
                "titel": "Wartung Ladesäulen Herbst",
                "leistungstyp": "wartung",
                "abrechnungsart": "wartungsvertrag",
                "status": "abgeschlossen",
            },
            {
                "vorgangsnummer": "V-2006",
                "kundennummer": "K-2002",
                "titel": "E-Check Rathaus",
                "leistungstyp": "pruefung",
                "abrechnungsart": "pauschale",
                "status": "abgerechnet",
            },
            {
                "vorgangsnummer": "V-2007",
                "kundennummer": "K-2003",
                "titel": "Planung PV-Anlage",
                "beschreibung": "Kunde hat den Auftrag zurückgezogen.",
                "leistungstyp": "planung",
                "abrechnungsart": "aufwand",
                "status": "storniert",
            },
        ],
    },
]


async def _get_or_none(session, model, **filters):
    result = await session.execute(select(model).filter_by(**filters))
    return result.scalar_one_or_none()


async def _seed_users_and_mandant(session, mandant_data: dict) -> tuple[Mandant, User]:
    mandant = await _get_or_none(session, Mandant, slug=mandant_data["slug"])
    if mandant is None:
        mandant = Mandant(
            name=mandant_data["name"],
            slug=mandant_data["slug"],
            branche=mandant_data["branche"],
            status="aktiv",
        )
        session.add(mandant)
        await session.flush()
        print(f"[seed] Mandant angelegt: {mandant.name} ({mandant.slug})")
    else:
        print(f"[seed] Mandant bereits vorhanden: {mandant.name}")

    admin_user: User | None = None
    for email, role, name in mandant_data["users"]:
        user = await _get_or_none(session, User, email=email)
        if user is None:
            user = User(
                mandant_id=mandant.id,
                email=email,
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=role,
                name=name,
            )
            session.add(user)
            await session.flush()
            print(f"[seed]   User angelegt: {email} ({role})")
        else:
            print(f"[seed]   User bereits vorhanden: {email}")
        if role == "mandant_admin":
            admin_user = user

    return mandant, admin_user


async def _seed_system_tags(session, mandant: Mandant) -> None:
    for label in SYSTEM_TAGS:
        existing = await _get_or_none(session, Tag, mandant_id=mandant.id, label=label)
        if existing is None:
            session.add(Tag(mandant_id=mandant.id, label=label, system_tag=True))
    await session.flush()


async def _seed_kunden(session, mandant: Mandant, kunden_data: list[dict]) -> dict[str, Kunde]:
    kunden_by_nummer: dict[str, Kunde] = {}
    anlagen_by_bezeichnung: dict[str, Anlage] = {}

    for kunde_data in kunden_data:
        kunde = await _get_or_none(
            session, Kunde, mandant_id=mandant.id, kundennummer=kunde_data["kundennummer"]
        )
        if kunde is None:
            kunde = Kunde(
                mandant_id=mandant.id,
                kundennummer=kunde_data["kundennummer"],
                name=kunde_data["name"],
                typ=kunde_data["typ"],
                adresse={"strasse": "Musterstraße 1", "plz": "12345", "ort": "Musterstadt"},
                portal_slug=secrets.token_urlsafe(12),
            )
            session.add(kunde)
            await session.flush()
            print(f"[seed]   Kunde angelegt: {kunde.name} ({kunde.kundennummer})")
        kunden_by_nummer[kunde_data["kundennummer"]] = kunde

        for anlage_data in kunde_data["anlagen"]:
            existing_anlage = await _get_or_none(
                session, Anlage, mandant_id=mandant.id, bezeichnung=anlage_data["bezeichnung"]
            )
            if existing_anlage is None:
                existing_anlage = Anlage(
                    mandant_id=mandant.id,
                    kunde_id=kunde.id,
                    bezeichnung=anlage_data["bezeichnung"],
                    anlagentyp=anlage_data["anlagentyp"],
                    qr_code=anlage_data.get("qr_code"),
                    adresse={"strasse": "Musterstraße 1", "plz": "12345", "ort": "Musterstadt"},
                )
                session.add(existing_anlage)
                await session.flush()
                print(f"[seed]     Anlage angelegt: {existing_anlage.bezeichnung}")
            anlagen_by_bezeichnung[anlage_data["bezeichnung"]] = existing_anlage

        for vertrag_data in kunde_data["vertraege"]:
            existing_vertrag = await _get_or_none(
                session, Vertrag, mandant_id=mandant.id, bezeichnung=vertrag_data["bezeichnung"]
            )
            if existing_vertrag is None:
                anlage = anlagen_by_bezeichnung.get(vertrag_data.get("anlage_bezeichnung"))
                session.add(
                    Vertrag(
                        mandant_id=mandant.id,
                        kunde_id=kunde.id,
                        anlage_id=anlage.id if anlage else None,
                        bezeichnung=vertrag_data["bezeichnung"],
                        abrechnungsart=vertrag_data["abrechnungsart"],
                        konditionen=vertrag_data["konditionen"],
                    )
                )
                await session.flush()
                print(f"[seed]     Vertrag angelegt: {vertrag_data['bezeichnung']}")

    return kunden_by_nummer


async def _seed_vorgaenge(
    session, mandant: Mandant, vorgaenge_data: list[dict], admin_user: User | None
) -> None:
    result = await session.execute(select(Anlage).where(Anlage.mandant_id == mandant.id))
    anlagen_by_bezeichnung = {a.bezeichnung: a for a in result.scalars().all()}
    result = await session.execute(select(Vertrag).where(Vertrag.mandant_id == mandant.id))
    vertraege_by_bezeichnung = {v.bezeichnung: v for v in result.scalars().all()}
    result = await session.execute(select(Kunde).where(Kunde.mandant_id == mandant.id))
    kunden_by_nummer = {k.kundennummer: k for k in result.scalars().all()}
    result = await session.execute(select(Tag).where(Tag.mandant_id == mandant.id))
    tags_by_label = {t.label: t for t in result.scalars().all()}

    for vorgang_data in vorgaenge_data:
        existing = await _get_or_none(
            session, Vorgang, mandant_id=mandant.id, vorgangsnummer=vorgang_data["vorgangsnummer"]
        )
        if existing is not None:
            continue

        anlage = anlagen_by_bezeichnung.get(vorgang_data.get("anlage_bezeichnung"))
        vertrag = vertraege_by_bezeichnung.get(vorgang_data.get("vertrag_bezeichnung"))
        kunde = kunden_by_nummer[vorgang_data["kundennummer"]]
        status = vorgang_data["status"]

        vorgang = Vorgang(
            mandant_id=mandant.id,
            vorgangsnummer=vorgang_data["vorgangsnummer"],
            kunde_id=kunde.id,
            anlage_id=anlage.id if anlage else None,
            vertrag_id=vertrag.id if vertrag else None,
            titel=vorgang_data["titel"],
            beschreibung=vorgang_data.get("beschreibung"),
            leistungstyp=vorgang_data["leistungstyp"],
            abrechnungsart=vorgang_data["abrechnungsart"],
            status=status,
            prioritaet=vorgang_data.get("prioritaet", 3),
        )
        if status in ("abgeschlossen", "abgerechnet"):
            vorgang.abgeschlossen_am = datetime.now(timezone.utc) - timedelta(days=3)
        session.add(vorgang)
        await session.flush()

        session.add(
            VorgangEvent(
                mandant_id=mandant.id,
                vorgang_id=vorgang.id,
                event_type="system",
                author_user_id=admin_user.id if admin_user else None,
                is_system=True,
                body="Vorgang angelegt",
                payload={"status": "neu"},
            )
        )
        if vorgang_data.get("kommentar"):
            session.add(
                VorgangEvent(
                    mandant_id=mandant.id,
                    vorgang_id=vorgang.id,
                    event_type="kommentar",
                    author_user_id=admin_user.id if admin_user else None,
                    body=vorgang_data["kommentar"],
                )
            )
        if status != "neu":
            session.add(
                VorgangEvent(
                    mandant_id=mandant.id,
                    vorgang_id=vorgang.id,
                    event_type="status_change",
                    author_user_id=admin_user.id if admin_user else None,
                    payload={"von": "neu", "nach": status},
                )
            )

        for label in vorgang_data.get("tags", []):
            tag = tags_by_label.get(label)
            if tag is not None:
                session.add(
                    TagAssignment(
                        tag_id=tag.id,
                        entity_type="vorgang",
                        entity_id=vorgang.id,
                        mandant_id=mandant.id,
                    )
                )

        print(f"[seed]   Vorgang angelegt: {vorgang.vorgangsnummer} – {vorgang.titel} [{status}]")

    await session.flush()


async def seed() -> None:
    async with system_session() as session:
        super_admin = await _get_or_none(session, User, email=SUPER_ADMIN_EMAIL)
        if super_admin is None:
            session.add(
                User(
                    mandant_id=None,
                    email=SUPER_ADMIN_EMAIL,
                    password_hash=hash_password(SUPER_ADMIN_PASSWORD),
                    role="super_admin",
                    name="Plattform Administrator",
                )
            )
            print(f"[seed] super_admin angelegt: {SUPER_ADMIN_EMAIL}")
        else:
            print(f"[seed] super_admin bereits vorhanden: {SUPER_ADMIN_EMAIL}")
        await session.flush()

        for mandant_data in MANDANTEN:
            mandant, admin_user = await _seed_users_and_mandant(session, mandant_data)
            await _seed_system_tags(session, mandant)
            await _seed_kunden(session, mandant, mandant_data["kunden"])
            await _seed_vorgaenge(session, mandant, mandant_data["vorgaenge"], admin_user)

    print("\n[seed] Fertig.")
    print(f"[seed] super_admin Passwort: {SUPER_ADMIN_PASSWORD}")
    print(f"[seed] Standard-Passwort für Mandanten-User: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
