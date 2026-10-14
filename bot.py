"""Stateless aiogram 3 bot: requests survive free Render sleep without FSM storage."""

import re
from aiogram import Dispatcher, Router, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, BotCommand
from pydantic import ValidationError
from .schemas import RecommendRequest
from .engine import NoBuildError

HELP = (
    "VOLTRIX ⚡ Подбор совместимого ПК без платных AI API.\n\n"
    "/build 80000 gaming AMD NVIDIA\n"
    "/build 45000 office Intel any\n\n"
    "Задачи: gaming / игры, work / работа, office / офис.\n"
    "Бренды процессора: any, AMD, Intel. Видеокарты: any, AMD, NVIDIA.\n"
    "Бюджет: 15 000–500 000 ₽. Предпочтения можно пропустить.\n"
    "Цены расчётные, не актуальные предложения магазинов. Сверяйте перед покупкой.\n"
    "Бот не хранит сборки. Сохраняйте их на сайте в браузере."
)


def parse_build(text: str) -> RecommendRequest:
    args = text.split()[1:]
    if not 1 <= len(args) <= 4 or not re.fullmatch(r"\d{1,6}", args[0]):
        raise ValueError("Формат: /build 80000 gaming AMD NVIDIA")
    purpose = args[1].lower() if len(args) > 1 else "gaming"
    purpose = {"игры": "gaming", "работа": "work", "офис": "office"}.get(
        purpose, purpose
    )
    brands = {"any": "any", "amd": "AMD", "intel": "Intel", "nvidia": "NVIDIA"}
    return RecommendRequest(
        budget=int(args[0]),
        purpose=purpose,
        cpu_brand=brands.get(args[2].lower(), args[2]) if len(args) > 2 else "any",
        gpu_brand=brands.get(args[3].lower(), args[3]) if len(args) > 3 else "any",
    )


def format_build(result: dict, base_url: str) -> str:
    from .catalog import CATEGORIES

    lines = ["VOLTRIX ⚡ Ваша сборка", ""]
    for category, item in result["components"].items():
        lines.append(
            f"{CATEGORIES[category]}: {item['name']} — ~{item['calculation_rub']:,} ₽".replace(
                ",", " "
            )
        )
    lines += [
        "",
        f"Итого: ~{result['total_rub']:,} ₽".replace(",", " "),
        f"Расчётный запас БП: от {result['compatibility']['recommended_psu_w']} Вт.",
        "Цены примерные. Проверьте цены, BIOS/QVL и ревизии у производителя.",
    ]
    lines += result["compatibility"]["warnings"]
    if base_url:
        ids = ",".join(item["id"] for item in result["components"].values())
        lines += ["", f"{base_url}/configurator?parts={ids}"]
    return "\n".join(lines)


def create_dispatcher(recommend_async, base_url: str) -> Dispatcher:
    router = Router()

    @router.message(CommandStart())
    @router.message(Command("help"))
    async def help_handler(message: Message):
        await message.answer(HELP + (f"\n\nСайт: {base_url}" if base_url else ""))

    @router.message(Command("build"))
    async def build_handler(message: Message):
        try:
            req = parse_build(message.text or "")
            result = await recommend_async(req)
        except (ValueError, ValidationError, NoBuildError) as exc:
            message_text = (
                str(exc)
                if isinstance(exc, NoBuildError)
                else "Проверьте бюджет, задачу и бренды. Пример: /build 80000 gaming AMD NVIDIA"
            )
            await message.answer(message_text)
            return
        await message.answer(format_build(result, base_url))

    @router.message()
    async def fallback(message: Message):
        await message.answer(
            "Для подбора отправьте /build 80000 gaming. Все параметры: /help"
        )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def register_webhook(bot: Bot, base_url: str, secret: str):
    await bot.set_webhook(
        url=base_url + "/telegram/webhook",
        secret_token=secret,
        allowed_updates=["message"],
        drop_pending_updates=False,
        max_connections=1,
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="О сервисе и командах"),
            BotCommand(command="build", description="Подобрать ПК под бюджет"),
            BotCommand(command="help", description="Как пользоваться"),
        ]
    )
