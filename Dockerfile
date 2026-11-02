FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /app/instance \
    && chown app:app /app /app/instance

COPY --chown=app:app . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# DB(wargame.db)와 시크릿 키가 저장되는 곳 → Coolify에서 볼륨으로 연결하세요
VOLUME ["/app/instance"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz', timeout=4)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
# --preload: 앱을 한 번만 초기화(DB 생성·문제 시드)한 뒤 워커를 띄움 → SQLite 초기화 경쟁 방지
CMD ["sh", "-c", "exec gunicorn --preload --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --threads 4 --access-logfile - run:app"]
