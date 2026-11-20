"""Herkunft eines Datensatzes (Migration 0129): 'ki' bei Anlage ueber den MCP-Adapter (auth.via == "mcp"),
sonst 'app'. Gleiches Wort wie bei Formularen; Telefonate nutzen aus Altbestand 'claude'."""
from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

ERSTELLT_VIA = ("app", "ki")


def erstellt_via_check() -> CheckConstraint:
    return CheckConstraint(f"erstellt_via IN {ERSTELLT_VIA}", name="erstellt_via_valid")


def erstellt_via_spalte() -> Mapped[str]:
    return mapped_column(Text, nullable=False, default="app", server_default="app")
