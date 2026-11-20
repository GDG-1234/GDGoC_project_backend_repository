# 학식·공지 skill 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 채팅 AI가 부르는 tool 3개(`cafeteria_get_menu`, `notice_search`, `notice_get_detail`)를 skill 틀 위에 만든다.

**Architecture:** 프로그램마다 `tools → service → source` 3층. `source.py`가 학교 사이트를 httpx로 읽고 BeautifulSoup으로 파싱해 Pydantic 모델로 바꾸며, 결과를 공용 `TtlCache`(메모리, 신선/오래된 값 구분)에 둔다. `service.py`가 tool 입력을 해석하고 `ToolOk(llm, ui)` / `ToolNeedClarification` / `ToolError`로 바꾼다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, httpx, beautifulsoup4(`html.parser`), pytest + anyio

**Spec:** `docs/superpowers/specs/2026-11-19-cafeteria-notice-design.md` (기반 틀: `feat/skills-framework` 브랜치의 `docs/superpowers/specs/2026-11-18-skill-framework-design.md`)

## Global Constraints

- 브랜치 `feat/skills-cafeteria-notice`, `feat/skills-framework`에서 갈라진다. main에 직접 push 금지.
- **커밋은 사용자에게 묻고 한다.** 커밋 메시지 `<type>: <한글 설명>`, 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- tool 이름 `<프로그램>_<기능>`. tool 함수는 `async def`, 인자는 `BaseModel` 하나. 반환은 `ToolOk | ToolNeedClarification`, 예상된 실패는 `raise ToolError(code, message)`.
- 테스트는 네트워크에 접속하지 않는다. HTTP는 각 `source.py`의 모듈 변수 `HTTP_TRANSPORT`를 `httpx.MockTransport`로 바꿔서 막는다.
- HTTP 요청 시간 제한 5초. 학식 페이지는 cp949로 디코드. User-Agent는 `"Mozilla/5.0 (compatible; gdg1234-bot)"` (개인 정보 없음).
- 캐시 신선 시간: 학식 600초, 공지 목록 300초, 공지 본문 1800초. 오래된 값 허용 86,400초. 공지 본문 캐시 최대 300개, 나머지 500개.
- 에러 코드: `SOURCE_UNAVAILABLE`(접속 실패, 캐시 없음), `SOURCE_CHANGED`(구조 변경), `NOTICE_NOT_FOUND`(본문 302).
- 공지 본문 최대 4,000자, 50자 미만이면 `bodyIsImage: true`.
- `llm`/`ui` 안의 키는 camelCase (`articleId`, `bodyIsImage`, `failedBoards`). 내부 모델은 `CamelModel`을 쓰고 `model_dump(mode="json", by_alias=True)`로 낸다.
- 공용 파일 변경(PR 설명에 적는다): `pyproject.toml`, `uv.lock`(beautifulsoup4, httpx), `app/common/cache.py`(새 파일), `app/programs/registry.py`(두 줄).
- 저장해 둔 테스트 페이지(2026-11-19 받음): `C:/Users/alfre/AppData/Local/Temp/claude/5a6dfc3217a7b92d/89eaa29f-dd47-43af-be49-6a69d8cf69d3/scratchpad/fixtures/`. 없어졌으면 각 Task의 curl 명령으로 다시 받되, 그날 내용이 달라지므로 테스트 기대값을 새 페이지에 맞춘다.

## Review Focus

1. 학교 사이트가 시간 초과이고 캐시도 없을 때 → invoke 응답이 200 + `status: "error"`, `code: "SOURCE_UNAVAILABLE"` (500 아님). → Task 3 `test_invoke_source_down`.
2. 캐시가 만료된 뒤 사이트가 죽었을 때 → 오래된 값으로 답하고 `llm.stale == true`. → Task 3 `test_get_menu_stale_when_source_down`.
3. 검색어에 `&`, 공백, 한글이 섞일 때 → 주소가 깨지지 않게 인코딩. → Task 4 `test_list_url_encodes_keyword`.
4. AI가 다른 게시판 코드로 본문을 요청했을 때(사이트가 302로 `/main`에 보냄) → `NOTICE_NOT_FOUND`, 메인 페이지를 본문으로 파싱하지 않음. → Task 4 `test_fetch_detail_redirect_is_not_found`.
5. 같은 질문이 동시에 몰릴 때 → 학교 사이트 요청은 한 번. → Task 1 `test_concurrent_misses_load_once`.

---

### Task 1: 브랜치·패키지 준비와 공용 TTL 캐시

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (`uv add`로만)
- Create: `app/common/cache.py`
- Test: `tests/common/__init__.py`(없으면), `tests/common/test_cache.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class CacheResult[T]:
      value: T
      stale: bool


  class TtlCache[T]:
      def __init__(
          self,
          fresh_seconds: float,
          stale_seconds: float = 86_400,
          max_items: int = 500,
          clock: Callable[[], float] = time.monotonic,
      ) -> None: ...
      async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> CacheResult[T]: ...
  ```

