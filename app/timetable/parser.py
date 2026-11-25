"""엑셀 시간표를 복사해 붙여넣은 글자를 수업 목록으로 바꾼다.

엑셀 받는 곳: nDRIMS → 수업/강의평가 → 개인강의 시간표조회 → 톱니바퀴(설정) → 엑셀 다운로드.
이 시간표 엑셀(격자형)을 드래그·복사하면 이런 글자가 된다.
- 칸은 탭으로 나뉘고, 줄바꿈이 있는 칸은 따옴표로 감싸진다 (엑셀 기본 복사 형식).
- 첫 열은 30분 단위 시간(`10:30-11:00`), 나머지 열은 요일이다.
- 수업 칸은 `1주차~15주차` / `과목명` / `강의실` 3줄이고, 수업 시간 동안 칸마다 반복된다.
- 한 칸에 수업이 둘 있으면 3줄 묶음이 이어진다.

요일 머리글(월, 화, ...)이 있으면 그것을 따르고, 없으면 월요일부터 차례로 본다.
같은 요일에 이어지는 같은 수업 칸은 하나로 합친다.
"""

import csv
import io
import re
from dataclasses import dataclass, field

DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
DAY_BY_KOREAN = {
    "월": "MON",
    "화": "TUE",
    "수": "WED",
    "목": "THU",
    "금": "FRI",
    "토": "SAT",
    "일": "SUN",
}

TIME_RANGE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*[-~]\s*(\d{1,2}):(\d{2})\s*$")
WEEKS = re.compile(r"^\d+\s*주차\s*[~-]\s*\d+\s*주차$")
# 5145(신공학관(기숙사) 401-5145 강의실) → 호실 5145, 안쪽 "신공학관(기숙사) 401-5145 강의실"
ROOM = re.compile(r"^(?P<number>[^()\s]+)\s*\((?P<inner>.*)\)$")
ROOM_INNER = re.compile(r"^(?P<building>.+?)\s+\d+-\S+(?:\s+(?P<description>.+))?$")


@dataclass(frozen=True)
class ParsedCourse:
    name: str
    day: str  # MON ~ SUN
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    weeks: str | None  # 예: 1주차~15주차
    room: str | None  # 강의실 칸 원문
    room_number: str | None  # 예: 5145
    building_name: str | None  # 예: 신공학관 (괄호 설명은 뺀다)
    room_description: str | None  # 예: 컴퓨터AI학부 실습실4


@dataclass
class ParseResult:
    courses: list[ParsedCourse] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Entry:
    weeks: str | None = None
    name: str | None = None
    room: str | None = None


def _minutes(hour: str, minute: str) -> int:
    return int(hour) * 60 + int(minute)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _header_days(row: list[str]) -> list[str] | None:
    """첫 줄이 요일 머리글이면 열 순서대로 요일을 돌려준다."""
    if not row or TIME_RANGE.match(row[0]):
        return None
    days = []
    for cell in row[1:]:
        text = cell.strip()
        day = next((code for ko, code in DAY_BY_KOREAN.items() if text.startswith(ko)), None)
        if day is None and text.upper()[:3] in DAYS:
            day = text.upper()[:3]
        days.append(day or "")
    return days if any(days) else None


def _cell_entries(text: str) -> list[_Entry]:
    """칸 하나를 수업 묶음(주차, 과목명, 강의실)으로 나눈다."""
    entries: list[_Entry] = []
    for line in (raw.strip() for raw in text.splitlines()):
        if not line:
            continue
        if WEEKS.match(line):
            entries.append(_Entry(weeks=line))
            continue
        if not entries or (entries[-1].name and entries[-1].room):
            entries.append(_Entry())
        current = entries[-1]
        if current.name is None:
            current.name = line
        else:
            current.room = line
    return [e for e in entries if e.name]


def parse_room(room: str | None) -> tuple[str | None, str | None, str | None]:
    """강의실 칸에서 (호실, 건물 이름, 설명)을 뽑는다. 형식이 다르면 (None, None, None)."""
    if not room:
        return None, None, None
    match = ROOM.match(room.strip())
    if not match:
        return None, None, None
    inner = ROOM_INNER.match(match["inner"].strip())
    if not inner:
        return match["number"], None, None
    building = re.sub(r"\(.*?\)", "", inner["building"]).strip() or None
    return match["number"], building, inner["description"]


def parse_pasted_timetable(text: str) -> ParseResult:
    result = ParseResult()
    rows = [
        row for row in csv.reader(io.StringIO(text), delimiter="\t") if any(c.strip() for c in row)
    ]
    if not rows:
        result.warnings.append("붙여넣은 내용이 비어 있습니다.")
        return result

    days = _header_days(rows[0])
    if days is not None:
        rows = rows[1:]

    # (요일, 과목명, 주차, 강의실) → 30분 칸들의 (시작, 끝) 분
    slots: dict[tuple[str, str, str | None, str | None], list[tuple[int, int]]] = {}
    for line_no, row in enumerate(rows, start=2 if days is not None else 1):
        time = TIME_RANGE.match(row[0]) if row else None
        if time is None:
            result.warnings.append(
                f"{line_no}번째 줄의 시간을 읽지 못해 건너뛰었습니다: {row[0][:20]!r}"
            )
            continue
        start, end = _minutes(time[1], time[2]), _minutes(time[3], time[4])
        in_day = all(int(time[i]) < 24 and int(time[i + 1]) < 60 for i in (1, 3))
        if not in_day or end <= start:
            result.warnings.append(
                f"{line_no}번째 줄의 시간이 올바르지 않아 건너뛰었습니다: {row[0].strip()[:20]!r}"
            )
            continue
        for col, cell in enumerate(row[1:]):
            if not cell.strip():
                continue
            day = days[col] if days is not None and col < len(days) else None
            if days is None:
                day = DAYS[col] if col < len(DAYS) else None
            if not day:
                result.warnings.append(
                    f"{line_no}번째 줄 {col + 2}번째 칸의 요일을 알 수 없어 건너뛰었습니다."
                )
                continue
            for entry in _cell_entries(cell):
                key = (day, entry.name or "", entry.weeks, entry.room)
                slots.setdefault(key, []).append((start, end))

    for (day, name, weeks, room), times in slots.items():
        number, building, description = parse_room(room)
        merged: list[list[int]] = []
        for start, end in sorted(set(times)):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            result.courses.append(
                ParsedCourse(
                    name=name,
                    day=day,
                    start_time=_hhmm(start),
                    end_time=_hhmm(end),
                    weeks=weeks,
                    room=room,
                    room_number=number,
                    building_name=building,
                    room_description=description,
                )
            )

    result.courses.sort(key=lambda c: (DAYS.index(c.day), c.start_time, c.name))
    if not result.courses and not result.warnings:
        result.warnings.append(
            "수업을 찾지 못했습니다. 시간표 엑셀의 표 부분을 복사했는지 확인해 주세요."
        )
    return result
