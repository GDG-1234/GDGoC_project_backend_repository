# 학식·공지 skill 설계

- 작성일: 2026-11-19
- 상태: 초안 (사용자 승인 전)
- 범위: 채팅 AI가 부르는 tool 3개 — 학식 메뉴(`cafeteria_get_menu`), 공지 목록(`notice_search`), 공지 본문(`notice_get_detail`)
- 기반: skill 공통 틀 `docs/superpowers/specs/2026-11-18-skill-framework-design.md` (`feat/skills-framework` 브랜치, PR 승인 대기 중)

---

## 1. 왜 만드는가

서비스의 메인은 AI 채팅이다. 학생이 "오늘 점심 뭐야?", "장학 공지 새로 올라온 거 있어?", "그 공지 마감 언제야?"라고 물으면 AI가 tool을 불러 답한다.
학식과 공지는 학교 사이트에 이미 있지만 찾기 번거롭다. 채팅의 가치는 링크를 던지는 게 아니라 **질문에 바로 답하는 것**이다. 그래서 공지는 목록뿐 아니라 본문까지 AI가 읽을 수 있게 한다 (사용자 결정: B안).

skill 틀의 첫 실사용처다. 틀이 실제 프로그램에서 쓸 만한지 확인하는 의미도 있다.

## 2. 목표 / 하지 않는 것 / 실패로 보는 것

**목표**
- "오늘/내일/수요일 학식", "상록원 3층 저녁" 같은 질문에 AI가 답할 수 있는 데이터를 준다.
- "장학 공지", "국가장학금 공지 있어?" 같은 질문에 최근 공지 목록을 준다.
- 목록에서 고른 공지의 본문을 줘서 AI가 마감일·대상·신청 방법을 답하거나 요약할 수 있게 한다.

**하지 않는 것**
- REST API(프론트 직접 조회). 채팅 tool로만 제공한다. 그래서 `router.py`는 만들지 않는다.
- DB 저장, 주기적 수집(크롤링 예약 작업). 필요해지면 가져오는 부분만 바꾼다 (4장 2번 방식).
- 고양(일산)캠퍼스 식당.
- 공지 첨부파일(PDF, HWP) 내용 읽기. 파일 이름과 주소만 준다.
- 새 공지 알림(푸시).

**실패로 보는 것**
- 학교 사이트가 느리거나 죽었을 때 tool이 멈추거나 500을 낸다.
- 메뉴가 없는데 AI가 지어낼 여지를 준다 (빈 결과와 "휴무"를 구분하지 못함).
- 공지 본문이 너무 길어 AI 토큰을 크게 낭비한다.
- 같은 질문이 몰릴 때 학교 사이트에 요청을 그대로 쏟아낸다.
- 테스트가 학교 사이트에 접속해야만 통과한다 (사이트가 바뀌거나 죽으면 CI가 깨진다).

## 3. 제약

- CLAUDE.md 규칙과 skill 틀 설계(이름 `<프로그램>_<기능>`, `ToolOk(llm, ui)`, `ToolNeedClarification`, `ToolError`, 입력 모델은 `BaseModel`, 기본 시간 제한 10초)를 따른다.
- **`feat/skills-framework`가 main에 아직 없다.** 이 작업은 그 브랜치에서 갈라져 나가고, 틀 PR이 머지된 뒤 PR을 올린다.
- Cloud Run 인스턴스 최대 2개. 메모리 캐시는 인스턴스마다 따로라 학교 사이트 요청이 최대 2배가 될 뿐, 동작에는 문제없다.
- 학교 사이트 robots.txt는 두 사이트 모두 이 페이지들을 막지 않는다 (2026-11-19 확인).

## 4. 고려한 방식

