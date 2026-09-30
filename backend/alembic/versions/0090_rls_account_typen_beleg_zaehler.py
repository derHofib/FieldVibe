"""RLS fuer account_typen und beleg_zaehler nachziehen.

Beide Tabellen tragen mandant_id (NOT NULL, keine globalen Vorlagen), wurden
aber in 0037/0040 ohne Row Level Security angelegt -- die Mandantentrennung
hing dort allein an Code-Pruefungen. Policy exakt wie in 0083/0084
(mandant_isolation inkl. Super-Admin-Ausnahme). Alle Schreib-/Lesepfade
laufen bereits in tenant_session bzw. system_session (is_super_admin), daher
kein Sonderfall fuer mandant_id IS NULL. Bewusst kein Trigger: anders als bei
den updated_at-Tabellen gibt es hier nichts zu pflegen.

Revision ID: 0090
Revises: 0089
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0090"
down_revision: Union[str, None] = "0089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABELLEN = ("account_typen", "beleg_zaehler")


def upgrade() -> None:
    for table in _TABELLEN:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY mandant_isolation ON {table}
            USING (
              mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
              OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
            )
            WITH CHECK (
              mandant_id = NULLIF(current_setting('app.current_mandant', true), '')::uuid
              OR coalesce(NULLIF(current_setting('app.is_super_admin', true), ''), 'false')::boolean
            )
            """
        )


def downgrade() -> None:
    for table in _TABELLEN:
        op.execute(f"DROP POLICY IF EXISTS mandant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
