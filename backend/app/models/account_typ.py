import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.rechte_registry import (
    BASIS_AKTIONEN,
    SCOPES,
    alle_aktionen,
    alle_bereich_keys,
    alle_bereiche,
    aktionen_fuer_bereich,
)
from app.db.base import Base, TimestampMixin

# Bereiche/Aktionen der Rechte-Matrix -- gemeinsam fuer alle Account-Typen
# eines Mandanten. super_admin und mandant_admin durchlaufen diese Matrix nie
# (siehe require_recht in app/api/deps.py), loesch_ansicht/loesch_operativ
# ebensowenig -- die bleiben aus Compliance-Gruenden bewusst ausserhalb der
# mandant_admin-Kontrolle (nur super_admin darf sie vergeben, siehe
# app/api/routes/users.py).
RECHTE_BEREICHE = alle_bereich_keys()
RECHTE_AKTIONEN = BASIS_AKTIONEN
# Zusatzaktionen, die nur fuer einzelne Bereiche existieren (z.B. projekte.
# zeitplan_*, abrechnung.freigeben) -- aus der Registry abgeleitet.
RECHTE_BEREICH_AKTIONEN: dict[str, tuple[str, ...]] = {
    b.key: tuple(a for a in b.aktionen if a not in BASIS_AKTIONEN)
    for b in alle_bereiche()
    if any(a not in BASIS_AKTIONEN for a in b.aktionen)
}
RECHTE_ALLE_AKTIONEN = alle_aktionen()


class AccountTyp(TimestampMixin, Base):
    """Frei vom mandant_admin definierter Account-Typ (z.B. "Techniker",
    "Buchhaltung", "Azubi"). Ersetzt die vormals fest verdrahteten Rollen
    disponent/techniker/controller/mitarbeiter -- ein User mit role='custom'
    (siehe app/models/user.py) zeigt ueber account_typ_id hierher, seine
    Rechte ergeben sich ausschliesslich aus AccountTypRecht."""

    __tablename__ = "account_typen"
    __table_args__ = (UniqueConstraint("mandant_id", "name", name="uq_account_typen_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(Text, nullable=True)
    farbe: Mapped[str | None] = mapped_column(Text, nullable=True)
    reihenfolge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Nur zugewiesenen Kunden sichtbar (Kunde-Techniker-Zuweisungen) -- die
    # ehemals an den Rollennamen "techniker" gebundene Einschraenkung ist
    # jetzt ein Schalter je Account-Typ (siehe app/services/kunde_zuweisung_service.py).
    nur_zugewiesene_kunden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Duerfen Nutzer dieses Account-Typs einen Vorgang per Klick selbst
    # uebernehmen ("Ticket übernehmen", siehe app/api/routes/vorgaenge.py),
    # oder muessen sie auf eine manuelle Zuweisung durch mandant_admin/Dispo
    # warten (siehe app/services/rechte_service.py:darf_vorgang_selbst_uebernehmen)?
    # Default false -- selbstaendige Techniker koennen das gezielt bekommen,
    # ohne dass es fuer alle automatisch mit aktiviert wird.
    darf_vorgaenge_selbst_uebernehmen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Einzelrecht "Zeiten buchen" (docs/konzepte/ZEITERFASSUNG.md, Abschnitt
    # 5.4) -- bewusst kein Teil der (bereich, aktion)-Rechte-Matrix, sondern
    # ein einzelner Ja/Nein-Schalter wie darf_vorgaenge_selbst_uebernehmen.
    # An keine Rolle und kein Geraet gebunden: auch ein Techniker in der
    # Feld-App kann buchen duerfen (siehe app/services/rechte_service.py:
    # darf_zeiten_buchen). mandant_admin/super_admin duerfen immer buchen,
    # unabhaengig von diesem Schalter.
    darf_zeiten_buchen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Einzelrecht "Abwesenheiten verwalten": Soll-Arbeitszeit, Feiertage und
    # Bundesland pflegen sowie fremdes Soll/Saldo lesen (app/api/routes/
    # arbeitszeit.py). Gleiches Muster wie darf_zeiten_buchen; mandant_admin/
    # super_admin duerfen immer.
    darf_abwesenheiten_verwalten: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AccountTypRecht(Base):
    """Eine (bereich, aktion)-Zeile je Account-Typ. Fehlt eine Zeile, gilt
    'nicht erlaubt' -- anders als bei den fruehren MandantRollenRecht-Defaults
    gibt es hier keinen impliziten Code-Default mehr, da jeder Account-Typ
    frei erstellt wird und keine Vorlage hat, auf die ein Default sinnvoll
    zurueckfallen koennte."""

    __tablename__ = "account_typ_rechte"
    __table_args__ = (
        UniqueConstraint(
            "account_typ_id", "bereich", "aktion", name="uq_account_typ_rechte"
        ),
        # bereich/aktion bewusst ohne DB-Check: Validierung gegen die Registry
        # (app/core/rechte_registry.py), ein Test prueft DB-Werte <= Registry.
        CheckConstraint(f"scope IN {SCOPES}", name="scope_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Fuer die eigene RLS-Policy; ein DB-Trigger fuellt NULL aus dem Account-Typ,
    # damit Insert-Pfade ohne explizite mandant_id weiter funktionieren.
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    account_typ_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_typen.id"), nullable=False
    )
    bereich: Mapped[str] = mapped_column(Text, nullable=False)
    aktion: Mapped[str] = mapped_column(Text, nullable=False)
    erlaubt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Reichweite der Berechtigung (Registry: SCOPES); wird erst von der
    # Rechte-Engine (Schritt 2) ausgewertet.
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="mandant", server_default="mandant")
