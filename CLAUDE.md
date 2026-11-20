# CLAUDE.md

AI 코딩 도구(Claude Code, Cursor, Copilot 등)가 이 저장소에서 작업할 때 따르는 규칙이다.
**두 사람이 같은 규칙을 쓰도록 이 파일을 함께 관리한다.** 규칙을 바꿀 때는 PR로 바꾼다.

## 프로젝트

- GDGoC 팀 1234 백엔드. 백엔드 개발자 2명이 함께 작업한다.
- 스택: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0(async), Alembic, PostgreSQL
- 패키지 관리: `uv` (`pip install`을 직접 쓰지 않는다)
- 인증: Firebase Authentication(Google 로그인). 백엔드는 비밀번호를 다루지 않고, 프론트가 보낸 ID 토큰만 검증한다 (`app/auth/`)

## 자주 쓰는 명령

```bash
uv sync                                   # 의존성 설치
uv run fastapi dev app/main.py            # 개발 서버 (http://127.0.0.1:8000/docs)
uv run pytest                             # 테스트
uv run ruff check --fix . && uv run ruff format .   # 린트 + 포맷
uv run alembic revision --autogenerate -m "설명"     # 마이그레이션 생성
uv run alembic upgrade head               # 마이그레이션 적용
docker compose up -d db                   # 로컬 PostgreSQL
```

## 폴더 구조 (프로그램 단위)

서비스의 메인은 AI 채팅이고, 길안내 같은 기능은 채팅이 부르는 프로그램(skill)이다.
**프로그램 하나 = 폴더 하나**로 `app/programs/` 아래에 둔다.

```
app/
├── main.py            # FastAPI 앱 생성, 라우터 등록만 한다
├── core/              # 설정(config.py), DB 세션(database.py), 보안(security.py) — 공용
├── common/            # 공용 예외, 응답 형식, 유틸
├── auth/              # 로그인, 사용자
├── chat/              # 채팅 창구, 대화 기록, AI 서비스 호출
└── programs/          # 채팅이 부르는 프로그램(skill)
    ├── registry.py        # @tool 데코레이터, 프로그램 목록(PROGRAM_MODULES)
    ├── schemas.py         # tool 결과(ToolOk 등), skills API 모델
    ├── result_store.py    # 화면용 결과(ui) 보관
    ├── service.py, router.py, dependencies.py   # /api/v1/skills
    └── <프로그램>/     # 예: navigation(길안내), cafeteria(학식)
        ├── tools.py       # @tool 함수. LLM이 부르는 입구, service.py를 부른다
        ├── router.py      # 엔드포인트. 요청/응답 처리만 한다
        ├── schemas.py     # Pydantic 요청/응답 모델
        ├── models.py      # SQLAlchemy 모델
        ├── service.py     # 비즈니스 로직
        └── repository.py  # DB 접근
tests/
├── auth/, chat/
└── programs/<프로그램>/
migrations/            # Alembic
prototype/             # 길안내 검증용 구현. navigation 이전이 끝나면 지운다 (ruff 검사 제외)
```

- `auth/`, `chat/`도 프로그램 폴더와 같은 파일 구성(router, schemas, models, service, repository)을 따른다.
- 한 프로그램 안의 기능은 쪼개지 않는다. 예: 건물 정보는 별도 프로그램이 아니라 `navigation/` 안에 둔다.
- 다른 프로그램의 router, repository, models를 import하지 않는다. 필요하면 그 프로그램의 `service.py` 함수만 쓴다.
- 새 프로그램은 `tools.py`에 `@tool` 함수를 만들고 `app/programs/registry.py`의 `PROGRAM_MODULES`에 한 줄 추가한다. tool 이름은 `<프로그램>_<기능>` (예: `cafeteria_get_menu`).

## 코드 규칙

- 계층 방향: `router → service → repository`. router에서 DB에 직접 접근하지 않는다.
- 요청/응답에는 항상 Pydantic 스키마를 쓴다. SQLAlchemy 모델을 그대로 반환하지 않는다.
- 엔드포인트 경로: `/api/v1/<복수형 리소스>` (예: `/api/v1/users/{user_id}`)
- 모든 엔드포인트에 `response_model`, `status_code`, `tags`를 지정한다.
- 에러는 `app/common/exceptions.py`의 공용 예외를 사용한다. 응답 형식을 임의로 만들지 않는다.
- 설정값과 비밀값은 `app/core/config.py`(pydantic-settings)를 통해 `.env`에서 읽는다. 코드에 하드코딩하지 않는다.
- DB I/O는 `async`로 작성한다.
- 타입 힌트를 모두 단다. 이름: 변수·함수 `snake_case`, 클래스 `PascalCase`.
- 새 기능에는 `tests/`에 테스트를 함께 추가한다.

## AI가 지켜야 할 것 (충돌 방지)

- **작업 범위 밖의 파일을 고치지 않는다.** 특히 다른 프로그램 폴더, `app/core/`, `app/common/`은 요청이 없으면 건드리지 않는다.
- 공용 파일(`app/main.py`, `app/core/*`, `pyproject.toml`, `uv.lock`, `migrations/`)을 바꿔야 하면 바꾸기 전에 사용자에게 알린다.
- 대규모 리포맷, 파일 이동, 이름 변경을 임의로 하지 않는다.
- 패키지는 `uv add <패키지>`로만 추가하고, 추가한 이유를 사용자에게 알린다.
- 마이그레이션 파일을 생성했다면 사용자에게 알린다. 기존 마이그레이션 파일은 수정하지 않는다.
- `.env`, 비밀값, 토큰을 커밋하거나 출력하지 않는다. 새 환경변수는 `.env.example`에 추가한다.
- 커밋 메시지는 아래 컨벤션을 따른다.
## Git 컨벤션

- 브랜치: `feat/<도메인>-<내용>`, `fix/...`, `chore/...`, `refactor/...`, `docs/...`
- 커밋: `<type>: <한글 설명>` (예: `feat: 회원가입 API 추가`)
  - type: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`
- `main`에 직접 push하지 않는다. 항상 PR → 상대방 리뷰 → Squash merge.