| 방식 | 장점 | 단점 |
|---|---|---|
| **1. 부를 때 읽고 메모리에 잠깐 저장 (선택)** | DB·마이그레이션·예약 작업 없음. 공용 파일을 거의 안 건드림. 항상 최신 | 캐시가 없을 때 첫 호출은 학교 사이트를 기다림. 사이트가 죽으면 캐시 없이는 답 못 함 |
| 2. 주기적으로 모아 DB에 저장 | 빠름. 사이트가 죽어도 마지막 데이터로 답함. 기록이 쌓임 | 모델·마이그레이션·수집 엔드포인트·Cloud Scheduler 설정, 배포 담당과 조율. 최대 수집 주기만큼 늦음 |
| 3. 매번 바로 읽기 (저장 없음) | 가장 단순 | 몰리면 학교 사이트에 요청이 그대로 감. 1번보다 아끼는 게 거의 없음 |

사용자가 **1번**을 골랐다. 나중에 2번으로 갈 수 있게, "사이트에서 읽기(source)"와 "tool이 쓰는 로직(service)"을 나눈다.

## 5. 데이터 출처 (2026-11-19 조사)

### 5-1. 학식 — 동국대 생협 `https://dgucoop.dongguk.edu`

| 페이지 | 주소 | 내용 |
|---|---|---|
| 날짜별 식단 | `/store/store.php?w=4&l=1&sday=<그날 0시(한국 시간)의 유닉스 시각>` | 그날 하루, 식당별 표 |

- 오늘의 식단(`?w=4`)과 주간 식단(`?w=4&l=2`) 페이지도 있지만 쓰지 않는다. 날짜별 페이지 하나로 **아무 날짜나** 볼 수 있다 (2026-11-19에 지난주·이번 주·다음 주 평일 모두 메뉴 확인. 예: 11/16 → `sday=1794754800`).
- 아직 올라오지 않은 날짜(예: 3주 뒤)는 모든 식당이 "휴무"로 나온다. 실제 휴무와 구분할 수 없다.
- 페이지에 식당이 12개 있지만 **9개는 HTML 주석(`<!-- -->`) 안에 있어 화면에 안 보인다** (그루터기, 팬앤누들, 가든쿡, 남산학사 등). 보이는 것은 **상록원3층식당, 상록원2층식당, 상록원1층식당(솥앤누들), 누리터 식당(일산캠퍼스)** 넷뿐이다. 주석 안 식당은 무시한다.
- 인코딩 EUC-KR(cp949). 식당 이름은 `td.menu_st`, 바로 다음 `<table>`이 메뉴 표다. 첫 행은 `구분` + 코너 이름들(집밥, 한그릇(한정판매) / 백반코너, 일품코너, 양식코너, 뚝배기코너 / 메뉴), 다음 행부터 첫 칸이 끼니(중식, 석식, 중·석식), 나머지 칸이 코너별 메뉴다.
- 칸 수가 머리 행보다 많은 경우가 있다 (솥앤누들: 머리 `구분, 메뉴`, 행 `중·석식, 솥밥, 누들, (빈칸), (빈칸)`). 빈 칸은 그 코너에 메뉴가 없다는 뜻이다.
- 휴무 날은 표에 `휴무` 칸 하나만 있다.
- 메뉴 칸은 자유 텍스트다. 메뉴·가격(`￦7,000`, `6,300원`)·운영 시간·원산지·"한정판매" 메모가 섞여 있다. 첫 줄에 `'김치가츠나베(뚝)'김치가츠나베(뚝)`처럼 이름이 따옴표로 한 번 더 붙는 찌꺼기가 있다.
- 페이지 머리에 날짜(`span.menu_date`, 예: `11월 19일`)가 있다.

### 5-2. 공지 — 동국대 홈페이지 `https://www.dongguk.edu`

| 페이지 | 주소 |
|---|---|
| 목록 | `/article/<게시판코드>/list?pageIndex=1` |
| 검색 | `/article/<게시판코드>/list?searchCondition=TA.SUBJECT&searchKeyword=<검색어>&pageIndex=1` (GET. **제목만 검색**한다. 제목+내용 `TA.SUBJECT%7C%7CTA.CONTENT`는 2026-11-19 측정에서 3~6초가 걸려 5초 제한에 걸렸다. 제목만은 0.3초) |
| 본문 | `/article/<게시판코드>/detail/<글번호>` (GET. **게시판 코드가 맞아야 열린다**) |

