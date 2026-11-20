from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.common.exceptions import register_exception_handlers
from app.core.config import get_settings
from app.programs.navigation.repository import STATIC_DIR as NAVIGATION_STATIC_DIR
from app.programs.navigation.router import router as navigation_router
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
app.include_router(chat_router)
app.include_router(navigation_router)
app.include_router(skills_router)

# 지도·층 단면도·건물 사진. Firebase Hosting이 /api/**만 백엔드로 넘기므로 /api 아래에 둔다.
app.mount("/api/static", StaticFiles(directory=NAVIGATION_STATIC_DIR), name="static")
