import re
from collections.abc import Iterator
from contextlib import contextmanager

from alembic import op

_TABELLENNAME = re.compile(r"^[a-z_][a-z0-9_]*$")


@contextmanager
def rls_fuer_backfill_aufheben(*tabellen: str) -> Iterator[None]:
    """Hebt FORCE ROW LEVEL SECURITY fuer die Dauer eines Daten-Backfills auf.

    Noetig bei UPDATE/INSERT ... SELECT ueber Mandantengrenzen auf RLS-Tabellen
    in Migrationen: dort ist kein app.current_mandant gesetzt, die Policies
    liessen den Backfill ins Leere laufen (und ein folgendes SET NOT NULL
    scheitert an den unberuehrten Zeilen).

    Funktioniert nur, wenn die Migrationsrolle Eigentuemerin der Tabelle ist
    (Owner-Rolle bzw. in Altinstallationen/Tests die App-Rolle): ohne FORCE ist
    die Eigentuemerin von RLS ausgenommen. Alles bleibt in der Migrations-
    Transaktion, kein Commit dazwischen -- FORCE ist am Ende wieder gesetzt.

    Der Ort liegt unter app/db statt alembic/helpers, weil ein Paket dort mit
    dem installierten Paket alembic kollidieren wuerde; prepend_sys_path in
    alembic.ini macht app in Migrationen importierbar.
    """
    for tabelle in tabellen:
        if not _TABELLENNAME.fullmatch(tabelle):
            raise ValueError(f"Ungueltiger Tabellenname: {tabelle!r}")

    for tabelle in tabellen:
        op.execute(f"ALTER TABLE {tabelle} NO FORCE ROW LEVEL SECURITY")
    yield
    # Bewusst kein try/finally: nach einer Exception im Block ist die
    # Transaktion abgebrochen, ein weiteres execute wuerde mit "current
    # transaction is aborted" die Originalursache ueberdecken. Alembic rollt
    # die Transaktion (transaktionales DDL) inkl. NO FORCE zurueck.
    for tabelle in tabellen:
        op.execute(f"ALTER TABLE {tabelle} FORCE ROW LEVEL SECURITY")
