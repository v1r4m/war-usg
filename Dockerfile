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

# Holds the DB (wargame.db) and the secret key → mount a volume here in Coolify
VOLUME ["/app/instance"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz', timeout=4)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
# --preload: initialize the app once (create DB, seed challenges) before forking workers → no SQLite init races
CMD ["sh", "-c", "exec gunicorn --preload --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --threads 4 --access-logfile - run:app"]
