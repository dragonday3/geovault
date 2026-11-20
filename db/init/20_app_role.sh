#!/bin/sh
# Runs once, on first start of an empty data volume (docker-entrypoint-initdb.d).
# Creates the least-privilege application role. The API never connects as the superuser.
#  - geovault_app owns the database (so it can run migrations in schema public)
#  - it is NOT superuser, cannot create roles or databases, cannot read server files
#  - PostGIS is installed here by the superuser because the extension is untrusted
set -eu

: "${GEOVAULT_DB_PASSWORD:?GEOVAULT_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v app_pw="$GEOVAULT_DB_PASSWORD" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE geovault_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION
    PASSWORD :'app_pw';
ALTER DATABASE :"DBNAME" OWNER TO geovault_app;
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO geovault_app;
SQL
