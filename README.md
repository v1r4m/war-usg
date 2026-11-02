# war-usg
The 最強海巨 (Ultimate Sea Giant) wargame 🌊🚩

A hacking wargame (CTF) platform built with Flask.

## Features
- **Sign up / log in**: hashed passwords, CSRF protection, open-redirect protection
- **Challenge list**: grouped by category, with difficulty, solved state, and solve counts
- **Flag submission**: constant-time comparison, per-minute rate limit, first blood
- **Scoreboard / user profiles**: ties go to whoever got there first
- **Admin pages**: dashboard, create / edit / hide / delete challenges, user management, submission log
- **Slash intro**: the team artwork waves like a flag on the home page; drag (or click) to slice it open
- **9 built-in labs**: flags are randomly generated on every install

| Challenge | Category | Difficulty | Topic |
|---|---|---|---|
| Welcome to USG | misc | easy | Submitting a flag |
| Invisible Note | web | easy | Viewing page source |
| No Robots Allowed | web | easy | robots.txt |
| Double Cipher | crypto | easy | Base64 + ROT13 |
| Cookie Monster | web | easy | Unsigned cookie tampering |
| Someone Else's Notes | web | medium | IDOR |
| SQL Login | web | medium | SQL injection |
| File Viewer | web | hard | Path traversal filter bypass |
| Deleted, Not Gone | cloud | medium | S3 versioning (delete markers, `ListBucketVersions`) |

> The labs are **intentionally vulnerable** for learning, but isolated so the server itself stays safe.
> SQLi only touches a fresh in-memory DB per request, path traversal reads from a virtual filesystem, never the real disk, and the S3 lab imitates a bucket in memory without touching AWS.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# create an admin account (you'll be prompted for the password)
flask --app run create-admin admin

# start the server → http://127.0.0.1:5050
# (on macOS, port 5000 is taken by the AirPlay receiver)
flask --app run run --debug --port 5050
```

On first start, the DB (`wargame.db`) and a secret key are created under `instance/`, and the default challenges are added.

## Docker / Coolify
```bash
docker build -t war-usg .
docker run -d -p 8000:8000 -v war-usg-data:/app/instance \
  -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD='change-me-please' war-usg
```

**Coolify setup**
1. New resource → GitHub repo `v1r4m/war-usg` → Build Pack: **Dockerfile**
2. Ports Exposes: `8000`
3. Persistent Storage: Volume Mount, destination path `/app/instance` (⚠️ without it, every redeploy wipes the DB)
4. Environment variables
   - `ADMIN_USERNAME`, `ADMIN_PASSWORD`: create the admin on first start (ignored if the account exists)
   - `TRUSTED_PROXIES=1`: see the real client IP / HTTPS behind Coolify's proxy
   - `SESSION_COOKIE_SECURE=1`: if you serve it over an HTTPS domain
   - `SECRET_KEY`: optional (otherwise generated and kept on the volume)
5. The health check uses `/healthz` (defined in the Dockerfile).

## Other commands
```bash
flask --app run reset-flags   # regenerate flags for the built-in labs
```

## Environment variables
| Name | Default | Description |
|---|---|---|
| `SECRET_KEY` | auto-generated | Session signing key |
| `DATABASE_URL` | `sqlite:///instance/wargame.db` | Database URL |
| `SITE_NAME` | `最強海巨` | Site name |
| `SUBMIT_RATE_LIMIT` | `10` | Flag submissions allowed per minute |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` when served over HTTPS |
| `TRUSTED_PROXIES` | `0` | Number of reverse proxies in front (`1` on Coolify) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | - | Create an admin on startup |
| `PORT` / `WEB_CONCURRENCY` | `8000` / `2` | Docker port / gunicorn workers |

## Layout
```
wargame/
  __init__.py   app factory, CLI commands
  models.py     User / Challenge / Solve / Submission
  auth.py       sign up / log in
  main.py       challenges, submissions, scoreboard, profiles
  admin.py      admin pages
  labs.py       intentionally vulnerable labs
  seed.py       default challenge set
  templates/  static/
```