- 목록 항목: `div.board_list li` 안의 `<a onclick="goDetail(글번호)">`. 고정 공지 표시(`span.fix`), 제목(`p.tit`, 안의 `span.mobile`은 빼야 한다), `div.info span` 두 개(날짜 `2026.11.19.`, `조회 291`). 한 페이지에 일반 글 10개 + 고정 공지. **고정 공지는 일반 글 목록에도 한 번 더 나온다** (최근 글이면).
- **검색해도 고정 공지는 검색어와 상관없이 전부 나온다** (장학공지 "국가" 검색 결과에 "창업유망팀" 고정 공지가 섞임). 검색할 때는 고정 공지 목록을 버리고 일반 글만 쓴다.
- 본문: `div.board_view` 안에 `div.tit > p`(제목), `div.tit div.info span`(`등록일 2026.11.18.`, `조회 879`), `div.view_cont`(본문, 안에 `<script>`가 섞여 있음). 게시판 코드가 틀리거나 없는 글이면 **302로 `/main`에 보낸다** (본문 없음). 리다이렉트를 따라가지 않고 302를 "글 없음"으로 본다.
- 첨부파일: `div.view_files li a`의 `href="javascript:downGO('파일이름','/files/article/<게시판>/<글번호>/','저장이름.hwp')"`. 실제 받는 주소는 `https://www.dongguk.edu/cmmn/fileDown.do?filename=<파일이름 URL 인코딩>&filepath=<경로>&filerealname=<저장이름>`. 페이지 아래쪽 `/resources/files/...pdf` 링크는 사이트 공통 꼬리말이라 첨부파일이 아니다.

## 6. 설계

### 6-1. 파일 구성

```
app/programs/
├── registry.py              # (수정) PROGRAM_MODULES에 두 줄 추가
├── cafeteria/
│   ├── __init__.py
│   ├── tools.py             # @tool cafeteria_get_menu
│   ├── schemas.py           # tool 입력 모델, 내부 데이터 모델(Restaurant, MenuCell 등)
│   ├── service.py           # 날짜 → 어느 페이지, 식당 이름 찾기, llm/ui 만들기
│   └── source.py            # 생협 사이트 읽기(httpx) + HTML 파싱 + 캐시
└── notice/
    ├── __init__.py
    ├── tools.py             # @tool notice_search, notice_get_detail
    ├── schemas.py
    ├── service.py
    └── source.py
app/common/cache.py          # (새 공용 파일) 작은 TTL 캐시. 두 프로그램이 같이 쓴다
tests/programs/cafeteria/    # fixtures/*.html (저장해 둔 실제 페이지) + 테스트
tests/programs/notice/
```

- `source.py`는 CLAUDE.md의 `repository.py` 자리다. DB가 아니라 외부 사이트를 읽어서 이름을 달리했다. 4장 2번으로 바꿀 때 이 파일만 DB를 읽는 `repository.py`로 바꾼다.
- 계층: `tools → service → source`. tools는 입력을 받아 service를 부르고 결과만 돌려준다.
- 두 프로그램은 서로 import하지 않는다.

### 6-2. 공용 부분

**HTTP:** `httpx.AsyncClient`, 요청 시간 제한 5초 (tool 기본 제한 10초 안에 끝나게). User-Agent는 일반적인 이름(개인 정보 없음). 학식 페이지는 cp949로 디코드한다.

**HTML 파싱:** `beautifulsoup4`(+ 표준 `html.parser`)를 쓴다.

**캐시 (`app/common/cache.py`):** 키(주소)별로 값과 저장 시각을 둔다.
- 신선한 동안은 캐시를 준다.
- 만료되면 다시 읽는다. **다시 읽기가 실패하면 하루 안의 오래된 값이라도 주고 `stale: true`로 표시**한다. 그것도 없으면 `ToolError("SOURCE_UNAVAILABLE", ...)`.
- 같은 키를 동시에 요청하면 한 번만 읽는다 (키별 `asyncio.Lock`).
- 캐시하는 것은 **파싱이 끝난 결과**다 (HTML 원문이 아님).

