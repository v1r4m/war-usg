#!/bin/sh
set -e

# 볼륨이 root 소유로 마운트되는 경우가 있어서, root로 시작했다면 권한을 맞춘 뒤 app 유저로 실행
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/instance
  export HOME=/app
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