- [ ] **Step 1: 브랜치를 만들고 패키지를 추가한다**

```bash
git switch -c feat/skills-cafeteria-notice feat/skills-framework
uv add beautifulsoup4 httpx
```
확인: `uv run python -c "import bs4, httpx"`가 에러 없이 끝난다. 사용자에게 "HTML 파싱용 beautifulsoup4, 직접 쓰는 httpx를 추가했다"고 알린다.

- [ ] **Step 2: 실패하는 테스트를 쓴다** (`tests/common/test_cache.py`, `pytestmark = pytest.mark.anyio`, 가짜 시계 `now = [0.0]; clock=lambda: now[0]`)

```python
async def test_fresh_value_is_reused():           # loader 호출 1번, 두 번째 결과 stale False
async def test_reload_after_fresh_expires():       # fresh 10, now=11 → loader 2번, 새 값
async def test_stale_value_when_reload_fails():    # 첫 값 "a" → now=11, loader가 RuntimeError → CacheResult("a", stale=True)
async def test_raise_when_reload_fails_and_too_old():  # stale_seconds 100, now=200 → RuntimeError 그대로
async def test_raise_when_first_load_fails():      # 캐시 없음 + 실패 → 예외 그대로
async def test_failure_is_not_cached():            # 실패 후 다음 호출이 loader를 다시 부른다
async def test_oldest_evicted_over_max_items():    # max_items 2, 키 a,b,c 저장 → a는 다시 loader 호출
async def test_concurrent_misses_load_once():
    # loader가 await anyio.sleep(0.01) 후 값 반환, 호출 수를 센다
    # asyncio.gather로 같은 키 5번 → 호출 수 1, 결과 모두 같은 값
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/common/test_cache.py -v`
Expected: FAIL (`ModuleNotFoundError: app.common.cache`)

- [ ] **Step 4: `app/common/cache.py`를 구현한다**

항목은 `dict[str, tuple[T, float]]`(값, 저장 시각). 키별 `asyncio.Lock`(`dict[str, asyncio.Lock]`). 순서:
1. 신선하면 바로 반환.
2. 아니면 키 잠금을 잡고 다시 확인(그 사이 다른 요청이 채웠을 수 있다).
3. `loader()` 성공 → 저장(넘치면 저장 시각이 가장 오래된 것 삭제) 후 `stale=False`.
4. 실패 → 항목이 있고 `나이 <= stale_seconds`면 `stale=True`로 반환, 아니면 다시 raise.

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/common/test_cache.py -v` → 8 passed
Run: `uv run ruff check app/common/cache.py tests/common` → All checks passed

- [ ] **Step 6: 커밋 (사용자 확인 후)**

```bash
git add pyproject.toml uv.lock app/common/cache.py tests/common
git commit -m "feat: 학교 사이트 조회용 공용 TTL 캐시 추가"
```

---

### Task 2: 학식 페이지 읽기·파싱 (`cafeteria/source.py`)

**Files:**
- Create: `app/programs/cafeteria/__init__.py`, `app/programs/cafeteria/schemas.py`, `app/programs/cafeteria/source.py`
- Create: `tests/programs/cafeteria/__init__.py`, `tests/programs/cafeteria/fixtures/cafeteria_2026-11-19.html`, `.../cafeteria_2026-11-22.html`
- Test: `tests/programs/cafeteria/test_source.py`

**Interfaces:**
- Consumes: `TtlCache`, `CacheResult` (Task 1)
- Produces:
  ```python
  # schemas.py
  class GetMenuInput(BaseModel):
      date: dt.date | None = Field(None, description="조회할 날짜 YYYY-MM-DD. 없으면 오늘(한국 시간)")
      cafeteria: str | None = Field(None, description="식당 이름 일부. 예: 3층, 2층, 솥앤누들, 교직원식당. 없으면 전체")
  class MealMenu(CamelModel): meal: str; corner: str | None; menu: str
  class Cafeteria(CamelModel): name: str; closed: bool; meals: list[MealMenu]
  class DayMenu(CamelModel): date: dt.date; cafeterias: list[Cafeteria]

  # source.py
  KST = ZoneInfo("Asia/Seoul")
  BASE_URL = "https://dgucoop.dongguk.edu/store/store.php"
  HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None
  class PageFormatError(Exception): ...
  def day_url(day: dt.date) -> str
  def parse_day_page(html: str, day: dt.date) -> DayMenu        # raises PageFormatError
  async def fetch_day_page(day: dt.date) -> str                   # raises httpx.HTTPError
  day_menu_cache: TtlCache[DayMenu]                               # fresh 600
  async def load_day_menu(day: dt.date) -> CacheResult[DayMenu]   # 키: day.isoformat()
  ```

- [ ] **Step 1: 테스트 페이지를 복사한다**

```bash
mkdir -p tests/programs/cafeteria/fixtures
FX="C:/Users/alfre/AppData/Local/Temp/claude/5a6dfc3217a7b92d/89eaa29f-dd47-43af-be49-6a69d8cf69d3/scratchpad/fixtures"
cp "$FX/cafeteria_2026-11-19.html" "$FX/cafeteria_2026-11-22.html" tests/programs/cafeteria/fixtures/
# 없어졌으면: curl -o tests/programs/cafeteria/fixtures/cafeteria_2026-11-19.html "https://dgucoop.dongguk.edu/store/store.php?w=4&l=1&sday=1795014000"  (22일은 sday=1795273200)
```
파일은 cp949 원본 그대로 둔다(변환 금지). `.gitattributes`가 줄바꿈을 바꾸지 않는지 `git diff --stat`으로 확인.

- [ ] **Step 2: 실패하는 테스트를 쓴다** (`tests/programs/cafeteria/test_source.py`, 페이지는 `read_bytes().decode("cp949")`)

```python
def test_day_url():
    assert day_url(dt.date(2026, 11, 19)) == f"{BASE_URL}?w=4&l=1&sday=1795014000"
    assert day_url(dt.date(2026, 11, 16)).endswith("sday=1794754800")

