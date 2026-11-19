# 길안내 REST API 설계 (프론트 연동용)

- 작성일: 2026-11-19 (같은 날 두 번 수정: prototype은 그대로 두고, 엔진·데이터·이미지를 `programs/navigation`에 복사해서 쓰는 방식으로 확정)
- 상태: 사용자 지시로 확정
- 범위: 위키 API 명세서 v0.4의 1~7장 API 6개를 `app/programs/navigation/`에 만든다
- 기준 문서: 위키 `docs/specs/API_명세서.md` (v0.4, **API 형식은 이 문서가 기준**), `docs/samples/` (주요 루트 10개)

---

## 1. 왜 만드는가

프론트(`feat/designed-chatbot-ui`)는 명세서 v0.4의 API 6개를 부르는 코드를 이미 갖고 있고, 백엔드가 없어서 목업으로 돌아가고 있다.
백엔드가 이 6개를 만들면 프론트는 설정만 바꿔 실제 데이터로 동작한다.

`prototype/engine.py`가 이미 명세서 형식의 응답을 만든다 (위키 샘플도 이 엔진으로 만들었다).

**사용자 결정**
- `prototype/`은 그대로 두고 계속 혼자 돌아가게 한다 (옮기거나 고치지 않는다).
- 팀원이 배포 이미지에서 `prototype/`을 뺐으므로(`.dockerignore`), 엔진·데이터·이미지를 `app/programs/navigation/`에 **복사**해서 쓴다. `.dockerignore`는 고치지 않는다.
- 엔진은 지금은 거의 그대로 복사하고, 정식 구조로 다듬는 일("리마스터")은 나중에 한다.

## 2. 목표 / 하지 않는 것 / 실패로 보는 것

**목표**
- 명세서 v0.4 1~7장의 API 6개를 같은 경로·필드·에러 코드로 제공한다.
- 지도·층 단면도·건물 사진 이미지를 백엔드가 `/api/static/...`으로 제공한다.
- 위키 샘플의 주요 루트 10개와 에러 루트 1개가 샘플과 같은 응답을 낸다 (이미지 URL 앞부분만 다름).
- 배포 이미지만으로 동작한다 (`prototype/`에 기대지 않는다).

**하지 않는 것**
- `prototype/` 수정·이동·삭제, `.dockerignore` 수정
- 엔진 리마스터 (타입 있는 데이터 모델, 알고리즘 정리, 공유 데이터 수정 제거). 나중에 한다
- 8장 v2(3D) API, DB 테이블, 데이터 보강
- 길안내 tool(skill 틀 연결)

**실패로 보는 것**
- 프론트가 코드(필드 이름, 에러 코드 처리)를 고쳐야 붙는다.
- prototype과 다른 결과가 나온다.
- 배포 환경에서 길안내 API나 이미지가 안 된다.

## 3. 제약

- 명세서 공통 규칙: camelCase, 인증 없음(v1), ID는 정수, 목록은 `{"items": [...]}`, 에러는 `{"error": {"code", "message"}}`.
- PR #9 공용 코드 사용: `AppException`, `CamelModel`, `ItemsResponse`, 요청 검증 실패 → 400 `VALIDATION_ERROR`, 처리 못 한 예외 → 500 `INTERNAL_ERROR`, CORS 설정.
- 복사한 엔진은 `app/` 안이라 **ruff 검사 대상**이다. 결과가 바뀌지 않는 범위에서 린트·포맷만 맞춘다.
- Firebase Hosting은 `/api/**`만 Cloud Run으로 넘긴다 (`docs/배포.md`). 그래서 이미지는 `/api/static`으로 준다.
- 저장소에 이미지 14MB가 한 번 더 들어간다 (prototype과 중복). 리마스터 때 prototype을 지우면 중복이 없어진다.
- 공용 파일 변경: `app/main.py`(라우터 등록, 정적 파일 mount). 새 패키지 없음.
- `/map`은 CLAUDE.md의 "복수형 리소스" 규칙과 다르지만 명세서(프론트와의 약속)를 따른다.

## 4. 고려한 방식

| 방식 | 장점 | 단점 |
|---|---|---|
| A. 엔진을 타입 있는 정식 코드로 다시 짬 | 정식 구조 | 지금 할 일이 많다. 나중에 리마스터로 한다 |
| B. prototype을 import하고 `.dockerignore`를 고침 | 중복 없음 | 팀원이 정한 배포 규칙을 바꿔야 한다. 사용자가 원하지 않음 |
| **C. 엔진·데이터·이미지를 `programs/navigation`에 복사하고 API 계층을 만듦 (선택)** | prototype과 결과가 같다. 배포 규칙을 안 건드린다. prototype도 그대로 돌아간다 | 코드·데이터·이미지가 중복된다 (리마스터 때 정리) |

## 5. 설계

### 5-1. 파일 구성

```
app/programs/navigation/
├── engine.py          # prototype/engine.py 복사본 (린트만 맞춤, 동작 그대로). 맨 위에 "리마스터 예정" 주석
├── data/              # prototype/data 복사: map, buildings, nodes, edges, places .json (convert_report.json 제외)
├── static/            # prototype/static 복사: map/, building/, floor/, infophoto/
├── repository.py      # Engine을 한 번만 만들어 둠
├── service.py         # API별 함수: Engine 호출, ApiError → AppException, 이미지 URL 변환
├── schemas.py         # 요청·응답 모델 (CamelModel), 명세서 2장 타입
└── router.py          # 엔드포인트 6개
tests/programs/navigation/
├── samples/           # 위키 docs/samples의 JSON (routes 11개, map, places, buildings, building_details)
├── test_samples.py    # 샘플과 응답 비교
└── test_api.py        # 검색, 에러, 이미지 제공 등
```

