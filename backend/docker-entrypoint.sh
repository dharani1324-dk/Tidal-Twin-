#!/bin/sh
# OceanVerse AI - Backend container entrypoint
# ----------------------------------------------
# 1) Wait for the database to accept connections
# 2) Create tables, seed locations, pull live data
# 3) Start the API server
#
# All configuration comes from environment variables
# supplied by docker-compose.yml

set -e

echo "[oceanverse] Waiting for database at ${DB_HOST}:${DB_PORT} ..."

# Simple retry loop (PostGIS can take a moment to be ready)
i=0
until python -c \
    "import socket, sys; s=socket.socket(); s.settimeout(3); s.connect((sys.argv[1], int(sys.argv[2]))); s.close()" \
    "${DB_HOST}" "${DB_PORT}"; do
  i=$((i+1))
  echo "[oceanverse] Database not ready yet (attempt ${i})"
  [ "$i" -gt 30 ] && echo "[oceanverse] Timed out waiting for database" && exit 1
  sleep 2
done

echo "[oceanverse] Database is reachable. Initializing schema ..."
python -m scripts.init_db

echo "[oceanverse] Seeding coastal locations ..."
python -m scripts.seed_data

echo "[oceanverse] Fetching live ocean observations (best effort) ..."
# Refresh may fail if the network is offline; the app still works on seeded data.
python -m scripts.refresh_ocean_data || echo "[oceanverse] WARNING: live data refresh failed - continuing with existing data"

echo "[oceanverse] Starting OceanVerse AI API on port ${PORT} ..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"