def test_parse_weekday_page():
    menu = parse_day_page(html_19, dt.date(2026, 11, 19))
    assert [c.name for c in menu.cafeterias] == ["상록원3층식당", "상록원2층식당", "상록원1층식당(솥앤누들)"]
    # 주석 안 식당(그루터기 등)과 일산 식당이 없다
    third, second, first = menu.cafeterias
    assert [(m.meal, m.corner) for m in third.meals] == [("중식", "집밥"), ("중식", "한그릇(한정판매)"), ("석식", "집밥")]
    assert third.meals[0].menu.startswith("김치가츠나베(뚝)\n(돼지:국내산)")   # '이름'이름 찌꺼기 제거
    assert "￦7,000" in third.meals[0].menu
    assert [(m.meal, m.corner) for m in second.meals] == [("중식", "일품코너"), ("중식", "양식코너"), ("중식", "뚝배기코너")]
    assert [(m.meal, m.corner) for m in first.meals] == [("중·석식", "메뉴"), ("중·석식", None)]
    assert first.meals[0].menu.startswith("****솥밥****") and first.meals[1].menu.startswith("****누들****")
    assert not any(c.closed for c in menu.cafeterias)

def test_parse_closed_day():
    menu = parse_day_page(html_22, dt.date(2026, 11, 22))
    assert len(menu.cafeterias) == 3
    assert all(c.closed and c.meals == [] for c in menu.cafeterias)

def test_header_date_mismatch_raises():   # html_19를 2026-11-20으로 → PageFormatError
def test_page_without_tables_raises():    # "<html><body></body></html>" → PageFormatError

async def test_fetch_decodes_cp949(monkeypatch):
    # MockTransport가 html_19 바이트를 돌려준다. 요청 URL이 day_url(...)과 같은지도 확인
    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    assert "상록원3층식당" in await fetch_day_page(dt.date(2026, 11, 19))

async def test_fetch_http_error_raises(monkeypatch):   # 500 응답 → httpx.HTTPStatusError
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/programs/cafeteria/test_source.py -v` → FAIL (모듈 없음)

- [ ] **Step 4: `schemas.py`, `source.py`를 구현한다**

- `day_url`: `sday = int(dt.datetime.combine(day, dt.time(), tzinfo=KST).timestamp())`.
- `parse_day_page` (BeautifulSoup `html.parser`, 주석 안 태그는 자동으로 무시된다):
  1. `span.menu_date` 텍스트의 `(\d+)월 (\d+)일`이 `day.month, day.day`와 다르거나 없으면 `PageFormatError`. `td.menu_st`가 없어도 `PageFormatError`.
  2. 각 `td.menu_st`: 이름에 `일산`이 있으면 건너뛴다. 메뉴 표는 `td.find_parent("table").find_next("table")`.
  3. 표의 직계 `tr`들: 첫 행 직계 `td` 텍스트 = 머리(`[구분, 코너…]`). 나머지 행마다 첫 칸 = 끼니, 이어지는 칸 i번째의 코너 = `머리[i+1]`(없으면 `None`).
  4. 칸 텍스트는 `get_text("\n", strip=True)`. 빈 칸·`휴무` 칸 버림. 첫 줄이 `^'(.+)'\1$`이면 `\1`로.
  5. 남은 칸이 없으면 `closed=True, meals=[]`.
- `fetch_day_page`: `httpx.AsyncClient(transport=HTTP_TRANSPORT, timeout=5, headers={"User-Agent": ...})`로 GET, `raise_for_status()`, `response.content.decode("cp949", errors="replace")`.
- `load_day_menu`: `day_menu_cache.get_or_load(day.isoformat(), lambda: _load(day))`, `_load`은 fetch 후 parse.

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/programs/cafeteria/test_source.py -v` → 7 passed

- [ ] **Step 6: 커밋 (사용자 확인 후)** — `feat: 생협 학식 페이지 파싱 추가`

---

### Task 3: `cafeteria_get_menu` tool