### 5-2. 엔진 (repository)

- `get_engine() -> Engine`에 `lru_cache`: `Engine(<navigation 폴더>/data)`를 한 번만 만든다. 라우터는 `Depends(get_engine)`로 받는다.
- 경로는 `Path(__file__)` 기준 (현재 작업 폴더에 기대지 않는다).

### 5-3. API (명세서 그대로, 경로 앞에 `/api/v1`)

| API | Engine 호출 | 에러 |
|---|---|---|
| `GET /map` | `get_map()` | - |
| `GET /places?q&category&buildingId&limit` | `search_places(q, category, building_id, limit)`. `limit`은 엔진이 1~30으로 잘라 맞춘다 (에러 아님) | 빈 `q`·공백 `q` → 400 `VALIDATION_ERROR` |
| `GET /places/nearest?x&y&floor` | `nearest_place(x, y, floor)` | 그 층에 장소 없음 → 404 `PLACE_NOT_FOUND` |
| `POST /routes` | `route(body)` | 400 `VALIDATION_ERROR`, 400 `SAME_PLACE`, 404 `PLACE_NOT_FOUND`, 422 `NO_ROUTE` |
| `GET /buildings` | `list_buildings()` | - |
| `GET /buildings/{buildingId}` | `building_detail(id)` | 404 `BUILDING_NOT_FOUND` |

- 엔진의 `ApiError(status, code, message)`를 service에서 `AppException(status, code, message)`로 바꿔 던진다.
- 요청은 FastAPI가 먼저 검사한다: `category`는 명세서의 7개 값, `mode`는 `FASTEST`·`EASIEST`, `placeId`는 정수, `x`·`y`는 숫자. 틀리면 400 `VALIDATION_ERROR`. 검사한 값을 엔진이 받는 dict로 바꿔 넘긴다.
- `POST /routes` 요청 모델: `from`은 파이썬 예약어라 필드 `from_`에 별칭 `from`. `options`와 각 옵션은 생략 가능.
- 응답은 엔진 dict를 응답 모델(`CamelModel`)로 검증해 돌려준다.
- 모든 엔드포인트에 `response_model`, `status_code`, `tags=["navigation"]`, `summary`.
- **이미지 URL 변환:** 엔진은 `/static/...`을 돌려준다. service에서 `/static/`으로 시작하는 URL을 `/api/static/`으로 바꾼다. 데이터 파일은 prototype과 같게 둔다.

### 5-4. 동시 요청 안전성

- 엔진의 `route()`는 계산 중 공유 간선 dict에 `_seg`, `_action`을 써넣었다가 끝에 지운다. 여러 스레드가 동시에 부르면 서로의 값을 덮어쓸 수 있다.
- 그래서 **엔드포인트를 `async def`로 두고 엔진을 그 안에서 바로 부른다.** 엔진 호출에는 `await`가 없어서 한 번에 끝까지 실행되고 다른 요청과 섞이지 않는다. 경로 계산은 몇 ms라 이벤트 루프를 오래 막지 않는다.
- 이 이유를 router 코드 주석에 남긴다. 리마스터 때 공유 데이터 수정을 없앤다.

### 5-5. 이미지 제공

- `app/main.py`에서 `app.mount("/api/static", StaticFiles(directory=<navigation/static>), name="static")`.
- 로컬은 프론트 Vite 프록시의 `/api` 규칙, 배포는 Firebase Hosting의 `/api/**` 규칙으로 그대로 된다.
- 프론트 목업 모드는 지금처럼 `/static/...`, 실서버 모드는 응답 URL(`/api/static/...`)을 그대로 쓴다 (명세서 1.1.1).

### 5-6. 테스트

- **샘플 비교 (`test_samples.py`):** 위키 `docs/samples/`의 JSON을 `tests/programs/navigation/samples/`로 복사한다. 샘플 안의 `/static/`을 `/api/static/`으로 바꾼 뒤 응답과 같아야 한다.
  - `routes/route_01~10.json`: `request`로 `POST /routes` → `response`와 같음
  - `route_err_no_route.json`: 422, 같은 에러 본문
  - `map.json`, `buildings.json`, `building_details.json`(건물 21개 전부)
  - `places.json`: 장소마다 이름으로 검색했을 때 같은 요약이 나옴
- **API 테스트 (`test_api.py`):** 검색(별칭, 여러 단어, 정렬, 필터, `limit` 31 → 30개 이하, 빈·공백 `q` → 400, 없는 `category` → 400), nearest(가까운 장소, 장소 없는 층 → 404), routes(같은 장소 400, 없는 장소 404, 잘못된 `mode` 400, `placeId` 누락 400, `options` 생략 가능), 건물 404, 이미지(`/api/static/map/campus.png` → 200 `image/png`, 없는 파일 → 404).
- **한 번만 하는 확인 (커밋하지 않음):** 장소 57곳의 모든 쌍 × 옵션 몇 가지를 prototype 엔진과 새 API에 넣어 결과가 같은지 비교한다.

## 6. 함께 바꾸는 것

- 위키 명세서: 예시 URL `/static/...` → `/api/static/...`, 11장 "정적 이미지 서빙 위치" 결정 기록. 저장소 밖이라 사용자가 고친다.
- 프론트: 코드 변경 없음. `.env`에서 `VITE_USE_MOCK=false`.

## 7. 구현하는 사람에게 맡기는 것

- 응답 모델에서 좌표를 `float`로 둘지 `int | float`로 둘지 (JSON 값이 같으면 된다)
- 이미지 URL 변환 함수의 위치와 이름, 로그 문구
