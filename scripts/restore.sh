#!/usr/bin/env bash
# Restore a backup into an EMPTY database: scripts/restore.sh <dump> <target DATABASE_URL>
set -euo pipefail
pg_restore --no-owner --exit-on-error -d "${2:?target url}" "${1:?dump file}"
