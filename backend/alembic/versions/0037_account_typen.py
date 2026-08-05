"""Frei vom mandant_admin definierbare Account-Typen mit eigener
Rechte-Matrix (Bereich x sehen/erstellen/bearbeiten/loeschen) -- loesen die
vormals fest verdrahteten Rollen disponent/techniker/controller/mitarbeiter
vollstaendig ab. super_admin, mandant_admin sowie die Papierkorb-Rollen
loesch_ansicht/loesch_operativ bleiben unangetastet fest verdrahtet (siehe
app/models/user.py).

Migriert bestehende Nutzer mit einer der vier abgeloesten Rollen automatisch
in einen neu angelegten, gleichnamigen Account-Typ je Mandant, mit Rechten,
die das bisherige (fest verdrahtete) Zugriffsverhalten so genau wie moeglich
nachbilden -- niemand verliert beim Umstieg Zugriff. Bestehende
MandantRollenRecht-Anpassungen (controller/mitarbeiter) werden dabei
uebernommen statt verworfen.

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-05
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RECHTE_BEREICHE = (
    "vorgaenge",
    "kunden",
    "material",
    "dispo",
    "abrechnung",
    "statistik",
    "mitarbeiterverwaltung",
)
RECHTE_AKTIONEN = ("sehen", "erstellen", "bearbeiten", "loeschen")

# Best-effort-Nachbildung des bisherigen, im Code fest verdrahteten
# Zugriffsverhaltens der vier abgeloesten Rollen (aus einer vollstaendigen
# Durchsicht aller require_roles(...)-Aufrufe zum Zeitpunkt dieser Migration).
LEGACY_DEFAULTS: dict[str, dict[str, set[str]]] = {
    "disponent": {
        "vorgaenge": {"sehen", "erstellen", "bearbeiten", "loeschen"},
        "kunden": {"sehen", "erstellen", "bearbeiten", "loeschen"},
        "material": {"sehen", "erstellen", "bearbeiten", "loeschen"},
        "dispo": {"sehen", "erstellen", "bearbeiten", "loeschen"},
        "abrechnung": {"sehen", "erstellen", "bearbeiten", "loeschen"},
        "statistik": {"sehen"},
        # "sehen" deckt u.a. den Kollegen-Picker fuer @-Erwaehnungen ab, den
        # disponent schon vor diesem Umbau unconditionell nutzen konnte
        # (siehe app/api/routes/users.py). "bearbeiten" deckt separat die
        # Einsicht in fremde Zeiterfassungen/Statistiken/Wochenzettel ab
        # (siehe app/services/rechte_service.py:darf_fremde_mitarbeiterdaten_einsehen),
        # die disponent ebenfalls schon vorher hatte.
        "mitarbeiterverwaltung": {"sehen", "bearbeiten"},
    },
    "techniker": {
        "vorgaenge": {"sehen", "erstellen", "bearbeiten"},
        "kunden": {"sehen"},
        "material": {"sehen"},
        "dispo": {"sehen"},
        "abrechnung": {"sehen"},
        "statistik": {"sehen"},
        # Nur "sehen" (@-Erwaehnungs-Picker) -- techniker konnte vor diesem
        # Umbau explizit NUR die eigene Zeiterfassung/Statistik einsehen,
        # bekommt "bearbeiten" (siehe darf_fremde_mitarbeiterdaten_einsehen)
        # daher bewusst nicht.
        "mitarbeiterverwaltung": {"sehen"},
    },
    "controller": {
        "vorgaenge": {"sehen"},
        "kunden": {"sehen"},
        "material": {"sehen"},
        "dispo": {"sehen"},
        "abrechnung": {"sehen"},
        "statistik": {"sehen"},
        "mitarbeiterverwaltung": {"sehen", "bearbeiten"},
    },
    "mitarbeiter": {
        "vorgaenge": {"sehen", "erstellen", "bearbeiten"},
        "kunden": {"sehen", "erstellen", "bearbeiten"},
        "material": {"sehen", "erstellen", "bearbeiten"},
        "dispo": {"sehen"},
        "abrechnung": set(),
        "statistik": {"sehen"},
        # Kein "sehen" (kein @-Erwaehnungs-Picker-Zugriff, unveraendert),
        # aber "bearbeiten" -- mitarbeiter konnte vor diesem Umbau ebenfalls
        # fremde Zeiterfassungen/Statistiken einsehen.
        "mitarbeiterverwaltung": {"bearbeiten"},
    },
}
LEGACY_LABEL = {
    "disponent": "Disponent",
    "techniker": "Techniker",
    "controller": "Controller",
    "mitarbeiter": "Mitarbeiter",
}
LEGACY_ICON = {"disponent": "🧭", "techniker": "🔧", "controller": "📊", "mitarbeiter": "👤"}


def upgrade() -> None:
    op.create_table(
        "account_typen",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mandant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mandanten.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("farbe", sa.Text(), nullable=True),
        sa.Column("reihenfolge", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "nur_zugewiesene_kunden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("mandant_id", "name", name=op.f("uq_account_typen_name")),
    )
    op.create_table(
        "account_typ_rechte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_typ_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account_typen.id"),
            nullable=False,
        ),
        sa.Column("bereich", sa.Text(), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("erlaubt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "account_typ_id", "bereich", "aktion", name=op.f("uq_account_typ_rechte")
        ),
        sa.CheckConstraint(
            f"bereich IN {RECHTE_BEREICHE}", name=op.f("ck_account_typ_rechte_bereich_valid")
        ),
        sa.CheckConstraint(
            f"aktion IN {RECHTE_AKTIONEN}", name=op.f("ck_account_typ_rechte_aktion_valid")
        ),
    )
    op.add_column(
        "users", sa.Column("account_typ_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_users_account_typ_id_account_typen"),
        "users",
        "account_typen",
        ["account_typ_id"],
        ["id"],
    )

    bind = op.get_bind()

    # Muss vor der Daten-Migration unten laufen: die UPDATE-Anweisungen dort
    # setzen role='custom', was die alte Constraint (noch ohne 'custom')
    # sonst mit einer CheckViolation ablehnen wuerde. Ein CHECK wird beim
    # Erstellen sofort gegen ALLE bestehenden Zeilen geprueft -- die alten
    # Rollennamen (disponent/techniker/controller/mitarbeiter) muessen daher
    # hier zusaetzlich zu 'custom' vorerst weiter erlaubt bleiben, bis die
    # Schleife unten jede Zeile auf 'custom' umgestellt hat; erst danach wird
    # unten auf den endgueltigen, engeren Wertebereich verschaerft.
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint(
        "role_valid",
        "users",
        "role IN ('super_admin','mandant_admin','custom','loesch_ansicht','loesch_operativ',"
        "'disponent','techniker','controller','mitarbeiter')",
    )

    mandant_rollen = bind.execute(
        text(
            "SELECT DISTINCT mandant_id, role FROM users "
            "WHERE role IN ('disponent','techniker','controller','mitarbeiter') "
            "AND mandant_id IS NOT NULL"
        )
    ).fetchall()

    # Bestehende MandantRollenRecht-Overrides (nur controller/mitarbeiter)
    # einlesen, damit individuelle Anpassungen des mandant_admin erhalten
    # bleiben statt beim Umstieg verworfen zu werden.
    hat_alte_tabelle = bind.execute(text("SELECT to_regclass('mandant_rollen_rechte')")).scalar()
    overrides: dict[tuple, bool] = {}
    if hat_alte_tabelle is not None:
        for row in bind.execute(
            text("SELECT mandant_id, rolle, bereich, aktion, erlaubt FROM mandant_rollen_rechte")
        ).fetchall():
            overrides[(str(row.mandant_id), row.rolle, row.bereich, row.aktion)] = row.erlaubt

    for mandant_id, rolle in mandant_rollen:
        typ_id = str(uuid.uuid4())
        bind.execute(
            text(
                "INSERT INTO account_typen "
                "(id, mandant_id, name, icon, farbe, reihenfolge, nur_zugewiesene_kunden, "
                "created_at, updated_at) "
                "VALUES (:id, :mandant_id, :name, :icon, NULL, 0, :nur_zugewiesen, now(), now())"
            ),
            {
                "id": typ_id,
                "mandant_id": str(mandant_id),
                "name": LEGACY_LABEL[rolle],
                "icon": LEGACY_ICON[rolle],
                "nur_zugewiesen": rolle == "techniker",
            },
        )
        for bereich in RECHTE_BEREICHE:
            for aktion in RECHTE_AKTIONEN:
                override_key = (str(mandant_id), rolle, bereich, aktion)
                bearbeiten_key = (str(mandant_id), rolle, bereich, "bearbeiten")
                if override_key in overrides:
                    erlaubt = overrides[override_key]
                elif aktion == "erstellen" and bearbeiten_key in overrides:
                    # Die alte Matrix kannte kein separates "erstellen" --
                    # eine bestehende "bearbeiten"-Freigabe deckte das ab.
                    erlaubt = overrides[bearbeiten_key]
                else:
                    erlaubt = aktion in LEGACY_DEFAULTS[rolle].get(bereich, set())
                bind.execute(
                    text(
                        "INSERT INTO account_typ_rechte "
                        "(id, account_typ_id, bereich, aktion, erlaubt) "
                        "VALUES (:id, :typ_id, :bereich, :aktion, :erlaubt)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "typ_id": typ_id,
                        "bereich": bereich,
                        "aktion": aktion,
                        "erlaubt": erlaubt,
                    },
                )
        bind.execute(
            text(
                "UPDATE users SET role = 'custom', account_typ_id = :typ_id "
                "WHERE mandant_id = :mandant_id AND role = :rolle"
            ),
            {"typ_id": typ_id, "mandant_id": str(mandant_id), "rolle": rolle},
        )

    # Jetzt sind alle Zeilen auf 'custom' umgestellt -- die uebergangsweise
    # noch erlaubten alten Rollennamen koennen aus der Constraint entfernt
    # werden.
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint(
        "role_valid",
        "users",
        "role IN ('super_admin','mandant_admin','custom','loesch_ansicht','loesch_operativ')",
    )

    if hat_alte_tabelle is not None:
        op.drop_table("mandant_rollen_rechte")


def downgrade() -> None:
    op.create_table(
        "mandant_rollen_rechte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mandant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mandanten.id"), nullable=False
        ),
        sa.Column("rolle", sa.Text(), nullable=False),
        sa.Column("bereich", sa.Text(), nullable=False),
        sa.Column("aktion", sa.Text(), nullable=False),
        sa.Column("erlaubt", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "mandant_id", "rolle", "bereich", "aktion", name="uq_mandant_rollen_rechte"
        ),
        sa.CheckConstraint(
            "rolle IN ('controller', 'mitarbeiter')", name="ck_mandant_rollen_rechte_rolle_valid"
        ),
        sa.CheckConstraint(
            f"bereich IN {RECHTE_BEREICHE}", name="ck_mandant_rollen_rechte_bereich_valid"
        ),
        sa.CheckConstraint(
            "aktion IN ('sehen', 'bearbeiten')", name="ck_mandant_rollen_rechte_aktion_valid"
        ),
    )

    bind = op.get_bind()
    # Wie in upgrade(): erst auf eine Obermenge (alte UND neue Rollennamen)
    # erweitern, weil die ADD-CONSTRAINT sofort gegen alle bestehenden
    # Zeilen prueft und diese zu diesem Zeitpunkt noch 'custom' tragen.
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint(
        "role_valid",
        "users",
        "role IN ('super_admin','mandant_admin','custom','disponent','techniker','controller',"
        "'mitarbeiter','loesch_ansicht','loesch_operativ')",
    )

    # Best-effort-Rueckmigration: ein 'custom'-Nutzer bekommt die Rolle
    # zurueck, die dem Namen seines Account-Typs entspricht (Faelle ausserhalb
    # der vier Standardnamen -- z.B. neu vom mandant_admin angelegte
    # Account-Typen -- werden auf 'mitarbeiter' abgebildet, da eine
    # verlustfreie Rueckabbildung frei benannter Typen nicht moeglich ist).
    label_zu_rolle = {v: k for k, v in LEGACY_LABEL.items()}
    for label, rolle in label_zu_rolle.items():
        bind.execute(
            text(
                "UPDATE users SET role = :rolle "
                "WHERE role = 'custom' AND account_typ_id IN "
                "(SELECT id FROM account_typen WHERE name = :label)"
            ),
            {"rolle": rolle, "label": label},
        )
    bind.execute(text("UPDATE users SET role = 'mitarbeiter' WHERE role = 'custom'"))

    # Jetzt ist keine Zeile mehr 'custom' -- auf den engeren Ziel-Wertebereich
    # verschaerfen.
    op.drop_constraint("role_valid", "users", type_="check")
    op.create_check_constraint(
        "role_valid",
        "users",
        "role IN ('super_admin','mandant_admin','disponent','techniker','controller',"
        "'mitarbeiter','loesch_ansicht','loesch_operativ')",
    )

    op.drop_constraint(
        op.f("fk_users_account_typ_id_account_typen"), "users", type_="foreignkey"
    )
    op.drop_column("users", "account_typ_id")
    op.drop_table("account_typ_rechte")
    op.drop_table("account_typen")
