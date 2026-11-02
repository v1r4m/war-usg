"""기본 문제 세트. 플래그는 설치할 때마다 랜덤으로 생성되어 저장소에 노출되지 않습니다."""
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
        "스파이가 남긴 암호문을 손에 넣었다.\n"
        "두 번 꼬아 놓았다는 소문이 있는데... 🤔\n\n"
        f"{encoded}\n\n"
        "힌트: 하나는 '=' 로 끝나는 그것, 하나는 알파벳을 13칸 미는 그것."
    )


# (lab_key, title, category, difficulty, points, url, description(flag) -> str)
DEFAULTS = [
    (
        "welcome", "Welcome to USG", "misc", "easy", 10, None,
        lambda f: (
            "워게임에 오신 걸 환영합니다! 🚩\n\n"
            "플래그는 항상 USG{...} 형식입니다.\n"
            "아래 플래그를 그대로 제출해 보세요.\n\n"
            f"{f}"
        ),
    ),
    (
        "hidden", "보이지 않는 메모", "web", "easy", 50, "/labs/hidden",
        lambda f: "개발자가 페이지에 뭔가를 남기고 깜빡한 것 같다.\n화면에 보이는 게 전부일까?",
    ),
    (
        "robots", "로봇은 출입금지", "web", "easy", 100, "/labs/robots/",
        lambda f: "검색 엔진 로봇에게만 몰래 알려준 길이 있다고 한다.",
    ),
    (
        "cookie", "쿠키 몬스터", "web", "easy", 150, "/labs/cookie",
        lambda f: "관리자만 플래그를 볼 수 있다.\n그런데 내가 누구인지는 어디에 저장되어 있을까? 🍪",
    ),
    (
        "idor", "남의 메모장", "web", "medium", 200, "/labs/idor/",
        lambda f: "내 메모만 볼 수 있는 안전한 메모장... 정말 그럴까?",
    ),
    (
        "sqli", "SQL 로그인", "web", "medium", 250, "/labs/sqli",
        lambda f: (
            "관리자(admin) 계정으로 로그인하면 플래그를 준다.\n"
            "비밀번호는 매번 랜덤이라 알아낼 수 없다. 그렇다면...?"
        ),
    ),
    (
        "traversal", "파일 뷰어", "web", "hard", 300, "/labs/files?name=welcome.txt",
        lambda f: (
            "공개 폴더의 파일만 보여주는 뷰어.\n"
            "개발자는 '../' 를 막았으니 안전하다고 자신한다.\n"
            "플래그는 /srv/secret/flag.txt 에 있다."
        ),
    ),
    (
        "crypto", "이중 암호", "crypto", "easy", 100, None,
        _crypto_desc,
    ),
]


def seed_challenges():
    """아직 없는 기본 문제만 추가 (이미 있으면 건드리지 않음)."""
    existing = {c.lab_key for c in Challenge.query.filter(Challenge.lab_key.isnot(None))}
    added = 0
    for key, title, cat, diff, pts, url, desc in DEFAULTS:
        if key in existing:
            continue
        flag = make_flag(key)
        db.session.add(Challenge(
            lab_key=key, title=title, category=cat, difficulty=diff, points=pts,
            url=url, flag=flag, description=desc(flag), visible=True,
        ))
        added += 1
    if added:
        db.session.commit()
    return added


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
