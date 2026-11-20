# skill 공통 틀 구현 가이드 (따라 치기용)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **이 문서는 사람이 직접 따라 치는 용도다.** 코드는 모두 미리 돌려 봤다 (PR #9 반영 main 기준, 테스트 50개 통과, ruff 통과). 각 코드 아래에 "무슨 코드인지" 설명을 붙였다.

**Goal:** AI 서비스가 백엔드 프로그램(tool)을 목록으로 받고 실행할 수 있는 공통 틀(`/api/v1/skills`)을 만든다.

**Architecture:** tool은 `@tool` 데코레이터를 붙인 `async` 함수다. 등록부(`ToolRegistry`)가 이름·설명·입력 모델을 모아 두고, `router → service`가 목록 조회와 실행을 처리한다. 화면용 결과(`ui`)는 `ResultStore`(지금은 메모리)에 `result_id`로 보관한다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings, pytest + anyio, httpx `AsyncClient`

**Spec:** `docs/superpowers/specs/2026-11-18-skill-framework-design.md`

## 2026-11-19 수정: 팀원 PR #9 반영

팀원이 PR #9(Google 로그인 + Cloud Run 배포)에서 공용 파일을 먼저 만들었다. 그래서 이 가이드를 거기에 맞췄다.

| 바뀐 점 | 예전 가이드 | 지금 |
|---|---|---|
| Task 0 | `uv add pydantic-settings` | 필요 없음 (PR #9에 이미 있음) |
| Task 1 공용 예외 | `exceptions.py`를 새로 만듦 | 팀원 파일에 `NotFoundException` 하나만 **추가** |
| Task 2 설정 | `config.py`를 새로 만듦 | 팀원 `Settings`에 필드 4개만 **추가** |
| tool 이름 | `cafeteria.get_menu` (점) | `cafeteria_get_menu` (밑줄). OpenAI·Claude가 점을 허용하지 않는다 |
| JSON 필드 | `input_schema`, `result_id`, `{"tools": [...]}` | `inputSchema`, `resultId`, `{"items": [...]}` (팀 규칙 `CamelModel`, `ItemsResponse`) |
| 요청 형식 오류 | 422 | 400 (팀원 처리기 기준) |
| API 테스트 | 동기 `TestClient` | 팀원 `conftest.py`의 `AsyncClient` + `async def` 테스트 |
| Task 4 | - | **바뀐 것 없음.** 이미 친 `tests/programs/test_result_store.py`는 그대로 쓴다 |

## Global Constraints

- tool 이름: `<프로그램>_<기능>`, 정규식 `^[a-z][a-z0-9]*(_[a-z0-9]+)+$`, 64자 이하
- 서비스 키 헤더: `X-Service-Key`, 설정값 `SERVICE_API_KEY` (비어 있으면 전부 거부)
- 기본값: `TOOL_TIMEOUT_SECONDS=10`, `RESULT_TTL_SECONDS=1800`, `RESULT_STORE_MAX_ITEMS=1000`
- `result_id` 형식: `"r_" + uuid4().hex`
- 공용 에러 형식: `{"error": {"code", "message"}}` (PR #9 `AppException`)
- API JSON은 camelCase (`CamelModel`), 목록은 `{"items": [...]}` (`ItemsResponse`)
- 커밋: `<type>: <한글 설명>`, `main`에 직접 push 금지 (CLAUDE.md)

## Review Focus

테스트로 막지 못했거나, 쓰는 사람이 부딪히기 쉬운 경우다.

1. **Cloud Run 인스턴스가 2개일 때:** `deploy.yml`이 최대 인스턴스 2로 되어 있다. 메모리 보관이라 다른 인스턴스에 저장된 `ui`는 못 찾는다. 지금은 `ui`를 꺼내는 쪽(채팅 창구)이 없어서 문제가 안 되지만, 채팅 창구 전에 DB 보관으로 바꾸거나 인스턴스를 1로 줄여야 한다.
2. **배포 서버에 `SERVICE_API_KEY`가 없을 때:** skills API가 전부 401이 된다. 배포 담당과 Secret Manager 설정을 맞춘다.
3. **tool 안에서 직접 `TimeoutError`를 던질 때:** 시간 초과(`TOOL_TIMEOUT`)로 보인다. 다른 사이트를 읽는 tool은 자기 에러를 `ToolError`로 바꿔 던진다.
4. **한글 같은 ASCII 밖 글자가 키 헤더에 올 때:** 500이 아니라 401이어야 한다. → Task 5 테스트 `non-ascii`로 막았다.
5. **tool이 `ToolOk`가 아닌 값(dict 등)을 반환할 때:** 서버가 죽지 않고 `TOOL_FAILED`. → Task 5 테스트 `test_wrong_return_type_is_tool_failed`로 막았다.

---

## 전체 그림

```
AI 서비스
  │  GET  /api/v1/skills                 (tool 목록)
  │  POST /api/v1/skills/{name}/invoke   (tool 실행)
  ▼
router.py ── dependencies.py (서비스 키 검사, registry·store 꺼내기)
  │
service.py ── registry.py     (@tool로 등록된 함수 찾기)
           └─ result_store.py (ui를 result_id로 보관)
```

| 파일 | 하는 일 |
|---|---|
| `app/common/exceptions.py` (수정) | `NotFoundException` 추가 |
| `app/core/config.py` (수정) | skills 설정 4개 추가 |
| `.env.example` (수정) | 환경변수 4개 추가 |
| `app/programs/schemas.py` | tool 결과 모델, API 요청·응답 모델 |
| `app/programs/registry.py` | `@tool` 데코레이터와 등록부 |
| `app/programs/result_store.py` | `ui` 보관소 (메모리) |
| `app/programs/service.py` | 목록·실행 로직 |
| `app/programs/dependencies.py` | 서비스 키 검사, 의존성 |
| `app/programs/router.py` | 엔드포인트 2개 |
| `app/main.py` (수정) | lifespan, 라우터 등록 |
| `CLAUDE.md` (수정) | 폴더 구조에 틀 파일과 `tools.py` 추가 |

---

### Task 0: 브랜치 준비

- [ ] **Step 1: 최신 main 받고 브랜치 만들기**

```powershell
git pull
git switch -c feat/skills-framework
```

`git switch -c`는 지금 바뀐 파일(이미 친 `test_result_store.py`)을 그대로 들고 새 브랜치로 옮겨 간다. `main`에 직접 올리지 않기 위해 브랜치를 만든다.

- [ ] **Step 2: 테스트 폴더 표시 파일 만들기**

```powershell
New-Item -ItemType File tests/programs/__init__.py
```

빈 파일이다. 팀원의 `tests/auth/__init__.py`와 같은 역할로, 폴더가 달라도 테스트 파일 이름이 겹칠 때 pytest가 헷갈리지 않게 해 준다.

- [ ] **Step 3: 기존 테스트 확인**

```powershell
uv sync
uv run pytest -q
```

`result_store.py`를 아직 안 만들었다면 이미 친 `test_result_store.py`가 import 에러를 내서 테스트 전체가 멈춘다 (`Interrupted: 1 error during collection`).

**그래서 순서는 Task 0 → Task 4 → Task 1 → Task 2 → Task 3 → Task 5 → Task 6을 권한다.** Task 4는 다른 Task에 기대지 않아서 먼저 해도 된다. Task 4를 끝내면 여기서 19 passed(팀원 테스트 14개 + `test_result_store.py` 5개)가 나온다.

---

### Task 1: 공용 예외에 404 추가

**Files:**
- Modify: `app/common/exceptions.py` (팀원 파일, 공용)

**Interfaces:**
- Consumes: PR #9 `AppException(status_code, code, message)`
- Produces: `NotFoundException(code: str = "NOT_FOUND", message: str = "찾을 수 없습니다.")`

- [ ] **Step 1: `ForbiddenException` 아래, `EmailNotAllowedException` 위에 추가**

```python
class NotFoundException(AppException):
    def __init__(self, code: str = "NOT_FOUND", message: str = "찾을 수 없습니다.") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, code, message)
```

**무슨 코드인가:**
- 팀원이 만든 `AppException`은 "상태 코드, 에러 코드, 메시지"를 들고 다니는 공용 예외다. 어디서든 `raise`하면 팀원이 등록해 둔 처리기가 `{"error": {"code", "message"}}` JSON으로 바꿔 준다.
- `NotFoundException`은 그 자식이다. 404를 미리 정해 두고, 에러 코드는 상황마다 바꿀 수 있게 인자로 받는다. 우리는 `NotFoundException("TOOL_NOT_FOUND", "...")`처럼 쓴다.
- `super().__init__(...)`: 부모 클래스(`AppException`)의 생성자를 불러 값을 채운다. 인자 순서가 `(상태 코드, 코드, 메시지)`인 점에 주의한다.
- 테스트는 Task 5의 `test_unknown_tool_returns_404`가 대신한다.

- [ ] **Step 2: 확인**

```powershell
uv run pytest -q
```

Expected: 기존과 같은 수로 통과 (아무것도 안 깨짐)

---

### Task 2: 설정 추가

**Files:**
- Modify: `app/core/config.py` (팀원 파일, 공용), `.env.example`
- 내 `.env`에도 추가 (커밋 안 함)

**Interfaces:**
- Produces: `Settings.service_api_key: str = ""`, `tool_timeout_seconds: float = 10`, `result_ttl_seconds: float = 1800`, `result_store_max_items: int = 1000`

- [ ] **Step 1: `Settings`의 `cors_origins` 줄 바로 아래에 추가**

```text
    cors_origins: CommaList = ["http://localhost:5173"]   # ← 원래 있는 줄

    # skill(프로그램) 공통 틀
    service_api_key: str = ""
    tool_timeout_seconds: float = 10
    result_ttl_seconds: float = 1800
    result_store_max_items: int = 1000
```

**무슨 코드인가:**
- 팀원의 `Settings`는 `BaseSettings`를 상속해서, 필드 이름과 같은 환경변수(`SERVICE_API_KEY` 등, 대소문자 무시)나 `.env` 값을 자동으로 읽는다. 우리는 필드 4개만 더한다.
- **왜 키의 기본값이 `""`인가:** 팀원의 `main.py`는 파일을 import하는 순간 `get_settings()`를 부른다 (CORS 설정 때문). 키를 필수로 만들면 `.env`에 키가 없는 사람은 서버가 아예 안 뜨고, 팀원 테스트의 `Settings(...)`도 깨진다. 그래서 기본값을 두고, 대신 Task 5에서 "빈 키면 아무도 통과 못 함"으로 막는다.
- `float`인 이유: `0.5`초 같은 값도 넣을 수 있게.

- [ ] **Step 2: `.env.example` 맨 아래에 추가**

```dotenv

# AI 서비스가 /api/v1/skills를 부를 때 쓰는 공유 비밀 키. 비워 두면 skills API가 모두 거부된다.
SERVICE_API_KEY=

# tool 기본 시간 제한(초), ui 결과 보관 시간(초)과 최대 개수
TOOL_TIMEOUT_SECONDS=10
RESULT_TTL_SECONDS=1800
RESULT_STORE_MAX_ITEMS=1000
```

팀원에게 "이런 환경변수가 생겼다"를 알리는 파일이다. 실제 비밀 값은 넣지 않는다.

- [ ] **Step 3: 내 `.env`에 키 넣기**

`.env`가 없으면 `Copy-Item .env.example .env`로 만든다. 그다음 `.env`에 `SERVICE_API_KEY=아무-긴-문자열`을 넣는다. 나중에 AI 파트와 같은 값을 쓴다. `.env`는 `.gitignore`에 있어 커밋되지 않는다.

- [ ] **Step 4: 확인 후 커밋**

```powershell
uv run pytest -q
```

Expected: 기존과 같은 수로 통과

```powershell
git add app/common/exceptions.py app/core/config.py .env.example tests/programs/__init__.py
git commit -m "feat: skill 틀용 설정과 NotFoundException 추가"
```

---

### Task 3: tool 결과 모델과 등록부(`@tool`)

**Files:**
- Create: `app/programs/schemas.py`, `app/programs/registry.py`
- Test: `tests/programs/test_registry.py`

**Interfaces:**
- Consumes: PR #9 `CamelModel`
- Produces (schemas): `ToolOk(llm, ui=None)`, `Candidate(value, label, description=None)`, `ToolNeedClarification(field, message, candidates)`, `ToolResult`, `ToolError(code, message, details=None)`, API 모델 `ToolInfo`, `InvokeRequest`, `ErrorInfo`, `InvokeOkResponse`, `InvokeNeedClarificationResponse`, `InvokeErrorResponse`, `InvokeResponse`
- Produces (registry): `ToolRegistry` (`register`, `tool`, `get`, `all`), `RegisteredTool` (`name`, `description`, `input_model`, `func`, `timeout`, `input_schema()`), `default_registry`, `tool`, `PROGRAM_MODULES`, `load_programs(modules=None)`

- [ ] **Step 1: 모델 파일 쓰기** — `app/programs/schemas.py`

registry가 `ToolResult`를 쓰므로 먼저 만든다. 모델만 있는 파일이라 테스트는 Task 3·5의 테스트가 대신한다.

```python
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.common.schemas import CamelModel

# ---- tool 함수가 반환하는 결과 ----


class Candidate(CamelModel):
    value: str
    label: str
    description: str | None = None


class ToolOk(BaseModel):
    """tool 성공 결과. llm은 AI에게 주고, ui는 백엔드가 보관한다."""

    llm: dict[str, Any]
    ui: dict[str, Any] | None = None


class ToolNeedClarification(BaseModel):
    """입력이 애매할 때. 후보만 주고, 되묻는 문장은 AI가 쓴다."""

    field: str
    message: str
    candidates: list[Candidate]


ToolResult = ToolOk | ToolNeedClarification


class ToolError(Exception):
    """tool 안에서 예상된 실패를 알릴 때 던진다. 예: 메뉴 없음."""

    def __init__(
        self, code: str, message: str, details: list[dict[str, Any]] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


# ---- API 요청/응답 (JSON은 camelCase) ----


class ToolInfo(CamelModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class InvokeRequest(CamelModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ErrorInfo(CamelModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class InvokeOkResponse(CamelModel):
    status: Literal["ok"] = "ok"
    llm: dict[str, Any]
    result_id: str | None


class InvokeNeedClarificationResponse(CamelModel):
    status: Literal["need_clarification"] = "need_clarification"
    field: str
    message: str
    candidates: list[Candidate]


class InvokeErrorResponse(CamelModel):
    status: Literal["error"] = "error"
    error: ErrorInfo


InvokeResponse = Annotated[
    InvokeOkResponse | InvokeNeedClarificationResponse | InvokeErrorResponse,
    Field(discriminator="status"),
]
```

**무슨 코드인가:** 파일이 두 부분으로 나뉜다.

*윗부분: tool 함수가 반환하는 것 (프로그램 개발자가 쓴다)*
- `ToolOk`: 성공. `llm`은 AI가 답변 문장을 쓸 때 볼 내용이고, `ui`는 프론트 카드용이다. `ui`는 없어도 된다.
- `ToolNeedClarification`: "상록원"처럼 애매한 입력일 때 후보(`Candidate`) 목록을 준다. `field`는 어느 입력이 애매한지 알려 준다.
- `ToolResult = ToolOk | ToolNeedClarification`: "둘 중 하나"라는 타입 별칭이다.
- `ToolError`: 반환이 아니라 `raise`로 쓴다. "메뉴 없음"처럼 예상된 실패를 알린다. 모델이 아니라 예외라서 `Exception`을 상속한다.

*아랫부분: HTTP API가 주고받는 모양 (AI 서비스가 본다)*
- **`CamelModel`**: 팀원이 만든 베이스 모델이다. 파이썬에서는 `input_schema`, `result_id`로 쓰고, JSON으로 나갈 때는 `inputSchema`, `resultId`로 자동으로 바뀐다 (`alias_generator=to_camel`). 팀 API 규칙이라 API 모델은 모두 이걸 상속한다.
- `ToolOk`, `ToolNeedClarification`은 API로 바로 나가지 않는 내부 모델이라 그냥 `BaseModel`을 쓴다. `Candidate`는 API 응답에도 들어가서 `CamelModel`이다.
- `InvokeRequest`: 실행 요청 본문 `{"arguments": {...}}`. 안 보내면 빈 dict.
- `InvokeOkResponse` 등 세 응답: `status` 값이 각각 `"ok"`, `"need_clarification"`, `"error"`로 고정(`Literal`)돼 있다.
- `InvokeResponse`: 셋 중 하나. `discriminator="status"`는 "`status` 값을 보고 어느 모델인지 고른다"는 뜻이라 Swagger 문서에도 깔끔하게 나온다.
- 주의: `ToolOk`에는 `ui`가 있지만 `InvokeOkResponse`에는 없다. `ui`가 AI 쪽으로 새지 않게 하는 핵심이 여기다.
- 목록 응답 모델은 따로 만들지 않는다. 팀원의 `ItemsResponse[ToolInfo]`(`{"items": [...]}`)를 Task 5에서 쓴다.

- [ ] **Step 2: 실패하는 테스트 쓰기** — `tests/programs/test_registry.py`

```python
import pytest
from pydantic import BaseModel, Field

from app.programs.registry import ToolRegistry, load_programs
from app.programs.schemas import ToolOk


class HelloInput(BaseModel):
    name: str = Field(description="인사할 사람 이름")


async def hello(args: HelloInput) -> ToolOk:
    return ToolOk(llm={"greeting": f"안녕, {args.name}"})


def test_decorator_registers_tool_and_returns_original_function() -> None:
    registry = ToolRegistry()

    decorated = registry.tool(name="demo_hello", description="인사한다")(hello)

    assert decorated is hello
    registered = registry.get("demo_hello")
    assert registered is not None
    assert registered.description == "인사한다"
    assert registered.input_model is HelloInput
    assert registered.timeout is None


def test_input_schema_comes_from_pydantic_model() -> None:
    registry = ToolRegistry()
    registry.register("demo_hello", "인사한다", hello)

    schema = registry.get("demo_hello").input_schema()  # type: ignore[union-attr]

    assert schema["type"] == "object"
    assert schema["required"] == ["name"]
    assert schema["properties"]["name"]["description"] == "인사할 사람 이름"


def test_all_returns_tools_in_registration_order() -> None:
    registry = ToolRegistry()
    registry.register("demo_b", "b", hello)
    registry.register("demo_a", "a", hello)

    assert [t.name for t in registry.all()] == ["demo_b", "demo_a"]


@pytest.mark.parametrize(
    "name",
    [
        "hello",
        "demo.hello",
        "Demo_hello",
        "1demo_hello",
        "demo_",
        "demo__hello",
        "",
        "a_" + "b" * 63,
    ],
)
def test_invalid_name_is_rejected(name: str) -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError):
        registry.register(name, "설명", hello)


def test_duplicate_name_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register("demo_hello", "인사한다", hello)

    with pytest.raises(ValueError):
        registry.register("demo_hello", "또 인사한다", hello)


def test_sync_function_is_rejected() -> None:
    registry = ToolRegistry()

    def sync_tool(args: HelloInput) -> ToolOk:
        return ToolOk(llm={})

    with pytest.raises(TypeError):
        registry.register("demo_sync", "동기 함수", sync_tool)  # type: ignore[arg-type]


def test_function_without_model_hint_is_rejected() -> None:
    registry = ToolRegistry()

    async def no_hint(args) -> ToolOk:  # type: ignore[no-untyped-def]
        return ToolOk(llm={})

    async def dict_hint(args: dict) -> ToolOk:
        return ToolOk(llm={})

    with pytest.raises(TypeError):
        registry.register("demo_no_hint", "힌트 없음", no_hint)
    with pytest.raises(TypeError):
        registry.register("demo_dict_hint", "dict 힌트", dict_hint)


def test_function_with_two_arguments_is_rejected() -> None:
    registry = ToolRegistry()

    async def two_args(args: HelloInput, extra: HelloInput) -> ToolOk:
        return ToolOk(llm={})

    with pytest.raises(TypeError):
        registry.register("demo_two", "인자 두 개", two_args)  # type: ignore[arg-type]


def test_load_programs_fails_loudly_on_typo() -> None:
    with pytest.raises(ModuleNotFoundError):
        load_programs(["app.programs.no_such_program.tools"])
```

**무슨 코드인가:**
- 테스트마다 `ToolRegistry()`를 새로 만든다. 앱 전체가 쓰는 등록부(`default_registry`)를 더럽히지 않기 위해서다.
- 첫 두 테스트: 데코레이터가 함수를 등록하는지, 입력 모델에서 JSON Schema(`required`, `description`)가 만들어지는지 본다. `decorated is hello`는 "데코레이터가 함수를 바꾸지 않고 그대로 돌려준다"는 확인이다.
- `@pytest.mark.parametrize`: 같은 테스트를 잘못된 이름 8개로 각각 돌린다. 점(`demo.hello`), 대문자, 숫자 시작, 끝 밑줄, 밑줄 두 개, 빈 이름, 65자짜리 이름이다.
- 나머지: 실수하기 쉬운 경우(이름 중복, `def`로 씀, 타입 힌트 빠짐, 인자 두 개, 모듈 이름 오타)를 **서버 시작 때 바로 에러**로 잡는지 본다.

- [ ] **Step 3: 실패하는지 확인**

```powershell
uv run pytest tests/programs/test_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.programs.registry'`

- [ ] **Step 4: 코드 쓰기** — `app/programs/registry.py`

```python
import importlib
import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar, get_type_hints

from pydantic import BaseModel

from app.programs.schemas import ToolResult

# 프로그램의 tools.py를 여기에 한 줄씩 추가한다.
PROGRAM_MODULES: list[str] = [
    # "app.programs.cafeteria.tools",
]

# <프로그램>_<기능>. OpenAI·Claude tool 이름 규칙(영문·숫자·_·-, 64자 이하) 안에 들어간다.
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
TOOL_NAME_MAX_LENGTH = 64

ToolFunc = Callable[[Any], Awaitable[ToolResult]]
F = TypeVar("F", bound=ToolFunc)


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_model: type[BaseModel]
    func: ToolFunc
    timeout: float | None

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self, name: str, description: str, func: ToolFunc, timeout: float | None = None
    ) -> RegisteredTool:
        if len(name) > TOOL_NAME_MAX_LENGTH or not TOOL_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"tool 이름은 '<프로그램>_<기능>' 형식이어야 합니다: {name}")
        if name in self._tools:
            raise ValueError(f"이미 등록된 tool 이름입니다: {name}")
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"tool 함수는 async def여야 합니다: {name}")
        registered = RegisteredTool(
            name=name,
            description=description,
            input_model=_find_input_model(name, func),
            func=func,
            timeout=timeout,
        )
        self._tools[name] = registered
        return registered

    def tool(self, name: str, description: str, timeout: float | None = None) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            self.register(name, description, func, timeout)
            return func

        return decorator

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def all(self) -> list[RegisteredTool]:
        return list(self._tools.values())


def _find_input_model(name: str, func: ToolFunc) -> type[BaseModel]:
    params = list(inspect.signature(func).parameters)
    if len(params) != 1:
        raise TypeError(f"tool 함수는 인자를 하나만 받아야 합니다: {name}")
    model = get_type_hints(func).get(params[0])
    if not (inspect.isclass(model) and issubclass(model, BaseModel)):
        raise TypeError(f"tool 함수의 인자에는 Pydantic 모델 타입 힌트가 필요합니다: {name}")
    return model


default_registry = ToolRegistry()
tool = default_registry.tool


def load_programs(modules: list[str] | None = None) -> None:
    """프로그램 모듈을 import해서 @tool 등록을 일으킨다. 앱 시작 때 한 번 부른다."""
    for module in PROGRAM_MODULES if modules is None else modules:
        importlib.import_module(module)
```

**무슨 코드인가:** tool을 모아 두는 "전화번호부"다.
- `PROGRAM_MODULES`: 새 프로그램을 붙일 때 고치는 유일한 곳이다. 학식을 만들면 주석을 풀어 `"app.programs.cafeteria.tools"`를 넣는다.
- `TOOL_NAME_PATTERN`: `소문자로 시작하는 단어` + `_단어`가 한 번 이상. 그래서 `cafeteria_get_menu`는 되고, `demo_`(끝 밑줄), `demo__hello`(밑줄 두 개)는 안 된다. `TOOL_NAME_MAX_LENGTH`는 LLM API들의 64자 제한이다.
- `ToolFunc`, `F`: 타입 힌트용이다. "인자 하나를 받아 `ToolResult`를 돌려주는 async 함수"라는 뜻이다. `F`는 데코레이터가 함수 타입을 그대로 유지하게 해 준다.
- `RegisteredTool`: 등록된 tool 한 개의 정보 묶음이다. `@dataclass(frozen=True)`는 필드만 적으면 생성자를 자동으로 만들어 주고, 만든 뒤에는 값을 못 바꾸게 한다. `input_schema()`는 Pydantic의 `model_json_schema()`로 JSON Schema를 만든다.
- `ToolRegistry.register`: 등록 전에 검사 3개(이름 형식, 중복, async인지)를 하고, 입력 모델을 찾아 저장한다.
- `ToolRegistry.tool`: 데코레이터다. `@registry.tool(...)`을 함수 위에 붙이면 파이썬이 그 함수를 `decorator(func)`에 넘기고, 우리는 `register`만 하고 함수는 그대로 돌려준다.
- `_find_input_model`: 함수의 유일한 인자의 타입 힌트를 읽어 Pydantic 모델인지 확인한다.
- `default_registry`, `tool`: 앱 전체가 함께 쓰는 등록부 하나와 그 데코레이터다. 프로그램 코드에서는 `from app.programs.registry import tool` 후 `@tool(...)`만 쓰면 된다.
- `load_programs`: 데코레이터는 **파일이 import될 때** 실행된다. 그래서 앱 시작 때 프로그램 모듈을 import해 줘야 등록이 일어난다.

- [ ] **Step 5: 통과하는지 확인**

```powershell
uv run pytest tests/programs/test_registry.py -v
```

Expected: 16 passed

- [ ] **Step 6: 커밋**

```powershell
git add app/programs/schemas.py app/programs/registry.py tests/programs/test_registry.py
git commit -m "feat: skill tool 등록부와 결과 모델 추가"
```

---

### Task 4: 화면용 결과 보관소 (바뀐 것 없음)

**Files:**
- Create: `app/programs/result_store.py`
- Test: `tests/programs/test_result_store.py` (**이미 쳤다.** 그대로 쓴다)

**Interfaces:**
- Produces: `StoredResult(result_id, tool_name, ui, created_at)`, `ResultStore` (Protocol: `async put(tool_name, ui) -> str`, `async get(result_id) -> StoredResult | None`), `MemoryResultStore(ttl_seconds, max_items, clock=time.monotonic)`

> 이미 친 `test_result_store.py`의 `@pytest.mark.anyio`는 팀원 `conftest.py`의 `anyio_backend` fixture(asyncio)와 그대로 맞는다.

- [ ] **Step 1: 실패하는지 확인**

```powershell
uv run pytest tests/programs/test_result_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.programs.result_store'`

- [ ] **Step 2: 코드 쓰기** — `app/programs/result_store.py`

```python
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredResult:
    result_id: str
    tool_name: str
    ui: dict[str, Any]
    created_at: float


class ResultStore(Protocol):
    async def put(self, tool_name: str, ui: dict[str, Any]) -> str: ...

    async def get(self, result_id: str) -> StoredResult | None: ...


class MemoryResultStore:
    """메모리에 ui를 잠시 보관한다. 서버를 재시작하면 사라진다."""

    def __init__(
        self,
        ttl_seconds: float,
        max_items: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._clock = clock
        self._items: OrderedDict[str, StoredResult] = OrderedDict()

    async def put(self, tool_name: str, ui: dict[str, Any]) -> str:
        self._remove_expired()
        while len(self._items) >= self._max_items:
            self._items.popitem(last=False)
        result_id = f"r_{uuid.uuid4().hex}"
        self._items[result_id] = StoredResult(result_id, tool_name, ui, self._clock())
        return result_id

    async def get(self, result_id: str) -> StoredResult | None:
        item = self._items.get(result_id)
        if item is None:
            return None
        if self._is_expired(item):
            del self._items[result_id]
            return None
        return item

    def _is_expired(self, item: StoredResult) -> bool:
        return self._clock() - item.created_at >= self._ttl

    def _remove_expired(self) -> None:
        # 넣은 순서대로 쌓이므로 앞에서부터 만료된 것만 지우면 된다.
        while self._items:
            oldest = next(iter(self._items.values()))
            if not self._is_expired(oldest):
                break
            self._items.popitem(last=False)
```

**무슨 코드인가:**
- `StoredResult`: 보관하는 한 건이다. 어느 tool의 결과인지, 언제 넣었는지도 같이 둔다. `@dataclass(frozen=True)`는 Task 3에서 설명했으므로 생략하겠습니다.
- `ResultStore(Protocol)`: "보관소라면 `put`과 `get`이 있어야 한다"는 약속(인터페이스)이다. 나머지 코드는 이 약속만 보고 쓴다. 그래서 나중에 DB 버전(`DbResultStore`)을 같은 모양으로 만들어 끼우면 다른 코드는 안 고쳐도 된다. `...`은 "몸체 없음"이라는 뜻이다.
- `MemoryResultStore`: 메모리 버전이다.
  - `OrderedDict`: 넣은 순서를 기억하는 dict다. `popitem(last=False)`는 가장 먼저 넣은 것을 꺼낸다.
  - `time.monotonic`: 컴퓨터 시계를 바꿔도 뒤로 가지 않는 시계다. 경과 시간을 잴 때 쓴다. 테스트는 이 자리에 `FakeClock`을 넣어 시간을 직접 움직인다.
  - `put`: 만료된 것을 먼저 치우고, 그래도 꽉 차 있으면 오래된 것부터 지운 뒤 새로 넣는다. `uuid4().hex`는 겹치지 않는 무작위 ID를 만든다.
  - `get`: 없거나 만료됐으면 `None`. 만료된 건 꺼내는 김에 지운다.
- 메서드가 `async`인 이유: 지금 메모리 버전은 기다릴 일이 없지만, DB 버전은 `await`가 필요하다. 약속을 미리 `async`로 맞춰 둔다.

- [ ] **Step 3: 통과하는지 확인**

```powershell
uv run pytest tests/programs/test_result_store.py -v
```

Expected: 5 passed

- [ ] **Step 4: 커밋**

```powershell
git add app/programs/result_store.py tests/programs/test_result_store.py
git commit -m "feat: 화면용 결과(ui) 메모리 보관소 추가"
```

---

### Task 5: 목록·실행 API (service, dependencies, router, main)

**Files:**
- Create: `app/programs/service.py`, `app/programs/dependencies.py`, `app/programs/router.py`
- Modify: `app/main.py` (공용)
- Test: `tests/programs/test_skills_api.py`

**Interfaces:**
- Consumes: Task 1 `NotFoundException` / PR #9 `UnauthorizedException`, `ItemsResponse`, `Settings`, `get_settings`, conftest `settings`·`client` fixture / Task 3 전부 / Task 4 `ResultStore`, `MemoryResultStore`, `StoredResult`
- Produces: `service.list_tools(registry) -> list[ToolInfo]`, `service.invoke_tool(registry, store, name, arguments, default_timeout) -> InvokeResponse`, `service.get_ui_result(store, result_id) -> StoredResult | None` (나중에 채팅 창구가 씀), `dependencies.verify_service_key`, `get_registry`, `get_result_store`

- [ ] **Step 1: 실패하는 테스트 쓰기** — `tests/programs/test_skills_api.py`

```python
import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.main import app
from app.programs.dependencies import get_registry, get_result_store
from app.programs.registry import ToolRegistry
from app.programs.result_store import MemoryResultStore
from app.programs.schemas import Candidate, ToolError, ToolNeedClarification, ToolOk

pytestmark = pytest.mark.anyio

KEY = "test-key"
HEADERS = {"X-Service-Key": KEY}

# ---- 테스트용 가짜 tool ----

registry = ToolRegistry()


class EchoInput(BaseModel):
    text: str = Field(description="돌려줄 글자")


class EmptyInput(BaseModel):
    pass


@registry.tool(name="test_echo", description="받은 글자를 돌려준다")
async def echo(args: EchoInput) -> ToolOk:
    return ToolOk(llm={"text": args.text}, ui={"card": args.text})


@registry.tool(name="test_no_ui", description="ui 없이 끝난다")
async def no_ui(args: EmptyInput) -> ToolOk:
    return ToolOk(llm={"done": True})


@registry.tool(name="test_ambiguous", description="후보를 돌려준다")
async def ambiguous(args: EmptyInput) -> ToolNeedClarification:
    return ToolNeedClarification(
        field="cafeteria",
        message="식당이 여러 곳입니다.",
        candidates=[
            Candidate(value="sangrok_3f", label="상록원3층식당"),
            Candidate(value="sangrok_2f", label="상록원2층식당"),
        ],
    )


@registry.tool(name="test_fail", description="예상된 실패")
async def fail(args: EmptyInput) -> ToolOk:
    raise ToolError("MENU_NOT_FOUND", "메뉴가 없습니다.")


@registry.tool(name="test_slow", description="너무 느리다", timeout=0.05)
async def slow(args: EmptyInput) -> ToolOk:
    await asyncio.sleep(1)
    return ToolOk(llm={})


@registry.tool(name="test_crash", description="예상 못 한 예외")
async def crash(args: EmptyInput) -> ToolOk:
    raise RuntimeError("secret internal detail")


@registry.tool(name="test_bad_return", description="잘못된 값을 반환한다")
async def bad_return(args: EmptyInput) -> ToolOk:
    return {"llm": {}}  # type: ignore[return-value]


# ---- 준비: conftest.py의 settings, client를 이 파일에 맞게 바꿔 쓴다 ----


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", service_api_key=KEY)


@pytest.fixture
def store() -> MemoryResultStore:
    return MemoryResultStore(ttl_seconds=60, max_items=10)


@pytest.fixture
async def skills_client(
    client: AsyncClient, store: MemoryResultStore
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_result_store] = lambda: store
    yield client


async def invoke(
    client: AsyncClient, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/skills/{name}/invoke", json={"arguments": arguments or {}}, headers=HEADERS
    )
    assert response.status_code == 200
    return response.json()


# ---- 목록 ----


async def test_list_skills_returns_registered_tools(skills_client: AsyncClient) -> None:
    response = await skills_client.get("/api/v1/skills", headers=HEADERS)

    assert response.status_code == 200
    tools = {t["name"]: t for t in response.json()["items"]}
    assert tools["test_echo"]["description"] == "받은 글자를 돌려준다"
    assert tools["test_echo"]["inputSchema"]["properties"]["text"]["description"] == "돌려줄 글자"


# ---- 인증 ----


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Service-Key": "wrong"}, {"X-Service-Key": "키".encode()}],
    ids=["missing", "wrong", "non-ascii"],
)
async def test_bad_service_key_returns_401(
    skills_client: AsyncClient, headers: dict[str, Any]
) -> None:
    responses = [
        await skills_client.get("/api/v1/skills", headers=headers),
        await skills_client.post(
            "/api/v1/skills/test_echo/invoke", json={"arguments": {}}, headers=headers
        ),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_empty_server_key_rejects_everyone(
    skills_client: AsyncClient, settings: Settings
) -> None:
    settings.service_api_key = ""

    response = await skills_client.get("/api/v1/skills", headers={"X-Service-Key": ""})

    assert response.status_code == 401


# ---- 실행 ----


async def test_unknown_tool_returns_404(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_nothing/invoke", json={"arguments": {}}, headers=HEADERS
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TOOL_NOT_FOUND"


async def test_ok_returns_llm_and_keeps_ui(
    skills_client: AsyncClient, store: MemoryResultStore
) -> None:
    body = await invoke(skills_client, "test_echo", {"text": "안녕"})

    assert body["status"] == "ok"
    assert body["llm"] == {"text": "안녕"}
    assert "ui" not in body
    stored = await store.get(body["resultId"])
    assert stored is not None
    assert stored.ui == {"card": "안녕"}


async def test_ok_without_ui_has_null_result_id(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_no_ui")

    assert body == {"status": "ok", "llm": {"done": True}, "resultId": None}


async def test_need_clarification_returns_candidates(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_ambiguous")

    assert body["status"] == "need_clarification"
    assert body["field"] == "cafeteria"
    assert [c["value"] for c in body["candidates"]] == ["sangrok_3f", "sangrok_2f"]


async def test_tool_error_is_returned_as_status_error(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_fail")

    assert body["status"] == "error"
    assert body["error"]["code"] == "MENU_NOT_FOUND"
    assert body["error"]["message"] == "메뉴가 없습니다."


async def test_invalid_arguments_returns_details(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_echo", {})

    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_ARGUMENTS"
    assert body["error"]["details"][0]["loc"] == ["text"]


async def test_slow_tool_times_out(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_slow")

    assert body["status"] == "error"
    assert body["error"]["code"] == "TOOL_TIMEOUT"


async def test_unexpected_exception_hides_internal_detail(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_crash/invoke", json={"arguments": {}}, headers=HEADERS
    )

    assert response.json()["error"]["code"] == "TOOL_FAILED"
    assert "secret" not in response.text


async def test_wrong_return_type_is_tool_failed(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_bad_return")

    assert body["error"]["code"] == "TOOL_FAILED"


async def test_arguments_not_object_returns_400(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_echo/invoke", json={"arguments": "안녕"}, headers=HEADERS
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
```

**무슨 코드인가:**
- **`pytestmark = pytest.mark.anyio`**: 이 파일의 모든 테스트에 `@pytest.mark.anyio`를 붙인 것과 같다. 그래서 테스트를 `async def`로 쓰고 안에서 `await`할 수 있다. 팀원의 `test_auth.py`와 같은 방식이다.
- **가짜 tool 7개:** 설계 문서의 경우마다 하나씩 만들었다. 성공(`echo`), `ui` 없는 성공, 후보 반환, 예상된 실패, 시간 초과(`timeout=0.05`초), 예상 못 한 예외, 잘못된 반환값.
- **팀원 `conftest.py` 다시 쓰기:** `conftest.py`는 pytest가 자동으로 읽는 공용 준비 파일이다. 거기 있는 `client` fixture가 테스트용 DB와 `AsyncClient`를 만들어 주고, `settings` fixture 값으로 설정을 바꿔 끼운다.
  - 이 파일에서 **같은 이름의 `settings` fixture를 다시 정의**하면, 이 파일 안에서는 pytest가 가까운 쪽(이 파일)을 쓴다. 그래서 conftest의 `client`가 서비스 키가 들어간 설정으로 만들어진다.
  - `skills_client`: conftest의 `client`를 받아, 등록부와 보관소만 테스트용으로 더 바꿔 끼운다 (`app.dependency_overrides`). 원래대로 돌려놓는 일은 conftest의 `client`가 끝날 때 `clear()`로 해 준다.
- **`AsyncClient`**: 서버를 띄우지 않고 앱에 바로 요청을 보내는 httpx 클라이언트다. `await client.get(...)`처럼 쓴다.
- **인증 테스트:** 키 없음, 틀린 키, 한글 키 세 경우 모두 두 엔드포인트가 401을 주는지 본다. `ids`는 테스트 결과에 보일 이름이다. `test_empty_server_key_rejects_everyone`은 서버 키를 비웠을 때 빈 헤더로도 못 들어오는지 본다.
- **JSON 이름:** 응답은 camelCase라서 `body["resultId"]`, `["items"]`, `["inputSchema"]`로 꺼낸다.
- **`ok` 테스트의 핵심:** 응답에 `ui`가 **없고**, 대신 보관소에 `ui`가 **들어 있는지** 둘 다 확인한다.
- **예외 테스트:** 응답 본문에 내부 메시지(`secret`)가 새지 않는지 본다.

- [ ] **Step 2: 실패하는지 확인**

```powershell
uv run pytest tests/programs/test_skills_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.programs.dependencies'`

- [ ] **Step 3: 서비스 쓰기** — `app/programs/service.py`

```python
import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from app.common.exceptions import NotFoundException
from app.programs.registry import ToolRegistry
from app.programs.result_store import ResultStore, StoredResult
from app.programs.schemas import (
    ErrorInfo,
    InvokeErrorResponse,
    InvokeNeedClarificationResponse,
    InvokeOkResponse,
    InvokeResponse,
    ToolError,
    ToolInfo,
    ToolNeedClarification,
    ToolOk,
)

logger = logging.getLogger(__name__)


def list_tools(registry: ToolRegistry) -> list[ToolInfo]:
    return [
        ToolInfo(name=t.name, description=t.description, input_schema=t.input_schema())
        for t in registry.all()
    ]


def _error(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> InvokeErrorResponse:
    return InvokeErrorResponse(error=ErrorInfo(code=code, message=message, details=details))


async def invoke_tool(
    registry: ToolRegistry,
    store: ResultStore,
    name: str,
    arguments: dict[str, Any],
    default_timeout: float,
) -> InvokeResponse:
    registered = registry.get(name)
    if registered is None:
        raise NotFoundException("TOOL_NOT_FOUND", f"'{name}' tool이 없습니다.")

    try:
        args = registered.input_model.model_validate(arguments)
    except ValidationError as exc:
        details = exc.errors(include_url=False, include_context=False)
        return _error("INVALID_ARGUMENTS", "입력값이 올바르지 않습니다.", list(details))

    timeout = registered.timeout if registered.timeout is not None else default_timeout
    try:
        result = await asyncio.wait_for(registered.func(args), timeout=timeout)
    except TimeoutError:
        return _error("TOOL_TIMEOUT", f"{timeout}초 안에 끝나지 않았습니다.")
    except ToolError as exc:
        return _error(exc.code, exc.message, exc.details)
    except Exception:
        logger.exception("tool 실행 실패: %s", name)
        return _error("TOOL_FAILED", "tool 실행 중 오류가 났습니다.")

    if isinstance(result, ToolNeedClarification):
        return InvokeNeedClarificationResponse(
            field=result.field, message=result.message, candidates=result.candidates
        )
    if not isinstance(result, ToolOk):
        logger.error("tool이 ToolOk/ToolNeedClarification이 아닌 값을 반환했습니다: %s", name)
        return _error("TOOL_FAILED", "tool 실행 중 오류가 났습니다.")

    result_id = await store.put(name, result.ui) if result.ui is not None else None
    return InvokeOkResponse(llm=result.llm, result_id=result_id)


async def get_ui_result(store: ResultStore, result_id: str) -> StoredResult | None:
    """채팅 창구가 result_id로 ui를 꺼낼 때 쓴다."""
    return await store.get(result_id)
```

**무슨 코드인가:** 이 틀의 핵심 로직이다. HTTP를 모르고, 등록부와 보관소만 받아 일한다 (CLAUDE.md의 `router → service` 계층).
- `list_tools`: 등록된 tool을 API 응답 모양(`ToolInfo`)으로 바꾼다.
- `_error`: 에러 응답을 짧게 만들기 위한 도우미다.
- `invoke_tool`은 위에서 아래로 단계를 밟는다.
  1. 이름으로 tool을 찾는다. 없으면 Task 1의 `NotFoundException` → 팀원 처리기가 404로 바꾼다.
  2. `model_validate`로 `arguments`(그냥 dict)를 입력 모델로 바꾼다. 틀리면 200 + `INVALID_ARGUMENTS`이고, `details`에 어디가 틀렸는지 넣는다. `include_url=False, include_context=False`는 JSON으로 못 바꾸는 값과 쓸데없는 문서 주소를 뺀다.
  3. `asyncio.wait_for`로 시간 제한을 걸고 실행한다. tool에 `timeout`이 없으면 설정값(10초)을 쓴다.
  4. 예외를 종류별로 받는다. 시간 초과 → `TOOL_TIMEOUT`, `ToolError` → tool이 정한 코드 그대로, 그 밖의 모든 예외 → `TOOL_FAILED`. 마지막 경우는 `logger.exception`으로 서버 로그에 전체 내용을 남기고, 응답에는 일반 문구만 준다.
  5. 결과 종류를 확인한다. 후보면 그대로 넘기고, `ToolOk`도 후보도 아니면 프로그램 쪽 버그라 `TOOL_FAILED`.
  6. 성공이면 `ui`가 있을 때만 보관소에 넣고 `result_id`를 받는다. 응답에는 `llm`과 `result_id`만 넣는다 (JSON에서는 `resultId`).
- 파이썬 코드에서는 `result_id=...`처럼 snake_case로 넣는다. `CamelModel`의 `populate_by_name=True` 덕분에 둘 다 받아 준다.
- `get_ui_result`: 지금은 아무도 안 부른다. 다음 단계의 채팅 창구가 `ui`를 꺼낼 때 쓸 입구다.

- [ ] **Step 4: 의존성 쓰기** — `app/programs/dependencies.py`

```python
import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from app.common.exceptions import UnauthorizedException
from app.core.config import Settings, get_settings
from app.programs.registry import ToolRegistry, default_registry
from app.programs.result_store import MemoryResultStore, ResultStore


def verify_service_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_service_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.service_api_key
    if not expected or x_service_key is None:
        raise UnauthorizedException("서비스 키가 올바르지 않습니다.")
    if not secrets.compare_digest(x_service_key.encode(), expected.encode()):
        raise UnauthorizedException("서비스 키가 올바르지 않습니다.")


def get_registry() -> ToolRegistry:
    return default_registry


@lru_cache
def get_result_store() -> ResultStore:
    settings = get_settings()
    return MemoryResultStore(
        ttl_seconds=settings.result_ttl_seconds, max_items=settings.result_store_max_items
    )
```

**무슨 코드인가:** FastAPI의 `Depends`로 엔드포인트에 넣어 줄 것들이다.
- `verify_service_key`: 요청 헤더의 키를 검사한다.
  - `Header()`: 파라미터 이름 `x_service_key`를 헤더 `X-Service-Key`로 자동 연결한다 (밑줄 → 하이픈).
  - `if not expected`: 서버에 키가 설정되지 않았으면(빈 문자열) 무조건 거부한다. Task 2에서 기본값을 `""`로 둔 대가로 여기서 막는다.
  - `secrets.compare_digest`: 비교하는 데 걸리는 시간이 내용과 상관없이 같다. 그냥 `==`를 쓰면 응답 시간 차이로 키를 한 글자씩 알아내는 공격이 가능하다.
  - `.encode()`: 바이트로 바꿔서 비교한다. 문자열 그대로 넣으면 한글 같은 글자가 왔을 때 `compare_digest`가 예외를 내서 500이 된다 (Review Focus 4번).
  - 팀원의 `UnauthorizedException`을 그대로 쓴다. 기본 메시지는 "로그인이 필요합니다."라서 우리 상황에 맞는 메시지를 넘긴다.
- `get_registry`: 앱이 쓰는 등록부를 돌려준다. 함수로 감싼 이유는 테스트에서 `dependency_overrides`로 바꿔 끼우기 위해서다.
- `get_result_store`: 보관소를 만든다. `@lru_cache` 덕분에 앱 전체에서 **딱 하나**만 만들어진다. 요청마다 새로 만들면 넣은 `ui`를 다음 요청에서 못 찾는다. (`lru_cache`는 팀원의 `get_settings`와 같은 방식이다.)

- [ ] **Step 5: 라우터 쓰기** — `app/programs/router.py`

```python
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.schemas import ItemsResponse
from app.core.config import Settings, get_settings
from app.programs import service
from app.programs.dependencies import get_registry, get_result_store, verify_service_key
from app.programs.registry import ToolRegistry
from app.programs.result_store import ResultStore
from app.programs.schemas import InvokeRequest, InvokeResponse, ToolInfo

router = APIRouter(prefix="/api/v1/skills", dependencies=[Depends(verify_service_key)])


@router.get(
    "",
    response_model=ItemsResponse[ToolInfo],
    status_code=status.HTTP_200_OK,
    tags=["skills"],
    summary="tool 목록 (AI 서비스 전용)",
)
async def list_skills(
    registry: Annotated[ToolRegistry, Depends(get_registry)],
) -> ItemsResponse[ToolInfo]:
    return ItemsResponse(items=service.list_tools(registry))


@router.post(
    "/{name}/invoke",
    response_model=InvokeResponse,
    status_code=status.HTTP_200_OK,
    tags=["skills"],
    summary="tool 실행 (AI 서비스 전용)",
)
async def invoke_skill(
    name: str,
    body: InvokeRequest,
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[ResultStore, Depends(get_result_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvokeResponse:
    return await service.invoke_tool(
        registry, store, name, body.arguments, settings.tool_timeout_seconds
    )
```

**무슨 코드인가:** HTTP 입구다. 요청을 받아 service에 넘기기만 한다.
- `APIRouter(prefix=..., dependencies=[Depends(verify_service_key)])`: 이 라우터의 **모든** 엔드포인트가 먼저 서비스 키 검사를 거친다.
- `response_model`, `status_code`, `tags`: CLAUDE.md 규칙대로 모든 엔드포인트에 단다. `summary`는 Swagger 화면에 보이는 한 줄 설명이다 (팀원 `auth/router.py`와 같은 방식).
- `ItemsResponse[ToolInfo]`: 팀원이 만든 목록 응답 모델이다. `[ToolInfo]`는 "안에 든 게 `ToolInfo`"라는 뜻이고, JSON은 `{"items": [...]}`가 된다.
- `""` 경로: prefix와 합쳐져 `/api/v1/skills`가 된다.
- `body: InvokeRequest`: 요청 본문을 Pydantic이 검사한다. `arguments`가 객체가 아니면 여기서 팀원 처리기가 400 `VALIDATION_ERROR`를 준다.
- `Annotated[..., Depends(...)]`: "이 값은 이 함수가 만들어 준다"는 표시다. 테스트에서 바꿔 끼운 것도 여기로 들어온다.

- [ ] **Step 6: `app/main.py` 고치기** (공용 파일이다. PR 설명에 적는다)

바뀌는 곳은 세 군데다: import 3줄 추가, `lifespan` 함수 추가 후 `FastAPI(...)`에 넘기기, `include_router` 한 줄 추가.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.common.exceptions import register_exception_handlers
from app.core.config import get_settings
from app.programs.registry import load_programs
from app.programs.router import router as skills_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_programs()
    yield


app = FastAPI(title="GDG 1234 Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(auth_router)
app.include_router(skills_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
```

**무슨 코드인가:** CORS, 예외 처리기, `auth_router`, Hello World는 팀원 코드 그대로다.
- `lifespan`: 서버가 켜질 때 `yield` 앞이, 꺼질 때 `yield` 뒤가 실행된다. 켜질 때 `load_programs()`로 프로그램 tool을 등록한다. `@asynccontextmanager`는 이런 "앞뒤가 있는 함수"를 만들어 주는 도구다.
- `app.include_router(skills_router)`: `/api/v1/skills` 엔드포인트를 앱에 붙인다.

- [ ] **Step 7: 통과하는지 확인**

```powershell
uv run pytest tests/programs/test_skills_api.py -v
```

Expected: 15 passed

- [ ] **Step 8: 커밋**

```powershell
git add app/programs/service.py app/programs/dependencies.py app/programs/router.py app/main.py tests/programs/test_skills_api.py
git commit -m "feat: skill 목록·실행 API 추가"
```

---

### Task 6: 전체 확인, CLAUDE.md, PR

**Files:**
- Modify: `CLAUDE.md` (폴더 구조 부분)

- [ ] **Step 1: 전체 테스트와 린트**

```powershell
uv run pytest -q
```

Expected: 50 passed (팀원 14 + Task 3의 16 + Task 4의 5 + Task 5의 15)

```powershell
uv run ruff check .
```

```powershell
uv run ruff format --check .
```

Expected: `All checks passed!`, `... files already formatted`. 포맷이 틀렸다고 나오면 `uv run ruff format .`을 한 번 돌린다.

- [ ] **Step 2: 서버를 띄워 직접 보기**

```powershell
uv run fastapi dev app/main.py
```

http://127.0.0.1:8000/docs 에서 `skills` 묶음에 엔드포인트 2개가 보인다. 요청할 때 `x-service-key` 칸에 `.env`의 키를 넣는다. 아직 등록된 프로그램이 없어서 목록은 `{"items": []}`가 정상이다.

- [ ] **Step 3: CLAUDE.md 폴더 구조 고치기**

`CLAUDE.md`의 폴더 구조 코드 블록에서 `└── programs/` 부분을 아래로 바꾼다.

```
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
```

그 아래 목록에 한 줄을 추가한다.

```
- 새 프로그램은 `tools.py`에 `@tool` 함수를 만들고 `app/programs/registry.py`의 `PROGRAM_MODULES`에 한 줄 추가한다. tool 이름은 `<프로그램>_<기능>` (예: `cafeteria_get_menu`).
```

- [ ] **Step 4: 커밋하고 PR 올리기**

```powershell
git add CLAUDE.md docs/superpowers/specs/2026-11-18-skill-framework-design.md docs/superpowers/plans/2026-11-18-skill-framework.md
git commit -m "docs: skill 틀 설계·구현 문서와 CLAUDE.md 구조 추가"
```

```powershell
git push -u origin feat/skills-framework
```

PR 설명에 적을 것 (공용 파일 변경 알림):
- 공용 파일: `app/main.py`(lifespan, skills 라우터), `app/core/config.py`(필드 4개), `app/common/exceptions.py`(`NotFoundException`), `.env.example`
- 새 패키지 없음
- 새 환경변수: `SERVICE_API_KEY`(비면 skills API 전부 거부), `TOOL_TIMEOUT_SECONDS`, `RESULT_TTL_SECONDS`, `RESULT_STORE_MAX_ITEMS`. 배포에 `SERVICE_API_KEY`를 넣는 방법(Secret Manager)은 배포 담당과 맞춘다.
- 알아 둘 점: `ui` 보관이 메모리라 Cloud Run 최대 인스턴스 2에서는 채팅 창구가 붙을 때 문제가 된다. 채팅 창구 전에 DB 보관으로 바꿀 예정.
- 설계 문서: `docs/superpowers/specs/2026-11-18-skill-framework-design.md`
