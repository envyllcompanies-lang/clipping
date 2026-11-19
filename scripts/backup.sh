#!/usr/bin/env bash
# Daily database backup (doc 25). Keeps 14 days. The bucket holds nothing irreplaceable.
set -euo pipefail
DIR="${1:-./var/backups}"; mkdir -p "$DIR"
F="$DIR/clipping-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner "${DATABASE_URL:?}" -f "$F"
find "$DIR" -name 'clipping-*.dump' -mtime +14 -delete
echo "$F"
