"""Default challenge set. Flags are randomly generated per install, so they never live in the repo."""
import base64
import codecs
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
            flag = make_flag(key)
            db.session.add(Challenge(
                lab_key=key, title=title, category=cat, difficulty=diff, points=pts,
                url=url, flag=flag, description=desc(flag), visible=True,
            ))
            changed += 1
        elif chal.title == LEGACY_TITLES.get(key) and chal.description != desc(chal.flag):
            # Only touch the text if it still looks like the shipped Korean default
            if any("가" <= ch <= "힣" for ch in chal.title + chal.description):
                chal.title = title
                chal.description = desc(chal.flag)
                changed += 1
    if changed:
        db.session.commit()
    return changed


def regenerate_lab_flags():
    descs = {key: desc for key, *_rest, desc in DEFAULTS}
    n = 0
    for chal in Challenge.query.filter(Challenge.lab_key.isnot(None)):
        if chal.lab_key not in descs:
            continue
        chal.flag = make_flag(chal.lab_key)
        chal.description = descs[chal.lab_key](chal.flag)
        n += 1
    db.session.commit()
    return n