| 대상 | 신선한 시간 |
|---|---|
| 학식 날짜별 페이지 | 10분 |
| 공지 목록·검색 결과 | 5분 |
| 공지 본문 | 30분 |

- 값은 모듈 상수로 둔다 (비밀값이 아니고 `app/core/config.py`를 건드리지 않기 위해).

**파싱이 깨졌을 때:** 페이지는 받았는데 식당 표(`td.menu_st`)나 공지 목록(`div.board_list`)을 찾지 못하거나, 학식 페이지 머리 날짜가 요청한 날짜와 다르면 사이트 구조가 바뀐 것으로 보고 로그에 남긴 뒤 `ToolError("SOURCE_CHANGED", ...)`를 낸다. "메뉴 없음"과 구분하기 위해서다. 공지 검색 결과 0건은 `div.board_list`가 있으면 정상이다.

### 6-3. `cafeteria_get_menu`

```python
class GetMenuInput(BaseModel):
    date: date | None = Field(None, description="조회할 날짜 YYYY-MM-DD. 없으면 오늘(한국 시간)")
    cafeteria: str | None = Field(
        None, description="식당 이름 일부. 예: 3층, 2층, 솥앤누들, 교직원식당. 없으면 전체"
    )
```

설명(LLM용): "동국대 서울캠퍼스 상록원 학생식당(1~3층) 메뉴를 날짜별로 조회한다."

**날짜 처리** (기준은 한국 시간 `Asia/Seoul`. 테스트를 위해 "오늘"을 바꿔 넣을 수 있게 만든다)
- "내일", "수요일"을 날짜로 바꾸는 일은 AI가 한다. AI 파트가 시스템 프롬프트에 오늘 날짜를 넣어야 한다 (AI 파트 요청서에 적는다). 도움이 되도록 `llm`에 `today`를 함께 준다.
- 날짜 제한은 두지 않는다. 날짜별 페이지 하나를 읽는다.
- 서울 식당이 모두 휴무면 `llm.note`에 "이 날은 모든 식당이 휴무이거나 아직 식단이 올라오지 않았습니다."를 넣는다 (휴무와 미등록을 구분할 수 없으므로 AI가 둘 다 말하게 한다).

**식당 고르기**
- 서울캠퍼스 식당만 다룬다. 이름에 `일산`이 들어간 식당은 버린다. 주석 안 식당은 파서가 보지 않는다.
- 이름 비교는 공백·괄호를 지운 뒤 부분 일치. 별칭을 둔다: "3층"·"교직원" → 상록원3층식당, "2층"·"학생식당" → 상록원2층식당, "1층"·"솥앤누들"·"솥밥"·"누들" → 상록원1층식당(솥앤누들). ("교직원식당", "상록원학생식당"은 생협 매장 안내 페이지의 정식 이름이다)
- 하나 맞으면 그 식당만. 여러 개 맞으면(예: "상록원") `ToolNeedClarification(field="cafeteria", candidates=[...])`. 하나도 안 맞으면 서울 식당 전체를 후보로 준다.

**결과**
```jsonc
// llm
{
  "date": "2026-11-19",
  "today": "2026-11-19",
  "stale": false,
  "note": null,
  "cafeterias": [
    {
      "name": "상록원3층식당",
      "closed": false,
      "meals": [
        { "meal": "중식", "corner": "집밥", "menu": "김치가츠나베(뚝)\n(돼지:국내산)\n계란말이\n...\n￦7,000" },
        { "meal": "중식", "corner": "한그릇(한정판매)", "menu": "..." }
      ]
    },
    { "name": "상록원2층식당", "closed": false, "meals": [ ... ] }
  ]
}
```
- `menu`는 칸 텍스트를 그대로(줄 단위, 앞뒤 공백·빈 줄 정리, 첫 줄의 `'이름'이름` 찌꺼기는 `이름`으로) 준다. 가격·원산지를 나누지 않는다. AI가 읽고 정리한다.
- 코너 이름은 머리 행의 같은 위치 칸이다. 머리 행보다 칸이 많으면 넘치는 칸의 `corner`는 `null`.
- 빈 칸과 `휴무` 칸은 버린다. 남은 칸이 없으면 `closed: true`, `meals: []`.
- `ui`: `llm`과 같은 구조 + 원본 페이지 주소. (프론트 카드 형태가 정해지면 바꾼다)