**Files:**
- Create: `app/programs/cafeteria/service.py`, `app/programs/cafeteria/tools.py`
- Modify: `app/programs/registry.py` (`PROGRAM_MODULES`에 `"app.programs.cafeteria.tools"`)
- Test: `tests/programs/cafeteria/test_service.py`, `tests/programs/cafeteria/test_tools.py`

**Interfaces:**
- Consumes: Task 2 전부, `ToolOk`, `ToolNeedClarification`, `Candidate`, `ToolError` (`app.programs.schemas`), `tool` (`app.programs.registry`)
- Produces:
  ```python
  # service.py
  ALIASES: dict[str, tuple[str, ...]] = {
      "상록원3층식당": ("3층", "교직원"),
      "상록원2층식당": ("2층", "학생식당"),
      "상록원1층식당(솥앤누들)": ("1층", "솥앤누들", "솥밥", "누들"),
  }
  ALL_CLOSED_NOTE = "이 날은 모든 식당이 휴무이거나 아직 식단이 올라오지 않았습니다."
  def today_kst() -> dt.date
  def match_cafeterias(query: str, names: list[str]) -> list[str]
  async def get_menu(args: GetMenuInput, today: dt.date) -> ToolOk | ToolNeedClarification
  # tools.py
  @tool(name="cafeteria_get_menu", description="동국대 서울캠퍼스 상록원 학생식당(1~3층) 메뉴를 날짜별로 조회한다.")
  async def get_menu(args: GetMenuInput) -> ToolOk | ToolNeedClarification
  ```

- [ ] **Step 1: 실패하는 service 테스트를 쓴다** (`test_service.py`. autouse fixture로 `source.day_menu_cache`를 새 `TtlCache(fresh_seconds=600)`로, `source.HTTP_TRANSPORT`를 html_19/html_22를 날짜(`sday`)에 맞춰 돌려주는 MockTransport로 바꾼다)

```python
NAMES = ["상록원3층식당", "상록원2층식당", "상록원1층식당(솥앤누들)"]

def test_match_cafeterias():
    assert match_cafeterias("3층", NAMES) == ["상록원3층식당"]
    assert match_cafeterias("교직원 식당", NAMES) == ["상록원3층식당"]
    assert match_cafeterias("상록원학생식당", NAMES) == ["상록원2층식당"]
    assert match_cafeterias("솥앤누들", NAMES) == ["상록원1층식당(솥앤누들)"]
    assert match_cafeterias("상록원", NAMES) == NAMES
    assert match_cafeterias("그루터기", NAMES) == []

async def test_get_menu_today_all():
    r = await get_menu(GetMenuInput(), today=dt.date(2026, 11, 19))
    assert isinstance(r, ToolOk)
    assert r.llm["date"] == "2026-11-19" and r.llm["today"] == "2026-11-19"
    assert r.llm["stale"] is False and r.llm["note"] is None
    assert [c["name"] for c in r.llm["cafeterias"]] == NAMES
    assert r.ui["url"].endswith("sday=1795014000")

async def test_get_menu_one_cafeteria():          # cafeteria="3층" → cafeterias 1개, 이름 상록원3층식당
async def test_get_menu_other_date():             # date=2026-11-22, today=11-19 → 모두 closed, note == ALL_CLOSED_NOTE
async def test_get_menu_ambiguous():              # cafeteria="상록원" → ToolNeedClarification(field="cafeteria"), 후보 value 3개 == NAMES
async def test_get_menu_unknown_cafeteria():      # cafeteria="그루터기" → ToolNeedClarification, 후보 3개 전부
async def test_get_menu_source_down():            # MockTransport가 httpx.ConnectTimeout → ToolError code "SOURCE_UNAVAILABLE"
async def test_get_menu_source_changed():         # MockTransport가 빈 html → ToolError code "SOURCE_CHANGED"
async def test_get_menu_stale_when_source_down():
    # 가짜 시계 캐시로 한 번 성공 → 시계를 601초 넘기고 MockTransport를 ConnectTimeout으로 → llm["stale"] is True, 메뉴는 그대로
```

- [ ] **Step 2: 실패하는 tool 테스트를 쓴다** (`test_tools.py`. `import app.programs.cafeteria.tools`로 등록. `settings` fixture를 `Settings(database_url="sqlite+aiosqlite://", service_api_key="test-key")`로 다시 정의, 헤더 `{"X-Service-Key": "test-key"}`. `monkeypatch.setattr(service, "today_kst", lambda: dt.date(2026, 11, 19))`, 캐시·transport는 Step 1과 같은 fixture)

```python
async def test_tool_listed(client):     # GET /api/v1/skills → items에 name "cafeteria_get_menu", inputSchema.properties에 "date", "cafeteria"
async def test_invoke_ok(client):       # POST .../cafeteria_get_menu/invoke {"arguments": {}} → status "ok", llm.date "2026-11-19", resultId가 "r_"로 시작
async def test_invoke_bad_date(client): # {"arguments": {"date": "어제"}} → status "error", error.code "INVALID_ARGUMENTS"
async def test_invoke_source_down(client):  # ConnectTimeout → 200, status "error", error.code "SOURCE_UNAVAILABLE"
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/programs/cafeteria -v` → 새 테스트 FAIL

