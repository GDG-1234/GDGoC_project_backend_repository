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
    "app.programs.cafeteria.tools",
    "app.programs.notice.tools",
    "app.programs.navigation.tools",
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
