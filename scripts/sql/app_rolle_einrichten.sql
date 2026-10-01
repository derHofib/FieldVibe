-- Richtet die App-Rolle ein, mit der Backend, Worker und Alembic sich
-- verbinden. Hintergrund: das offizielle postgres-Image macht POSTGRES_USER
-- zum Bootstrap-Superuser, dem sich weder SUPERUSER noch BYPASSRLS entziehen
-- lassen -- ein Superuser umgeht jede RLS-Policy. Deshalb bleibt dieser User
-- reiner Admin, die Anwendung laeuft als eigene, unprivilegierte Rolle.
--
-- Aufruf (als Admin/Bootstrap-User), idempotent:
--   psql -v ON_ERROR_STOP=1 -U <admin> -d <db> \
--     -v app_rolle=fieldvibe_app -v app_passwort=... -v db_name=<db> \
--     -f scripts/sql/app_rolle_einrichten.sql
-- Meist ueber scripts/app_rolle_einrichten.sh.

\if :{?app_rolle}
\else
  DO $$ BEGIN RAISE EXCEPTION 'psql-Variable app_rolle fehlt (-v app_rolle=...)'; END $$;
  \quit
\endif
\if :{?app_passwort}
\else
  DO $$ BEGIN RAISE EXCEPTION 'psql-Variable app_passwort fehlt (-v app_passwort=...)'; END $$;
  \quit
\endif
\if :{?db_name}
\else
  DO $$ BEGIN RAISE EXCEPTION 'psql-Variable db_name fehlt (-v db_name=...)'; END $$;
  \quit
\endif

-- DO-Bloecke sind Dollar-Quotes, psql ersetzt dort keine Variablen; die
-- Werte reisen deshalb als Session-Settings hinein und werden im Block per
-- format(%I/%L) sicher gequotet.
SELECT set_config('fieldvibe.app_rolle', :'app_rolle', false),
       set_config('fieldvibe.app_passwort', :'app_passwort', false),
       set_config('fieldvibe.db_name', :'db_name', false) \gset ignore_

DO $$
DECLARE
  app text := current_setting('fieldvibe.app_rolle');
  pw  text := current_setting('fieldvibe.app_passwort');
  db  text := current_setting('fieldvibe.db_name');
  r   record;
  n   integer;
