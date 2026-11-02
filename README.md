# war-usg
바다거임 워게임~! 🌊🚩

Flask로 만든 해킹 워게임(CTF) 플랫폼입니다.

## 기능
- **회원가입 / 로그인** (비밀번호 해시, CSRF 보호, 오픈 리다이렉트 방지)
- **문제 목록** – 분야별 그룹, 난이도 뱃지, 해결 여부 / 해결 인원 표시
- **플래그 제출** – 상수 시간 비교, 1분당 제출 횟수 제한, 🩸 퍼스트 블러드
- **스코어보드 / 유저 프로필** – 동점이면 먼저 도달한 사람이 위
- **관리자 페이지** – 대시보드, 문제 추가·수정·공개 전환·삭제, 유저 관리, 제출 로그
- **내장 실습 문제 8개** – 설치할 때마다 플래그가 랜덤으로 생성됩니다

| 문제 | 분야 | 난이도 | 주제 |
|---|---|---|---|
| Welcome to USG | misc | easy | 플래그 제출 연습 |
| 보이지 않는 메모 | web | easy | HTML 소스 보기 |
| 로봇은 출입금지 | web | easy | robots.txt |
| 이중 암호 | crypto | easy | Base64 + ROT13 |
| 쿠키 몬스터 | web | easy | 서명 없는 쿠키 변조 |
| 남의 메모장 | web | medium | IDOR |
| SQL 로그인 | web | medium | SQL Injection |
| 파일 뷰어 | web | hard | Path Traversal 필터 우회 |

> 실습 문제는 학습용으로 **일부러 취약하게** 만들었지만 서버 자체는 안전하도록 격리되어 있습니다.
> SQLi는 요청마다 새로 만드는 인메모리 DB만 쓰고, 경로 탐색은 실제 디스크가 아닌 가상 파일시스템만 조회합니다.

## 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 관리자 계정 만들기 (비밀번호는 프롬프트로 입력)
flask --app run create-admin admin

# 서버 실행 → http://127.0.0.1:5000
flask --app run run --debug
```

첫 실행 시 `instance/` 폴더에 DB(`wargame.db`)와 시크릿 키가 자동 생성되고 기본 문제가 등록됩니다.

## 그 밖의 명령
```bash
flask --app run reset-flags   # 내장 문제 플래그 재생성
```

## 환경 변수
| 이름 | 기본값 | 설명 |
|---|---|---|
| `SECRET_KEY` | 자동 생성 | 세션 서명 키 |
| `DATABASE_URL` | `sqlite:///instance/wargame.db` | DB 주소 |
| `SITE_NAME` | `USG Wargame` | 사이트 이름 |
| `SUBMIT_RATE_LIMIT` | `10` | 1분당 플래그 제출 허용 횟수 |
| `SESSION_COOKIE_SECURE` | `0` | HTTPS 배포 시 `1` |

## 구조
```
wargame/
  __init__.py   앱 팩토리, CLI 명령
  models.py     User / Challenge / Solve / Submission
  auth.py       회원가입·로그인
  main.py       문제, 제출, 스코어보드, 프로필
  admin.py      관리자 페이지
  labs.py       실습용 취약 문제들
  seed.py       기본 문제 세트
  templates/  static/
```
