#!/bin/sh
# Read-only database role for GeoServer. Idempotent: runs automatically on a new data volume
# (docker-entrypoint-initdb.d) and can be re-run on an existing one:
#   docker compose exec -T db sh /docker-entrypoint-initdb.d/30_geoserver_role.sh
#
# Defence in depth: even with GeoServer admin access, this role can read ONLY the
# public_places view (migration 0010). It cannot read users, favourites, shares, photos,
# tokens or the audit log, and every transaction it opens is read-only.
set -eu

: "${GEOVAULT_GEOSERVER_DB_PASSWORD:?GEOVAULT_GEOSERVER_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v ro_pw="$GEOVAULT_GEOSERVER_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE geoserver_ro LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'geoserver_ro')\gexec
ALTER ROLE geoserver_ro PASSWORD :'ro_pw';
ALTER ROLE geoserver_ro SET default_transaction_read_only = on;
ALTER ROLE geoserver_ro SET statement_timeout = '15s';
GRANT CONNECT ON DATABASE :"DBNAME" TO geoserver_ro;
GRANT USAGE ON SCHEMA public TO geoserver_ro;
-- The view may not exist yet on a brand-new volume; migration 0010 grants it then.
SELECT 'GRANT SELECT ON public.public_places TO geoserver_ro'
WHERE to_regclass('public.public_places') IS NOT NULL\gexec
SQL
