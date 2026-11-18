-- Prueft die Besitz- und Rechteverhaeltnisse im Schema public nach der Einrichtung
-- (scripts/app_rolle_einrichten.sh) bzw. nach einem Restore. Nur lesend.
--
-- Aufruf (als Admin/Bootstrap-User):
--   psql -v ON_ERROR_STOP=1 -Atq -U <admin> -d <db> -v app_rolle=fieldvibe_app \
--     -v system_rolle=fieldvibe_system -v owner_rolle=fieldvibe_owner \
--     -f scripts/sql/besitz_pruefen.sql
-- owner_rolle leer bzw. weggelassen = Modus "App-Rolle ist Eigentuemerin".
--
-- Ausgabe bei Erfolg eine Zeile: ok|<eigentuemer>|<tabellen>|<sequenzen>|<funktionen>|<typen>.
-- Bei einem Verstoss bricht das Skript mit einer Exception ab (psql-Exit != 0, Meldung
-- "Besitzpruefung fehlgeschlagen: ..." auf stderr). Extension-Objekte (deptype 'e') bleiben
-- beim Admin und werden nicht geprueft.

\if :{?app_rolle}
\else
  DO $$ BEGIN RAISE EXCEPTION 'psql-Variable app_rolle fehlt (-v app_rolle=...)'; END $$;
  \quit
\endif
\if :{?system_rolle}
\else
  \set system_rolle ''
\endif
\if :{?owner_rolle}
\else
  \set owner_rolle ''
\endif

SELECT set_config('fieldvibe.app_rolle', :'app_rolle', false),
       set_config('fieldvibe.system_rolle', :'system_rolle', false),
       set_config('fieldvibe.owner_rolle', :'owner_rolle', false) \gset ignore_

DO $$
DECLARE
  app text := current_setting('fieldvibe.app_rolle');
  sys text := current_setting('fieldvibe.system_rolle');
  own text := current_setting('fieldvibe.owner_rolle');
  eigner text;
  rolle text;
  n integer;
  liste text;
  n_tab integer;
  n_seq integer;
  n_fkt integer;
  n_typ integer;