### 6-4. `notice_search`

```python
class NoticeBoard(StrEnum):
    general = "general"  # 일반공지 GENERALNOTICES
    academic = "academic"  # 학사공지 HAKSANOTICE
    scholarship = "scholarship"  # 장학공지 JANGHAKNOTICE
    admission = "admission"  # 입시공지 IPSINOTICE
    research = "research"  # 학술공지 HAKSULNOTICE
    event = "event"  # 행사공지(정각원 법회 등 불교 행사) BUDDHISTEVENT
    international = "international"  # 국제교류(교환학생 등) INTEXNOTICE
    foreign_student = "foreign_student"  # 외국인 유학생 INTSTUNOTICE
    safety = "safety"  # 안전공지 SAFENOTICE


class SearchInput(BaseModel):
    board: NoticeBoard | None = Field(
        None, description="게시판. 없으면 일반·학사·장학 공지를 함께 본다"
    )
    keyword: str | None = Field(None, min_length=1, max_length=50, description="제목 검색어")
    limit: int = Field(5, ge=1, le=10, description="가져올 개수")
```

설명(LLM용): "동국대 홈페이지 공지사항 최근 글을 찾는다. 본문이 필요하면 결과의 board, articleId로 notice_get_detail을 부른다."

- 채용·교직원 경조사·홍보영상·동국소식·커뮤니티는 학생 질문과 거리가 멀어 뺐다.
- `board`가 없으면 일반·학사·장학 3개를 동시에 읽어 날짜 내림차순으로 합친다. 일부 게시판만 실패하면(캐시도 없음) 나머지로 답하고 `failedBoards`에 적는다. 셋 다 실패하면 `SOURCE_UNAVAILABLE`. 하나라도 오래된 캐시를 썼으면 `stale: true`.
- 첫 페이지만 본다. 검색어가 없으면 고정 공지는 `pinned: true`로 표시하고 일반 글과 같이 날짜순(같은 날이면 글번호 큰 것 먼저)으로 섞는다. 같은 글번호는 한 번만(고정 표시 유지). 검색어가 있으면 고정 공지 목록은 버린다 (5-2 참고).
- 결과가 없으면 `ToolOk(llm={"items": [], ...})` (에러 아님). AI가 "찾지 못했다"고 답한다.

```jsonc
// llm
{
  "board": "scholarship",       // null이면 여러 게시판
  "keyword": "국가장학금",
  "stale": false,
  "failedBoards": [],
  "items": [
    { "board": "scholarship", "articleId": 26767040, "title": "[한국장학재단] 2027년 1학기 국가장학금 1차 신청 안내(11/24(화) ~ 1/7(목))",
      "date": "2026-11-18", "views": 1520, "pinned": false, "url": "https://www.dongguk.edu/article/JANGHAKNOTICE/detail/26767040" }
  ]
}
```
- `ui`: 같은 `items` (카드 목록).

### 6-5. `notice_get_detail`

```python
class DetailInput(BaseModel):
    board: NoticeBoard = Field(description="notice_search 결과의 board")
    article_id: int = Field(gt=0, description="notice_search 결과의 articleId")
```

- 본문 `div.view_cont`를 텍스트로 바꾼다. 줄바꿈은 살리고, 표는 칸을 ` | `로 이어 한 줄로 만든다. 이미지는 버린다.
- **본문은 최대 4,000자.** 넘으면 자르고 `truncated: true`.
- 본문 텍스트가 거의 없으면(예: 50자 미만, 이미지 공지) `bodyIsImage: true`. AI가 "원문 링크를 확인하라"고 안내하게 한다.
- 응답이 302(리다이렉트)면 글이 없거나 게시판이 틀린 것이다 → `ToolError("NOTICE_NOT_FOUND", ...)`. 200인데 `div.view_cont`가 없으면 `SOURCE_CHANGED`.

