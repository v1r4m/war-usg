#!/bin/sh
# Write the flag from $FLAG (it must match the challenge's flag in the wargame).
set -e
chmod 0600 flag.txt
if [ -n "$FLAG" ]; then
  printf '%s' "$FLAG" > flag.txt
elif [ ! -s flag.txt ]; then
  echo "warning: FLAG is not set" >&2
  printf 'USG{flag_not_configured}' > flag.txt
fi
chmod 0400 flag.txt
exec gunicorn --bind "0.0.0.0:${PORT}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 app:app