- [ ] **Step 4: `service.py`, `tools.py`를 구현하고 등록한다**

- 정규화: 공백과 `()` 제거. `match_cafeterias`: `q in 정규화(이름)` 또는 `any(별칭 in q for 별칭 in ALIASES.get(이름, ()))`인 이름들을, `names` 순서대로.
- `get_menu`: 날짜 = `args.date or today`. `load_day_menu` 호출, `httpx.HTTPError` → `ToolError("SOURCE_UNAVAILABLE", "학식 사이트에 접속하지 못했습니다.")`, `PageFormatError` → 로그(`logger.warning`) 후 `ToolError("SOURCE_CHANGED", "학식 사이트 형식이 바뀌어 메뉴를 읽지 못했습니다.")`.
- 식당 선택: `args.cafeteria`가 있으면 `match_cafeterias`. 0개 → 전체 후보, 2개 이상 → 그 후보로 `ToolNeedClarification(field="cafeteria", message="어느 식당인지 골라 주세요.", candidates=[Candidate(value=n, label=n)...])`.
- `llm = {"date", "today", "stale", "note", "cafeterias": [c.model_dump(mode="json", by_alias=True)...]}`. 고른 식당이 모두 `closed`면 `note = ALL_CLOSED_NOTE`. `ui = {**llm, "url": day_url(날짜)}`.
- `tools.py`는 `service.today_kst()`를 **모듈 이름으로** 부른다 (테스트에서 바꿔 넣기 위해).
- `registry.py`의 `PROGRAM_MODULES`에 `"app.programs.cafeteria.tools"`.

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/programs/cafeteria -v` → all passed
Run: `uv run pytest` → 기존 테스트 포함 전부 통과

- [ ] **Step 6: 커밋 (사용자 확인 후)** — `feat: 학식 메뉴 조회 tool 추가`

---

### Task 4: 공지 페이지 읽기·파싱 (`notice/source.py`)

**Files:**
- Create: `app/programs/notice/__init__.py`, `app/programs/notice/schemas.py`, `app/programs/notice/source.py`
- Create: `tests/programs/notice/__init__.py`, `tests/programs/notice/fixtures/` (아래 4개)
- Test: `tests/programs/notice/test_source.py`

**Interfaces:**
- Consumes: `TtlCache`, `CacheResult` (Task 1)
- Produces:
  ```python
  # schemas.py
  class NoticeBoard(StrEnum): general, academic, scholarship, admission, research, event, international, foreign_student, safety
  BOARD_CODES: dict[NoticeBoard, str] = {general: "GENERALNOTICES", academic: "HAKSANOTICE", scholarship: "JANGHAKNOTICE",
      admission: "IPSINOTICE", research: "HAKSULNOTICE", event: "BUDDHISTEVENT", international: "INTEXNOTICE",
      foreign_student: "INTSTUNOTICE", safety: "SAFENOTICE"}
  class SearchInput(BaseModel):   # 스펙 6-4 그대로 (board None 기본, keyword 1~50자, limit 5 / 1~10)
  class DetailInput(BaseModel):   # 스펙 6-5 그대로 (board 필수, article_id > 0)
  class NoticeItem(CamelModel): board: NoticeBoard; article_id: int; title: str; date: dt.date; views: int; pinned: bool; url: str
  class NoticeList(CamelModel): pinned: list[NoticeItem]; regular: list[NoticeItem]
  class Attachment(CamelModel): name: str; url: str
  class NoticeDetail(CamelModel): board: NoticeBoard; article_id: int; title: str; date: dt.date; views: int
      body: str; truncated: bool; body_is_image: bool; attachments: list[Attachment]; url: str

  # source.py
  BASE_URL = "https://www.dongguk.edu"
  MAX_BODY_CHARS = 4000; IMAGE_BODY_THRESHOLD = 50
  HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None
  class PageFormatError(Exception): ...
  class NoticeNotFoundError(Exception): ...
  def list_url(board: NoticeBoard, keyword: str | None) -> str
  def detail_url(board: NoticeBoard, article_id: int) -> str
  def parse_list(html: str, board: NoticeBoard) -> NoticeList          # raises PageFormatError
  def parse_detail(html: str, board: NoticeBoard, article_id: int) -> NoticeDetail   # raises PageFormatError
  def html_to_text(element: Tag) -> str
  async def fetch_list_page(board: NoticeBoard, keyword: str | None) -> str
  async def fetch_detail_page(board: NoticeBoard, article_id: int) -> str   # 3xx → NoticeNotFoundError
  list_cache: TtlCache[NoticeList]       # fresh 300, 키 f"{board}|{keyword or ''}"
  detail_cache: TtlCache[NoticeDetail]   # fresh 1800, max_items 300, 키 f"{board}|{article_id}"
  async def load_list(board: NoticeBoard, keyword: str | None) -> CacheResult[NoticeList]
  async def load_detail(board: NoticeBoard, article_id: int) -> CacheResult[NoticeDetail]
  ```

- [ ] **Step 1: 테스트 페이지를 복사한다** (scratchpad `fixtures/`에서 `tests/programs/notice/fixtures/`로)

| 파일 | 원래 주소 (없어졌을 때 다시 받기) |
|---|---|
| `notice_general_list.html` | `https://www.dongguk.edu/article/GENERALNOTICES/list` |
| `notice_scholarship_search.html` | `https://www.dongguk.edu/article/JANGHAKNOTICE/list?searchCondition=TA.SUBJECT&searchKeyword=%EA%B5%AD%EA%B0%80&pageIndex=1` |
| `notice_scholarship_26767024.html` | `https://www.dongguk.edu/article/JANGHAKNOTICE/detail/26767024` |
| `notice_general_26767048.html` | `https://www.dongguk.edu/article/GENERALNOTICES/detail/26767048` |

