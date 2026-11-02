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
flask --app run s3-script     # print the CloudShell upload script for the S3 lab (see below)
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
| `S3_LAB_BUCKET` | - | Serve "Deleted, Not Gone" from this real S3 bucket instead of memory |
| `S3_LAB_REGION` | `ap-northeast-2` | Region of that bucket |
| `S3_LAB_FLAG` | - | Pin the S3 lab's flag (the bucket is uploaded by hand, so it must not change) |

## Real S3 for "Deleted, Not Gone"
By default the S3 lab runs in memory. To use a real bucket instead:

1. Create the bucket once (use a separate personal AWS account):
   - Block Public Access: keep the two **ACL** options on, turn the two **policy** options off
     (also at the account level)
   - Bucket Versioning: enabled
   - Static website hosting: enabled, index and error document `index.html`
   - Bucket policy (replace `BUCKET`):
     ```json
     {"Version": "2012-10-17", "Statement": [
       {"Sid": "PublicReadObjectsAndVersions", "Effect": "Allow", "Principal": "*",
        "Action": "s3:Get*", "Resource": "arn:aws:s3:::BUCKET/*"},
       {"Sid": "PublicListVersionsOnly", "Effect": "Allow", "Principal": "*",
        "Action": "s3:ListBucketVersions", "Resource": "arn:aws:s3:::BUCKET"}]}
     ```
2. Set `S3_LAB_BUCKET`, `S3_LAB_REGION` and `S3_LAB_FLAG` (e.g. `USG{...}`) and restart.
   The challenge now links to the bucket's website endpoint and the in-memory routes return 404.
   The wargame never writes to AWS, so no access key is needed.
3. Generate the upload script and run it in **AWS CloudShell** (the `>_` icon in the console,
   which uses your console login):
   ```bash
   flask --app run s3-script > upload.sh   # in Coolify: the app's Terminal
   ```
   Paste it into CloudShell (or upload the file and `bash upload.sh`). It empties the bucket first,
   so it's safe to rerun and old flags never linger. Rerun it whenever the flag changes.

Before deleting the bucket, empty it with `flask --app run s3-script --purge-only` the same way
(versioned buckets must be empty to delete).
Requests and transfer on a public bucket are billed to you, so set an AWS Budgets alert.

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
