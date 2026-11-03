# Judge server for this challenge. Runs as its own Coolify resource, apart from the wargame,
# because players' code runs in here (and the revenge is meant to be escaped).
FROM python:3.12-slim

# Unprivileged account that runs the judge, and with it the players' code
RUN useradd --system --uid 10010 --no-create-home judge

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py start.sh ./
RUN chmod 0755 start.sh && touch flag.txt && chown judge:judge flag.txt

USER judge
ENV PORT=8000
EXPOSE 8000
CMD ["./start.sh"]