- [ ] **Step 2: 실패하는 테스트를 쓴다** (`test_source.py`, 페이지는 utf-8)

```python
def test_list_url():
    assert list_url(NoticeBoard.general, None) == "https://www.dongguk.edu/article/GENERALNOTICES/list?pageIndex=1"
    assert list_url(NoticeBoard.scholarship, "국가") == ("https://www.dongguk.edu/article/JANGHAKNOTICE/list?pageIndex=1"
        "&searchCondition=TA.SUBJECT&searchKeyword=%EA%B5%AD%EA%B0%80")  # 제목만 (Task 6에서 변경)

def test_list_url_encodes_keyword():
    assert "searchKeyword=%EA%B5%AD%EA%B0%80+%26+a" in list_url(NoticeBoard.general, "국가 & a")

def test_parse_general_list():
    lst = parse_list(general_list_html, NoticeBoard.general)
    assert [i.article_id for i in lst.pinned] == [26767048, 26767047, 26767044, 26767036, 26767030, 26767012]
    assert all(i.pinned for i in lst.pinned) and not any(i.pinned for i in lst.regular)
    assert len(lst.regular) == 10 and lst.regular[-1].article_id == 26767004
    first = lst.regular[0]
    assert first.title == "[동국대학교 인권센터] 2026학년도 인권실태조사 참여 안내 (2026.11.17~11.24)"   # "공지" 접두어 없음
    assert first.date == dt.date(2026, 11, 19) and first.views == 291
    assert first.url == "https://www.dongguk.edu/article/GENERALNOTICES/detail/26767048"

def test_parse_search_list():      # scholarship 검색 페이지 → pinned 10개, regular 10개, regular[0].article_id == 26767028
def test_parse_list_without_board_raises():   # "<html></html>" → PageFormatError

def test_parse_detail_with_attachments():
    d = parse_detail(scholarship_detail_html, NoticeBoard.scholarship, 26767024)
    assert d.title.startswith("2026학년도 국가우수장학금(이공계)")
    assert d.date == dt.date(2026, 11, 18) and d.views == 879
    assert d.truncated is False and d.body_is_image is False
    first_line = d.body.splitlines()[0]
    assert "자연과학" in first_line and "공학계열" in first_line     # 인라인 태그를 한 줄로 잇는다
    name = "2026-2학기 국가우수(이공계)장학 일시지원유형 신청서.hwp"
    assert d.attachments[0] == Attachment(name=name, url="https://www.dongguk.edu/cmmn/fileDown.do?filename="
        + quote(name, safe="") + "&filepath=/files/article/JANGHAKNOTICE/26767024/&filerealname=91093BC65F6B4100A6C9CFE56B08FC3F.hwp")
    assert len(d.attachments) == 2

def test_parse_detail_without_attachments():
    d = parse_detail(general_detail_html, NoticeBoard.general, 26767048)
    assert d.attachments == []                                        # 꼬리말 pdf 링크는 첨부가 아님
    assert d.body.splitlines()[0] == "[동국대학교 인권센터] 2026학년도 인권실태조사 참여 안내"
    assert "https://forms.gle/1Hmey68SP2vxuStQA" in d.body
    assert "$(document)" not in d.body                                # script 제거
    assert d.views == 292

def test_parse_detail_truncates():     # view_cont에 "가" * 5000인 최소 html → len(body) == 4000, truncated True
def test_parse_detail_image_only():    # view_cont에 <img>만 → body_is_image True
def test_parse_detail_without_view_cont_raises():   # PageFormatError

async def test_fetch_detail_redirect_is_not_found(monkeypatch):
    # MockTransport가 302 + Location: /main → NoticeNotFoundError (리다이렉트를 따라가지 않는다)
async def test_fetch_list_requests_list_url(monkeypatch):   # 요청 URL == list_url(...), 응답 텍스트 반환
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/programs/notice/test_source.py -v` → FAIL

- [ ] **Step 4: `schemas.py`, `source.py`를 구현한다**

