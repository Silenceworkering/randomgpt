import logging

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

from dedlainych.telegram.handlers import UI

log = logging.getLogger(__name__)


def build_dispatcher(sessions, config) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(UI(sessions, config).router)

    @dispatcher.errors()
    async def errors(event: ErrorEvent):
        # No message bodies, tokens or remote URL paths in logs.
        log.error("Ошибка обработки Telegram: %s", type(event.exception).__name__)
        if event.update.callback_query:
            try:
                await event.update.callback_query.answer(
                    "💀 Не получилось. Попробуй снова чуть позже.", show_alert=True
                )
            except Exception:
                pass
        return True

    return dispatcher
