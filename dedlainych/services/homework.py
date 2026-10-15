from datetime import date, timedelta
from html import escape

from sqlalchemy import select

from dedlainych.db.models import Subject, User, UserSettings
from dedlainych.db.repositories import completed_ids, visible_homework
from dedlainych.services.schedule import lessons_on, next_day

from dedlainych.telegram.render import limit_html

LINE = "━━━━━━━━━━━━━━━━"


async def summary(session, user_id: int, start: date, nearest: bool = True):
    user = await session.get(User, user_id)
    prefs = await session.get(UserSettings, user_id)
    if not user or not prefs:
        return "💀 Нажми /start для регистрации.", []
    day = await next_day(session, user.group_code, prefs.subgroup, start) if nearest else start
    all_tasks = await visible_homework(session, user_id)
    done = await completed_ids(session, user_id)
    subjects = {
        s.id: s.name
        for s in (await session.scalars(select(Subject).where(Subject.group_code == user.group_code))).all()
    }
    if day is None:
        return (
            "📅 Расписание на ближайшие 120 дней пока не загружено.\n"
            "Дедлайны не потерялись — загляни в 📂 Все задания.",
            [],
        )
    lessons = await lessons_on(session, user.group_code, prefs.subgroup, day)
    subject_ids = {lesson.subject_id for lesson in lessons}
    tasks = [
        h
        for h in all_tasks
        if h.due == day or (h.subject_id in subject_ids and (h.due is None or h.due <= day))
    ]
    lines = [
        f"💀 <b>ДЕДЛАЙНЫЧ | ДОМАШКА</b>\n\n📅 {day:%d.%m.%Y}",
        f"🎓 {escape(user.group_code)} · 👥 №{prefs.subgroup}",
        LINE,
    ]
    if day != start:
        lines.append(f"😴 На {start:%d.%m} пар не найдено. Ближайший учебный день — {day:%d.%m}.")
    shown_subjects = set()
    for lesson in lessons[:12]:
        if lesson.subject_id in shown_subjects:
            continue
        shown_subjects.add(lesson.subject_id)
        lines.append(f"📚 <b>{lesson.start:%H:%M} — {escape(subjects.get(lesson.subject_id, 'Предмет'))}</b>")
        if not any(h.subject_id == lesson.subject_id for h in tasks):
            lines.append("😎 По этому предмету домашка пока не найдена!")
    for h in tasks[:10]:
        urgent = h.due is not None and h.due <= start + timedelta(days=1) and h.id not in done
        lines.extend(
            [
                LINE,
                f"{'🚨' if urgent else '📚'} <b>#{h.id} {escape(subjects.get(h.subject_id, 'Уточнить предмет'))}</b>",
                escape(h.description[:180]),
                f"📅 {h.due.strftime('%d.%m') if h.due else 'Срок не указан'} · "
                f"{'✅ Выполнено' if h.id in done else '❌ Не выполнено'}",
            ]
        )
    count = sum(h.id in done for h in tasks)
    lines.extend([LINE, f"🔥 Всего: {len(tasks)} · ✅ {count} · ⏳ {len(tasks) - count}"])
    if len(tasks) > 10:
        lines.append("Остальные задания — в архиве 📂")
    return limit_html("\n".join(lines)), tasks[:10]
