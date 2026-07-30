import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.vorgang import ABRECHNUNGSARTEN_VORGANG, LEISTUNGSTYPEN

DAUERAUFTRAG_MODI = ("rollierend", "fest")


class Dauerauftrag(TimestampMixin, Base):
    """Wiederkehrender Auftrag: erzeugt automatisch einen neuen Vorgang fuer
    denselben Kunden, sobald der jeweils zuletzt erzeugte Vorgang eines
    Ziels abgeschlossen wird -- nie waehrend ein Vorgang noch offen ist
    (siehe app/api/routes/vorgaenge.py, Abschluss-Hook).

    Ein Dauerauftrag kann mehrere Ziele buendeln (z.B. 100 Anlagen desselben
    Kunden statt 100 einzelner Daueraufträge) -- siehe app.models.dauerauftrag_ziel.
    DauerauftragZiel. Jedes Ziel hat seinen eigenen Zyklus
    (naechste_faelligkeit_am/offener_vorgang_id) und dreht sich unabhaengig
    von den anderen Zielen im selben Buendel weiter.

    modus="rollierend" (Default): naechste_faelligkeit_am = tatsaechliches
    Abschlussdatum + intervall_tage -- die Frist "wandert" mit, wenn ein
    Vorgang frueher oder spaeter als geplant erledigt wird.
    modus="fest": naechste_faelligkeit_am = bisherige naechste_faelligkeit_am
    + intervall_tage -- die Frist bleibt an einem festen Kalenderrhythmus
    verankert, unabhaengig vom tatsaechlichen Abschlussdatum.

    toleranz_frueh_tage/toleranz_spaet_tage (beide optional, NULL = kein
    Hinweis): wird ein Vorgang mehr als diese Anzahl Tage vor bzw. nach
    seiner geplanten Faelligkeit abgeschlossen, entsteht dazu lediglich ein
    Hinweis-Event im Vorgangs-Chat -- der Abschluss selbst wird nie
    blockiert."""

    __tablename__ = "dauerauftraege"
    __table_args__ = (
        CheckConstraint("intervall_tage > 0", name="ck_dauerauftraege_intervall_positiv"),
        CheckConstraint(
            f"abrechnungsart IN {ABRECHNUNGSARTEN_VORGANG}",
            name="ck_dauerauftraege_abrechnungsart_valid",
        ),
        CheckConstraint(
            f"leistungstyp IN {LEISTUNGSTYPEN}", name="ck_dauerauftraege_leistungstyp_valid"
        ),
        CheckConstraint(f"modus IN {DAUERAUFTRAG_MODI}", name="ck_dauerauftraege_modus_valid"),
        CheckConstraint(
            "toleranz_frueh_tage IS NULL OR toleranz_frueh_tage >= 0",
            name="ck_dauerauftraege_toleranz_frueh_positiv",
        ),
        CheckConstraint(
            "toleranz_spaet_tage IS NULL OR toleranz_spaet_tage >= 0",
            name="ck_dauerauftraege_toleranz_spaet_positiv",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mandant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandanten.id"), nullable=False
    )
    kunde_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("kunden.id"), nullable=False
    )
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    abrechnungsart: Mapped[str] = mapped_column(Text, nullable=False)
    leistungstyp: Mapped[str] = mapped_column(Text, nullable=False)
    intervall_tage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    modus: Mapped[str] = mapped_column(Text, nullable=False, default="rollierend")
    toleranz_frueh_tage: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    toleranz_spaet_tage: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
