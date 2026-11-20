# skill 공통 틀 설계

- 작성일: 2026-11-18 (2026-11-19 수정: PR #9의 공용 코드에 맞춤, tool 이름 규칙 변경)
- 상태: 초안 (사용자 승인 전)
- 범위: 채팅이 부르는 프로그램(skill)의 공통 틀. 정의, 등록, 목록·실행 API, 화면용 결과 보관
- 관련 문서: 저장소 밖 `작업정리.md`, `필수작업.md` (5-2. skill 공통 틀), 위키 `docs/guides/가이드_총관리자.md` 4장

---

## 1. 왜 만드는가

서비스의 메인은 AI 채팅이다. 길안내, 학식 같은 기능은 채팅이 부르는 프로그램(skill)이다.
AI 파트가 LLM으로 "어떤 tool을 어떤 값으로 부를지" 고르고, 백엔드가 그 tool을 실행한다.
위키의 원칙(경로 계산 같은 정확한 일은 서버가 하고, AI는 tool을 골라 설명한다. AI 기능은 새 API로 붙인다)을 그대로 따른다.

이 틀이 있어야 프로그램을 붙일 수 있다. 첫 사용처는 학식(`cafeteria`), 다음은 길안내(`navigation`) 이전이다.
나중에 같은 tool 정의를 MCP 서버로도 공개할 수 있게 한다 (개인 AI 연동 아이디어).

## 2. 목표 / 하지 않는 것 / 실패로 보는 것

**목표**
- 프로그램 개발자가 함수 하나와 입력 모델 하나로 tool을 추가할 수 있다.
- AI 서비스가 `GET /api/v1/skills`로 tool 목록(이름, 설명, 입력 JSON Schema)을 받고, `POST /api/v1/skills/{name}/invoke`로 실행한다.
- 실행 결과는 `llm`(AI에 주는 내용)과 `ui`(화면용 데이터)로 나뉜다. AI에는 `llm`과 `resultId`만 준다.
- `ui`는 백엔드가 `resultId`로 잠시 보관하고, 나중에 채팅 창구가 꺼내 쓴다.

**하지 않는 것 (이번 범위 밖)**
- 채팅 창구(`POST /api/v1/chat`), 대화 기록 DB, 스트리밍
- 학식, 길안내 tool 자체 (이 틀 위에 따로 만든다)
- `ui` DB 보관 (DB는 PR #9로 생겼지만, `ui`를 꺼내 쓰는 채팅 창구가 아직 없다. 채팅 창구 작업 때 바꾼다)
- MCP 서버 공개
- 사용자 로그인 연동. invoke는 AI 서비스만 부른다 (Firebase 로그인은 프론트↔백엔드용)

**실패로 보는 것**
- 프로그램을 하나 추가할 때 틀 코드(`registry.py`, router 등)를 여러 군데 고쳐야 한다.
- 입력 JSON Schema가 실제 코드와 따로 놀아 AI가 잘못된 값을 보낸다.
- tool 이름이 LLM API 규칙에 맞지 않아 AI 파트가 이름을 바꿔 써야 한다.
- tool 하나가 멈추거나 예외를 내서 서버 전체 응답이 막힌다.
- 프론트용 `ui` 데이터(좌표, 이미지 주소 등)가 AI 쪽으로 새어 나가 토큰을 낭비한다.

## 3. 제약

- 스택과 규칙: CLAUDE.md (계층 방향, `response_model`·`status_code`·`tags`, 공용 예외, 설정은 `.env`).
- **PR #9(팀원)의 공용 코드를 따른다.**
  - 공용 예외: `app/common/exceptions.py`의 `AppException(status_code, code, message)`와 자식 예외. 응답 `{"error": {"code", "message"}}`. 요청 검증 실패는 **400** `VALIDATION_ERROR`.
  - API 스키마: `app/common/schemas.py`의 `CamelModel`을 상속해 **JSON 필드는 camelCase**로 낸다. 목록 응답은 `ItemsResponse[T]` = `{"items": [...]}`.
  - 설정: `app/core/config.py`의 `Settings`에 필드를 추가한다. `main.py`가 import 시점에 `get_settings()`를 부르므로 **새 필드는 모두 기본값이 있어야 한다.**
  - 테스트: `tests/conftest.py`의 `settings`, `client`(httpx `AsyncClient`) fixture와 anyio를 쓴다.
- `ui` 보관은 메모리. **Cloud Run 최대 인스턴스가 2**(`deploy.yml`)라서, 채팅 창구가 붙으면 다른 인스턴스에 저장된 `ui`를 못 찾을 수 있다. 채팅 창구 작업 전에 DB 보관으로 바꾸거나 최대 인스턴스를 1로 줄인다.
- 공용 파일을 건드린다: `app/main.py`, `app/core/config.py`, `app/common/exceptions.py`, `.env.example`, `CLAUDE.md`. PR 설명에 적는다. 새 패키지는 없다 (`pydantic-settings`는 PR #9에 이미 있다).

## 4. 고려한 방식

| 방식 | 장점 | 단점 |
|---|---|---|
| **A. 함수 + `@tool` 데코레이터 (선택)** | 코드가 가장 짧다. FastAPI 라우터와 쓰는 느낌이 비슷하다. 입력 모델에서 JSON Schema 자동 생성 | 데코레이터가 import 시점에 등록되므로 `registry.py`에 프로그램 모듈 import 한 줄이 필요하다 |
| B. tool마다 클래스 (`class GetMenuTool(Tool)`) | 구조가 명확하고 공통 동작을 부모 클래스에 넣기 쉽다 | tool마다 적는 코드가 많다 |
| C. MCP 라이브러리(FastMCP)를 틀로 사용 | 나중에 MCP 공개가 바로 된다 | `llm`/`ui` 분리, `need_clarification`, `resultId`가 MCP에 없어 그 위에 틀을 또 얹어야 한다. AI 파트의 HTTP 호출과 따로 논다. MCP는 아직 다음 목표 |

사용자가 A를 골랐다. A의 tool 정의(이름, 설명, 입력 JSON Schema)는 MCP tool 형식과 같아서 나중에 C로 넘어가기 쉽다.

`ui` 보관 방식도 사용자가 골랐다: **메모리 보관으로 시작, DB는 나중에.**

## 5. 설계

### 5-1. 파일 구성

```
app/
├── main.py                    # (수정) skills 라우터 등록, lifespan에서 tool 불러오기
├── core/config.py             # (수정) Settings에 필드 4개 추가
├── common/exceptions.py       # (수정) NotFoundException 추가
└── programs/
    ├── registry.py            # @tool 데코레이터, ToolRegistry, 프로그램 목록
    ├── schemas.py             # ToolOk / ToolNeedClarification / ToolError, API 요청·응답 모델
    ├── result_store.py        # ResultStore(Protocol) + MemoryResultStore
    ├── service.py             # list_tools, invoke_tool, get_ui_result
    ├── router.py              # GET /api/v1/skills, POST /api/v1/skills/{name}/invoke
    ├── dependencies.py        # 서비스 키 검사, registry·store 의존성
    └── <프로그램>/tools.py     # 각 프로그램의 @tool 함수 (service.py를 부른다)
tests/programs/
├── test_registry.py
├── test_result_store.py
└── test_skills_api.py
```

- `programs/` 바로 아래 파일은 틀 코드다. 프로그램 폴더 안의 파일 구성(router, schemas, service ...)은 CLAUDE.md 그대로이고, `tools.py`가 하나 추가된다.
- 계층: `router → service → (registry, result_store)`.

### 5-2. tool 정의

```python
# app/programs/cafeteria/tools.py (예시)
from pydantic import BaseModel, Field
from app.programs.registry import tool
from app.programs.schemas import ToolOk


class GetMenuInput(BaseModel):
    date: str | None = Field(None, description="YYYY-MM-DD. 없으면 오늘")
    cafeteria: str | None = Field(None, description="식당 이름. 예: 상록원3층식당")


@tool(name="cafeteria_get_menu", description="동국대 학식 메뉴를 조회한다", timeout=10)
async def get_menu(args: GetMenuInput) -> ToolOk:
    ...
    return ToolOk(llm={...}, ui={...})
```

- **이름 형식: `<프로그램>_<기능>`**, 정규식 `^[a-z][a-z0-9]*(_[a-z0-9]+)+$`, 64자 이하. 어기면 시작 시 에러.
  - 처음엔 `cafeteria.get_menu`(점)였으나 바꿨다. OpenAI·Claude의 tool 이름은 영문·숫자·`_`·`-`만 허용(`^[a-zA-Z0-9_-]{1,64}$`)해서 점이 들어가면 AI 파트가 LLM에 그대로 넘길 수 없다. 밑줄 형식은 위키 예시(`find_route`)와도 같다.
  - 앞부분이 프로그램 폴더 이름이다 (`cafeteria_...` → `app/programs/cafeteria/`). 정규식으로는 검사하지 않고 규칙으로 지킨다.
- 함수는 `async def`, 인자는 Pydantic 모델 하나. 입력 모델은 데코레이터가 타입 힌트에서 읽는다.
- 입력 모델은 `CamelModel`이 아니라 `BaseModel`을 쓴다. LLM이 보는 JSON Schema의 필드 이름을 파이썬 이름 그대로 두기 위해서다.
- `description`과 입력 필드의 `Field(description=...)`는 LLM이 읽는다.
- `timeout`(초)은 선택, 기본값은 설정 `TOOL_TIMEOUT_SECONDS`(10).
- 같은 이름을 두 번 등록하면 시작 시 에러.

### 5-3. tool 결과

tool 함수는 아래 둘 중 하나를 반환하거나 `ToolError`를 던진다.

| 결과 | 필드 | 뜻 |
|---|---|---|
| `ToolOk` | `llm: dict`, `ui: dict \| None` | 성공. `llm`은 AI가 답변 문장에 쓸 내용(짧게), `ui`는 프론트 카드용 |
| `ToolNeedClarification` | `field: str`, `message: str`, `candidates: list[Candidate]` | 입력이 애매하다. `Candidate = {value, label, description?}`. 되묻는 문장은 AI가 쓴다 |
| `raise ToolError(code, message)` | | 예상된 실패. 예: `MENU_NOT_FOUND`, `SOURCE_UNAVAILABLE` |

### 5-4. API

두 엔드포인트 모두 AI 서비스만 부른다. 헤더 `X-Service-Key`가 설정값 `SERVICE_API_KEY`와 같아야 한다 (`secrets.compare_digest`, 바이트로 비교). 다르거나 없으면 401. **서버의 `SERVICE_API_KEY`가 비어 있으면 모든 요청을 401로 거부한다.**

JSON 필드 이름은 팀 규칙대로 camelCase다.

**`GET /api/v1/skills`** → 200

```json
{
  "items": [
    {
      "name": "cafeteria_get_menu",
      "description": "동국대 학식 메뉴를 조회한다",
      "inputSchema": { "type": "object", "properties": { ... } }
    }
  ]
}
```

**`POST /api/v1/skills/{name}/invoke`**

요청:
```json
{ "arguments": { "date": "2026-11-18" } }
```
요청 본문을 객체로 둔 것은 나중에 `context`(사용자, 대화 ID)를 더하기 위해서다.

응답 (tool 수준의 결과는 모두 200, `status`로 구분):
```json
{ "status": "ok", "llm": { ... }, "resultId": "r_3f9c..." }
{ "status": "need_clarification", "field": "cafeteria", "message": "...", "candidates": [ ... ] }
{ "status": "error", "error": { "code": "MENU_NOT_FOUND", "message": "..." } }
```
- `ok`에서 `ui`가 있을 때만 `resultId`를 만든다. 없으면 `null`. `ui` 자체는 응답에 넣지 않는다.
- `error`는 `{code, message, details?}`이다.
- 입력 검증 실패도 200 + `status: "error"`, `code: "INVALID_ARGUMENTS"`로 준다. `error.details`에 Pydantic 에러 목록(`loc`, `msg`, `type`)을 넣어 LLM이 고쳐서 다시 부를 수 있게 한다.
- 시간 초과는 `TOOL_TIMEOUT`, tool 안의 예상 못 한 예외와 잘못된 반환값은 `TOOL_FAILED` (로그에 남기고 응답에는 내부 내용을 넣지 않는다).
- `llm` 안의 내용은 각 프로그램이 정한다 (camelCase 변환 대상 아님).

HTTP 에러 (공용 에러 형식):
| 상황 | 상태 코드 | code |
|---|---|---|
| 서비스 키 없음·틀림, 서버 키 미설정 | 401 | `UNAUTHORIZED` |
| 없는 tool 이름 | 404 | `TOOL_NOT_FOUND` |
| 요청 본문 형식 자체가 틀림 (`arguments`가 객체가 아님 등) | 400 | `VALIDATION_ERROR` |

### 5-5. 화면용 결과 보관

```python
class ResultStore(Protocol):
    async def put(self, tool_name: str, ui: dict) -> str: ...  # result_id 반환
    async def get(self, result_id: str) -> StoredResult | None: ...  # 만료됐거나 없으면 None
```

- `MemoryResultStore`: dict + 만료 시간. `RESULT_TTL_SECONDS`(기본 1800 = 30분), 최대 `RESULT_STORE_MAX_ITEMS`(기본 1000)개. `put`할 때 만료된 것을 지우고, 그래도 넘치면 오래된 것부터 지운다.
- `result_id`: `"r_" + uuid4().hex`.
- 앱 전체에서 store 하나를 쓴다 (`dependencies.py`가 `lru_cache`로 제공). 테스트는 의존성 교체로 새 store를 쓴다.
- 꺼내는 쪽은 HTTP가 아니라 `service.get_ui_result(store, result_id)` 함수다. 나중에 채팅 창구가 부른다.
- DB로 바꿀 때는 같은 Protocol을 따르는 `DbResultStore`를 만들고 의존성만 바꾼다 (3장 Cloud Run 인스턴스 문제 참고).

### 5-6. 프로그램 등록

```python
# app/programs/registry.py
PROGRAM_MODULES: list[str] = [
    # "app.programs.cafeteria.tools",
]
```
- `load_programs()`가 이 목록을 import해서 데코레이터 등록을 일으킨다. `main.py`의 lifespan에서 한 번 부른다.
- 새 프로그램을 추가할 때 틀 쪽에서 고치는 곳은 이 목록 한 줄뿐이다.
- `ToolRegistry`는 클래스이고, 기본 인스턴스 하나를 데코레이터가 쓴다. 테스트는 새 `ToolRegistry`를 만들어 쓴다.

### 5-7. 설정과 공용 예외

`app/core/config.py`의 `Settings`에 추가:
| 이름 | 기본값 | 뜻 |
|---|---|---|
| `SERVICE_API_KEY` | `""` (비면 skills API 전부 거부) | AI 서비스 ↔ 백엔드 공유 비밀 키 |
| `TOOL_TIMEOUT_SECONDS` | 10 | tool 기본 시간 제한 |
| `RESULT_TTL_SECONDS` | 1800 | `ui` 보관 시간 |
| `RESULT_STORE_MAX_ITEMS` | 1000 | `ui` 보관 최대 개수 |

- 키에 기본값 `""`을 둔 이유: `main.py`가 import 시점에 설정을 읽고, 기존 테스트의 `Settings(...)`도 키를 넘기지 않는다. 필수로 두면 앱과 기존 테스트가 깨진다. 대신 빈 키는 "아무도 통과 못 함"으로 처리해 안전하게 둔다.
- `.env.example`에 위 항목을 추가한다.
- 배포: Cloud Run에 `SERVICE_API_KEY`를 Secret Manager로 넣는 일은 배포 담당과 맞춘다 (이번 범위 밖, PR 설명에 적는다).

`app/common/exceptions.py`에 추가: `NotFoundException(code="NOT_FOUND", message=...)` (404). 나머지(`AppException`, `UnauthorizedException`, 처리기)는 PR #9 것을 그대로 쓴다.

### 5-8. 테스트

- `test_registry.py`: 데코레이터 등록, 입력 모델에서 JSON Schema 생성, 이름 형식 위반(점, 대문자, 숫자 시작, 끝 밑줄, 밑줄 두 개, 64자 초과)·중복 등록 에러, 인자 타입 힌트 없음·인자 두 개 에러
- `test_result_store.py`: put/get, 만료 후 None, 최대 개수 초과 시 오래된 것 삭제
- `test_skills_api.py`: conftest의 `client`를 쓰고, 이 파일에서 `settings` fixture를 다시 정의해 키를 넣는다. 테스트용 가짜 tool로 목록(`items`, `inputSchema`), 401(키 없음·틀림·한글·서버 키 미설정), 404, `ok`(+ `ui` 보관, 응답에 `ui` 없음, `resultId`), `ui` 없음 → `resultId: null`, `need_clarification`, `ToolError`, 입력 검증 실패, 시간 초과, 예상 못 한 예외, 잘못된 반환값, 본문 형식 오류(400)

## 6. 함께 바꾸는 문서

- `CLAUDE.md`: 폴더 구조에 `programs/` 틀 파일과 프로그램 폴더의 `tools.py`를 추가한다.
- AI 파트 요청서: 5-4의 API 형식을 반영한다 (이름 형식 `<프로그램>_<기능>`, `X-Service-Key`, 응답 `status` 세 가지, camelCase). 요청서는 저장소 밖이라 사용자가 고친다.
- 위키 `가이드_총관리자.md` 4장: AI가 "4단계 예정"으로 남아 있다. 팀과 방향을 맞춘 뒤 고친다 (이번 범위 밖).

## 7. 구현하는 사람에게 맡기는 것

- 내부 함수·클래스 이름, 로그 문구
- `MemoryResultStore`의 동시성 처리 (단일 이벤트 루프라 `await` 없는 dict 조작이면 잠금 없이 충분)
- 테스트용 가짜 tool 모양