- `list_url`: `urlencode`로 `pageIndex=1`, 검색어가 있으면 이어서 `searchCondition="TA.SUBJECT"` (Task 6에서 제목만으로 변경), `searchKeyword=keyword` (이 순서).
- `parse_list`: `div.board_list`가 없으면 `PageFormatError`. 각 `li`의 `a[onclick]`에서 `goDetail\((\d+)\)`. `span.fix`가 있으면 pinned 목록, 없으면 regular 목록. 제목은 `p.tit`에서 `span.mobile`을 지운 뒤 `get_text(strip=True)`. `div.info span` 첫째 `2026.11.19.` → 날짜, 둘째 `조회 291` → 숫자.
- `parse_detail`: `div.board_view div.view_cont`가 없으면 `PageFormatError`. 제목 `div.board_view div.tit > p`, info span `등록일 2026.11.18.`, `조회 879`. 본문은 `html_to_text`, 4,000자 넘으면 자르고 `truncated`. 50자 미만이면 `body_is_image`. 첨부는 `div.view_files li a`의 `href`에서 `downGO\('(.*?)','(.*?)','(.*?)'\)` → 위 테스트의 URL 형식.
- `html_to_text`: 이 알고리즘대로 (BeautifulSoup `get_text("\n")`은 인라인 태그마다 줄을 끊어서 쓰지 않는다).
  ```python
  # 1) script, style 삭제  2) <br>을 "\n" 문자열로 교체
  # 3) td, th 뒤에 " | "  4) p, div, li, tr, table, h1~h6 뒤에 "\n"
  # 5) get_text("")  6) 줄마다 \xa0→공백, 연속 공백 1개로, strip, " | "로 끝나면 떼기  7) 빈 줄 버리고 "\n".join
  ```
- `fetch_detail_page`: `follow_redirects=False`. `response.is_redirect`면 `NoticeNotFoundError`, 아니면 `raise_for_status()` 후 `response.text`.
- `load_list` / `load_detail`: 캐시 키는 Interfaces 그대로, 로더는 fetch 후 parse.

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/programs/notice/test_source.py -v` → all passed

- [ ] **Step 6: 커밋 (사용자 확인 후)** — `feat: 학교 공지 목록·본문 파싱 추가`

---

### Task 5: `notice_search`, `notice_get_detail` tool

**Files:**
- Create: `app/programs/notice/service.py`, `app/programs/notice/tools.py`
- Modify: `app/programs/registry.py` (`"app.programs.notice.tools"` 추가)
- Test: `tests/programs/notice/test_service.py`, `tests/programs/notice/test_tools.py`

**Interfaces:**
- Consumes: Task 4 전부, 틀의 `ToolOk`, `ToolError`, `tool`
- Produces:
  ```python
  DEFAULT_BOARDS = (NoticeBoard.general, NoticeBoard.academic, NoticeBoard.scholarship)
  def merge_items(lists: list[NoticeList], with_pinned: bool, limit: int) -> list[NoticeItem]
  async def search(args: SearchInput) -> ToolOk
  async def get_detail(args: DetailInput) -> ToolOk
  # tools.py
  @tool(name="notice_search", description="동국대 홈페이지 공지사항 최근 글을 찾는다. 본문이 필요하면 결과의 board, articleId로 notice_get_detail을 부른다.")
  @tool(name="notice_get_detail", description="동국대 공지사항 글 하나의 본문과 첨부파일 목록을 가져온다. board와 articleId는 notice_search 결과에서 쓴다.")
  ```

- [ ] **Step 1: 실패하는 service 테스트를 쓴다** (autouse fixture로 `list_cache`, `detail_cache`를 새 캐시로, `HTTP_TRANSPORT`를 URL 경로·검색어에 따라 fixture를 돌려주는 MockTransport로)

```python
def test_merge_with_pinned():
    items = merge_items([parse_list(general_list_html, NoticeBoard.general)], with_pinned=True, limit=5)
    assert [i.article_id for i in items] == [26767048, 26767047, 26767044, 26767036, 26767030]
    assert all(i.pinned for i in items)          # 일반 목록의 중복은 고정 표시를 유지한 채 하나로

def test_merge_search_drops_pinned_list():
    items = merge_items([parse_list(search_html, NoticeBoard.scholarship)], with_pinned=False, limit=3)
    assert [i.article_id for i in items] == [26767028, 26767024, 26766019]
    assert not any(i.pinned for i in items)

async def test_search_one_board():
    r = await search(SearchInput(board="general", limit=3))
    assert r.llm["board"] == "general" and r.llm["keyword"] is None and r.llm["failedBoards"] == []
    assert [i["articleId"] for i in r.llm["items"]] == [26767048, 26767047, 26767044]
    assert r.ui == {"items": r.llm["items"]}

async def test_search_default_boards_partial_failure():
    # general만 fixture, academic·scholarship은 ConnectTimeout → items는 general 것, failedBoards == ["academic", "scholarship"]
async def test_search_all_fail():           # 모두 ConnectTimeout → ToolError "SOURCE_UNAVAILABLE"
async def test_search_no_results():         # 결과 0건인 board_list 페이지 → ToolOk, items == []

