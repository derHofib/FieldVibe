"""Strukturelle Rollenlogik an einer Stelle (Plattform vs. Mandant, Papierkorb-
Rollen, Mitarbeiter-Accounts). Fachliche Berechtigungen ("darf X sehen/
bearbeiten") laufen NIE hierueber, sondern ueber berechtigung_service bzw.
require_recht. Die Helfer nehmen alles mit `.role` entgegen (AuthContext, User)."""
from typing import Protocol


class _HatRolle(Protocol):
    role: str


PAPIERKORB_ROLLEN = ("loesch_ansicht", "loesch_operativ")
# Accounts, die als Techniker/Bearbeiter zugewiesen werden koennen.
MITARBEITER_ROLLEN = ("mandant_admin", "custom")


def ist_plattform_admin(wer: _HatRolle) -> bool:
    return wer.role == "super_admin"


def ist_mandant_admin(wer: _HatRolle) -> bool:
    return wer.role == "mandant_admin"


def hat_admin_rechte_im_mandant(wer: _HatRolle) -> bool:
    """mandant_admin und loesch_operativ (dieselben Rechte wie ein mandant_admin,
    siehe deps.require_roles) -- fuer die Grenzen bei Rollenvergabe und Verwaltung
    fremder Accounts in users.py."""
    return wer.role in ("mandant_admin", "loesch_operativ")


def ist_mitarbeiter_account(wer: _HatRolle) -> bool:
    return wer.role in MITARBEITER_ROLLEN
