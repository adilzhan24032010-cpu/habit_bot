import os
import asyncio
from aiohttp import web
import web
import asyncio
import logging
import os
import re
from datetime import datetime, time as dtime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")

# Price in Telegram Stars (XTR). 1 Star ~ $0.013-0.02 depending on region.
# 150 Stars ~ roughly $2-3, adjust as you like.
PREMIUM_PRICE_STARS = 50

router = Router()
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_website():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои привычки", callback_data="list")],
            [InlineKeyboardButton(text="⭐ Premium", callback_data="premium_info")],
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    await message.answer(
        "Привет! Я бот-трекер привычек 🌱\n\n"
        "Команды:\n"
        "/add <название> — добавить привычку\n"
        "/list — список привычек\n"
        "/done <номер> — отметить выполненной сегодня\n"
        "/remove <номер> — удалить привычку\n"
        "/time <номер> <ЧЧ:ММ> — время напоминания\n"
        "/premium — снять лимит и открыть все функции\n\n"
        f"Бесплатно: до {db.FREE_HABIT_LIMIT} привычек.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("add"))
async def cmd_add(message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    name = message.text.partition(" ")[2].strip()
    if not name:
        await message.answer("Использование: /add Читать 20 минут")
        return
    habit_id = db.add_habit(message.from_user.id, name)
    if habit_id is None:
        await message.answer(
            f"Достигнут бесплатный лимит ({db.FREE_HABIT_LIMIT} привычек).\n"
            "Оформи /premium, чтобы добавлять без ограничений."
        )
        return
    await message.answer(f"Добавлено: «{name}» (#{habit_id}). Напоминание по умолчанию — 09:00.\n"
                          f"Изменить время: /time {habit_id} 20:30")


@router.message(Command("list"))
async def cmd_list(message: Message):
    await send_habit_list(message.from_user.id, message)


async def send_habit_list(user_id: int, message: Message):
    habits = db.list_habits(user_id)
    if not habits:
        await message.answer("Пока нет привычек. Добавь: /add Пить воду")
        return
    lines = []
    for h in habits:
        streak = db.get_streak(h["habit_id"])
        lines.append(f"#{h['habit_id']} {h['name']} — ⏰ {h['remind_time']} — 🔥 стрик: {streak}")
    await message.answer("\n".join(lines))


@router.message(Command("done"))
async def cmd_done(message: Message):
    arg = message.text.partition(" ")[2].strip()
    if not arg.isdigit():
        await message.answer("Использование: /done <номер привычки>")
        return
    ok = db.mark_done(message.from_user.id, int(arg))
    if ok:
        streak = db.get_streak(int(arg))
        await message.answer(f"Отлично! Засчитано ✅ Текущий стрик: {streak} 🔥")
    else:
        await message.answer("Не найдено или уже отмечено сегодня.")


@router.message(Command("remove"))
async def cmd_remove(message: Message):
    arg = message.text.partition(" ")[2].strip()
    if not arg.isdigit():
        await message.answer("Использование: /remove <номер привычки>")
        return
    ok = db.remove_habit(message.from_user.id, int(arg))
    await message.answer("Удалено." if ok else "Не найдено.")


@router.message(Command("time"))
async def cmd_time(message: Message):
    parts = message.text.split()
    if len(parts) != 3 or not parts[1].isdigit() or not re.match(r"^\d{2}:\d{2}$", parts[2]):
        await message.answer("Использование: /time <номер> <ЧЧ:ММ>, например /time 1 21:00")
        return
    habit_id, remind_time = int(parts[1]), parts[2]
    if not db.is_premium(message.from_user.id):
        await message.answer("Гибкое время напоминаний доступно в /premium. Бесплатно — время фиксировано на 09:00.")
        return
    ok = db.set_remind_time(message.from_user.id, habit_id, remind_time)
    await message.answer("Готово ⏰" if ok else "Не найдено.")


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    if db.is_premium(message.from_user.id):
        await message.answer("У тебя уже активен Premium ⭐")
        return
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title="Premium подписка",
        description="Безлимит привычек + гибкое время напоминаний + приоритетная поддержка",
        payload="premium_subscription",
        currency="XTR",
        prices=[LabeledPrice(label="Premium (1 месяц)", amount=PREMIUM_PRICE_STARS)],
        provider_token="",  # not needed for Telegram Stars
    )


@router.callback_query(F.data == "list")
async def cb_list(callback: CallbackQuery):
    await send_habit_list(callback.from_user.id, callback.message)
    await callback.answer()


@router.callback_query(F.data == "premium_info")
async def cb_premium_info(callback: CallbackQuery):
    await callback.message.answer(
        f"⭐ Premium за {PREMIUM_PRICE_STARS} Stars/мес:\n"
        "— Безлимит привычек (бесплатно доступно 3)\n"
        "— Гибкое время напоминаний для каждой привычки\n"
        "— Приоритетная поддержка\n\n"
        "Оформить: /premium"
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    from datetime import timedelta
    until = (datetime.utcnow() + timedelta(days=30)).isoformat()
    db.set_premium(message.from_user.id, until)
    await message.answer("Спасибо! Premium активирован на 30 дней 🎉")


async def send_reminders(bot: Bot):
    now = datetime.utcnow().strftime("%H:%M")
    habits = db.all_habits_for_reminders()
    for h in habits:
        if h["remind_time"] == now:
            try:
                await bot.send_message(
                    h["uid"], f"⏰ Напоминание: «{h['name']}»\nОтметить: /done {h['habit_id']}"
                )
            except Exception as e:
                logger.warning(f"Failed to send reminder to {h['uid']}: {e}")


async def main(async def main():
    await start_website()  # <-- ДОБАВИТЬ ЭТУ СТРОЧКУ
    # дальше идет твой dp.start_polling(bot)):
    db.init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, "cron", minute="*", args=[bot])
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
