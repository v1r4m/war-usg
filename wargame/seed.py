"""Default challenge set. Flags are randomly generated per install, so they never live in the repo."""
import base64
import codecs
import os
import secrets

from .extensions import db
from .models import Challenge


def make_flag(slug):
    return f"USG{{{slug}_{secrets.token_hex(6)}}}"


def _crypto_desc(flag):
    encoded = base64.b64encode(codecs.encode(flag, "rot13").encode()).decode()
    return (
        "We intercepted a message left behind by a spy.\n"
        "Rumor says it was scrambled twice... 🤔\n\n"
        f"{encoded}\n\n"
        "Hint: one of them ends with '=', the other shifts the alphabet by 13."
    )


def _s3_desc(flag):
    from .s3lab import bucket_name

    where = (
        "This is a real S3 bucket, so the AWS CLI works too (no account needed: --no-sign-request)."
        if bucket_name() else
        "(The bucket is simulated inside the wargame. No AWS account needed.)"
    )
    return (
        "Ocean Corp moved its employee portal to S3 static website hosting.\n"
        "Last month an incident report went up by mistake, but the security team says\n"
        "\"we deleted it right away, so it's fine.\"\n\n"
        "Is it really gone? 🪣\n\n"
        f"{where}"
    )


_BAEKJOON_RULES = (
    "Write def f(arr) that sorts the first N cells of arr in place.\n"
    "You only get arr[i] reads/writes, integer arithmetic and bit ops, comparisons, if and while,\n"
    "and every one of them costs a cycle."
)


def _supplychain_desc(flag):
    return (
        "Ladies and Gentelmen, we proudly introduce our web calculator."
    )


def _baekjoon_desc(flag):
    return (
        "A classic online-judge problem: sort an array. 📝\n\n"
        f"{_BAEKJOON_RULES}\n\n"
        "N = 4096 64-bit integers, and the cycle budget is tight.\n"
        "Quicksort, heapsort, merge sort, radix sort... the judge has seen them all.\n"
        "Get Accepted and the judge hands you the flag."
    )


def _baekjoon_revenge_desc(flag):
    return (
        "The judge is back, and this time N = 65536. 😈\n\n"
        f"{_BAEKJOON_RULES}\n\n"
        "Even reading every element once barely fits in the budget.\n"
        "Honest sorting won't get you there. Maybe the judge itself will."
    )


# Challenges whose server runs in its own container (see challenges/). The wargame only links to
# them, so the URL and flag come from the environment and must match what that container serves.
EXTERNAL = {
    "baekjoon": ("BAEKJOON_URL", "BAEKJOON_FLAG"),
    "baekjoon_revenge": ("BAEKJOON_REVENGE_URL", "BAEKJOON_REVENGE_FLAG"),
}

# Credits shown next to the title. Filled in when empty, so an admin's edit wins.
AUTHORS = {
    "s3versions": "GoldenFall",
    "supplychain": "viram",
    "baekjoon": "viram",
    "baekjoon_revenge": "viram",
}


def _env(name):
    return (os.environ.get(name) or "").strip() or None


# (lab_key, title, category, difficulty, points, url, description(flag) -> str)
DEFAULTS = [
    (
        "welcome", "Welcome to USG", "misc", "easy", 10, None,
        lambda f: (
            "Welcome to the wargame! 🚩\n\n"
            "Flags always look like USG{...}.\n"
            "Submit the flag below as-is to get started.\n\n"
            f"{f}"
        ),
    ),
    (
        "hidden", "Invisible Note", "web", "easy", 50, "/labs/hidden",
        lambda f: "Looks like the developer left something on the page and forgot about it.\nIs what you see really all there is?",
    ),
    (
        "robots", "No Robots Allowed", "web", "easy", 100, "/labs/robots/",
        lambda f: "Rumor has it there's a path they only told the search engine robots about.",
    ),
    (
        "cookie", "Cookie Monster", "web", "easy", 150, "/labs/cookie",
        lambda f: "Only admins can see the flag.\nBut where does the site keep track of who you are? 🍪",
    ),
    (
        "idor", "Someone Else's Notes", "web", "medium", 200, "/labs/idor/",
        lambda f: "A safe note app where you can only read your own notes... or can you?",
    ),
    (
        "sqli", "SQL Login", "web", "medium", 250, "/labs/sqli",
        lambda f: (
            "Log in as admin and you get the flag.\n"
            "The password is random every time, so you can't guess it. So then...?"
        ),
    ),
    (
        "traversal", "File Viewer", "web", "hard", 300, "/labs/files?name=welcome.txt",
        lambda f: (
            "A viewer that only shows files from the public folder.\n"
            "The developer blocked '../' and is confident it's safe now.\n"
            "The flag is at /srv/secret/flag.txt."
        ),
    ),
    (
        "crypto", "Double Cipher", "crypto", "easy", 100, None,
        _crypto_desc,
    ),
    (
        "s3versions", "Deleted, Not Gone", "cloud", "medium", 200, "/labs/s3web/",
        _s3_desc,
    ),
    (
        "supplychain", "web calc", "misc", "medium", 250, "/labs/calc/",
        _supplychain_desc,
    ),
    (
        "baekjoon", "baekjoon", "misc", "hard", 400, None,
        _baekjoon_desc,
    ),
    (
        "baekjoon_revenge", "baekjoon revenge", "misc", "hard", 350, None,
        _baekjoon_revenge_desc,
    ),
]

