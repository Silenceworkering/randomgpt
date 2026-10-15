import asyncio
import io
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape
from pathlib import PurePath
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from dedlainych.config import Settings
from dedlainych.db.models import (
    Attachment,
    ConnectedChat,
    Homework,
    Lesson,
    Source,
    Subject,
    User,
    UserSettings,
)
from dedlainych.db.repositories import (
    accessible,
    completed_ids,
    ingest,
    local_today,
    preferences,
    register,
    toggle_completion,
    set_completion,
    visible_homework,
)
from dedlainych.services.admin import is_admin
from dedlainych.services.ai import Analyzer
from dedlainych.services.attachments import ALLOWED, extract
from dedlainych.services.homework import LINE, summary
from dedlainych.services.group_6104 import configure_week
from dedlainych.services.schedule import import_schedule, lessons_on
from dedlainych.telegram.keyboards import back, keyboard, menu, task_buttons

from dedlainych.telegram.render import limit_html

log = logging.getLogger(__name__)


async def edit(callback: CallbackQuery, text: str, markup):
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(limit_html(text), reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


class UI:
    def __init__(self, sessions, config: Settings):
        self.sessions = sessions
        self.config = config
        self.analyzer = Analyzer(config)
        self.rate: dict[int, float] = {}
        self.chat_locks = defaultdict(asyncio.Lock)
        self.router = Router()
        self.router.message.register(self.start, CommandStart(), F.chat.type == "private")
        self.router.message.register(self.admin_command, Command("admin"), F.chat.type == "private")
        self.router.callback_query.register(self.callback)
        self.router.edited_message.register(self.group_message, F.chat.type.in_({"group", "supergroup"}))
        self.router.message.register(self.group_message, F.chat.type.in_({"group", "supergroup"}))
        self.router.message.register(self.private, F.chat.type == "private")

    async def start(self, message: Message):
        async with self.sessions() as session:
            prefs = await register(session, message.from_user.id, self.config.group_code)
            await session.commit()
            if prefs.registered:
                await message.answer(
                    await self.home_text(session, message.from_user.id),
                    reply_markup=menu(is_admin(message.from_user.id, self.config)),
                )
                return
        await message.answer(
            "💀 <b>Йоу! Я Дедлайныч 😎</b>\n\n"
            "Пока ты отдыхаешь, я слежу за дедлайнами!\n\n"
            "📚 Соберу домашку из подключённых чатов.\n📅 Подберу ДЗ к парам.\n"
            "⏰ Напомню о сдаче.\n\n🎓 АмГУ · 6104-ОБ\n\nВыбери подгруппу:",
            reply_markup=keyboard([[("1️⃣ Первая", "on_sub:1"), ("2️⃣ Вторая", "on_sub:2")]]),
        )

    async def home_text(self, session, uid):
        prefs = await session.get(UserSettings, uid)
        user = await session.get(User, uid)
        return (
            "💀 <b>ДЕДЛАЙНЫЧ</b>\n\nЙоу, студент! 😎\n"
            "Пока ты отдыхаешь,\nя слежу за дедлайнами!\n\n" + LINE + "\n"
            "📚 Соберу всю домашку.\n🧠 Разберусь в сообщениях.\n📅 Подберу ДЗ к парам.\n"
            "⏰ Напомню о заданиях.\n🔥 Спасу от неожиданной сдачи.\n"
            + LINE
            + f"\n🎓 Группа: {escape(user.group_code)}\n👥 Подгруппа: №{prefs.subgroup}\n\n👇 Что будем делать?"
        )

    async def callback(self, cb: CallbackQuery):
        uid, data = cb.from_user.id, cb.data or ""
        if not isinstance(cb.message, Message) or cb.message.chat.type != "private":
            await cb.answer("Открой личный чат с ботом", show_alert=True)
            return
        now = time.monotonic()
        if now - self.rate.get(uid, 0) < 0.4:
            await cb.answer("💀 Полсекундочки!")
            return
        self.rate[uid] = now
        if len(self.rate) > 10000:
            self.rate = {k: v for k, v in self.rate.items() if now - v < 60}
        try:
            await cb.answer()
        except TelegramBadRequest:
            # After a Render cold start Telegram may expire the callback toast.
            # The authenticated action and editing its message are still valid.
            pass
        try:
            async with self.sessions() as session:
                prefs = await session.get(UserSettings, uid)
                if not prefs:
                    await edit(cb, "💀 Сначала нажми /start", back())
                    return
                if data.startswith("on_sub:"):
                    await preferences(session, uid, subgroup=int(data.split(":")[1]))
                    await edit(
                        cb,
                        "⏰ Во сколько присылать сводку? Позже время можно изменить.",
                        keyboard(
                            [
                                [("19:00", "on_time:19:00"), ("20:30", "on_time:20:30")],
                                [("22:00", "on_time:22:00"), ("🔕 Отключить", "on_time:off")],
                            ]
                        ),
                    )
                elif data.startswith("on_time:"):
                    value = data.removeprefix("on_time:")
                    await preferences(
                        session,
                        uid,
                        enabled=value != "off",
                        **(
                            {"notify_time": datetime.strptime(value, "%H:%M").time()}
                            if value != "off"
                            else {}
                        ),
                    )
                    await edit(
                        cb,
                        "🌍 Выбери часовой пояс. Благовещенск — Asia/Yakutsk (UTC+9).",
                        keyboard(
                            [
                                [("Благовещенск", "on_tz:Asia/Yakutsk")],
                                [("Москва", "on_tz:Europe/Moscow")],
                                [("Другой пояс", "custom_tz")],
                            ]
                        ),
                    )
                elif data.startswith("on_tz:"):
                    await preferences(session, uid, timezone=data.removeprefix("on_tz:"), registered=True)
                    await edit(cb, await self.home_text(session, uid), menu(is_admin(uid, self.config)))
                elif data == "custom_tz":
                    await edit(
                        cb, "🌍 Напиши: <code>пояс Asia/Yakutsk</code>\nМожно любой пояс IANA.", back()
                    )
                elif not prefs.registered and data != "home":
                    await edit(cb, "💀 Заверши регистрацию через /start", back())
                else:
                    await self.section(session, cb, uid, data, prefs)
                await session.commit()
        except (ValueError, PermissionError) as exc:
            await edit(cb, f"💀 {escape(str(exc))[:500]}", back())

    async def section(self, session, cb, uid, data, prefs):
        user = await session.get(User, uid)
        today = local_today(prefs.timezone)
        if data == "home":
            await edit(cb, await self.home_text(session, uid), menu(is_admin(uid, self.config)))
        elif data in {"now", "tomorrow"} or data.startswith("day:"):
            day = (
                date.fromisoformat(data[4:])
                if data.startswith("day:")
                else today + timedelta(days=data == "tomorrow")
            )
            text, tasks = await summary(session, uid, day)
            await edit(cb, text, task_buttons(tasks, await completed_ids(session, uid)))
        elif data == "choose_day":
            await edit(cb, "📅 Напиши <code>день 2026-10-16</code> с нужной датой.", back())
        elif data == "schedule":
            rows = await lessons_on(session, user.group_code, prefs.subgroup, today)
            names = {
                s.id: s.name
                for s in (
                    await session.scalars(select(Subject).where(Subject.group_code == user.group_code))
                ).all()
            }
            text = f"📅 <b>РАСПИСАНИЕ · {today:%d.%m.%Y}</b>\n{LINE}\n"
            text += (
                "\n\n".join(
                    f"⏰ {r.start:%H:%M}–{r.end:%H:%M}\n📚 {escape(names[r.subject_id])}\n"
                    f"🚪 {escape(r.room)} · {escape(r.teacher)}\n👥 {r.subgroup or 'Все'} · неделя {r.week or '—'}"
                    for r in rows[:15]
                )
                or "😴 На сегодня пар не найдено. Возможно, расписание ещё не загружено."
            )
            await edit(cb, limit_html(text), back([[("📅 Другой день", "choose_day")]]))
        elif data.startswith("archive:"):
            await self.archive(session, cb, uid, int(data.split(":")[1]))
        elif data == "progress":
            tasks = await visible_homework(session, uid)
            done = await completed_ids(session, uid)
            count = sum(h.id in done for h in tasks)
            await edit(
                cb,
                f"📊 <b>ТВОЙ ПРОГРЕСС</b>\n{LINE}\n📚 Всего: {len(tasks)}\n✅ Выполнено: {count}\n"
                f"⏳ Осталось: {len(tasks) - count}\n🔥 Прогресс: {round(100 * count / len(tasks)) if tasks else 0}%\n"
                "В архиве доступны выполненные задания.",
                back([[("📂 Архив", "archive:0")]]),
            )
        elif data in {"settings", "notifications"}:
            await edit(
                cb,
                f"⚙️ <b>НАСТРОЙКИ</b>\n{LINE}\n👥 Подгруппа №{prefs.subgroup}\n"
                f"⏰ {prefs.notify_time:%H:%M} · {escape(prefs.timezone)}\n"
                f"🔔 {'Включены' if prefs.enabled else 'Выключены'}\n"
                f"🚨 Выделение дедлайнов: {'да' if prefs.urgent_enabled else 'нет'}\n\n"
                + (
                    "🕒 Бесплатный режим: сводки проверяются раз в 30 минут, возможны задержки.\n"
                    if self.config.run_mode == "webhook"
                    else ""
                )
                + "Изменить время: <code>время 20:30</code>\n"
                "Изменить пояс: <code>пояс Asia/Yakutsk</code>",
                back(
                    [
                        [("1️⃣ Подгруппа", "sub:1"), ("2️⃣ Подгруппа", "sub:2")],
                        [("🔔 Вкл/выкл", "notify_toggle"), ("🚨 Вкл/выкл", "urgent_toggle")],
                    ]
                ),
            )
        elif data.startswith("sub:"):
            await preferences(session, uid, subgroup=int(data.split(":")[1]))
            await self.section(session, cb, uid, "settings", prefs)
        elif data in {"notify_toggle", "urgent_toggle"}:
            key = "enabled" if data == "notify_toggle" else "urgent_enabled"
            await preferences(session, uid, **{key: not getattr(prefs, key)})
            await self.section(session, cb, uid, "settings", prefs)
        elif data.startswith("complete:"):
            _, raw_id, raw_state = data.split(":")
            if raw_state not in {"0", "1"}:
                raise ValueError("Неверный статус")
            hid = int(raw_id)
            await set_completion(session, uid, hid, raw_state == "1")
            await self.task(session, cb, uid, hid)
        elif data.startswith("toggle:"):
            hid = int(data.split(":")[1])
            await toggle_completion(session, uid, hid)
            await session.flush()
            await self.task(session, cb, uid, hid)
        elif data.startswith("task:"):
            await self.task(session, cb, uid, int(data.split(":")[1]))
        elif data.startswith("files:"):
            h = await accessible(session, uid, int(data.split(":")[1]))
            if not h:
                raise PermissionError("Задание недоступно")
            attachments = (
                await session.scalars(select(Attachment).where(Attachment.source_id == h.source_id))
            ).all()
            for attachment in attachments[:10]:
                if attachment.kind == "photo":
                    await cb.message.answer_photo(attachment.file_id)
                else:
                    await cb.message.answer_document(attachment.file_id)
            if not attachments:
                await edit(cb, "📎 Прикреплённых материалов не найдено.", back())
        elif data == "help":
            await edit(
                cb,
                "💀 <b>ПОМОЩЬ</b>\n\n"
                "⚡ Узнать сейчас — ближайший учебный день с учётом подгруппы.\n"
                "📚 На завтра — сводка на следующий учебный день.\n"
                "✅ Выполнение видно только тебе.\n"
                "🔎 Поиск: <code>поиск интеграл</code>\n"
                "📚 Предмет: <code>предмет Математика</code>\n"
                "📅 Дата: <code>дата 2026-10-16</code>\n"
                "✅ Завершённые: <code>выполненные</code>\n"
                "📅 Другой день: <code>день 2026-10-16</code>\n\n"
                "Распознавание может ошибаться: сверяйся с источником. "
                "Если домашка не найдена, это не значит, что её нет.\n"
                "Я вижу только новые сообщения подключённых чатов, историю Telegram не читаю.\n"
                "Режим анализа: "
                + (
                    "локальная LLM Ollama с резервом"
                    if self.config.ai_provider == "ollama"
                    else "правила, без ИИ"
                ),
                back(),
            )
        elif data == "admin" or data.startswith(("review:", "approve:", "reject:")):
            await self.admin_callback(session, cb, uid, data, user.group_code)
        else:
            raise ValueError("Кнопка устарела. Открой главное меню.")

    async def task(self, session, cb, uid, hid):
        h = await accessible(session, uid, hid)
        if not h:
            raise PermissionError("Задание недоступно")
        subject = await session.get(Subject, h.subject_id) if h.subject_id else None
        source = await session.get(Source, h.source_id)
        done = hid in await completed_ids(session, uid)
        text = (
            f"📚 <b>#{h.id} {escape(subject.name if subject else 'Уточнить предмет')}</b>\n{LINE}\n"
            f"{escape(h.description)}\n\n📅 {h.due or 'Срок не указан'}\n"
            f"{'✅ Выполнено' if done else '❌ Не выполнено'}\n📥 Получено: {source.received_at:%d.%m.%Y}"
        )
        if source.link:
            text += f'\n🔗 <a href="{escape(source.link, quote=True)}">Источник</a>'
        await edit(
            cb,
            limit_html(text),
            back(
                [
                    [(("↩️ Вернуть" if done else "✅ Выполнено"), f"complete:{hid}:{0 if done else 1}")],
                    [("📎 Материалы", f"files:{hid}"), ("📂 Архив", "archive:0")],
                ]
            ),
        )

    async def archive(self, session, cb, uid, page):
        if page < 0:
            raise ValueError("Неверная страница")
        user = await session.get(User, uid)
        prefs = await session.get(UserSettings, uid)
        query = select(Homework).where(
            Homework.group_code == user.group_code,
            Homework.subgroup.in_([0, prefs.subgroup]),
            Homework.status == "approved",
        )
        rows = list(
            (await session.scalars(query.order_by(Homework.id.desc()).offset(page * 8).limit(9))).all()
        )
        done = await completed_ids(session, uid)
        text = f"📂 <b>АРХИВ · страница {page + 1}</b>\n{LINE}\n"
        text += (
            "\n".join(
                f"{'✅' if h.id in done else '⏳'} #{h.id} {escape(h.description[:120])}" for h in rows[:8]
            )
            or "Пока пусто. Дедлайныч на страже 👀"
        )
        buttons = [[(f"📚 #{h.id}", f"task:{h.id}")] for h in rows[:8]]
        nav = []
        if page:
            nav.append(("⬅️", f"archive:{page - 1}"))
        if len(rows) > 8:
            nav.append(("➡️", f"archive:{page + 1}"))
        if nav:
            buttons.append(nav)
        await edit(cb, text, back(buttons))

    async def admin_callback(self, session, cb, uid, data, group):
        if not is_admin(uid, self.config):
            raise PermissionError("Только для администраторов")
        if data == "admin":
            counts = {}
            for model in [User, Homework, ConnectedChat, Lesson]:
                counts[model.__name__] = await session.scalar(select(func.count()).select_from(model))
            await edit(
                cb,
                "👑 <b>АДМИНСКАЯ</b>\n"
                + LINE
                + f"\n👥 Пользователей: {counts['User']}\n📚 Заданий: {counts['Homework']}\n"
                f"💬 Чатов: {counts['ConnectedChat']}\n📅 Занятий: {counts['Lesson']}\n\n"
                "<code>/admin</code> — все команды управления.\n"
                "Отправь JSON-файл расписания для импорта.",
                back([[("🧐 Проверить задания", "review:0")]]),
            )
            return
        if data.startswith("review:"):
            page = int(data.split(":")[1])
            rows = (
                await session.scalars(
                    select(Homework)
                    .where(Homework.group_code == group, Homework.status == "pending")
                    .order_by(Homework.id)
                    .offset(max(0, page) * 5)
                    .limit(6)
                )
            ).all()
            text = "🧐 <b>НА ПРОВЕРКЕ</b>\n" + "\n\n".join(
                f"#{h.id} {escape(h.description[:250])}" for h in rows[:5]
            )
            buttons = [
                [(f"✅ #{h.id}", f"approve:{h.id}"), (f"🗑 #{h.id}", f"reject:{h.id}")] for h in rows[:5]
            ]
            if len(rows) > 5:
                buttons.append([("➡️ Далее", f"review:{page + 1}")])
            await edit(cb, text or "Проверять нечего", back(buttons))
            return
        action, hid = data.split(":")
        h = await session.get(Homework, int(hid))
        if not h or h.group_code != group:
            raise PermissionError("Задание другой группы или удалено")
        if action == "approve" and not h.subject_id:
            raise ValueError(f"Сначала назначь предмет: /admin subject {h.id} Название")
        h.status = "approved" if action == "approve" else "rejected"
        await session.flush()
        await self.admin_callback(session, cb, uid, "review:0", group)

    async def admin_command(self, message: Message):
        if not is_admin(message.from_user.id, self.config):
            await message.answer("🔒 Только для администраторов.")
            return
        parts = (message.text or "").split(maxsplit=3)
        help_text = (
            "👑 <b>УПРАВЛЕНИЕ</b>\n\n"
            "<code>/admin chat_add -1001234567890</code> — подключить чат\n"
            "<code>/admin chat_del -1001234567890</code> — отключить\n"
            "<code>/admin chats</code> — список\n"
            "<code>/admin week 1 2026-10-12</code> — неделя и её понедельник (6104-ОБ)\n"
            "<code>/admin week_off</code> — отключить повторение недель\n"
            "<code>/admin subjects</code> — предметы\n"
            "<code>/admin subject_add Математика|матеша|математика</code> — предмет и псевдонимы\n"
            "<code>/admin subject_rename 1 Новое название</code> — переименовать предмет\n"
            "<code>/admin subject_del 1</code> — удалить неиспользуемый предмет\n"
            "<code>/admin subject 12 Математика</code> — предмет задания\n"
            "<code>/admin due 12 2026-10-16</code> — срок (или none)\n"
            "<code>/admin text 12 Новое описание</code> — исправить текст\n"
            "<code>/admin delete 12</code> — убрать ошибочное задание\n"
            "<code>/admin inspect 12</code> — исходный текст и статус\n"
            "📅 Импорт: отправь JSON-документ, структура — в README.\n"
            "Перенос: измени дату в импорте и включи прежнюю пару с cancelled=true."
        )
        try:
            async with self.sessions() as session:
                await register(session, message.from_user.id, self.config.group_code)
                user = await session.get(User, message.from_user.id)
                group = user.group_code
                action = parts[1] if len(parts) > 1 else ""
                if action == "week":
                    await configure_week(session, group, int(parts[2]), date.fromisoformat(parts[3]))
                    await message.answer(
                        "✅ Предметы и чередование недель сохранены. ДЗ на завтра учитывает подгруппу. "
                        "Шаблон повторяется до отключения /admin week_off; каникулы и переносы не определяются автоматически."
                    )
                elif action == "week_off":
                    from dedlainych.db.models import WeeklyPlan

                    plan = await session.get(WeeklyPlan, group)
                    if plan:
                        await session.delete(plan)
                    await message.answer("✅ Повторение недель отключено. Задания сохранены.")
                elif action in {"chat_add", "chat_del"}:
                    cid = int(parts[2])
                    if cid >= 0:
                        raise ValueError("Нужен ID группы, начинающийся с -")
                    chat = await session.get(ConnectedChat, cid)
                    if action == "chat_add":
                        info = await message.bot.get_chat(cid)
                        member = await message.bot.get_chat_member(cid, message.bot.id)
                        if member.status in {"left", "kicked"}:
                            raise ValueError("Сначала добавь бота в чат")
                        if chat and chat.group_code != group:
                            raise PermissionError("Чат уже привязан к другой группе")
                        if not chat:
                            session.add(ConnectedChat(id=cid, group_code=group, title=info.title or ""))
                    elif chat and chat.group_code == group:
                        await session.delete(chat)
                    await message.answer(
                        "💬 Настройки чата сохранены. Privacy Mode отключи через BotFather /setprivacy."
                    )
                elif action in {"chats", "subjects"}:
                    model = ConnectedChat if action == "chats" else Subject
                    rows = (
                        await session.scalars(select(model).where(model.group_code == group).limit(50))
                    ).all()
                    await message.answer(
                        (
                            "\n".join(
                                escape(f"{r.id} — {r.title if action == 'chats' else r.name}") for r in rows
                            )
                            or "Пока пусто"
                        )[:4000]
                    )
                elif action in {"subject_rename", "subject_del"}:
                    subject = await session.get(Subject, int(parts[2]))
                    if not subject or subject.group_code != group:
                        raise PermissionError("Предмет недоступен")
                    if action == "subject_rename":
                        name = parts[3].strip()
                        if not name or len(name) > 200:
                            raise ValueError("Название от 1 до 200 символов")
                        conflict = await session.scalar(
                            select(Subject.id).where(
                                Subject.group_code == group, Subject.name == name, Subject.id != subject.id
                            )
                        )
                        if conflict:
                            raise ValueError("Предмет с таким названием уже есть")
                        subject.name = name
                    else:
                        used = await session.scalar(
                            select(func.count())
                            .select_from(Homework)
                            .where(Homework.subject_id == subject.id)
                        )
                        used += await session.scalar(
                            select(func.count()).select_from(Lesson).where(Lesson.subject_id == subject.id)
                        )
                        from dedlainych.db.models import WeeklyPlan

                        plan = await session.get(WeeklyPlan, group)
                        if used or (plan and any(r["subject_id"] == subject.id for r in plan.lessons)):
                            raise ValueError("Предмет используется: переименуй его вместо удаления")
                        await session.delete(subject)
                    await message.answer("📚 Справочник обновлён.")
                elif action == "subject_add":
                    values = " ".join(parts[2:]).split("|")
                    name = values[0].strip()
                    if not name or len(name) > 200:
                        raise ValueError("Название от 1 до 200 символов")
                    row = await session.scalar(
                        select(Subject).where(Subject.group_code == group, Subject.name == name)
                    )
                    if not row:
                        row = Subject(group_code=group, name=name)
                        session.add(row)
                    row.aliases = [v.strip() for v in values[1:] if v.strip()][:30]
                    await message.answer("📚 Предмет и псевдонимы сохранены.")
                elif action in {"subject", "due", "text", "delete", "inspect"}:
                    h = await session.get(Homework, int(parts[2]))
                    if not h or h.group_code != group:
                        raise PermissionError("Задание недоступно")
                    if action == "subject":
                        subject = await session.scalar(
                            select(Subject).where(Subject.group_code == group, Subject.name == parts[3])
                        )
                        if not subject:
                            raise ValueError("Сначала добавь предмет через subject_add")
                        h.subject_id = subject.id
                    elif action == "due":
                        h.due = None if parts[3] == "none" else date.fromisoformat(parts[3])
                    elif action == "text":
                        h.description = parts[3][:2000]
                        h.status = "pending"
                    elif action == "delete":
                        h.status = "rejected"
                    else:
                        source = await session.get(Source, h.source_id)
                        await message.answer(
                            limit_html(f"🧐 #{h.id} · {escape(h.status)}\n{escape(source.text[:3000])}")
                        )
                        materials = (
                            await session.scalars(select(Attachment).where(Attachment.source_id == source.id))
                        ).all()
                        for material in materials[:10]:
                            if material.kind == "photo":
                                await message.answer_photo(material.file_id)
                            else:
                                await message.answer_document(material.file_id)
                    if action != "inspect":
                        await message.answer("✅ Сохранено. Подтверждение — в админском меню.")
                else:
                    await message.answer(help_text)
                await session.commit()
        except (ValueError, IndexError, PermissionError) as exc:
            await message.answer("💀 Не получилось: " + escape(str(exc))[:500] + "\n/admin — подсказка")

    async def private(self, message: Message):
        uid = message.from_user.id
        if (
            message.document
            and is_admin(uid, self.config)
            and (message.document.file_name or "").endswith(".json")
        ):
            try:
                if not message.document.file_size or message.document.file_size > 1_000_000:
                    raise ValueError("Лимит импорта — 1 МБ")
                stream = io.BytesIO()
                await message.bot.download(message.document, destination=stream)
                async with self.sessions() as session:
                    await register(session, uid, self.config.group_code)
                    user = await session.get(User, uid)
                    count = await import_schedule(session, user.group_code, stream.getvalue())
                    await session.commit()
                await message.answer(f"📅 Импортировано занятий: {count}. Домашка сохранена.")
            except (ValueError, KeyError, TypeError) as exc:
                await message.answer("💀 Импорт отклонён: " + escape(str(exc))[:700])
            return
        text = (message.text or "").strip()
        try:
            async with self.sessions() as session:
                prefs = await session.get(UserSettings, uid)
                if not prefs:
                    await message.answer("💀 Нажми /start")
                    return
                if text.lower().startswith("время "):
                    await preferences(
                        session, uid, notify_time=datetime.strptime(text[6:].strip(), "%H:%M").time()
                    )
                    await message.answer("⏰ Время сохранено!")
                elif text.lower().startswith("пояс "):
                    await preferences(session, uid, timezone=text[5:].strip(), registered=True)
                    await message.answer(
                        "🌍 Часовой пояс сохранён!", reply_markup=menu(is_admin(uid, self.config))
                    )
                elif text.lower().startswith("день "):
                    result, tasks = await summary(session, uid, date.fromisoformat(text[5:].strip()))
                    await message.answer(
                        result, reply_markup=task_buttons(tasks, await completed_ids(session, uid))
                    )
                elif (
                    text.lower().startswith(("поиск ", "предмет ", "дата ")) or text.lower() == "выполненные"
                ):
                    user = await session.get(User, uid)
                    query = select(Homework).where(
                        Homework.group_code == user.group_code,
                        Homework.subgroup.in_([0, prefs.subgroup]),
                        Homework.status == "approved",
                    )
                    if text.lower().startswith("поиск "):
                        term = text[6:].strip().replace("%", "\\%").replace("_", "\\_")
                        query = query.where(Homework.description.ilike("%" + term + "%", escape="\\"))
                    elif text.lower().startswith("предмет "):
                        query = query.join(Subject).where(
                            func.lower(Subject.name) == text[8:].strip().lower()
                        )
                    elif text.lower().startswith("дата "):
                        query = query.where(Homework.due == date.fromisoformat(text[5:].strip()))
                    else:
                        ids = await completed_ids(session, uid)
                        query = query.where(Homework.id.in_(ids))
                    rows = (await session.scalars(query.order_by(Homework.id.desc()).limit(9))).all()
                    result = (
                        "\n\n".join(f"📚 #{h.id} {escape(h.description[:250])}" for h in rows[:8])
                        or "🔎 Ничего не найдено."
                    )
                    if len(rows) > 8:
                        result += "\nЕсть ещё результаты — уточни запрос или открой архив."
                    await message.answer(
                        result, reply_markup=back([[(f"📚 #{h.id}", f"task:{h.id}")] for h in rows[:8]])
                    )
                else:
                    await message.answer(
                        "💀 Выбери действие в меню. /start", reply_markup=menu(is_admin(uid, self.config))
                    )
                await session.commit()
        except (ValueError, KeyError) as exc:
            await message.answer("💀 Проверь формат: " + escape(str(exc))[:300])

    async def group_message(self, message: Message):
        # Chat-level serialization protects duplicates and edits within the single polling process.
        async with self.chat_locks[message.chat.id]:
            async with self.sessions() as session:
                if not await session.get(ConnectedChat, message.chat.id):
                    return
            content = message.text or message.caption or ""
            files = []
            attachment = message.photo[-1] if message.photo else message.document
            if attachment:
                name = "photo.jpg" if message.photo else (message.document.file_name or "file")
                kind = "photo" if message.photo else "document"
                files.append({"file_id": attachment.file_id, "kind": kind, "name": name[:255]})
                if (
                    attachment.file_size
                    and attachment.file_size <= self.config.max_file_bytes
                    and PurePath(name.lower()).suffix in ALLOWED
                ):
                    try:
                        stream = io.BytesIO()
                        await message.bot.download(attachment, destination=stream)
                        content += "\n" + await extract(stream.getvalue(), name, self.config.max_file_bytes)
                    except Exception:
                        # Preserve Telegram file_id even if parsing is unsafe/unavailable.
                        log.warning("Вложение не распознано; сохранено для проверки")
            link = None
            if message.chat.username:
                link = f"https://t.me/{message.chat.username}/{message.message_id}"
            elif str(message.chat.id).startswith("-100"):
                link = f"https://t.me/c/{str(message.chat.id)[4:]}/{message.message_id}"
            async with self.sessions() as session:
                rows = await ingest(
                    session,
                    self.analyzer,
                    message.chat.id,
                    message.message_id,
                    content,
                    files,
                    (message.edit_date or message.date).astimezone(ZoneInfo(self.config.tz)).date(),
                    link,
                    received_at=message.date,
                )
                await session.commit()
            if any(h.status == "pending" for h in rows):
                for admin_id in self.config.admin_ids:
                    try:
                        await message.bot.send_message(
                            admin_id,
                            "🧐 Дедлайныч нашёл сомнительное задание. Проверь его в админском меню.",
                            reply_markup=back([[("👑 Проверить", "review:0")]]),
                        )
                    except Exception:
                        log.warning("Не удалось доставить запрос проверки администратору")
