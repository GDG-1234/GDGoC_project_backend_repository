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
