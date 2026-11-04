# war-usg
The 最強海巨 (Ultimate Sea Giant) wargame 🌊🚩

A hacking wargame (CTF) platform built with Flask.

## Features
- **Sign up / log in**: hashed passwords, CSRF protection, open-redirect protection
- **Challenge list**: grouped by category, with difficulty, solved state, and solve counts
- **Flag submission**: constant-time comparison, per-minute rate limit, first blood
- **Scoreboard / user profiles**: ties go to whoever got there first
- **Admin pages**: dashboard, create / edit / hide / delete challenges, user management, submission log
- **Credits**: each challenge can name its author, shown on the list and the challenge page
- **Slash intro**: the team artwork waves like a flag on the home page; drag (or click) to slice it open
- **12 built-in challenges**: flags are randomly generated on every install (except the externally hosted ones)

| Challenge | Category | Difficulty | Topic | Author |
|---|---|---|---|---|
| Welcome to USG | misc | easy | Submitting a flag | |
| Invisible Note | web | easy | Viewing page source | |
| No Robots Allowed | web | easy | robots.txt | |
| Double Cipher | crypto | easy | Base64 + ROT13 | |
| Cookie Monster | web | easy | Unsigned cookie tampering | |
| Someone Else's Notes | web | medium | IDOR | |
| SQL Login | web | medium | SQL injection | |
| File Viewer | web | hard | Path traversal filter bypass | |
| Deleted, Not Gone | cloud | medium | S3 versioning (delete markers, `ListBucketVersions`) | GoldenFall |
| web calc | misc | medium | A PyPI dependency whose published artifact differs from its source (same version, xz-style) | v1r4m |
| baekjoon | misc | hard | Sorting under a cycle budget | viram |
| baekjoon revenge | misc | hard | The same judge, N = 65536 | viram |

> The labs are **intentionally vulnerable** for learning, but isolated so the server itself stays safe.
> SQLi only touches a fresh in-memory DB per request, path traversal reads from a virtual filesystem, never the real disk, the S3 lab imitates a bucket in memory without touching AWS, and the supply-chain lab's dependency (`litexpr`) carries a backdoor that only ever returns one fixed constant string — it reads no environment, opens no network, and runs no code, so it is safe to install on the server.
> The baekjoon judges run players' code, so they live in their own containers (`challenges/`), never inside the wargame.

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
| `SUPPLYCHAIN_FLAG` | baked into litexpr | Override "Just a Patch Release" flag (must match the published litexpr artifact) |
| `BAEKJOON_URL` / `BAEKJOON_FLAG` | - | Link and flag of the baekjoon judge (hidden until the URL is set) |
| `BAEKJOON_REVENGE_URL` / `BAEKJOON_REVENGE_FLAG` | - | Same for baekjoon revenge |

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

## "web calc" (supply-chain lab)

USG Calc (`/labs/calc/`) evaluates expressions with the PyPI package **`litexpr`**. The clean
source lives at [`github.com/v1r4m/litexpr`](https://github.com/v1r4m/litexpr), but the artifact
published to PyPI at the **same version (1.4.1)** smuggles a hidden branch into `evaluate()`:
`litexpr.evaluate("_diag(1337)")` returns the flag. So the calculator server leaks it for one
magic input — the lesson is that the published artifact need not match its source (à la xz-utils).

The backdoor only returns a fixed constant (no env/network/exec), so it is safe to run. For the
challenge to be solvable, the server must install that artifact:

```bash
pip install litexpr==1.4.1   # the backdoored build; the flag is baked in
```

The flag is therefore fixed. `SUPPLYCHAIN_FLAG` can override what the wargame accepts if you
rebuild the package with a different flag. The backdoored artifact is produced from the clean
checkout by the release kit (kept out of the public repo), not committed here.

## baekjoon judges (separate containers)
`challenges/baekjoon` and `challenges/baekjoon-revenge` are small Flask judges that run the
submitted code, so each one is deployed as its **own** Coolify resource, away from the wargame's DB.
The revenge is meant to be escaped, so treat that container as owned by the players.

1. New resource → same GitHub repo → Build Pack: **Dockerfile**,
   Base Directory `/challenges/baekjoon` (or `/challenges/baekjoon-revenge`), Ports Exposes `8000`
2. Environment variable `FLAG=USG{...}` on the judge (no storage needed)
3. On the wargame, set `BAEKJOON_URL` to the judge's public URL and `BAEKJOON_FLAG` to the same flag
   (`BAEKJOON_REVENGE_URL` / `BAEKJOON_REVENGE_FLAG` for the revenge), then redeploy.
   The challenge shows up once its URL is set; the environment always wins over admin edits.

Run one locally:
```bash
docker build -t usg-baekjoon challenges/baekjoon
docker run --rm -p 8001:8000 -e FLAG='USG{test}' usg-baekjoon   # → http://localhost:8001
```

## Layout
```
wargame/
  __init__.py   app factory, CLI commands
  models.py     User / Challenge / Solve / Submission
  auth.py       sign up / log in
  main.py       challenges, submissions, scoreboard, profiles
  admin.py      admin pages
  labs.py       intentionally vulnerable labs
  calclab.py    "Just a Patch Release" calculator (uses the litexpr dependency)
  seed.py       default challenge set
  templates/  static/
challenges/
  baekjoon/          judge for "baekjoon" (own container)
  baekjoon-revenge/  judge for "baekjoon revenge" (own container)
```
