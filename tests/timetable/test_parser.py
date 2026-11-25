from pathlib import Path

import pytest

from app.timetable.parser import parse_pasted_timetable, parse_room
from app.timetable.service import guess_floor

FIXTURES = Path(__file__).parent / "fixtures"
# 실제 학교 시간표 엑셀에서 드래그·복사한 글자 (머리글 없음, 시간 열 + 6요일)
EXCEL_GRID = (FIXTURES / "excel_grid_paste.txt").read_text(encoding="utf-8")


def summary(text: str) -> list[tuple[str, str, str, str]]:
    return [(c.day, c.start_time, c.end_time, c.name) for c in parse_pasted_timetable(text).courses]


def test_excel_grid_courses() -> None:
    assert summary(EXCEL_GRID) == [
        ("MON", "10:30", "12:00", "소프트웨어공학"),
        ("MON", "13:00", "15:30", "시스템소프트웨어"),
        ("MON", "15:00", "17:00", "인공지능"),
        ("TUE", "13:00", "14:30", "암호학과네트워크보안"),
        ("TUE", "15:00", "17:00", "데이터베이스설계"),
        ("WED", "10:30", "12:00", "소프트웨어공학"),
        ("WED", "13:00", "15:30", "시스템소프트웨어"),
        ("WED", "15:00", "17:00", "인공지능"),
        ("THU", "13:00", "14:30", "암호학과네트워크보안"),
        ("THU", "15:00", "17:00", "데이터베이스설계"),
    ]


def test_excel_grid_room_details() -> None:
    courses = parse_pasted_timetable(EXCEL_GRID).courses
    software = courses[0]
    system = courses[1]

    assert parse_pasted_timetable(EXCEL_GRID).warnings == []
    assert software.weeks == "1주차~15주차"
    assert software.room == "5145(신공학관(기숙사) 401-5145 강의실)"
    assert (software.room_number, software.building_name) == ("5145", "신공학관")
    assert system.room_description == "컴퓨터AI학부 실습실4"


def test_header_row_sets_days() -> None:
    text = (
        "\t화\t목\n"
        '09:00-09:30\t"1주차~15주차\n과목\n301(혜화관 402-301 강의실)"\t\n'
        '09:30-10:00\t"1주차~15주차\n과목\n301(혜화관 402-301 강의실)"\t\n'
    )

    assert summary(text) == [("TUE", "09:00", "10:00", "과목")]


def test_separate_blocks_are_not_merged() -> None:
    cell = '"1주차~15주차\n과목\n301(혜화관 402-301 강의실)"'
    text = f"09:00-09:30\t{cell}\n09:30-10:00\t\n10:00-10:30\t{cell}\n"

    assert summary(text) == [("MON", "09:00", "09:30", "과목"), ("MON", "10:00", "10:30", "과목")]


def test_cell_without_weeks_line() -> None:
    text = '09:00-09:30\t"과목\n301(혜화관 402-301 강의실)"\n'

    courses = parse_pasted_timetable(text).courses
    assert [(c.name, c.weeks, c.building_name) for c in courses] == [("과목", None, "혜화관")]


@pytest.mark.parametrize("text", ["", "   \n\t\n", "아무 글자"])
def test_no_courses_gives_warning(text: str) -> None:
    result = parse_pasted_timetable(text)

    assert result.courses == []
    assert result.warnings


def test_bad_time_row_is_skipped_with_warning() -> None:
    text = '아침\t"과목\n301(혜화관 402-301 강의실)"\n09:00-09:30\t"과목B\n강의실"\n'

    result = parse_pasted_timetable(text)
    assert [c.name for c in result.courses] == ["과목B"]
    assert any("시간" in w for w in result.warnings)


@pytest.mark.parametrize(
    ("room", "expected"),
    [
        ("5145(신공학관(기숙사) 401-5145 강의실)", ("5145", "신공학관", "강의실")),
        (
            "6119(신공학관(기숙사) 401-6119 컴퓨터AI학부 실습실4)",
            ("6119", "신공학관", "컴퓨터AI학부 실습실4"),
        ),
        ("301(혜화관 402-301)", ("301", "혜화관", None)),
        ("온라인 강의", (None, None, None)),
        (None, (None, None, None)),
    ],
)
def test_parse_room(room: str | None, expected: tuple[str | None, ...]) -> None:
    assert parse_room(room) == expected


@pytest.mark.parametrize(
    ("number", "floor"),
    [("5145", 5), ("6119", 6), ("301", 3), ("B101", -1), ("강의실", None), (None, None)],
)
def test_guess_floor(number: str | None, floor: int | None) -> None:
    assert guess_floor(number) == floor


@pytest.mark.parametrize("time", ["15:00-14:30", "10:00-10:00", "24:00-24:30", "09:60-10:30"])
def test_invalid_time_row_is_skipped(time: str) -> None:
    cell = '"과목\n301(혜화관 402-301 강의실)"'
    text = f"09:00-09:30\t{cell}\n{time}\t{cell}\n"

    result = parse_pasted_timetable(text)

    assert summary(text) == [("MON", "09:00", "09:30", "과목")]
    assert any("올바르지 않아" in w for w in result.warnings)
