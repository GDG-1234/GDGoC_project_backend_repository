"""길안내 데이터 접근. 지금은 DB 없이 `data/`의 JSON을 엔진이 메모리에 올린다."""

from functools import lru_cache
from pathlib import Path

from app.programs.navigation.engine import Engine

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
STATIC_DIR = PACKAGE_DIR / "static"


@lru_cache
def get_engine() -> Engine:
    """엔진은 앱 전체에서 하나만 만든다 (JSON을 한 번만 읽는다)."""
    return Engine(DATA_DIR)
