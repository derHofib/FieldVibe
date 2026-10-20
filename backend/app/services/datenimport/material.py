"""Material-Import: Artikelstamm mit optionalem Mindest- und Anfangsbestand.

Der Anfangsbestand wird wie in POST /api/material gebucht (Bestand im Zentrallager plus
Bewegung "eingang"). Einkaufspreise kennt das Materialmodell nicht -- eine EK-Spalte bleibt
unzugeordnet."""
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.models.anlage import Anlage
from app.models.material import Material, MaterialBestand, MaterialBewegung
from app.schemas.material import MaterialCreate
from app.services.datenimport import werte
from app.services.datenimport.basis import (
    Konfiguration,
    Kontext,
    ZeilenErgebnis,
    pydantic_meldung,
    vorschau_von,
    zeilen_iter,
)
from app.services.datenimport.parser import Tabelle

_CENT = Decimal("0.01")
_MAX_BETRAG = Decimal("99999999.99")
_EINHEITEN = {
    werte.schluessel(s): "Stk" for s in ("stk", "stk.", "stück", "stueck", "st", "st.", "stuck", "pcs")
}
_BEZEICHNUNGEN = {"bezeichnung": "Bezeichnung", "einzelpreis": "Einzelpreis", "mindestbestand": "Mindestbestand", "menge": "Bestand"}


def _menge(text: str, name: str, warnungen: list[str], *, grenze: Decimal = _MAX_BETRAG) -> Decimal | None:
    try:
        betrag = werte.parse_dezimal(text)
    except ValueError:
        raise ValueError(f"{name} ist keine gültige Zahl") from None
    if betrag is None:
        return None
    if betrag < 0:
        raise ValueError(f"{name} darf nicht negativ sein")
    if betrag > grenze:
        raise ValueError(f"{name} ist zu groß")
    gerundet = betrag.quantize(_CENT, rounding=ROUND_HALF_UP)
    if gerundet != betrag:
        warnungen.append(f"{name} wurde auf zwei Nachkommastellen gerundet")
    return gerundet


