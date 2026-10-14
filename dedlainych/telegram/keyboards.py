from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows
        ]
    )


def menu(admin=False):
    rows = [
        [("📚 Домашка на завтра", "tomorrow"), ("⚡ Узнать сейчас", "now")],
        [("📅 Расписание", "schedule"), ("📂 Все задания", "archive:0")],
        [("✅ Мои задания", "progress"), ("🔔 Уведомления", "notifications")],
        [("⚙️ Настройки", "settings"), ("❓ Помощь", "help")],
    ]
    if admin:
        rows.append([("👑 Админская", "admin")])
    return keyboard(rows)


def back(rows=None):
    return keyboard([*(rows or []), [("🏠 Главное меню", "home")]])


def task_buttons(tasks, done):
    return back(
        [
            [("✅" if h.id in done else "❌", f"toggle:{h.id}"), (f"📚 Задание #{h.id}", f"task:{h.id}")]
            for h in tasks
        ]
        + [[("📅 Другой день", "choose_day"), ("🔄 Обновить", "now")]]
    )