BEGIN
  IF app = current_user THEN
    RAISE EXCEPTION 'App-Rolle % ist identisch mit dem ausfuehrenden Admin-User -- dann waere nichts abgesichert.', app;
  END IF;
  IF length(pw) < 8 THEN
    RAISE EXCEPTION 'Passwort der App-Rolle ist zu kurz (mindestens 8 Zeichen).';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app) THEN
    EXECUTE format('CREATE ROLE %I LOGIN', app);
    RAISE NOTICE 'Rolle % angelegt.', app;
  ELSE
    RAISE NOTICE 'Rolle % existiert bereits -- Attribute und Passwort werden neu gesetzt.', app;
  END IF;
  EXECUTE format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION PASSWORD %L',
    app, pw);

  -- CREATE auf der DB: Migration 0001 legt die (trusted) Extensions
  -- pgcrypto/pg_trgm an, sofern sie noch nicht existieren.
  EXECUTE format('GRANT CONNECT, CREATE ON DATABASE %I TO %I', db, app);
  EXECUTE format('GRANT USAGE, CREATE ON SCHEMA public TO %I', app);

  -- Eigentum uebertragen statt REASSIGN OWNED: das wuerde beim
  -- Bootstrap-User auch Systemobjekte betreffen. Extension-Objekte (deptype
  -- 'e') bleiben bewusst beim Admin; ihre Funktionen sind per Default fuer
  -- PUBLIC ausfuehrbar.
  FOR r IN
    SELECT c.relkind, format('%I.%I', n.nspname, c.relname) AS name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
      AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = app)
      AND NOT EXISTS (SELECT 1 FROM pg_depend d
                      WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
    ORDER BY (c.relkind = 'S'), c.relname  -- Sequenzen zuletzt: owned-by-Sequenzen ziehen mit der Tabelle um
  LOOP
    -- Owned-by-Sequenzen sind nach dem Tabellen-Wechsel schon umgezogen.
    IF r.relkind = 'S' AND (SELECT relowner FROM pg_class WHERE oid = r.name::regclass)
                           = (SELECT oid FROM pg_roles WHERE rolname = app) THEN
      CONTINUE;
    END IF;
    EXECUTE format('ALTER %s %s OWNER TO %I',
      CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                     WHEN 'S' THEN 'SEQUENCE' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
      r.name, app);
  END LOOP;

  FOR r IN
    SELECT p.prokind, p.oid::regprocedure::text AS name
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.prokind IN ('f', 'p', 'a')
      AND p.proowner <> (SELECT oid FROM pg_roles WHERE rolname = app)
      AND NOT EXISTS (SELECT 1 FROM pg_depend d
                      WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
  LOOP
    EXECUTE format('ALTER %s %s OWNER TO %I',
      CASE r.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END,
      r.name, app);
  END LOOP;

  -- Array-/Tabellen-Rowtypes ziehen mit ihrem Basistyp um und werden nicht
  -- einzeln angefasst (daher nur e/d/r).
  FOR r IN
    SELECT t.typtype, format('%I.%I', n.nspname, t.typname) AS name
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public'
      AND t.typtype IN ('e', 'd', 'r')
      AND t.typowner <> (SELECT oid FROM pg_roles WHERE rolname = app)
      AND NOT EXISTS (SELECT 1 FROM pg_depend d
                      WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e')
  LOOP
    EXECUTE format('ALTER %s %s OWNER TO %I',
      CASE r.typtype WHEN 'd' THEN 'DOMAIN' ELSE 'TYPE' END, r.name, app);
  END LOOP;

  -- Kontrolle: nichts im Schema public darf noch dem Admin gehoeren, sonst
  -- scheitert eine spaetere Migration (ALTER TABLE ... braucht Eigentum).
  SELECT (
    (SELECT count(*) FROM pg_class c
      WHERE c.relnamespace = 'public'::regnamespace
        AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
        AND pg_get_userbyid(c.relowner) <> app
        AND NOT EXISTS (SELECT 1 FROM pg_depend d
                        WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'))
    + (SELECT count(*) FROM pg_proc p
        WHERE p.pronamespace = 'public'::regnamespace
          AND p.prokind IN ('f', 'p', 'a')
          AND pg_get_userbyid(p.proowner) <> app
          AND NOT EXISTS (SELECT 1 FROM pg_depend d
                          WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e'))
    + (SELECT count(*) FROM pg_type t
        WHERE t.typnamespace = 'public'::regnamespace
          AND t.typtype IN ('e', 'd', 'r')
          AND pg_get_userbyid(t.typowner) <> app
          AND NOT EXISTS (SELECT 1 FROM pg_depend d
                          WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e'))
  ) INTO n;
  IF n <> 0 THEN
    RAISE EXCEPTION 'Eigentumsuebertragung unvollstaendig: % Objekt(e) in public gehoeren nicht %.', n, app;
  END IF;

  -- FORCE RLS haengt an der Tabelle, nicht am Eigentuemer; die Kontrolle
  -- stellt sicher, dass kein Ownerwechsel daran etwas geaendert hat.
  SELECT count(*) INTO n FROM pg_class
   WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
     AND relrowsecurity AND NOT relforcerowsecurity;
  IF n <> 0 THEN
    RAISE EXCEPTION '% Tabelle(n) mit RLS aber ohne FORCE ROW LEVEL SECURITY.', n;
  END IF;

  RAISE NOTICE 'App-Rolle % ist eingerichtet, alle Objekte in public gehoeren ihr.', app;
END
$$;

-- Bewusst nicht ausgegeben: das Passwort. Nur den Rollenstatus.
SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolcanlogin
FROM pg_roles WHERE rolname = :'app_rolle';
