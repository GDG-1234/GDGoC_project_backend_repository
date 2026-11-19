# 길안내 REST API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 위키 API 명세서 v0.4의 길안내 API 6개와 이미지(`/api/static`)를 `app/programs/navigation/`에 만든다.

**Architecture:** `prototype/engine.py`·`data/`·`static/`을 `app/programs/navigation/`에 복사하고(prototype은 그대로 둠), 그 위에 `repository → service → router` API 계층을 얹는다. 응답은 `CamelModel` 응답 모델로 검증한다.

**Tech Stack:** FastAPI, Pydantic v2, `StaticFiles`, pytest + anyio + httpx `AsyncClient`

**Spec:** `docs/superpowers/specs/2026-11-19-navigation-api-design.md`

## Global Constraints

- 경로: `/api/v1/map`, `/api/v1/places`, `/api/v1/places/nearest`, `/api/v1/routes`, `/api/v1/buildings`, `/api/v1/buildings/{buildingId}`, 이미지 `/api/static/...`
- JSON camelCase (`CamelModel`), 목록 `ItemsResponse` (`{"items": [...]}`), 에러 `AppException(status, code, message)`
- 에러 코드: 400 `VALIDATION_ERROR`, 400 `SAME_PLACE`, 404 `PLACE_NOT_FOUND`, 404 `BUILDING_NOT_FOUND`, 422 `NO_ROUTE`
- `PlaceCategory`: BUILDING, ENTRANCE, CLASSROOM, LIBRARY, CAFETERIA, FACILITY, LANDMARK / `RouteMode`: FASTEST, EASIEST / `FacilityType`: VENDING, PRINTER, ATM, STORE, CAFE, LOUNGE, SHOWER, ETC / `StepAction`: START, WALK, ENTER_BUILDING, EXIT_BUILDING, STAIRS_UP, STAIRS_DOWN, ELEVATOR, UPHILL, DOWNHILL, ARRIVE
- 엔드포인트는 `async def` (엔진의 공유 데이터 수정 때문, 설계 5-4), `tags=["navigation"]`
- `prototype/`, `.dockerignore`는 고치지 않는다

## Review Focus

1. **동시에 여러 경로 요청:** 엔진이 공유 간선에 임시 값을 써넣는다. 엔드포인트가 `def`로 바뀌면 스레드끼리 섞인다 → router 주석으로 막고, Task 3 테스트 `test_concurrent_routes_match_sequential`로 확인.
2. **장소 이름에 공백만 있는 검색어(`q=" "`):** 400이어야 한다 (엔진 `ApiError`) → Task 3 `test_search_blank_q_is_400`.
3. **배포 이미지에서 데이터·이미지 경로:** `Path(__file__)` 기준이어야 Docker `WORKDIR`과 무관하다 → Task 2 `test_engine_loads_from_package_data`.
4. **엔진이 모르는 데이터 값(새 facility type 등):** 응답 모델 검증에서 500이 난다 → Task 4에서 건물 21개·장소 57곳 전부를 응답 모델로 통과시킨다.
5. **이미지 URL 중 `/static/`이 아닌 값(`null`):** 변환이 `None`을 건드리지 않아야 한다 → Task 3 `test_building_floor_without_image_has_null_url` (데이터에 없으면 단위 테스트로).

---

### Task 1: 브랜치, 복사

- [ ] `git switch -c feat/navigation-api` (main에서)
- [ ] 복사: `prototype/engine.py` → `app/programs/navigation/engine.py`, `prototype/data/{map,buildings,nodes,edges,places}.json` → `app/programs/navigation/data/`, `prototype/static/` → `app/programs/navigation/static/`
- [ ] `engine.py`: 맨 위 docstring에 "prototype/engine.py 복사본, 리마스터 예정" 추가, ruff 통과하도록만 수정 (동작 변경 금지)
- [ ] 확인: `uv run ruff check app/programs/navigation`, `uv run ruff format --check app/programs/navigation`

### Task 2: 응답 모델과 엔진 준비 (schemas, repository)

**Files:** Create `app/programs/navigation/schemas.py`, `app/programs/navigation/repository.py`

**Interfaces — Produces:**
- schemas (모두 `CamelModel`): `Point`, `ImageBounds`, `PlaceSummary`, `NearestPlaceResponse`, `MapInfoResponse`, `PlaceRef(id, name)`, `RouteSummary`(필드 `from_` 별칭 `from`), `RoutePoint`, `RouteSegment`, `RouteStep`, `RouteResponse`, `RoutePlaceInput(place_id)`, `RouteOptions(mode="FASTEST", avoid_road=False, avoid_stairs=False, compare=False)`, `RouteRequest(from_ 별칭 from, to, options=RouteOptions())`, `BuildingSummary`, `BuildingFloor`, `Facility`, `BuildingDetailResponse`, 타입 `PlaceCategory`, `RouteMode`, `FacilityType`, `StepAction` (Literal)
- repository: `DATA_DIR`, `STATIC_DIR` (`Path(__file__).parent / "data"`, `/ "static"`), `get_engine() -> Engine` (`lru_cache`)