class MaterialVerarbeiter:
    entitaet = "material"

    async def pruefen(self, kontext: Kontext, tabelle: Tabelle, konfig: Konfiguration) -> list[ZeilenErgebnis]:
        zeilen_db = (
            await kontext.session.execute(
                select(
                    Material.id, Material.artikelnummer, Material.bezeichnung, Material.einzelpreis, Material.geloescht_am
                ).where(Material.mandant_id == kontext.mandant_id)
            )
        ).all()
        nach_nummer: dict[str, dict] = {}
        nach_bezeichnung: dict[str, dict] = {}
        for mid, nummer, bezeichnung, preis, geloescht in zeilen_db:
            if geloescht is not None:
                continue
            bestand = {"id": mid, "artikelnummer": nummer, "bezeichnung": bezeichnung, "einzelpreis": preis}
            if nummer:
                nach_nummer.setdefault(nummer.strip().casefold(), bestand)
            elif bezeichnung:
                nach_bezeichnung.setdefault(werte.schluessel(bezeichnung), bestand)
        datei_nummer: dict[str, int] = {}
        datei_bezeichnung: dict[str, int] = {}
        ergebnisse = []
        for nr, zeile in zeilen_iter(tabelle, konfig):
            if nr % 200 == 0:
                kontext.frist_pruefen()
            erg = ZeilenErgebnis(nr=nr)
            ergebnisse.append(erg)
            warnungen: list[str] = []
            artikelnummer = zeile.text("artikelnummer")
            bezeichnung = zeile.text("bezeichnung")
            erg.vorschau = vorschau_von({"artikelnummer": artikelnummer, "bezeichnung": bezeichnung})
            if not bezeichnung:
                erg.fehler("Bezeichnung fehlt")
                continue
            if len(bezeichnung) > 300 or len(artikelnummer) > 100:
                erg.fehler("Bezeichnung oder Artikelnummer ist zu lang")
                continue
            einheit_text = zeile.text("einheit")
            einheit = _EINHEITEN.get(werte.schluessel(einheit_text), einheit_text[:20]) or "Stk"
            try:
                preis = _menge(zeile.roh("einzelpreis"), "Einzelpreis", warnungen)
                mindest = _menge(zeile.roh("mindestbestand"), "Mindestbestand", warnungen)
                bestand_menge = _menge(zeile.roh("bestand"), "Bestand", warnungen)
            except ValueError as exc:
                erg.fehler(str(exc))
                continue
            try:
                geprueft = MaterialCreate(
                    bezeichnung=bezeichnung, einheit=einheit, einzelpreis=preis,
                    mindestbestand=mindest or Decimal("0"), artikelnummer=artikelnummer or None,
                    menge=bestand_menge or Decimal("0"),
                )
            except ValidationError as exc:
                erg.fehler(pydantic_meldung(exc, _BEZEICHNUNGEN))
                continue

            art, bestand, in_datei = None, None, None
            if artikelnummer:
                schluessel = artikelnummer.strip().casefold()
                bestand = nach_nummer.get(schluessel)
                in_datei = datei_nummer.get(schluessel) if bestand is None else None
                art = "artikelnummer" if bestand or in_datei else None
            else:
                schluessel = werte.schluessel(bezeichnung)
                bestand = nach_bezeichnung.get(schluessel)
                in_datei = datei_bezeichnung.get(schluessel) if bestand is None else None
                art = "bezeichnung" if bestand or in_datei else None

            nutzlast = {
                "typ": "neu", "bezeichnung": bezeichnung, "einheit": geprueft.einheit,
                "artikelnummer": geprueft.artikelnummer, "einzelpreis": geprueft.einzelpreis,
                "mindestbestand": geprueft.mindestbestand, "menge": geprueft.menge,
            }
            if art is None:
                (datei_nummer if artikelnummer else datei_bezeichnung)[schluessel] = nr
                erg.nutzlast = nutzlast
                erg.meldungen += warnungen
                if warnungen:
                    erg.status = "warnung"
                continue

            erg.status, erg.dublette_art = "dublette", art
            erg.dublette_von = f"Zeile {in_datei}" if in_datei else f"{bestand['artikelnummer'] or '–'} {bestand['bezeichnung']}"
            grund = "Artikelnummer" if art == "artikelnummer" else "Bezeichnung"
            erg.meldungen.append(
                f"Dublette: gleiche {grund} wie {erg.dublette_von} ({'in derselben Datei' if in_datei else 'im Bestand'})"
            )
            aktion = konfig.aktion_fuer(art)
            if aktion == "anlegen":
                (datei_nummer if artikelnummer else datei_bezeichnung).setdefault(schluessel, nr)
                erg.nutzlast = nutzlast
                erg.meldungen.append("Wird trotzdem als neuer Artikel angelegt")
                erg.meldungen += warnungen
            elif aktion == "aktualisieren" and bestand is not None:
                if bestand["einzelpreis"] is None and geprueft.einzelpreis is not None:
                    erg.aktion = "aktualisieren"
                    erg.nutzlast = {"typ": "aktualisieren", "id": bestand["id"], "einzelpreis": geprueft.einzelpreis}
                    bestand["einzelpreis"] = geprueft.einzelpreis
                    erg.meldungen.append("Leere Felder werden ergänzt: einzelpreis")
                else:
                    erg.aktion = "ueberspringen"
                    erg.meldungen.append("Keine leeren Felder zu ergänzen – Zeile wird übersprungen")
            else:
                erg.aktion = "ueberspringen"
        return ergebnisse

    async def vorbereiten_schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> None:
        # Zentrallager einmal pro Lauf bestimmen (aeltestes Lager, wie POST /api/material).
        lager = (
            await kontext.session.execute(
                select(Anlage.id)
                .where(Anlage.mandant_id == kontext.mandant_id, Anlage.objekttyp == "lager")
                .order_by(Anlage.created_at.asc())
            )
        ).scalars().first()
        if lager is None and any(z.nutzlast and z.nutzlast["typ"] == "neu" for z in zeilen):
            raise RuntimeError("Kein Lagerort für diesen Mandanten vorhanden")
        kontext.extra["lager"] = lager

    async def schreiben(self, kontext: Kontext, zeilen: list[ZeilenErgebnis]) -> list[tuple[str, UUID, str, int]]:
        session = kontext.session
        eintraege: list[tuple[str, UUID, str, int]] = []
        lager = kontext.extra["lager"]
        updates = {z.nutzlast["id"]: z for z in zeilen if z.nutzlast and z.nutzlast["typ"] == "aktualisieren"}
        neue: list[tuple[ZeilenErgebnis, UUID]] = []
        for zeile in zeilen:
            n = zeile.nutzlast
            if not n or n["typ"] != "neu":
                continue
            material = Material(
                id=uuid4(), mandant_id=kontext.mandant_id, bezeichnung=n["bezeichnung"], einheit=n["einheit"],
                mindestbestand=n["mindestbestand"], einzelpreis=n["einzelpreis"], artikelnummer=n["artikelnummer"],
            )
            session.add(material)
            neue.append((zeile, material.id))
            eintraege.append(("material", material.id, "angelegt", zeile.nr))
        # Erst die Artikel flushen: Bestand und Bewegung verweisen per FK darauf.
        await session.flush()
        for zeile, material_id in neue:
            menge = zeile.nutzlast["menge"]
            session.add(MaterialBestand(mandant_id=kontext.mandant_id, material_id=material_id, lager_id=lager, menge=menge))
            if menge > 0:
                session.add(
                    MaterialBewegung(
                        mandant_id=kontext.mandant_id, material_id=material_id, typ="eingang",
                        nach_lager_id=lager, menge=menge, erstellt_von=kontext.user_id,
                    )
                )
        if updates:
            objekte = (await session.execute(select(Material).where(Material.id.in_(list(updates))))).scalars().all()
            for material in objekte:
                zeile = updates[material.id]
                if material.einzelpreis is None:
                    material.einzelpreis = zeile.nutzlast["einzelpreis"]
                eintraege.append(("material", material.id, "aktualisiert", zeile.nr))
        await session.flush()
        return eintraege