async def test_get_detail():
    r = await get_detail(DetailInput(board="scholarship", article_id=26767024))
    assert r.llm["articleId"] == 26767024 and r.llm["bodyIsImage"] is False and len(r.llm["attachments"]) == 2
    assert r.llm["stale"] is False
    assert "body" not in r.ui and r.ui["url"].endswith("/JANGHAKNOTICE/detail/26767024")

async def test_get_detail_not_found():      # 302 → ToolError "NOTICE_NOT_FOUND"
```

- [ ] **Step 2: 실패하는 tool 테스트를 쓴다** (`test_tools.py`, Task 3 Step 2와 같은 준비. `import app.programs.notice.tools`)

```python
async def test_tools_listed(client):   # "notice_search", "notice_get_detail" 둘 다 목록에. notice_search inputSchema의 board enum에 "foreign_student" 포함
async def test_invoke_search(client):  # {"arguments": {"board": "scholarship", "keyword": "국가"}} → status "ok", llm.items[0].articleId == 26767028
async def test_invoke_detail_bad_board(client):   # {"board": "news", "article_id": 1} → error.code "INVALID_ARGUMENTS"
```

- [ ] **Step 3: 실패를 확인한다**

Run: `uv run pytest tests/programs/notice -v` → 새 테스트 FAIL

- [ ] **Step 4: `service.py`, `tools.py`를 구현하고 등록한다**

- `merge_items`: `with_pinned`면 pinned + regular, 아니면 regular만. `(board, article_id)`로 중복 제거(하나라도 pinned면 pinned). `(date, article_id)` 내림차순, 앞에서 `limit`개.
- `search`: 게시판 = `[args.board]` 또는 `DEFAULT_BOARDS`. `asyncio.gather(*(load_list(b, args.keyword) ...), return_exceptions=True)`. `httpx.HTTPError`, `PageFormatError`인 게시판은 `failedBoards`(그 외 예외는 다시 raise). 전부 실패면 하나라도 HTTPError가 있으면 `SOURCE_UNAVAILABLE`, 아니면 `SOURCE_CHANGED`(로그). `llm = {"board": args.board, "keyword", "stale": 성공한 것 중 하나라도 stale, "failedBoards", "items": [i.model_dump(mode="json", by_alias=True)]}`, `ui = {"items": llm["items"]}`.
- `get_detail`: `load_detail`. `NoticeNotFoundError` → `ToolError("NOTICE_NOT_FOUND", "해당 공지를 찾지 못했습니다. 게시판과 글번호를 확인하세요.")`, HTTPError → `SOURCE_UNAVAILABLE`, PageFormatError → `SOURCE_CHANGED`. `llm = {**detail.model_dump(mode="json", by_alias=True), "stale": ...}`, `ui = {"title", "date", "url", "attachments"}`.
- `registry.py`의 `PROGRAM_MODULES`에 `"app.programs.notice.tools"`.

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/programs/notice -v` → all passed

- [ ] **Step 6: 커밋 (사용자 확인 후)** — `feat: 학교 공지 검색·본문 조회 tool 추가`

---

### Task 6: 전체 확인과 실제 사이트 점검

**Files:** 없음 (확인만)

- [ ] **Step 1: 전체 테스트와 린트**

Run: `uv run pytest` → 전부 통과 (기존 auth·skills 테스트 포함)
Run: `uv run ruff check . && uv run ruff format --check .` → 문제 없음

- [ ] **Step 2: 실제 사이트로 한 번 돌려 본다** (테스트가 아니라 수동 확인. `.env`에 `SERVICE_API_KEY`를 임시 값으로 두고)

Run: `uv run fastapi dev app/main.py` 후
```bash
curl -s -X POST localhost:8000/api/v1/skills/cafeteria_get_menu/invoke -H "X-Service-Key: <키>" -H "Content-Type: application/json" -d '{"arguments":{}}'
curl -s -X POST localhost:8000/api/v1/skills/notice_search/invoke -H "X-Service-Key: <키>" -H "Content-Type: application/json" -d '{"arguments":{"keyword":"장학"}}'
curl -s -X POST localhost:8000/api/v1/skills/notice_get_detail/invoke -H "X-Service-Key: <키>" -H "Content-Type: application/json" -d '{"arguments":{"board":"scholarship","article_id":<위 결과의 articleId>}}'
```
Expected: 셋 다 `"status":"ok"`, 오늘 메뉴·최근 장학 공지·본문이 보인다. 키 값은 출력하거나 커밋하지 않는다.

- [ ] **Step 3: PR 설명 초안을 남긴다** (PR은 틀 PR 머지 후, 사용자 확인 후 올린다)

담을 내용: tool 3개 요약, 공용 변경(`beautifulsoup4`·`httpx` 추가 이유, `app/common/cache.py`, `registry.py` 두 줄), AI 파트 요청(시스템 프롬프트에 오늘 날짜), 메모리 캐시라 인스턴스마다 따로라는 점.