- [ ] 테스트 `tests/programs/navigation/test_repository.py::test_engine_loads_from_package_data`: `get_engine().get_map()["width"] == 3000`, `STATIC_DIR / "map" / "campus.png"` 존재
- [ ] 구현, 통과 확인

### Task 3: service, router, main

**Files:** Create `service.py`, `router.py`; Modify `app/main.py` (라우터 등록 + `app.mount("/api/static", StaticFiles(directory=STATIC_DIR), name="static")`); Test `tests/programs/navigation/test_api.py`

**Interfaces — Produces (service):** `get_map(engine) -> MapInfoResponse`, `search_places(engine, q, category, building_id, limit) -> ItemsResponse[PlaceSummary]`, `nearest_place(engine, x, y, floor) -> NearestPlaceResponse`, `find_route(engine, request: RouteRequest) -> RouteResponse`, `list_buildings(engine) -> ItemsResponse[BuildingSummary]`, `get_building(engine, building_id) -> BuildingDetailResponse`, `to_public_url(url: str | None) -> str | None` (`/static/` → `/api/static/`). 엔진 `ApiError` → `AppException`.

- [ ] 테스트 (`client` fixture 사용, 모두 `async`):
  - `test_map_returns_api_static_url`: `imageUrl == "/api/static/map/campus.png"`, `width == 3000`
  - `test_search_by_alias`: `q=신공` → 첫 결과 이름에 "신공학관"
  - `test_search_exact_match_first`: `q=중앙도서관` → `items[0].name == "중앙도서관"`
  - `test_search_limit_clamped`: `q=관&limit=31` → 200, 30개 이하
  - `test_search_blank_q_is_400`: `q=%20` → 400 `VALIDATION_ERROR`; `q=` → 400
  - `test_search_unknown_category_is_400`
  - `test_search_category_filter`: `category=ENTRANCE` → 모두 ENTRANCE
  - `test_nearest_returns_place`: 정문 좌표 → 정문, `distancePx == 0.0`
  - `test_nearest_floor_without_places_is_404`: `floor=99` → 404 `PLACE_NOT_FOUND`
  - `test_route_same_place_is_400` (`SAME_PLACE`), `test_route_unknown_place_is_404`, `test_route_bad_mode_is_400`, `test_route_missing_place_id_is_400`, `test_route_without_options_ok`
  - `test_building_not_found_is_404` (`BUILDING_NOT_FOUND`)
  - `test_static_image_served`: `/api/static/map/campus.png` → 200, `image/png`; 없는 파일 → 404
  - `test_concurrent_routes_match_sequential`: 같은 요청 10개를 `asyncio.gather`로 보낸 결과가 하나씩 보낸 결과와 같음
  - `test_to_public_url`: `"/static/a.png"` → `"/api/static/a.png"`, `None` → `None`, `"http://x"` 그대로
- [ ] 실패 확인 → 구현 → 통과 확인

### Task 4: 위키 샘플 비교

**Files:** Create `tests/programs/navigation/samples/` (위키 `docs/samples/`의 `map.json`, `places.json`, `buildings.json`, `building_details.json`, `routes/*.json` 복사), `tests/programs/navigation/test_samples.py`

- [ ] 샘플을 읽을 때 문자열의 `/static/`을 `/api/static/`으로 바꾸는 도우미
- [ ] `test_route_sample[route_01..10]`: `request` → 200, 응답 == `response`
- [ ] `test_route_error_sample`: 422, 본문 == 샘플
- [ ] `test_map_sample`, `test_buildings_sample`, `test_building_detail_sample[21개]`, `test_place_summaries_match_sample` (장소마다 이름 검색 결과에 같은 요약이 있음)
- [ ] 통과 확인

### Task 5: 전체 확인

- [ ] 커밋하지 않는 스크립트: 장소 모든 쌍 × 옵션 {기본, EASIEST, avoidRoad, avoidStairs, compare}를 `prototype.engine.Engine`과 API에 넣어 비교 (이미지 URL만 다름)
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
- [ ] 서버 띄워 확인: `/docs`에 navigation 6개, `/api/v1/routes` 한 번, 이미지 한 장
- [ ] 커밋은 사용자에게 물어본 뒤