BEGIN
  eigner := COALESCE(NULLIF(own, ''), app);

  FOREACH rolle IN ARRAY ARRAY[app, NULLIF(sys, ''), NULLIF(own, '')] LOOP
    IF rolle IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rolle) THEN
      RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: Rolle % existiert nicht.', rolle;
    END IF;
  END LOOP;

  -- Eigentum: alles in public gehoert dem Eigentuemer (im Owner-Modus also weder
  -- App- noch System-Rolle).
  SELECT count(*), string_agg(format('%s (%s)', c.relname, pg_get_userbyid(c.relowner)), ', ' ORDER BY c.relname)
    INTO n, liste
    FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace
     AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
     AND pg_get_userbyid(c.relowner) <> eigner
     AND NOT EXISTS (SELECT 1 FROM pg_depend d
                     WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e');
  IF n > 0 THEN
    RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % Tabelle(n)/Sequenz(en)/View(s) gehoeren nicht %: %', n, eigner, left(liste, 300);
  END IF;

  SELECT count(*), string_agg(p.proname, ', ' ORDER BY p.proname)
    INTO n, liste
    FROM pg_proc p
   WHERE p.pronamespace = 'public'::regnamespace
     AND p.prokind IN ('f', 'p', 'a')
     AND pg_get_userbyid(p.proowner) <> eigner
     AND NOT EXISTS (SELECT 1 FROM pg_depend d
                     WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e');
  IF n > 0 THEN
    RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % Funktion(en) gehoeren nicht %: %', n, eigner, left(liste, 300);
  END IF;

  SELECT count(*), string_agg(t.typname, ', ' ORDER BY t.typname)
    INTO n, liste
    FROM pg_type t
   WHERE t.typnamespace = 'public'::regnamespace
     AND t.typtype IN ('e', 'd', 'r')
     AND pg_get_userbyid(t.typowner) <> eigner
     AND NOT EXISTS (SELECT 1 FROM pg_depend d
                     WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e');
  IF n > 0 THEN
    RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % Typ(en) gehoeren nicht %: %', n, eigner, left(liste, 300);
  END IF;

  -- App- und System-Rolle: DML auf allen Tabellen, USAGE auf allen Sequenzen.
  FOREACH rolle IN ARRAY ARRAY[app, NULLIF(sys, '')] LOOP
    CONTINUE WHEN rolle IS NULL;
    SELECT count(*), string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO n, liste
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind IN ('r', 'p')
       AND NOT (has_table_privilege(rolle, c.oid, 'SELECT') AND has_table_privilege(rolle, c.oid, 'INSERT')
                AND has_table_privilege(rolle, c.oid, 'UPDATE') AND has_table_privilege(rolle, c.oid, 'DELETE'));
    IF n > 0 THEN
      RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % hat auf % Tabelle(n) nicht SELECT/INSERT/UPDATE/DELETE: %', rolle, n, left(liste, 300);
    END IF;
    SELECT count(*), string_agg(c.relname, ', ' ORDER BY c.relname)
      INTO n, liste
      FROM pg_class c
     WHERE c.relnamespace = 'public'::regnamespace
       AND c.relkind = 'S'
       -- CASE: has_sequence_privilege wirft bei Nicht-Sequenzen, der Planer wertet sonst vor dem relkind-Filter aus.
       AND CASE WHEN c.relkind = 'S' THEN NOT has_sequence_privilege(rolle, c.oid, 'USAGE') END;
    IF n > 0 THEN
      RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % hat auf % Sequenz(en) kein USAGE: %', rolle, n, left(liste, 300);
    END IF;
  END LOOP;

  -- RLS ohne FORCE waere fuer die Eigentuemer-Rolle wirkungslos.
  SELECT count(*), string_agg(relname, ', ' ORDER BY relname)
    INTO n, liste
    FROM pg_class
   WHERE relnamespace = 'public'::regnamespace AND relkind IN ('r', 'p')
     AND relrowsecurity AND NOT relforcerowsecurity;
  IF n > 0 THEN
    RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: % Tabelle(n) mit RLS aber ohne FORCE ROW LEVEL SECURITY: %', n, left(liste, 300);
  END IF;

  -- Default-Privilegien: kuenftige Migrationen (als Owner) muessen App und System
  -- automatisch DML-Rechte geben.
  IF own <> '' THEN
    FOREACH rolle IN ARRAY ARRAY[app, NULLIF(sys, '')] LOOP
      CONTINUE WHEN rolle IS NULL;
      SELECT count(DISTINCT a.privilege_type) INTO n
        FROM pg_default_acl d, aclexplode(d.defaclacl) a
       WHERE d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = own)
         AND d.defaclnamespace = 'public'::regnamespace
         AND d.defaclobjtype = 'r'
         AND a.grantee = (SELECT oid FROM pg_roles WHERE rolname = rolle)
         AND a.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE');
      IF n <> 4 THEN
        RAISE EXCEPTION 'Besitzpruefung fehlgeschlagen: Default-Privilegien von % in public geben % keine vollen DML-Rechte auf kuenftige Tabellen.', own, rolle;
      END IF;
    END LOOP;
  END IF;

  SELECT count(*) INTO n_tab FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e');
  SELECT count(*) INTO n_seq FROM pg_class c
   WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e');
  SELECT count(*) INTO n_fkt FROM pg_proc p
   WHERE p.pronamespace = 'public'::regnamespace AND p.prokind IN ('f', 'p', 'a')
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e');
  SELECT count(*) INTO n_typ FROM pg_type t
   WHERE t.typnamespace = 'public'::regnamespace AND t.typtype IN ('e', 'd', 'r')
     AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e');

  PERFORM set_config('fieldvibe.besitz_ergebnis',
    format('ok|%s|%s|%s|%s|%s', eigner, n_tab, n_seq, n_fkt, n_typ), false);
END
$$;

SELECT current_setting('fieldvibe.besitz_ergebnis');