```jsonc
// llm
{
  "board": "scholarship", "articleId": 26767040,
  "title": "...", "date": "2026-11-18", "views": 1520,
  "body": "1. 신청 기간: 2026.11.24.(화) 09:00 ~ 2027.1.7.(목) 18:00\n...",
  "truncated": false, "bodyIsImage": false,
  "attachments": [ { "name": "신청 안내.pdf", "url": "https://www.dongguk.edu/resources/files/..." } ],
  "url": "https://www.dongguk.edu/article/JANGHAKNOTICE/detail/26767040",
  "stale": false
}
```
- `ui`: 제목, 날짜, 원문 주소, 첨부파일 (본문은 넣지 않는다).

### 6-6. 에러 코드 정리

| code | 언제 |
|---|---|
| `SOURCE_UNAVAILABLE` | 학교 사이트 접속 실패·시간 초과이고, 하루 안의 캐시도 없음 |
| `SOURCE_CHANGED` | 페이지는 받았지만 표·목록을 못 찾음 (사이트 구조 변경 의심) |
| `NOTICE_NOT_FOUND` | 본문 페이지에 글이 없음 |

입력 형식 오류(`INVALID_ARGUMENTS`)와 시간 초과(`TOOL_TIMEOUT`)는 틀이 처리한다.

### 6-7. 테스트

- 실제 페이지를 `tests/programs/<프로그램>/fixtures/`에 저장해 두고 파싱을 테스트한다. **테스트는 네트워크에 접속하지 않는다.** source의 HTTP 부분은 `httpx.MockTransport`로 바꾼다.
- 학식: 날짜별 페이지 파싱(평일·휴일, 주석 안 식당 무시, 일산 제외, 칸 넘침), 날짜 → `sday` 계산, 머리 날짜 불일치 → `SOURCE_CHANGED`, 식당 이름 하나·여러 개·없음, 전부 휴무 → `note`.
- 공지: 목록 파싱(고정 공지, 날짜, 조회수, `span.mobile` 제거), 검색 시 고정 공지 버림, 여러 게시판 합치기·중복 제거·일부 실패, 본문 텍스트 변환·자르기·이미지 공지, 첨부파일 주소, 없는 글.
- 캐시: 신선할 때 재사용, 만료 후 다시 읽기, 실패 시 오래된 값 + `stale`, 동시 요청 한 번만 읽기.
- tool 단위: skill 틀의 invoke API로 세 tool을 한 번씩 불러 `status`와 `llm` 모양을 확인.

### 6-8. 공용 파일·패키지 변경 (PR 설명에 적는다)

- `uv add beautifulsoup4` — HTML 파싱. `uv add httpx` — 이미 FastAPI를 통해 깔려 있지만 직접 쓰므로 명시한다. → `pyproject.toml`, `uv.lock` 변경.
- `app/common/cache.py` 새 파일.
- `app/programs/registry.py`의 `PROGRAM_MODULES`에 두 줄.
- `.env`, 설정, 마이그레이션 변경 없음.

### 6-9. 브랜치와 PR

- 브랜치: `feat/skills-cafeteria-notice`, `feat/skills-framework`에서 갈라진다.
- PR은 틀 PR이 main에 머지된 뒤 main 기준으로 다시 맞춰(rebase) 올린다. 학식과 공지는 한 PR에 커밋을 나눠 담는다.

## 7. 구현하는 사람에게 맡기는 것

- 별칭 목록의 세부 내용, 내부 함수·클래스 이름, 로그 문구.
- 표 칸 텍스트 정리 세부(연속 공백, `--> ` 같은 주석 찌꺼기 제거).
- 캐시 최대 개수 등 메모리 상한 (공지 본문 캐시는 글 수만큼 늘어나므로 수백 개 정도로 제한).