# Earlier versions shipped Korean titles. Built-in challenges still carrying one of these
# (i.e. never edited by an admin) are upgraded to the English text on startup.
LEGACY_TITLES = {
    "welcome": "Welcome to USG",
    "hidden": "보이지 않는 메모",
    "robots": "로봇은 출입금지",
    "cookie": "쿠키 몬스터",
    "idor": "남의 메모장",
    "sqli": "SQL 로그인",
    "traversal": "파일 뷰어",
    "crypto": "이중 암호",
}


def seed_challenges():
    """Add any missing default challenges and upgrade untouched legacy (Korean) ones."""
    existing = {c.lab_key: c for c in Challenge.query.filter(Challenge.lab_key.isnot(None))}
    changed = 0
    for key, title, cat, diff, pts, url, desc in DEFAULTS:
        chal = existing.get(key)
        if chal is None:
            flag = _pinned_flag(key) or make_flag(key)
            if key in EXTERNAL:
                url = _env(EXTERNAL[key][0])
            db.session.add(Challenge(
                lab_key=key, title=title, category=cat, difficulty=diff, points=pts,
                url=url, flag=flag, description=desc(flag), author=AUTHORS.get(key),
                # an external challenge stays hidden until its server is configured
                visible=key not in EXTERNAL or url is not None,
            ))
            changed += 1
            continue
        if chal.author is None and key in AUTHORS:
            chal.author = AUTHORS[key]
            changed += 1
        if key == "supplychain":
            # Keep the flag matching whatever the published litexpr artifact reveals.
            pinned = _pinned_flag("supplychain")
            if pinned and chal.flag != pinned:
                chal.flag = pinned
                chal.description = desc(pinned)
                changed += 1
        if chal.title == LEGACY_TITLES.get(key) and chal.description != desc(chal.flag):
            # Only touch the text if it still looks like the shipped Korean default
            if any("가" <= ch <= "힣" for ch in chal.title + chal.description):
                chal.title = title
                chal.description = desc(chal.flag)
                changed += 1
    changed += _sync_s3_challenge()
    changed += _sync_external_challenges()
    if changed:
        db.session.commit()
    return changed


def _pinned_flag(lab_key):
    """Flags that live outside the wargame are pinned from the environment:
    S3_LAB_FLAG for the hand-uploaded bucket, *_FLAG for the external containers."""
    from .s3lab import LAB_KEY, fixed_flag

    if lab_key == LAB_KEY:
        return fixed_flag()
    if lab_key in EXTERNAL:
        return _env(EXTERNAL[lab_key][1])
    if lab_key == "supplychain":
        # The flag is baked into the published litexpr artifact, so it is fixed: the
        # challenge must accept exactly what the package reveals. Env can override it.
        from .calclab import FLAG as _supplychain_flag
        return _env("SUPPLYCHAIN_FLAG") or _supplychain_flag
    return None


def _sync_external_challenges():
    """Apply *_URL / *_FLAG to the external challenges. The environment wins when set.
    A challenge that was hidden for lack of a server is shown once its URL appears."""
    changed = 0
    for key, (url_var, _flag_var) in EXTERNAL.items():
        chal = Challenge.query.filter_by(lab_key=key).first()
        if chal is None:
            continue
        url, flag = _env(url_var), _pinned_flag(key)
        if url and chal.url != url:
            if chal.url is None:
                chal.visible = True
            chal.url = url
            changed += 1
        if flag and chal.flag != flag:
            chal.flag = flag
            changed += 1
    return changed


def _sync_s3_challenge():
    """Point the S3 lab at the real bucket when S3_LAB_BUCKET is set, or back at the in-memory one,
    and apply S3_LAB_FLAG. Only touches a link that is still one of the two defaults, so admin edits survive."""
    from .s3lab import LAB_KEY, bucket_name, website_url

    chal = Challenge.query.filter_by(lab_key=LAB_KEY).first()
    if chal is None:
        return 0
    changed = 0
    pinned = _pinned_flag(LAB_KEY)
    if pinned and chal.flag != pinned:
        chal.flag = pinned
        changed = 1
    memory_url = "/labs/s3web/"
    want = website_url() if bucket_name() else memory_url
    if chal.url != want and (chal.url == memory_url or (chal.url or "").endswith(".amazonaws.com/")):
        chal.url = want
        changed = 1
    if changed:
        chal.description = _s3_desc(chal.flag)
    return changed


def regenerate_lab_flags():
    descs = {key: desc for key, *_rest, desc in DEFAULTS}
    n = 0
    for chal in Challenge.query.filter(Challenge.lab_key.isnot(None)):
        if chal.lab_key not in descs:
            continue
        if chal.lab_key in EXTERNAL and not _pinned_flag(chal.lab_key):
            continue  # the flag lives in another container; a new random one would never match
        chal.flag = _pinned_flag(chal.lab_key) or make_flag(chal.lab_key)
        chal.description = descs[chal.lab_key](chal.flag)
        n += 1
    db.session.commit()
    return n
