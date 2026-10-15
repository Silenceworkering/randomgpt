"""Предметы из расписания, предоставленного владельцем группы 6104-ОБ."""

from datetime import date

from sqlalchemy import select

from dedlainych.db.models import Subject, WeeklyPlan

ALG = "Линейная алгебра и теория матриц"
HIST = "История России"
GRAPH = "Начертательная геометрия и инженерная графика"
PROG = "Основы программирования"
PYTHON = "Основы программирования на Python"
STATE = "Основы российской государственности"
ANALYSIS = "Математический анализ"
DIGITAL = "Цифровая грамотность"
ADAPT = "Адаптивный курс математики"
LANG = "Иностранный язык"
GEOM = "Начертательная геометрия"
SPORT = "Физическая культура и спорт"
CULTURE = "Культурология"
RUS = "Русский язык и деловая коммуникация"
INTRO = "Введение в профессию"

# weekday (Monday=0), time, subject, subgroup (0=both).
MONDAY = [
    (0, "08:15", ALG, 0),
    (0, "09:55", HIST, 0),
    (0, "11:35", GRAPH, 1),
    (0, "14:00", PROG, 1),
    (0, "14:00", GRAPH, 2),
]
FRIDAY = [(4, "08:15", DIGITAL, 1), (4, "08:15", LANG, 2), (4, "09:55", LANG, 1), (4, "09:55", DIGITAL, 2)]
WEEKS = {
    1: MONDAY
    + [
        (1, "08:15", ALG, 0),
        (1, "09:55", PYTHON, 0),
        (1, "11:35", STATE, 0),
        (2, "08:15", HIST, 0),
        (2, "09:55", ANALYSIS, 0),
        (2, "11:35", ANALYSIS, 0),
        (3, "08:15", DIGITAL, 0),
        (3, "09:55", STATE, 0),
        (3, "11:35", ADAPT, 0),
        (3, "14:00", PYTHON, 2),
    ]
    + FRIDAY
    + [(4, "11:35", GEOM, 0), (4, "14:00", SPORT, 0)],
    2: MONDAY
    + [
        (1, "08:15", CULTURE, 0),
        (1, "09:55", PYTHON, 0),
        (1, "11:35", STATE, 0),
        (1, "14:00", RUS, 0),
        (2, "08:15", HIST, 0),
        (2, "09:55", ANALYSIS, 0),
        (2, "11:35", ANALYSIS, 0),
        (2, "14:00", INTRO, 0),
        (3, "08:15", RUS, 0),
        (3, "09:55", CULTURE, 0),
        (3, "11:35", INTRO, 0),
        (3, "14:00", PYTHON, 2),
    ]
    + FRIDAY
    + [(4, "11:35", SPORT, 0)],
}
ALIASES = {
    ALG: ["линал", "линалу", "линейная алгебра", "алгебре"],
    HIST: ["история", "истории", "исторе"],
    GRAPH: ["инженерная графика", "инженерке", "инженерная графика и начертательная геометрия"],
    PROG: ["прога", "проге", "программированию"],
    PYTHON: ["python", "pyhon", "питон", "питону", "пайтон"],
    STATE: ["орг", "государственности"],
    ANALYSIS: ["матан", "матану", "матанализ", "матанализу"],
    DIGITAL: ["цифровая грамотность", "цифровой грамотности", "цифра", "цифре"],
    ADAPT: ["адаптив", "адаптиву", "адаптивной математике"],
    LANG: ["английский", "английскому", "англ", "иняз", "инязу", "иностранному"],
    GEOM: ["начерталка", "начерталке", "начертательной геометрии"],
    SPORT: ["физра", "физре", "физкультура"],
    CULTURE: ["культурологии", "культурка"],
    RUS: ["русский", "русскому", "деловая коммуникация"],
    INTRO: ["введению в профессию"],
}


async def configure_week(session, group: str, week: int, monday: date):
    if group != "6104-ОБ":
        raise ValueError("Этот шаблон предназначен только для 6104-ОБ")
    if week not in (1, 2) or monday.weekday() != 0:
        raise ValueError("Укажи неделю 1 или 2 и дату понедельника этой недели")
    rows = []
    for number, lessons in WEEKS.items():
        for weekday, start, name, subgroup in lessons:
            subject = await session.scalar(
                select(Subject).where(Subject.group_code == group, Subject.name == name)
            )
            if subject is None:
                subject = Subject(group_code=group, name=name, aliases=ALIASES.get(name, []))
                session.add(subject)
                await session.flush()
            else:
                subject.aliases = sorted(set(subject.aliases + ALIASES.get(name, [])))
            rows.append(
                dict(week=number, weekday=weekday, start=start, subject_id=subject.id, subgroup=subgroup)
            )
    plan = await session.get(WeeklyPlan, group)
    if plan is None:
        plan = WeeklyPlan(group_code=group)
        session.add(plan)
    plan.anchor_monday, plan.anchor_week, plan.lessons = monday, week, rows
    await session.flush()
