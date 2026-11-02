#!/bin/sh
set -e

# Volumes are sometimes mounted root-owned: if started as root, fix ownership, then drop to the app user
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/instance
  export HOME=/app
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
