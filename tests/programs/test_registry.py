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
